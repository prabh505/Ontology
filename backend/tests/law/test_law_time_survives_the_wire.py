"""What deserialization can and cannot re-check about LAW-TIME (DEF-0002).

`test_law_time_is_enforced_at_construction.py` asserts that a `VIOLATION` cannot be
reintroduced by replaying stored data. That is true, and it is narrower than the guarantee
`CausalEdge`'s own docstring and `docs/contracts.md` §6 used to claim.

The boundary, stated exactly:

  * A stored `VIOLATION` verdict is refused. The verdict is a field, the field has a banned
    value, and the validator sees it. This is re-checkable.
  * A stored `UNDETERMINED` verdict rewritten to `CERTAIN` is **accepted**, and the edge may
    then carry `INFERRED`. This is NOT re-checkable, because a `CausalEdge` stores
    `source_event_id` and `target_event_id` -- identifiers, not intervals. Nothing inside
    the artifact can recompute `verdict(cause.occurred_at, effect.occurred_at)`, so the
    validator has no way to know the stored verdict is a lie.

The same hole is reachable without any serialization at all: `CausalEdge(...)` called
directly takes `temporal_verdict` as an argument. `CausalEdge.between` is the *sanctioned*
constructor, not the *only* one -- pydantic cannot distinguish a direct call from the
`model_validate` that deserialization requires.

These tests pin the real boundary so that it is a known, measured limit rather than an
assumed guarantee. They are written to FAIL if the hole is ever closed, which is the point:
closing it changes the address recipe or the stored fields, and either is an ADR and an
`engine_version` bump (`docs/contracts.md` §8), not an edit.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from causalog.core.aggregation import aggregate
from causalog.core.errors import LawViolationError
from causalog.core.provenance import ProvenanceClass
from causalog.core.serialization import from_canonical_json, to_canonical_json
from causalog.core.temporal import (
    UNKNOWN_EARLIEST,
    UNKNOWN_LATEST,
    Precision,
    TemporalVerdict,
    TimeInterval,
)
from causalog.core.types import (
    CausalEdge,
    ConfidenceComponent,
    DirectCause,
    Event,
    EvidenceItem,
    EvidenceKind,
)

pytestmark = pytest.mark.law


def _interval(first_hour: int, last_hour: int) -> TimeInterval:
    return TimeInterval(
        t_earliest=datetime(2026, 1, 1, first_hour, tzinfo=UTC),
        t_latest=datetime(2026, 1, 1, last_hour, tzinfo=UTC),
        precision=Precision.HOUR,
        provenance=ProvenanceClass.OBSERVED,
        source="test-fixture",
    )


UNKNOWN_INTERVAL = TimeInterval(
    t_earliest=UNKNOWN_EARLIEST,
    t_latest=UNKNOWN_LATEST,
    precision=Precision.UNKNOWN,
    provenance=ProvenanceClass.ASSUMED,
    source="not recorded by the source",
)

CONFIDENCE = aggregate(
    [
        ConfidenceComponent(
            component_name="rule_support",
            value=0.9,
            provenance_class=ProvenanceClass.ASSUMED,
            evidence_record_ids=("evd:1",),
        )
    ]
)

EVIDENCE = (
    EvidenceItem(
        evidence_item_id="evi:1",
        kind=EvidenceKind.RULE,
        description="a rule fired",
        supporting_ids=("evd:1",),
        strength=0.9,
        verification="rule://R-0001",
        provenance_class=ProvenanceClass.ASSUMED,
    ),
)


def _event(event_id: str, interval: TimeInterval) -> Event:
    return Event(
        event_id=event_id,
        event_type="SYNTHETIC",
        occurred_at=interval,
        trigger=None,
        source_entity_ids=(),
        target_entity_ids=(),
        changed_attributes=(),
        metadata=(),
        provenance_class=ProvenanceClass.OBSERVED,
        confidence=CONFIDENCE,
        is_actionable=False,
        source_record_ref="evd:1",
        evidence_record_ids=("evd:1",),
    )


# A cause interval that starts before the effect's interval ends, so the pair escapes the
# `cause.t_earliest >= effect.t_latest` VIOLATION test -- but overlaps, so it is not
# precedence either. This is the pair the audit probe used.
REVERSED_CAUSE = _event("evt:cause", _interval(3, 6))
REVERSED_EFFECT = _event("evt:effect", _interval(1, 4))
UNPLACED_EFFECT = _event("evt:unplaced", UNKNOWN_INTERVAL)


def _edge(cause: Event, effect: Event) -> CausalEdge:
    return CausalEdge.between(
        source_event=cause,
        target_event=effect,
        payload=DirectCause(),
        confidence=CONFIDENCE,
        evidence=EVIDENCE,
        propagation_weight=0.5,
        provenance_class=ProvenanceClass.STATISTICAL,
        run_id="run:0000000000000000",
    )


# ---------------------------------------------------------------------------------------
# what deserialization DOES re-check
# ---------------------------------------------------------------------------------------


def test_a_stored_violation_verdict_is_still_refused() -> None:
    """The re-checkable half, restated here so the boundary has both sides in one file."""
    stored = to_canonical_json(_edge(REVERSED_CAUSE, REVERSED_EFFECT))
    with pytest.raises(LawViolationError):
        from_canonical_json(CausalEdge, stored.replace('"UNDETERMINED"', '"VIOLATION"'))


def test_a_stored_observed_provenance_is_still_refused() -> None:
    """LAW-PROVENANCE's half of the same guard survives the wire."""
    stored = to_canonical_json(_edge(REVERSED_CAUSE, REVERSED_EFFECT))
    with pytest.raises(LawViolationError):
        from_canonical_json(CausalEdge, stored.replace('"STATISTICAL"', '"OBSERVED"'))


