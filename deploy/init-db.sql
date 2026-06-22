-- Cria o banco do N8N no mesmo cluster PostgreSQL.
-- O banco principal (ranking_tenis) é criado pelo POSTGRES_DB env var.
SELECT 'CREATE DATABASE n8n'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'n8n'
)\gexec
