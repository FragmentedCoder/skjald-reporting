import re
import time
from datetime import timedelta

import pyotp
import pytest
from sqlalchemy import select

from app import console
from app.audit import AuditEntry
from app.policy import SecurityPolicy, load_policy, save_policy
from app.roles import Role, grant_role, roles_of
from app.users import find_user
from tests.conftest import PASSWORD

USERS = "/api/admin/users"


def actions(session):
    found = list(session.scalars(select(AuditEntry.action).order_by(AuditEntry.seq)))
    session.commit()
    return found


@pytest.fixture
def bjorn(client, admin):
    """A user an Administrator added. Yields (user id, temporary password)."""
    _, headers = admin
    created = client.post(USERS, headers=headers, json={
        "username": "Bjorn", "display_name": "Bjørn Havn", "email": "bjorn@example.com",
        "roles": ["technician"],
    })
    assert created.status_code == 200, created.text
    body = created.json()
    return body["user"]["id"], body["temporary_password"]


def sign_in(browser, username, password):
    return browser.post("/api/auth/sign-in", json={"username": username, "password": password})


# Adding users


def test_a_new_user_gets_a_random_temporary_password_that_expires(
    client, admin, session, frozen_clock
) -> None:
    _, headers = admin
    body = client.post(USERS, headers=headers, json={
        "username": "bjorn", "display_name": "Bjørn Havn", "roles": ["technician", "reviewer"],
    }).json()

    assert re.fullmatch(r"([a-z2-9]{4}-){3}[a-z2-9]{4}", body["temporary_password"])
    assert body["user"]["roles"] == ["reviewer", "technician"]
    assert body["user"]["password_change_required"]
    expires = body["expires_at"].replace("Z", "+00:00")
    assert expires.startswith((frozen_clock.now + timedelta(days=7)).date().isoformat())
    assert "admin.user_created" in actions(session)


def test_a_username_can_only_be_added_once(client, admin, bjorn) -> None:
    _, headers = admin
    again = client.post(USERS, headers=headers, json={"username": "bjorn", "display_name": "B"})
    assert again.status_code == 409


def test_only_administrators_reach_the_admin_panel(client, make_user, session, full_session):
    technician = make_user()
    grant_role(session, technician, Role.TECHNICIAN, actor=None, ip=None)
    session.commit()
    assert client.get(USERS, headers=full_session(technician)).status_code == 403


# The new user's first sign-in


def test_a_temporary_password_must_be_replaced_before_anything_else(
    bjorn, new_client, no_breach_found
) -> None:
    _, temporary = bjorn
    browser = new_client()
    info = sign_in(browser, "bjorn", temporary).json()
    assert info["password_change_required"] and info["second_factor"] == "enrol"
    csrf = {"X-CSRF-Token": info["csrf_token"]}

    assert browser.post("/api/auth/mfa/totp/enrol", headers=csrf).status_code == 403
    same = browser.post("/api/auth/new-password", headers=csrf, json={"new_password": temporary})
    assert same.status_code == 400

    changed = browser.post("/api/auth/new-password", headers=csrf,
                           json={"new_password": PASSWORD})
    assert changed.status_code == 200
    assert not changed.json()["password_change_required"]
    csrf = {"X-CSRF-Token": changed.json()["csrf_token"]}
    assert browser.post("/api/auth/mfa/totp/enrol", headers=csrf).status_code == 200


def test_an_expired_temporary_password_no_longer_signs_in(
    bjorn, new_client, frozen_clock
) -> None:
    _, temporary = bjorn
    frozen_clock.advance(days=8)
    assert sign_in(new_client(), "bjorn", temporary).status_code == 401


# Changing users


def test_details_roles_and_status_can_be_changed(client, admin, bjorn, session) -> None:
    _, headers = admin
    user_id, _ = bjorn
    updated = client.patch(f"{USERS}/{user_id}", headers=headers, json={
        "display_name": "Bjørn Havnsø", "email": "", "roles": ["reviewer", "auditor"],
        "is_active": False,
    }).json()
    assert updated["display_name"] == "Bjørn Havnsø"
    assert updated["email"] is None
    assert updated["roles"] == ["auditor", "reviewer"]
    assert updated["is_active"] is False
    about_bjorn = list(session.scalars(
        select(AuditEntry.action).where(AuditEntry.target_id == str(user_id))
    ))
    session.commit()
    # technician at creation, then reviewer and auditor granted, technician revoked
    assert about_bjorn.count("auth.role.granted") == 3
    assert about_bjorn.count("auth.role.revoked") == 1
    assert "admin.user_updated" in about_bjorn


