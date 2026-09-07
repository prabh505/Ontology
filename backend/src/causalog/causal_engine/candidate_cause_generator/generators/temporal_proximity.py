"""Generator (a): two events sit within a declared window for their sequenced type pair.

The weakest of the seven, and deliberately so. It claims only that the pack declared this
sequenced type pair worth considering and that these two instances fall inside the declared
separation. It knows nothing about mechanism, nothing about participants, and nothing about
whether the pair recurs.

**The window does not decide precedence.** `causalog.core.temporal.verdict` does, in
`gate.py`, and no width declared in a pack can override it. This generator will happily
propose a pair the gate then rejects, and that rejection is counted rather than hidden --
a large rejection count here is a finding about the declared widths.
"""

from __future__ import annotations

from causalog.causal_engine.candidate_cause_generator.context import (
    GenerationContext,
    GeneratorStatus,
    Proposal,
)
from causalog.causal_engine.candidate_cause_generator.generators.support import (
    events_of_timeline,
    evidence_item,
    separation_bounds,
)
from causalog.core.provenance import ProvenanceClass
from causalog.core.types import DirectCause, EvidenceKind

__all__ = ["TemporalProximityGenerator"]


class TemporalProximityGenerator:
    """Propose a pair for every declared sequenced type pair whose instances fall in window."""

    generator_id = "temporal_proximity"

    def status(self, context: GenerationContext) -> GeneratorStatus:
        """Runnable only when the pack declares at least one proximity window."""
        if not context.parameters.proximity_windows:
            return GeneratorStatus.NOT_RUNNABLE
        return GeneratorStatus.RAN

    def requirement(self) -> str:
        """Return what a pack must declare for this generator to run."""
        return (
            "candidate_generation.proximity_windows -- at least one sequenced event-type "
            "pair with a TemporalWindow. Without a declared width this generator would "
            "have to invent one, and an invented width is domain policy in engine code."
        )

    def propose(self, context: GenerationContext) -> tuple[Proposal, ...]:
        """Return one proposal per in-window instance pair, in canonical sequence.

        Scoped to WITHIN a timeline rather than across the whole event set. Two events in
        unrelated process instances that happen to fall within a window are not a
        hypothesis anybody wants; they are the combinatorial explosion prd.md §27's
        candidate graph is otherwise vulnerable to.
        """
        parameters = context.parameters
        events_by_id = context.events_by_id()
        proposals: list[Proposal] = []
        for timeline in context.timelines:
            held = events_of_timeline(timeline, events_by_id)
            for cause in held:
                for effect in held:
                    if cause.event_id == effect.event_id:
                        continue
                    declared = parameters.window_entry_for(cause.event_type, effect.event_type)
                    if declared is None:
                        continue
                    window = declared.window
                    bounds = separation_bounds(cause.occurred_at, effect.occurred_at)
                    if not bounds.within(
                        window.minimum_seconds,
                        window.maximum_seconds,
                        window.minimum_inclusive,
                        window.maximum_inclusive,
                    ):
                        continue
                    proposals.append(
                        Proposal(
                            generator_id=self.generator_id,
                            cause_event=cause,
                            effect_event=effect,
                            payload=DirectCause(),
                            evidence=(
                                evidence_item(
                                    kind=EvidenceKind.TEMPORAL_PROXIMITY,
                                    description=(
                                        f"{cause.event_type} and {effect.event_type} fall "
                                        f"within the window the pack declares for that "
                                        f"sequenced pair, on timeline {timeline.timeline_id}. "
                                        "Proximity within a declared window establishes "
                                        "that the pair is worth considering. It "
                                        "establishes no mechanism and no shared "
                                        "participant."
                                    ),
                                    verification=(
                                        "separation_bounds(cause.occurred_at, "
                                        "effect.occurred_at) yields "
                                        f"[{bounds.minimum_seconds}, {bounds.maximum_seconds}] "
                                        "seconds, which overlaps the declared window "
                                        f"[{window.minimum_seconds}, "
                                        f"{window.maximum_seconds}] "
                                        f"(minimum_inclusive={window.minimum_inclusive}, "
                                        f"maximum_inclusive={window.maximum_inclusive}) for "
                                        f"{cause.event_type} -> {effect.event_type}"
                                    ),
                                    supporting_ids=(
                                        cause.event_id,
                                        effect.event_id,
                                        timeline.timeline_id,
                                    ),
                                    strength=declared.evidence_strength,
                                    provenance_class=ProvenanceClass.ASSUMED,
                                ),
                            ),
                        )
                    )
        return tuple(sorted(proposals, key=lambda item: item.sort_key()))
