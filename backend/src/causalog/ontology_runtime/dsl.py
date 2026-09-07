"""The domain-pack DSL: the normative, declarative description of a domain.

This module is the **single source of truth** for the pack schema (ADR-0026). The JSON
Schema published at `ontology/_schema/ontology.schema.json` is generated from these models
by `schema_export.py`, so the two cannot drift: a change here that is not exported fails
`scripts/export_ontology_schema.py --check`.

Every model is `frozen=True, extra="forbid"`, matching `causalog.core`. An undeclared key in
an authored pack is a hard error rather than a silently ignored line, because a typo in a
key name is otherwise indistinguishable from a deliberate omission.

**No pack may carry executable code.** There is no expression string, no callable
reference, and no plugin hook anywhere in this schema. A metric that cannot be written as a
`MeasurementExpression` needs a new operator and an ADR (ADR-0026), not an escape hatch.

LAW-DOMAIN applies to this file: it describes the *shape* of a domain description and may
never name a concept from any one domain.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalog.core.errors import ContractViolationError
from causalog.core.provenance import ProvenanceClass

__all__ = [
    "PACK_ID_PATTERN",
    "PACK_SCHEMA_VERSION",
    "ActionabilitySpec",
    "AttributeOrigin",
    "AttributeSemantics",
    "AttributeSpec",
    "AttributeType",
    "Cardinality",
    "ClassSpec",
    "DefaultConfidenceComponentSpec",
    "DefaultConfidenceSpec",
    "DerivationSpec",
    "DomainPack",
    "EntityTypeSpec",
    "EventCategorySpec",
    "EventTypeSpec",
    "ExpressionOperator",
    "ExternalEventTypeSpec",
    "ExternalStatus",
    "LifecycleSpec",
    "MeasurementDefinitionSpec",
    "MeasurementExpression",
    "MeasurementKind",
    "ObservationMode",
    "ParticipantSpec",
    "PostconditionSpec",
    "PreconditionSpec",
    "ProcessDefinitionSpec",
    "ProcessVariantSpec",
    "RelationshipTypeSpec",
    "RemovalSpec",
    "ResolvedPack",
    "TemporalValidity",
    "TransitionSpec",
]

#: The version of the DSL itself, not of any pack authored in it. A pack declaring a
#: different value is refused rather than best-effort parsed: a schema mismatch is a
#: migration, exactly as `core.serialization` treats a wire-format mismatch.
PACK_SCHEMA_VERSION: Final[str] = "1.2.0"

#: Type, category, state, and role names. Uppercase so a pack identifier is never confused
#: with an attribute name, which is lower snake case.
SYMBOL_PATTERN: Final[str] = r"^[A-Z][A-Z0-9_]*$"

#: Attribute names.
LOWER_SYMBOL_PATTERN: Final[str] = r"^[a-z][a-z0-9_]*$"

#: Pack identifiers. A leading underscore marks a pack that is not a domain -- the shared
#: base every domain overlay extends. Domains never carry one.
PACK_ID_PATTERN: Final[str] = r"^_?[a-z][a-z0-9_]*$"

#: Semantic version, exactly three numeric components.
SEMVER_PATTERN: Final[str] = r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"

_SEMVER_RE: Final[re.Pattern[str]] = re.compile(SEMVER_PATTERN)


class _Spec(BaseModel):
    """Base for every DSL node: immutable, closed, and alias-addressable."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class AttributeType(str, Enum):
    """The closed set of attribute value types a pack may declare."""

    STRING = "STRING"
    INTEGER = "INTEGER"
    DECIMAL = "DECIMAL"
    BOOLEAN = "BOOLEAN"
    INSTANT = "INSTANT"
    DURATION = "DURATION"
    ENUMERATION = "ENUMERATION"


class AttributeSemantics(str, Enum):
    """What an attribute *means* to the engine, independent of its storage type.

    The engine reads semantics, never names. `QUANTITY` and `MONETARY` are both `DECIMAL`
    and are treated differently by measurement roll-up; that distinction has to be
    declared, because no type system carries it.
    """

    IDENTIFIER = "IDENTIFIER"
    CATEGORICAL = "CATEGORICAL"
    QUANTITY = "QUANTITY"
    MONETARY = "MONETARY"
    RATIO = "RATIO"
    INSTANT = "INSTANT"
    DURATION = "DURATION"
    FLAG = "FLAG"
    FREE_TEXT = "FREE_TEXT"
    GEOSPATIAL = "GEOSPATIAL"


