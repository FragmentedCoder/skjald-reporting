"""Roles and what each one may do: the access table in docs/architecture.md.

Routes ask for a capability, never a role, so this table is the one place that
says who may do what. Which customers someone sees (all, assigned, names only)
is a separate question, answered when customers exist.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app import audit, clock
from app.db import Base, UTCDateTime
from app.users import User


class Role(StrEnum):
    ADMINISTRATOR = "administrator"
    REPORT_DESIGNER = "report_designer"
    TECHNICIAN = "technician"
    REVIEWER = "reviewer"
    AUDITOR = "auditor"


class Capability(StrEnum):
    MANAGE_CUSTOMERS = "manage_customers"
    CREATE_PROJECTS_AND_REPORTS = "create_projects_and_reports"
    FILL_IN_REPORTS = "fill_in_reports"
    REVIEW_AND_COUNTERSIGN = "review_and_countersign"
    BUILD_TEMPLATES = "build_templates"
    EDIT_LIBRARY = "edit_library"
    LOCK_LIBRARY_ENTRIES = "lock_library_entries"
    CHECK_SIGNED_REPORTS = "check_signed_reports"
    EDIT_STYLES = "edit_styles"
    ADMINISTER = "administer"  # users, roles, policies, keys, backups, settings
    BREAK_CHECKOUTS = "break_checkouts"
    READ_AUDIT_LOG = "read_audit_log"


_A, _D, _T, _R, _U = (
    Role.ADMINISTRATOR,
    Role.REPORT_DESIGNER,
    Role.TECHNICIAN,
    Role.REVIEWER,
    Role.AUDITOR,
)

GRANTS: dict[Capability, frozenset[Role]] = {
    Capability.MANAGE_CUSTOMERS: frozenset({_A}),
    Capability.CREATE_PROJECTS_AND_REPORTS: frozenset({_A, _T}),
    Capability.FILL_IN_REPORTS: frozenset({_A, _T}),
    Capability.REVIEW_AND_COUNTERSIGN: frozenset({_A, _R}),
    Capability.BUILD_TEMPLATES: frozenset({_A, _D}),
    Capability.EDIT_LIBRARY: frozenset({_A, _D, _T}),
    Capability.LOCK_LIBRARY_ENTRIES: frozenset({_A}),
    Capability.CHECK_SIGNED_REPORTS: frozenset(Role),
    Capability.EDIT_STYLES: frozenset({_A, _D}),
    Capability.ADMINISTER: frozenset({_A}),
    Capability.BREAK_CHECKOUTS: frozenset({_A}),
    Capability.READ_AUDIT_LOG: frozenset({_A, _U}),
}


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(30), primary_key=True)
    granted_at: Mapped[datetime] = mapped_column(UTCDateTime)
    granted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


def roles_of(db: Session, user_id: int) -> set[Role]:
    return {Role(r) for r in db.scalars(select(UserRole.role).where(UserRole.user_id == user_id))}


def can(roles: set[Role], capability: Capability) -> bool:
    return bool(roles & GRANTS[capability])


def revoke_role(
    db: Session, user: User, role: Role, *, actor: User | None, ip: str | None
) -> None:
    """Take a role away, and log who did it. Does nothing if they don't have it."""
    held = db.get(UserRole, (user.id, role.value))
    if held is None:
        return
    db.delete(held)
    audit.append(
        db,
        "auth.role.revoked",
        actor_id=actor.id if actor else None,
        actor_name=actor.username if actor else None,
        target_type="user",
        target_id=str(user.id),
        ip=ip,
        details={"role": role.value, "user": user.username},
    )


def grant_role(
    db: Session, user: User, role: Role, *, actor: User | None, ip: str | None
) -> None:
    """Give user a role, and log who did it. Does nothing if they have it already."""
    if db.get(UserRole, (user.id, role.value)) is not None:
        return
    db.add(
        UserRole(
            user_id=user.id,
            role=role.value,
            granted_at=clock.utcnow(),
            granted_by=actor.id if actor else None,
        )
    )
    audit.append(
        db,
        "auth.role.granted",
        actor_id=actor.id if actor else None,
        actor_name=actor.username if actor else None,
        target_type="user",
        target_id=str(user.id),
        ip=ip,
        details={"role": role.value, "user": user.username},
    )
