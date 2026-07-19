"""controle de lembretes de contrato pendente

Revision ID: 0026
Revises: 0025
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "players",
        sa.Column("contrato_lembretes_enviados", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "players",
        sa.Column("contrato_ultimo_lembrete_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("players", "contrato_ultimo_lembrete_em")
    op.drop_column("players", "contrato_lembretes_enviados")