class AttributeOrigin(str, Enum):
    """Where an attribute's value comes from.

    This is the field that makes the traceability constraint mechanical rather than
    editorial: every attribute states whether a source column carries it, whether it is
    computed, or whether it is an assumption with no source behind it at all.
    """

    SOURCE_COLUMN = "SOURCE_COLUMN"
    DERIVED = "DERIVED"
    ASSUMED = "ASSUMED"


class Cardinality(str, Enum):
    """The multiplicity of a structural relationship."""

    ONE_TO_ONE = "ONE_TO_ONE"
    ONE_TO_MANY = "ONE_TO_MANY"
    MANY_TO_ONE = "MANY_TO_ONE"
    MANY_TO_MANY = "MANY_TO_MANY"


class TemporalValidity(str, Enum):
    """Whether a relationship holds for all time or only over an interval.

    `TIME_VARYING` tells the graph builder the edge needs a validity interval; `STATIC`
    tells it the edge does not. Guessing either way produces a graph that answers
    "what was true then" incorrectly.
    """

    STATIC = "STATIC"
    TIME_VARYING = "TIME_VARYING"


class ObservationMode(str, Enum):
    """Whether the source logs an event type directly, or the engine reconstructs it.

    `DERIVED` is the load-bearing member (ADR-0029). A source that records a field but
    never records the occurrence it implies produces a `DERIVED` event type, which must
    declare its basis and may never claim `OBSERVED` provenance.
    """

    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"


class ExternalStatus(str, Enum):
    """The lifecycle of an externally-sourced event type.

    Only one member exists on purpose. V1 declares external event types so the schema is
    future-proof and populates none of them; a second member is a feature, and features
    arrive through the PRD, not through an enum.
    """

    DECLARED_UNPOPULATED = "DECLARED_UNPOPULATED"


class MeasurementKind(str, Enum):
    """What a measurement measures. Read by ranking; never branched on by name."""

    DELAY = "DELAY"
    DURATION = "DURATION"
    COST = "COST"
    IMPACT = "IMPACT"
    COUNT = "COUNT"
    RATIO = "RATIO"
    QUANTITY = "QUANTITY"


