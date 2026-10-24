"""The first-run setup wizard: company name, break-glass Administrator, recovery kit.

Every step needs the setup token. The recovery kit and the last step also need
the new Administrator to be fully signed in, second factor included. Once setup
is complete, every step answers 410 Gone.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, clock
from app.admin import SecuritySettings
from app.auth.dependencies import DB, FullSession, client_ip
from app.auth.passwords import PasswordRejected
from app.auth.pwned import BreachCheckUnavailable
from app.auth.routes import SessionInfo, session_info, set_session_cookie
from app.auth.sessions import UserSession, start_session
from app.auth.sign_in import too_many_failures_from
from app.crypto.key_files import load_or_create_backup_key
from app.crypto.keys import load_master_key, to_kit_text
from app.policy import load_policy, save_policy
from app.roles import Role, grant_role
from app.settings import settings
from app.setup import (
    company_name,
    complete_setup,
    mark_recovery_kit_shown,
    mark_security_reviewed,
    recovery_kit_shown,
    security_reviewed,
    set_company_name,
    setup_complete,
    setup_token_valid,
)
from app.users import User, create_user, find_user, vet_new_password

router = APIRouter(prefix="/setup")

TOKEN_HEADER = "X-Setup-Token"
TOKEN_REJECTED = "setup.token_rejected"
TOKEN_MAX_FAILURES = 10


class SetupStatus(BaseModel):
    needed: bool


class SetupProgress(BaseModel):
    company_name: str | None
    # Passkeys are bound to this address, so it must be right before any are made.
    address: str
    security_reviewed: bool
    security: SecuritySettings
    administrator: str | None


class CompanyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class AdministratorRequest(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    display_name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(min_length=1, max_length=1024)
    # Only after the wizard has shown that the breach check service can't be reached.
    skip_breach_check: bool = False


class RecoveryKit(BaseModel):
    master_key: str
    backup_key: str
    address: str
    company_name: str | None
    shown_at: datetime


class CompleteRequest(BaseModel):
    kit_saved: bool


def require_setup_token(request: Request, db: DB) -> None:
    if setup_complete(db):
        raise HTTPException(status.HTTP_410_GONE, "Skjald is already set up.")
    ip = client_ip(request)
    if too_many_failures_from(db, ip, TOKEN_REJECTED, limit=TOKEN_MAX_FAILURES):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many wrong setup tokens from this computer. Try again in 15 minutes.",
        )
    if not setup_token_valid(db, request.headers.get(TOKEN_HEADER, "")):
        audit.append(db, TOKEN_REJECTED, ip=ip)
        db.commit()
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "That setup token isn't right. Use the newest one Skjald printed.",
        )


SetupToken = Annotated[None, Depends(require_setup_token)]


def _break_glass_administrator(db: Session) -> User | None:
    return db.scalar(select(User).where(User.is_break_glass.is_(True)))


def _require_setup_administrator(record: UserSession) -> None:
    if not record.user.is_break_glass:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the administrator created in setup can do this."
        )


@router.get("/status")
def setup_status(db: DB) -> SetupStatus:
    return SetupStatus(needed=not setup_complete(db))


@router.post("/progress")
def setup_progress(_: SetupToken, db: DB) -> SetupProgress:
    administrator = _break_glass_administrator(db)
    policy = asdict(load_policy(db))
    return SetupProgress(
        company_name=company_name(db),
        address=settings.address,
        security_reviewed=security_reviewed(db),
        security=SecuritySettings(**{k: policy[k] for k in SecuritySettings.model_fields}),
        administrator=administrator.username if administrator else None,
    )


@router.post("/company")
def name_company(body: CompanyRequest, request: Request, _: SetupToken, db: DB) -> SetupProgress:
    set_company_name(db, body.name)
    audit.append(db, "setup.company_named", ip=client_ip(request), details={"name": body.name})
    db.commit()
    return setup_progress(None, db)


@router.post("/security")
def set_security(
    body: SecuritySettings, request: Request, _: SetupToken, db: DB
) -> SetupProgress:
    """The starting security policy. The admin IP allowlist is left to the admin panel."""
    save_policy(db, replace(load_policy(db), **body.model_dump()))
    mark_security_reviewed(db)
    audit.append(db, "setup.security_set", ip=client_ip(request), details=body.model_dump())
    db.commit()
    return setup_progress(None, db)


@router.post("/administrator")
def create_administrator(
    body: AdministratorRequest, request: Request, response: Response, _: SetupToken, db: DB
) -> SessionInfo:
    existing = _break_glass_administrator(db)
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"The administrator is already created. Sign in as {existing.username} to continue.",
        )
    if find_user(db, body.username) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That username is taken.")

    ip = client_ip(request)
    policy = load_policy(db)
    if body.skip_breach_check and policy.breach_check_enabled:
        policy = replace(policy, breach_check_enabled=False)
        save_policy(db, policy)
        audit.append(db, "setup.breach_check_turned_off", ip=ip)
    db.commit()  # the breach check calls out to the network: never inside a transaction

    try:
        password = vet_new_password(body.password, policy, username=body.username)
    except PasswordRejected as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except BreachCheckUnavailable as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Skjald couldn't reach the breach check service (api.pwnedpasswords.com) to "
            "check the password.",
        ) from exc

    user = create_user(
        db, body.username, body.display_name, password, email=body.email, is_break_glass=True
    )
    audit.append(
        db, "setup.administrator_created", actor_id=user.id, actor_name=user.username, ip=ip
    )
    grant_role(db, user, Role.ADMINISTRATOR, actor=None, ip=ip)
    token, record = start_session(
        db, user, policy, ip=ip, user_agent=request.headers.get("user-agent")
    )
    audit.append(
        db, "auth.sign_in.succeeded", actor_id=user.id, actor_name=user.username, ip=ip,
        details={"session": record.id, "break_glass": True, "via": "setup"},
    )
    db.commit()
    set_session_cookie(response, token)
    return session_info(db, record, token)


@router.post("/recovery-kit")
def show_recovery_kit(
    request: Request, _: SetupToken, record: FullSession, db: DB
) -> RecoveryKit:
    """The master and backup keys, for keeping offline. Shown only until setup is complete."""
    _require_setup_administrator(record)
    master_key = load_master_key(settings.master_key_path)
    backup_key = load_or_create_backup_key(settings.data_dir, settings.master_key_path)
    mark_recovery_kit_shown(db)
    audit.append(
        db, "setup.recovery_kit_shown", actor_id=record.user.id,
        actor_name=record.user.username, ip=client_ip(request),
    )
    db.commit()
    return RecoveryKit(
        master_key=to_kit_text(master_key),
        backup_key=to_kit_text(backup_key),
        address=settings.address,
        company_name=company_name(db),
        shown_at=clock.utcnow(),
    )


@router.post("/complete")
def finish_setup(
    body: CompleteRequest, request: Request, _: SetupToken, record: FullSession, db: DB
) -> SetupStatus:
    _require_setup_administrator(record)
    if company_name(db) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Name the company first.")
    if not security_reviewed(db):
        raise HTTPException(status.HTTP_409_CONFLICT, "Review the security settings first.")
    if not recovery_kit_shown(db) or not body.kit_saved:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Save the recovery kit before finishing setup."
        )
    complete_setup(db)
    audit.append(
        db, "setup.completed", actor_id=record.user.id, actor_name=record.user.username,
        ip=client_ip(request),
    )
    db.commit()
    return SetupStatus(needed=False)
