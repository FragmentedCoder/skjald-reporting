import pyotp
import pytest
from sqlalchemy import select

from app.audit import AuditEntry
from app.policy import SecurityPolicy, save_policy
from tests.conftest import PASSWORD

NEW_PASSWORD = "en helt ny og lang adgangssætning"


def sign_in(browser, password=PASSWORD):
    return browser.post("/api/auth/sign-in", json={"username": "astrid", "password": password})


@pytest.fixture
def astrid(make_user, new_client):
    """Astrid, fully signed in with an authenticator app. Yields (browser, csrf headers)."""
    make_user()
    browser = new_client()
    csrf = {"X-CSRF-Token": sign_in(browser).json()["csrf_token"]}
    secret = browser.post("/api/auth/mfa/totp/enrol", headers=csrf).json()["secret"]
    done = browser.post("/api/auth/mfa/totp/confirm", headers=csrf,
                        json={"code": pyotp.TOTP(secret).now()}).json()
    return browser, {"X-CSRF-Token": done["session"]["csrf_token"]}


def actions(session):
    found = list(session.scalars(select(AuditEntry.action).order_by(AuditEntry.seq)))
    session.commit()
    return found


def test_the_account_page_shows_factors_codes_and_sessions(astrid) -> None:
    browser, _ = astrid
    account = browser.get("/api/account").json()
    assert account["username"] == "astrid"
    assert [f["kind"] for f in account["factors"]] == ["totp"]
    assert account["recovery_codes_left"] == 10
    assert [s["current"] for s in account["sessions"]] == [True]


def test_name_email_and_theme_can_be_changed(astrid, session) -> None:
    browser, csrf = astrid
    account = browser.patch("/api/account", headers=csrf, json={
        "display_name": "Astrid F.", "email": "astrid@example.com", "theme": "dark",
    }).json()
    assert (account["display_name"], account["email"], account["theme"]) == (
        "Astrid F.", "astrid@example.com", "dark"
    )
    assert browser.get("/api/auth/session").json()["user"]["theme"] == "dark"
    assert browser.patch("/api/account", headers=csrf, json={"theme": "pink"}).status_code == 422
    assert "account.updated" in actions(session)


def test_changing_the_password_needs_the_current_one(astrid, no_breach_found) -> None:
    browser, csrf = astrid
    attempt = {"current_password": "not it, but long", "new_password": NEW_PASSWORD}
    wrong = browser.post("/api/account/password", headers=csrf, json=attempt)
    assert wrong.status_code == 400


def test_changing_the_password_ends_other_sessions_and_rotates_this_one(
    astrid, new_client, no_breach_found, session
) -> None:
    browser, csrf = astrid
    other = new_client()
    sign_in(other)
    old_cookie = browser.cookies.get("__Host-skjald_session")

    changed = browser.post("/api/account/password", headers=csrf,
                           json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert changed.status_code == 200
    assert browser.cookies.get("__Host-skjald_session") != old_cookie
    assert other.get("/api/auth/session").status_code == 401
    assert sign_in(new_client(), NEW_PASSWORD).status_code == 200
    assert sign_in(new_client(), PASSWORD).status_code == 401
    assert "auth.password.changed" in actions(session)


def test_wrong_confirmation_passwords_count_towards_the_lockout(astrid, session) -> None:
    browser, csrf = astrid
    save_policy(session, SecurityPolicy(lockout_threshold=3))
    session.commit()
    for _ in range(2):
        refused = browser.post("/api/account/recovery-codes", headers=csrf,
                               json={"password": "a wrong guess, long"})
        assert refused.status_code == 400
    locked = browser.post("/api/account/recovery-codes", headers=csrf,
                          json={"password": "a wrong guess, long"})
    assert locked.status_code == 401
    assert browser.get("/api/auth/session").status_code == 401


def test_new_recovery_codes_replace_the_old_ones(astrid) -> None:
    browser, csrf = astrid
    codes = browser.post("/api/account/recovery-codes", headers=csrf,
                         json={"password": PASSWORD}).json()["recovery_codes"]
    assert len(codes) == 10
    assert browser.get("/api/account").json()["recovery_codes_left"] == 10


def test_the_last_second_factor_cannot_be_removed(astrid) -> None:
    browser, csrf = astrid
    factor = browser.get("/api/account").json()["factors"][0]
    refused = browser.post(f"/api/account/factors/{factor['id']}/remove", headers=csrf,
                           json={"password": PASSWORD})
    assert refused.status_code == 409


def test_a_second_factor_can_be_removed_when_another_remains(astrid, session) -> None:
    browser, csrf = astrid
    secret = browser.post("/api/auth/mfa/totp/enrol", headers=csrf).json()["secret"]
    added = browser.post("/api/auth/mfa/totp/confirm", headers=csrf, json={
        "code": pyotp.TOTP(secret).now(), "label": "Spare phone"})
    csrf = {"X-CSRF-Token": added.json()["session"]["csrf_token"]}
    first = browser.get("/api/account").json()["factors"][0]

    left = browser.post(f"/api/account/factors/{first['id']}/remove", headers=csrf,
                        json={"password": PASSWORD}).json()
    assert [f["label"] for f in left["factors"]] == ["Spare phone"]
    assert "auth.mfa.removed" in actions(session)


def test_other_sessions_can_be_ended(astrid, new_client) -> None:
    browser, csrf = astrid
    other = new_client()
    sign_in(other)
    account = browser.post("/api/account/sessions/end-others", headers=csrf).json()
    assert [s["current"] for s in account["sessions"]] == [True]
    assert other.get("/api/auth/session").status_code == 401
