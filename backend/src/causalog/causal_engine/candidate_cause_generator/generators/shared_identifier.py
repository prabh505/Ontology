"""Generator (c2): two events carry an identifier in common that is not a participant.

`EvidenceKind.SHARED_IDENTIFIER` is documented as "an identifier in common that is not
itself a participant". This generator reads `Event.metadata`, restricted to the keys the pack
DECLARES as carrying an identifier, and further excludes any value that names a participant
of either event -- otherwise every shared-entity pair would be proposed twice under two
evidence kinds, and the per-generator counts would both be wrong.

**Why the keys are declared rather than "all of metadata".** Measured, not predicted: the
Event Generator stamps traceability pairs on every event it emits -- `observation_mode`,
`emission`, `occurred_at_policy` (`extraction/event_generator/emit.py::_metadata`) -- and
nothing in the metadata shape distinguishes those from a domain identifier. A first draft of
this generator read all of `metadata` and, on the reference dataset, proposed a candidate for
**every pair of events sharing an observation mode**: 87,446 proposals, exactly matching the
shared-entity generator, none of which said anything about the domain. That is a fact about
how the events were MADE.

So the pack declares which keys carry identifiers, and a pack declaring none switches this
generator off and is told so. **The DataCo pack declares none, because DataCo's `Event`
carries none** -- every identifier the source records becomes a participant entity, which is
the shared-entity generator's territory. That is a real gap in this dataset reported as a
gap, rather than a generator producing 87,446 meaningless hypotheses.

This is a weaker linkage than a shared participant and is weighted separately by the pack
to say so: a common identifier links two RECORDS without establishing that they concern
one modelled thing.
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

__all__ = ["SharedIdentifierGenerator"]


def _identifier_pairs(event: Event, declared_keys: frozenset[str]) -> frozenset[tuple[str, str]]:
    """Return the declared-identifier metadata pairs, minus any participant value.

    Two filters, and both are load-bearing. The KEY filter keeps out the Event Generator's
    traceability pairs, which sit on every event and mean nothing here -- see the module
    docstring for the measurement that made this necessary. The VALUE filter keeps out
    anything naming a participant: two events may record one entity under two different
    metadata keys, and excluding by key name alone would let that pair through as a "shared
    identifier" when it is a shared participant wearing another label.
    """
    participants = frozenset(event.source_entity_ids) | frozenset(event.target_entity_ids)
    return frozenset(
        (key, value)
        for key, value in event.metadata
        if key in declared_keys and value not in participants
    )


class SharedIdentifierGenerator:
    """Propose every within-timeline pair sharing a declared, non-participant identifier."""

    generator_id = "shared_identifier"

    def status(self, context: GenerationContext) -> GeneratorStatus:
        """Runnable only when the pack declares both the keys and the weight."""
        parameters = context.parameters
        if parameters.shared_identifier_strength is None or not parameters.identifier_metadata_keys:
            return GeneratorStatus.NOT_RUNNABLE
        return GeneratorStatus.RAN

    def requirement(self) -> str:
        """Return what a pack must declare for this generator to run."""
        return (
            "candidate_generation.identifier_metadata_keys -- which Event.metadata keys "
            "carry a domain identifier rather than the Event Generator's traceability pairs "
            "-- and candidate_generation.shared_identifier_strength. Declaring no keys "
            "switches this generator off deliberately: on a dataset whose every identifier "
            "becomes a participant entity, there is nothing here the shared-entity "
            "generator does not already reach."
        )

    def propose(self, context: GenerationContext) -> tuple[Proposal, ...]:
        """Return one proposal per sequenced within-timeline pair sharing an identifier."""
        strength = context.parameters.shared_identifier_strength
        declared_keys = frozenset(context.parameters.identifier_metadata_keys)
        if strength is None or not declared_keys:
            return ()
        events_by_id = context.events_by_id()
        proposals: list[Proposal] = []
        seen: set[tuple[str, str]] = set()
        for timeline in context.timelines:
            held = events_of_timeline(timeline, events_by_id)
            for cause in held:
                cause_pairs = _identifier_pairs(cause, declared_keys)
                if not cause_pairs:
                    continue
                for effect in held:
                    if cause.event_id == effect.event_id:
                        continue
                    key = (cause.event_id, effect.event_id)
                    if key in seen:
                        continue
                    shared = tuple(sorted(cause_pairs & _identifier_pairs(effect, declared_keys)))
                    if not shared:
                        continue
                    seen.add(key)
                    rendered = ", ".join(f"{name}={value}" for name, value in shared)
                    proposals.append(
                        Proposal(
                            generator_id=self.generator_id,
                            cause_event=cause,
                            effect_event=effect,
                            payload=DirectCause(),
                            evidence=(
                                evidence_item(
                                    kind=EvidenceKind.SHARED_IDENTIFIER,
                                    description=(
                                        f"{cause.event_type} and {effect.event_type} carry "
                                        "the same non-participant identifier(s). This "
                                        "links two records. It does not establish that "
                                        "they concern one modelled entity, and it "
                                        "establishes no mechanism."
                                    ),
                                    verification=(
                                        "set(cause.metadata) & set(effect.metadata), "
                                        "restricted to the declared "
                                        f"identifier_metadata_keys {sorted(declared_keys)} "
                                        "and excluding values naming a participant of "
                                        f"either event, == [{rendered}]"
                                    ),
                                    supporting_ids=(cause.event_id, effect.event_id),
                                    strength=strength,
                                    provenance_class=ProvenanceClass.ASSUMED,
                                ),
                            ),
                        )
                    )
        return tuple(sorted(proposals, key=lambda item: item.sort_key()))
