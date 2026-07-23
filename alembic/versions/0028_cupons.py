"""cupons de desconto

Revision ID: 0028
Revises: 0027
Create Date: 2026-07-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cupons",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("codigo", sa.String(40), nullable=False),
        sa.Column("percentual", sa.Integer(), nullable=False),
        sa.Column("descricao", sa.String(200), nullable=True),
        sa.Column("validade_inicio", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validade_fim", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_usos", sa.Integer(), nullable=True),
        sa.Column("usos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cupons_codigo", "cupons", ["codigo"], unique=True)

    op.add_column("payments", sa.Column("cupom_codigo", sa.String(40), nullable=True))
    op.add_column("payments", sa.Column("valor_desconto", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("payments", "valor_desconto")
    op.drop_column("payments", "cupom_codigo")
    op.drop_index("ix_cupons_codigo", table_name="cupons")
    op.drop_table("cupons")
