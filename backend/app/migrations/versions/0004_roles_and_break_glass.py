"""Roles, and the break-glass Administrator flag

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.Column("granted_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("user_id", "role"),
    )
    # Plain ADD COLUMN, never a table rebuild (see 0003).
    op.add_column(
        "users",
        sa.Column("is_break_glass", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "is_break_glass")
    op.drop_table("user_roles")
