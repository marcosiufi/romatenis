"""player contrato autentique

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column("contrato_autentique_id", sa.String(100), nullable=True))
    op.add_column("players", sa.Column("contrato_link_assinatura", sa.String(500), nullable=True))
    op.add_column("players", sa.Column("contrato_assinado", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("players", sa.Column("contrato_enviado_em", sa.DateTime(timezone=True), nullable=True))
    op.add_column("players", sa.Column("contrato_assinado_em", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("players", "contrato_assinado_em")
    op.drop_column("players", "contrato_enviado_em")
    op.drop_column("players", "contrato_assinado")
    op.drop_column("players", "contrato_link_assinatura")
    op.drop_column("players", "contrato_autentique_id")
