#!/usr/bin/env python3
"""Every forward migration has an exact reverse (ADR-0033).

ADR-0015 excludes every migration framework, so the property a framework would have given
for free -- "this migration can be undone" -- has to be checked. This is that check.

Four rules, each checked mechanically:

  1. Every `deployment/sql/migrations/NNNN_x.sql` has `deployment/sql/down/NNNN_x.sql`.
     A migration nobody can undo is a migration nobody will risk applying, and
     "forward-only" in practice means "irreversible in an incident".
  2. Every reverse has a forward. A reversal for a migration that was never written would
     undo something nothing created.
  3. Every filename matches `NNNN_<verb>_<subject>.sql` (`CONVENTIONS.md` §5). The numeric
     prefix is the only thing ordering the series.
  4. The series is contiguous from 0001. A gap usually means a migration was deleted
     rather than reversed, which leaves the ledger describing a schema nobody can rebuild.

`--self-test` proves each rule rejects the violation it exists to catch, before the scan
runs. Every enforcement script in this repository does this: a check observed only to pass
has not been observed to work (DEF-0001, ADR-0019).
"""

from __future__ import annotations

import contextlib
import io
import re
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SQL_ROOT = REPO_ROOT / "deployment" / "sql"

FILENAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


def check(sql_root: Path) -> int:
    """Run every rule against a migration tree. Returns the violation count."""
    forward_dir = sql_root / "migrations"
    reverse_dir = sql_root / "down"
    failures = 0

    if not forward_dir.is_dir():
        print(
            f"{forward_dir}: no migration directory. The series is discovered from the"
        )
        print("  directory, so an absent one is an error and never an empty series.")
        return 1

    forward = sorted(forward_dir.glob("*.sql"))
    reverse = sorted(reverse_dir.glob("*.sql")) if reverse_dir.is_dir() else []

    # Rule 3 -- naming.
    for path in forward + reverse:
        if FILENAME.match(path.name) is None:
            print(
                f"{path.relative_to(sql_root).as_posix()}: does not match "
                "NNNN_<verb>_<subject>.sql (CONVENTIONS.md §5). The numeric prefix is the "
                "only thing ordering the series."
            )
            failures += 1

    forward_names = {path.name for path in forward}
    reverse_names = {path.name for path in reverse}

    # Rule 1 -- every forward has a reverse.
    for name in sorted(forward_names - reverse_names):
        print(
            f"migrations/{name} has no reverse at down/{name}. Every forward migration "
            "ships with its exact reverse (ADR-0033): a migration nobody can undo is one "
            "nobody will risk applying."
        )
        failures += 1

    # Rule 2 -- every reverse has a forward.
    for name in sorted(reverse_names - forward_names):
        print(
            f"down/{name} has no forward migration. A reversal for a migration that was "
            "never written would undo something nothing created."
        )
        failures += 1

    # Rule 4 -- the series is contiguous.
    versions = sorted(
        match.group(1) for path in forward if (match := FILENAME.match(path.name))
    )
    expected = [f"{index:04d}" for index in range(1, len(versions) + 1)]
    if versions and versions != expected:
        print(
            f"migration series is not contiguous: found {versions}, expected {expected}. "
            "A gap usually means a migration was deleted rather than reversed, which "
            "leaves the ledger describing a schema nobody can rebuild."
        )
        failures += 1

    return failures


def self_test() -> int:
    """Prove each rule rejects its violation and accepts a clean tree."""
    failures = 0
    scratch = Path(tempfile.mkdtemp(prefix="causalog-migration-selftest-"))
    try:
        cases: list[tuple[str, dict[str, list[str]], bool]] = [
            (
                "a clean pair is accepted",
                {
                    "migrations": ["0001_create_thing.sql"],
                    "down": ["0001_create_thing.sql"],
                },
                False,
            ),
            (
                "a forward with no reverse is rejected",
                {"migrations": ["0001_create_thing.sql"], "down": []},
                True,
            ),
            (
                "a reverse with no forward is rejected",
                {"migrations": [], "down": ["0001_create_thing.sql"]},
                True,
            ),
            (
                "a dated filename is rejected",
                {
                    "migrations": ["20260829_create_thing.sql"],
                    "down": ["20260829_create_thing.sql"],
                },
                True,
            ),
            (
                "a gap in the series is rejected",
                {
                    "migrations": ["0001_create_thing.sql", "0003_create_other.sql"],
                    "down": ["0001_create_thing.sql", "0003_create_other.sql"],
                },
                True,
            ),
        ]
        for index, (description, tree, must_fail) in enumerate(cases):
            root = scratch / f"case{index}"
            for directory, names in tree.items():
                (root / directory).mkdir(parents=True, exist_ok=True)
                for name in names:
                    (root / directory / name).write_text("SELECT 1;\n")
            (root / "down").mkdir(parents=True, exist_ok=True)
            # The rules print their diagnostics, and a self-test that dumped five
            # deliberate violations would bury the one line that matters. Captured, not
            # suppressed: a failing case prints its description below.
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                observed = check(root) > 0
            if observed != must_fail:
                verb = "reject" if must_fail else "accept"
                print(f"SELF-TEST FAILED: the check did not {verb} -- {description}")
                print(captured.getvalue())
                failures += 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    if failures:
        return failures
    print("SELF-TEST: migration-pair rules observed to reject and to accept.")
    return 0


def main() -> int:
    """Run the self-test or the scan."""
    if "--self-test" in sys.argv:
        return 1 if self_test() else 0
    failures = check(SQL_ROOT)
    if failures:
        print(f"\n{failures} migration-pair violation(s). ADR-0033.")
        return 1
    print("migration pairs: every forward migration has its exact reverse.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
