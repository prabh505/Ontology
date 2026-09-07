"""Generator (d): the two events' participants are connected in the relationship graph.

Reaches pairs the shared-entity generator cannot: two occurrences concerning two DIFFERENT
entities that a declared structural relationship connects, within a declared hop bound.

**This generator produces nothing today, and that is a fact rather than a bug.**
`Relationship` is module 7's output and module 7 is not-started (`CONTEXT.md` §3), so
`GraphFacts.relationships()` returns an empty tuple and the BFS has no edges to walk. The
generator still RUNS and still reports -- `0 candidates over 0 relationships` -- because a
generator that is silently absent from the report is indistinguishable from one that ran
and found nothing, which is the distinction this whole module is built around.

`CAUSES` is never a relationship type (`core.types.relationship`), so nothing walked here
can be a causal edge smuggled in as a structural one.
"""

from __future__ import annotations

from collections import deque

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
from causalog.core.types import DirectCause, Event, EvidenceKind, Relationship

__all__ = ["StructuralPathGenerator"]


def _adjacency(relationships: tuple[Relationship, ...]) -> dict[str, tuple[tuple[str, str], ...]]:
    """Return an undirected adjacency map: entity -> ((neighbour, relationship_id), ...).

    Undirected because a structural connection is a connection whichever end it was
    authored from -- `BELONGS_TO` read backwards still says the two things are related.
    Direction of the CAUSAL claim is decided by the temporal gate and never by which way a
    structural edge was written.

    Every neighbour list is sorted, so the traversal below is deterministic
    (`CONVENTIONS.md` §11): an unsorted adjacency yields a different shortest path on two
    runs whenever two paths tie in length.
    """
    built: dict[str, list[tuple[str, str]]] = {}
    for relationship in relationships:
        built.setdefault(relationship.source_entity_id, []).append(
            (relationship.target_entity_id, relationship.relationship_id)
        )
        built.setdefault(relationship.target_entity_id, []).append(
            (relationship.source_entity_id, relationship.relationship_id)
        )
    return {key: tuple(sorted(value)) for key, value in sorted(built.items())}


def _shortest_path(
    adjacency: dict[str, tuple[tuple[str, str], ...]],
    starts: tuple[str, ...],
    goals: frozenset[str],
    max_hops: int,
) -> tuple[str, ...] | None:
    """Return the relationship identifiers of the shortest path within `max_hops`, or None.

    Breadth-first over a sorted adjacency from sorted starts, so the path returned is the
    same on every run. A path of length zero -- the two events already share an entity --
    returns None: that pair is the shared-entity generator's, and proposing it here too
    would double-count one linkage under two generators.
    """
    frontier: deque[tuple[str, tuple[str, ...]]] = deque((start, ()) for start in sorted(starts))
    visited: set[str] = set(starts)
    while frontier:
        entity, path = frontier.popleft()
        if len(path) >= max_hops:
            continue
        for neighbour, relationship_id in adjacency.get(entity, ()):
            if neighbour in visited:
                continue
            extended = (*path, relationship_id)
            if neighbour in goals:
                return extended
            visited.add(neighbour)
            frontier.append((neighbour, extended))
    return None


def _participants(event: Event) -> frozenset[str]:
    """Return every entity the event names, in either role."""
    return frozenset(event.source_entity_ids) | frozenset(event.target_entity_ids)


class StructuralPathGenerator:
    """Propose pairs whose participants are connected within the declared hop bound."""

    generator_id = "structural_path"

    def status(self, context: GenerationContext) -> GeneratorStatus:
        """Runnable only when the pack declares both a hop bound and a weight."""
        parameters = context.parameters
        if parameters.structural_max_hops is None or parameters.structural_path_strength is None:
            return GeneratorStatus.NOT_RUNNABLE
        return GeneratorStatus.RAN

    def requirement(self) -> str:
        """Return what a pack must declare for this generator to run."""
        return (
            "candidate_generation.structural_max_hops and "
            "candidate_generation.structural_path_strength. Note separately that this "
            "generator reads GraphFacts.relationships(), which is module 7's output; until "
            "module 7 exists it runs over an empty relationship set and reports zero."
        )

    def propose(self, context: GenerationContext) -> tuple[Proposal, ...]:
        """Return one proposal per within-timeline pair connected within the hop bound."""
        parameters = context.parameters
        max_hops = parameters.structural_max_hops
        strength = parameters.structural_path_strength
        if max_hops is None or strength is None:
            return ()
        relationships = context.facts.relationships()
        if not relationships:
            return ()
        adjacency = _adjacency(relationships)
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
                    effect_entities = _participants(effect)
                    if not effect_entities or cause_entities & effect_entities:
                        continue
                    path = _shortest_path(
                        adjacency, tuple(sorted(cause_entities)), effect_entities, max_hops
                    )
                    if path is None:
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
                                        f"{cause.event_type} and {effect.event_type} name "
                                        "no entity in common, but their participants are "
                                        f"connected through {len(path)} declared "
                                        "structural relationship(s). A structural "
                                        "connection establishes that the two occurrences "
                                        "are reachable from one another. It establishes "
                                        "no mechanism and no direction."
                                    ),
                                    verification=(
                                        "breadth-first search over "
                                        "GraphFacts.relationships(), treated as "
                                        "undirected, from the cause's participants to the "
                                        "effect's, bounded at "
                                        f"structural_max_hops={max_hops}; shortest path "
                                        f"traverses relationship ids {list(path)}"
                                    ),
                                    supporting_ids=(cause.event_id, effect.event_id, *path),
                                    strength=strength,
                                    provenance_class=ProvenanceClass.ASSUMED,
                                ),
                            ),
                        )
                    )
        return tuple(sorted(proposals, key=lambda item: item.sort_key()))
