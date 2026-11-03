#!/usr/bin/env python3
"""Reset the demo database to its pristine seeded state.

    python scripts/reset_demo.py

Reads DATABASE_URL from the environment (backend/.env is used as a fallback), then
drops every table/view/routine in that schema and rebuilds them from
``database/schema_paas.sql`` + ``database/seed_paas.sql``. Safe to run from a PaaS
cron job, a systemd timer or by hand.

WARNING: this deletes all data in the configured database. Point it at the demo
database only - never at a database that holds real records.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.core.config import settings  # noqa: E402  (loads .env)
from backend.app.core.db_bootstrap import reset_demo_database  # noqa: E402


def main() -> int:
    url = os.environ.get("DATABASE_URL") or settings.DATABASE_URL
    database = url.rsplit("/", 1)[-1].split("?")[0]
    print(f"Resetting database '{database}' ...")
    try:
        report = reset_demo_database(url)
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    print("Done. Demo data is back to the seeded state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
