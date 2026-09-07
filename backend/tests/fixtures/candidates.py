"""Synthetic, domain-neutral scaffolding for the module 9 tests.

`CONVENTIONS.md` §14: fixtures are synthetic and domain-neutral by default. Event types
here are `STAGE_ONE`..`STAGE_FOUR`; nothing names a real domain, because a module whose
entire premise is domain independence must not be tested through domain vocabulary.

Builds on `tests.fixtures.facts` rather than beside it -- these helpers assemble
generation contexts out of the artifacts `facts.py` already addresses correctly, so a
broken address recipe fails here too rather than being papered over by a second builder.
"""

from __future__ import annotations

from causalog.causal_engine.candidate_cause_generator import GenerationContext
from causalog.causal_engine.confidence_scorer import PairBaseRates, ScoringContext
from causalog.core.precedence import DerivedPrecedenceIndex
from causalog.core.provenance import ProvenanceClass
from causalog.core.run import OutputEnvelope
from causalog.core.temporal import (
    UNKNOWN_EARLIEST,
    UNKNOWN_LATEST,
    Precision,
    TimeInterval,
)
from causalog.core.types import Entity, Event, Timeline
from causalog.rule_engine import (
    CandidateGenerationSpec,
    ConfidenceBandSpec,
    ConfidenceScoringSpec,
    EvaluationResult,
)
from causalog.rule_engine.dsl import ProximityWindowSpec, TemporalWindow
from causalog.rule_engine.facts import FactSet
from fixtures.facts import entity, event, evidence_record, interval, timeline

__all__ = [
    "RUN_ID",
    "context_for",
    "envelope",
    "linear_process",
    "scoring_context_for",
    "scoring_parameters",
    "unknown_time_event",
    "window",
]

RUN_ID = "run:fixture00000000"


def envelope(run_id: str = RUN_ID) -> OutputEnvelope:
    """Return a fixed envelope. Every version is pinned so reruns are byte-identical."""
    return OutputEnvelope(
        run_id=run_id,
        ontology_version="1.0.0",
        ontology_hash="ont:0000000000000000",
        dataset_version="dataset:test-0001",
        rule_pack_version="1.1.0",
        engine_version="0.1.0",
        graph_projection_version="gpv:0000000000000000",
        seed=0,
        execution_id="execution:fixture",
    )


def window(
    cause_type: str, effect_type: str, *, seconds: int = 864_000, strength: float = 0.5
) -> ProximityWindowSpec:
    """Return one declared proximity window, ten days wide unless told otherwise."""
    return ProximityWindowSpec(
        cause_event_type=cause_type,
        effect_event_type=effect_type,
        window=TemporalWindow(minimum_seconds=0, maximum_seconds=seconds),
        rationale="fixture window; not calibrated against anything",
        evidence_strength=strength,
    )


def linear_process(
    *event_types: str, subject: str = "A", start_day: int = 0, step_days: int = 2
) -> tuple[Entity, tuple[Event, ...], Timeline]:
    """Return one participant, one event per type two days apart, and their timeline.

    Separated by whole days with DAY precision, so `verdict` returns `CERTAIN` for every
    forward pair and `VIOLATION` for every reverse one. That is what makes the gate's
    behaviour assertable without the fixture having to reach into `core.temporal`.
    """
    citation = evidence_record(f"row-{subject}")
    participant = entity(subject, citation=citation)
    events = tuple(
        event(
            event_type,
            interval(start_day + index * step_days),
            citation=citation,
            participants=(participant,),
        )
        for index, event_type in enumerate(event_types)
    )
    return participant, events, timeline(*events)


def unknown_time_event(event_type: str, *, participant: Entity, subject: str = "A") -> Event:
    """Return an event the source never placed in time.

    `Precision.UNKNOWN` forces `ASSUMED` provenance and the unbounded interval -- the
    invariants `TimeInterval` enforces. Any candidate touching it is
    `temporally_unverifiable`, which is the third gate outcome and NOT the same as
    `UNDETERMINED`.
    """
    citation = evidence_record(f"row-{subject}-unplaced")
    return event(
        event_type,
        TimeInterval(
            t_earliest=UNKNOWN_EARLIEST,
            t_latest=UNKNOWN_LATEST,
            precision=Precision.UNKNOWN,
            provenance=ProvenanceClass.ASSUMED,
            source="fixture: the source recorded no instant",
        ),
        citation=citation,
        participants=(participant,),
    )


