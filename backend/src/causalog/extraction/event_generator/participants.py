"""Resolve which entities take part in an emitted event, and in which direction.

Entirely pack-driven. `ParticipantSpec` declares role -> entity type; the mapping declares
exactly one identifying key per entity type; so a record that supplies that key determines
the participant. Nothing is declared twice, which is why an emission rule says nothing about
participants: a second declaration would be a second place for the two to disagree.

Source and target, and why the rule is the postconditions
---------------------------------------------------------
`Event` carries `source_entity_ids` and `target_entity_ids` and the contract does not define
which is which, so this module has to, and the choice has to come from data rather than from
a convention nobody can move when the ontology changes.

**A role the event type's postconditions name is a source; every other role is a target.**
A postcondition is the pack saying "this event leaves this participant in this state" -- it
is the declaration of what the event happened TO. An event type declaring no postconditions
falls back to `required` for the same reason: a participant the event cannot exist without
is what it is about, and an optional one is context.

This is a labelling decision, not a causal one. Neither field may be read as a cause: a
cause is an inferred edge between two events (ADR-0020), and it is created three layers
above this one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from causalog.core.types.entity import Entity
from causalog.ingestion.schema_mapper.apply import RecordView
from causalog.ontology_runtime.dsl import EventTypeSpec

__all__ = ["ParticipantPlan", "Participants", "ResolvedParticipants"]


@dataclass(frozen=True)
class ParticipantPlan:
    """One event type's role assignment, computed once from the pack."""

    event_type: str
    source_types: tuple[str, ...]
    target_types: tuple[str, ...]
    required_types: frozenset[str]

    @classmethod
    def build(cls, spec: EventTypeSpec) -> ParticipantPlan:
        """Derive the plan from one event type's participants and postconditions."""
        changed_roles = {condition.role for condition in spec.postconditions}
        if not changed_roles:
            changed_roles = {item.role for item in spec.participants if item.required}
        sources = sorted(
            {item.entity_type for item in spec.participants if item.role in changed_roles}
        )
        targets = sorted(
            {item.entity_type for item in spec.participants if item.role not in changed_roles}
            - set(sources)
        )
        return cls(
            event_type=spec.id,
            source_types=tuple(sources),
            target_types=tuple(targets),
            required_types=frozenset(
                item.entity_type for item in spec.participants if item.required
            ),
        )


@dataclass(frozen=True)
class ResolvedParticipants:
    """The identifiers one record supplies for one event type's roles."""

    source_entity_ids: tuple[str, ...]
    target_entity_ids: tuple[str, ...]
    missing_required: tuple[str, ...]
    """Entity types a required role names and this record supplies no key for. A rule whose
    condition held but whose required participant is absent produces NO event; the count
    reaches the quality report rather than an exception, because a record that describes a
    participant it does not name is a data-quality fact about the source, not a defect in
    this module."""
    unresolved: tuple[str, ...]
    """Identifiers that no extracted entity carries. An event built on one would be an
    ORPHAN -- it names a participant nothing in the store describes."""

    @property
    def entity_ids(self) -> tuple[str, ...]:
        """Return every participant identifier, sequenced, for the content address."""
        return tuple(sorted(set(self.source_entity_ids) | set(self.target_entity_ids)))

    @property
    def is_orphan(self) -> bool:
        """Return whether this event would name a participant nothing describes."""
        return bool(self.unresolved) or not self.entity_ids


@dataclass
class Participants:
    """Resolve participants for every event type under one ontology hash."""

    ontology_hash: str
    plans: dict[str, ParticipantPlan] = field(default_factory=dict)

    def resolve(
        self, record: RecordView, event_type: str, known: frozenset[str]
    ) -> ResolvedParticipants:
        """Return the participants one record supplies for one event type."""
        plan = self.plans[event_type]
        sources, missing_source = self._identifiers(record, plan.source_types, plan)
        targets, missing_target = self._identifiers(record, plan.target_types, plan)
        found = set(sources) | set(targets)
        return ResolvedParticipants(
            source_entity_ids=sources,
            target_entity_ids=targets,
            missing_required=tuple(sorted(set(missing_source) | set(missing_target))),
            unresolved=tuple(sorted(item for item in found if item not in known)),
        )

    def _identifiers(
        self, record: RecordView, entity_types: tuple[str, ...], plan: ParticipantPlan
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Return the resolvable identifiers, and the required types that were absent."""
        resolved: list[str] = []
        missing: list[str] = []
        for entity_type in entity_types:
            natural_key = record.natural_key(entity_type)
            if natural_key is None:
                if entity_type in plan.required_types:
                    missing.append(entity_type)
                continue
            resolved.append(Entity.address(self.ontology_hash, entity_type, natural_key))
        return tuple(sorted(set(resolved))), tuple(missing)
