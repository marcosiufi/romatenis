#!/bin/bash
# Backup diário do banco do Roma Tênis.
#
#   pg_dump → gzip → cifra (AES-256, senha do .env) → 14 cópias locais → nuvem (rclone)
#
# Roda pelo cron (deploy/romatenis-backup.cron) e pode ser chamado à mão:
#   /opt/romatenis/scripts/backup_db.sh
#
# O arquivo vai cifrado porque o banco tem CPF, endereço e telefone de todo
# associado: a nuvem (ou um e-mail) não pode ser o lugar onde isso vaza. Sem
# BACKUP_SENHA o arquivo não abre — guarde a senha fora do servidor também,
# senão o backup não serve para nada no dia em que o servidor morrer.
#
# Qualquer falha manda e-mail (pelo SMTP do .env); toda segunda-feira sai um
# aviso de que o backup segue em dia — silêncio não é prova de nada.
#
# Variáveis (lidas do .env ao lado do docker-compose.yml, ou do ambiente):
#   BACKUP_SENHA           obrigatória — senha da cifra
#   BACKUP_RCLONE_REMOTE   destino na nuvem, ex. nuvem:RomaTenis/backups (vazio = só local)
#   BACKUP_EMAIL           quem recebe os avisos (padrão: SMTP_USER)
#   BACKUP_DIR             pasta local (padrão: ./backups)
#   COMPOSE_FILE           padrão docker-compose.yml
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

# Lê uma chave do .env sem "dar source" no arquivo: um valor com espaço ou
# cifrão quebraria o shell. Variável já presente no ambiente tem prioridade.
valor() {
    local atual="${!1:-}"
    if [ -n "$atual" ]; then printf '%s' "$atual"; return; fi
    [ -f .env ] || return 0
    sed -n "s/^$1=//p" .env | tail -1 | sed 's/^"\(.*\)"$/\1/; s/^'"'"'\(.*\)'"'"'$/\1/'
}

DB_USER="$(valor DB_USER)";            DB_USER="${DB_USER:-ranking}"
DB_NAME="$(valor DB_NAME)";            DB_NAME="${DB_NAME:-ranking_tenis}"
BACKUP_SENHA="$(valor BACKUP_SENHA)"
BACKUP_RCLONE_REMOTE="$(valor BACKUP_RCLONE_REMOTE)"
BACKUP_DIR="$(valor BACKUP_DIR)";      BACKUP_DIR="${BACKUP_DIR:-$DIR/backups}"
SMTP_HOST="$(valor SMTP_HOST)"; SMTP_PORT="$(valor SMTP_PORT)"; SMTP_PORT="${SMTP_PORT:-587}"
SMTP_USER="$(valor SMTP_USER)"; SMTP_PASS="$(valor SMTP_PASS)"
BACKUP_EMAIL="$(valor BACKUP_EMAIL)";  BACKUP_EMAIL="${BACKUP_EMAIL:-$SMTP_USER}"
export BACKUP_SENHA

avisar() {  # assunto corpo — pelo SMTP do .env, sem depender de programa de e-mail
    [ -n "$SMTP_HOST" ] && [ -n "$SMTP_USER" ] && [ -n "$BACKUP_EMAIL" ] || return 0
    local msg; msg="$(mktemp)"
    printf 'From: %s\nTo: %s\nSubject: %s\nContent-Type: text/plain; charset=UTF-8\n\n%s\n' \
        "$SMTP_USER" "$BACKUP_EMAIL" "$1" "$2" > "$msg"
    if [ "$SMTP_PORT" = "465" ]; then
        curl -sS --url "smtps://$SMTP_HOST:$SMTP_PORT" --user "$SMTP_USER:$SMTP_PASS" \
            --mail-from "$SMTP_USER" --mail-rcpt "$BACKUP_EMAIL" -T "$msg" >/dev/null || true
    else
        curl -sS --ssl-reqd --url "smtp://$SMTP_HOST:$SMTP_PORT" --user "$SMTP_USER:$SMTP_PASS" \
            --mail-from "$SMTP_USER" --mail-rcpt "$BACKUP_EMAIL" -T "$msg" >/dev/null || true
    fi
    rm -f "$msg"
}

falha() {
    echo "$(date '+%F %T') FALHA: $1" >&2
    avisar "FALHA no backup do banco do Roma Tenis" \
        "O backup de $(date '+%d/%m/%Y %H:%M') falhou: $1
Veja /var/log/romatenis-backup.log no servidor e corrija hoje: sem backup, um problema no disco leva cadastros, pagamentos e contratos."
    exit 1
}
trap 'falha "erro inesperado na linha $LINENO"' ERR

[ -n "$BACKUP_SENHA" ] || falha "BACKUP_SENHA não está no .env"
command -v openssl >/dev/null || falha "openssl não instalado"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
CARIMBO="$(date '+%Y-%m-%d_%H%M')"
ARQ="$BACKUP_DIR/romatenis-$CARIMBO.sql.gz.enc"

# O pipe inteiro falha se qualquer etapa falhar (pipefail): dump vazio não
# vira "backup ok".
docker compose -f "$COMPOSE_FILE" exec -T db pg_dump -U "$DB_USER" --no-owner --no-privileges "$DB_NAME" \
    | gzip -9 \
    | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:BACKUP_SENHA -out "$ARQ"
chmod 600 "$ARQ"

# Conferência: decifra e procura o cabeçalho do pg_dump. Um arquivo que não
# abre é pior que nenhum, porque dá a sensação de estar coberto.
TAMANHO="$(stat -c %s "$ARQ")"
[ "$TAMANHO" -gt 1024 ] || falha "arquivo pequeno demais ($TAMANHO bytes)"
# grep -c lê o dump inteiro: com pipefail, um grep -q que parasse no primeiro
# acerto derrubaria o gunzip com SIGPIPE e o pipeline sairia como falha
if ! openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_SENHA -in "$ARQ" \
        | gunzip | grep -c "PostgreSQL database dump" >/dev/null; then
    falha "o arquivo gerado não decifra ou não é um dump"
fi

# 14 cópias locais, as mais recentes (loop em vez de xargs: caminho com
# espaço quebraria o xargs)
ls -1t "$BACKUP_DIR"/romatenis-*.sql.gz.enc 2>/dev/null | tail -n +15 | while IFS= read -r antigo; do
    rm -f "$antigo"
done

# Nuvem: copia e descarta o que tem mais de 30 dias lá
if [ -n "$BACKUP_RCLONE_REMOTE" ]; then
    command -v rclone >/dev/null || falha "rclone não instalado (BACKUP_RCLONE_REMOTE definido)"
    rclone copy "$ARQ" "$BACKUP_RCLONE_REMOTE" --quiet || falha "rclone não conseguiu enviar para $BACKUP_RCLONE_REMOTE"
    rclone delete "$BACKUP_RCLONE_REMOTE" --min-age 30d --quiet || true
    ONDE="local e $BACKUP_RCLONE_REMOTE"
else
    ONDE="só local (BACKUP_RCLONE_REMOTE vazio)"
fi

echo "$(date '+%F %T') ok $(basename "$ARQ") ($TAMANHO bytes) — $ONDE"

# Prova de vida semanal
if [ "$(date +%u)" = "1" ]; then
    avisar "Backup do banco do Roma Tenis em dia" \
        "O backup diário segue funcionando. Último arquivo: $(basename "$ARQ") ($TAMANHO bytes), guardado em: $ONDE.
Para restaurar: scripts/restaurar_backup.sh (seção 22 do docs/SISTEMA.md)."
fi
