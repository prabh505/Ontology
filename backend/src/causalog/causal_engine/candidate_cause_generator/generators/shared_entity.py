"""Generator (c1): two events name one entity in common.

`EvidenceKind` distinguishes `SHARED_ENTITY` from `SHARED_IDENTIFIER`, so this module and
`shared_identifier.py` are two generators rather than one with a branch. Fusing them under
one identifier would make the per-generator report unable to say which of the two produced
a proposal -- and the whole purpose of that report is that a generator producing everything
or nothing is obvious.

A shared participant is the strongest linkage available without a rule: it is a fact about
the records rather than a belief about the domain. It is still only a linkage. Two events
naming one entity is a reason to CONSIDER a pair, never a reason to believe one produced
the other, and the evidence text says so in as many words.
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

__all__ = ["SharedEntityGenerator"]


def _participants(event: Event) -> frozenset[str]:
    """Return every entity the event names, in either role.

    Both roles, deliberately. A pair linked through one event's source and another's target
    is as linked as a pair sharing a source, and distinguishing them would be a claim about
    direction that this generator has no basis for -- direction comes from the temporal
    gate, not from which field an identifier sat in.
    """
    return frozenset(event.source_entity_ids) | frozenset(event.target_entity_ids)


class SharedEntityGenerator:
    """Propose every within-timeline pair of events that name an entity in common."""

    generator_id = "shared_entity"

    def status(self, context: GenerationContext) -> GeneratorStatus:
        """Runnable only when the pack states what a shared participant is worth."""
        if context.parameters.shared_entity_strength is None:
            return GeneratorStatus.NOT_RUNNABLE
        return GeneratorStatus.RAN

    def requirement(self) -> str:
        """Return what a pack must declare for this generator to run."""
        return (
            "candidate_generation.shared_entity_strength -- the authored weight the "
            "resulting EvidenceItem carries. Module 9 may not invent one: a weight is a "
            "judgement, and judgement is module 10's."
        )

    def propose(self, context: GenerationContext) -> tuple[Proposal, ...]:
        """Return one proposal per sequenced within-timeline pair sharing an entity."""
        strength = context.parameters.shared_entity_strength
        if strength is None:
            return ()
        events_by_id = context.events_by_id()
        proposals: list[Proposal] = []
        seen: set[tuple[str, str]] = set()
        for timeline in context.timelines:
            held = events_of_timeline(timeline, events_by_id)
            for cause in held:
                cause_entities = _participants(cause)
                if not cause_entities:
                    continue
                for effect in held:
                    if cause.event_id == effect.event_id:
                        continue
                    key = (cause.event_id, effect.event_id)
                    if key in seen:
                        continue
                    shared = tuple(sorted(cause_entities & _participants(effect)))
                    if not shared:
                        continue
                    seen.add(key)
                    proposals.append(
                        Proposal(
                            generator_id=self.generator_id,
                            cause_event=cause,
                            effect_event=effect,
                            payload=DirectCause(),
                            evidence=(
                                evidence_item(
                                    kind=EvidenceKind.SHARED_ENTITY,
                                    description=(
                                        f"{cause.event_type} and {effect.event_type} both "
                                        f"name {len(shared)} entity(ies) in common. A "
                                        "shared participant establishes that the two "
                                        "occurrences concern the same thing. It "
                                        "establishes no mechanism, and it is not a reason "
                                        "to believe one produced the other."
                                    ),
                                    verification=(
                                        "set(cause.source_entity_ids + "
                                        "cause.target_entity_ids) & "
                                        "set(effect.source_entity_ids + "
                                        f"effect.target_entity_ids) == {list(shared)}"
                                    ),
                                    supporting_ids=(cause.event_id, effect.event_id, *shared),
                                    strength=strength,
                                    provenance_class=ProvenanceClass.ASSUMED,
                                ),
                            ),
                        )
                    )
        return tuple(sorted(proposals, key=lambda item: item.sort_key()))
