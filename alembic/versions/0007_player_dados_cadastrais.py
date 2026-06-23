"""player dados cadastrais — cpf, apelido, nascimento, endereco

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column("cpf",           sa.String(14),  nullable=True))
    op.add_column("players", sa.Column("data_nascimento", sa.Date(),     nullable=True))
    op.add_column("players", sa.Column("apelido",       sa.String(50),  nullable=True))
    op.add_column("players", sa.Column("rua",           sa.String(200), nullable=True))
    op.add_column("players", sa.Column("numero",        sa.String(20),  nullable=True))
    op.add_column("players", sa.Column("complemento",   sa.String(100), nullable=True))
    op.add_column("players", sa.Column("bairro",        sa.String(100), nullable=True))
    op.add_column("players", sa.Column("cidade",        sa.String(100), nullable=True))
    op.add_column("players", sa.Column("estado",        sa.String(2),   nullable=True))
    op.add_column("players", sa.Column("pais",          sa.String(50),  nullable=True, server_default="Brasil"))
    op.add_column("players", sa.Column("cep",           sa.String(9),   nullable=True))
    op.create_unique_constraint("uq_players_cpf", "players", ["cpf"])


def downgrade() -> None:
    op.drop_constraint("uq_players_cpf", "players", type_="unique")
    for col in ["cep", "pais", "estado", "cidade", "bairro", "complemento",
                "numero", "rua", "apelido", "data_nascimento", "cpf"]:
        op.drop_column("players", col)
