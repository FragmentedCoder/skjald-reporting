from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import clock
from app.auth import pwned
from app.auth.sessions import COOKIE_NAME, csrf_token_for, start_session
from app.crypto.keys import generate_key
from app.db import get_db, make_engine
from app.main import app
from app.migrate import upgrade
from app.policy import SecurityPolicy
from app.users import create_user, vet_new_password

PASSWORD = "lang nok adgangskode til fjorden"


@pytest.fixture
def master_key_path(tmp_path):
    path = tmp_path / "master.key"
    path.write_bytes(generate_key())
    return path


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def engine(data_dir, master_key_path):
    engine = make_engine(data_dir, master_key_path)
    upgrade(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def client(engine):
    def test_db():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[get_db] = test_db
    # https: the session cookie is Secure, so it is only sent back over HTTPS.
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()


class FrozenClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@pytest.fixture
def frozen_clock(monkeypatch):
    frozen = FrozenClock()
    monkeypatch.setattr(clock, "utcnow", lambda: frozen.now)
    return frozen


@pytest.fixture(autouse=True)
def no_breach_service(monkeypatch):
    """Tests never reach api.pwnedpasswords.com; the ones that need it patch _client."""

    def refuse(request):
        raise AssertionError(f"Unexpected network call in a test: {request.url}")

    monkeypatch.setattr(
        pwned, "_client", lambda: httpx.Client(transport=httpx.MockTransport(refuse))
    )


@pytest.fixture
def no_breach_found(monkeypatch):
    """A breach service that knows none of the passwords (padding entries only)."""

    def answer(request):
        return httpx.Response(200, text="\r\n".join(f"{i:035X}:0" for i in range(5)))

    monkeypatch.setattr(
        pwned, "_client", lambda: httpx.Client(transport=httpx.MockTransport(answer))
    )


@pytest.fixture
def full_session(session):
    """Sign a user in with both factors already passed; returns the headers to send."""

    def sign_in(user):
        token, record = start_session(session, user, SecurityPolicy(), ip="testclient",
                                      user_agent=None)
        record.mfa_verified_at = clock.utcnow()
        session.commit()
        return {"Cookie": f"{COOKIE_NAME}={token}", "X-CSRF-Token": csrf_token_for(token)}

    return sign_in


@pytest.fixture
def new_client(client):
    """More browsers, sharing the test database but not each other's cookies."""
    opened = []

    def make():
        browser = TestClient(app, base_url="https://testserver")
        opened.append(browser)
        return browser

    yield make
    for browser in opened:
        browser.close()


@pytest.fixture
def admin(make_user, session, full_session):
    """An active Administrator, fully signed in. Yields (user, request headers)."""
    from app.roles import Role, grant_role

    user = make_user("admin", display_name="Ingrid Admin")
    grant_role(session, user, Role.ADMINISTRATOR, actor=None, ip=None)
    session.commit()
    return user, full_session(user)


NO_BREACH_CHECK = SecurityPolicy(breach_check_enabled=False)


@pytest.fixture
def make_user(session):
    def make(username="astrid", password=PASSWORD, **fields):
        vetted = vet_new_password(password, NO_BREACH_CHECK, username=username)
        user = create_user(
            session, username, fields.pop("display_name", "Astrid Fjeld"), vetted, **fields
        )
        session.commit()
        return user

    return make
