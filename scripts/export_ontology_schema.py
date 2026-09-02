#!/usr/bin/env python3
"""Generate `ontology/_schema/ontology.schema.json` from the DSL models, or check it.

The pydantic models in `causalog.ontology_runtime.dsl` are the normative description of the
domain-pack schema (ADR-0026). This script renders them as JSON Schema so tooling outside
Python can validate a pack, and `--check` fails the build when the published file is not
what the models produce.

Why generated rather than hand-authored: a hand-written schema beside a code validator is
two descriptions of one contract, free to disagree. The disagreement surfaces as a pack one
accepts and the other rejects, and nobody can say which is right.

`--self-test` runs first in CI, as every enforcement script in this repository does. A
check observed only to pass has not been observed to work (DEF-0001).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

from causalog.ontology_runtime.schema_export import render_schema  # noqa: E402

SCHEMA_PATH = REPO_ROOT / "ontology" / "_schema" / "ontology.schema.json"


def self_test() -> int:
    """Prove the check rejects a stale file before trusting it to accept a current one."""
    current = render_schema()

    if not current.endswith("\n"):
        print(
            "SELF-TEST FAILED: rendered schema does not end with exactly one newline."
        )
        return 1
    if render_schema() != current:
        print(
            "SELF-TEST FAILED: two renders of the same models differ; output is not stable."
        )
        return 1

    stale = current.replace('"title"', '"titl3"', 1)
    if stale == current:
        print(
            "SELF-TEST FAILED: could not construct a stale variant; the probe is broken."
        )
        return 1
    if _compare(stale, current) == 0:
        print("SELF-TEST FAILED: the comparison accepted a stale schema.")
        return 1
    if _compare(current, current) != 0:
        print("SELF-TEST FAILED: the comparison rejected a current schema.")
        return 1

    for required in ("$schema", "$id", "pack_schema_version", "$defs"):
        if required not in current:
            print(f"SELF-TEST FAILED: rendered schema omits {required!r}.")
            return 1

    print(
        "SELF-TEST: export_ontology_schema observed to reject a stale schema and accept a "
        "current one."
    )
    return 0


def _compare(published: str, generated: str) -> int:
    """Return 0 when the two texts agree, 1 otherwise."""
    return 0 if published == generated else 1


def check() -> int:
    """Fail if the published schema is not what the models currently produce."""
    generated = render_schema()
    if not SCHEMA_PATH.is_file():
        print(
            f"ONTOLOGY SCHEMA: {SCHEMA_PATH} does not exist. Run this script with --write."
        )
        return 1
    published = SCHEMA_PATH.read_text(encoding="utf-8")
    if _compare(published, generated) != 0:
        print(
            f"ONTOLOGY SCHEMA: {SCHEMA_PATH.relative_to(REPO_ROOT)} is stale.\n"
            "    The published JSON Schema no longer matches "
            "causalog.ontology_runtime.dsl.\n"
            "    The models are normative (ADR-0026); regenerate rather than hand-editing:\n"
            "        python scripts/export_ontology_schema.py --write"
        )
        return 1
    print(
        f"ONTOLOGY SCHEMA: {SCHEMA_PATH.relative_to(REPO_ROOT)} matches the DSL models."
    )
    return 0


def write() -> int:
    """Regenerate the published schema from the models."""
    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(render_schema(), encoding="utf-8")
    print(f"ONTOLOGY SCHEMA: wrote {SCHEMA_PATH.relative_to(REPO_ROOT)}.")
    return 0


def main() -> int:
    """Parse arguments and dispatch. Default action is --check."""
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--self-test", action="store_true", help="prove the check can reject"
    )
    group.add_argument(
        "--write", action="store_true", help="regenerate the published schema"
    )
    group.add_argument(
        "--check", action="store_true", help="fail if the published file is stale"
    )
    arguments = parser.parse_args()
    if arguments.self_test:
        return self_test()
    if arguments.write:
        return write()
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
