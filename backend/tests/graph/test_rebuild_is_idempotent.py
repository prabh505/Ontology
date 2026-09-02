"""The projection is a function of the facts, so rebuilding it twice yields one graph.

ADR-0001 makes Neo4j a derived store and requires that dropping and rebuilding the whole
projection is always safe and routine. Three properties make that true rather than hoped
for, and each is asserted here:

  1. **Idempotence.** Two rebuilds of one run produce the same content hash and the same
     version. If they did not, "rebuild it" would be advice with a caveat.
  2. **Determinism as a tripwire.** A second rebuild whose hash DIFFERS is refused, loudly,
     as a determinism defect rather than retried -- it means something upstream is not a
     function of its inputs (`docs/architecture.md` §3.3 step 6). A rebuild that quietly
     accepted the new hash would erase the only signal that exists.
  3. **Run isolation.** Dropping one run's inferences leaves observed structure and every
     other run untouched. This is what makes a run comparable, deletable, and safe to
     re-derive.

These run against the in-memory projection so they need no Neo4j. What they assert is the
CONTRACT -- `GraphProjection`'s three guarantees -- and the Cypher adapter is held to the
same contract by `tests/graph/test_neo4j_projection.py`, which skips when the service is
absent. Asserting the contract in the fast suite and the wiring in the slow one is the
split that keeps both honest.
"""

from __future__ import annotations

from typing import Any

import pytest

from causalog.core.errors import ContractViolationError
from causalog.core.run import RunKey
from tests.fixtures import facts


@pytest.fixture
def projection() -> None:
    """Return an in-memory projection over a seeded repository, plus the run and facts."""
    from causalog.persistence.memory import InMemoryFactRepository, InMemoryGraphProjection

    repository = InMemoryFactRepository()
    citation = facts.evidence_record("row:1")
    repository.write_evidence_records([citation])
    participant = facts.entity("P1", citation=citation)
    repository.write_entities([participant], facts.ONTOLOGY_HASH)
    early = facts.event(
        "STAGE_ONE", facts.interval(0), citation=citation, participants=(participant,)
    )
    late = facts.event(
        "STAGE_TWO", facts.interval(10), citation=citation, participants=(participant,)
    )
    repository.write_events([early, late], facts.ONTOLOGY_HASH)
    held = facts.state(
        participant,
        "OPEN",
        facts.interval(0, span_days=10),
        derived_from=early,
        citation=citation,
    )
    repository.write_states([held], facts.DATASET_VERSION)

    run_id = repository.register_run(
        RunKey(
            dataset_version=facts.DATASET_VERSION,
            ontology_hash=facts.ONTOLOGY_HASH,
            rule_pack_version="1.0.0",
            engine_version="0.1.0",
            seed=0,
        )
    )
    repository.write_causal_edges([facts.causal_edge(early, late, run_id)])
    return InMemoryGraphProjection(repository=repository), repository, run_id, early, late


def test_rebuilding_twice_produces_an_identical_graph(projection: tuple[Any, ...]) -> None:
    graph, repository, run_id, *_ = projection
    first = graph.rebuild_from_facts(run_id)
    first_hash = graph.content_hash(run_id)
    second = graph.rebuild_from_facts(run_id)

    assert first == second, (
        "Two rebuilds of one run produced different versions. The projection is a function "
        "of the facts; if running the function twice gives two answers, 'just rebuild it' "
        "stops being safe advice (ADR-0001)."
    )
    assert graph.content_hash(run_id) == first_hash


def test_the_version_is_derived_from_the_content_and_the_run() -> None:
    """`gpv:` addresses BOTH, and neither alone would be enough.

    From the run alone, two builds of one run share a version and staleness is
    undetectable. From the hash alone, two runs that happen to project identically share
    one, and a reader cannot tell which run it is looking at.
    """
    from causalog.persistence.neo4j.projection import projection_version_for

    assert projection_version_for("run:a", "hash1") != projection_version_for("run:a", "hash2")
    assert projection_version_for("run:a", "hash1") != projection_version_for("run:b", "hash1")
    assert projection_version_for("run:a", "hash1") == projection_version_for("run:a", "hash1")
    assert projection_version_for("run:a", "hash1").startswith("gpv:")


