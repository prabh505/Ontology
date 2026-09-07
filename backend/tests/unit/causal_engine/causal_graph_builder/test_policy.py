"""The promotion decision: every condition, and every reason it can refuse.

One test per stated failure mode (`CONVENTIONS.md` §3). The decisions here are the module's
whole reason to exist, so each demotion reason gets its own assertion rather than being
covered incidentally by an end-to-end run.
"""

from __future__ import annotations

import pytest

from causalog.causal_engine.causal_graph_builder import (
    DemotionReason,
    PromotedEdge,
    PropagationWeight,
    TypingBasis,
    TypingRecord,
    WeightBasis,
    decide,
    promote,
)
from causalog.core.errors import LawViolationError
from causalog.core.provenance import ProvenanceClass
from causalog.rule_engine import ConfidenceBandSpec
from fixtures.candidates import linear_process, unknown_time_event
from fixtures.facts import entity, event, evidence_record, interval, timeline
from fixtures.graphs import (
    build_context,
    candidate,
    graph_parameters,
    permissive_scoring,
    scored_graph,
)


def _one_claim(strong_floor: float = 0.0) -> tuple:
    """Return one scored claim between two cleanly ordered events, with its context."""
    _, events, timeline = linear_process("STAGE_ONE", "STAGE_TWO", subject="A")
    candidates = (candidate(events[0], events[1]),)
    bands = permissive_scoring(strong_floor)
    graph = scored_graph(candidates, events, (timeline,), bands)
    context = build_context(events, (timeline,), candidates, bands=bands)
    return graph.edges[0], context


def test_a_clean_claim_is_promoted() -> None:
    """Ordered events, a declared threshold it clears, and nothing else in the way."""
    scored, context = _one_claim()
    verdict = decide(scored, context.parameters, context.bands, context.events_by_id())
    assert verdict.promotes
    assert verdict.threshold_band == "STRONG"


def test_a_kind_with_no_declared_threshold_is_never_promoted() -> None:
    """A statement about the pack, and it must not read as a finding against the claim."""
    scored, context = _one_claim()
    parameters = graph_parameters(kinds=("CONDITIONAL",))
    verdict = decide(scored, parameters, context.bands, context.events_by_id())
    assert verdict.reason is DemotionReason.NO_THRESHOLD_DECLARED
    assert "about the pack rather than about this claim" in verdict.detail


def test_a_claim_below_its_kinds_floor_is_demoted_on_the_threshold() -> None:
    """The commonest honest rejection, and it names both numbers."""
    scored, context = _one_claim(strong_floor=0.99)
    verdict = decide(scored, context.parameters, context.bands, context.events_by_id())
    assert verdict.reason is DemotionReason.BELOW_KIND_THRESHOLD
    assert "0.990000" in verdict.detail


def test_insufficient_evidence_is_not_a_low_score() -> None:
    """The outcome is checked before the band, so the reason is never mistaken for one."""
    _, events, timeline = linear_process("STAGE_ONE", "STAGE_TWO", subject="A")
    candidates = (candidate(events[0], events[1]),)
    bands = permissive_scoring().model_copy(update={"minimum_scored_components": 8})
    graph = scored_graph(candidates, events, (timeline,), bands)
    context = build_context(events, (timeline,), candidates, bands=bands)
    verdict = decide(graph.edges[0], context.parameters, context.bands, context.events_by_id())
    assert verdict.reason is DemotionReason.INSUFFICIENT_EVIDENCE
    assert "not a weak claim" in verdict.detail


def test_an_unverifiable_pair_is_refused_and_named_as_such() -> None:
    """`TEMPORALLY_UNVERIFIABLE` is kept distinct from an unresolvable tie."""
    participant, events, timeline = linear_process("STAGE_ONE", "STAGE_TWO", subject="A")
    unplaced = unknown_time_event("STAGE_THREE", participant=participant)
    facts = (*events, unplaced)
    candidates = (candidate(events[0], unplaced),)
    graph = scored_graph(candidates, facts, (timeline,))
    context = build_context(facts, (timeline,), candidates)
    verdict = decide(graph.edges[0], context.parameters, context.bands, context.events_by_id())
    assert verdict.reason is DemotionReason.TEMPORALLY_UNVERIFIABLE
    assert "never placed" in verdict.detail


