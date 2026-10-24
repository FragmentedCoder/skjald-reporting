"""Reading the audit log: Administrators and Auditors (READ_AUDIT_LOG)."""

# No `from __future__ import annotations` here: FastAPI resolves the Filters class's
# annotations at runtime, and a class has no globals to resolve postponed ones from.
import csv
import io
import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import ColumnElement, select

from app import audit
from app.audit import AuditEntry, timestamp
from app.auth.dependencies import DB, client_ip, require
from app.auth.sessions import UserSession
from app.roles import Capability
from app.users import normalize_username

router = APIRouter(prefix="/audit")

Auditor = Annotated[UserSession, Depends(require(Capability.READ_AUDIT_LOG))]
PAGE_SIZE = 50
CSV_COLUMNS = ("seq", "occurred_at", "actor_id", "actor_name", "action", "target_type",
               "target_id", "ip", "details", "hash")
# A spreadsheet treats a cell starting with one of these as a formula (CSV injection).
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


class AuditEntryOut(BaseModel):
    seq: int
    occurred_at: str
    actor_name: str | None
    action: str
    target_type: str | None
    target_id: str | None
    ip: str | None
    details: dict[str, Any]


class AuditPage(BaseModel):
    entries: list[AuditEntryOut]
    next_before: int | None


class ChainStatus(BaseModel):
    ok: bool
    entries_checked: int
    first_bad_seq: int | None
    problem: str | None


class Filters:
    """The same filters for the list and the export. An action ending in `.*` matches a group."""

    def __init__(
        self,
        action: str | None = None,
        actor: str | None = None,
        since: date | None = None,
        until: date | None = None,
    ) -> None:
        self.values = {"action": action, "actor": actor, "since": since, "until": until}
        self.clauses: list[ColumnElement[bool]] = []
        if action and action.endswith(".*"):
            self.clauses.append(AuditEntry.action.startswith(action[:-1], autoescape=True))
        elif action:
            self.clauses.append(AuditEntry.action == action)
        if actor:
            self.clauses.append(AuditEntry.actor_name == normalize_username(actor))
        if since:
            self.clauses.append(AuditEntry.occurred_at >= _day_start(since))
        if until:
            self.clauses.append(AuditEntry.occurred_at < _day_start(until + timedelta(days=1)))


def _day_start(day: date) -> str:
    return timestamp(datetime.combine(day, time.min, tzinfo=UTC))


def _out(entry: AuditEntry) -> AuditEntryOut:
    return AuditEntryOut(
        seq=entry.seq, occurred_at=entry.occurred_at, actor_name=entry.actor_name,
        action=entry.action, target_type=entry.target_type, target_id=entry.target_id,
        ip=entry.ip, details=json.loads(entry.details),
    )


@router.get("")
def list_entries(
    _: Auditor,
    db: DB,
    filters: Annotated[Filters, Depends()],
    before: int | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = PAGE_SIZE,
) -> AuditPage:
    query = select(AuditEntry).where(*filters.clauses)
    if before is not None:
        query = query.where(AuditEntry.seq < before)
    rows = list(db.scalars(query.order_by(AuditEntry.seq.desc()).limit(limit + 1)))
    more = len(rows) > limit
    rows = rows[:limit]
    return AuditPage(entries=[_out(e) for e in rows], next_before=rows[-1].seq if more else None)


@router.get("/actions")
def list_actions(_: Auditor, db: DB) -> list[str]:
    return list(db.scalars(select(AuditEntry.action).distinct().order_by(AuditEntry.action)))


@router.get("/verify")
def verify_chain(_: Auditor, db: DB) -> ChainStatus:
    check = audit.verify(db)
    return ChainStatus(ok=check.ok, entries_checked=check.entries_checked,
                       first_bad_seq=check.first_bad_seq, problem=check.problem)


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(FORMULA_STARTS) else text


@router.get("/export")
def export_csv(
    request: Request, reader: Auditor, db: DB, filters: Annotated[Filters, Depends()]
) -> Response:
    rows = list(db.scalars(select(AuditEntry).where(*filters.clauses).order_by(AuditEntry.seq)))
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for entry in rows:
        writer.writerow([_cell(getattr(entry, column)) for column in CSV_COLUMNS])
    audit.append(
        db, "audit.exported", actor_id=reader.user.id, actor_name=reader.user.username,
        ip=client_ip(request),
        details={"rows": len(rows), "filters": {k: str(v) for k, v in filters.values.items() if v}},
    )
    db.commit()
    day = datetime.now(UTC).strftime("%Y%m%d")
    return Response(
        buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="skjald-audit-{day}.csv"'},
    )
