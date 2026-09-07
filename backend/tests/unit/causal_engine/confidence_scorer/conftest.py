"""Shared construction for the module 10 tests.

Every helper here builds through the real pipeline -- module 9's generators and gate, then
module 10's fusion -- rather than hand-assembling a `FusedClaim`. A hand-built claim would
let these tests pass over a shape the system never produces, which is the failure mode
`CONVENTIONS.md` §1 names when it says a check that has never been observed to reject has
not been tested.
"""

from __future__ import annotations

import pytest

from causalog.causal_engine.candidate_cause_generator import (
    GenerationContext,
    generate_candidates,
)
from causalog.causal_engine.confidence_scorer import FusedClaim, fuse_candidates
from causalog.core.types import Event, Timeline
from causalog.rule_engine import CandidateGenerationSpec
from causalog.rule_engine.facts import FactSet
from fixtures.candidates import RUN_ID, envelope, linear_process, window


@pytest.fixture
def three_stage_run() -> tuple[tuple[Event, ...], tuple[Timeline, ...]]:
    """Return three process instances, each running STAGE_ONE -> TWO -> THREE.

    Every instance exhibits every stage, so every sequenced type pair has lift exactly
    1.0. That is deliberate: it is the base-rate case, and it must score zero.
    """
    events: list[Event] = []
    timelines: list[Timeline] = []
    for subject in ("A", "B", "C"):
        _, produced, built = linear_process(
            "STAGE_ONE", "STAGE_TWO", "STAGE_THREE", subject=subject
        )
        events.extend(produced)
        timelines.append(built)
    return tuple(events), tuple(timelines)


def generation_parameters(**overrides: object) -> CandidateGenerationSpec:
    """Return module 9 parameters permissive enough that several generators propose."""
    declared: dict[str, object] = {
        "proximity_windows": (
            window("STAGE_ONE", "STAGE_TWO"),
            window("STAGE_TWO", "STAGE_THREE"),
        ),
        "minimum_support_count": 1,
        "historical_frequency_strength": 0.4,
        "minimum_lift": 1.0,
        "statistical_association_strength": 0.2,
        "shared_entity_strength": 0.55,
        "per_effect_candidate_cap": 20,
    }
    declared.update(overrides)
    return CandidateGenerationSpec(**declared)  # type: ignore[arg-type]


def candidates_over(
    events: tuple[Event, ...],
    timelines: tuple[Timeline, ...],
    parameters: CandidateGenerationSpec | None = None,
):
    """Return module 9's real output over these facts."""
    context = GenerationContext(
        facts=FactSet.of(events=events),
        timelines=timelines,
        parameters=parameters if parameters is not None else generation_parameters(),
        rule_evaluation=None,
        run_id=RUN_ID,
    )
    return generate_candidates(context, envelope())


def one_claim(
    events: tuple[Event, ...],
    timelines: tuple[Timeline, ...],
    cause_type: str,
    effect_type: str,
) -> FusedClaim:
    """Return the fused claim over the first pair of the two named types."""
    by_id = {event.event_id: event for event in events}
    generated = candidates_over(events, timelines)
    claims, _ = fuse_candidates(generated.graph.candidates)
    for claim in claims:
        source = by_id[claim.source_event_id]
        target = by_id[claim.target_event_id]
        if source.event_type == cause_type and target.event_type == effect_type:
            return claim
    raise AssertionError(f"no fused claim from {cause_type} to {effect_type}")
