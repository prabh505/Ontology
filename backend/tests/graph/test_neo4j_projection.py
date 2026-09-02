"""The Cypher adapter against a live Neo4j -- the wiring, not the contract.

`test_rebuild_is_idempotent.py` asserts the `GraphProjection` CONTRACT against the
in-memory projection, so it runs in the fast suite and needs no service. This file asserts
the things only a real server can answer: that the schema can actually be applied, that the
edition split of DEF-0004 works on the edition this repository ships, and that the
compensating checks fire.

Both `schema.py` and `test_rebuild_is_idempotent.py` referred to this file before it
existed. That is its own small lesson: a docstring naming a test is not a test, and the
adapter went unrun against a live server while two modules said it was covered.

Skips with a stated reason when `CAUSALOG_NEO4J_URI` is unset -- never passes silently.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests import persistence_support
from tests.fixtures import facts


@pytest.fixture
def live_projection() -> Any:
    """Yield `(projection, run_id, namespace)` for a run staged into a live Neo4j."""
    from causalog.core.run import RunKey
    from causalog.persistence.neo4j.projection import Neo4jProjection
    from causalog.persistence.postgres.fact_repository import PostgresFactRepository

    persistence_support.neo4j_settings()  # skips, with a reason, when there is no service
    factory_iterator = persistence_support.migrated_database()
    factory = next(factory_iterator)

    persistence_support.register_dataset(factory, facts.DATASET_VERSION, facts.ONTOLOGY_HASH)
    repository = PostgresFactRepository(factory)
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

    projection = Neo4jProjection.from_environment(repository, factory)
    report = projection.rebuild(run_id)
    try:
        yield projection, run_id, report
    finally:
        projection.drop_run(run_id)
        projection._drop_namespace(report.namespace)
        # The driver holds a socket, and `filterwarnings = ["error"]` turns the
        # ResourceWarning from an unclosed one into a test error -- correctly, because a
        # rebuild that leaks a connection per run would exhaust the pool in a long session.
        projection._driver.close()
        for _ in factory_iterator:  # run the teardown of migrated_database
            pass


def test_the_schema_applies_against_the_edition_this_repository_ships(
    live_projection: Any,
) -> None:
    """DEF-0004, as a regression.

    The first time the rebuild was pointed at a live Neo4j it aborted on step 2:

        Neo.DatabaseError.Schema.ConstraintCreationFailed
        Property existence constraint requires Neo4j Enterprise Edition

    `schema.py` declared node and relationship existence constraints, which are an
    Enterprise feature, and `docker-compose.yml` pins `neo4j:5.26.0-community`. Every
    statement was exercised by unit tests over the module's string tuples, which is how a
    feature-gated family of statements read as working code for as long as it did.

    That this test reaches its assertions at all is the assertion: `rebuild` completed.
    """
    _, _, report = live_projection
    assert report.content_hash
    assert report.enforcement in {"constraints", "post-write checks"}


def test_the_report_says_which_enforcement_was_in_force(live_projection: Any) -> None:
    """The two paths are not equally strong, so a report may not hide which one it used.

    On Enterprise the database makes a violation unrepresentable. On Community it is
    detected after the write and before the swap. A build that did not say which would let
    a reader assume the stronger one.
    """
    projection, _, report = live_projection
    expected = (
        "constraints" if projection._supports_existence_constraints() else "post-write checks"
    )
    assert report.enforcement == expected


def test_the_community_check_is_observed_to_reject(live_projection: Any) -> None:
    """A compensating check that cannot be seen to fire is not a control (ADR-0019).

    This is the whole reason the Community path is acceptable at all. An inferred edge with
    no `run_id` is planted directly through the driver -- the exact state the Enterprise
    constraint made impossible, and the exact state that would let `drop_run` silently miss
    an inference -- and the checker must refuse it.
    """
    from causalog.core.errors import ContractViolationError

    projection, _, report = live_projection
    namespace = report.namespace

    with projection._driver.session() as session:
        session.run(
            "MATCH (a:Event {namespace: $ns}), (b:Event {namespace: $ns}) "
            "WHERE a.event_id <> b.event_id WITH a, b LIMIT 1 "
            "CREATE (a)-[:CAUSES {namespace: $ns, provenance_class: 'INFERRED'}]->(b)",
            ns=namespace,
        )

    with pytest.raises(ContractViolationError) as raised:
        projection._verify_existence_invariants(namespace)
    assert "run_id" in str(raised.value)
    assert "DEF-0004" in str(raised.value)


def test_the_community_check_accepts_a_clean_projection(live_projection: Any) -> None:
    """The other half of ADR-0019: a check that rejects everything is equally useless."""
    projection, _, report = live_projection
    projection._verify_existence_invariants(report.namespace)


def test_an_observed_edge_carrying_a_run_id_is_refused(live_projection: Any) -> None:
    """The invariant NO edition ever enforced, and the one `drop_run` depends on.

    `drop_run` is safe because observed edges have no `run_id` to match. Neither the
    Enterprise constraints nor anything else checked the converse -- that an observed edge
    never acquires one -- so a projection bug there would have made `drop_run` delete
    observed structure while every constraint stayed green.
    """
    from causalog.core.errors import ContractViolationError

    projection, run_id, report = live_projection
    namespace = report.namespace

    with projection._driver.session() as session:
        session.run(
            "MATCH (a:Event {namespace: $ns}), (b:Event {namespace: $ns}) "
            "WHERE a.event_id <> b.event_id WITH a, b LIMIT 1 "
            "CREATE (a)-[:PRECEDES {namespace: $ns, dataset_version: $dv, run_id: $run}]->(b)",
            ns=namespace,
            dv=facts.DATASET_VERSION,
            run=run_id,
        )

    with pytest.raises(ContractViolationError) as raised:
        projection._verify_existence_invariants(namespace)
    assert "PRECEDES" in str(raised.value)


def test_every_enterprise_constraint_has_a_community_check() -> None:
    """The two enforcement paths must cover the same ground, derived from the same tuples.

    Needs no service. If a relationship type is added to `INFERRED_RELATIONSHIP_TYPES` and
    only one of the two paths picks it up, the invariant holds on one edition and silently
    does not hold on the other -- which is worse than it holding on neither, because the
    Enterprise run would certify it.
    """
    from causalog.persistence.neo4j import schema

    checks = " ".join(description for description, _ in schema.existence_invariant_queries())
    for relationship_type in schema.INFERRED_RELATIONSHIP_TYPES:
        assert f"{relationship_type} edges with no run_id" in checks
        assert f"{relationship_type} edges with no provenance_class" in checks
    for relationship_type in schema.OBSERVED_RELATIONSHIP_TYPES:
        assert f"{relationship_type} edges with no dataset_version" in checks
        assert f"{relationship_type} edges carrying a run_id" in checks


def test_the_community_statement_set_omits_only_the_enterprise_family() -> None:
    """Dropping the existence constraints must not quietly drop the keys or the indexes."""
    from causalog.persistence.neo4j import schema

    community = set(schema.schema_statements(existence_constraints=False))
    enterprise = set(schema.schema_statements(existence_constraints=True))

    assert community < enterprise
    assert enterprise - community == set(schema.existence_constraint_statements())
    assert set(schema.UNIQUENESS_CONSTRAINTS) <= community
    assert set(schema.INDEXES) <= community
    assert not any("IS NOT NULL" in statement for statement in community)
