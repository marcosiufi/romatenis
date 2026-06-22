"""initial

Revision ID: 0001
Revises:
Create Date: 2026-06-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ── Enum helpers ──────────────────────────────────────────────────────────────

_ENUMS = [
    ("niveljogador",            ["A", "B", "C", "D", "nao_classificado"]),
    ("tipopartida",             ["simples", "duplas"]),
    ("statuspartida",           ["agendado", "realizado", "cancelado_sem_placar", "wo"]),
    ("ladopartida",             ["A", "B"]),
    ("tiporeserva",             ["ranking", "locacao_avulsa", "aula"]),
    ("statusreserva",           ["confirmada", "cancelada"]),
    ("metodopagamento",         ["pix", "cartao", "boleto"]),
    ("statuspagamento",         ["pendente", "pago", "falhou", "estornado"]),
    ("planoassinatura",         ["mensal", "trimestral", "semestral", "anual"]),
    ("formapagamento",          ["pix_avista", "boleto_avista", "cartao_parcelado"]),
    ("statusassinatura",        ["ativa", "expirada", "inadimplente", "cancelada"]),
    ("statustemporada",         ["ativa", "encerrada"]),
    ("tipomensagem",            ["confirmacao_reserva", "lembrete_partida", "solicitacao_placar",
                                  "resultado_rating", "cobranca", "aviso_expiracao"]),
    ("statusenvio",             ["enviado", "falhou", "pendente"]),
    ("statusconvite",           ["pendente", "confirmado", "recusado", "expirado", "cancelado"]),
    ("statusrodadamatchmaking", ["aguardando", "confirmada", "falhou"]),
]


def _e(name: str) -> sa.Enum:
    return sa.Enum(name=name, create_type=False)


def upgrade() -> None:
    for name, values in _ENUMS:
        sa.Enum(*values, name=name).create(op.get_bind(), checkfirst=True)

    op.create_table(
        "seasons",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("data_inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_fim", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", _e("statustemporada"), nullable=False, server_default="ativa"),
        sa.Column("ranking_final", sa.JSON, nullable=True),
    )

    op.create_table(
        "players",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("nome", sa.String(150), nullable=False),
        sa.Column("telefone", sa.String(20), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("senha_hash", sa.String(255), nullable=False),
        sa.Column("is_admin", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("rating_atual", sa.Float, nullable=False, server_default="1000.0"),
        sa.Column("nivel", _e("niveljogador"), nullable=False, server_default="nao_classificado"),
        sa.Column("partidas_computadas_rating", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pontos_ranking_temporada_atual", sa.Integer, nullable=False, server_default="0"),
        sa.Column("aceita_convites_sistema", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("data_cadastro", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.Integer, sa.ForeignKey("players.id"), nullable=False),
        sa.Column("plano", _e("planoassinatura"), nullable=False),
        sa.Column("valor_mensal", sa.Numeric(10, 2), nullable=False),
        sa.Column("valor_total_ciclo", sa.Numeric(10, 2), nullable=False),
        sa.Column("forma_pagamento", _e("formapagamento"), nullable=False),
        sa.Column("parcelas", sa.Integer, nullable=False, server_default="1"),
        sa.Column("antecipacao_solicitada", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("status", _e("statusassinatura"), nullable=False, server_default="ativa"),
        sa.Column("data_inicio_ciclo", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_expiracao", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gateway_subscription_id", sa.String(255), nullable=True),
    )

    op.create_table(
        "matches",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tipo", _e("tipopartida"), nullable=False),
        sa.Column("status", _e("statuspartida"), nullable=False, server_default="agendado"),
        sa.Column("data_hora", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duracao_minutos", sa.Integer, nullable=True),
        sa.Column("placar", sa.JSON, nullable=True),
        sa.Column("lado_vencedor", sa.String(1), nullable=True),
        sa.Column("season_id", sa.Integer, sa.ForeignKey("seasons.id"), nullable=True),
    )

    op.create_table(
        "match_participants",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("match_id", sa.Integer, sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("player_id", sa.Integer, sa.ForeignKey("players.id"), nullable=False),
        sa.Column("lado", _e("ladopartida"), nullable=False),
        sa.Column("rating_antes", sa.Float, nullable=True),
        sa.Column("rating_depois", sa.Float, nullable=True),
        sa.Column("pontos_atribuidos", sa.Integer, nullable=True),
    )

    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("data_hora_inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_hora_fim", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tipo", _e("tiporeserva"), nullable=False),
        sa.Column("status", _e("statusreserva"), nullable=False, server_default="confirmada"),
        sa.Column("jogador_responsavel_id", sa.Integer, sa.ForeignKey("players.id"), nullable=True),
        sa.Column("cliente_locacao_nome", sa.String(150), nullable=True),
        sa.Column("cliente_locacao_telefone", sa.String(20), nullable=True),
        sa.Column("match_id", sa.Integer, sa.ForeignKey("matches.id"), nullable=True, unique=True),
        sa.Column("valor", sa.Numeric(10, 2), nullable=True),
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("booking_id", sa.Integer, sa.ForeignKey("bookings.id"), nullable=True),
        sa.Column("subscription_id", sa.Integer, sa.ForeignKey("subscriptions.id"), nullable=True),
        sa.Column("valor", sa.Numeric(10, 2), nullable=False),
        sa.Column("metodo", _e("metodopagamento"), nullable=False),
        sa.Column("status", _e("statuspagamento"), nullable=False, server_default="pendente"),
        sa.Column("gateway_id", sa.String(255), nullable=True),
        sa.Column("data_pagamento", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "whatsapp_message_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.Integer, sa.ForeignKey("players.id"), nullable=False),
        sa.Column("tipo", _e("tipomensagem"), nullable=False),
        sa.Column("status_envio", _e("statusenvio"), nullable=False, server_default="pendente"),
        sa.Column("wamid", sa.String(255), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_table(
        "match_invitations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tipo", _e("tipopartida"), nullable=False),
        sa.Column("slot_data_hora", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", _e("statusrodadamatchmaking"), nullable=False, server_default="aguardando"),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("booking_id", sa.Integer, sa.ForeignKey("bookings.id"), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_table(
        "match_invitation_players",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("invitation_id", sa.Integer, sa.ForeignKey("match_invitations.id"), nullable=False),
        sa.Column("player_id", sa.Integer, sa.ForeignKey("players.id"), nullable=False),
        sa.Column("lado_proposto", sa.String(1), nullable=False),
        sa.Column("status", _e("statusconvite"), nullable=False, server_default="pendente"),
        sa.Column("respondido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("wamid_convite", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("match_invitation_players")
    op.drop_table("match_invitations")
    op.drop_table("whatsapp_message_logs")
    op.drop_table("payments")
    op.drop_table("bookings")
    op.drop_table("match_participants")
    op.drop_table("matches")
    op.drop_table("subscriptions")
    op.drop_table("players")
    op.drop_table("seasons")

    for name, _ in reversed(_ENUMS):
        op.execute(f"DROP TYPE IF EXISTS {name}")
