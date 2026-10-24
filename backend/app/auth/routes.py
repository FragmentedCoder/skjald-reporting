from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import audit
from app.auth.dependencies import DB, AnySession, client_ip
from app.auth.mfa import Method, SecondFactorState, second_factor_state
from app.auth.sessions import COOKIE_NAME, UserSession, csrf_token_for, start_session
from app.auth.sign_in import (
    ADDRESS_WINDOW,
    FAILED_ACTION,
    authenticate,
    too_many_failures_from,
)
from app.policy import load_policy
from app.roles import Capability, Role, can, roles_of

router = APIRouter(prefix="/auth")

SIGN_IN_FAILED = (
    "Sign-in failed. Check your username and password, or wait a few minutes and try again."
)


class SignInRequest(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=1024)


class UserInfo(BaseModel):
    id: int
    username: str
    display_name: str
    theme: str
    roles: list[Role]
    # What the roles allow, worked out here so the frontend never re-derives it.
    capabilities: list[Capability]


class SessionInfo(BaseModel):
    user: UserInfo
    # enrol: set up a second factor now. verify: use one of `methods`. done: signed in.
    second_factor: SecondFactorState
    methods: list[Method]
    # A temporary password must be replaced before the app opens.
    password_change_required: bool
    csrf_token: str
    expires_at: datetime


def session_info(db: Session, record: UserSession, token: str) -> SessionInfo:
    state, methods = second_factor_state(db, record)
    roles = roles_of(db, record.user_id)
    return SessionInfo(
        user=UserInfo(
            id=record.user.id,
            username=record.user.username,
            display_name=record.user.display_name,
            theme=record.user.theme,
            roles=sorted(roles),
            capabilities=sorted(c for c in Capability if can(roles, c)),
        ),
        second_factor=state,
        methods=methods,
        password_change_required=record.user.must_change_password,
        csrf_token=csrf_token_for(token),
        expires_at=record.expires_at,
    )


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, secure=True, samesite="strict", path="/"
    )


@router.post("/sign-in")
def sign_in(body: SignInRequest, request: Request, response: Response, db: DB) -> SessionInfo:
    ip = client_ip(request)
    if too_many_failures_from(db, ip):
        audit.append(db, "auth.sign_in.throttled", ip=ip)
        db.commit()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many sign-in attempts from this computer. Try again in 15 minutes.",
            headers={"Retry-After": str(int(ADDRESS_WINDOW.total_seconds()))},
        )

    policy = load_policy(db)
    outcome = authenticate(db, body.username, body.password, policy)
    account = outcome.account
    actor_id = account.id if account else None
    actor_name = account.username if account else None

    if not outcome.ok or account is None:
        # The typed username is not logged for unknown accounts: people type
        # passwords into the username field.
        audit.append(
            db, FAILED_ACTION, actor_id=actor_id, actor_name=actor_name, ip=ip,
            details={"reason": outcome.reason},
        )
        if outcome.locked_now:
            audit.append(
                db, "auth.account.locked", actor_id=actor_id, actor_name=actor_name, ip=ip,
                details={"minutes": policy.lockout_minutes},
            )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, SIGN_IN_FAILED)

    token, record = start_session(
        db, account, policy, ip=ip, user_agent=request.headers.get("user-agent")
    )
    details: dict[str, object] = {"session": record.id}
    if account.is_break_glass:
        details["break_glass"] = True
    audit.append(
        db, "auth.sign_in.succeeded", actor_id=actor_id, actor_name=actor_name, ip=ip,
        details=details,
    )
    db.commit()
    set_session_cookie(response, token)
    return session_info(db, record, token)


@router.get("/session")
def get_current_session(request: Request, record: AnySession, db: DB) -> SessionInfo:
    return session_info(db, record, request.cookies[COOKIE_NAME])


@router.post("/sign-out", status_code=status.HTTP_204_NO_CONTENT)
def sign_out(request: Request, response: Response, record: AnySession, db: DB) -> None:
    audit.append(
        db,
        "auth.sign_out",
        actor_id=record.user.id,
        actor_name=record.user.username,
        ip=client_ip(request),
        details={"session": record.id},
    )
    db.delete(record)
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/", secure=True, httponly=True, samesite="strict")