def context_for(
    events: tuple[Event, ...],
    timelines: tuple[Timeline, ...],
    parameters: CandidateGenerationSpec,
    *,
    rule_evaluation: EvaluationResult | None = None,
    relationships: tuple[object, ...] = (),
    run_id: str = RUN_ID,
) -> GenerationContext:
    """Return a context over the given facts, with everything else defaulted."""
    return GenerationContext(
        facts=FactSet.of(events=events, relationships=relationships),  # type: ignore[arg-type]
        timelines=timelines,
        parameters=parameters,
        rule_evaluation=rule_evaluation,
        run_id=run_id,
    )


# ---------------------------------------------------------------------------------------
# Module 10 scaffolding. Built on the module 9 helpers above rather than beside them, so a
# broken address recipe or a broken gate fails here too instead of being papered over by a
# second builder (`CONVENTIONS.md` §14).
# ---------------------------------------------------------------------------------------


def scoring_parameters(
    *,
    lift_reference: float | None = 3.0,
    small_sample_prior_count: int | None = 20,
    evidence_count_saturation_k: int | None = 3,
    temporal_reference_seconds: int | None = 86_400,
    undetermined_temporal_support: float | None = 0.15,
    derived_precedence_temporal_support: float | None = 0.10,
    minimum_scored_components: int | None = 3,
    promotion_band: str | None = "STRONG",
    with_bands: bool = True,
) -> ConfidenceScoringSpec:
    """Return a fully declared scoring spec, with every knob overridable to None.

    Defaulted to DataCo's declared values so a fixture and the shipped pack agree unless a
    test deliberately says otherwise; every field is settable to None so the NOT-SCORABLE
    path is reachable without hand-building a spec.
    """
    bands = (
        (
            ConfidenceBandSpec(
                name="STRONG",
                minimum_scalar=0.70,
                plain_language="fixture band; strong",
            ),
            ConfidenceBandSpec(
                name="SUGGESTIVE",
                minimum_scalar=0.45,
                plain_language="fixture band; suggestive",
            ),
            ConfidenceBandSpec(
                name="WEAK",
                minimum_scalar=0.0,
                plain_language="fixture band; weak -- inspect before acting",
            ),
        )
        if with_bands
        else ()
    )
    return ConfidenceScoringSpec(
        lift_reference=lift_reference,
        small_sample_prior_count=small_sample_prior_count,
        evidence_count_saturation_k=evidence_count_saturation_k,
        temporal_reference_seconds=temporal_reference_seconds,
        undetermined_temporal_support=undetermined_temporal_support,
        derived_precedence_temporal_support=derived_precedence_temporal_support,
        minimum_scored_components=minimum_scored_components,
        promotion_band=promotion_band if with_bands else None,
        confidence_bands=bands,
    )


def scoring_context_for(
    events: tuple[Event, ...],
    timelines: tuple[Timeline, ...],
    parameters: ConfidenceScoringSpec | None = None,
    *,
    rule_evaluation: EvaluationResult | None = None,
    relationships: tuple[object, ...] = (),
    confounding_flags: tuple[object, ...] = (),
    suppressed_pairs: frozenset[tuple[str, str]] = frozenset(),
    proposed_pairs: frozenset[tuple[str, str]] = frozenset(),
    derived_precedence: DerivedPrecedenceIndex | None = None,
    run_id: str = RUN_ID,
) -> ScoringContext:
    """Return a scoring context over the given facts, with base rates computed from them."""
    facts = FactSet.of(events=events, relationships=relationships)  # type: ignore[arg-type]
    events_by_id = {item.event_id: item for item in facts.events()}
    return ScoringContext(
        facts=facts,
        timelines=timelines,
        base_rates=PairBaseRates.of(timelines, events_by_id),
        parameters=parameters if parameters is not None else scoring_parameters(),
        rule_evaluation=rule_evaluation,
        confounding_flags=confounding_flags,  # type: ignore[arg-type]
        suppressed_pairs=suppressed_pairs,
        proposed_pairs=proposed_pairs,
        derived_precedence=derived_precedence,
        run_id=run_id,
    )
