import re

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from webauthn.helpers import bytes_to_base64url

from app.audit import AuditEntry, verify
from app.auth.sessions import COOKIE_NAME
from app.main import app
from app.policy import SecurityPolicy, save_policy
from app.settings import settings
from tests.conftest import PASSWORD
from tests.soft_authenticator import SoftAuthenticator

TOTP_PERIOD = 30
MFA = "/api/auth/mfa"


def sign_in(client, password=PASSWORD):
    return client.post("/api/auth/sign-in", json={"username": "astrid", "password": password})


def post(client, path, body=None):
    csrf = client.get("/api/auth/session").json()["csrf_token"]
    return client.post(path, json=body or {}, headers={"X-CSRF-Token": csrf})


def code_at(secret, moment, steps=0):
    return pyotp.TOTP(secret).generate_otp(int(moment.timestamp()) // TOTP_PERIOD + steps)


def audit_actions(session):
    actions = list(session.scalars(select(AuditEntry.action).order_by(AuditEntry.seq)))
    session.commit()
    return actions


@pytest.fixture
def enrolled(client, make_user, frozen_clock):
    """Astrid has set up an authenticator app and signed out. Yields (secret, recovery codes)."""
    make_user()
    sign_in(client)
    secret = post(client, f"{MFA}/totp/enrol").json()["secret"]
    result = post(client, f"{MFA}/totp/confirm", {"code": code_at(secret, frozen_clock.now)})
    post(client, "/api/auth/sign-out")
    frozen_clock.advance(seconds=2 * TOTP_PERIOD)
    return secret, result.json()["recovery_codes"]


@pytest.fixture
def stranger(client):
    """A second browser, sharing the test database but not the first one's cookies."""
    with TestClient(app, base_url="https://testserver") as other:
        yield other


# Authenticator apps


def test_a_first_sign_in_must_set_up_a_second_factor(client, make_user) -> None:
    make_user()
    assert sign_in(client).json()["second_factor"] == "enrol"
    assert client.get(f"{MFA}/factors").status_code == 403


def test_setting_up_an_authenticator_app_finishes_sign_in(
    client, make_user, session, frozen_clock, stranger
) -> None:
    make_user()
    first = sign_in(client)
    old_token, old_csrf = first.cookies[COOKIE_NAME], first.json()["csrf_token"]

    enrolment = post(client, f"{MFA}/totp/enrol").json()
    assert enrolment["otpauth_uri"].startswith("otpauth://totp/Skjald:astrid?")
    assert "issuer=Skjald" in enrolment["otpauth_uri"]

    code = code_at(enrolment["secret"], frozen_clock.now)
    response = post(client, f"{MFA}/totp/confirm", {"code": code, "label": "Work phone"})
    assert response.status_code == 200
    body = response.json()
    assert body["session"]["second_factor"] == "done"

    codes = body["recovery_codes"]
    assert len(set(codes)) == 10
    assert all(re.fullmatch(r"[a-z2-9]{4}-[a-z2-9]{4}-[a-z2-9]{4}", c) for c in codes)

    # A new token and CSRF token; the one from before the second factor is dead.
    assert response.cookies[COOKIE_NAME] != old_token
    assert body["session"]["csrf_token"] != old_csrf
    replayed = stranger.get("/api/auth/session", headers={"Cookie": f"{COOKIE_NAME}={old_token}"})
    assert replayed.status_code == 401

    factors = client.get(f"{MFA}/factors").json()
    assert [f["label"] for f in factors["factors"]] == ["Work phone"]
    assert factors["recovery_codes_left"] == 10
    assert audit_actions(session)[-3:] == [
        "auth.mfa.enrolled",
        "auth.mfa.recovery_codes_issued",
        "auth.mfa.verified",
    ]


def test_a_wrong_code_does_not_finish_setup(client, make_user, frozen_clock) -> None:
    make_user()
    sign_in(client)
    secret = post(client, f"{MFA}/totp/enrol").json()["secret"]
    wrong = code_at(secret, frozen_clock.now, steps=5)
    assert post(client, f"{MFA}/totp/confirm", {"code": wrong}).status_code == 400
    assert client.get("/api/auth/session").json()["second_factor"] == "enrol"


def test_a_returning_user_signs_in_with_the_app(client, enrolled, frozen_clock) -> None:
    secret, _ = enrolled
    info = sign_in(client).json()
    assert (info["second_factor"], info["methods"]) == ("verify", ["totp", "recovery_code"])

    response = post(client, f"{MFA}/totp/verify", {"code": code_at(secret, frozen_clock.now)})
    assert response.status_code == 200
    assert response.json()["session"]["second_factor"] == "done"
    assert response.json()["recovery_codes"] is None


def test_a_code_cannot_be_used_twice(client, enrolled, frozen_clock) -> None:
    secret, _ = enrolled
    code = code_at(secret, frozen_clock.now)
    sign_in(client)
    assert post(client, f"{MFA}/totp/verify", {"code": code}).status_code == 200
    post(client, "/api/auth/sign-out")

    sign_in(client)
    assert post(client, f"{MFA}/totp/verify", {"code": code}).status_code == 400


@pytest.mark.parametrize(("steps", "accepted"), [(-1, True), (1, True), (-2, False), (2, False)])
def test_a_phone_clock_one_step_off_is_tolerated(
    client, enrolled, frozen_clock, steps, accepted
) -> None:
    secret, _ = enrolled
    sign_in(client)
    code = code_at(secret, frozen_clock.now, steps)
    response = post(client, f"{MFA}/totp/verify", {"code": code})
    assert (response.status_code == 200) is accepted


def test_a_password_alone_cannot_add_a_factor_to_a_protected_account(client, enrolled) -> None:
    sign_in(client)
    assert post(client, f"{MFA}/totp/enrol").status_code == 403
    assert post(client, f"{MFA}/passkey/registration-options").status_code == 403


# Recovery codes and lockout


def test_each_recovery_code_works_once(client, enrolled, session) -> None:
    _, codes = enrolled
    sign_in(client)
    response = post(client, f"{MFA}/recovery-code/verify", {"code": codes[0].upper()})
    assert response.json()["session"]["second_factor"] == "done"
    post(client, "/api/auth/sign-out")

    sign_in(client)
    assert post(client, f"{MFA}/recovery-code/verify", {"code": codes[0]}).status_code == 400
    spaced = codes[1].replace("-", " ")
    assert post(client, f"{MFA}/recovery-code/verify", {"code": spaced}).status_code == 200

    used = session.scalars(
        select(AuditEntry.details).where(AuditEntry.action == "auth.recovery_code.used")
    ).all()
    session.commit()
    assert used == ['{"left":9}', '{"left":8}']


def test_wrong_codes_share_the_password_lockout(client, enrolled, session) -> None:
    save_policy(session, SecurityPolicy(lockout_threshold=3))
    session.commit()
    sign_in(client)
    for _ in range(2):
        assert post(client, f"{MFA}/totp/verify", {"code": "000000"}).status_code == 400

    assert post(client, f"{MFA}/totp/verify", {"code": "000000"}).status_code == 401
    assert client.get("/api/auth/session").status_code == 401
    assert sign_in(client).status_code == 401
    assert "auth.account.locked" in audit_actions(session)


def test_only_a_full_sign_in_resets_the_failure_count(
    client, enrolled, session, frozen_clock
) -> None:
    secret, _ = enrolled
    save_policy(session, SecurityPolicy(lockout_threshold=3))
    session.commit()

    for _ in range(2):
        sign_in(client, password="wrong password, long enough")
    sign_in(client)
    code = code_at(secret, frozen_clock.now)
    assert post(client, f"{MFA}/totp/verify", {"code": code}).status_code == 200
    post(client, "/api/auth/sign-out")

    for _ in range(2):
        sign_in(client, password="wrong password, long enough")
    assert sign_in(client).status_code == 200


# Passkeys and hardware keys


@pytest.fixture
def passkey(monkeypatch):
    monkeypatch.setattr(settings, "address", "https://testserver")
    return SoftAuthenticator("testserver", "https://testserver")


def register(client, authenticator, label="YubiKey"):
    options = post(client, f"{MFA}/passkey/registration-options").json()
    credential = authenticator.register(options)
    return post(client, f"{MFA}/passkey/register", {"credential": credential, "label": label})


def authenticate(client, authenticator):
    options = post(client, f"{MFA}/passkey/authentication-options").json()
    credential = authenticator.authenticate(options)
    return post(client, f"{MFA}/passkey/verify", {"credential": credential})


def test_a_passkey_can_be_set_up_and_used(client, make_user, passkey, session) -> None:
    make_user()
    sign_in(client)
    options = post(client, f"{MFA}/passkey/registration-options").json()
    assert options["rp"] == {"id": "testserver", "name": "Skjald"}
    assert options["user"]["name"] == "astrid"

    response = post(
        client, f"{MFA}/passkey/register",
        {"credential": passkey.register(options), "label": "YubiKey"},
    )
    assert response.status_code == 200
    assert response.json()["session"]["second_factor"] == "done"
    assert len(response.json()["recovery_codes"]) == 10
    post(client, "/api/auth/sign-out")

    assert sign_in(client).json()["methods"] == ["webauthn", "recovery_code"]
    options = post(client, f"{MFA}/passkey/authentication-options").json()
    assert [c["id"] for c in options["allowCredentials"]] == [
        bytes_to_base64url(passkey.credential_id)
    ]
    response = post(
        client, f"{MFA}/passkey/verify", {"credential": passkey.authenticate(options)}
    )
    assert response.json()["session"]["second_factor"] == "done"
    assert verify(session).ok


def test_a_passkey_made_for_another_site_is_refused(client, make_user, passkey) -> None:
    make_user()
    sign_in(client)
    phishing_page = SoftAuthenticator("testserver", "https://skjald.example.evil")
    assert register(client, phishing_page).status_code == 400
    assert client.get("/api/auth/session").json()["second_factor"] == "enrol"


def test_a_passkey_answer_cannot_be_replayed(client, make_user, passkey) -> None:
    make_user()
    sign_in(client)
    register(client, passkey)
    post(client, "/api/auth/sign-out")

    sign_in(client)
    options = post(client, f"{MFA}/passkey/authentication-options").json()
    answer = passkey.authenticate(options)
    assert post(client, f"{MFA}/passkey/verify", {"credential": answer}).status_code == 200
    post(client, "/api/auth/sign-out")

    sign_in(client)
    post(client, f"{MFA}/passkey/authentication-options")  # a fresh challenge
    assert post(client, f"{MFA}/passkey/verify", {"credential": answer}).status_code == 400


def test_a_cloned_passkey_is_refused(client, make_user, passkey) -> None:
    make_user()
    sign_in(client)
    register(client, passkey)
    post(client, "/api/auth/sign-out")
    sign_in(client)
    assert authenticate(client, passkey).status_code == 200
    post(client, "/api/auth/sign-out")

    passkey.sign_count = 0  # a copy of the key, whose counter lags the original's
    sign_in(client)
    assert authenticate(client, passkey).status_code == 400
