"""Bring the database schema up to date. Runs before the app starts (see the Dockerfile)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

from app.db import get_engine


def upgrade(engine: Engine | None = None, revision: str = "head") -> None:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    with (engine or get_engine()).connect() as conn:
        config.attributes["connection"] = conn
        command.upgrade(config, revision)


if __name__ == "__main__":
    upgrade()
