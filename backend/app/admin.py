"""The admin panel's API: users and their roles, security settings, server settings.

Every route needs the ADMINISTER capability, which also enforces the admin IP
allowlist. Guards keep an install from locking itself out: you can't disable
yourself or drop your own Administrator role, the break-glass Administrator
keeps that role and stays active, and an allowlist that leaves out your own
address is refused.
"""

from __future__ import annotations

import importlib.metadata
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app import audit, clock
from app.account import SessionSummary, factor_infos, session_summaries
from app.auth.dependencies import DB, client_ip, require
from app.auth.mfa import MfaFactor, RecoveryCode, confirmed_factors, unused_recovery_codes
from app.auth.mfa_routes import FactorInfo
from app.auth.sessions import UserSession, end_sessions
from app.policy import LIMITS, admin_allowed_from, load_policy, normalize_networks, save_policy
from app.roles import Capability, Role, grant_role, revoke_role, roles_of
from app.settings import settings
from app.setup import company_name, set_company_name, setup_completed_at
from app.users import User, create_user, find_user, set_password, temporary_password

router = APIRouter(prefix="/admin")

Admin = Annotated[UserSession, Depends(require(Capability.ADMINISTER))]


def _limit(name: str) -> Any:
    low, high = LIMITS[name]
    return Field(ge=low, le=high)


class SecuritySettings(BaseModel):
    """The security policy as people edit it, in the admin panel and the setup wizard."""

    min_password_length: int = _limit("min_password_length")
    breach_check_enabled: bool
    lockout_threshold: int = _limit("lockout_threshold")
    lockout_minutes: int = _limit("lockout_minutes")
    idle_timeout_minutes: int = _limit("idle_timeout_minutes")
    max_session_hours: int = _limit("max_session_hours")


class AdminSecurity(SecuritySettings):
    admin_allowlist: list[str] = Field(max_length=50)


class AdminSecurityView(AdminSecurity):
    your_address: str | None
    limits: dict[str, tuple[int, int]]


class UserSummary(BaseModel):
    id: int
    username: str
    display_name: str
    email: str | None
    roles: list[Role]
    is_active: bool
    is_break_glass: bool
    locked: bool
    second_factors: int
    password_change_required: bool
    last_sign_in_at: datetime | None
    created_at: datetime


class UserDetail(UserSummary):
    password_expires_at: datetime | None
    factors: list[FactorInfo]
    recovery_codes_left: int
    sessions: list[SessionSummary]


class NewUser(BaseModel):
    username: str = Field(min_length=1, max_length=150, pattern=r"^\S+$")
    display_name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=254, pattern=r"^([^@\s]+@[^@\s]+)?$")
    roles: list[Role] = []


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=254, pattern=r"^([^@\s]+@[^@\s]+)?$")
    roles: list[Role] | None = None
    is_active: bool | None = None


class TemporaryPassword(BaseModel):
    user: UserDetail
    temporary_password: str
    expires_at: datetime


class ServerInfo(BaseModel):
    company_name: str | None
    address: str
    version: str
    schema_version: str | None
    setup_completed_at: str | None
    keys: dict[str, bool]


class ServerUpdate(BaseModel):
    company_name: str = Field(min_length=1, max_length=200)


def _log(
    db: Session, request: Request, admin: UserSession, action: str, *,
    target: User | None = None, details: dict[str, object] | None = None,
) -> None:
    audit.append(
        db, action, actor_id=admin.user.id, actor_name=admin.user.username,
        target_type="user" if target else None, target_id=str(target.id) if target else None,
        ip=client_ip(request), details=details,
    )


def _summary_fields(db: Session, user: User) -> dict[str, Any]:
    locked_until = user.locked_until
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "roles": sorted(roles_of(db, user.id)),
        "is_active": user.is_active,
        "is_break_glass": user.is_break_glass,
        "locked": locked_until is not None and locked_until > clock.utcnow(),
        "second_factors": len(confirmed_factors(db, user.id)),
        "password_change_required": user.must_change_password,
        "last_sign_in_at": user.last_sign_in_at,
        "created_at": user.created_at,
    }


