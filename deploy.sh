#!/bin/bash
# Deploy da aplicação Ranking de Tênis
# Execute no diretório do projeto: bash deploy.sh
set -euo pipefail

echo "=== Deploy Ranking de Tênis | $(date '+%Y-%m-%d %H:%M:%S') ==="
echo ""

# Verifica se o .env existe
if [ ! -f .env ]; then
    echo "ERRO: arquivo .env não encontrado."
    echo "Execute: cp .env.example .env && nano .env"
    exit 1
fi

# ── 1. Atualiza código ────────────────────────────────────────────────────────
echo "▶ Atualizando código..."
git pull origin main

# ── 2. Constrói imagem API ────────────────────────────────────────────────────
echo "▶ Construindo imagem da API..."
docker compose build api

# ── 3. Sobe todos os serviços ─────────────────────────────────────────────────
echo "▶ Iniciando serviços..."
docker compose up -d

# ── 4. Aguarda o banco ficar pronto ──────────────────────────────────────────
echo "▶ Aguardando PostgreSQL..."
until docker compose exec -T db pg_isready -U "${DB_USER:-ranking}" -q; do
    sleep 2
done
echo "   PostgreSQL pronto."

# ── 5. Executa migrações ──────────────────────────────────────────────────────
echo "▶ Executando migrações Alembic..."
docker compose exec -T api alembic upgrade head

echo ""
echo "=== Deploy concluído ==="
echo ""
docker compose ps
echo ""
echo "Logs da API:"
docker compose logs --tail=20 api
echo ""
echo "────────────────────────────────────────────────"
echo "Primeiro deploy? Crie o admin interativamente:"
echo "  docker compose exec api python scripts/seed_admin.py"
echo "────────────────────────────────────────────────"
