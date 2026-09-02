"""One contract suite, run against BOTH the in-memory fake and the PostgreSQL adapter.

This file exists to solve the problem every fake has: it drifts. A fake passes, the real
adapter does not, and nobody finds out until the slowest job in CI. Parameterizing the
suite over both implementations makes that impossible by construction -- a behaviour the
two do not share fails in one of them, here, in the fast suite.

The PostgreSQL parameter skips with a stated reason when no database is reachable. It is
never silently dropped: a suite that quietly halved itself would report exactly like one
that ran in full (DEF-0001).

What is asserted here is BEHAVIOUR, not implementation: canonical sequencing, the
dataset/run scoping asymmetry, the law refusals, and idempotent writes. None of it asserts
that a causal conclusion is correct -- there is no ground truth for causality in this
dataset (`CONVENTIONS.md` §14), and every property below is structural.
"""

from __future__ import annotations

from typing import Any

import pytest

from causalog.core.errors import ContractViolationError, LawViolationError
from causalog.core.run import RunKey
from tests import persistence_support
from tests.fixtures import facts


def _in_memory() -> None:
    from causalog.persistence.memory import InMemoryFactRepository

    return InMemoryFactRepository(), None


def _postgres() -> None:
    from causalog.persistence.postgres.fact_repository import PostgresFactRepository

    generator = persistence_support.migrated_database()
    factory = next(generator)
    persistence_support.register_dataset(factory, facts.DATASET_VERSION, facts.ONTOLOGY_HASH)
    repository = PostgresFactRepository(factory)
    # Stashed so `pin_dataset_version` below can satisfy the foreign key that only the
    # real schema has. The fake has no version registry, which is exactly the kind of
    # difference this parameterized suite exists to keep visible rather than to paper over.
    repository.test_factory = factory  # type: ignore[attr-defined]
    return repository, generator


def pin_dataset_version(repository: Any, dataset_version: str) -> None:
    """Register a dataset version, where the implementation has a registry to put it in.

    A no-op against the in-memory fake, which has no version tables. The asymmetry is
    deliberate and is not a hole: migration 0003's foreign key exists so a Run cannot name
    an unregistered input, and the fake asserts the *behaviour* under test here -- that
    facts citing two dataset versions are refused -- rather than restating the constraint.
    """
    factory = getattr(repository, "test_factory", None)
    if factory is not None:
        persistence_support.register_dataset(factory, dataset_version, facts.ONTOLOGY_HASH)


@pytest.fixture(params=["memory", "postgres"])
def repository(request: pytest.FixtureRequest) -> None:
    """Yield each implementation of the fact repository in turn."""
    builder = _in_memory if request.param == "memory" else _postgres
    repo, teardown = builder()
    yield repo
    if teardown is not None:
        for _ in teardown:  # drain, running the rollback in the generator's finally block
            pass


def _seed(repository: Any) -> dict[str, object]:
    citation = facts.evidence_record("row:1")
    repository.write_evidence_records([citation])
    first = facts.entity("P1", citation=citation)
    second = facts.entity("P2", citation=citation)
    repository.write_entities([second, first], facts.ONTOLOGY_HASH)
    early = facts.event("STAGE_ONE", facts.interval(0), citation=citation, participants=(first,))
    late = facts.event("STAGE_TWO", facts.interval(10), citation=citation, participants=(first,))
    repository.write_events([late, early], facts.ONTOLOGY_HASH)
    return {"citation": citation, "first": first, "second": second, "early": early, "late": late}


def test_entities_come_back_in_canonical_sequence(repository: Any) -> None:
    seeded = _seed(repository)
    read = list(repository.entities_for_dataset(facts.DATASET_VERSION))
    identifiers = [entity.entity_id for entity in read]
    assert identifiers == sorted(identifiers), (
        "Entities must be sequenced by entity_id (CONVENTIONS.md §11). They were written "
        "in the reverse order, so insertion order and canonical order disagree here on "
        "purpose -- an implementation that returned insertion order would pass a test "
        "that seeded them already sorted."
    )
    assert {entity.natural_key for entity in read} == {"P1", "P2"}
    assert seeded["first"].entity_id in identifiers


