"""add aguardando_pagamento to statusreserva enum"""
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE statusreserva ADD VALUE IF NOT EXISTS 'aguardando_pagamento'")


def downgrade() -> None:
    # PostgreSQL não permite remover valores de enum; downgrade é no-op.
    pass
