"""politica de cancelamento: prazo configuravel e cancelado_por no match

Revision ID: 0029
Revises: 0028
Create Date: 2026-07-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "configuracoes",
        sa.Column("cancelamento_antecedencia_horas", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column("matches", sa.Column("cancelado_por_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_matches_cancelado_por_id", "matches", "players",
        ["cancelado_por_id"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_matches_cancelado_por_id", "matches", type_="foreignkey")
    op.drop_column("matches", "cancelado_por_id")
    op.drop_column("configuracoes", "cancelamento_antecedencia_horas")
