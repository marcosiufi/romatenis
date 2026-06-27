"""add hora_abertura hora_fechamento to configuracoes"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("configuracoes", sa.Column("hora_abertura", sa.Integer(), nullable=False, server_default="7"))
    op.add_column("configuracoes", sa.Column("hora_fechamento", sa.Integer(), nullable=False, server_default="22"))


def downgrade() -> None:
    op.drop_column("configuracoes", "hora_fechamento")
    op.drop_column("configuracoes", "hora_abertura")
