"""Imports every module that defines tables, so Base.metadata is complete for migrations."""

import app.audit
import app.auth.mfa
import app.auth.sessions
import app.policy
import app.roles
import app.users  # noqa: F401
