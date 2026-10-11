from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.core.database import Base
import app.models  # noqa: F401 — importa todos os modelos para o Alembic detectar as tabelas

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Usa DATABASE_URL do .env (converte asyncpg → psycopg2 para migrações síncronas)
_sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2").replace(
    "asyncpg://", "psycopg2://"
)
config.set_main_option("sqlalchemy.url", _sync_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # Uma transação por migration, não uma para o lote inteiro.
        #
        # O PostgreSQL proíbe usar um valor de enum na mesma transação em que
        # ele foi criado (`ALTER TYPE ... ADD VALUE`). A 0016 cria
        # 'aguardando_pagamento' e a 0030 o usa: num lote único, um banco novo
        # falhava com UnsafeNewEnumValueUsage. Produção nunca viu o erro porque
        # cada deploy aplicou uma migration de cada vez — mas recriar o banco do
        # zero (servidor novo, recuperação de desastre, ambiente local) quebrava.
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
