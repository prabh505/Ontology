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
    "ActionabilityView",
    "AttributeView",
    "DurationExpressionOperator",
    "DurationExpressionView",
    "DurationMeasurementView",
    "EntityTypeView",
    "EventTypeView",
    "LifecycleTransitionView",
    "LifecycleView",
    "MagnitudeMeasurementView",
    "MeasurementExpressionOperator",
    "MeasurementExpressionView",
    "MeasurementKindView",
    "MutabilityView",
    "OrdinalClassView",
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
# Magnitude views (ADR-0056).
#
# `DurationExpressionOperator` above is a deliberate SUBSET -- the operators a duration
# measurement uses -- and it omits `PRODUCT` and `RATIO`. Propagation-weight attribution
# needs the whole closed set and the whole kind set, because the quantity being apportioned
# may be an `IMPACT`, a `COST` or a `QUANTITY` as easily as a `DELAY`. These are the full
# mirrors, added beside the duration ones rather than by widening them: widening
# `DurationExpressionOperator` would let a duration measurement declare a `RATIO` that
# `state_engine`'s evaluator refuses, and the refusal would arrive at evaluation time
# instead of at load time.
#
# The two enums MUST stay in step -- `DurationExpressionOperator` is a subset of
# `MeasurementExpressionOperator`, never a divergent set. `core.measurement` walks both
# structurally and cannot check that at type level, so it is checked by a test
# (`tests/unit/core/test_measurement.py`), as ADR-0056 states.
# ---------------------------------------------------------------------------


class MeasurementExpressionOperator(str, Enum):
    """The whole closed operator set of `ontology_runtime.dsl.ExpressionOperator`.

    A mirror, not a re-export -- no package below `extraction` may import the DSL enum
    (forbidden edge F3). Closed for the reason the DSL's is closed: the alternative is an
    expression string evaluated at runtime, which is executable code inside a data file.
    """

    CONSTANT = "CONSTANT"
    ATTRIBUTE = "ATTRIBUTE"
    SUM = "SUM"
    DIFFERENCE = "DIFFERENCE"
    PRODUCT = "PRODUCT"
    RATIO = "RATIO"
    DURATION_BETWEEN = "DURATION_BETWEEN"
    MINIMUM = "MINIMUM"
    MAXIMUM = "MAXIMUM"


class MeasurementKindView(str, Enum):
    """What a measurement measures. Read by attribution; never branched on by name."""

    DELAY = "DELAY"
    DURATION = "DURATION"
    COST = "COST"
    IMPACT = "IMPACT"
    COUNT = "COUNT"
    RATIO = "RATIO"
    QUANTITY = "QUANTITY"


class MeasurementExpressionView(BaseModel):
    """One node of any measurement's operator tree, mirroring `MeasurementExpression`.

    Field-identical to `DurationExpressionView` apart from the operator enum, and that is
    deliberate: `core.measurement` walks either one through the same structural protocol,
    so the two never need converting into each other.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    op: MeasurementExpressionOperator
    event_type: str | None = None
    attribute: str | None = None
    value: float | None = None
    operands: tuple[MeasurementExpressionView, ...] = ()


class MagnitudeMeasurementView(BaseModel):
    """One pack-declared measurement of any kind, with the kind kept beside the tree.

    `kind` is carried because a propagation weight apportions a magnitude and the unit of
    that magnitude changes what a share of it means -- a share of a `DELAY` in days and a
    share of an `IMPACT` in currency are both shares, and a report that printed them
    without saying which would be printing two things under one heading.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: MeasurementKindView
    unit: str
    expression: MeasurementExpressionView


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


# ---------------------------------------------------------------------------
# Actionability views (ADR-0008's criterion, transported the ADR-0056 way).
#
# `Event.is_actionable` already carries the BOOLEAN to `L6`, stamped at generation time so
# that the Root Cause Analyzer never reads the ontology (forbidden edge F3). A boolean is
# enough to FILTER on and not enough to RANK on: prd.md §29 asks which actionable event to
# change, and two actionable events differ in what changing them costs, in how bad the
# thing being changed is, and -- since ADR-0073 -- in what TAKING the action risks. Those
# facts are declared per event type in the pack, carry integer ranks in the pack's shared
# vocabularies, and today stop at `ontology_runtime`.
#
# They arrive here as flattened views rather than as new fields on `Event`, for the reason
# ADR-0056 gave for the magnitude views: `Event` is frozen and is the most-consumed type in
# the system, and an adapter-produced view costs no change to a frozen contract.
#
# NOTHING BELOW MAKES AN ACTIONABILITY CLAIM TRUE. `CONTEXT.md` R-15 records that a
# mis-declared flag silently changes the headline ranking and that nothing in this system
# can detect it. Carrying the declaration further does not validate it, and every consumer
# is required to say so beside the ranking it produces.
# ---------------------------------------------------------------------------


