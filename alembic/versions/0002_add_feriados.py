"""add feriados table

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feriados",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("data", sa.Date, nullable=False),
        sa.Column("descricao", sa.String(100), nullable=False),
        sa.Column("recorrente", sa.Boolean, nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_table("feriados")
