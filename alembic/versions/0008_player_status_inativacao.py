"""player status e data_inativacao — regras de expiracao 7d e 90d

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column(
        "status", sa.String(20), nullable=False, server_default="ativo"
    ))
    op.add_column("players", sa.Column(
        "data_inativacao", sa.DateTime(timezone=True), nullable=True
    ))
    op.create_index("ix_players_status", "players", ["status"])


def downgrade() -> None:
    op.drop_index("ix_players_status", "players")
    op.drop_column("players", "data_inativacao")
    op.drop_column("players", "status")
