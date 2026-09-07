"""End to end: fusion, the eight components, the gates, the outcome, and promotion.

These run module 9 for real and score its actual output. A hand-built candidate would let
the module pass over a shape the pipeline never produces.
"""

from __future__ import annotations

import pytest

from causalog.causal_engine.candidate_cause_generator import GenerationResult
from causalog.causal_engine.confidence_scorer import (
    SCORER_COUNT,
    ScoringOutcome,
    ScoringResult,
    fuse_candidates,
    score_candidates,
)
from causalog.core.aggregation import (
    CONTRADICTION_CEILING_ANCHORS,
    TEMPORAL_CEILING_ANCHORS,
    V2_COMPONENT_NAMES,
    ceiling_at,
)
from causalog.core.provenance import ProvenanceClass
from causalog.core.types import Event, Timeline
from causalog.rule_engine import ConfidenceScoringSpec
from fixtures.candidates import envelope, scoring_context_for, scoring_parameters
from tests.unit.causal_engine.confidence_scorer.conftest import candidates_over


def _score(
    events: tuple[Event, ...],
    timelines: tuple[Timeline, ...],
    parameters: ConfidenceScoringSpec | None = None,
    **context_kwargs: object,
) -> tuple[GenerationResult, ScoringResult]:
    """Run module 9 then module 10 over these facts and return the scoring result."""
    generated = candidates_over(events, timelines)
    context = scoring_context_for(
        events,
        timelines,
        parameters if parameters is not None else scoring_parameters(),
        confounding_flags=generated.confounding_flags,
        proposed_pairs=frozenset(
            (candidate.source_event_id, candidate.target_event_id)
            for candidate in generated.graph.candidates
        ),
        **context_kwargs,  # type: ignore[arg-type]
    )
    return generated, score_candidates(generated.graph.candidates, context, envelope())


# ---------------------------------------------------------------------------------------
# Fusion
# ---------------------------------------------------------------------------------------


