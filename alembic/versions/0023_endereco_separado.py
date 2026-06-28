"""separa campo endereco em campos individuais

Revision ID: 0023
Revises: 0022
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("configuracoes", sa.Column("end_logradouro", sa.String(300), nullable=False, server_default="Rua Minoru Mizutani"))
    op.add_column("configuracoes", sa.Column("end_numero",     sa.String(20),  nullable=False, server_default="99"))
    op.add_column("configuracoes", sa.Column("end_complemento",sa.String(100), nullable=False, server_default=""))
    op.add_column("configuracoes", sa.Column("end_bairro",     sa.String(200), nullable=False, server_default="Recreio das Acácias"))
    op.add_column("configuracoes", sa.Column("end_cidade",     sa.String(200), nullable=False, server_default="Ribeirão Preto"))
    op.add_column("configuracoes", sa.Column("end_estado",     sa.String(2),   nullable=False, server_default="SP"))
    op.add_column("configuracoes", sa.Column("end_pais",       sa.String(100), nullable=False, server_default="Brasil"))
    op.add_column("configuracoes", sa.Column("end_cep",        sa.String(10),  nullable=False, server_default="14098-555"))
    op.drop_column("configuracoes", "endereco")


def downgrade() -> None:
    op.add_column("configuracoes", sa.Column("endereco", sa.Text, nullable=False, server_default=""))
    for col in ["end_logradouro", "end_numero", "end_complemento", "end_bairro", "end_cidade", "end_estado", "end_pais", "end_cep"]:
        op.drop_column("configuracoes", col)
