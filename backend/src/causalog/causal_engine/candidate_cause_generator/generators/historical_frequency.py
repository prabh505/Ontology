"""Generator (e): this sequenced type pair recurs across process instances.

Counts, and nothing else. An sequenced pair of event types is offered as a hypothesis when it
co-occurs -- in that sequence, within one timeline -- in at least the declared number of
distinct process instances.

**What separates this from `statistical_association.py`.** This generator measures
RECURRENCE: how many instances exhibit the pattern at all. That one measures ASSOCIATION:
whether the pattern occurs more than the two types' independent rates predict. A pair can
recur constantly and have no association (both types occur in every instance), and a pair
can be strongly associated and recur rarely. They are different findings and they are kept
apart so a reader can see which one a candidate rests on.

Recurrence is not causation, is not correlation, and does not survive the disappearance of
the temporal gate: the gate is what supplies direction here, and the count supplies only
the reason to look.
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
)
from causalog.core.provenance import ProvenanceClass
from causalog.core.types import DirectCause, Event, EvidenceKind

__all__ = ["HistoricalFrequencyGenerator"]


def _sequenced_type_pairs(held: tuple[Event, ...]) -> frozenset[tuple[str, str]]:
    """Return every sequenced event-type pair one timeline exhibits.

    Sequenced by the timeline's own sequence, which is `Timeline`'s contract and not a
    precedence claim -- `TimeInterval.sort_key` says so explicitly. Precedence is decided
    later by `verdict`, and a pair this function reports may well be rejected there.
    """
    pairs: set[tuple[str, str]] = set()
    for index, cause in enumerate(held):
        for effect in held[index + 1 :]:
            if cause.event_type != effect.event_type:
                pairs.add((cause.event_type, effect.event_type))
    return frozenset(pairs)


class HistoricalFrequencyGenerator:
    """Propose pairs whose sequenced type pattern recurs across enough instances."""

    generator_id = "historical_frequency"

    def status(self, context: GenerationContext) -> GeneratorStatus:
        """Runnable only when the pack declares both a support floor and a weight."""
        parameters = context.parameters
        if (
            parameters.minimum_support_count is None
            or parameters.historical_frequency_strength is None
        ):
            return GeneratorStatus.NOT_RUNNABLE
        return GeneratorStatus.RAN

    def requirement(self) -> str:
        """Return what a pack must declare for this generator to run."""
        return (
            "candidate_generation.minimum_support_count and "
            "candidate_generation.historical_frequency_strength. A support floor written "
            "into engine code would be a threshold that does not move when the domain is "
            "swapped (CONVENTIONS.md §6a)."
        )

    def propose(self, context: GenerationContext) -> tuple[Proposal, ...]:
        """Return one proposal per instance pair whose type pattern clears the floor."""
        parameters = context.parameters
        floor = parameters.minimum_support_count
        strength = parameters.historical_frequency_strength
        if floor is None or strength is None:
            return ()
        events_by_id = context.events_by_id()

        per_timeline: list[tuple[str, tuple[Event, ...], frozenset[tuple[str, str]]]] = []
        support: dict[tuple[str, str], int] = {}
        for timeline in context.timelines:
            held = events_of_timeline(timeline, events_by_id)
            pairs = _sequenced_type_pairs(held)
            per_timeline.append((timeline.timeline_id, held, pairs))
            for pair in pairs:
                support[pair] = support.get(pair, 0) + 1

        instances = len(per_timeline)
        recurrent = {pair for pair, seen in support.items() if seen >= floor}
        proposals: list[Proposal] = []
        for timeline_id, held, pairs in per_timeline:
            for pair in sorted(pairs & recurrent):
                cause_type, effect_type = pair
                seen = support[pair]
                for index, cause in enumerate(held):
                    if cause.event_type != cause_type:
                        continue
                    for effect in held[index + 1 :]:
                        if effect.event_type != effect_type:
                            continue
                        proposals.append(
                            Proposal(
                                generator_id=self.generator_id,
                                cause_event=cause,
                                effect_event=effect,
                                payload=DirectCause(),
                                evidence=(
                                    evidence_item(
                                        kind=EvidenceKind.HISTORICAL_FREQUENCY,
                                        description=(
                                            f"The sequenced pattern {cause_type} then "
                                            f"{effect_type} recurs in {seen} of "
                                            f"{instances} process instance(s). Recurrence "
                                            "establishes that the pattern is common. It "
                                            "does not establish that either occurrence "
                                            "produced the other, and it is not a "
                                            "correlation: nothing here compares the "
                                            "pattern against what independence would "
                                            "predict."
                                        ),
                                        verification=(
                                            "count of timelines whose event sequence "
                                            f"contains {cause_type} before {effect_type} "
                                            f"== {seen}; total timelines == {instances}; "
                                            f"declared minimum_support_count == {floor}"
                                        ),
                                        supporting_ids=(
                                            cause.event_id,
                                            effect.event_id,
                                            timeline_id,
                                        ),
                                        strength=strength,
                                        provenance_class=ProvenanceClass.STATISTICAL,
                                    ),
                                ),
                            )
                        )
        return tuple(sorted(proposals, key=lambda item: item.sort_key()))
