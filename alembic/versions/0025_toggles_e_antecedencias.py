"""toggles de contratacao/reserva e antecedencias configuraveis

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

MSG_PLANOS = (
    "Ainda não estamos aceitando contratações. Cadastre-se e entre "
    "na lista de espera para ser avisado assim que abrirmos!"
)
MSG_RESERVAS = (
    "Ainda não estamos aceitando reservas de quadra. "
    "Em breve liberaremos os agendamentos!"
)

COLUNAS = [
    ("contratacao_planos_ativa",  sa.Boolean(), "true"),
    ("reservas_ativas",           sa.Boolean(), "true"),
    ("msg_planos_desabilitado",   sa.Text(),    MSG_PLANOS),
    ("msg_reservas_desabilitado", sa.Text(),    MSG_RESERVAS),
    ("ranking_antecedencia_minima_horas", sa.Integer(), "6"),
    ("ranking_ultima_hora_horas",         sa.Integer(), "1"),
    ("jogo_avulso_ultima_hora_horas",     sa.Integer(), "1"),
    ("locacao_libera_slot_ranking_horas", sa.Integer(), "6"),
]


def upgrade() -> None:
    for nome, tipo, default in COLUNAS:
        op.add_column(
            "configuracoes",
            sa.Column(nome, tipo, nullable=False, server_default=default),
        )


def downgrade() -> None:
    for nome, _, _ in reversed(COLUNAS):
        op.drop_column("configuracoes", nome)