class ExpressionOperator(str, Enum):
    """The closed operator set a measurement may be built from.

    Closed by design. The alternative -- an expression string evaluated at runtime -- is
    executable code inside a data file, which ADR-0026 refuses. A metric that needs an
    operator absent here needs the operator added, with an ADR, and every pack revalidated.
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


#: Operators taking exactly two operands.
BINARY_OPERATORS: Final[frozenset[ExpressionOperator]] = frozenset(
    {
        ExpressionOperator.DIFFERENCE,
        ExpressionOperator.RATIO,
        ExpressionOperator.DURATION_BETWEEN,
    }
)

#: Operators taking two or more operands.
VARIADIC_OPERATORS: Final[frozenset[ExpressionOperator]] = frozenset(
    {
        ExpressionOperator.SUM,
        ExpressionOperator.PRODUCT,
        ExpressionOperator.MINIMUM,
        ExpressionOperator.MAXIMUM,
    }
)


class EventCategorySpec(_Spec):
    """A pack-declared event category.

    Categories are data. The engine groups by whatever a pack declares and knows none of
    the names; a category set hardcoded anywhere in the engine would be one domain's
    vocabulary wearing a generic label.
    """

    id: str = Field(pattern=SYMBOL_PATTERN)
    description: str = Field(min_length=1)


class ClassSpec(_Spec):
    """One member of a pack-declared ordinal vocabulary (cost, severity or risk).

    `rank` carries the sequence so a ranker can compare two members without reading their
    names. Names are for humans; `rank` is for the engine.
    """

    id: str = Field(pattern=SYMBOL_PATTERN)
    description: str = Field(min_length=1)
    rank: int = Field(ge=0)


class AttributeSpec(_Spec):
    """One attribute of an entity type or event type, with its provenance of definition.

    Exactly one of `source_column`, `derivation_basis`, `assumption` is present, selected
    by `origin`. The three are kept as separate fields rather than one free-text note so
    that "which columns does this pack actually consume" is a query rather than a reading
    exercise.
    """

    name: str = Field(pattern=LOWER_SYMBOL_PATTERN)
    type: AttributeType
    semantics: AttributeSemantics
    description: str = Field(min_length=1)
    origin: AttributeOrigin
    source_column: str | None = None
    derivation_basis: str | None = None
    assumption: str | None = None
    enumeration_values: tuple[str, ...] = ()
    unit: str | None = None
    #: ADR-0067, pack schema 1.1.0, additive. Whether a hypothetical may set this attribute
    #: to something else. **The default refuses.** A pack authored against 1.0.0 declares no
    #: changeable attribute at all, which is ADR-0049's absent-means-CANNOT-RUN rule in the
    #: direction that withholds permission rather than granting it: a simulator asked to
    #: change an undeclared attribute reports which declaration it would have needed.
    #:
    #: Nothing validates the claim. `mutable: true` on an attribute no operator could really
    #: have set is a declaration that loads cleanly and is wrong (R-16).
    mutable: bool = False
    #: The DECLARED closed vocabulary a changed value must belong to. Distinct from
    #: `enumeration_values`, which describes what the SOURCE carries: a pack may admit a
    #: value for a hypothetical that no record ever held, and conflating the two would make
    #: every unwitnessed value inadmissible.
    admissible_values: tuple[str, ...] = ()
    #: The DECLARED inclusive numeric bound `(low, high)` a changed value must lie within.
    #: Not the observed range -- that is measured from a run and is what a support envelope
    #: compares against (ADR-0070). A value inside this bound and outside anything the data
    #: witnessed is possible and unsupported, which is the case an extrapolation verdict
    #: exists to name.
    admissible_range: tuple[float, float] | None = None

    @model_validator(mode="after")
    def _check_mutability(self) -> AttributeSpec:
        """Refuse a bound that admits nothing, and a bound on an unchangeable attribute."""
        if self.admissible_range is not None:
            low, high = self.admissible_range
            if low > high:
                raise ContractViolationError(
                    f"attribute '{self.name}' declares admissible_range ({low}, {high}), "
                    "whose low bound is above its high one. That range admits no value, so "
                    "every change would be refused and the declaration would read as though "
                    "it permitted one."
                )
        if not self.mutable and (self.admissible_values or self.admissible_range is not None):
            raise ContractViolationError(
                f"attribute '{self.name}' declares an admissible bound but is not marked "
                "mutable. A bound on a value nothing may set is a declaration with no "
                "consumer, and a pack author reading it would believe the attribute is a "
                "lever. Add 'mutable: true' or remove the bound."
            )
        if len(set(self.admissible_values)) != len(self.admissible_values):
            raise ContractViolationError(
                f"attribute '{self.name}' repeats a value in admissible_values; the "
                "vocabulary is a set and a repeat makes its canonical form ambiguous."
            )
        if list(self.admissible_values) != sorted(self.admissible_values):
            raise ContractViolationError(
                f"attribute '{self.name}' declares admissible_values out of canonical "
                "sequence; two packs differing only in authoring sequence must hash alike "
                "(CONVENTIONS.md §11)."
            )
        return self

    @model_validator(mode="after")
    def _check_origin_evidence(self) -> AttributeSpec:
        """Require exactly the origin field the declared origin calls for."""
        required: dict[AttributeOrigin, str] = {
            AttributeOrigin.SOURCE_COLUMN: "source_column",
            AttributeOrigin.DERIVED: "derivation_basis",
            AttributeOrigin.ASSUMED: "assumption",
        }
        expected = required[self.origin]
        for origin, field_name in required.items():
            value = getattr(self, field_name)
            if origin is self.origin and not (value and value.strip()):
                raise ContractViolationError(
                    f"attribute '{self.name}' declares origin {self.origin.value} and "
                    f"must supply a non-empty '{expected}'. An attribute whose origin is "
                    "unstated cannot be traced back to anything."
                )
            if origin is not self.origin and value is not None:
                raise ContractViolationError(
                    f"attribute '{self.name}' declares origin {self.origin.value} but also "
                    f"supplies '{field_name}'. Exactly one origin field is admissible; two "
                    "would let the pack claim two different provenances for one value."
                )
        if self.type is AttributeType.ENUMERATION and not self.enumeration_values:
            raise ContractViolationError(
                f"attribute '{self.name}' is ENUMERATION and declares no "
                "'enumeration_values'; an unbounded enumeration is a STRING."
            )
        if self.type is not AttributeType.ENUMERATION and self.enumeration_values:
            raise ContractViolationError(
                f"attribute '{self.name}' declares 'enumeration_values' but its type is "
                f"{self.type.value}; only ENUMERATION admits them."
            )
        if len(set(self.enumeration_values)) != len(self.enumeration_values):
            raise ContractViolationError(
                f"attribute '{self.name}' repeats an entry in 'enumeration_values'."
            )
        return self


class TransitionSpec(_Spec):
    """One legal state transition, and optionally the event type that effects it."""

    from_state: str = Field(alias="from", pattern=SYMBOL_PATTERN)
    to_state: str = Field(alias="to", pattern=SYMBOL_PATTERN)
    triggered_by: str | None = Field(default=None, pattern=SYMBOL_PATTERN)

    @model_validator(mode="after")
    def _check_not_self(self) -> TransitionSpec:
        """Refuse a transition from a state to itself."""
        if self.from_state == self.to_state:
            raise ContractViolationError(
                f"transition '{self.from_state}' -> '{self.to_state}' is a self-loop; a "
                "state machine that can transition to its current state cannot report "
                "that anything changed."
            )
        return self


class LifecycleSpec(_Spec):
    """The state machine an entity type moves through."""

    states: tuple[str, ...] = Field(min_length=1)
    initial_states: tuple[str, ...] = Field(min_length=1)
    terminal_states: tuple[str, ...] = ()
    transitions: tuple[TransitionSpec, ...] = ()


class EntityTypeSpec(_Spec):
    """A kind of thing the domain contains."""

    id: str = Field(pattern=SYMBOL_PATTERN)
    description: str = Field(min_length=1)
    identifying_keys: tuple[str, ...] = ()
    attributes: tuple[AttributeSpec, ...] = ()
    lifecycle: LifecycleSpec | None = None


class RelationshipTypeSpec(_Spec):
    """A structural, non-causal edge between two entity types.

    `CAUSES` is refused here by `structural.py`. `docs/contracts.md` §5 forbids it on
    `Relationship`, and a pack is the one place someone could reintroduce it as data.
    """

    id: str = Field(pattern=SYMBOL_PATTERN)
    description: str = Field(min_length=1)
    from_entity_type: str = Field(alias="from", pattern=SYMBOL_PATTERN)
    to_entity_type: str = Field(alias="to", pattern=SYMBOL_PATTERN)
    cardinality: Cardinality
    temporal_validity: TemporalValidity


class ParticipantSpec(_Spec):
    """An entity type an event type involves, under a named role.

    The role, not the entity type, is what preconditions and postconditions refer to. That
    indirection is what lets one event type involve two entities of the same type without
    the conditions becoming ambiguous.
    """

    role: str = Field(pattern=SYMBOL_PATTERN)
    entity_type: str = Field(pattern=SYMBOL_PATTERN)
    required: bool = True


class PreconditionSpec(_Spec):
    """A state a participant is expected to hold in before the event occurs."""

    role: str = Field(pattern=SYMBOL_PATTERN)
    state_in: tuple[str, ...] = Field(min_length=1)


class PostconditionSpec(_Spec):
    """The state a participant holds in after the event occurs."""

    role: str = Field(pattern=SYMBOL_PATTERN)
    state: str = Field(pattern=SYMBOL_PATTERN)


class DefaultConfidenceComponentSpec(_Spec):
    """One named component of a declared default confidence.

    Deliberately *not* a `core.types.ConfidenceComponent`: that type requires
    `evidence_record_ids`, and a pack has no evidence records -- they are minted when a
    record is read. A pack declares the names and weights; the event generator materializes
    the vector against real evidence.
    """

    component_name: str = Field(pattern=LOWER_SYMBOL_PATTERN)
    value: float = Field(ge=0.0, le=1.0)


class DefaultConfidenceSpec(_Spec):
    """The confidence a derived event type carries in the absence of anything better."""

    components: tuple[DefaultConfidenceComponentSpec, ...] = Field(min_length=1)
    aggregation: str = Field(min_length=1)
    provenance_class: ProvenanceClass

    @model_validator(mode="after")
    def _check_components(self) -> DefaultConfidenceSpec:
        """Require sorted, unique component names and a non-observed class."""
        names = [component.component_name for component in self.components]
        if names != sorted(names):
            raise ContractViolationError(
                "default_confidence.components must be sequenced by component_name "
                "(CONVENTIONS.md §11); an unsequenced vector serializes two ways."
            )
        if len(set(names)) != len(names):
            raise ContractViolationError(
                "default_confidence.components repeats a component_name; two values under "
                "one name have no defined combination."
            )
        if self.provenance_class is ProvenanceClass.OBSERVED:
            raise ContractViolationError(
                "default_confidence.provenance_class is OBSERVED; a confidence declared in "
                "a pack was never read from a source record (LAW-PROVENANCE)."
            )
        return self


class DerivationSpec(_Spec):
    """How a derived event type is reconstructed, and how sure the pack is about it."""

    basis: str = Field(min_length=1)
    source_columns: tuple[str, ...] = ()
    default_confidence: DefaultConfidenceSpec


class ActionabilitySpec(_Spec):
    """Whether an operator can act on an event type, at what cost, and at what risk.

    Root-cause ranking reads this (ADR-0008), which is why it is declared rather than
    inferred. `provenance_class` is pinned to `ASSUMED`: risk R-15 records that nothing in
    the system can validate an actionability claim, and labelling it anything stronger
    would hide that.

    `risk_class` arrives at pack schema 1.2.0 (ADR-0073) because prd.md §50 requires an
    operational risk on every recommendation and nothing in this repository declared one.
    It is OPTIONAL where `cost_class` is mandatory, and the asymmetry is deliberate: an
    actionable type with no cost would rank as free, which is a wrong number, whereas an
    actionable type with no risk ranks nowhere on that objective and is reported as
    `NOT_DECLARED`. ADR-0049's rule in the direction that refuses -- absent means the
    objective CANNOT RUN for this type, never that the risk is nil.
    """

    actionable: bool
    severity_class: str = Field(pattern=SYMBOL_PATTERN)
    cost_class: str | None = Field(default=None, pattern=SYMBOL_PATTERN)
    #: ADR-0073, pack schema 1.2.0, additive. Names a member of `risk_classes`. Absent is a
    #: legitimate state and is never read as "no risk"; see this class's docstring.
    risk_class: str | None = Field(default=None, pattern=SYMBOL_PATTERN)
    provenance_class: ProvenanceClass = ProvenanceClass.ASSUMED

    @model_validator(mode="after")
    def _check_cost_accompanies_actionability(self) -> ActionabilitySpec:
        """Require a cost class exactly when the event type is actionable."""
        if self.provenance_class is not ProvenanceClass.ASSUMED:
            raise ContractViolationError(
                "actionability.provenance_class must be ASSUMED; no observation in any "
                "dataset establishes that an operator can act on an event (risk R-15)."
            )
        if self.actionable and self.cost_class is None:
            raise ContractViolationError(
                "actionability declares actionable: true with no cost_class; intervention "
                "ranking multiplies impact by cost, and an absent cost would rank free."
            )
        if not self.actionable and self.cost_class is not None:
            raise ContractViolationError(
                "actionability declares actionable: false with a cost_class; a cost for an "
                "action nobody can take is a number with no referent."
            )
        if not self.actionable and self.risk_class is not None:
            raise ContractViolationError(
                "actionability declares actionable: false with a risk_class; the risk of "
                "taking an action nobody can take is a number with no referent (ADR-0073). "
                "An actionable type MAY omit risk_class -- that is reported as NOT_DECLARED "
                "rather than defaulted -- but a non-actionable type may not carry one."
            )
        return self


class EventTypeSpec(_Spec):
    """A kind of occurrence the domain produces."""

    id: str = Field(pattern=SYMBOL_PATTERN)
    description: str = Field(min_length=1)
    category: str = Field(pattern=SYMBOL_PATTERN)
    observation: ObservationMode
    provenance_class: ProvenanceClass
    participants: tuple[ParticipantSpec, ...] = Field(min_length=1)
    required_attributes: tuple[AttributeSpec, ...] = ()
    preconditions: tuple[PreconditionSpec, ...] = ()
    postconditions: tuple[PostconditionSpec, ...] = ()
    actionability: ActionabilitySpec
    derivation: DerivationSpec | None = None

    @model_validator(mode="after")
    def _check_derivation_matches_observation(self) -> EventTypeSpec:
        """Keep a reconstructed event type from presenting itself as a recorded one."""
        if self.observation is ObservationMode.DERIVED:
            if self.derivation is None:
                raise ContractViolationError(
                    f"event type '{self.id}' is DERIVED and declares no 'derivation'; a "
                    "reconstructed occurrence must state what it was reconstructed from "
                    "(ADR-0029)."
                )
            if self.provenance_class is ProvenanceClass.OBSERVED:
                raise ContractViolationError(
                    f"event type '{self.id}' is DERIVED and claims OBSERVED provenance. A "
                    "derived event never masquerades as an observed one (ADR-0029, "
                    "LAW-PROVENANCE)."
                )
        elif self.derivation is not None:
            raise ContractViolationError(
                f"event type '{self.id}' is OBSERVED and declares a 'derivation'; an "
                "occurrence the source records directly is not reconstructed from anything."
            )
        return self


class ExternalEventTypeSpec(_Spec):
    """An event type sourced outside the primary dataset, declared but not populated.

    Present so the schema does not have to change when an external feed arrives, and
    refused everywhere else by `structural.py` so declaring one does not accidentally ship
    a V1 feature (`CONTEXT.md` §10).
    """

    id: str = Field(pattern=SYMBOL_PATTERN)
    description: str = Field(min_length=1)
    category: str = Field(pattern=SYMBOL_PATTERN)
    status: ExternalStatus
    prospective_participants: tuple[ParticipantSpec, ...] = ()
    note: str = Field(min_length=1)


class ProcessVariantSpec(_Spec):
    """An admissible departure from a canonical sequence."""

    id: str = Field(pattern=SYMBOL_PATTERN)
    description: str = Field(min_length=1)
    sequence: tuple[str, ...] = Field(min_length=1)


class ProcessDefinitionSpec(_Spec):
    """A named canonical flow: the expected happy-path sequence of event types.

    The timeline builder groups against this and the rule engine reasons against it. It is
    an *expectation*, never a constraint: a run that departs from it produces a finding,
    not a rejected record.
    """

    id: str = Field(pattern=SYMBOL_PATTERN)
    description: str = Field(min_length=1)
    anchor_entity_type: str = Field(pattern=SYMBOL_PATTERN)
    canonical_sequence: tuple[str, ...] = Field(min_length=2)
    variants: tuple[ProcessVariantSpec, ...] = ()
    optional_steps: tuple[str, ...] = ()
    repeatable_steps: tuple[str, ...] = ()


class MeasurementExpression(_Spec):
    """One node of a measurement's operator tree.

    Recursive, closed, and inert. Nothing here is evaluated by this module -- the tree is
    data that a downstream module walks. That is the whole point: a formula expressed as a
    tree can be inspected, diffed, and hashed; a formula expressed as a string has to be
    executed before anyone knows what it says.
    """

    op: ExpressionOperator
    event_type: str | None = Field(default=None, pattern=SYMBOL_PATTERN)
    attribute: str | None = Field(default=None, pattern=LOWER_SYMBOL_PATTERN)
    value: float | None = None
    operands: tuple[MeasurementExpression, ...] = ()

    @model_validator(mode="after")
    def _check_arity(self) -> MeasurementExpression:
        """Enforce the arity and leaf shape each operator admits."""
        if self.op is ExpressionOperator.CONSTANT:
            if self.value is None or self.operands or self.event_type or self.attribute:
                raise ContractViolationError(
                    "a CONSTANT expression carries 'value' alone -- no operands, no "
                    "'event_type', no 'attribute'."
                )
            return self
        if self.op is ExpressionOperator.ATTRIBUTE:
            if not (self.event_type and self.attribute) or self.operands or self.value is not None:
                raise ContractViolationError(
                    "an ATTRIBUTE expression carries 'event_type' and 'attribute' alone -- "
                    "no operands and no 'value'."
                )
            return self
        if self.value is not None or self.event_type or self.attribute:
            raise ContractViolationError(
                f"a {self.op.value} expression is an operator node and carries only "
                "'operands'; leaf fields belong on CONSTANT and ATTRIBUTE nodes."
            )
        if self.op in BINARY_OPERATORS and len(self.operands) != 2:
            raise ContractViolationError(
                f"a {self.op.value} expression takes exactly two operands; it was given "
                f"{len(self.operands)}."
            )
        if self.op in VARIADIC_OPERATORS and len(self.operands) < 2:
            raise ContractViolationError(
                f"a {self.op.value} expression takes two or more operands; it was given "
                f"{len(self.operands)}."
            )
        return self


class MeasurementDefinitionSpec(_Spec):
    """How one domain metric is computed from event attributes.

    Every metric the engine reports is defined here. A formula written into a reasoning
    module instead would be domain logic in the engine, which is the thing LAW-DOMAIN
    exists to prevent.
    """

    id: str = Field(pattern=SYMBOL_PATTERN)
    description: str = Field(min_length=1)
    kind: MeasurementKind
    unit: str = Field(min_length=1)
    provenance_class: ProvenanceClass
    expression: MeasurementExpression


class RemovalSpec(_Spec):
    """Identifiers an overlay withdraws from the pack it extends.

    Removal is explicit and per-identifier. An overlay cannot drop an inherited declaration
    by omitting it, because omission is indistinguishable from not having thought about it.
    """

    event_categories: tuple[str, ...] = ()
    cost_classes: tuple[str, ...] = ()
    severity_classes: tuple[str, ...] = ()
    risk_classes: tuple[str, ...] = ()
    entity_types: tuple[str, ...] = ()
    relationship_types: tuple[str, ...] = ()
    event_types: tuple[str, ...] = ()
    external_event_types: tuple[str, ...] = ()
    process_definitions: tuple[str, ...] = ()
    measurement_definitions: tuple[str, ...] = ()


class _PackBody(_Spec):
    """The declaration namespaces shared by an authored pack and a resolved one."""

    event_categories: tuple[EventCategorySpec, ...] = ()
    cost_classes: tuple[ClassSpec, ...] = ()
    severity_classes: tuple[ClassSpec, ...] = ()
    #: ADR-0073, pack schema 1.2.0, additive. An empty vocabulary is a pack that declares
    #: no operational risk at all; every consumer reports NOT_DECLARED and never defaults.
    risk_classes: tuple[ClassSpec, ...] = ()
    entity_types: tuple[EntityTypeSpec, ...] = ()
    relationship_types: tuple[RelationshipTypeSpec, ...] = ()
    event_types: tuple[EventTypeSpec, ...] = ()
    external_event_types: tuple[ExternalEventTypeSpec, ...] = ()
    process_definitions: tuple[ProcessDefinitionSpec, ...] = ()
    measurement_definitions: tuple[MeasurementDefinitionSpec, ...] = ()


class DomainPack(_PackBody):
    """One authored `ontology.yaml`, exactly as written, before resolution.

    `extends` and `removes` are authoring instructions rather than domain facts, which is
    why they exist here and not on `ResolvedPack`: once resolution has run there is no
    inheritance left to describe, and a hash computed over a pack that still remembered how
    it was assembled would differ from an identical pack written out in full.
    """

    pack_schema_version: str = Field(pattern=SEMVER_PATTERN)
    pack_id: str = Field(pattern=PACK_ID_PATTERN)
    ontology_version: str = Field(pattern=SEMVER_PATTERN)
    description: str = Field(min_length=1)
    extends: str | None = Field(default=None, pattern=PACK_ID_PATTERN)
    removes: RemovalSpec | None = None

    @model_validator(mode="after")
    def _check_schema_version(self) -> DomainPack:
        """Refuse a pack authored against a different DSL version."""
        if self.pack_schema_version != PACK_SCHEMA_VERSION:
            raise ContractViolationError(
                f"pack '{self.pack_id}' declares pack_schema_version "
                f"{self.pack_schema_version!r}; this engine reads {PACK_SCHEMA_VERSION!r}. "
                "A version mismatch is a migration, never a best-effort parse."
            )
        if self.removes is not None and self.extends is None:
            raise ContractViolationError(
                f"pack '{self.pack_id}' declares 'removes' without 'extends'; there is "
                "nothing to withdraw from."
            )
        return self


class ResolvedPack(_PackBody):
    """A pack with its inheritance chain applied and every namespace canonically sequenced.

    This is what the engine reads and what `ontology_hash` addresses. Two packs that resolve
    to the same declarations hash identically however they were authored -- which is the
    property that makes the hash a statement about semantics rather than about formatting.
    """

    pack_schema_version: str = Field(pattern=SEMVER_PATTERN)
    pack_id: str = Field(pattern=PACK_ID_PATTERN)
    ontology_version: str = Field(pattern=SEMVER_PATTERN)
    description: str = Field(min_length=1)
    lineage: tuple[str, ...] = ()


def is_semantic_version(text: str) -> bool:
    """Return whether `text` is a three-component semantic version."""
    return _SEMVER_RE.match(text) is not None
