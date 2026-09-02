#!/usr/bin/env python3
"""Apply or reverse the numbered SQL migration series (ADR-0033).

ADR-0015 excludes every migration framework: migrations are numbered raw SQL. Its own
negative-consequences section names the cost -- "writing an apply-and-record runner by
hand" -- and `causalog.persistence.postgres.migrator` is that runner. This is its command
line.

  make migrate                    apply everything pending
  make migrate TARGET=0007        apply up to and including 0007
  make migrate-down TARGET=0003   reverse back to 0003, leaving 0001-0003 applied
  make migrate-down TARGET=0000   reverse everything

The ledger, not the schema, is the authority on what has been applied. A migration whose
file bytes changed after it was applied is a HARD ERROR naming the version -- never a
silent skip and never a re-application. An applied migration is history: editing one means
the database in front of you and the file in this repository describe different schemas,
and a runner that shrugs lets that difference grow unnoticed.

Exit codes: 0 applied (or nothing to do), 1 a migration or a checksum failed, 2 the
database is not reachable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

SQL_ROOT = REPO_ROOT / "deployment" / "sql"


def main() -> int:
    """Parse arguments and drive the runner."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--down",
        action="store_true",
        help="reverse migrations instead of applying them; --target is then required",
    )
    parser.add_argument(
        "--target",
        help="the version to stop at; applying includes it, reversing leaves it applied",
    )
    parser.add_argument(
        "--status", action="store_true", help="print the ledger and exit"
    )
    arguments = parser.parse_args()

    from causalog.core.errors import CausaLogError
    from causalog.persistence.postgres.connection import PostgresConnectionFactory
    from causalog.persistence.postgres.migrator import PostgresMigrator

    try:
        migrator = PostgresMigrator(PostgresConnectionFactory(), SQL_ROOT)
    except CausaLogError as error:
        print(f"MIGRATE: NOT-RUNNABLE. {error}")
        return 2

    try:
        applied = set(migrator.applied_versions())
    except Exception as error:  # noqa: BLE001 -- the driver's own connection failures
        print(f"MIGRATE: cannot reach the database. {error}")
        return 2

    if arguments.status:
        for migration in migrator.migrations:
            mark = "applied" if migration.version in applied else "PENDING"
            print(f"  {migration.version}_{migration.name:<32} {mark}")
        return 0

    try:
        if arguments.down:
            if not arguments.target:
                parser.error(
                    "--target is required when reversing. Reversing 'everything by "
                    "default' is how a development database becomes an incident."
                )
            reversed_versions = migrator.rollback(arguments.target)
            if not reversed_versions:
                print(f"MIGRATE: nothing to reverse above {arguments.target}.")
                return 0
            print(
                f"MIGRATE: reversed {len(reversed_versions)} migration(s), newest first."
            )
            for version in reversed_versions:
                print(f"  - {version}")
            return 0

        applied_now = migrator.migrate(arguments.target)
        if not applied_now:
            print("MIGRATE: schema is current; nothing pending.")
            return 0
        print(f"MIGRATE: applied {len(applied_now)} migration(s).")
        for version in applied_now:
            print(f"  + {version}")
        return 0
    except CausaLogError as error:
        print(f"MIGRATE FAILED: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
