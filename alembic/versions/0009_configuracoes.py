"""tabela configuracoes — precos editaveis pelo admin

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "configuracoes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("preco_mensal",       sa.Numeric(10, 2), nullable=False, server_default="89.90"),
        sa.Column("preco_trimestral",   sa.Numeric(10, 2), nullable=False, server_default="239.90"),
        sa.Column("preco_semestral",    sa.Numeric(10, 2), nullable=False, server_default="449.90"),
        sa.Column("preco_anual",        sa.Numeric(10, 2), nullable=False, server_default="839.90"),
        sa.Column("preco_locacao_hora", sa.Numeric(10, 2), nullable=False, server_default="120.00"),
    )
    # Insere a linha única de configuração com os defaults
    op.execute(
        "INSERT INTO configuracoes (id, preco_mensal, preco_trimestral, preco_semestral, preco_anual, preco_locacao_hora) "
        "VALUES (1, 89.90, 239.90, 449.90, 839.90, 120.00)"
    )


def downgrade() -> None:
    op.drop_table("configuracoes")
