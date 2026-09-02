"""Bi-temporal storage: re-inference supersedes, it never rewrites (ADR-0032).

The property under test, in one sentence: **a re-derivation that changes what the engine
believes must leave what it used to believe readable.**

Why that matters here rather than being general good practice. A Run is re-derived whenever
the ontology, the rule pack, or the engine version changes (ADR-0013), and a re-derivation
can narrow a state's validity interval -- a better ontology places a transition more
precisely. With one time axis that correction OVERWRITES the interval a past conclusion was
computed against. The conclusion then cannot be reproduced (its inputs are gone), cannot be
audited (the audit record cites a state that now says something else), and cannot be
compared against the new one (there is nothing to compare). `docs/architecture.md` §4.4
promises all three, and prd.md §54's "no inferred result should overwrite observed facts"
fails silently rather than loudly.

These tests run against both the PostgreSQL adapter and the in-memory fake, because a fake
that quietly overwrote would make the fast suite green while the property was gone.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from causalog.core.errors import LawViolationError
from causalog.core.temporal import Precision, TimeInterval
from tests import persistence_support
from tests.fixtures import facts

#: The system-time instants these tests choose. They are CHOSEN, not observed: the
#: repository takes `believed_from` from the `Clock` port, so a test can place a belief at
#: a fixed instant and assert an as-of read against it. A suite that let the database
#: default `system_from` to `now()` could not assert anything about a past belief without
#: sleeping, and a test that sleeps is a test nobody runs (`CONVENTIONS.md` §11).
BELIEVED_FROM = datetime(2026, 6, 1, tzinfo=UTC)
RETRACTED_AT = datetime(2026, 7, 1, tzinfo=UTC)
LATER_STILL = datetime(2026, 8, 1, tzinfo=UTC)


def _memory() -> None:
    from causalog.persistence.memory import InMemoryFactRepository

    return InMemoryFactRepository(), None


def _postgres() -> None:
    from causalog.persistence.postgres.fact_repository import PostgresFactRepository

    generator = persistence_support.migrated_database()
    factory = next(generator)
    persistence_support.register_dataset(factory, facts.DATASET_VERSION, facts.ONTOLOGY_HASH)
    return PostgresFactRepository(factory), generator


@pytest.fixture(params=["memory", "postgres"])
def repository(request: pytest.FixtureRequest) -> None:
    """Yield each implementation in turn."""
    repo, teardown = (_memory if request.param == "memory" else _postgres)()
    yield repo
    if teardown is not None:
        for _ in teardown:
            pass


def _seed_one_state(repository: Any) -> None:
    """Store a single state and return it with its participant and origin event."""
    citation = facts.evidence_record("row:1")
    repository.write_evidence_records([citation])
    participant = facts.entity("P1", citation=citation)
    repository.write_entities([participant], facts.ONTOLOGY_HASH)
    origin = facts.event(
        "STAGE_ONE", facts.interval(0), citation=citation, participants=(participant,)
    )
    repository.write_events([origin], facts.ONTOLOGY_HASH)
    wide = facts.state(
        participant,
        "OPEN",
        facts.interval(0, span_days=30),
        derived_from=origin,
        citation=citation,
    )
    repository.write_states([wide], facts.DATASET_VERSION, BELIEVED_FROM)
    return participant, origin, citation, wide


def test_a_correction_supersedes_rather_than_rewrites(repository: Any) -> None:
    """The headline property: the narrowed belief is current, the old one is still there."""
    participant, origin, citation, wide = _seed_one_state(repository)

    # Re-inference narrows the validity interval: a better ontology placed the transition
    # more precisely. The state is CONTENT-ADDRESSED over its interval, so a narrowed
    # interval is a different state_id -- a different claim about when something held is a
    # different claim (docs/contracts.md §2).
    narrow_interval = TimeInterval(
        t_earliest=facts.EPOCH,
        t_latest=facts.EPOCH + timedelta(days=7),
        precision=Precision.DAY,
        provenance=facts.ProvenanceClass.OBSERVED,
        source="re-inference",
    )
    narrow = facts.state(
        participant, "OPEN", narrow_interval, derived_from=origin, citation=citation
    )

    repository.retract_states([wide.state_id], RETRACTED_AT)
    repository.write_states([narrow], facts.DATASET_VERSION, RETRACTED_AT)

    current = list(repository.states_for_dataset(facts.DATASET_VERSION))
    assert [state.state_id for state in current] == [narrow.state_id], (
        "The ordinary read returns what the engine believes NOW: the narrowed state, and "
        "only it. A superseded belief that leaked into this read would silently double "
        "every downstream count."
    )

    earlier = list(repository.states_as_believed_at(facts.DATASET_VERSION, BELIEVED_FROM))
    assert wide.state_id in {state.state_id for state in earlier}, (
        "The as-of read must still return the WIDE interval. This is the whole point: a "
        "conclusion computed in June against a thirty-day validity can still be "
        "reproduced in August, when the engine believes seven days (ADR-0032)."
    )
    assert narrow.state_id not in {state.state_id for state in earlier}, (
        "The as-of read must NOT return a belief the engine had not yet formed. Returning "
        "it would make a past conclusion reproducible against inputs it never saw, which "
        "is the opposite of an audit."
    )


def test_the_valid_interval_and_the_system_interval_are_independent(repository: Any) -> None:
    """Two axes, and moving one must not move the other.

    Valid time says when the world was in a condition. System time says when this system
    believed it. Collapsing them -- the single-timestamp design -- is what makes a
    correction indistinguishable from a fact that changed.
    """
    participant, origin, citation, wide = _seed_one_state(repository)
    repository.retract_states([wide.state_id], RETRACTED_AT)

    as_believed = list(repository.states_as_believed_at(facts.DATASET_VERSION, BELIEVED_FROM))
    recovered = next(state for state in as_believed if state.state_id == wide.state_id)
    assert recovered.held_over == wide.held_over, (
        "Retracting a belief changed its VALID interval. The two axes are independent: "
        "when the world was in a condition is not affected by when we stopped believing "
        "it was (ADR-0032)."
    )


def test_a_retraction_at_the_closing_instant_is_not_returned(repository: Any) -> None:
    """The half-open upper bound, asserted because the off-by-one here is invisible.

    The as-of predicate is `system_from <= t < system_to`. A belief closed at exactly `t`
    is NOT returned by a query as of `t`. Were it inclusive, the moment of retraction would
    return two beliefs for one state, and `core.derivation.current_state` raises on two --
    it treats simultaneous states as a contradiction in the source rather than resolving
    one by arbitrary choice.
    """
    participant, origin, citation, wide = _seed_one_state(repository)
    repository.retract_states([wide.state_id], RETRACTED_AT)

    at_the_instant = list(repository.states_as_believed_at(facts.DATASET_VERSION, RETRACTED_AT))
    assert wide.state_id not in {state.state_id for state in at_the_instant}

    just_before = list(
        repository.states_as_believed_at(
            facts.DATASET_VERSION, RETRACTED_AT - timedelta(microseconds=1)
        )
    )
    assert wide.state_id in {state.state_id for state in just_before}


def test_closing_a_period_before_it_began_is_refused(repository: Any) -> None:
    """A belief cannot end before it started."""
    participant, origin, citation, wide = _seed_one_state(repository)
    with pytest.raises(LawViolationError, match="before it began"):
        repository.retract_states([wide.state_id], datetime(2020, 1, 1, tzinfo=UTC))


def test_retracting_twice_is_idempotent_and_does_not_reopen(repository: Any) -> None:
    """A second retraction closes nothing and never reopens what the first closed."""
    participant, origin, citation, wide = _seed_one_state(repository)
    assert repository.retract_states([wide.state_id], RETRACTED_AT) == 1
    assert repository.retract_states([wide.state_id], LATER_STILL) == 0, (
        "The second retraction must touch nothing. Closing an already-closed period "
        "would rewrite when the engine is recorded as having stopped believing something."
    )
    still_closed = list(repository.states_as_believed_at(facts.DATASET_VERSION, LATER_STILL))
    assert wide.state_id not in {state.state_id for state in still_closed}


def test_reopening_a_closed_period_is_refused_by_the_database() -> None:
    """The database refuses a direct reopen, not only the repository (ADR-0032).

    Separate from the parameterized tests above because it bypasses the repository
    entirely: the guard has to hold against a `psql` session, which is the case the
    application-level check cannot cover.
    """
    import psycopg

    generator = persistence_support.migrated_database()
    factory = next(generator)
    try:
        persistence_support.register_dataset(factory, facts.DATASET_VERSION, facts.ONTOLOGY_HASH)
        from causalog.persistence.postgres.fact_repository import PostgresFactRepository

        repository = PostgresFactRepository(factory)
        participant, origin, citation, wide = _seed_one_state(repository)

        # A second state, left OPEN. The content-change and DELETE probes below need a row
        # whose system period is still open: on a closed row the "already closed" branch
        # fires first, and the test would then pass while saying nothing about the guard it
        # names.
        still_open = facts.state(
            participant,
            "CLOSED",
            facts.interval(31, span_days=5),
            derived_from=origin,
            citation=citation,
        )
        repository.write_states([still_open], facts.DATASET_VERSION, BELIEVED_FROM)
        repository.retract_states([wide.state_id], RETRACTED_AT)

        with factory.connect() as connection, connection.cursor() as cursor:
            with pytest.raises(psycopg.errors.RestrictViolation, match="already closed"):
                cursor.execute(
                    "UPDATE state SET system_to = 'infinity' WHERE state_id = %s",
                    (wide.state_id,),
                )
            connection.rollback()

            # Two distinct refusals, asserted separately because they are two distinct
            # ways to rewrite history and the trigger checks them in a fixed sequence.
            #
            # (a) An edit that leaves the period OPEN. This is the in-place mutation --
            #     the row keeps being current and now says something else.
            with pytest.raises(psycopg.errors.RestrictViolation, match="in place"):
                cursor.execute("UPDATE state SET state_name = 'OPEN' WHERE system_to = 'infinity'")
            connection.rollback()

            # (b) An edit that DOES close the period, and changes content in the same
            #     statement. This is the subtle one: it looks like a legitimate retraction
            #     and would smuggle a content change through with it. The whole-row jsonb
            #     comparison is what catches it, and it is why that comparison exists.
            with pytest.raises(psycopg.errors.RestrictViolation, match="row content"):
                cursor.execute(
                    "UPDATE state SET state_name = 'OPEN', system_to = %s "
                    "WHERE system_to = 'infinity'",
                    (LATER_STILL,),
                )
            connection.rollback()

            with pytest.raises(psycopg.errors.RestrictViolation, match="RETRACTED"):
                cursor.execute("DELETE FROM state")
            connection.rollback()
    finally:
        for _ in generator:
            pass
