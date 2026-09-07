"""The LAW-TIME gate, property-based over arbitrary interval pairs.

Property-based rather than example-based because the gate's contract is a statement about
*every* pair of intervals, and an example suite proves it for the pairs somebody thought
of. ADR-0024 adopted hypothesis for exactly this; `tests/conftest.py` derandomizes it so a
failure reproduces from the test name.

Three outcomes are asserted, and the third is the one most easily lost:
`temporally_unverifiable` is a distinct state from `UNDETERMINED`, and neither is the same
as rejection.
"""

from __future__ import annotations

import pytest
from hypothesis import given

from causalog.causal_engine.candidate_cause_generator import (
    Proposal,
    RejectionReason,
    gate,
    gate_all,
)
from causalog.core.errors import ContractViolationError
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import (
    TemporalVerdict,
    TimeInterval,
    is_unverifiable,
    verdict,
)
from causalog.core.types import CandidateEdge, DirectCause, EvidenceItem, EvidenceKind
from fixtures.candidates import RUN_ID
from fixtures.facts import entity, event, evidence_record, interval
from tests.unit.core.strategies import intervals

CITATION = evidence_record("row-gate")
PARTICIPANT = entity("GATE", citation=CITATION)

EVIDENCE = (
    EvidenceItem(
        evidence_item_id="evi:fixture00000000",
        kind=EvidenceKind.TEMPORAL_PROXIMITY,
        description="fixture justification",
        supporting_ids=("a",),
        strength=0.5,
        verification="fixture verification",
        provenance_class=ProvenanceClass.ASSUMED,
    ),
)


def _proposal(cause_interval: TimeInterval, effect_interval: TimeInterval) -> Proposal:
    """Return a proposal over two events placed at the given intervals."""
    cause = event("STAGE_ONE", cause_interval, citation=CITATION, participants=(PARTICIPANT,))
    effect = event("STAGE_TWO", effect_interval, citation=CITATION, participants=(PARTICIPANT,))
    return Proposal(
        generator_id="fixture",
        cause_event=cause,
        effect_event=effect,
        payload=DirectCause(),
        evidence=EVIDENCE,
    )


@given(cause=intervals(), effect=intervals())
def test_a_violation_is_never_constructed(cause: TimeInterval, effect: TimeInterval) -> None:
    """LAW-TIME. The one thing this module may never produce, over arbitrary intervals."""
    outcome = gate(_proposal(cause, effect), RUN_ID)
    expected = verdict(cause, effect)
    if expected is TemporalVerdict.VIOLATION:
        assert outcome.candidate is None
        assert outcome.reason is RejectionReason.TEMPORAL_VIOLATION
    else:
        assert outcome.candidate is not None
        assert outcome.candidate.temporal_verdict is not TemporalVerdict.VIOLATION


@given(cause=intervals(), effect=intervals())
def test_an_undetermined_pair_is_retained_and_never_promotable(
    cause: TimeInterval, effect: TimeInterval
) -> None:
    """`CONTEXT.md` R-14: retained, flagged, blocked. Never dropped to tidy the graph."""
    outcome = gate(_proposal(cause, effect), RUN_ID)
    if verdict(cause, effect) is not TemporalVerdict.UNDETERMINED:
        return
    assert outcome.candidate is not None, "an UNDETERMINED pair must be RETAINED"
    assert outcome.candidate.admits_promotion is False


@given(cause=intervals(), effect=intervals())
def test_unverifiable_is_a_third_state_distinct_from_undetermined(
    cause: TimeInterval, effect: TimeInterval
) -> None:
    """`docs/contracts.md` §3: never placed, versus placed and inseparable.

    The flag tracks `is_unverifiable` on either interval, exactly and only. A candidate can
    be `UNDETERMINED` without being unverifiable -- two overlapping placed intervals -- and
    the two counts must never be summed.
    """
    outcome = gate(_proposal(cause, effect), RUN_ID)
    if outcome.candidate is None:
        return
    assert outcome.candidate.temporally_unverifiable == (
        is_unverifiable(cause) or is_unverifiable(effect)
    )


@given(cause=intervals(), effect=intervals())
def test_the_gate_never_assigns_inferred_provenance(
    cause: TimeInterval, effect: TimeInterval
) -> None:
    """Promotion is a judgement, and judgement is module 10's.

    Even a `CERTAIN` verdict over two placed, observed intervals produces `ASSUMED` or
    `STATISTICAL`. A module that promoted its own output would have made the decision it
    exists not to make.
    """
    outcome = gate(_proposal(cause, effect), RUN_ID)
    if outcome.candidate is None:
        return
    assert outcome.candidate.provenance_class is not ProvenanceClass.INFERRED
    assert outcome.candidate.provenance_class is not ProvenanceClass.OBSERVED


def test_a_self_pair_is_refused_before_it_reaches_the_gate() -> None:
    """`Proposal` refuses it at construction, so the gate never sees one."""
    single = event("STAGE_ONE", interval(0), citation=CITATION, participants=(PARTICIPANT,))
    with pytest.raises(ContractViolationError, match="its own cause"):
        Proposal(
            generator_id="fixture",
            cause_event=single,
            effect_event=single,
            payload=DirectCause(),
            evidence=EVIDENCE,
        )


def test_a_constraint_prohibition_is_a_counted_rejection_not_a_silent_filter() -> None:
    """ADR-0044: every suppression is reported. Carried one layer forward."""
    cause = event("STAGE_ONE", interval(0), citation=CITATION, participants=(PARTICIPANT,))
    effect = event("STAGE_TWO", interval(2), citation=CITATION, participants=(PARTICIPANT,))
    proposal = Proposal(
        generator_id="fixture",
        cause_event=cause,
        effect_event=effect,
        payload=DirectCause(),
        evidence=EVIDENCE,
    )
    (outcome,) = gate_all((proposal,), RUN_ID, frozenset({(cause.event_id, effect.event_id)}))
    assert outcome.candidate is None
    assert outcome.reason is RejectionReason.CONSTRAINT_SUPPRESSED


def test_candidate_edge_refuses_a_violation_on_the_deserialization_path_too() -> None:
    """A rejected pair must not be reintroducible by writing it out and reading it back."""
    with pytest.raises(Exception, match="VIOLATION"):
        CandidateEdge.model_validate(
            {
                "candidate_edge_id": "edg:0000000000000000",
                "generator_id": "fixture",
                "source_event_id": "evt:a",
                "target_event_id": "evt:b",
                "payload": {"edge_kind": "DIRECT"},
                "evidence": [EVIDENCE[0].model_dump()],
                "provenance_class": "ASSUMED",
                "temporal_verdict": "VIOLATION",
                "temporally_unverifiable": False,
                "run_id": RUN_ID,
            }
        )


def test_candidate_edge_refuses_inferred_over_an_unverifiable_pair() -> None:
    """An inference standing on absent time is an inference standing on nothing."""
    with pytest.raises(Exception, match="INFERRED"):
        CandidateEdge.model_validate(
            {
                "candidate_edge_id": "edg:0000000000000000",
                "generator_id": "fixture",
                "source_event_id": "evt:a",
                "target_event_id": "evt:b",
                "payload": {"edge_kind": "DIRECT"},
                "evidence": [EVIDENCE[0].model_dump()],
                "provenance_class": "INFERRED",
                "temporal_verdict": "CERTAIN",
                "temporally_unverifiable": True,
                "run_id": RUN_ID,
            }
        )