def _detail(db: Session, user: User) -> UserDetail:
    return UserDetail(
        **_summary_fields(db, user),
        password_expires_at=user.password_expires_at,
        factors=factor_infos(db, user.id),
        recovery_codes_left=len(unused_recovery_codes(db, user.id)),
        sessions=session_summaries(db, user.id),
    )


def _target(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That user doesn't exist.")
    return user


def _not_yourself(admin: UserSession, user: User, what: str) -> None:
    if user.id == admin.user_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"You can't {what} for yourself here. Use Your account."
        )


# Users


@router.get("/users")
def list_users(_: Admin, db: DB) -> list[UserSummary]:
    users = db.scalars(select(User).order_by(User.display_name, User.username))
    return [UserSummary(**_summary_fields(db, user)) for user in users]


@router.post("/users")
def add_user(body: NewUser, request: Request, admin: Admin, db: DB) -> TemporaryPassword:
    if find_user(db, body.username) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That username is taken.")
    password = temporary_password(load_policy(db), username=body.username)
    db.commit()  # create_user hashes the password: never inside a transaction
    user = create_user(db, body.username, body.display_name, password, email=body.email or None,
                       temporary=True)
    for role in sorted(set(body.roles)):
        grant_role(db, user, role, actor=admin.user, ip=client_ip(request))
    _log(db, request, admin, "admin.user_created", target=user,
         details={"username": user.username, "roles": sorted(r.value for r in body.roles)})
    db.commit()
    assert user.password_expires_at is not None
    return TemporaryPassword(user=_detail(db, user), temporary_password=password.value,
                             expires_at=user.password_expires_at)


@router.get("/users/{user_id}")
def get_user(user_id: int, _: Admin, db: DB) -> UserDetail:
    return _detail(db, _target(db, user_id))


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, request: Request, admin: Admin, db: DB
                ) -> UserDetail:
    user = _target(db, user_id)
    current = roles_of(db, user.id)
    wanted = set(body.roles) if body.roles is not None else current
    deactivating = body.is_active is False and user.is_active
    losing_admin = Role.ADMINISTRATOR in current and Role.ADMINISTRATOR not in wanted

    if user.id == admin.user_id and deactivating:
        raise HTTPException(status.HTTP_409_CONFLICT, "You can't disable your own account.")
    if user.id == admin.user_id and losing_admin:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "You can't remove your own Administrator role."
        )
    # With these two rules an active Administrator always remains: whoever makes
    # the change is one, and can't step themselves down.
    if user.is_break_glass and (deactivating or losing_admin):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The break-glass administrator always keeps the Administrator role and stays active.",
        )

    changes: dict[str, object] = {}
    if body.display_name is not None and body.display_name.strip() != user.display_name:
        changes["display_name"] = [user.display_name, body.display_name.strip()]
        user.display_name = body.display_name.strip()
    if "email" in body.model_fields_set and (body.email or None) != user.email:
        changes["email"] = [user.email, body.email or None]
        user.email = body.email or None
    if body.is_active is not None and body.is_active != user.is_active:
        changes["is_active"] = [user.is_active, body.is_active]
        user.is_active = body.is_active
        if not body.is_active:
            changes["sessions_ended"] = end_sessions(db, user.id)
    ip = client_ip(request)
    for role in sorted(wanted - current):
        grant_role(db, user, role, actor=admin.user, ip=ip)
    for role in sorted(current - wanted):
        revoke_role(db, user, role, actor=admin.user, ip=ip)
    if changes:
        _log(db, request, admin, "admin.user_updated", target=user, details=changes)
    db.commit()
    return _detail(db, user)


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, request: Request, admin: Admin, db: DB) -> TemporaryPassword:
    user = _target(db, user_id)
    _not_yourself(admin, user, "reset the password")
    password = temporary_password(load_policy(db), username=user.username)
    set_password(db, user, password, temporary=True)
    ended = end_sessions(db, user.id)
    _log(db, request, admin, "admin.password_reset", target=user,
         details={"sessions_ended": ended})
    db.commit()
    assert user.password_expires_at is not None
    return TemporaryPassword(user=_detail(db, user), temporary_password=password.value,
                             expires_at=user.password_expires_at)


