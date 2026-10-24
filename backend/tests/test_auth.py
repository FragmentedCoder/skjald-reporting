import hashlib

import pytest
import sqlcipher3
from sqlalchemy import select

from app.audit import AuditEntry, verify
from app.auth import sign_in as sign_in_module
from app.auth.dependencies import FullSession
from app.auth.sessions import COOKIE_NAME, UserSession
from app.main import app
from app.policy import SecurityPolicy, save_policy
from tests.conftest import PASSWORD


def _sign_in(client, username="astrid", password=PASSWORD, **kwargs):
    return client.post(
        "/api/auth/sign-in", json={"username": username, "password": password}, **kwargs
    )


def _audit(session, action):
    entries = session.scalars(select(AuditEntry).where(AuditEntry.action == action)).all()
    session.commit()  # end the read: an open transaction holds the write lock
    return entries


def test_sign_in_sets_a_hardened_session_cookie(client, make_user) -> None:
    make_user()
    response = _sign_in(client)

    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE_NAME}=")
    for attribute in ("HttpOnly", "Secure", "SameSite=strict", "Path=/"):
        assert attribute.lower() in cookie.lower()
    for attribute in ("Domain", "Max-Age", "expires"):
        assert attribute.lower() not in cookie.lower()

    body = response.json()
    assert body["user"]["username"] == "astrid"
    assert body["second_factor"] == "enrol"
    assert len(body["csrf_token"]) == 64


def test_only_a_hash_of_the_session_token_is_stored(client, make_user, session) -> None:
    make_user()
    token = _sign_in(client).cookies[COOKIE_NAME]
    stored = session.scalars(select(UserSession.token_hash)).one()
    assert stored != token
    assert stored == hashlib.sha256(token.encode()).hexdigest()


def test_the_password_check_runs_without_holding_the_database_lock(
    client, make_user, engine, monkeypatch
) -> None:
    make_user()
    observed = []
    real_verify = sign_in_module.verify_password

    def verify_while_probing(stored, password):
        pooled = engine.raw_connection()
        probe = pooled.driver_connection
        try:
            probe.execute("PRAGMA busy_timeout = 0")
            probe.execute("BEGIN IMMEDIATE")
            probe.execute("ROLLBACK")
            observed.append("free")
        except sqlcipher3.OperationalError:
            observed.append("locked")
        finally:
            probe.execute("PRAGMA busy_timeout = 30000")
            pooled.close()
        return real_verify(stored, password)

    monkeypatch.setattr(sign_in_module, "verify_password", verify_while_probing)
    assert _sign_in(client).status_code == 200
    assert observed == ["free"]


def test_every_kind_of_failure_gets_the_same_answer(client, make_user, session) -> None:
    make_user()
    inactive = make_user("bjorn", display_name="Bjørn")
    inactive.is_active = False
    session.commit()

    answers = [
        _sign_in(client, password="wrong password, long enough"),
        _sign_in(client, username="nobody-by-this-name"),
        _sign_in(client, username="bjorn"),
    ]

    assert {r.status_code for r in answers} == {401}
    assert len({r.text for r in answers}) == 1
    reasons = [e.details for e in _audit(session, "auth.sign_in.failed")]
    assert reasons == [
        '{"reason":"wrong_password"}',
        '{"reason":"unknown_user"}',
        '{"reason":"inactive"}',
    ]


def test_a_typed_username_that_matches_no_account_is_not_logged(client, session) -> None:
    _sign_in(client, username="Hunter2-typed-in-the-wrong-box")
    entry = _audit(session, "auth.sign_in.failed")[0]
    assert "Hunter2" not in f"{entry.actor_name} {entry.details} {entry.target_id}"


def test_an_account_locks_after_repeated_failures_and_unlocks_later(
    client, make_user, session, frozen_clock
) -> None:
    make_user()
    save_policy(session, SecurityPolicy(lockout_threshold=3, lockout_minutes=15))
    session.commit()

    for _ in range(3):
        _sign_in(client, password="wrong password, long enough")
    assert len(_audit(session, "auth.account.locked")) == 1

    locked = _sign_in(client)
    assert locked.status_code == 401
    assert _audit(session, "auth.sign_in.failed")[-1].details == '{"reason":"locked"}'

    frozen_clock.advance(minutes=16)
    assert _sign_in(client).status_code == 200


