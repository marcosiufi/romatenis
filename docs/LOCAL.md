# Rodar o Roma Tênis na máquina local

Para testar antes de publicar. Usa `docker-compose.local.yml`: projeto Docker
separado (`romatenis-local`), sem Caddy, sem `.env`, sem tocar em produção.

## Subir

```bash
docker compose -f docker-compose.local.yml up -d --build
docker compose -f docker-compose.local.yml exec api alembic upgrade head
docker compose -f docker-compose.local.yml exec api python scripts/seed_local.py
```

- App do associado: http://localhost:8100/app/
- Painel admin: http://localhost:8100/admin/

Porta **8100** (a 8000 costuma estar ocupada por outros projetos).

## Credenciais de teste

Só existem no banco local, criadas pelo `scripts/seed_local.py`:

| conta | e-mail | senha |
|---|---|---|
| Admin | `admin@teste.romatenis.com.br` | `roma-local-2026` |
| Associada (Ana) | `ana@teste.romatenis.com.br` | `roma-local-2026` |

O seed recusa rodar fora de `ENVIRONMENT=development`.

## Editar e ver

O código é montado como volume: CSS, HTML e JS aparecem no **F5** (sem
rebuild). Python recarrega sozinho. Se o navegador insistir na versão antiga,
`Ctrl+Shift+R`.

## Recriar do zero

```bash
docker compose -f docker-compose.local.yml down -v
```

e rode os três comandos de "Subir" de novo.

## Parar

```bash
docker compose -f docker-compose.local.yml down
```