def test_an_undetermined_pair_is_refused_with_a_different_reason() -> None:
    """Two events the source placed but could not separate. The R-14 case.

    Overlapping intervals rather than identical instants: identical instants are a LAW-TIME
    VIOLATION and are refused at candidate construction, which is a different -- and already
    tested -- path. `UNDETERMINED` is the case where both events WERE placed and the bounds
    admit either ordering, which is what a day-granular source produces in bulk.
    """
    citation = evidence_record("row-overlap")
    participant = entity("A", citation=citation)
    earlier = event(
        "STAGE_ONE", interval(0, span_days=2), citation=citation, participants=(participant,)
    )
    later = event(
        "STAGE_TWO", interval(1, span_days=2), citation=citation, participants=(participant,)
    )
    events = (earlier, later)
    line = timeline(*events)
    candidates = (candidate(earlier, later),)
    graph = scored_graph(candidates, events, (line,))
    context = build_context(events, (line,), candidates)
    verdict = decide(graph.edges[0], context.parameters, context.bands, context.events_by_id())
    assert verdict.reason is DemotionReason.TEMPORAL_NOT_CERTAIN
    assert "could not separate" in verdict.detail


def test_law_time_is_re_verified_against_the_events_not_the_stored_fields() -> None:
    """A stored verdict the intervals do not support is refused, and the mismatch is named.

    This is the check a stored `CausalEdge` cannot perform on itself: it holds identifiers,
    not intervals (DEF-0002). Removing the events from the fact set makes re-verification
    impossible, and an impossible check must never read as a passed one.
    """
    scored, context = _one_claim()
    verdict = decide(scored, context.parameters, context.bands, {})
    assert verdict.reason is DemotionReason.TEMPORAL_NOT_CERTAIN
    assert "could not be re-verified" in verdict.detail


def test_a_threshold_naming_an_undeclared_band_reports_the_pack_not_the_claim() -> None:
    """The loader errors on this; the builder repeats it so an unchecked pack still says why."""
    scored, context = _one_claim()
    bands = context.bands.model_copy(
        update={
            "confidence_bands": (
                ConfidenceBandSpec(name="OTHER", minimum_scalar=0.0, plain_language="fixture"),
            )
        }
    )
    verdict = decide(scored, context.parameters, bands, context.events_by_id())
    assert verdict.reason is DemotionReason.POLICY_NOT_RUNNABLE


def test_promote_refuses_an_edge_whose_events_are_absent() -> None:
    """The second belt-and-braces check raises rather than laundering the edge."""
    scored, context = _one_claim()
    with pytest.raises(LawViolationError, match="LAW-TIME"):
        promote(
            scored,
            PropagationWeight(
                weight=1.0, basis=WeightBasis.CONFIDENCE_SHARE, competing_edge_count=1
            ),
            TypingRecord(edge_kind="DIRECT", basis=TypingBasis.UNTYPED_DEFAULT),
            "STRONG",
            _lineage_of(scored),
            {},
        )


def test_promotion_assigns_inferred_and_replaces_the_propagation_weight() -> None:
    """One field, one meaning: module 10's placeholder scalar becomes an attribution share."""
    scored, context = _one_claim()
    weight = PropagationWeight(
        weight=0.25, basis=WeightBasis.CONFIDENCE_SHARE, competing_edge_count=4
    )
    promoted = promote(
        scored,
        weight,
        TypingRecord(edge_kind="DIRECT", basis=TypingBasis.UNTYPED_DEFAULT),
        "STRONG",
        _lineage_of(scored),
        context.events_by_id(),
    )
    assert isinstance(promoted, PromotedEdge)
    assert promoted.edge.provenance_class is ProvenanceClass.INFERRED
    assert promoted.edge.propagation_weight == 0.25
    assert promoted.edge.causal_edge_id == scored.edge.causal_edge_id
    assert scored.edge.provenance_class is not ProvenanceClass.INFERRED


def _lineage_of(scored: object) -> object:
    """Return a minimal, valid lineage for the edge under test."""
    from causalog.causal_engine.causal_graph_builder import EdgeLineage

    return EdgeLineage(
        candidate_edge_ids=(scored.edge.causal_edge_id,),
        generator_ids=("fixture_generator",),
        evidence_item_ids=tuple(sorted({item.evidence_item_id for item in scored.edge.evidence})),
        confidence=scored.edge.confidence,
        band_name=scored.band_name,
        scored_component_count=scored.scored_component_count,
        outcome=scored.outcome.value,
    )
