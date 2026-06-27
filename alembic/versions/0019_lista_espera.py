"""lista de espera do ranking + limite_ranking na configuracao

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Cria o enum com tratamento de duplicata (PostgreSQL nao suporta IF NOT EXISTS em CREATE TYPE)
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE statuslistaespera AS ENUM "
        "('aguardando', 'convocado', 'expirado', 'ativado', 'removido'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$"
    )
    op.create_table(
        "lista_espera",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "aguardando", "convocado", "expirado", "ativado", "removido",
                name="statuslistaespera",
                create_type=False,  # já criado acima com IF NOT EXISTS
            ),
            nullable=False,
            server_default="aguardando",
        ),
        sa.Column("data_inscricao", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_convocacao", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_expiracao_convocacao", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notas", sa.String(), nullable=True),
    )
    op.create_index("ix_lista_espera_player_id", "lista_espera", ["player_id"])
    op.create_index("ix_lista_espera_status", "lista_espera", ["status"])

    op.add_column(
        "configuracoes",
        sa.Column("limite_ranking", sa.Integer(), nullable=False, server_default="30"),
    )


def downgrade() -> None:
    op.drop_column("configuracoes", "limite_ranking")
    op.drop_index("ix_lista_espera_status", table_name="lista_espera")
    op.drop_index("ix_lista_espera_player_id", table_name="lista_espera")
    op.drop_table("lista_espera")
    op.execute("DROP TYPE IF EXISTS statuslistaespera")
