from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text

import app.models  # noqa: F401
from app.db import Base, make_engine
from app.migrate import upgrade


def test_the_migrations_build_exactly_the_schema_the_models_describe(engine) -> None:
    with engine.connect() as conn:
        differences = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert differences == []


def test_tables_whose_ids_reach_the_audit_log_never_reuse_an_id(engine) -> None:
    # compare_metadata doesn't look at AUTOINCREMENT, so check the migrations directly.
    autoincrement = {
        table.name for table in Base.metadata.tables.values()
        if table.kwargs.get("sqlite_autoincrement")
    }
    assert autoincrement == {"users", "user_sessions", "mfa_factors"}
    with engine.connect() as conn:
        for name in autoincrement:
            sql = conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :n"),
                {"n": name},
            ).scalar()
            assert "AUTOINCREMENT" in sql, name


def test_upgrading_keeps_existing_rows(data_dir, master_key_path) -> None:
    """SQLite rebuilds a table to change some constraints, and dropping the old copy
    with foreign keys on deletes every row that cascades from it. Data must survive."""
    engine = make_engine(data_dir, master_key_path)
    upgrade(engine, "0002")
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO users (id, username, display_name, is_active, failed_sign_ins, created_at)"
            " VALUES (1, 'astrid', 'Astrid', 1, 0, '2026-10-24 12:00:00')"
        ))
        conn.execute(text(
            "INSERT INTO user_sessions (token_hash, user_id, created_at, last_seen_at, expires_at)"
            " VALUES ('h', 1, '2026-10-24 12:00:00', '2026-10-24 12:00:00', '2026-10-25')"
        ))

    upgrade(engine)

    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM users")).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM user_sessions")).scalar() == 1
    engine.dispose()
