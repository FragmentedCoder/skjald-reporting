"""The tamper-evident audit log (see docs/architecture.md, "Audit log").

Entries are numbered without gaps, and each entry's hash covers its own
contents and the previous entry's hash. Editing or removing an entry breaks
the chain from that point on, which verify() reports.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app import clock
from app.db import Base

GENESIS_HASH = "0" * 64

_HASHED_FIELDS = (
    "seq",
    "occurred_at",
    "actor_id",
    "actor_name",
    "action",
    "target_type",
    "target_id",
    "ip",
    "details",
    "prev_hash",
)


class AuditEntry(Base):
    __tablename__ = "audit_log"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    occurred_at: Mapped[str] = mapped_column(String(32), index=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, index=True)
    actor_name: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(100), index=True)
    target_type: Mapped[str | None] = mapped_column(String(50))
    target_id: Mapped[str | None] = mapped_column(String(100))
    ip: Mapped[str | None] = mapped_column(String(45))
    details: Mapped[str] = mapped_column(Text)
    prev_hash: Mapped[str] = mapped_column(String(64), unique=True)
    hash: Mapped[str] = mapped_column(String(64), unique=True)


@dataclass(frozen=True)
class ChainCheck:
    ok: bool
    entries_checked: int
    first_bad_seq: int | None = None
    problem: str | None = None


def timestamp(moment: datetime) -> str:
    """The form occurred_at is stored in. It sorts as text, so time ranges compare as strings."""
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(values: Mapping[Any, Any]) -> str:
    payload = {name: values[name] for name in _HASHED_FIELDS}
    return hashlib.sha256(_dumps(payload).encode()).hexdigest()


def append(
    session: Session,
    action: str,
    *,
    actor_id: int | None = None,
    actor_name: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    ip: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> AuditEntry:
    """Add an entry to the caller's transaction.

    It commits or rolls back together with the action it records, so neither
    can exist without the other. Never put secrets, passwords or codes in details.
    """
    last = session.execute(
        select(AuditEntry.seq, AuditEntry.hash).order_by(AuditEntry.seq.desc()).limit(1)
    ).first()
    values: dict[str, Any] = {
        "seq": last.seq + 1 if last else 1,
        "occurred_at": timestamp(clock.utcnow()),
        "actor_id": actor_id,
        "actor_name": actor_name,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "ip": ip,
        "details": _dumps(dict(details or {})),
        "prev_hash": last.hash if last else GENESIS_HASH,
    }
    entry = AuditEntry(**values, hash=_hash(values))
    session.add(entry)
    session.flush()
    return entry


def verify(session: Session, batch_size: int = 1000) -> ChainCheck:
    """Walk the whole chain from the first entry and report the first break, if any.

    The chain alone cannot show that the newest entries were removed; the daily
    timestamp of the chain head is what catches that.
    """
    columns = [getattr(AuditEntry, name) for name in (*_HASHED_FIELDS, "hash")]
    rows = session.execute(
        select(*columns).order_by(AuditEntry.seq).execution_options(yield_per=batch_size)
    )
    expected_seq = 1
    expected_prev = GENESIS_HASH
    for row in rows:
        entry = row._mapping
        if entry["seq"] != expected_seq:
            return ChainCheck(False, expected_seq - 1, expected_seq, "the entry is missing")
        if entry["prev_hash"] != expected_prev:
            return ChainCheck(
                False, expected_seq - 1, expected_seq, "it does not link to the entry before it"
            )
        if _hash(entry) != entry["hash"]:
            return ChainCheck(
                False, expected_seq - 1, expected_seq, "it was changed after it was written"
            )
        expected_prev = entry["hash"]
        expected_seq += 1
    return ChainCheck(True, expected_seq - 1)
