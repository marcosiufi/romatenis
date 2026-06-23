"""Converte status suspenso->inativo e adiciona novos valores de status

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-23
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Converte jogadores suspensos para inativo (status é String, sem migração de tipo)
    op.execute("UPDATE players SET status = 'inativo' WHERE status = 'suspenso'")


def downgrade() -> None:
    pass