@router.post("/users/{user_id}/reset-second-factors")
def reset_second_factors(user_id: int, request: Request, admin: Admin, db: DB) -> UserDetail:
    """For a lost phone or key: the user sets up a new second factor at next sign-in."""
    user = _target(db, user_id)
    _not_yourself(admin, user, "reset second factors")
    removed = len(confirmed_factors(db, user.id))
    db.execute(delete(MfaFactor).where(MfaFactor.user_id == user.id))
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    ended = end_sessions(db, user.id)
    _log(db, request, admin, "admin.second_factors_reset", target=user,
         details={"factors_removed": removed, "sessions_ended": ended})
    db.commit()
    return _detail(db, user)


@router.post("/users/{user_id}/unlock")
def unlock_user(user_id: int, request: Request, admin: Admin, db: DB) -> UserDetail:
    user = _target(db, user_id)
    user.locked_until = None
    user.failed_sign_ins = 0
    _log(db, request, admin, "admin.user_unlocked", target=user)
    db.commit()
    return _detail(db, user)


@router.post("/users/{user_id}/sign-out")
def sign_out_everywhere(user_id: int, request: Request, admin: Admin, db: DB) -> UserDetail:
    user = _target(db, user_id)
    _not_yourself(admin, user, "end every session")
    ended = end_sessions(db, user.id)
    _log(db, request, admin, "auth.sessions.ended", target=user,
         details={"count": ended, "by": "administrator"})
    db.commit()
    return _detail(db, user)


# Security


def _security_view(db: Session, request: Request) -> AdminSecurityView:
    policy = load_policy(db)
    values = asdict(policy)
    values["admin_allowlist"] = list(policy.admin_allowlist)
    return AdminSecurityView(**values, your_address=client_ip(request), limits=LIMITS)


@router.get("/security")
def get_security(request: Request, _: Admin, db: DB) -> AdminSecurityView:
    return _security_view(db, request)


@router.put("/security")
def update_security(body: AdminSecurity, request: Request, admin: Admin, db: DB
                    ) -> AdminSecurityView:
    try:
        allowlist = normalize_networks(body.admin_allowlist)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Each allowlist entry must be an address or a range, such as 10.0.0.0/24.",
        ) from exc
    old = load_policy(db)
    new = replace(old, **body.model_dump(exclude={"admin_allowlist"}), admin_allowlist=allowlist)
    ip = client_ip(request)
    if not admin_allowed_from(new, ip):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Your own address ({ip}) isn't in the allowlist, so saving it would lock you out "
            "of the admin panel.",
        )
    changes = {
        name: [before, after]
        for name, before in asdict(old).items()
        if (after := asdict(new)[name]) != before
    }
    if changes:
        save_policy(db, new)
        _log(db, request, admin, "admin.security_changed", details={"changes": changes})
    db.commit()
    return _security_view(db, request)


# Server


def _server_info(db: Session) -> ServerInfo:
    data_dir = Path(settings.data_dir)
    return ServerInfo(
        company_name=company_name(db),
        address=settings.address,
        version=importlib.metadata.version("skjald-backend"),
        schema_version=db.execute(text("SELECT version_num FROM alembic_version")).scalar(),
        setup_completed_at=setup_completed_at(db),
        keys={
            "master_key": Path(settings.master_key_path).exists(),
            "database_key": (data_dir / "db.key.enc").exists(),
            "backup_key": (data_dir / "backup.key.enc").exists(),
        },
    )


@router.get("/server")
def get_server(_: Admin, db: DB) -> ServerInfo:
    return _server_info(db)


@router.put("/server")
def update_server(body: ServerUpdate, request: Request, admin: Admin, db: DB) -> ServerInfo:
    before = company_name(db)
    if body.company_name.strip() != before:
        set_company_name(db, body.company_name)
        _log(db, request, admin, "admin.company_renamed",
             details={"from": before, "to": body.company_name.strip()})
    db.commit()
    return _server_info(db)
