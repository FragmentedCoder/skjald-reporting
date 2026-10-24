import csv
import io

import pytest
from sqlalchemy import select

from app import audit
from app.audit import AuditEntry
from app.roles import Role, grant_role


@pytest.fixture
def log(session, frozen_clock):
    """A small log over three days."""
    for day, action, actor, details in [
        (0, "auth.sign_in.succeeded", "astrid", {}),
        (0, "auth.sign_in.failed", None, {"reason": "unknown_user"}),
        (1, "admin.user_created", "admin", {"username": "=HYPERLINK(\"http://x\")"}),
        (2, "auth.sign_out", "astrid", {}),
    ]:
        frozen_clock.now = frozen_clock.now.replace(day=20 + day)
        audit.append(session, action, actor_name=actor, details=details)
    session.commit()


def entries(client, headers, **params):
    return client.get("/api/audit", headers=headers, params=params).json()


def test_entries_come_newest_first_in_pages(client, admin, log) -> None:
    _, headers = admin
    first = entries(client, headers, limit=2)
    assert [e["action"] for e in first["entries"]] == ["auth.sign_out", "admin.user_created"]
    rest = entries(client, headers, limit=2, before=first["next_before"])
    assert [e["action"] for e in rest["entries"]][:2] == [
        "auth.sign_in.failed", "auth.sign_in.succeeded"
    ]


# The admin fixture's own role grant is entry 1, logged before the frozen clock.
@pytest.mark.parametrize(("params", "expected"), [
    ({"action": "auth.*"},
     ["auth.sign_out", "auth.sign_in.failed", "auth.sign_in.succeeded", "auth.role.granted"]),
    ({"action": "auth.sign_out"}, ["auth.sign_out"]),
    ({"actor": "ASTRID"}, ["auth.sign_out", "auth.sign_in.succeeded"]),
    ({"since": "2026-10-21", "until": "2026-10-21"}, ["admin.user_created"]),
])
def test_entries_can_be_filtered(client, admin, log, params, expected) -> None:
    _, headers = admin
    assert [e["action"] for e in entries(client, headers, **params)["entries"]] == expected


def test_the_chain_is_checked_on_request(client, admin, log) -> None:
    _, headers = admin
    status = client.get("/api/audit/verify", headers=headers).json()
    assert status["ok"] and status["entries_checked"] == 5


def test_the_export_is_csv_safe_for_spreadsheets_and_logged(client, admin, log, session) -> None:
    _, headers = admin
    response = client.get("/api/audit/export", headers=headers, params={"action": "admin.*"})
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0][:5] == ["seq", "occurred_at", "actor_id", "actor_name", "action"]
    assert len(rows) == 2
    details = rows[1][8]
    assert details.startswith('{"username":"=HYPERLINK')  # JSON, so it starts with "{": safe

    exported = session.scalars(
        select(AuditEntry).where(AuditEntry.action == "audit.exported")
    ).one()
    session.commit()
    assert exported.details == '{"filters":{"action":"admin.*"},"rows":1}'


def test_a_cell_that_looks_like_a_formula_is_neutralised() -> None:
    from app.audit_routes import _cell

    assert _cell("=1+1") == "'=1+1"
    assert _cell("-5") == "'-5"
    assert _cell("@SUM(A1)") == "'@SUM(A1)"
    assert _cell("10.0.0.5") == "10.0.0.5"
    assert _cell(None) == ""


def test_auditors_read_the_log_and_technicians_do_not(
    client, make_user, session, full_session, log
) -> None:
    auditor = make_user("auditor", display_name="Aud Itor")
    grant_role(session, auditor, Role.AUDITOR, actor=None, ip=None)
    technician = make_user("tech", display_name="Tech")
    grant_role(session, technician, Role.TECHNICIAN, actor=None, ip=None)
    session.commit()
    assert client.get("/api/audit", headers=full_session(auditor)).status_code == 200
    assert client.get("/api/admin/users", headers=full_session(auditor)).status_code == 403
    assert client.get("/api/audit", headers=full_session(technician)).status_code == 403