@pytest.mark.parametrize(("change", "message"), [
    ({"is_active": False}, "disable your own account"),
    ({"roles": []}, "remove your own Administrator role"),
])
def test_you_cannot_lock_yourself_out(client, admin, change, message) -> None:
    user, headers = admin
    refused = client.patch(f"{USERS}/{user.id}", headers=headers, json=change)
    assert refused.status_code == 409
    assert message in refused.json()["detail"]


def test_the_break_glass_administrator_keeps_its_role(
    client, admin, make_user, session
) -> None:
    _, headers = admin
    glass = make_user("glass", display_name="Break glass")
    glass.is_break_glass = True
    grant_role(session, glass, Role.ADMINISTRATOR, actor=None, ip=None)
    session.commit()
    for change in ({"is_active": False}, {"roles": ["auditor"]}):
        assert client.patch(f"{USERS}/{glass.id}", headers=headers, json=change).status_code == 409


def test_an_administrator_can_step_another_one_down(
    client, admin, make_user, session, full_session, new_client
) -> None:
    first, _ = admin
    second = make_user("second", display_name="Second Admin")
    grant_role(session, second, Role.ADMINISTRATOR, actor=None, ip=None)
    session.commit()
    stepped = client.patch(f"{USERS}/{first.id}", headers=full_session(second),
                           json={"roles": ["auditor"], "is_active": False}).json()
    assert stepped["roles"] == ["auditor"] and not stepped["is_active"]
    assert sign_in(new_client(), "admin", PASSWORD).status_code == 401


def test_resetting_a_password_signs_the_user_out_everywhere(
    client, admin, bjorn, new_client
) -> None:
    _, headers = admin
    user_id, temporary = bjorn
    browser = new_client()
    assert sign_in(browser, "bjorn", temporary).status_code == 200

    reset = client.post(f"{USERS}/{user_id}/reset-password", headers=headers).json()
    assert reset["temporary_password"] != temporary
    assert browser.get("/api/auth/session").status_code == 401
    assert sign_in(new_client(), "bjorn", temporary).status_code == 401
    assert sign_in(new_client(), "bjorn", reset["temporary_password"]).status_code == 200


def test_after_a_reset_the_second_factor_comes_first_then_the_new_password(
    client, admin, make_user, new_client, no_breach_found
) -> None:
    _, headers = admin
    astrid = make_user()
    browser = new_client()
    csrf = {"X-CSRF-Token": sign_in(browser, "astrid", PASSWORD).json()["csrf_token"]}
    secret = browser.post("/api/auth/mfa/totp/enrol", headers=csrf).json()["secret"]
    totp = pyotp.TOTP(secret)
    browser.post("/api/auth/mfa/totp/confirm", headers=csrf, json={"code": totp.now()})
    temporary = client.post(f"{USERS}/{astrid.id}/reset-password",
                            headers=headers).json()["temporary_password"]

    browser = new_client()
    info = sign_in(browser, "astrid", temporary).json()
    assert info["second_factor"] == "verify" and info["password_change_required"]
    csrf = {"X-CSRF-Token": info["csrf_token"]}
    early = browser.post("/api/auth/new-password", headers=csrf, json={"new_password": PASSWORD})
    assert early.status_code == 403

    # The next period's code, so the one used at enrolment isn't replayed.
    code = totp.at(time.time() + 30)
    verified = browser.post("/api/auth/mfa/totp/verify", headers=csrf, json={"code": code})
    csrf = {"X-CSRF-Token": verified.json()["session"]["csrf_token"]}
    # Both factors passed, but the temporary password still keeps the app closed.
    closed = browser.get("/api/account")
    assert closed.status_code == 403 and "new password" in closed.json()["detail"]

    changed = browser.post("/api/auth/new-password", headers=csrf,
                           json={"new_password": "en helt ny og lang adgangssætning"})
    assert changed.status_code == 200
    assert browser.get("/api/account").status_code == 200


def test_resetting_second_factors_makes_the_user_set_one_up_again(
    client, admin, make_user, new_client, session
) -> None:
    _, headers = admin
    astrid = make_user()
    browser = new_client()
    csrf = {"X-CSRF-Token": sign_in(browser, "astrid", PASSWORD).json()["csrf_token"]}
    secret = browser.post("/api/auth/mfa/totp/enrol", headers=csrf).json()["secret"]
    browser.post("/api/auth/mfa/totp/confirm", headers=csrf,
                 json={"code": pyotp.TOTP(secret).now()})

    detail = client.post(f"{USERS}/{astrid.id}/reset-second-factors", headers=headers).json()
    assert detail["second_factors"] == 0 and detail["recovery_codes_left"] == 0
    assert detail["sessions"] == []
    assert sign_in(new_client(), "astrid", PASSWORD).json()["second_factor"] == "enrol"


