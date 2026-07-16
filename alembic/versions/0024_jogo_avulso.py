"""jogo avulso: convidados, match.avulso, participante convidado e preco

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Novo valor no enum de tipo de reserva (PG 16 aceita dentro de transação
    # desde que o valor não seja usado nesta mesma migration).
    op.execute("ALTER TYPE tiporeserva ADD VALUE IF NOT EXISTS 'jogo_avulso'")

    op.create_table(
        "convidados",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("cpf", sa.String(11), nullable=False),
        sa.Column("whatsapp", sa.String(20), nullable=False),
        sa.Column("data_nascimento", sa.Date(), nullable=False),
        sa.Column("apelido", sa.String(100), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_convidados_cpf", "convidados", ["cpf"])

    op.add_column(
        "matches",
        sa.Column("avulso", sa.Boolean(), nullable=False, server_default="false"),
    )

    op.add_column("match_participants", sa.Column("convidado_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_match_participants_convidado_id",
        "match_participants", "convidados",
        ["convidado_id"], ["id"],
    )
    op.alter_column("match_participants", "player_id", existing_type=sa.Integer(), nullable=True)

    op.add_column(
        "configuracoes",
        sa.Column("preco_jogo_avulso", sa.Numeric(10, 2), nullable=False, server_default="60.00"),
    )


def downgrade() -> None:
    op.drop_column("configuracoes", "preco_jogo_avulso")
    op.alter_column("match_participants", "player_id", existing_type=sa.Integer(), nullable=False)
    op.drop_constraint("fk_match_participants_convidado_id", "match_participants", type_="foreignkey")
    op.drop_column("match_participants", "convidado_id")
    op.drop_column("matches", "avulso")
    op.drop_index("ix_convidados_cpf", table_name="convidados")
    op.drop_table("convidados")
    # O valor 'jogo_avulso' permanece no enum — remover exige recriar o tipo.
