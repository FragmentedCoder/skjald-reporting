"""Security settings Administrators can change (see docs/architecture.md, "Login")."""

from __future__ import annotations

import ipaddress
import json
from dataclasses import asdict, dataclass, fields
from typing import Any

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base

POLICY_KEY = "security_policy"

# The allowed range of each number, for the admin panel, the wizard and the API alike.
LIMITS: dict[str, tuple[int, int]] = {
    "min_password_length": (8, 64),
    "lockout_threshold": (3, 50),
    "lockout_minutes": (1, 1440),
    "idle_timeout_minutes": (5, 720),
    "max_session_hours": (1, 72),
}


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


@dataclass(frozen=True)
class SecurityPolicy:
    min_password_length: int = 12
    # Needs outbound HTTPS to api.pwnedpasswords.com; offline installs turn it off.
    breach_check_enabled: bool = True
    lockout_threshold: int = 10
    lockout_minutes: int = 15
    idle_timeout_minutes: int = 30
    max_session_hours: int = 12
    # Addresses (CIDR) the admin panel answers from; empty means any. Cleared from the
    # VM console with `python -m app.console reset-allowlist` if it ever locks everyone out.
    admin_allowlist: tuple[str, ...] = ()


def load_policy(db: Session) -> SecurityPolicy:
    stored = db.get(Setting, POLICY_KEY)
    if stored is None:
        return SecurityPolicy()
    known = {field.name for field in fields(SecurityPolicy)}
    values: dict[str, Any] = {k: v for k, v in json.loads(stored.value).items() if k in known}
    if "admin_allowlist" in values:
        values["admin_allowlist"] = tuple(values["admin_allowlist"])
    return SecurityPolicy(**values)


def save_policy(db: Session, policy: SecurityPolicy) -> None:
    db.merge(Setting(key=POLICY_KEY, value=json.dumps(asdict(policy))))


def normalize_networks(entries: list[str]) -> tuple[str, ...]:
    """Parse CIDR ranges (a bare address counts as a single host). Raises ValueError."""
    return tuple(str(ipaddress.ip_network(entry.strip(), strict=False)) for entry in entries)


def admin_allowed_from(policy: SecurityPolicy, ip: str | None) -> bool:
    if not policy.admin_allowlist:
        return True
    if ip is None:
        return False
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(address in ipaddress.ip_network(net) for net in policy.admin_allowlist)
