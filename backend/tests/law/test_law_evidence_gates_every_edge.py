"""LAW-EVIDENCE at the boundary it exists to hold: module 10's own output.

The lint (`scripts/check_confidence_is_a_vector.py`) catches a confidence NAMED as a bare
float. It cannot catch a vector that is technically well formed and epistemically empty: one
component instead of eight, or a component citing nothing, or a scalar whose function is not
registered. `ConfidenceVector` refuses only the empty case.

So this file asserts the law over the artifacts the module actually produces. Module 10 is
the only place a `CausalEdge` is constructed and the only module permitted to write `CAUSES`
(`docs/architecture.md` §Module 10); if the law holds here it holds for every causal claim
the system can make.
"""

from __future__ import annotations

import pytest

from causalog.causal_engine.candidate_cause_generator import (
    GenerationContext,
    generate_candidates,
)
from causalog.causal_engine.confidence_scorer import (
    SCORER_COUNT,
    ScoringOutcome,
    ScoringResult,
    score_candidates,
)
from causalog.core.aggregation import AGGREGATORS, V2_COMPONENT_NAMES
from causalog.core.provenance import PROVENANCE_STRENGTH, ProvenanceClass
from causalog.core.types import CausalEdge, Event, Timeline
from causalog.rule_engine import CandidateGenerationSpec
from causalog.rule_engine.facts import FactSet
from fixtures.candidates import (
    RUN_ID,
    envelope,
    linear_process,
    scoring_context_for,
    scoring_parameters,
    unknown_time_event,
    window,
)
from fixtures.facts import timeline as build_timeline


@pytest.fixture
def scored_run() -> ScoringResult:
    """Return module 10's output over a run holding placed and unplaced events alike.

    Deliberately mixed: an unverifiable edge and a certain one exercise different paths
    through promotion, and a law that only held on the easy half would not be a law.
    """
    events: list[Event] = []
    timelines: list[Timeline] = []
    for subject in ("A", "B", "C"):
        participant, produced, _ = linear_process(
            "STAGE_ONE", "STAGE_TWO", "STAGE_THREE", subject=subject
        )
        held = list(produced)
        if subject == "C":
            held.append(unknown_time_event("STAGE_FOUR", participant=participant))
        events.extend(held)
        timelines.append(build_timeline(*held))
    all_events, all_timelines = tuple(events), tuple(timelines)

    parameters = CandidateGenerationSpec(
        proximity_windows=(
            window("STAGE_ONE", "STAGE_TWO"),
            window("STAGE_TWO", "STAGE_THREE"),
        ),
        minimum_support_count=1,
        historical_frequency_strength=0.4,
        minimum_lift=1.0,
        statistical_association_strength=0.2,
        shared_entity_strength=0.55,
        per_effect_candidate_cap=20,
    )
    generated = generate_candidates(
        GenerationContext(
            facts=FactSet.of(events=all_events),
            timelines=all_timelines,
            parameters=parameters,
            rule_evaluation=None,
            run_id=RUN_ID,
        ),
        envelope(),
    )
    context = scoring_context_for(
        all_events,
        all_timelines,
        scoring_parameters(),
        confounding_flags=generated.confounding_flags,
        proposed_pairs=frozenset(
            (candidate.source_event_id, candidate.target_event_id)
            for candidate in generated.graph.candidates
        ),
    )
    return score_candidates(generated.graph.candidates, context, envelope())


def test_no_edge_carries_a_confidence_without_components(scored_run: ScoringResult) -> None:
    """The law, stated plainly. A confidence returned without components is a defect."""
    assert scored_run.graph.edges
    for edge in scored_run.graph.edges:
        assert edge.edge.confidence.components
        assert len(edge.edge.confidence.components) == SCORER_COUNT
        assert {
            component.component_name for component in edge.edge.confidence.components
        } == V2_COMPONENT_NAMES


def test_every_component_is_named_valued_classed_and_traceable(scored_run: ScoringResult) -> None:
    """The four things `docs/contracts.md` §5 requires of a component, on every edge.

    A component that cannot be traced to evidence means the module is not done
    (`CONVENTIONS.md` §8). The one admissible exception is a component that measured
    nothing, and it must SAY so rather than merely cite nothing.
    """
    for edge in scored_run.graph.edges:
        missing = {item.component_name for item in edge.explanations if item.missing}
        for component in edge.edge.confidence.components:
            assert component.component_name.strip()
            assert 0.0 <= component.value <= 1.0
            assert isinstance(component.provenance_class, ProvenanceClass)
            if component.component_name not in missing:
                assert component.evidence_record_ids


def test_every_scalar_names_a_registered_function_and_recomputes_to_itself(
    scored_run: ScoringResult,
) -> None:
    """A scalar nobody can recompute is the unexplained number prd.md §49 forbids."""
    for edge in scored_run.graph.edges:
        vector = edge.edge.confidence
        assert vector.aggregation in AGGREGATORS
        assert AGGREGATORS[vector.aggregation](vector.components) == vector.scalar


def test_the_vector_provenance_is_the_weakest_component_not_the_arithmetic(
    scored_run: ScoringResult,
) -> None:
    """A high number over ASSUMED inputs is still ASSUMED (ADR-0005).

    The scalar and the provenance answer different questions and are answered separately.
    An aggregator that folded provenance into its arithmetic would let a confident score
    upgrade the pedigree of its own inputs.
    """
    for edge in scored_run.graph.edges:
        vector = edge.edge.confidence
        assert PROVENANCE_STRENGTH[vector.provenance_class] == min(
            PROVENANCE_STRENGTH[component.provenance_class] for component in vector.components
        )


def test_no_edge_is_ever_observed_and_none_is_inferred_on_unsound_time(
    scored_run: ScoringResult,
) -> None:
    """LAW-PROVENANCE and LAW-TIME, on the artifacts rather than on the type.

    Causation is never read from a source record, so `OBSERVED` is unreachable here. And
    an inference standing on ambiguous or absent time is an inference standing on
    nothing -- `CausalEdge` enforces it independently, which is what makes this a check
    of the module rather than a restatement of the type.
    """
    for edge in scored_run.graph.edges:
        assert edge.edge.provenance_class is not ProvenanceClass.OBSERVED
        if edge.edge.provenance_class is ProvenanceClass.INFERRED:
            assert edge.edge.temporally_unverifiable is False
            assert edge.outcome is ScoringOutcome.SCORED


def test_a_vector_of_mostly_absence_can_never_become_an_inference(
    scored_run: ScoringResult,
) -> None:
    """`INSUFFICIENT_EVIDENCE` blocks promotion regardless of how the arithmetic came out."""
    for edge in scored_run.graph.insufficient_edges():
        assert edge.edge.provenance_class is not ProvenanceClass.INFERRED
        assert edge.band_name is None


def test_the_only_causal_edges_in_the_run_came_through_this_module(
    scored_run: ScoringResult,
) -> None:
    """Module 10 is the only module permitted to construct one, and it used `between`.

    Asserted through the identifier: `CausalEdge.address` is content-addressed over
    `(source, target, edge_kind)`, so an edge whose stored id disagrees with its own
    recipe was assembled around the sanctioned constructor.
    """
    for edge in scored_run.graph.edges:
        assert edge.edge.causal_edge_id == CausalEdge.address(
            edge.edge.source_event_id,
            edge.edge.target_event_id,
            edge.edge.payload.edge_kind,
        )
