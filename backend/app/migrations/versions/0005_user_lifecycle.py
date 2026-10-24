"""Temporary passwords, last sign-in, theme

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Plain ADD COLUMN, never a table rebuild (see 0003).
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("users", sa.Column("password_expires_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("last_sign_in_at", sa.DateTime(), nullable=True))
    op.add_column(
        "users",
        sa.Column("theme", sa.String(length=10), nullable=False, server_default="system"),
    )


def downgrade() -> None:
    for column in ("theme", "last_sign_in_at", "password_expires_at", "must_change_password"):
        op.drop_column("users", column)
