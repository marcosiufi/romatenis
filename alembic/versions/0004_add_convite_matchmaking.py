"""add convite_matchmaking to tipo_mensagem enum

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS requer PostgreSQL 9.3+ e é idempotente
    op.execute("ALTER TYPE tipo_mensagem ADD VALUE IF NOT EXISTS 'convite_matchmaking'")


def downgrade() -> None:
    # Remoção de valor de enum não é suportada diretamente pelo PostgreSQL;
    # requer recriar o tipo — deixado como no-op intencional.
    pass
