"""slots_ranking + player reset_token"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "slots_ranking",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dia_semana", sa.Integer(), nullable=False),
        sa.Column("hora_inicio", sa.Time(), nullable=False),
        sa.Column("hora_fim", sa.Time(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column("players", sa.Column("reset_token", sa.String(255), nullable=True))
    op.add_column(
        "players",
        sa.Column("reset_token_expiracao", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("players", "reset_token_expiracao")
    op.drop_column("players", "reset_token")
    op.drop_table("slots_ranking")
