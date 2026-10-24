from __future__ import annotations

import hmac
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import audit
from app.auth.sessions import COOKIE_NAME, UserSession, csrf_token_for, find_live_session
from app.db import get_db
from app.policy import admin_allowed_from, load_policy
from app.roles import Capability, can, roles_of

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "X-CSRF-Token"

DB = Annotated[Session, Depends(get_db)]


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def current_session(request: Request, db: DB) -> UserSession:
    """Any live session, including one still waiting for its second factor."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
    record = find_live_session(db, token, load_policy(db))
    db.commit()
    if record is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has ended. Sign in again.")
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if not hmac.compare_digest(sent, csrf_token_for(token)):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "The request could not be verified. Reload the page and try again.",
            )
    return record


AnySession = Annotated[UserSession, Depends(current_session)]


def require_full_session(record: AnySession) -> UserSession:
    """A session that has passed both factors. Every route that touches data depends on this."""
    if record.mfa_verified_at is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Finish signing in with your second factor first."
        )
    if record.user.must_change_password:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Choose a new password first.")
    return record


FullSession = Annotated[UserSession, Depends(require_full_session)]


def require(capability: Capability) -> Callable[..., UserSession]:
    """A dependency that lets through only signed-in users whose roles grant capability.

    The admin panel (ADMINISTER) also answers only from the admin IP allowlist.
    """

    def check(request: Request, record: FullSession, db: DB) -> UserSession:
        ip = client_ip(request)
        if not can(roles_of(db, record.user_id), capability):
            refusal = "You don't have access to this."
        elif capability is Capability.ADMINISTER and not admin_allowed_from(load_policy(db), ip):
            refusal = "The admin panel isn't available from this address."
        else:
            return record
        audit.append(
            db,
            "auth.access_denied",
            actor_id=record.user.id,
            actor_name=record.user.username,
            ip=ip,
            details={"capability": capability.value, "path": request.url.path},
        )
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, refusal)

    return check
