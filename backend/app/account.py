"""Your own account: password, second factors, recovery codes, theme, sessions.

Also the forced password change after an Administrator hands out a temporary
password. Changing what proves who you are (removing a factor, new recovery
codes) asks for your password again; a wrong one counts towards the lockout.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, NoReturn

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.auth.dependencies import DB, AnySession, FullSession, client_ip
from app.auth.mfa import confirmed_factors, issue_recovery_codes, unused_recovery_codes
from app.auth.mfa_routes import FactorInfo
from app.auth.passwords import PasswordRejected, verify_password
from app.auth.pwned import BreachCheckUnavailable
from app.auth.routes import SessionInfo, session_info, set_session_cookie
from app.auth.sessions import UserSession, end_sessions, rotate_token
from app.auth.sign_in import record_password_failure
from app.policy import load_policy
from app.users import set_password, vet_new_password

router = APIRouter()


class SessionSummary(BaseModel):
    id: int
    created_at: datetime
    last_seen_at: datetime
    ip: str | None
    user_agent: str | None
    second_factor_done: bool
    current: bool = False


class AccountInfo(BaseModel):
    username: str
    display_name: str
    email: str | None
    theme: str
    password_changed_at: datetime | None
    factors: list[FactorInfo]
    recovery_codes_left: int
    sessions: list[SessionSummary]


class AccountUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=254, pattern=r"^([^@\s]+@[^@\s]+)?$")
    theme: Literal["system", "light", "dark"] | None = None


class NewPasswordRequest(BaseModel):
    new_password: str = Field(min_length=1, max_length=1024)


class PasswordChangeRequest(NewPasswordRequest):
    current_password: str = Field(min_length=1, max_length=1024)


class PasswordConfirmation(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


class RecoveryCodes(BaseModel):
    recovery_codes: list[str]


def factor_infos(db: Session, user_id: int) -> list[FactorInfo]:
    return [
        FactorInfo(id=f.id, kind=f.kind, label=f.label, created_at=f.created_at,
                   last_used_at=f.last_used_at)
        for f in confirmed_factors(db, user_id)
    ]


def session_summaries(
    db: Session, user_id: int, current: UserSession | None = None
) -> list[SessionSummary]:
    records = db.scalars(
        select(UserSession).where(UserSession.user_id == user_id).order_by(UserSession.id)
    )
    return [
        SessionSummary(
            id=r.id, created_at=r.created_at, last_seen_at=r.last_seen_at, ip=r.ip,
            user_agent=r.user_agent, second_factor_done=r.mfa_verified_at is not None,
            current=current is not None and r.id == current.id,
        )
        for r in records
    ]


def _log(
    db: Session, request: Request, record: UserSession, action: str,
    details: dict[str, object] | None = None,
) -> None:
    audit.append(db, action, actor_id=record.user.id, actor_name=record.user.username,
                 ip=client_ip(request), details=details)


def _confirm_password(db: Session, request: Request, record: UserSession, password: str) -> None:
    """Re-check the user's password before a sensitive change. Hashes outside a transaction."""
    policy = load_policy(db)
    user = record.user
    hashed = user.password_hash
    db.commit()
    if hashed is not None and verify_password(hashed, password):
        return
    outcome = record_password_failure(db, user, policy)
    ip = client_ip(request)
    audit.append(db, "auth.password_confirmation.failed", actor_id=user.id,
                 actor_name=user.username, ip=ip)
    if outcome.locked_now:
        audit.append(db, "auth.account.locked", actor_id=user.id, actor_name=user.username,
                     ip=ip, details={"minutes": policy.lockout_minutes})
        db.delete(record)
        db.commit()
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Too many wrong attempts. Sign in again in a few minutes."
        )
    db.commit()
    raise HTTPException(status.HTTP_400_BAD_REQUEST, "That's not your password.")


def _refuse_password(exc: Exception) -> NoReturn:
    if isinstance(exc, BreachCheckUnavailable):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Skjald couldn't check the new password against known data breaches. Try again "
            "in a moment, or ask an administrator.",
        ) from exc
    raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


