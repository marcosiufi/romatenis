"""subscription: add pausada status and pause fields

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE statusassinatura ADD VALUE IF NOT EXISTS 'pausada'")
    op.add_column("subscriptions", sa.Column("data_pausa", sa.DateTime(timezone=True), nullable=True))
    op.add_column("subscriptions", sa.Column("data_retorno_prevista", sa.DateTime(timezone=True), nullable=True))
    op.add_column("subscriptions", sa.Column("notas", sa.Text(), nullable=True))
    op.add_column("subscriptions", sa.Column("aviso_7d_enviado", sa.Boolean(), nullable=True, server_default="false"))
    op.add_column("subscriptions", sa.Column("aviso_1d_enviado", sa.Boolean(), nullable=True, server_default="false"))


def downgrade() -> None:
    op.drop_column("subscriptions", "aviso_1d_enviado")
    op.drop_column("subscriptions", "aviso_7d_enviado")
    op.drop_column("subscriptions", "notas")
    op.drop_column("subscriptions", "data_retorno_prevista")
    op.drop_column("subscriptions", "data_pausa")