# ---------------------------------------------------------------------------------------
# what deserialization CANNOT re-check -- DEF-0002
# ---------------------------------------------------------------------------------------


def test_an_undetermined_verdict_rewritten_to_certain_is_accepted() -> None:
    """DEF-0002. The edge carries event *ids*, so the verdict cannot be recomputed.

    A temporally undetermined edge, written to disk with its verdict rewritten, reads back
    as an admissible `CERTAIN` edge and may then be promoted to `INFERRED`. No exception is
    raised anywhere on the path.
    """
    edge = _edge(REVERSED_CAUSE, REVERSED_EFFECT)
    assert edge.temporal_verdict is TemporalVerdict.UNDETERMINED

    laundered = from_canonical_json(
        CausalEdge,
        to_canonical_json(edge)
        .replace('"UNDETERMINED"', '"CERTAIN"')
        .replace('"STATISTICAL"', '"INFERRED"'),
    )
    assert laundered.temporal_verdict is TemporalVerdict.CERTAIN
    assert laundered.provenance_class is ProvenanceClass.INFERRED


def test_the_unverifiable_flag_can_be_cleared_on_the_wire() -> None:
    """DEF-0002. `temporally_unverifiable` is stored, not derived from stored data.

    The flag records a property of the *events'* intervals, and the edge does not carry
    those intervals. Clearing it is therefore invisible to the validator.
    """
    edge = _edge(REVERSED_CAUSE, UNPLACED_EFFECT)
    assert edge.temporally_unverifiable

    laundered = from_canonical_json(
        CausalEdge,
        to_canonical_json(edge)
        .replace('"UNDETERMINED"', '"CERTAIN"')
        .replace("true", "false")
        .replace('"STATISTICAL"', '"INFERRED"'),
    )
    assert not laundered.temporally_unverifiable
    assert laundered.provenance_class is ProvenanceClass.INFERRED


def test_direct_construction_never_evaluates_law_time() -> None:
    """DEF-0002, without any serialization involved -- the likelier way to hit it.

    `between` is the sanctioned constructor because it is the only one that sees both
    intervals. Nothing requires a caller to use it: the class is a plain pydantic model and
    `model_validate` needs the same unguarded path that a direct call takes.
    """
    edge = CausalEdge(
        causal_edge_id=CausalEdge.address("evt:cause", "evt:effect", DirectCause().edge_kind),
        source_event_id="evt:cause",
        target_event_id="evt:effect",
        payload=DirectCause(),
        confidence=CONFIDENCE,
        evidence=EVIDENCE,
        propagation_weight=0.5,
        provenance_class=ProvenanceClass.INFERRED,
        temporal_verdict=TemporalVerdict.CERTAIN,
        temporally_unverifiable=False,
        run_id="run:0000000000000000",
    )
    # The two events whose ids this edge names in fact overlap; no interval was consulted.
    assert edge.temporal_verdict is TemporalVerdict.CERTAIN
    assert edge.provenance_class is ProvenanceClass.INFERRED


def test_the_stored_identifier_is_not_re_derived() -> None:
    """DEF-0002's companion: `Run` re-derives its own id on construction; `CausalEdge` does not.

    `docs/contracts.md` §5 states the `Run` behaviour explicitly. The asymmetry is not
    stated anywhere, so a reader may reasonably assume both types self-check.
    """
    edge = CausalEdge(
        causal_edge_id="edg:0000000000000000",  # not the address of this pair
        source_event_id="evt:cause",
        target_event_id="evt:effect",
        payload=DirectCause(),
        confidence=CONFIDENCE,
        evidence=EVIDENCE,
        propagation_weight=0.5,
        provenance_class=ProvenanceClass.STATISTICAL,
        temporal_verdict=TemporalVerdict.UNDETERMINED,
        temporally_unverifiable=False,
        run_id="run:0000000000000000",
    )
    assert edge.causal_edge_id != CausalEdge.address(
        "evt:cause", "evt:effect", DirectCause().edge_kind
    )
