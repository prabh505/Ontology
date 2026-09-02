"""`CONVENTIONS.md` §10: extraction may widen or offset an instant, and never invent one.

`test_cleaning_never_imputes_time.py` enumerates the mapping's transform registry. This
enumerates the OTHER place an instant is built -- the emission policies of module 4 -- and
asserts the same property over real output: no emitted interval is EXACT, no UNKNOWN
interval is narrowed, every interval names its derivation, and a derived bound is INFERRED
rather than ASSUMED so that a computed window stays distinguishable from a typed one.
"""

from __future__ import annotations

import pytest

from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import (
    UNKNOWN_EARLIEST,
    UNKNOWN_LATEST,
    Precision,
    TemporalVerdict,
    verdict,
)
from causalog.ingestion.schema_mapper.dsl import OccurredAtPolicy
from extraction_harness import Expansion, expand
from fixtures.dataco.expansion import GROUND_TRUTH_DATASET_VERSION, rows

pytestmark = pytest.mark.law


@pytest.fixture(scope="module")
def generated() -> Expansion:
    return expand(rows(), GROUND_TRUTH_DATASET_VERSION)


def test_the_scan_covers_something(generated: Expansion) -> None:
    generation = generated.generation
    assert generation.events, "no event was produced, which reads identically to passing"


def test_no_emitted_interval_claims_exact_precision(generated: Expansion) -> None:
    """A parsed source instant is never exact, and neither is one derived from two."""
    generation = generated.generation
    assert not [
        event for event in generation.events if event.occurred_at.precision is Precision.EXACT
    ]


def test_an_unknown_interval_is_never_narrowed(generated: Expansion) -> None:
    """Narrowing an absent instant to a guessed window is imputation (ADR-0021)."""
    generation = generated.generation
    for event in generation.events:
        if event.occurred_at.precision is not Precision.UNKNOWN:
            continue
        assert (event.occurred_at.t_earliest, event.occurred_at.t_latest) == (
            UNKNOWN_EARLIEST,
            UNKNOWN_LATEST,
        )
        assert event.occurred_at.provenance is ProvenanceClass.ASSUMED


def test_every_interval_names_the_derivation_that_produced_its_bounds(generated: Expansion) -> None:
    generation = generated.generation
    for event in generation.events:
        assert event.occurred_at.source.strip()


def test_a_derived_bound_is_inferred_and_never_assumed(generated: Expansion) -> None:
    """`ASSUMED` is a value somebody typed; `INFERRED` is a bound computed from evidence.

    Conflating them makes a re-derivable window indistinguishable from a chosen one.
    """
    generation = generated.generation
    derived = [
        event
        for event in generation.events
        if dict(event.metadata).get("occurred_at_policy")
        in (OccurredAtPolicy.BOUNDED_BETWEEN.value, OccurredAtPolicy.OFFSET_FROM.value)
        and event.occurred_at.precision is not Precision.UNKNOWN
    ]
    assert derived, "no derived interval was produced, so this proved nothing"
    for event in derived:
        assert event.occurred_at.provenance is ProvenanceClass.INFERRED


def test_an_inferred_interval_can_never_certify_a_precedence(generated: Expansion) -> None:
    """The guard that makes a narrowed window safe to produce freely (ADR-0021).

    Called through `core.temporal.verdict` -- the engine's own LAW-TIME function -- rather
    than reimplemented, so the answer is exactly the one module 9 will get.
    """
    generation = generated.generation
    inferred = [
        event
        for event in generation.events
        if event.occurred_at.provenance is ProvenanceClass.INFERRED
        and event.occurred_at.precision is not Precision.UNKNOWN
    ]
    observed = [
        event
        for event in generation.events
        if event.occurred_at.provenance is ProvenanceClass.ASSUMED
        and event.occurred_at.precision is Precision.MINUTE
    ]
    assert inferred and observed
    for cause in observed:
        for effect in inferred:
            assert verdict(cause.occurred_at, effect.occurred_at) is not TemporalVerdict.CERTAIN


def test_an_unplaced_event_yields_undetermined_against_everything(generated: Expansion) -> None:
    """An event with no instant may sit on a timeline and may never carry an INFERRED edge."""
    generation = generated.generation
    unplaced = next(
        event for event in generation.events if event.occurred_at.precision is Precision.UNKNOWN
    )
    placed = next(
        event for event in generation.events if event.occurred_at.precision is Precision.MINUTE
    )
    assert verdict(unplaced.occurred_at, placed.occurred_at) is TemporalVerdict.UNDETERMINED
    assert verdict(placed.occurred_at, unplaced.occurred_at) is TemporalVerdict.UNDETERMINED
