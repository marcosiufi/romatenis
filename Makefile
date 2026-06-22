.PHONY: up down migrate seed dev lint

## Sobe PostgreSQL em background
up:
	docker compose up -d db

## Para todos os containers
down:
	docker compose down

## Roda a migration inicial (e qualquer pending)
migrate:
	alembic upgrade head

## Reverte a última migration
rollback:
	alembic downgrade -1

## Cria admin inicial interativamente
seed:
	python scripts/seed_admin.py

## Inicia o backend em modo de desenvolvimento (reload automático)
dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

## Gera nova migration a partir dos modelos
## Uso: make migration msg="descricao da mudanca"
migration:
	alembic revision --autogenerate -m "$(msg)"