def test_parallel_candidates_fuse_into_one_edge_carrying_every_justification(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """Module 9's multigraph becomes one scored edge per (source, target, kind).

    `CausalEdge.address` omits the generator and `CandidateEdge.address` includes it, so
    several proposals over one pair are one claim with several justifications. Scoring
    them separately would emit several edges colliding on one identifier.
    """
    events, timelines = three_stage_run
    generated, result = _score(events, timelines)
    assert len(generated.graph.candidates) > len(result.graph.edges)
    for edge in result.graph.edges:
        claim_items = {item.evidence_item_id for item in edge.edge.evidence}
        contributing = {
            item.evidence_item_id
            for candidate in generated.graph.candidates
            if (candidate.source_event_id, candidate.target_event_id)
            == (edge.edge.source_event_id, edge.edge.target_event_id)
            and candidate.payload.edge_kind is edge.edge.payload.edge_kind
            for item in candidate.evidence
        }
        assert claim_items == contributing


def test_fusion_is_deterministic_and_canonically_sequenced(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """Two fusions of one input produce one value; the graph refuses an unsequenced one."""
    events, timelines = three_stage_run
    generated = candidates_over(events, timelines)
    first, first_divergences = fuse_candidates(generated.graph.candidates)
    second, second_divergences = fuse_candidates(tuple(reversed(generated.graph.candidates)))
    assert first == second
    assert first_divergences == second_divergences
    keys = [claim.sort_key() for claim in first]
    assert keys == sorted(keys)


# ---------------------------------------------------------------------------------------
# LAW-EVIDENCE: no component is ever skipped
# ---------------------------------------------------------------------------------------


def test_every_edge_carries_all_eight_components(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """The module's central rule. A vector short a component silently changes every score.

    `ConfidenceVector` would accept seven components quite happily -- it only requires
    non-empty, sorted and unrepeated -- and `weighted_mean` would renormalize over what
    remained. That is precisely why this is asserted here rather than left to the type.
    """
    events, timelines = three_stage_run
    _, result = _score(events, timelines)
    assert result.graph.edges
    for edge in result.graph.edges:
        names = {item.component_name for item in edge.edge.confidence.components}
        assert names == V2_COMPONENT_NAMES
        assert len(edge.edge.confidence.components) == SCORER_COUNT
        assert len(edge.explanations) == SCORER_COUNT


def test_a_missing_component_is_emitted_flagged_and_counted_never_omitted(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """Missing costs score and is reported; it never abstains and never disappears.

    `graph_connectivity` is missing on every edge today because module 7 does not exist.
    The component is present in every vector at 0.0, its explanation says missing, and
    the report counts it -- so the gap is in the artifact rather than inferable from one.
    """
    events, timelines = three_stage_run
    _, result = _score(events, timelines)
    for edge in result.graph.edges:
        connectivity = next(
            item for item in edge.explanations if item.component_name == "graph_connectivity"
        )
        assert connectivity.missing is True
        value = next(
            item.value
            for item in edge.edge.confidence.components
            if item.component_name == "graph_connectivity"
        )
        assert value == 0.0
    tally = next(
        item for item in result.report.components if item.component_name == "graph_connectivity"
    )
    assert tally.missing_count == len(result.graph.edges)
    assert tally.looks_inert is True


def test_every_component_that_scored_cites_evidence(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """LAW-EVIDENCE: a value nobody can trace back to a record is a defect."""
    events, timelines = three_stage_run
    _, result = _score(events, timelines)
    for edge in result.graph.edges:
        missing_names = {item.component_name for item in edge.explanations if item.missing}
        for component in edge.edge.confidence.components:
            if component.component_name in missing_names:
                continue
            assert component.evidence_record_ids, component.component_name


# ---------------------------------------------------------------------------------------
# The gates
# ---------------------------------------------------------------------------------------


def test_the_temporal_gate_caps_every_edge_it_binds_on(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """No edge's scalar exceeds the ceiling its temporal support implies. Ever."""
    events, timelines = three_stage_run
    _, result = _score(events, timelines)
    for edge in result.graph.edges:
        temporal = next(
            item.value
            for item in edge.edge.confidence.components
            if item.component_name == "temporal_support"
        )
        assert edge.edge.confidence.scalar <= ceiling_at(temporal, TEMPORAL_CEILING_ANCHORS)


def test_an_unverifiable_edge_is_capped_however_strong_its_other_support() -> None:
    """The requirement in one test: ordering that rests on nothing is a hard cap.

    An event the source never placed in time gives `temporal_support == 0.0`, whose
    ceiling is 0.25. Whatever the other seven components say, the scalar cannot exceed it
    -- because a claim that A caused B without knowing A came first is not a weak causal
    claim, it is not a causal claim.
    """
    from fixtures.candidates import linear_process, unknown_time_event
    from fixtures.facts import timeline as build_timeline

    participant, placed, _ = linear_process("STAGE_ONE", "STAGE_TWO", subject="A")
    unplaced = unknown_time_event("STAGE_THREE", participant=participant)
    events = (*placed, unplaced)
    timelines = (build_timeline(*events),)
    _, result = _score(events, timelines)

    unverifiable = [edge for edge in result.graph.edges if edge.edge.temporally_unverifiable]
    assert unverifiable, "the fixture must produce at least one unverifiable edge"
    for edge in unverifiable:
        assert edge.edge.confidence.scalar <= 0.25
        # The gate is recorded as BINDING only where it actually held the score down. On
        # this sparse fixture the addend mean is already below the ceiling, so the cap is
        # not what produced the low score -- and saying otherwise would overstate it. The
        # cap itself is asserted unconditionally above, and exercised against every addend
        # at 1.0 in `tests/unit/core/test_confidence_aggregation.py`.
        if edge.ungated_mean > 0.25:
            assert edge.binding_gate == "temporal_support"
        assert edge.edge.provenance_class is not ProvenanceClass.INFERRED


def test_the_contradiction_gate_caps_a_prohibited_pair(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """A pair the pack prohibits is capped, not outvoted by correlation.

    A prohibition drives `contradiction_freedom` to 0.5, whose ceiling is 0.60. The edge
    cannot be reported above that however much other support it carries.
    """
    events, timelines = three_stage_run
    generated = candidates_over(events, timelines)
    pair = (
        generated.graph.candidates[0].source_event_id,
        generated.graph.candidates[0].target_event_id,
    )
    _, result = _score(events, timelines, suppressed_pairs=frozenset({pair}))
    edge = next(
        item
        for item in result.graph.edges
        if (item.edge.source_event_id, item.edge.target_event_id) == pair
    )
    freedom = next(
        item.value
        for item in edge.edge.confidence.components
        if item.component_name == "contradiction_freedom"
    )
    assert freedom == 0.5
    assert edge.edge.confidence.scalar <= ceiling_at(freedom, CONTRADICTION_CEILING_ANCHORS)


def test_the_report_says_which_gate_bound_and_how_often(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """A gate binding on most edges is a finding no single edge can express."""
    events, timelines = three_stage_run
    _, result = _score(events, timelines)
    counted = dict(result.report.gate_binding_counts)
    assert sum(counted.values()) == len(result.graph.edges)


# ---------------------------------------------------------------------------------------
# Insufficient evidence, bands, promotion
# ---------------------------------------------------------------------------------------


def test_insufficient_evidence_is_a_distinct_outcome_not_a_low_band(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """Not-enough-measured gets no band, is never promoted, and still has a vector.

    Setting the floor to eight makes every edge insufficient, because
    `graph_connectivity` is missing on all of them. The vector is still complete --
    LAW-EVIDENCE is not waivable and an empty vector is a defect -- and no band is
    assigned, because an absence of measurement must not be shown as a measurement.
    """
    events, timelines = three_stage_run
    parameters = scoring_parameters(minimum_scored_components=8)
    _, result = _score(events, timelines, parameters)
    assert result.graph.edges
    for edge in result.graph.edges:
        assert edge.outcome is ScoringOutcome.INSUFFICIENT_EVIDENCE
        assert edge.band_name is None
        assert edge.band_plain_language is None
        assert edge.edge.provenance_class is not ProvenanceClass.INFERRED
        assert edge.edge.confidence.components
    assert result.report.insufficient_count == len(result.graph.edges)
    assert result.report.scored_count == 0


def test_a_low_score_with_enough_measured_is_scored_and_banded(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """The other half of the distinction: a weak claim is a finding, and gets a band."""
    events, timelines = three_stage_run
    _, result = _score(events, timelines, scoring_parameters(minimum_scored_components=3))
    scored = result.graph.scored_edges()
    assert scored
    for edge in scored:
        assert edge.outcome is ScoringOutcome.SCORED
        assert edge.band_name is not None
        assert edge.band_plain_language


def test_a_pack_declaring_no_bands_gets_no_labels_rather_than_invented_ones(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """The engine never writes the sentence the pack refused to write (ADR-0053)."""
    events, timelines = three_stage_run
    parameters = scoring_parameters(with_bands=False)
    _, result = _score(events, timelines, parameters)
    assert all(edge.band_name is None for edge in result.graph.edges)
    assert result.report.bands_declared == ()
    assert all(
        edge.edge.provenance_class is not ProvenanceClass.INFERRED for edge in result.graph.edges
    )


def test_promotion_requires_time_outcome_and_band_together(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """Three necessary conditions, and the type enforces the first independently.

    A promoted edge must be temporally certain, scored rather than insufficient, and at
    the pack's declared promotion band. `CausalEdge` itself refuses `INFERRED` on an
    ambiguous or absent interval, so a bug here raises rather than laundering an edge in.
    """
    events, timelines = three_stage_run
    _, result = _score(events, timelines)
    for edge in result.graph.promoted_edges():
        assert edge.edge.temporally_unverifiable is False
        assert edge.outcome is ScoringOutcome.SCORED
        assert edge.band_name == "STRONG"


def test_the_graph_refuses_to_lose_an_edge_between_two_of_its_own_numbers(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """Every fused claim is scored. An edge dropped in between is a silent judgement."""
    events, timelines = three_stage_run
    generated, result = _score(events, timelines)
    claims, _ = fuse_candidates(generated.graph.candidates)
    assert result.graph.claims_scored == len(claims) == len(result.graph.edges)
    assert (
        result.report.scored_count + result.report.insufficient_count == result.graph.claims_scored
    )


def test_the_graph_is_sequenced_canonically_and_never_by_score(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """Ranking is module 11's. A graph arriving pre-sorted makes its job look done."""
    events, timelines = three_stage_run
    _, result = _score(events, timelines)
    keys = [edge.sort_key() for edge in result.graph.edges]
    assert keys == sorted(keys)


def test_the_vector_names_a_registered_function_that_reproduces_its_own_scalar(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """A scalar whose function is unnamed is the unexplained number prd.md §49 forbids."""
    from causalog.core.aggregation import AGGREGATORS

    events, timelines = three_stage_run
    _, result = _score(events, timelines)
    for edge in result.graph.edges:
        vector = edge.edge.confidence
        assert vector.aggregation in AGGREGATORS
        assert AGGREGATORS[vector.aggregation](vector.components) == vector.scalar


def test_the_breakdown_matches_the_vector_it_explains(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """A breakdown naming other components would be read as the reason for this number."""
    events, timelines = three_stage_run
    _, result = _score(events, timelines)
    for edge in result.graph.edges:
        assert [item.component_name for item in edge.explanations] == [
            item.component_name for item in edge.edge.confidence.components
        ]


def test_scoring_is_deterministic(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """Two scorings of one input are byte-identical (`CONVENTIONS.md` §11)."""
    from causalog.core.serialization import to_canonical_json

    events, timelines = three_stage_run
    _, first = _score(events, timelines)
    _, second = _score(events, timelines)
    assert to_canonical_json(first.graph) == to_canonical_json(second.graph)
    assert to_canonical_json(first.report) == to_canonical_json(second.report)


def test_the_report_leads_with_what_is_not_calibrated(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """The caveat comes before the numbers, so a reader who stops early has read it."""
    from causalog.causal_engine.confidence_scorer import NOT_CALIBRATED_NOTICE, render_markdown

    events, timelines = three_stage_run
    _, result = _score(events, timelines)
    rendered = render_markdown(result.report)
    assert NOT_CALIBRATED_NOTICE.splitlines()[0] in rendered
    assert rendered.index("## What is not calibrated") < rendered.index(
        "## Confidence distribution"
    )


def test_a_run_with_no_scoring_knobs_declared_scores_nothing_and_says_which(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """An empty `confidence_scoring` block is legal and produces missing components.

    ADR-0049's rule carried forward: absent means NOT SCORABLE, never a default. The two
    components that need no declaration -- diversity and contradiction freedom -- still
    score, which is why the vector is never empty.
    """
    events, timelines = three_stage_run
    _, result = _score(events, timelines, ConfidenceScoringSpec())
    for edge in result.graph.edges:
        missing = {item.component_name for item in edge.explanations if item.missing}
        assert {"temporal_support", "historical_support", "statistical_support"} <= missing
        assert "contradiction_freedom" not in missing
        assert edge.band_name is None
    assert all(tally.requirement for tally in result.report.missing_components)


@pytest.mark.parametrize("floor", [1, 3, 8])
def test_the_outcome_floor_is_read_from_the_pack(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]], floor: int
) -> None:
    """How many measured components make a score meaningful is a domain judgement."""
    events, timelines = three_stage_run
    _, result = _score(events, timelines, scoring_parameters(minimum_scored_components=floor))
    for edge in result.graph.edges:
        expected = (
            ScoringOutcome.SCORED
            if edge.scored_component_count >= floor
            else ScoringOutcome.INSUFFICIENT_EVIDENCE
        )
        assert edge.outcome is expected