def _change_password(
    db: Session, request: Request, response: Response, record: UserSession, new_password: str,
) -> SessionInfo:
    """Set a new password, sign out every other session, and rotate this one's token."""
    policy = load_policy(db)
    user = record.user
    old_hash = user.password_hash
    was_temporary = user.must_change_password
    db.commit()  # the checks below hash and call out to the network
    if old_hash is not None and verify_password(old_hash, new_password):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Choose a password different from your current one."
        )
    try:
        vetted = vet_new_password(new_password, policy, username=user.username)
    except (PasswordRejected, BreachCheckUnavailable) as exc:
        _refuse_password(exc)
    set_password(db, user, vetted, temporary=False)
    ended = end_sessions(db, user.id, keep=record)
    token = rotate_token(record)
    _log(db, request, record, "auth.password.changed",
         {"was_temporary": was_temporary, "other_sessions_ended": ended})
    db.commit()
    set_session_cookie(response, token)
    return session_info(db, record, token)


@router.post("/auth/new-password")
def choose_new_password(
    body: NewPasswordRequest, request: Request, response: Response, record: AnySession, db: DB
) -> SessionInfo:
    """Replace a temporary password. If the account has a second factor, it comes first."""
    if not record.user.must_change_password:
        raise HTTPException(status.HTTP_409_CONFLICT, "Your password doesn't need changing.")
    if record.mfa_verified_at is None and confirmed_factors(db, record.user_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Finish signing in with your second factor first."
        )
    return _change_password(db, request, response, record, body.new_password)


@router.get("/account")
def get_account(record: FullSession, db: DB) -> AccountInfo:
    user = record.user
    return AccountInfo(
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        theme=user.theme,
        password_changed_at=user.password_changed_at,
        factors=factor_infos(db, user.id),
        recovery_codes_left=len(unused_recovery_codes(db, user.id)),
        sessions=session_summaries(db, user.id, current=record),
    )


@router.patch("/account")
def update_account(body: AccountUpdate, request: Request, record: FullSession, db: DB
                   ) -> AccountInfo:
    user = record.user
    changed = body.model_dump(exclude_unset=True)
    if "display_name" in changed and body.display_name:
        user.display_name = body.display_name.strip()
    if "email" in changed:
        user.email = body.email or None
    if "theme" in changed and body.theme:
        user.theme = body.theme
    if changed:
        _log(db, request, record, "account.updated", {"fields": sorted(changed)})
    db.commit()
    return get_account(record, db)


@router.post("/account/password")
def change_my_password(
    body: PasswordChangeRequest, request: Request, response: Response, record: FullSession,
    db: DB,
) -> SessionInfo:
    _confirm_password(db, request, record, body.current_password)
    return _change_password(db, request, response, record, body.new_password)


@router.post("/account/factors/{factor_id}/remove")
def remove_my_factor(
    factor_id: int, body: PasswordConfirmation, request: Request, record: FullSession, db: DB
) -> AccountInfo:
    _confirm_password(db, request, record, body.password)
    factors = confirmed_factors(db, record.user_id)
    factor = next((f for f in factors if f.id == factor_id), None)
    if factor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That second factor doesn't exist.")
    if len(factors) == 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Every account needs a second factor. Add another before removing this one.",
        )
    db.delete(factor)
    _log(db, request, record, "auth.mfa.removed", {"method": factor.kind, "label": factor.label})
    db.commit()
    return get_account(record, db)


@router.post("/account/recovery-codes")
def new_recovery_codes(
    body: PasswordConfirmation, request: Request, record: FullSession, db: DB
) -> RecoveryCodes:
    _confirm_password(db, request, record, body.password)
    codes = issue_recovery_codes(db, record.user_id)
    _log(db, request, record, "auth.mfa.recovery_codes_issued", {"count": len(codes)})
    db.commit()
    return RecoveryCodes(recovery_codes=codes)


@router.post("/account/sessions/end-others")
def end_my_other_sessions(request: Request, record: FullSession, db: DB) -> AccountInfo:
    ended = end_sessions(db, record.user_id, keep=record)
    _log(db, request, record, "auth.sessions.ended", {"count": ended, "by": "self"})
    db.commit()
    return get_account(record, db)

