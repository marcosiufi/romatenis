#!/bin/bash
# Restaura um backup feito por scripts/backup_db.sh.
#
#   /opt/romatenis/scripts/restaurar_backup.sh backups/romatenis-2026-10-28_0310.sql.gz.enc --confirmo
#
# SUBSTITUI o banco atual. O banco que estava no ar é renomeado para
# <nome>_antigo e fica lá até você apagar à mão — nada é destruído sem volta.
# Precisa da mesma BACKUP_SENHA que cifrou o arquivo (no .env ou no ambiente).
#
# Arquivo que está na nuvem: baixe antes com
#   rclone copy nuvem:RomaTenis/backups/romatenis-....sql.gz.enc /opt/romatenis/backups/
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

ARQ="${1:-}"
if [ -z "$ARQ" ] || [ ! -f "$ARQ" ]; then
    echo "uso: $0 ARQUIVO.sql.gz.enc --confirmo" >&2
    exit 2
fi
if [ "${2:-}" != "--confirmo" ]; then
    echo "Isto SUBSTITUI o banco atual pelo conteúdo de $ARQ." >&2
    echo "O banco atual é guardado como <nome>_antigo. Para seguir, repita com --confirmo." >&2
    exit 2
fi

valor() {
    local atual="${!1:-}"
    if [ -n "$atual" ]; then printf '%s' "$atual"; return; fi
    [ -f .env ] || return 0
    sed -n "s/^$1=//p" .env | tail -1 | sed 's/^"\(.*\)"$/\1/; s/^'"'"'\(.*\)'"'"'$/\1/'
}
DB_USER="$(valor DB_USER)"; DB_USER="${DB_USER:-ranking}"
DB_NAME="$(valor DB_NAME)"; DB_NAME="${DB_NAME:-ranking_tenis}"
BACKUP_SENHA="$(valor BACKUP_SENHA)"
[ -n "$BACKUP_SENHA" ] || { echo "BACKUP_SENHA ausente" >&2; exit 1; }
export BACKUP_SENHA

SQL="$(mktemp)"
trap 'rm -f "$SQL"' EXIT
echo "Decifrando $ARQ…"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_SENHA -in "$ARQ" | gunzip > "$SQL"
grep -q "PostgreSQL database dump" "$SQL" || { echo "O arquivo não é um dump válido (senha errada?)" >&2; exit 1; }

echo "Parando a API para ninguém gravar no meio da restauração…"
docker compose -f "$COMPOSE_FILE" stop api

ANTIGO="${DB_NAME}_antigo"
echo "Guardando o banco atual como $ANTIGO e criando $DB_NAME vazio…"
docker compose -f "$COMPOSE_FILE" exec -T db psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d postgres \
    -c "DROP DATABASE IF EXISTS \"$ANTIGO\";" \
    -c "ALTER DATABASE \"$DB_NAME\" RENAME TO \"$ANTIGO\";" \
    -c "CREATE DATABASE \"$DB_NAME\" OWNER \"$DB_USER\";"

echo "Restaurando…"
# stdout no /dev/null: o dump imprime o resultado de cada setval; erros
# continuam aparecendo (stderr) e param o script
docker compose -f "$COMPOSE_FILE" exec -T db psql -q -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" < "$SQL" > /dev/null

echo "Subindo a API…"
docker compose -f "$COMPOSE_FILE" start api

echo "Pronto. O banco anterior continua em $ANTIGO; quando tiver certeza de que está tudo certo:"
echo "  docker compose -f $COMPOSE_FILE exec -T db psql -U $DB_USER -d postgres -c 'DROP DATABASE \"$ANTIGO\";'"
