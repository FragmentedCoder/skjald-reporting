"""Second factors: TOTP, passkeys, recovery codes

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "mfa_factors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("totp_secret", sa.String(length=64), nullable=True),
        sa.Column("totp_last_step", sa.Integer(), nullable=True),
        sa.Column("credential_id", sa.LargeBinary(), nullable=True),
        sa.Column("public_key", sa.LargeBinary(), nullable=True),
        sa.Column("sign_count", sa.Integer(), nullable=True),
        sa.Column("transports", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credential_id"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_mfa_factors_user_id", "mfa_factors", ["user_id"])
    op.create_table(
        "recovery_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("salt", sa.LargeBinary(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recovery_codes_user_id", "recovery_codes", ["user_id"])
    # Plain ADD COLUMN, never batch_alter_table: a batch rebuild drops the old table,
    # and with foreign keys on that deletes every row cascading from it.
    op.add_column("user_sessions", sa.Column("challenge", sa.LargeBinary(), nullable=True))
    op.add_column(
        "user_sessions", sa.Column("challenge_purpose", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "user_sessions", sa.Column("challenge_expires_at", sa.DateTime(), nullable=True)
    )
    op.add_column("users", sa.Column("webauthn_handle", sa.LargeBinary(), nullable=True))
    op.create_index("ix_users_webauthn_handle", "users", ["webauthn_handle"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_webauthn_handle", table_name="users")
    op.drop_column("users", "webauthn_handle")
    op.drop_column("user_sessions", "challenge_expires_at")
    op.drop_column("user_sessions", "challenge_purpose")
    op.drop_column("user_sessions", "challenge")
    op.drop_index("ix_recovery_codes_user_id", table_name="recovery_codes")
    op.drop_table("recovery_codes")
    op.drop_index("ix_mfa_factors_user_id", table_name="mfa_factors")
    op.drop_table("mfa_factors")
