"""add horarios_especiais table"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "horarios_especiais",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("descricao", sa.String(100), nullable=False),
        sa.Column("fechado", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("hora_abertura", sa.Integer(), nullable=True),
        sa.Column("hora_fechamento", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("data"),
    )


def downgrade() -> None:
    op.drop_table("horarios_especiais")
