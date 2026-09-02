#!/usr/bin/env python3
"""Rebuild the Neo4j projection from PostgreSQL alone (ADR-0001 obligation).

PostgreSQL is the system of record. Neo4j is a derived projection. Dropping and rebuilding
the entire projection must always be a safe, routine operation, and ADR-0001 requires that
a command exists which does it. This is that command.

Procedure (documented in full in `docs/architecture.md` §3, implemented in
`causalog.persistence.neo4j.projection`):

  1. Resolve `run_id` to its RunKey: dataset_version, ontology_hash, rule_pack_version,
     engine_version, seed.
  2. Create the target projection in a versioned namespace. The live namespace is never
     mutated in place; a failed rebuild leaves the previous projection serving.
  3. Stream facts from PostgreSQL in canonical sequence (CONVENTIONS.md §11): events by
     (t_earliest, t_latest, event_id), entities by entity_id, edges by
     (source_event_id, target_event_id, edge_kind). Every SQL read carries an explicit
     ORDER BY on a unique key.
  4. Verify node and edge counts and the projection content hash against the values
     computed from PostgreSQL.
  5. Atomically swap the projection alias, then drop the superseded namespace.
  6. Assert the rebuilt projection hash equals the prior build's hash for the same run_id.
     A mismatch is a determinism defect, not a retryable error.

Never repairs a projection. A corrupt projection is rebuilt, never patched.

Exit codes: 0 rebuilt (or verified), 1 a check failed, 2 the stack is not reachable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))


def main() -> int:
    """Parse arguments and drive the rebuild."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-id", required=True, help="the content-addressed run identifier"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="stage, verify, and hash without swapping the live projection",
    )
    arguments = parser.parse_args()

    from neo4j.exceptions import Neo4jError, ServiceUnavailable

    from causalog.core.errors import CausaLogError
    from causalog.persistence.neo4j.projection import Neo4jProjection
    from causalog.persistence.postgres.connection import PostgresConnectionFactory
    from causalog.persistence.postgres.fact_repository import PostgresFactRepository

    try:
        factory = PostgresConnectionFactory()
        repository = PostgresFactRepository(factory)
        projection = Neo4jProjection.from_environment(repository, factory)
    except CausaLogError as error:
        print(f"REBUILD: NOT-RUNNABLE. {error}")
        return 2
    except ServiceUnavailable as error:
        print(f"REBUILD: NOT-RUNNABLE. Neo4j is not reachable: {error}")
        return 2

    # Driver errors are caught alongside CausaLogError because this script publishes an
    # exit-code contract (0 rebuilt / 1 a check failed / 2 stack not reachable) and an
    # unhandled exception honours none of it. Found the first time the rebuild was run
    # against a live Neo4j: the Enterprise-only constraint failure of DEF-0004 surfaced as
    # a raw `neo4j.exceptions.DatabaseError` traceback, which exits 1 by accident rather
    # than by decision and buries the one line that says what to do.
    try:
        report = projection.rebuild(arguments.run_id, verify_only=arguments.verify_only)
    except CausaLogError as error:
        print(f"REBUILD FAILED: {error}")
        return 1
    except ServiceUnavailable as error:
        print(f"REBUILD: NOT-RUNNABLE. Neo4j became unreachable mid-rebuild: {error}")
        return 2
    except Neo4jError as error:
        print(f"REBUILD FAILED: Neo4j rejected a statement: {error}")
        return 1

    verb = "verified" if arguments.verify_only else "rebuilt"
    print(f"REBUILD: {verb} {report.run_id}")
    print(f"  namespace         {report.namespace}")
    print(f"  projection version {report.graph_projection_version}")
    print(f"  content hash      {report.content_hash}")
    print(f"  nodes / edges     {report.node_count} / {report.edge_count}")
    print(f"  invariants        enforced by {report.enforcement}")
    if report.matched_previous_build is None:
        print("  determinism       first build of this run; nothing to compare against")
    else:
        print("  determinism       content hash matches the previous build of this run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
