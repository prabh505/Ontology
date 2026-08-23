#!/usr/bin/env python3
"""Rebuild the Neo4j projection from PostgreSQL alone (ADR-0001 obligation).

PostgreSQL is the system of record. Neo4j is a derived projection. Dropping and rebuilding
the entire projection must always be a safe operation, and ADR-0001 requires that a command
exists which does it. This is that command.

Procedure (documented in full in `docs/architecture.md` §3):

  1. Resolve `run_id` to its RunKey: dataset_version, ontology_hash, rule_pack_version,
     engine_version, seed.
  2. Create the target projection in a versioned namespace. The live namespace is never
     mutated in place; a failed rebuild must leave the previous projection serving.
  3. Stream facts from PostgreSQL in canonical sequence (CONVENTIONS.md §11): events by
     (t_earliest, t_latest, event_id), entities by entity_id, edges by
     (source_event_id, target_event_id, edge_type). Every SQL read carries an explicit
     ORDER BY on a unique key.
  4. Verify node and edge counts and the projection content hash against the values
     computed from PostgreSQL.
  5. Atomically swap the projection alias, then drop the superseded namespace.
  6. Assert the rebuilt projection hash equals the prior build's hash for the same run_id.
     A mismatch is a determinism defect, not a retryable error.

Never repairs a projection. A corrupt projection is rebuilt, never patched.
"""

from __future__ import annotations

import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ADAPTER = (
    REPO_ROOT
    / "backend"
    / "src"
    / "causalog"
    / "persistence"
    / "neo4j"
    / "projection.py"
)


def main() -> int:
    """Parse arguments and drive the rebuild."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-id", required=True, help="the content-addressed run identifier"
    )
    parser.add_argument(
        "--verify-only", action="store_true", help="hash and compare without swapping"
    )
    parser.parse_args()

    if not ADAPTER.exists():
        print(
            "REBUILD: NOT-YET-RUNNABLE.\n"
            f"  No projection adapter at {ADAPTER.relative_to(REPO_ROOT).as_posix()}.\n"
            "  The six-step procedure above is the contract module 8 (Temporal Graph\n"
            "  Builder) implements; it owns the projection build (ADR-0001).\n"
            "  Tracked in PROGRESS.md as a known gap."
        )
        return 2

    raise NotImplementedError(
        "draft contract; implemented with module 8 (Temporal Graph Builder)"
    )


if __name__ == "__main__":
    raise SystemExit(main())
