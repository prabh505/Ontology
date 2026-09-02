"""Group events into candidate timeline instances, keyed by the ontology's own declarations.

Grouping is never by a hardcoded entity type or attribute name. A process instance's key is
whichever entity type the active `ProcessDefinitionSpec.anchor_entity_type` names; an entity
view's key is simply "this entity participated." Neither reads a domain vocabulary string.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from causalog.core.ontology_view import ProcessDefinitionView
from causalog.core.types import Entity, Event

__all__ = ["ProcessInstanceGroup", "group_by_entity", "group_by_process_instance"]


@dataclass(frozen=True)
class ProcessInstanceGroup:
    """One anchor entity's events, under one declared process definition."""

    process_definition: ProcessDefinitionView
    anchor_entity_id: str
    events: tuple[Event, ...]


def group_by_process_instance(
    events: tuple[Event, ...],
    entities: tuple[Entity, ...],
    process_definitions: tuple[ProcessDefinitionView, ...],
) -> tuple[ProcessInstanceGroup, ...]:
    """Group events by their participating anchor entity, per process definition.

    An event belongs to a process definition's instance set when one of its participants
    is an entity of the definition's declared `anchor_entity_type`. An event naming more
    than one entity of that type (unusual, but not forbidden) belongs to every such
    instance -- the group is a membership test, not a partition, and duplicating a shared
    event across instances is honest where silently picking one would not be.
    """
    entity_type_by_id = {entity.entity_id: entity.entity_type for entity in entities}
    groups: list[ProcessInstanceGroup] = []
    for process_definition in process_definitions:
        buckets: dict[str, list[Event]] = defaultdict(list)
        for event in events:
            participant_ids = event.source_entity_ids + event.target_entity_ids
            anchors = [
                entity_id
                for entity_id in participant_ids
                if entity_type_by_id.get(entity_id) == process_definition.anchor_entity_type
            ]
            for anchor_id in anchors:
                buckets[anchor_id].append(event)
        for anchor_id in sorted(buckets):
            groups.append(
                ProcessInstanceGroup(
                    process_definition=process_definition,
                    anchor_entity_id=anchor_id,
                    events=tuple(buckets[anchor_id]),
                )
            )
    return tuple(groups)


def group_by_entity(
    events: tuple[Event, ...], entities: tuple[Entity, ...]
) -> tuple[tuple[str, tuple[Event, ...]], ...]:
    """Group events by every entity that participates in at least one of them.

    No process definition is consulted -- this is raw observed participation, the
    grouping every `TimelineView.ENTITY` timeline is built from.
    """
    buckets: dict[str, list[Event]] = defaultdict(list)
    known_ids = {entity.entity_id for entity in entities}
    for event in events:
        for entity_id in event.source_entity_ids + event.target_entity_ids:
            if entity_id in known_ids:
                buckets[entity_id].append(event)
    return tuple((entity_id, tuple(buckets[entity_id])) for entity_id in sorted(buckets))
