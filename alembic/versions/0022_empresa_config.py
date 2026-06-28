"""dados da empresa na configuracao

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("configuracoes", sa.Column("razao_social", sa.String(300), nullable=False, server_default="Rosangela Pioli Siufi"))
    op.add_column("configuracoes", sa.Column("nome_fantasia", sa.String(300), nullable=False, server_default="Roma Tênis"))
    op.add_column("configuracoes", sa.Column("cnpj", sa.String(30), nullable=False, server_default="29.616.848/0001-21"))
    op.add_column("configuracoes", sa.Column("cpf_responsavel", sa.String(20), nullable=False, server_default="05405791814"))
    op.add_column("configuracoes", sa.Column("endereco", sa.Text, nullable=False, server_default="Rua Minoru Mizutani, 99, Recreio das Acácias, Ribeirão Preto-SP · CEP 14098-555"))
    op.add_column("configuracoes", sa.Column("whatsapp", sa.String(30), nullable=False, server_default="5516993618092"))
    op.add_column("configuracoes", sa.Column("instagram", sa.String(100), nullable=False, server_default="romatenisrp"))
    op.add_column("configuracoes", sa.Column("email_contato", sa.String(200), nullable=False, server_default="contato@romatenis.com.br"))


def downgrade() -> None:
    for col in ["razao_social", "nome_fantasia", "cnpj", "cpf_responsavel", "endereco", "whatsapp", "instagram", "email_contato"]:
        op.drop_column("configuracoes", col)