def test_a_changed_hash_on_rebuild_is_refused_as_a_determinism_defect(
    projection: tuple[Any, ...],
) -> None:
    """Step 6 of the rebuild, asserted by planting the thing it exists to catch.

    A rebuild that produced a different graph from the same run is not a transient
    failure. Retrying it would hide the one observation that says the pipeline is not
    deterministic, so the rebuild refuses instead.
    """
    graph, repository, run_id, early, late = projection
    graph.rebuild_from_facts(run_id)

    # A fact appears that was not there when the first projection was built. In production
    # this is the shape of the defect -- a write that landed outside the run's inputs.
    citation = facts.evidence_record("row:2")
    repository.write_evidence_records([citation])
    extra = facts.event("STAGE_THREE", facts.interval(20), citation=citation)
    repository.write_events([extra], facts.ONTOLOGY_HASH)

    with pytest.raises(ContractViolationError, match="determinism defect"):
        graph.rebuild_from_facts(run_id)


def test_dropping_a_run_leaves_observed_structure_untouched(projection: tuple[Any, ...]) -> None:
    """Run isolation, which is what makes a run deletable without risk.

    Inferred elements carry a `run_id`; observed ones never do. So a drop CANNOT reach
    observed structure -- the isolation is structural, not a filter somebody remembered to
    write.
    """
    graph, repository, run_id, *_ = projection
    graph.rebuild_from_facts(run_id)

    entities_before = list(repository.entities_for_dataset(facts.DATASET_VERSION))
    events_before = list(repository.events_for_dataset(facts.DATASET_VERSION))
    states_before = list(repository.states_for_dataset(facts.DATASET_VERSION))

    removed = graph.drop_run(run_id)
    assert removed == 1

    assert list(repository.entities_for_dataset(facts.DATASET_VERSION)) == entities_before
    assert list(repository.events_for_dataset(facts.DATASET_VERSION)) == events_before
    assert list(repository.states_for_dataset(facts.DATASET_VERSION)) == states_before
    assert graph.projection_version(run_id) is None


def test_a_projection_for_an_unregistered_run_is_refused(projection: tuple[Any, ...]) -> None:
    graph, *_ = projection
    with pytest.raises(ContractViolationError, match="unregistered run"):
        graph.rebuild_from_facts("run:ffffffffffffffff")


def test_asking_for_a_version_the_store_is_not_serving_raises(projection: tuple[Any, ...]) -> None:
    """A stale projection is never served as if fresh (`docs/architecture.md` §3.2)."""
    from causalog.core.errors import ProjectionStaleError

    graph, repository, run_id, *_ = projection
    version = graph.rebuild_from_facts(run_id)
    graph.require_version(run_id, version)
    with pytest.raises(ProjectionStaleError, match="requested"):
        graph.require_version(run_id, "gpv:0000000000000000")


def test_the_two_edge_families_are_declared_separately() -> None:
    """PRECEDES (observed) and CAUSES (inferred) must never be one vocabulary.

    Asserted against the schema module rather than a live store, because the property is
    structural: an observed type that appeared in the inferred tuple would get a `run_id`
    existence constraint and stop being writable from facts, and an inferred type in the
    observed tuple would lose the constraint that makes run isolation work.
    """
    from causalog.persistence.neo4j import schema

    assert "PRECEDES" in schema.OBSERVED_RELATIONSHIP_TYPES
    assert "CAUSES" in schema.INFERRED_RELATIONSHIP_TYPES
    assert not set(schema.OBSERVED_RELATIONSHIP_TYPES) & set(
        schema.INFERRED_RELATIONSHIP_TYPES
    ), "A relationship type in both families would be scoped by both and by neither."

    statements = "\n".join(schema.schema_statements())
    for relationship_type in schema.INFERRED_RELATIONSHIP_TYPES:
        assert f"FOR ()-[r:{relationship_type}]-() REQUIRE r.run_id IS NOT NULL" in statements, (
            f"{relationship_type} has no run_id existence constraint. An inferred edge "
            "with no run is an inference with nothing to scope it -- the thing ADR-0013 "
            "makes impossible in PostgreSQL, and it must be equally impossible here or "
            "the projection becomes the way around it."
        )
    for relationship_type in schema.OBSERVED_RELATIONSHIP_TYPES:
        assert (
            f"FOR ()-[r:{relationship_type}]-() REQUIRE r.dataset_version IS NOT NULL" in statements
        )


def test_every_prd_47_label_and_type_is_declared() -> None:
    """prd.md §47 is the published graph contract; the schema must cover it exactly."""
    from causalog.persistence.neo4j import schema

    assert set(schema.NODE_LABELS) == {
        "Entity",
        "Event",
        "State",
        "Location",
        "Time",
        "ExternalEvent",
        "Recommendation",
        "Intervention",
    }
    assert set(schema.RELATIONSHIP_TYPES) == {
        "CAUSES",
        "PRECEDES",
        "BELONGS_TO",
        "LOCATED_AT",
        "TRANSITIONS_TO",
        "PART_OF",
        "AFFECTS",
        "BLOCKS",
        "AMPLIFIES",
        "REDUCES",
        "RECOMMENDS",
    }