def test_a_password_alone_does_not_reset_the_failure_count(client, make_user, session) -> None:
    # Otherwise someone with the password could guess second-factor codes forever,
    # a few at a time between sign-ins. Only a full sign-in resets it (test_mfa.py).
    make_user()
    save_policy(session, SecurityPolicy(lockout_threshold=3))
    session.commit()

    for password in ("wrong one, long enough", "wrong two, long enough", PASSWORD):
        _sign_in(client, password=password)
    _sign_in(client, password="wrong three, long enough")

    assert _sign_in(client).status_code == 401


def test_one_address_trying_many_usernames_is_throttled(client, monkeypatch) -> None:
    monkeypatch.setattr(sign_in_module, "ADDRESS_MAX_FAILURES", 5)
    for i in range(5):
        assert _sign_in(client, username=f"guess-{i}").status_code == 401

    throttled = _sign_in(client, username="guess-5")
    assert throttled.status_code == 429
    assert throttled.headers["retry-after"] == "900"


def test_the_session_endpoint_needs_a_live_session(client, make_user) -> None:
    make_user()
    assert client.get("/api/auth/session").status_code == 401

    csrf = _sign_in(client).json()["csrf_token"]
    response = client.get("/api/auth/session")
    assert response.status_code == 200
    assert response.json()["csrf_token"] == csrf


def test_an_idle_session_ends(client, make_user, session, frozen_clock) -> None:
    make_user()
    _sign_in(client)
    frozen_clock.advance(minutes=29)
    assert client.get("/api/auth/session").status_code == 200

    frozen_clock.advance(minutes=31)
    assert client.get("/api/auth/session").status_code == 401
    assert session.scalars(select(UserSession)).all() == []


def test_a_session_ends_at_its_maximum_length_even_when_in_use(
    client, make_user, frozen_clock
) -> None:
    make_user()
    _sign_in(client)
    for _ in range(35):  # 11 h 40 min of steady use
        frozen_clock.advance(minutes=20)
        assert client.get("/api/auth/session").status_code == 200

    frozen_clock.advance(minutes=20)
    assert client.get("/api/auth/session").status_code == 401


def test_signing_out_needs_the_csrf_token_and_ends_the_session(client, make_user) -> None:
    make_user()
    csrf = _sign_in(client).json()["csrf_token"]

    assert client.post("/api/auth/sign-out").status_code == 403
    assert client.post("/api/auth/sign-out", headers={"X-CSRF-Token": "0" * 64}).status_code == 403

    response = client.post("/api/auth/sign-out", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 204
    assert COOKIE_NAME in response.headers["set-cookie"]
    assert client.get("/api/auth/session").status_code == 401


def test_a_stolen_cookie_is_useless_after_sign_out(client, make_user) -> None:
    make_user()
    response = _sign_in(client)
    token, csrf = response.cookies[COOKIE_NAME], response.json()["csrf_token"]
    client.post("/api/auth/sign-out", headers={"X-CSRF-Token": csrf})

    replayed = client.get("/api/auth/session", headers={"Cookie": f"{COOKIE_NAME}={token}"})
    assert replayed.status_code == 401


def test_writes_started_by_another_site_are_refused(client, make_user) -> None:
    make_user()
    response = _sign_in(client, headers={"Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403
    assert _sign_in(client, headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200


@pytest.fixture
def full_session_route():
    @app.get("/api/test-only/full")
    def full(_: FullSession) -> dict[str, bool]:
        return {"ok": True}

    yield "/api/test-only/full"
    app.router.routes.pop()


def test_a_password_alone_does_not_open_protected_routes(
    client, make_user, full_session_route
) -> None:
    make_user()
    _sign_in(client)
    response = client.get(full_session_route)
    assert response.status_code == 403
    assert "second factor" in response.json()["detail"]


def test_a_new_session_never_reuses_an_old_ones_id(client, make_user, session) -> None:
    # The audit log refers to sessions by ID; a reused ID would blur whose actions were whose.
    make_user()
    for _ in range(2):
        csrf = _sign_in(client).json()["csrf_token"]
        client.post("/api/auth/sign-out", headers={"X-CSRF-Token": csrf})
    sessions = [e.details for e in _audit(session, "auth.sign_in.succeeded")]
    assert sessions == ['{"session":1}', '{"session":2}']


def test_sign_ins_and_sign_outs_are_audited_in_an_unbroken_chain(
    client, make_user, session
) -> None:
    make_user()
    csrf = _sign_in(client).json()["csrf_token"]
    client.post("/api/auth/sign-out", headers={"X-CSRF-Token": csrf})

    succeeded = _audit(session, "auth.sign_in.succeeded")[0]
    assert (succeeded.actor_name, succeeded.ip) == ("astrid", "testclient")
    assert len(_audit(session, "auth.sign_out")) == 1
    assert verify(session).ok