def test_a_locked_account_can_be_unlocked(client, admin, make_user, session, new_client):
    _, headers = admin
    astrid = make_user()
    save_policy(session, SecurityPolicy(lockout_threshold=3))
    session.commit()
    for _ in range(3):
        sign_in(new_client(), "astrid", "wrong password, long enough")
    assert client.get(f"{USERS}/{astrid.id}", headers=headers).json()["locked"]

    assert not client.post(f"{USERS}/{astrid.id}/unlock", headers=headers).json()["locked"]
    assert sign_in(new_client(), "astrid", PASSWORD).status_code == 200


def test_actions_on_yourself_point_to_your_account(client, admin) -> None:
    user, headers = admin
    for action in ("reset-password", "reset-second-factors", "sign-out"):
        assert client.post(f"{USERS}/{user.id}/{action}", headers=headers).status_code == 409


# Security settings and the admin IP allowlist


def security(**changes):
    values = {
        "min_password_length": 12, "breach_check_enabled": True, "lockout_threshold": 10,
        "lockout_minutes": 15, "idle_timeout_minutes": 30, "max_session_hours": 12,
        "admin_allowlist": [],
    }
    return values | changes


def test_security_settings_are_saved_and_the_change_logged(client, admin, session) -> None:
    _, headers = admin
    saved = client.put("/api/admin/security", headers=headers,
                       json=security(lockout_threshold=5, breach_check_enabled=False)).json()
    assert saved["lockout_threshold"] == 5 and saved["your_address"] == "testclient"
    policy = load_policy(session)
    session.commit()
    assert (policy.lockout_threshold, policy.breach_check_enabled) == (5, False)
    entry = session.scalars(
        select(AuditEntry).where(AuditEntry.action == "admin.security_changed")
    ).one()
    session.commit()
    assert entry.details == (
        '{"changes":{"breach_check_enabled":[true,false],"lockout_threshold":[10,5]}}'
    )


@pytest.mark.parametrize("change", [
    {"min_password_length": 4}, {"idle_timeout_minutes": 0}, {"max_session_hours": 1000},
])
def test_security_settings_stay_within_their_limits(client, admin, change) -> None:
    _, headers = admin
    assert client.put("/api/admin/security", headers=headers,
                      json=security(**change)).status_code == 422


def test_an_allowlist_that_would_lock_you_out_is_refused(client, admin) -> None:
    _, headers = admin
    refused = client.put("/api/admin/security", headers=headers,
                         json=security(admin_allowlist=["10.0.0.0/24"]))
    assert refused.status_code == 400
    assert "lock you out" in refused.json()["detail"]
    bad = client.put("/api/admin/security", headers=headers,
                     json=security(admin_allowlist=["not an address"]))
    assert bad.status_code == 400


def test_the_allowlist_closes_the_admin_panel_to_other_addresses(
    client, admin, session
) -> None:
    _, headers = admin
    save_policy(session, SecurityPolicy(admin_allowlist=("10.0.0.0/24",)))
    session.commit()
    refused = client.get(USERS, headers=headers)
    assert refused.status_code == 403
    assert "isn't available from this address" in refused.json()["detail"]

    console.reset_allowlist(session)
    session.commit()
    assert client.get(USERS, headers=headers).status_code == 200
    assert "admin.allowlist_reset" in actions(session)


# Server


def test_server_info_and_renaming_the_company(client, admin, session, monkeypatch) -> None:
    from app.settings import settings

    monkeypatch.setattr(settings, "address", "https://skjald.example.internal")
    _, headers = admin
    info = client.put("/api/admin/server", headers=headers,
                      json={"company_name": "Nordlys IT ApS"}).json()
    assert info["company_name"] == "Nordlys IT ApS"
    assert info["address"] == "https://skjald.example.internal"
    assert info["schema_version"] == "0005"
    assert re.fullmatch(r"\d+\.\d+\.\d+", info["version"])
    assert "admin.company_renamed" in actions(session)


def test_a_removed_user_cannot_be_found(client, admin) -> None:
    _, headers = admin
    assert client.get(f"{USERS}/999", headers=headers).status_code == 404


def test_find_user_still_matches_after_admin_changes(client, admin, bjorn, session) -> None:
    _, headers = admin
    user_id, _ = bjorn
    client.patch(f"{USERS}/{user_id}", headers=headers, json={"roles": ["auditor"]})
    user = find_user(session, "BJORN")
    assert user is not None and roles_of(session, user.id) == {Role.AUDITOR}
    session.commit()
