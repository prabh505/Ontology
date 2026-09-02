#!/usr/bin/env python3
"""Report drift between the system of record and the derived graph projection.

ADR-0001 makes Neo4j a projection with no authority: every node and every relationship in
it must be a function of PostgreSQL facts, and "a write with no backing PostgreSQL fact is
a defect". That claim is only worth what a check makes it worth. `rebuild_graph.py`
verifies at build time; this command verifies at any time, which is the case that matters
-- drift arrives after the build, from a manual Cypher session, a partial failure, or a
projection nobody rebuilt after new facts landed.

WHAT IT COMPARES

  1. Per-family counts. Entities, events, and states in the projection against the same
     counts computed from the facts; inferred relationships against the run's causal edges.
  2. The content hash. Recomputed from the live namespace and compared against the hash
     the registry recorded at swap time. A difference means the store changed after the
     build, which the counts alone can miss -- an element edited in place keeps the count
     identical.
  3. The registry itself. A run with no live projection, or with more than one, is
     reported here rather than discovered by a reader mid-query.

WHAT IT DOES NOT DO: repair. A drifted projection is REBUILT, never patched. Patching
would produce a graph that matches the facts and was not derived from them, and nothing
downstream could tell the two apart.

`--self-test` proves the comparison rejects a planted mismatch and accepts a matching pair,
before any scan runs. Every enforcement script here does that: a check observed only to
pass has not been observed to work (DEF-0001, ADR-0019).

Exit codes: 0 no drift, 1 drift found, 2 the stack is not reachable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

#: Projection labels and relationship families, paired with the fact family each is
#: derived from. `Location` and `ExternalEvent` are deliberately absent: they are
#: ADDITIONAL labels on Entity and Event nodes, so their counts are subsets rather than
#: additions, and comparing them against a fact count would report drift on every run.
COMPARED = (
    ("Entity", "entity"),
    ("Event", "event"),
    ("State", "state"),
)


def compare_counts(
    projected: dict[str, int], expected: dict[str, int], inferred_types: tuple[str, ...]
) -> list[str]:
    """Return one line per disagreement between projection and facts.

    A pure function of two dicts, so the self-test can drive it with planted values and
    the scan can drive it with real ones. That shape is deliberate -- a comparison that
    could only run against a live stack could only be tested against a live stack.
    """
    drift = []
    for label, family in COMPARED:
        actual = projected.get(label, 0)
        if actual != expected.get(family, 0):
            drift.append(
                f"{label}: projection has {actual}, the facts have "
                f"{expected.get(family, 0)}"
            )
    projected_edges = sum(projected.get(name, 0) for name in inferred_types)
    if projected_edges != expected.get("causal_edge", 0):
        drift.append(
            f"inferred relationships: projection has {projected_edges}, the facts have "
            f"{expected.get('causal_edge', 0)}"
        )
    return drift


def self_test() -> int:
    """Prove the comparison rejects a mismatch and accepts a match."""
    inferred = ("CAUSES", "AMPLIFIES")
    matching_projection = {
        "Entity": 3,
        "Event": 9,
        "State": 4,
        "CAUSES": 5,
        "AMPLIFIES": 2,
    }
    matching_facts = {"entity": 3, "event": 9, "state": 4, "causal_edge": 7}

    failures = 0
    if compare_counts(matching_projection, matching_facts, inferred):
        print("SELF-TEST FAILED: a matching projection was reported as drifted.")
        failures += 1

    for description, projection in (
        ("a missing node", {**matching_projection, "Event": 8}),
        ("an extra node with no backing fact", {**matching_projection, "Entity": 4}),
        ("a deleted inferred edge", {**matching_projection, "CAUSES": 4}),
        ("an empty projection", {}),
    ):
        if not compare_counts(projection, matching_facts, inferred):
            print(f"SELF-TEST FAILED: the check did not report drift -- {description}.")
            failures += 1

    # The subset-label trap, planted because it is the mistake this check would most
    # plausibly make: Location and ExternalEvent are additional labels on nodes already
    # counted as Entity and Event, so a comparison that summed every label would report
    # drift on a projection that is perfectly correct.
    with_subset_labels = {**matching_projection, "Location": 2, "ExternalEvent": 3}
    if compare_counts(with_subset_labels, matching_facts, inferred):
        print(
            "SELF-TEST FAILED: additional labels (Location, ExternalEvent) were counted "
            "as extra nodes. They are subsets of Entity and Event, not additions."
        )
        failures += 1

    if failures:
        return failures
    print(
        "SELF-TEST: drift comparison observed to reject a mismatch and accept a match."
    )
    return 0


def main() -> int:
    """Run the self-test, or compare a live projection against the facts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", help="the content-addressed run identifier")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="prove the comparison before running it",
    )
    arguments = parser.parse_args()

    if arguments.self_test:
        return 1 if self_test() else 0
    if not arguments.run_id:
        parser.error("--run-id is required unless --self-test is given")

    from causalog.core.errors import CausaLogError
    from causalog.persistence.neo4j import INFERRED_RELATIONSHIP_TYPES
    from causalog.persistence.neo4j.projection import Neo4jProjection
    from causalog.persistence.postgres.connection import PostgresConnectionFactory
    from causalog.persistence.postgres.fact_repository import PostgresFactRepository

    try:
        factory = PostgresConnectionFactory()
        repository = PostgresFactRepository(factory)
        projection = Neo4jProjection.from_environment(repository, factory)
    except CausaLogError as error:
        print(f"DRIFT CHECK: NOT-RUNNABLE. {error}")
        return 2

    run = repository.run(arguments.run_id)
    if run is None:
        print(
            f"DRIFT CHECK: no run registered as {arguments.run_id!r}. A projection for an "
            "unregistered run has no facts to be compared against."
        )
        return 1

    try:
        recorded_hash = _recorded_hash(factory, arguments.run_id)
        projected = projection.element_counts(arguments.run_id)
        live_hash = projection.content_hash(arguments.run_id)
    except CausaLogError as error:
        print(f"DRIFT CHECK: {error}")
        return 1

    expected = repository.fact_counts(run.key.dataset_version, arguments.run_id)
    drift = compare_counts(projected, expected, INFERRED_RELATIONSHIP_TYPES)

    if recorded_hash is None:
        drift.append(
            "the registry holds no content hash for the live projection, so nothing can "
            "certify what was built"
        )
    elif recorded_hash != live_hash:
        drift.append(
            f"content hash: the store now hashes to {live_hash!r}; the registry recorded "
            f"{recorded_hash!r} at swap time. The projection changed after it was built."
        )

    if not drift:
        print(f"DRIFT CHECK: run {arguments.run_id} -- projection matches the facts.")
        print(f"  content hash {live_hash}")
        for label, family in COMPARED:
            print(f"  {label:<10} {projected.get(label, 0):>10} == {expected[family]}")
        return 0

    print(f"DRIFT CHECK: run {arguments.run_id} -- {len(drift)} disagreement(s).")
    for line in drift:
        print(f"  - {line}")
    print(
        "\nA drifted projection is REBUILT, never patched: a graph that matches the facts "
        "without having been derived from them is indistinguishable from one that was.\n"
        f"  make rebuild-graph RUN_ID={arguments.run_id}"
    )
    return 1


def _recorded_hash(factory: object, run_id: str) -> str | None:
    """Return the content hash the registry recorded when this build went live."""
    with factory.connect() as connection, connection.cursor() as cursor:  # type: ignore[attr-defined]
        cursor.execute(
            "SELECT content_hash FROM graph_projection WHERE run_id = %s AND status = 'live'",
            (run_id,),
        )
        record = cursor.fetchone()
    return None if record is None else str(record[0])


if __name__ == "__main__":
    raise SystemExit(main())
