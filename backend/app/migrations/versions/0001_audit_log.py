"""Audit log

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("seq", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("occurred_at", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_name", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=True),
        sa.Column("target_id", sa.String(length=100), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("seq"),
        sa.UniqueConstraint("prev_hash"),
        sa.UniqueConstraint("hash"),
    )
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_actor_id", "audit_log", ["actor_id"])
    op.create_index("ix_audit_log_occurred_at", "audit_log", ["occurred_at"])
    # Append-only at the database level too, so an application bug can't edit history.
    op.execute(
        "CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log "
        "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END"
    )
    op.execute(
        "CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log "
        "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END"
    )


def downgrade() -> None:
    op.drop_table("audit_log")
