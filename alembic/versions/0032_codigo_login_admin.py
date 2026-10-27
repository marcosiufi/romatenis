"""codigo de login (segundo fator do admin) nos jogadores

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Só o hash do código vai ao banco; o código em si vai por e-mail e vive
    # dez minutos. As tentativas erradas são contadas para o código não poder
    # ser adivinhado dentro do prazo.
    op.add_column("players", sa.Column("codigo_login_hash", sa.String(64), nullable=True))
    op.add_column("players", sa.Column("codigo_login_expira", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "players",
        sa.Column("codigo_login_tentativas", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("players", "codigo_login_tentativas")
    op.drop_column("players", "codigo_login_expira")
    op.drop_column("players", "codigo_login_hash")
