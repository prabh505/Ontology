"""Synthetic, domain-neutral scaffolding for the Causal Graph Builder's tests.

`CONVENTIONS.md` §14: fixtures are synthetic and domain-neutral. Event types here are
`STAGE_ONE`..`STAGE_FOUR`, and nothing names a real domain -- a module whose whole premise is
domain independence must not be tested through domain vocabulary.

Built on `fixtures.candidates` and `fixtures.facts` rather than beside them, and the scored
graphs are produced by **running module 10 for real** rather than by hand-assembling
`ScoredEdge` values. That is deliberate: a hand-built vector could disagree with its own
explanations, and every one of this module's tests would then be asserting against an
artifact module 10 would never produce.
"""

from __future__ import annotations

from causalog.causal_engine.causal_graph_builder import GraphBuildContext
from causalog.causal_engine.confidence_scorer import CausalGraph, score_candidates
from causalog.core.provenance import ProvenanceClass
from causalog.core.types import CandidateEdge, Event, Timeline
from causalog.core.types.causal_edge import CausalEdgePayload, DirectCause
from causalog.rule_engine import (
    CompetingEffectPolicy,
    ConfidenceBandSpec,
    ConfidenceScoringSpec,
    GraphConstructionSpec,
    PromotionThresholdSpec,
    WeightNormalization,
)
from causalog.rule_engine.facts import FactSet
from fixtures.candidates import RUN_ID, envelope, scoring_context_for, scoring_parameters
from fixtures.facts import evidence_item

__all__ = [
    "build_context",
    "candidate",
    "graph_parameters",
    "permissive_scoring",
    "scored_graph",
]


def permissive_scoring(strong_floor: float = 0.0) -> ConfidenceScoringSpec:
    """Return a scoring spec whose top band is reachable, so promotion is exercisable.

    The shipped DataCo pack puts `STRONG` at 0.70 and nothing on the measured slice reaches
    it, which is the honest finding module 10 reports and is a terrible way to test a
    promotion policy: every test would assert against an empty graph and would pass for the
    wrong reason. Lowering the floor HERE, in a fixture, keeps the pack honest while making
    the promotion path reachable -- and no test asserts a scalar against a shipped threshold.
    """
    return scoring_parameters(
        minimum_scored_components=1,
        promotion_band=None,
    ).model_copy(
        update={
            "confidence_bands": (
                ConfidenceBandSpec(
                    name="STRONG",
                    minimum_scalar=strong_floor,
                    plain_language="fixture band; reachable so promotion can be tested",
                ),
                ConfidenceBandSpec(
                    name="UNREACHABLE",
                    minimum_scalar=1.0,
                    plain_language="fixture band; nothing reaches it",
                ),
            )
        }
    )


def graph_parameters(
    *,
    kinds: tuple[str, ...] = ("DIRECT",),
    band: str = "STRONG",
    policy: CompetingEffectPolicy | None = CompetingEffectPolicy.RETAIN_ALL,
    retain: int | None = None,
    ceiling: float | None = 0.05,
    circuits: int | None = 100,
    minimum_participants: int | None = 2,
    attributions: tuple = (),
) -> GraphConstructionSpec:
    """Return a fully declared construction spec, with every knob overridable."""
    return GraphConstructionSpec(
        promotion_thresholds=tuple(
            PromotionThresholdSpec(
                edge_kind=kind,
                minimum_band=band,
                rationale="fixture threshold; not calibrated against anything",
            )
            for kind in kinds
        ),
        competing_effect_policy=policy,
        competing_retain_count=retain,
        diversity_credit_ceiling=ceiling,
        magnitude_attributions=attributions,
        weight_normalization=WeightNormalization.SHARE_OF_INCOMING,
        circuit_enumeration_cap=circuits,
        loop_minimum_participants=minimum_participants,
    )


def candidate(
    source: Event,
    target: Event,
    *,
    generator_id: str = "fixture_generator",
    payload: CausalEdgePayload | None = None,
    run_id: str = RUN_ID,
) -> CandidateEdge:
    """Return one proposal between two events, through the sanctioned constructor.

    `CandidateEdge.between` is used rather than a direct construction so the fixture cannot
    manufacture a temporal standing the events do not support -- which is the whole point of
    the tests that then re-verify it.
    """
    return CandidateEdge.between(
        source_event=source,
        target_event=target,
        generator_id=generator_id,
        payload=payload if payload is not None else DirectCause(),
        evidence=(evidence_item((source.event_id, target.event_id)),),
        provenance_class=ProvenanceClass.ASSUMED,
        run_id=run_id,
    )


def scored_graph(
    candidates: tuple[CandidateEdge, ...],
    events: tuple[Event, ...],
    timelines: tuple[Timeline, ...],
    parameters: ConfidenceScoringSpec | None = None,
) -> CausalGraph:
    """Run module 10 over the given proposals and return its graph."""
    context = scoring_context_for(
        events,
        timelines,
        parameters if parameters is not None else permissive_scoring(),
    )
    return score_candidates(candidates, context, envelope()).graph


def build_context(
    events: tuple[Event, ...],
    timelines: tuple[Timeline, ...],
    candidates: tuple[CandidateEdge, ...],
    parameters: GraphConstructionSpec | None = None,
    *,
    bands: ConfidenceScoringSpec | None = None,
    rule_evaluation: object | None = None,
    measurements: tuple = (),
    run_id: str = RUN_ID,
) -> GraphBuildContext:
    """Return a build context over the given facts, with everything else defaulted."""
    return GraphBuildContext(
        facts=FactSet.of(events=events),
        timelines=timelines,
        candidates=candidates,
        parameters=parameters if parameters is not None else graph_parameters(),
        bands=bands if bands is not None else permissive_scoring(),
        rule_evaluation=rule_evaluation,  # type: ignore[arg-type]
        magnitude_measurements=measurements,
        run_id=run_id,
    )
