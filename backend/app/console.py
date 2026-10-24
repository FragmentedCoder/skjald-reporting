"""Commands for the VM console, for what the web UI can't do.

    docker compose exec app python -m app.console reset-allowlist

reset-allowlist clears the admin IP allowlist, for when it locks every
Administrator out. Running it needs shell access to the VM, which is the point.
"""

from __future__ import annotations

import sys
from dataclasses import replace

from sqlalchemy.orm import Session

from app import audit
from app.policy import load_policy, save_policy


def reset_allowlist(db: Session) -> int:
    policy = load_policy(db)
    removed = len(policy.admin_allowlist)
    save_policy(db, replace(policy, admin_allowlist=()))
    audit.append(db, "admin.allowlist_reset", actor_name="console", details={"removed": removed})
    return removed


def main(argv: list[str]) -> int:
    from app.db import get_engine

    if argv != ["reset-allowlist"]:
        print(__doc__, file=sys.stderr)
        return 2
    with Session(get_engine()) as db:
        removed = reset_allowlist(db)
        db.commit()
    print(f"Admin IP allowlist cleared ({removed} entries removed); the admin panel answers "
          "from any address again.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
