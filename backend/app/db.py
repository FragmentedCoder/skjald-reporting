from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import sqlcipher3
from sqlalchemy import DateTime, create_engine, event
from sqlalchemy.engine import Connection, Dialect, Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import QueuePool
from sqlalchemy.types import TypeDecorator

from app.crypto.key_files import load_or_create_database_key
from app.settings import settings


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator[datetime]):
    """Stores UTC without an offset (SQLite has no time zones) and returns aware datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetime: use clock.utcnow().")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


def _connect(db_path: Path, key: bytes) -> sqlcipher3.Connection:
    conn = sqlcipher3.connect(str(db_path), check_same_thread=False)
    conn.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
    conn.execute("PRAGMA cipher_memory_security = ON")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    # A wrong key fails here, not on PRAGMA key: SQLCipher only notices once it
    # has to parse an actual page.
    conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
    # SQLAlchemy emits BEGIN itself (see make_engine), so the driver must not.
    conn.isolation_level = None
    return conn


def make_engine(
    data_dir: str | Path | None = None, master_key_path: str | Path | None = None
) -> Engine:
    resolved_data_dir = Path(data_dir if data_dir is not None else settings.data_dir)
    resolved_master_key_path = (
        master_key_path if master_key_path is not None else settings.master_key_path
    )
    resolved_data_dir.mkdir(parents=True, exist_ok=True)
    db_path = resolved_data_dir / "skjald.db"
    key = load_or_create_database_key(resolved_data_dir, resolved_master_key_path)
    # module=sqlcipher3: without it SQLAlchemy assumes the stdlib sqlite3 module and
    # passes sqlcipher3's exceptions through unwrapped, so catching
    # sqlalchemy.exc.IntegrityError would never match.
    engine = create_engine(
        "sqlite://",
        module=sqlcipher3,
        creator=lambda: _connect(db_path, key),
        poolclass=QueuePool,
    )

    # SQLite allows one writer at a time anyway. Taking the write lock when a
    # transaction begins, rather than at its first write, means read-then-write
    # steps (the audit chain head, report numbers, job claims) never interleave
    # and never fail halfway with SQLITE_BUSY_SNAPSHOT.
    @event.listens_for(engine, "begin")
    def _begin_immediate(conn: Connection) -> None:
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


# Built lazily: importing this module must not require the master key to
# exist yet (tests build their own engines with make_engine() instead).
_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = make_engine()
    return _engine


def get_db() -> Generator[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False
        )
    session = _session_factory()
    try:
        yield session
    finally:
        session.close()


def check_integrity(bound_engine: Engine) -> list[str]:
    """Problems PRAGMA cipher_integrity_check found; empty means the database is intact."""
    with bound_engine.connect() as conn:
        rows = conn.exec_driver_sql("PRAGMA cipher_integrity_check").fetchall()
        return [row[0] for row in rows]
