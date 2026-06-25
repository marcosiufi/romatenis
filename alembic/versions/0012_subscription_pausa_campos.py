"""Adiciona pausa_solicitada e pausa_motivo à tabela subscriptions

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-25
"""

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "subscriptions",
        sa.Column("pausa_solicitada", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "subscriptions",
        sa.Column("pausa_motivo", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("subscriptions", "pausa_motivo")
    op.drop_column("subscriptions", "pausa_solicitada")