def test_events_come_back_in_canonical_time_sequence(repository: Any) -> None:
    seeded = _seed(repository)
    read = list(repository.events_for_dataset(facts.DATASET_VERSION))
    assert [event.event_id for event in read] == [
        seeded["early"].event_id,
        seeded["late"].event_id,
    ], (
        "Events must be sequenced by (t_earliest, t_latest, event_id). They were written "
        "later-first, so a repository returning insertion order fails here."
    )


def test_writing_the_same_fact_twice_stores_it_once(repository: Any) -> None:
    seeded = _seed(repository)
    rewritten = repository.write_entities([seeded["first"]], facts.ONTOLOGY_HASH)
    assert rewritten == 0, (
        "Content addressing means the same participant seen twice is one row. A second "
        "write is a no-op, not an error and not a duplicate (docs/architecture.md §2, "
        "module 3)."
    )
    assert len(list(repository.entities_for_dataset(facts.DATASET_VERSION))) == 2


def test_an_unevidenced_observed_entity_is_refused(repository: Any) -> None:
    citation = facts.evidence_record("row:1")
    repository.write_evidence_records([citation])
    unevidenced = facts.entity("P9", citation=citation).model_copy(
        update={"evidence_record_ids": ()}
    )
    with pytest.raises(LawViolationError, match="LAW-EVIDENCE"):
        repository.write_entities([unevidenced], facts.ONTOLOGY_HASH)


def test_a_causal_relationship_type_is_refused(repository: Any) -> None:
    seeded = _seed(repository)
    causal = facts.relationship(
        seeded["first"], seeded["second"], "BELONGS_TO", citation=seeded["citation"]
    ).model_copy(update={"relationship_type": "CAUSES"})
    with pytest.raises(LawViolationError, match="CAUSES"):
        repository.write_relationships([causal], facts.DATASET_VERSION)


def test_an_edge_with_no_run_is_refused(repository: Any) -> None:
    seeded = _seed(repository)
    edge = facts.causal_edge(seeded["early"], seeded["late"], "run:0000000000000000")
    unscoped = edge.model_copy(update={"run_id": ""})
    with pytest.raises(LawViolationError, match="run_id"):
        repository.write_causal_edges([unscoped])


def test_an_edge_with_no_evidence_is_refused(repository: Any) -> None:
    seeded = _seed(repository)
    edge = facts.causal_edge(seeded["early"], seeded["late"], "run:0000000000000000")
    with pytest.raises(LawViolationError, match="LAW-EVIDENCE"):
        repository.write_causal_edges([edge.model_copy(update={"evidence": ()})])


def test_facts_spanning_two_dataset_versions_are_refused(repository: Any) -> None:
    pin_dataset_version(repository, "dataset:a")
    pin_dataset_version(repository, "dataset:b")
    first = facts.evidence_record("row:1", "dataset:a")
    second = facts.evidence_record("row:2", "dataset:b")
    repository.write_evidence_records([first, second])
    subject = facts.entity("P1", citation=first).model_copy(
        update={"evidence_record_ids": (first.evidence_record_id, second.evidence_record_id)}
    )
    with pytest.raises(ContractViolationError, match="dataset versions"):
        repository.write_entities([subject], facts.ONTOLOGY_HASH)


def test_registering_a_run_twice_yields_one_identifier(repository: Any) -> None:
    key = RunKey(
        dataset_version=facts.DATASET_VERSION,
        ontology_hash=facts.ONTOLOGY_HASH,
        rule_pack_version="1.0.0",
        engine_version="0.1.0",
        seed=0,
    )
    first = repository.register_run(key)
    second = repository.register_run(key)
    assert first == second == key.address(), (
        "Two executions of one Run are one Run (ADR-0013). A second registration returns "
        "the same content-addressed identifier rather than minting a second row."
    )
    assert repository.run(first) is not None


def test_an_absent_run_reads_as_none_rather_than_raising(repository: Any) -> None:
    assert repository.run("run:ffffffffffffffff") is None, (
        "An absent run is not an error at this layer. The caller decides what it means -- "
        "a 404 at the API, a hard error in the rebuild -- and a repository that raised "
        "would take that decision away from both."
    )
