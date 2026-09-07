"""controle de acesso a quadra: leitores faciais, credenciais e janelas

Revision ID: 0031
Revises: 0030
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgENUM
from sqlalchemy.dialects.postgresql import JSONB

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def _cria_enum(nome: str, *valores: str) -> None:
    """PostgreSQL nao aceita IF NOT EXISTS em CREATE TYPE."""
    lista = ", ".join(f"'{v}'" for v in valores)
    op.execute(
        f"DO $$ BEGIN CREATE TYPE {nome} AS ENUM ({lista}); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )


def upgrade() -> None:
    _cria_enum("papel_dispositivo", "entrada", "saida")
    _cria_enum(
        "status_credencial",
        "pendente_foto", "pendente_envio", "sincronizada", "erro", "removida",
    )
    _cria_enum("status_janela", "ativa", "cancelada")
    _cria_enum("tipo_evento_acesso", "entrada", "saida", "negado", "abertura_remota")
    _cria_enum("status_comando_acesso", "pendente", "executado", "erro")

    # ── Configuracoes ────────────────────────────────────────────────────────
    for coluna in (
        sa.Column("acesso_ativo", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("acesso_minutos_antes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("acesso_minutos_depois", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("acesso_agente_token", sa.Text(), nullable=False, server_default=""),
        sa.Column("acesso_exige_selfie", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("acesso_agente_visto_em", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("configuracoes", coluna)

    # Selfie do convidado de jogo avulso.
    op.add_column("convidados", sa.Column("foto_url", sa.String(500), nullable=True))

    # ── Leitores ─────────────────────────────────────────────────────────────
    op.create_table(
        "dispositivos_acesso",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nome", sa.String(100), nullable=False),
        sa.Column(
            "papel",
            PgENUM("entrada", "saida", name="papel_dispositivo", create_type=False),
            nullable=False,
        ),
        sa.Column("modelo", sa.String(60), nullable=False, server_default="SS 3531 MF LITE"),
        sa.Column("host", sa.String(120), nullable=False),
        sa.Column("porta", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("usuario", sa.String(80), nullable=False, server_default="admin"),
        sa.Column("senha_cifrada", sa.Text(), nullable=False, server_default=""),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("ultimo_contato_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_erro", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── Credenciais ──────────────────────────────────────────────────────────
    op.create_table(
        "credenciais_acesso",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "player_id", sa.Integer(),
            sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=True, unique=True,
        ),
        sa.Column(
            "convidado_id", sa.Integer(),
            sa.ForeignKey("convidados.id", ondelete="CASCADE"), nullable=True, unique=True,
        ),
        sa.Column(
            "booking_id", sa.Integer(),
            sa.ForeignKey("bookings.id", ondelete="CASCADE"), nullable=True, unique=True,
        ),
        sa.Column("nome", sa.String(150), nullable=False),
        sa.Column("id_dispositivo", sa.String(20), nullable=False, unique=True),
        sa.Column("foto_url", sa.String(500), nullable=True),
        sa.Column("foto_hash", sa.String(64), nullable=True),
        sa.Column("token_selfie", sa.String(64), nullable=True, unique=True),
        sa.Column(
            "status",
            PgENUM(
                "pendente_foto", "pendente_envio", "sincronizada", "erro", "removida",
                name="status_credencial", create_type=False,
            ),
            nullable=False, server_default="pendente_foto",
        ),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column("sincronizada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        # Exatamente uma origem: associado, convidado ou cliente de locacao.
        sa.CheckConstraint(
            "(player_id IS NOT NULL)::int + (convidado_id IS NOT NULL)::int "
            "+ (booking_id IS NOT NULL)::int = 1",
            name="ck_credencial_uma_origem",
        ),
    )
    op.create_index("ix_credenciais_acesso_status", "credenciais_acesso", ["status"])

    # ── Janelas ──────────────────────────────────────────────────────────────
    op.create_table(
        "janelas_acesso",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "credencial_id", sa.Integer(),
            sa.ForeignKey("credenciais_acesso.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "booking_id", sa.Integer(),
            sa.ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fim", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            PgENUM("ativa", "cancelada", name="status_janela", create_type=False),
            nullable=False, server_default="ativa",
        ),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_janelas_acesso_credencial_id", "janelas_acesso", ["credencial_id"])
    op.create_index("ix_janelas_acesso_booking_id", "janelas_acesso", ["booking_id"])
    op.create_index("ix_janelas_acesso_periodo", "janelas_acesso", ["inicio", "fim"])

    # ── Eventos ──────────────────────────────────────────────────────────────
    op.create_table(
        "eventos_acesso",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "dispositivo_id", sa.Integer(),
            sa.ForeignKey("dispositivos_acesso.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "credencial_id", sa.Integer(),
            sa.ForeignKey("credenciais_acesso.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "tipo",
            PgENUM(
                "entrada", "saida", "negado", "abertura_remota",
                name="tipo_evento_acesso", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("momento", sa.DateTime(timezone=True), nullable=False),
        sa.Column("nome_lido", sa.String(150), nullable=True),
        sa.Column("motivo", sa.String(200), nullable=True),
        # Idempotencia: o agente reenvia lotes quando a rede falha.
        sa.Column("chave_externa", sa.String(120), nullable=False, unique=True),
        sa.Column("recebido_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_eventos_acesso_credencial_id", "eventos_acesso", ["credencial_id"])
    op.create_index("ix_eventos_acesso_momento", "eventos_acesso", ["momento"])

    # ── Comandos ─────────────────────────────────────────────────────────────
    op.create_table(
        "comandos_acesso",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tipo", sa.String(40), nullable=False),
        sa.Column("payload", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "status",
            PgENUM("pendente", "executado", "erro", name="status_comando_acesso", create_type=False),
            nullable=False, server_default="pendente",
        ),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("executado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_comandos_acesso_status", "comandos_acesso", ["status"])


def downgrade() -> None:
    op.drop_table("comandos_acesso")
    op.drop_table("eventos_acesso")
    op.drop_table("janelas_acesso")
    op.drop_table("credenciais_acesso")
    op.drop_table("dispositivos_acesso")

    op.drop_column("convidados", "foto_url")
    for coluna in (
        "acesso_agente_visto_em", "acesso_exige_selfie", "acesso_agente_token",
        "acesso_minutos_depois", "acesso_minutos_antes", "acesso_ativo",
    ):
        op.drop_column("configuracoes", coluna)

    for tipo in (
        "status_comando_acesso", "tipo_evento_acesso", "status_janela",
        "status_credencial", "papel_dispositivo",
    ):
        op.execute(f"DROP TYPE IF EXISTS {tipo}")
