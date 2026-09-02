"""LAW-TIME is enforced in code, not by convention (CONVENTIONS.md §1, ADR-0007).

The law says no causal edge may exist where the cause does not precede the effect. "May not
exist" is stronger than "should not be created": these tests assert that a temporally
invalid edge cannot be produced by any path, including deserialization of stored data,
because an edge that can be written to disk and read back is an edge that exists.

The escape hatch is deliberately narrow. An absent timestamp yields
`temporally_unverifiable`, which is a distinct recorded state -- retained, visible, and
barred from promotion. It is never a silent pass.
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


def _interval(
    first_hour: int,
    last_hour: int,
    precision: Precision = Precision.HOUR,
    provenance: ProvenanceClass = ProvenanceClass.OBSERVED,
) -> TimeInterval:
    return TimeInterval(
        t_earliest=datetime(2026, 1, 1, first_hour, tzinfo=UTC),
        t_latest=datetime(2026, 1, 1, last_hour, tzinfo=UTC),
        precision=precision,
        provenance=provenance,
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


def _edge(
    cause: Event,
    effect: Event,
    provenance: ProvenanceClass = ProvenanceClass.STATISTICAL,
) -> CausalEdge:
    return CausalEdge.between(
        source_event=cause,
        target_event=effect,
        payload=DirectCause(),
        confidence=CONFIDENCE,
        evidence=EVIDENCE,
        propagation_weight=0.5,
        provenance_class=provenance,
        run_id="run:0000000000000000",
    )


EARLY = _event("evt:early", _interval(1, 2))
LATE = _event("evt:late", _interval(3, 4))
OVERLAPPING = _event("evt:overlapping", _interval(2, 5))
UNPLACED = _event("evt:unplaced", UNKNOWN_INTERVAL)


# ---------------------------------------------------------------------------------------
# a temporally invalid edge cannot be constructed
# ---------------------------------------------------------------------------------------


def test_constructing_a_backwards_edge_raises() -> None:
    """The headline guarantee: the effect cannot precede its own cause."""
    with pytest.raises(LawViolationError):
        _edge(LATE, EARLY)


def test_the_error_names_the_law_and_both_events() -> None:
    """The message must be actionable and must not quote a raw record.

    `CONVENTIONS.md` §7: an error must name the offending identifier and the contract
    violated, and must not quote a raw source record.
    """
    with pytest.raises(LawViolationError) as raised:
        _edge(LATE, EARLY)
    message = str(raised.value)
    assert "LAW-TIME" in message
    assert LATE.event_id in message
    assert EARLY.event_id in message


def test_a_violation_cannot_be_reintroduced_by_deserialization() -> None:
    """The gap a construction-time-only check would leave.

    If the invariant lived solely in `between`, a rejected edge could be written to disk
    with the verdict rewritten and read straight back into the graph.
    """
    stored = to_canonical_json(_edge(EARLY, LATE))
    tampered = stored.replace('"CERTAIN"', '"VIOLATION"')
    assert tampered != stored
    with pytest.raises(LawViolationError):
        from_canonical_json(CausalEdge, tampered)


def test_an_event_cannot_cause_itself() -> None:
    """A self-edge is degenerate and would make every propagation walk non-terminating."""
    with pytest.raises(Exception, match="does not cause itself"):
        _edge(EARLY, EARLY)


# ---------------------------------------------------------------------------------------
# ambiguity is retained, not resolved
# ---------------------------------------------------------------------------------------


def test_overlapping_intervals_produce_a_retained_undetermined_edge() -> None:
    """Ambiguity is retained rather than resolved.

    ADR-0007 retains ambiguity rather than guessing, so the thinness of the graph is a
    reported finding about the dataset rather than a silent loss (risk R-14).
    """
    edge = _edge(EARLY, OVERLAPPING)
    assert edge.temporal_verdict is TemporalVerdict.UNDETERMINED
    assert not edge.temporally_unverifiable


def test_an_undetermined_edge_may_never_be_promoted_to_inferred() -> None:
    """Retained is not the same as admissible: promotion needs CERTAIN."""
    with pytest.raises(LawViolationError):
        _edge(EARLY, OVERLAPPING, ProvenanceClass.INFERRED)


# ---------------------------------------------------------------------------------------
# absent time is a distinct state, never a silent pass
# ---------------------------------------------------------------------------------------


def test_an_absent_timestamp_is_flagged_rather_than_rejected_or_ignored() -> None:
    """The only escape hatch, and it is explicit on the artifact."""
    edge = _edge(EARLY, UNPLACED)
    assert edge.temporally_unverifiable
    assert edge.temporal_verdict is TemporalVerdict.UNDETERMINED


def test_unverifiable_is_distinguishable_from_merely_undetermined() -> None:
    """The flag and the verdict answer different questions.

    The reason the flag exists beside the verdict: "the data could not separate these
    two" and "the data never placed one of them" are different findings, and collapsing
    them hides which one the run actually hit.
    """
    overlapping_edge = _edge(EARLY, OVERLAPPING)
    unplaced_edge = _edge(EARLY, UNPLACED)
    assert overlapping_edge.temporal_verdict == unplaced_edge.temporal_verdict
    assert overlapping_edge.temporally_unverifiable != unplaced_edge.temporally_unverifiable


def test_an_unverifiable_edge_may_never_be_promoted_to_inferred() -> None:
    """An absent instant blocks promotion.

    `CONVENTIONS.md` §10: an UNKNOWN-precision event may sit on a timeline but may
    never participate in an INFERRED causal edge.
    """
    with pytest.raises(LawViolationError):
        _edge(EARLY, UNPLACED, ProvenanceClass.INFERRED)


def test_there_is_no_argument_that_bypasses_the_check() -> None:
    """The law has no opt-out parameter.

    A skip flag on the sanctioned constructor would make the law optional. The verdict
    and the flag are computed, never accepted from the caller -- a caller who could pass
    `temporal_verdict=CERTAIN` could launder a rejected edge into the graph.
    """
    parameters = set(CausalEdge.between.__annotations__)
    assert "temporal_verdict" not in parameters
    assert "temporally_unverifiable" not in parameters
    assert not any("skip" in name or "force" in name for name in parameters)


# ---------------------------------------------------------------------------------------
# the admissible case still works
# ---------------------------------------------------------------------------------------


def test_a_strictly_preceding_pair_is_admissible_and_promotable() -> None:
    """The law must not be satisfied by refusing everything."""
    edge = _edge(EARLY, LATE, ProvenanceClass.INFERRED)
    assert edge.temporal_verdict is TemporalVerdict.CERTAIN
    assert not edge.temporally_unverifiable
