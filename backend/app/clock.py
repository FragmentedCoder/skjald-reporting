from datetime import UTC, datetime


def utcnow() -> datetime:
    """The current time in UTC. Call it as clock.utcnow() so tests can move time."""
    return datetime.now(UTC)
