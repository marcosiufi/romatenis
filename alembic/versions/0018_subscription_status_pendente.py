"""add pendente to statusassinatura enum"""
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE statusassinatura ADD VALUE IF NOT EXISTS 'pendente'")


def downgrade() -> None:
    # PostgreSQL não permite remover valores de enum; downgrade é no-op.
    pass
