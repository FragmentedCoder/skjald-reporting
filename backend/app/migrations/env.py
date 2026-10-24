from alembic import context
from sqlalchemy.engine import Connection

import app.models  # noqa: F401
from app.db import Base, get_engine

if context.is_offline_mode():
    raise RuntimeError("Offline (SQL script) migrations are not supported.")


def run(connection: Connection) -> None:
    # No render_as_batch: batch mode rebuilds tables, and on SQLite with foreign keys
    # on, dropping the old copy deletes every row that cascades from it
    # (tests/test_migrations.py checks upgrades keep data).
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is None:
    with get_engine().connect() as conn:
        run(conn)
else:
    run(connection)