class OrdinalClassView(BaseModel):
    """One member of a pack-declared ordinal vocabulary: a name and its rank.

    Names are for humans; `rank` is for the engine. A consumer compares ranks and never
    reads a name, so a pack may rename a class without changing any sequencing, and may not
    change a sequencing without changing a rank.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    rank: int


class ActionabilityView(BaseModel):
    """What one event type's declaration says about acting on it.

    `actionable` duplicates what `Event.is_actionable` already carries, deliberately: a
    consumer holding only this view can answer the whole question without also holding the
    events, and a consumer holding both can check the two agree. `cost_class` and
    `severity_class` name members of the pack's ordinal vocabularies and are resolved to
    ranks by the consumer, not here -- resolving them here would require this view to hold
    the vocabularies too, and a view that carries its own lookup table is a store.

    `cost_class` is present exactly when `actionable` is true. That is the pack schema's
    own invariant, restated here rather than assumed: a cost for an action nobody can take
    is a number with no referent, and an absent cost on an actionable type would rank that
    type as free.

    `risk_class` (ADR-0073) is NOT under that invariant and the asymmetry is the point. It
    may be absent on an actionable type, and absent means the risk objective CANNOT RUN for
    that type -- reported as `NOT_DECLARED` and ranked nowhere. It is never read as
    `NEGLIGIBLE`. An absent cost would rank a type as free, which is a wrong number; an
    absent risk ranks it nowhere, which is a true statement about the pack.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_type: str
    actionable: bool
    cost_class: str | None = None
    severity_class: str
    #: ADR-0073. Names a member of the pack's risk vocabulary, resolved to a rank by the
    #: consumer. `None` is a legitimate state, not a lookup miss to be worked around.
    risk_class: str | None = None


# ---------------------------------------------------------------------------
# ADR-0067: which attributes a hypothetical may change.
#
# Whether an attribute is something an operator could have set differently is a claim about
# the DOMAIN, not about the engine. Deriving it here -- say, by treating anything outside an
# event's content address as changeable -- would be an unfalsifiable domain judgement written
# into reasoning code, which is the R-16 shape and the exact thing LAW-DOMAIN exists to stop.
#
# NOTHING BELOW MAKES A MUTABILITY CLAIM TRUE. `mutable: true` on an attribute no operator
# could really have set is a declaration that validates cleanly and is wrong, and no procedure
# in this repository can check it. R-16 covers it; every consumer says so.
# ---------------------------------------------------------------------------


class AttributeView(BaseModel):
    """One declared attribute, with enough shape to check a proposed value against it.

    `EventTypeView.required_attributes` carries names alone, which is all a validator needed
    while nothing proposed to CHANGE one. It is a frozen `core` type with consumers, so this
    lands beside it rather than widening it (ADR-0056 and ADR-0062 set the precedent).

    `admissible_values` and `admissible_range` are the DECLARED bound -- what the domain says
    is possible. They are not the observed range, which is measured from a run and is what a
    support envelope compares against (ADR-0070). The two are kept apart because a value can
    be entirely possible and entirely outside anything the data witnessed, and that is
    precisely the case an extrapolation verdict exists to name; collapsing them would hide it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    #: The declared type name, as a plain string. Not an enum here: the DSL's `AttributeType`
    #: lives at L1 and mirroring it would put two copies of a closed set in two layers, which
    #: is the divergence `check_law_copies.py` exists to catch one level up.
    type_name: str
    unit: str | None = None
    #: Empty when the attribute declares no closed vocabulary. Sorted, so two adapters over
    #: one pack produce one value (`CONVENTIONS.md` §11).
    admissible_values: tuple[str, ...] = ()
    #: Inclusive `(low, high)`, or `None` when the pack declares no numeric bound.
    admissible_range: tuple[float, float] | None = None


class MutabilityView(BaseModel):
    """The attributes of one event type that a pack declares a hypothetical may change.

    **An absent declaration means no attribute of that type may be changed**, never that
    every attribute may be -- ADR-0049's absent-means-CANNOT-RUN rule, in the direction that
    refuses. A consumer that finds no view for an event type reports which declaration it
    would have needed and simulates nothing, rather than defaulting to permission.

    `mutable_attributes` is sorted by name and its members are unique, so the view is
    canonical and a digest over it is stable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_type: str
    mutable_attributes: tuple[AttributeView, ...] = ()

    def attribute(self, name: str) -> AttributeView | None:
        """Return the declared changeable attribute of that name, or None if it declares none.

        `None` is the refusal, not a lookup miss to be worked around: the caller turns it into
        a rejection naming the declaration that would have admitted the change.
        """
        for candidate in self.mutable_attributes:
            if candidate.name == name:
                return candidate
        return None
