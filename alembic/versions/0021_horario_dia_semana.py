"""horario por dia da semana

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "horarios_dia_semana",
        sa.Column("dia_semana", sa.Integer, primary_key=True),
        sa.Column("aberto", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("hora_abertura", sa.Integer, nullable=False, server_default="7"),
        sa.Column("hora_fechamento", sa.Integer, nullable=False, server_default="22"),
    )
    op.bulk_insert(
        sa.table(
            "horarios_dia_semana",
            sa.column("dia_semana", sa.Integer),
            sa.column("aberto", sa.Boolean),
            sa.column("hora_abertura", sa.Integer),
            sa.column("hora_fechamento", sa.Integer),
        ),
        [
            {"dia_semana": i, "aberto": True, "hora_abertura": 7, "hora_fechamento": 22}
            for i in range(7)
        ],
    )


def downgrade() -> None:
    op.drop_table("horarios_dia_semana")
