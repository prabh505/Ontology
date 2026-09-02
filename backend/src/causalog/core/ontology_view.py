"""Plain, ontology-runtime-independent views of ontology-declared configuration.

`graph_engine` may never import `ontology_runtime` (LAW-DOMAIN, ADR-0002, forbidden edge
F3, `scripts/check_layers.py`) -- only `ingestion`, `extraction`, and `orchestration` may
consume it directly. These types are the shape Timeline Builder and State Engine read
instead: plain data, produced by an adapter living in a package that IS permitted to import
`ontology_runtime` (see `causalog.extraction.ontology_adapters`), and consumed here at `L0`
where every layer may import from.

This is the same pattern `causalog.core.types.entity.Lifecycle` already establishes for
Entity Extractor: a core type that is the runtime materialization of an ontology-declared
shape, kept separate from the DSL model that validated it.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

__all__ = [
    "DurationExpressionOperator",
    "DurationExpressionView",
    "DurationMeasurementView",
    "EntityTypeView",
    "EventTypeView",
    "LifecycleTransitionView",
    "LifecycleView",
    "ParticipantView",
    "ProcessDefinitionView",
    "ProcessVariantView",
    "RelationshipTypeView",
    "VocabularyView",
]


class ProcessVariantView(BaseModel):
    """A named, admissible departure from a canonical sequence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    sequence: tuple[str, ...]


class ProcessDefinitionView(BaseModel):
    """The declared canonical flow `graph_engine.timeline_builder` groups against."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    anchor_entity_type: str
    canonical_sequence: tuple[str, ...]
    variants: tuple[ProcessVariantView, ...] = ()
    optional_steps: tuple[str, ...] = ()
    repeatable_steps: tuple[str, ...] = ()


class LifecycleTransitionView(BaseModel):
    """One legal transition, and the event type that effects it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_state: str
    to_state: str
    triggered_by: str


class LifecycleView(BaseModel):
    """One entity type's declared state machine, indexed by triggering event type."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_type: str
    initial_states: tuple[str, ...]
    transitions: tuple[LifecycleTransitionView, ...]


class DurationExpressionOperator(str, Enum):
    """The subset of `ontology_runtime.dsl.ExpressionOperator` a duration measurement uses.

    A mirror, not a re-export -- `graph_engine` may not import the DSL enum directly.
    """

    CONSTANT = "CONSTANT"
    ATTRIBUTE = "ATTRIBUTE"
    SUM = "SUM"
    DIFFERENCE = "DIFFERENCE"
    DURATION_BETWEEN = "DURATION_BETWEEN"
    MINIMUM = "MINIMUM"
    MAXIMUM = "MAXIMUM"


class DurationExpressionView(BaseModel):
    """One node of a measurement's operator tree, mirroring `MeasurementExpression`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    op: DurationExpressionOperator
    event_type: str | None = None
    attribute: str | None = None
    value: float | None = None
    operands: tuple[DurationExpressionView, ...] = ()


class DurationMeasurementView(BaseModel):
    """One pack-declared `DURATION`/`DELAY` measurement."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    unit: str
    expression: DurationExpressionView


# ---------------------------------------------------------------------------
# Vocabulary views (ADR-0046).
#
# `rule_engine` is L5 and forbidden edge F3 blocks it from importing
# `ontology_runtime` -- so it cannot ask the pack whether a name a rule uses was ever
# declared. These views are the shape it reads instead, produced by the same adapter that
# already produces the process and lifecycle views above.
#
# WHAT THEY DELIBERATELY OMIT, stated here rather than discovered: attribute types, units,
# semantics, origins, pre/postconditions, actionability, observation mode, and every
# derivation basis. A validator holding one of these can check that a name EXISTS and that
# a role BELONGS to an event type. It cannot check that a comparison is type-correct or
# that a condition is meaningful. A projection that omits a field cannot validate against
# it, and pretending otherwise is how a green check comes to mean less than a reader thinks.
# ---------------------------------------------------------------------------


class ParticipantView(BaseModel):
    """One role an event type declares, and the entity type that fills it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: str
    entity_type: str
    required: bool


class EventTypeView(BaseModel):
    """One declared event type: its roles, and the attributes it guarantees to carry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    participants: tuple[ParticipantView, ...]
    required_attributes: tuple[str, ...]

    def participant(self, role: str) -> ParticipantView | None:
        """Return the declared participant filling `role`, or None if it declares none."""
        for candidate in self.participants:
            if candidate.role == role:
                return candidate
        return None


class EntityTypeView(BaseModel):
    """One declared entity type: the states it may hold and the attributes it may carry.

    `state_names` is empty for a type with no declared lifecycle. That is a legitimate
    declaration -- a reference type that never changes condition -- and is not the same as
    a type whose lifecycle failed to load, which is an error the pack loader raises.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    state_names: tuple[str, ...]
    terminal_state_names: tuple[str, ...]
    attribute_names: tuple[str, ...]


class RelationshipTypeView(BaseModel):
    """One declared structural relationship type and the two ends it connects."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    from_entity_type: str
    to_entity_type: str


class VocabularyView(BaseModel):
    """Every name a pack declares, with enough structure to check a reference against it.

    Every collection is sorted by `id`, so two adapters over one pack produce one value and
    a hash over it is stable (`CONVENTIONS.md` §11).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_types: tuple[EventTypeView, ...]
    entity_types: tuple[EntityTypeView, ...]
    relationship_types: tuple[RelationshipTypeView, ...]

    def event_type(self, identifier: str) -> EventTypeView | None:
        """Return the declared event type with this identifier, or None."""
        for candidate in self.event_types:
            if candidate.id == identifier:
                return candidate
        return None

    def entity_type(self, identifier: str) -> EntityTypeView | None:
        """Return the declared entity type with this identifier, or None."""
        for candidate in self.entity_types:
            if candidate.id == identifier:
                return candidate
        return None

    def relationship_type(self, identifier: str) -> RelationshipTypeView | None:
        """Return the declared relationship type with this identifier, or None."""
        for candidate in self.relationship_types:
            if candidate.id == identifier:
                return candidate
        return None
