"""add foto_url to players

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("players", sa.Column("foto_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("players", "foto_url")
