"""The rule DSL: rules are DATA (prd.md §46, ADR-0044).

These pydantic models are **normative**, exactly as `causalog.ontology_runtime.dsl` is
normative for a domain pack and `causalog.ingestion.schema_mapper.dsl` for a mapping. A pack
file is one YAML document validated against them.

**Forbidden, and enforced by the absence of any field that could carry it:** there is no
expression string, no callable reference, no import path, no plugin hook, and no `eval`
anywhere in this schema. A condition that cannot be written as a closed operator tree needs a
new operator and an ADR, never an escape hatch. A pack with an escape hatch is executable
code, which is precisely what prd.md §46 forbids.

**This module contains no domain vocabulary.** Every name a rule uses -- the types it
matches, the roles it binds, the attributes it reads -- is a string supplied by the pack and
checked against a `VocabularyView` (ADR-0046). Nothing here branches on the value of one
(LAW-DOMAIN, ADR-0002).

Why this does not reuse `schema_mapper.dsl.ConditionExpression`
--------------------------------------------------------------
That import would be a legal downward edge (L5 -> L2) and was rejected in ADR-0044. Its
addresses are `CONCEPT.attribute` over *records* -- a mapping question, answered before any
event exists. A rule condition addresses a **role-bound participant of a matched event**,
which is a different address space. Sharing one type would force it to carry an address form
one of the two evaluators cannot resolve, and the first divergence would surface as a silent
mis-evaluation rather than as a type error.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalog.core.errors import ContractViolationError
from causalog.core.scalarization import OBJECTIVES

__all__ = [
    "COMPARISON_OPERATORS",
    "JUNCTION_OPERATORS",
    "OBJECTIVES",
    "PRESENCE_OPERATORS",
    "RULE_PACK_SCHEMA_VERSION",
    "AmplificationBody",
    "CandidateGenerationSpec",
    "CausalBody",
    "CompetingEffectPolicy",
    "ConditionExpression",
    "ConditionOperator",
    "ConfidenceBandSpec",
    "ConfidenceScoringSpec",
    "ConstraintBody",
    "CounterfactualSimulationSpec",
    "EntityRelation",
    "EventPattern",
    "GraphConstructionSpec",
    "ImpactAggregationSpec",
    "InhibitionBody",
    "JointBody",
    "KnowledgeProvenance",
    "MagnitudeAttributionSpec",
    "ModifierBody",
    "ObjectiveWeightSpec",
    "PatternMiningSpec",
    "PromotionThresholdSpec",
    "PropagationAnalysisSpec",
    "ProximityWindowSpec",
    "RecommendationSpec",
    "RelationDirection",
    "RoleAddress",
    "RootCauseAnalysisSpec",
    "Rule",
    "RuleBody",
    "RuleKind",
    "RulePackSpec",
    "TemporalWindow",
    "WeightNormalization",
]

#: The version of THIS schema, not of any pack authored against it. A pack states the
#: version it was written for and the loader refuses a mismatch, so a pack written against
#: an older DSL cannot be silently reinterpreted under a newer one.
RULE_PACK_SCHEMA_VERSION: Final[str] = "1.7.0"

#: Identifiers are upper snake case, matching the ontology pack's `SYMBOL_PATTERN`, so a
#: rule cannot name a type in a case the pack never declared.
SYMBOL_PATTERN: Final[str] = r"^[A-Z][A-Z0-9_]*$"

#: Rule identifiers admit a hyphen, because `R-DCO-0007` reads better in a trace than
#: `R_DCO_0007` and a rule identifier is never a Python name.
RULE_ID_PATTERN: Final[str] = r"^[A-Z][A-Z0-9_-]*$"

#: Attribute names are lower snake case, matching `AttributeSpec.name` in the pack DSL.
ATTRIBUTE_PATTERN: Final[str] = r"^[a-z][a-z0-9_]*$"


class _Spec(BaseModel):
    """Every node of the DSL: frozen, and refusing a field the schema does not declare.

    `extra="forbid"` is the load-bearing half. A typo in a pack key is a hard error naming
    the key, never a silently ignored line that leaves a rule doing something other than
    what it appears to say.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class KnowledgeProvenance(str, Enum):
    """Where a rule's knowledge came from (ADR-0045).

    **Deliberately not `causalog.core.provenance.ProvenanceClass`.** That enum answers *how
    a fact came to be known* and is folded by `core.aggregation.combine` under the
    weakest-input rule. A rule is not a fact; it is a policy about facts. Carrying
    `ProvenanceClass` here would invite exactly one arithmetic -- combining a rule's pedigree
    with its matched events' provenance -- and the result would claim that an assumption
    about the world is the same kind of thing as an unrecorded timestamp.
    """

    DOMAIN_EXPERTISE = "DOMAIN_EXPERTISE"
    """A practitioner asserts the mechanism. No row in this dataset establishes it."""

    DATASET_OBSERVATION = "DATASET_OBSERVATION"
    """Something measured in the pinned dataset motivated the rule. The basis names what."""

    ASSUMPTION = "ASSUMPTION"
    """Nobody has evidence. Declared so a reader sees it, never smuggled in as expertise."""


class RuleKind(str, Enum):
    """The closed set of rule bodies.

    The first five mirror prd.md §26 and the `CausalEdge` payload union
    (`core/types/causal_edge.py`, ADR-0022) -- one vocabulary for the five categories, not a
    second, weaker one made of strings.

    `CONSTRAINT` has no edge counterpart, and that is the point: it produces a
    **prohibition**, not a claim. Pruning an impossible candidate is a different act from
    proposing a possible one, and collapsing the two would make impossibility rankable.
    """

    CAUSAL = "CAUSAL"
    CONDITIONAL = "CONDITIONAL"
    JOINT = "JOINT"
    AMPLIFICATION = "AMPLIFICATION"
    INHIBITION = "INHIBITION"
    CONSTRAINT = "CONSTRAINT"


class ConditionOperator(str, Enum):
    """The closed operator set a condition tree may use.

    Closed by construction. There is no `CUSTOM`, no `EXPRESSION`, and no `CALL`.
    """

    ALWAYS = "ALWAYS"
    """The empty condition. A rule with no condition says so, rather than omitting a field."""

    ATTRIBUTE = "ATTRIBUTE"
    CONSTANT = "CONSTANT"
    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    GREATER_THAN = "GREATER_THAN"
    LESS_THAN = "LESS_THAN"
    IN = "IN"
    IS_PRESENT = "IS_PRESENT"
    IS_ABSENT = "IS_ABSENT"
    AND = "AND"
    OR = "OR"
    NOT = "NOT"


COMPARISON_OPERATORS: Final[frozenset[ConditionOperator]] = frozenset(
    {
        ConditionOperator.EQUALS,
        ConditionOperator.NOT_EQUALS,
        ConditionOperator.GREATER_THAN,
        ConditionOperator.LESS_THAN,
    }
)

JUNCTION_OPERATORS: Final[frozenset[ConditionOperator]] = frozenset(
    {ConditionOperator.AND, ConditionOperator.OR}
)

PRESENCE_OPERATORS: Final[frozenset[ConditionOperator]] = frozenset(
    {ConditionOperator.IS_PRESENT, ConditionOperator.IS_ABSENT}
)

#: Operators whose operands are compared numerically. Kept apart from EQUALS/NOT_EQUALS,
#: which compare as text -- an attribute value reaches the evaluator as a string, and
#: guessing which strings are numbers is how two packs come to disagree about `"10" > "9"`.
NUMERIC_OPERATORS: Final[frozenset[ConditionOperator]] = frozenset(
    {ConditionOperator.GREATER_THAN, ConditionOperator.LESS_THAN}
)


class RoleAddress(_Spec):
    """One addressable value: a named binding of the rule, one of its roles, one attribute.

    `binding` names WHICH matched event of the rule this address refers to -- `CAUSE`,
    `EFFECT`, or a contributor label on a joint rule. Without it a two-event rule could not
    say whether `SUBJECT.status` meant the antecedent's or the consequent's.

    `role` is a participant role the addressed event type declares, never an entity type.
    Conditions refer to roles for the reason the ontology pack gives: one event may involve
    two participants of the same type, and a type name cannot tell them apart.
    """

    binding: str = Field(pattern=SYMBOL_PATTERN)
    role: str = Field(pattern=SYMBOL_PATTERN)
    attribute: str = Field(pattern=ATTRIBUTE_PATTERN)

    def rendered(self) -> str:
        """Return the stable text form used in a trace and in a diagnostic path."""
        return f"{self.binding}.{self.role}.{self.attribute}"


class ConditionExpression(_Spec):
    """One node of a closed condition operator tree.

    The shape rules below are enforced at construction rather than at evaluation, so a
    malformed condition is a load error naming the rule, never a runtime surprise inside a
    match.
    """

    op: ConditionOperator
    address: RoleAddress | None = None
    value: str | None = None
    values: tuple[str, ...] = ()
    operands: tuple[ConditionExpression, ...] = ()

    @model_validator(mode="after")
    def _check_shape(self) -> ConditionExpression:
        """Enforce the arity and field set each operator admits."""
        if self.op is ConditionOperator.ALWAYS:
            self._refuse_any("ALWAYS", ("address", "value", "values", "operands"))
            return self

        if self.op is ConditionOperator.ATTRIBUTE:
            if self.address is None:
                raise ContractViolationError(
                    "ConditionExpression ATTRIBUTE carries no address; a leaf that reads a "
                    "value must say which value."
                )
            self._refuse_any("ATTRIBUTE", ("value", "values", "operands"))
            return self

        if self.op is ConditionOperator.CONSTANT:
            if self.value is None:
                raise ContractViolationError(
                    "ConditionExpression CONSTANT carries no value; an absent constant is "
                    "not the empty string, and defaulting it would invent a comparison."
                )
            self._refuse_any("CONSTANT", ("address", "values", "operands"))
            return self

        if self.op in COMPARISON_OPERATORS:
            if len(self.operands) != 2:
                raise ContractViolationError(
                    f"ConditionExpression {self.op.value} takes exactly two operands; "
                    f"{len(self.operands)} supplied."
                )
            for operand in self.operands:
                if operand.op not in (ConditionOperator.ATTRIBUTE, ConditionOperator.CONSTANT):
                    raise ContractViolationError(
                        f"ConditionExpression {self.op.value} compares leaves only; operand "
                        f"is {operand.op.value}. Nesting a junction inside a comparison has "
                        "no defined truth value."
                    )
            self._refuse_any(self.op.value, ("address", "value", "values"))
            return self

        if self.op is ConditionOperator.IN:
            if len(self.operands) != 1 or self.operands[0].op is not ConditionOperator.ATTRIBUTE:
                raise ContractViolationError(
                    "ConditionExpression IN takes exactly one ATTRIBUTE operand."
                )
            if not self.values:
                raise ContractViolationError(
                    "ConditionExpression IN carries an empty `values`; a membership test "
                    "against nothing is always false and is a defect, not a rule."
                )
            if len(set(self.values)) != len(self.values):
                raise ContractViolationError(
                    "ConditionExpression IN repeats a member of `values`; a repeat changes "
                    "nothing and means one of the two was meant to be a different value."
                )
            if tuple(sorted(self.values)) != self.values:
                raise ContractViolationError(
                    "ConditionExpression IN `values` must be sorted, so one membership set "
                    "has one canonical form and one hash (CONVENTIONS.md §11)."
                )
            self._refuse_any("IN", ("address", "value"))
            return self

        if self.op in PRESENCE_OPERATORS:
            if len(self.operands) != 1 or self.operands[0].op is not ConditionOperator.ATTRIBUTE:
                raise ContractViolationError(
                    f"ConditionExpression {self.op.value} takes exactly one ATTRIBUTE operand."
                )
            self._refuse_any(self.op.value, ("address", "value", "values"))
            return self

        if self.op is ConditionOperator.NOT:
            if len(self.operands) != 1:
                raise ContractViolationError(
                    f"ConditionExpression NOT takes exactly one operand; "
                    f"{len(self.operands)} supplied."
                )
            self._refuse_any("NOT", ("address", "value", "values"))
            return self

        if len(self.operands) < 2:
            raise ContractViolationError(
                f"ConditionExpression {self.op.value} takes at least two operands; "
                f"{len(self.operands)} supplied. A junction over one operand is that "
                "operand, and writing it means something was left out."
            )
        self._refuse_any(self.op.value, ("address", "value", "values"))
        return self

    def _refuse_any(self, label: str, fields: tuple[str, ...]) -> None:
        """Refuse a populated field this operator does not admit."""
        for field in fields:
            populated = getattr(self, field)
            if populated:
                raise ContractViolationError(
                    f"ConditionExpression {label} carries `{field}`, which it does not "
                    "admit. A field the operator ignores is a rule that reads differently "
                    "from how it evaluates."
                )

    def addresses(self) -> tuple[RoleAddress, ...]:
        """Return every address this subtree reads, in traversal sequence."""
        found: list[RoleAddress] = []
        if self.address is not None:
            found.append(self.address)
        for operand in self.operands:
            found.extend(operand.addresses())
        return tuple(found)

    def is_trivial(self) -> bool:
        """Return whether this tree asserts nothing, and therefore needs no trace entry."""
        return self.op is ConditionOperator.ALWAYS


#: The condition every rule carries when the author wrote none. Stated explicitly rather
#: than represented by `None`, so an evaluator never has two shapes to handle.
ALWAYS: Final[ConditionExpression] = ConditionExpression(op=ConditionOperator.ALWAYS)


class RelationDirection(str, Enum):
    """How the two matched events' participants must be connected.

    `SHARED_PARTICIPANT` is the degenerate and commonest case: the two events name the same
    entity. It is a member here rather than a separate field so that a rule states its
    linkage exactly one way.
    """

    SHARED_PARTICIPANT = "SHARED_PARTICIPANT"
    FROM_TO = "FROM_TO"
    TO_FROM = "TO_FROM"


class EntityRelation(_Spec):
    """The structural linkage two matched events must satisfy to be a candidate pair.

    This is what stops a rule pairing every antecedent with every consequent in the dataset:
    a pair is admissible only when the two named roles resolve to entities that are the same
    entity, or that a declared relationship type connects.

    `relationship_type` is required except under `SHARED_PARTICIPANT`, where there is no
    edge to name -- the two roles resolve to one entity or the pair is rejected.
    """

    direction: RelationDirection
    cause_role: str = Field(pattern=SYMBOL_PATTERN)
    effect_role: str = Field(pattern=SYMBOL_PATTERN)
    relationship_type: str | None = Field(default=None, pattern=SYMBOL_PATTERN)

    @model_validator(mode="after")
    def _check_shape(self) -> EntityRelation:
        """Enforce that a directed relation names its type and a shared one does not."""
        if self.direction is RelationDirection.SHARED_PARTICIPANT:
            if self.relationship_type is not None:
                raise ContractViolationError(
                    "EntityRelation SHARED_PARTICIPANT names a relationship_type; there is "
                    "no edge to name when the two roles must resolve to one entity."
                )
        elif self.relationship_type is None:
            raise ContractViolationError(
                f"EntityRelation {self.direction.value} names no relationship_type; a "
                "directed linkage must say which declared relationship it traverses."
            )
        return self


class TemporalWindow(_Spec):
    """The separation two matched events must exhibit, with its boundaries as data.

    Both bounds are in whole seconds and both are explicit. `inclusive` is carried per end
    rather than assumed, because "within 24 hours" and "within 24 hours, exclusive" are
    different rules and a reader must not have to infer which one a comparison operator
    buried in the evaluator meant.

    **This is a matching window, not a claim of precedence.** Precedence is decided by
    `causalog.core.temporal.verdict` over the two intervals, and no window value can
    override it -- a pair inside the window whose verdict is `VIOLATION` is never emitted.
    """

    minimum_seconds: int = Field(ge=0)
    maximum_seconds: int = Field(ge=0)
    minimum_inclusive: bool = True
    maximum_inclusive: bool = True

    @model_validator(mode="after")
    def _check_bounds(self) -> TemporalWindow:
        """Refuse a window that admits nothing."""
        if self.minimum_seconds > self.maximum_seconds:
            raise ContractViolationError(
                f"TemporalWindow bounds are reversed: minimum_seconds "
                f"{self.minimum_seconds} exceeds maximum_seconds {self.maximum_seconds}; "
                "the window admits no pair."
            )
        if self.minimum_seconds == self.maximum_seconds and not (
            self.minimum_inclusive and self.maximum_inclusive
        ):
            raise ContractViolationError(
                "TemporalWindow is a single instant with an exclusive end; it admits no "
                "pair, which is a defect rather than a very strict rule."
            )
        return self


class EventPattern(_Spec):
    """One event a rule matches: its type, and the label the rule binds it under.

    `binding` is what the rule's conditions and its trace refer to. It is authored rather
    than derived so that a joint rule with three contributors of the same type can address
    each of them.
    """

    binding: str = Field(pattern=SYMBOL_PATTERN)
    event_type: str = Field(pattern=SYMBOL_PATTERN)


class CausalBody(_Spec):
    """`CAUSAL` / `CONDITIONAL`: one antecedent, one consequent, a window and a linkage.

    The two kinds share this body. They differ in what the loader requires of `conditions`:
    a `CONDITIONAL` rule with an `ALWAYS` condition is refused, because prd.md §26's
    conditional cause is defined by the condition it carries, and one without a condition is
    a direct cause that has been mislabelled.
    """

    cause: EventPattern
    effect: EventPattern
    window: TemporalWindow
    relation: EntityRelation
    conditions: ConditionExpression = ALWAYS


class JointBody(_Spec):
    """`JOINT`: a set of antecedents that together produce one consequent (prd.md §26).

    Conjunctive and unranked, matching `core.types.causal_edge.ContributingCause`. There is
    deliberately no per-contributor weight: ranking the members of a joint cause asserts
    that one of them mattered more, which is a finding the Confidence Scorer may reach and
    a rule author may not declare.
    """

    contributors: tuple[EventPattern, ...] = Field(min_length=2)
    effect: EventPattern
    window: TemporalWindow
    relation: EntityRelation
    joint_cause_group_id: str = Field(pattern=SYMBOL_PATTERN)
    conditions: ConditionExpression = ALWAYS

    @model_validator(mode="after")
    def _check_bindings(self) -> JointBody:
        """Refuse two contributors sharing one binding label."""
        labels = [contributor.binding for contributor in self.contributors]
        if len(set(labels)) != len(labels):
            raise ContractViolationError(
                "JointBody repeats a contributor binding; two contributors sharing a label "
                "cannot be told apart by a condition or in a trace."
            )
        if self.effect.binding in labels:
            raise ContractViolationError(
                "JointBody binds its effect under a label a contributor already uses."
            )
        return self


class ModifierBody(_Spec):
    """Shared shape of `AMPLIFICATION` and `INHIBITION` (prd.md §26).

    Public so a consumer can narrow to "this is a modifier" without naming both subclasses;
    never instantiated directly, because a modifier with no multiplier bound is neither.

    A modifier does not propose an edge. It states that when its own pattern matches over
    the same bindings as a named target rule, that rule's claim carries a different
    magnitude. `modifies` names the target by rule identifier, so the relationship is
    inspectable in the pack rather than inferred from overlapping patterns.
    """

    modifier: EventPattern
    modifies: str = Field(pattern=RULE_ID_PATTERN)
    window: TemporalWindow
    relation: EntityRelation
    magnitude_multiplier: float
    conditions: ConditionExpression = ALWAYS


class AmplificationBody(ModifierBody):
    """The event increases downstream magnitude. Bound as `AmplifyingCause` is bound."""

    @model_validator(mode="after")
    def _check_multiplier(self) -> AmplificationBody:
        """Enforce the bound `core.types.causal_edge.AmplifyingCause` enforces."""
        if not self.magnitude_multiplier > 1.0:
            raise ContractViolationError(
                f"AmplificationBody.magnitude_multiplier is {self.magnitude_multiplier}; "
                "amplification requires a multiplier strictly above 1.0, matching "
                "AmplifyingCause. A rule that amplifies by 1.0 amplifies nothing."
            )
        return self


class InhibitionBody(ModifierBody):
    """The event reduces propagation. Bound as `InhibitingCause` is bound."""

    @model_validator(mode="after")
    def _check_multiplier(self) -> InhibitionBody:
        """Enforce the bound `core.types.causal_edge.InhibitingCause` enforces."""
        if not 0.0 <= self.magnitude_multiplier < 1.0:
            raise ContractViolationError(
                f"InhibitionBody.magnitude_multiplier is {self.magnitude_multiplier}; "
                "inhibition requires a multiplier in [0.0, 1.0), matching InhibitingCause."
            )
        return self


class ConstraintBody(_Spec):
    """`CONSTRAINT`: a structural impossibility, which prunes rather than proposes.

    Exactly one of `forbidden_event_type` and `forbidden_state` is set.

    * `forbidden_event_type` -- an entity in `subject_state` cannot participate in an
      event of that type. This is what prunes a candidate pair.
    * `forbidden_state` -- an entity in `subject_state` cannot reach that state. This
      prunes nothing on its own and is checked against observed states, which is how a
      pack states an invariant the ontology's transition table alone does not carry.

    `subject_state` is the condition the prohibition applies under. A constraint with no
    state would be a claim that the type never occurs at all, which belongs in the ontology
    as a removed event type, not here as a rule.
    """

    subject_entity_type: str = Field(pattern=SYMBOL_PATTERN)
    subject_state: str = Field(pattern=SYMBOL_PATTERN)
    subject_role: str = Field(pattern=SYMBOL_PATTERN)
    forbidden_event_type: str | None = Field(default=None, pattern=SYMBOL_PATTERN)
    forbidden_state: str | None = Field(default=None, pattern=SYMBOL_PATTERN)
    conditions: ConditionExpression = ALWAYS

    @model_validator(mode="after")
    def _check_exactly_one(self) -> ConstraintBody:
        """Enforce that exactly one prohibition is stated."""
        stated = [
            name
            for name, populated in (
                ("forbidden_event_type", self.forbidden_event_type),
                ("forbidden_state", self.forbidden_state),
            )
            if populated is not None
        ]
        if len(stated) != 1:
            raise ContractViolationError(
                "ConstraintBody must state exactly one of forbidden_event_type or "
                f"forbidden_state; {stated or 'neither'} supplied. Two prohibitions in one "
                "rule cannot be reported separately when one of them fires."
            )
        return self


RuleBody = CausalBody | JointBody | AmplificationBody | InhibitionBody | ConstraintBody

#: The one body class each kind admits. `AMPLIFICATION` and `INHIBITION` declare identical
#: field sets and differ only in the bound they place on `magnitude_multiplier`, so a plain
#: union would resolve them by whichever happens to validate -- picking the right class for
#: the wrong reason, and silently accepting a rule labelled `AMPLIFICATION` whose multiplier
#: makes it an inhibition. `Rule` selects from this table by the declared kind instead.
BODY_FOR_KIND: Final[dict[RuleKind, type[_Spec]]] = {
    RuleKind.CAUSAL: CausalBody,
    RuleKind.CONDITIONAL: CausalBody,
    RuleKind.JOINT: JointBody,
    RuleKind.AMPLIFICATION: AmplificationBody,
    RuleKind.INHIBITION: InhibitionBody,
    RuleKind.CONSTRAINT: ConstraintBody,
}


class Rule(_Spec):
    """One rule: its identity, its pedigree, and exactly one body.

    Every field in the header is required. None of them is decorative:

    * `description` is what the rule claims, and reaches an explanation.
    * `rationale` is why anyone should believe it. A rule nobody justified is a rule
      nobody can argue with.
    * `author` is who to ask.
    * `knowledge_provenance` and `evidence_basis` are the pair ADR-0045 requires -- the
      class, and the content behind it. An `ASSUMPTION` with an empty basis is refused,
      because an assumption whose content nobody wrote down is not inspectable and the
      whole premise of this system is that a user sees what it is assuming.
    * `base_strength` is the rule's own weight, in `[0, 1]`. It is **not** a confidence: it
      is one input a `ConfidenceVector` is later assembled from by module 10, and it is a
      bare float for the same reason `EvidenceItem.strength` is (`docs/contracts.md` §5).
      **It is named `base_strength`, not `confidence_weight`, deliberately.** The first
      draft used the latter and `scripts/check_confidence_is_a_vector.py` refused the
      build: a `confidence`-named field bound to a float is the unexplained number
      prd.md §49 forbids, and the lint cannot know that this one is not. Renaming was the
      correct fix; an allowlist entry would have taught the next reader that a bare float
      confidence is acceptable here.
    * `enabled` lets a pack retire a rule without deleting its identifier, so a past run
      that cites the identifier stays legible. A disabled rule is loaded, validated, and
      reported in coverage, and never evaluated.
    """

    id: str = Field(pattern=RULE_ID_PATTERN)
    kind: RuleKind
    description: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    author: str = Field(min_length=1)
    knowledge_provenance: KnowledgeProvenance
    evidence_basis: str = Field(min_length=1)
    base_strength: float = Field(ge=0.0, le=1.0)
    enabled: bool = True
    disabled_reason: str | None = None
    body: RuleBody

    @model_validator(mode="before")
    @classmethod
    def _parse_body_by_kind(cls, data: object) -> object:
        """Select the body class from the declared kind, rather than by union resolution.

        `AMPLIFICATION` and `InhibitionBody` share a field set, so union resolution would
        choose between them by which multiplier bound happens to pass -- accepting a rule
        labelled one thing and shaped like the other. The kind is authoritative here, and a
        body that does not fit it fails naming both.
        """
        if not isinstance(data, dict):
            return data
        kind = data.get("kind")
        body = data.get("body")
        if kind is None or not isinstance(body, dict):
            return data
        try:
            selected = BODY_FOR_KIND[RuleKind(kind)]
        except ValueError:
            return data
        return {**data, "body": selected.model_validate(body)}

    @model_validator(mode="after")
    def _check_body_matches_kind(self) -> Rule:
        """Enforce that the body is the one the declared kind admits."""
        wanted = BODY_FOR_KIND[self.kind]
        if not isinstance(self.body, wanted):
            raise ContractViolationError(
                f"Rule {self.id} declares kind {self.kind.value} and carries a "
                f"{type(self.body).__name__}; {wanted.__name__} is required."
            )
        if (
            self.kind is RuleKind.CONDITIONAL
            and isinstance(self.body, CausalBody)
            and self.body.conditions.is_trivial()
        ):
            raise ContractViolationError(
                f"Rule {self.id} declares kind CONDITIONAL and carries no condition. "
                "prd.md §26's conditional cause IS the condition it carries; one "
                "without a condition is a direct cause that has been mislabelled."
            )
        if (
            self.knowledge_provenance is KnowledgeProvenance.ASSUMPTION
            and not self.evidence_basis.strip()
        ):
            raise ContractViolationError(
                f"Rule {self.id} is an ASSUMPTION with an empty evidence_basis; an "
                "assumption nobody wrote down cannot be shown to a user (ADR-0045)."
            )
        if not self.enabled and not (self.disabled_reason or "").strip():
            raise ContractViolationError(
                f"Rule {self.id} is disabled and states no disabled_reason; a rule switched "
                "off for a reason nobody recorded is switched off for no reason anybody can "
                "check."
            )
        if self.enabled and self.disabled_reason is not None:
            raise ContractViolationError(
                f"Rule {self.id} is enabled and carries a disabled_reason; the two "
                "disagree, and a reader cannot tell which one is stale."
            )
        return self

    def bindings(self) -> tuple[str, ...]:
        """Return every binding label this rule's body declares, sorted."""
        body = self.body
        if isinstance(body, CausalBody):
            labels = {body.cause.binding, body.effect.binding}
        elif isinstance(body, JointBody):
            labels = {contributor.binding for contributor in body.contributors}
            labels.add(body.effect.binding)
        elif isinstance(body, ConstraintBody):
            labels = {"SUBJECT"}
        else:
            labels = {body.modifier.binding}
        return tuple(sorted(labels))

    def event_types(self) -> tuple[str, ...]:
        """Return every event type this rule names, sorted."""
        body = self.body
        if isinstance(body, CausalBody):
            named = {body.cause.event_type, body.effect.event_type}
        elif isinstance(body, JointBody):
            named = {contributor.event_type for contributor in body.contributors}
            named.add(body.effect.event_type)
        elif isinstance(body, ConstraintBody):
            named = set() if body.forbidden_event_type is None else {body.forbidden_event_type}
        else:
            named = {body.modifier.event_type}
        return tuple(sorted(named))

    def produced_event_types(self) -> tuple[str, ...]:
        """Return the event types this rule EXPLAINS -- names as a consequent.

        A constraint explains nothing; it prunes. A modifier explains nothing; it rescales
        another rule's claim. Both correctly return empty, and the coverage report counts
        them that way rather than crediting a type with an explanation it does not have.
        """
        body = self.body
        if isinstance(body, CausalBody):
            return (body.effect.event_type,)
        if isinstance(body, JointBody):
            return (body.effect.event_type,)
        return ()

    def antecedent_event_types(self) -> tuple[str, ...]:
        """Return the event types this rule reasons FROM, sorted."""
        body = self.body
        if isinstance(body, CausalBody):
            return (body.cause.event_type,)
        if isinstance(body, JointBody):
            return tuple(sorted(contributor.event_type for contributor in body.contributors))
        if isinstance(body, ConstraintBody):
            return ()
        return (body.modifier.event_type,)

    def conditions(self) -> ConditionExpression:
        """Return this rule's condition tree. Every body carries one."""
        return self.body.conditions


class ProximityWindowSpec(_Spec):
    """One sequenced event-type pair, and the separation within which proximity is admissible.

    This is the declaration module 9's temporal-proximity generator reads. It lives in the
    rule pack rather than in the ontology pack because a window is a claim about *causal
    plausibility* -- "an effect of this type, if it has a cause of that type, follows it
    within this long" -- and that is causal knowledge, which is what a rule pack holds. The
    ontology describes what a domain IS; this describes what someone believes about how it
    behaves, and ADR-0045's whole point is that those are different kinds of statement.

    `rationale` is required for the same reason `Rule.rationale` is: a window nobody
    justified is a threshold nobody can argue with, and its width silently governs how many
    hypotheses the engine will consider.

    **A window matches; it never asserts precedence.** Precedence is decided by
    `causalog.core.temporal.verdict` over the two intervals, and no value here can override
    it -- a pair inside the window whose verdict is `VIOLATION` is never emitted.
    """

    cause_event_type: str = Field(pattern=SYMBOL_PATTERN)
    effect_event_type: str = Field(pattern=SYMBOL_PATTERN)
    window: TemporalWindow
    rationale: str = Field(min_length=1)
    #: The weight the resulting `EvidenceItem` carries, authored exactly as
    #: `Rule.base_strength` is and for the same reason: it is NOT a confidence, it is one
    #: input module 10 assembles a vector from, and module 9 may not invent it. Required,
    #: so a pack that declares a window also states what it thinks the window is worth.
    evidence_strength: float = Field(ge=0.0, le=1.0)


class CandidateGenerationSpec(_Spec):
    """Every parameter module 9's generators need, declared as data (ADR: schema 1.1.0).

    None of these may be a literal in engine code. A window width, a hop bound, a support
    threshold and a per-effect cap are all domain policy: they decide which hypotheses the
    engine is willing to entertain, they differ per domain, and a number written into
    `causal_engine/` does not move when the domain is swapped -- which is LAW-DOMAIN
    defeated by a value rather than by a word (`CONVENTIONS.md` §6a, ADR-0031).

    **Every field is optional and absent by default, and an absent field means the
    generator that needs it CANNOT RUN.** That is deliberately not the same as the
    generator running and finding nothing. `ontology_runtime` introduced the third severity
    `NOT_RUNNABLE` for exactly this failure -- a check that could not run reads identically
    to a check that passed -- and module 9's report carries the same distinction rather than
    reporting an unconfigured generator as a clean zero.

    A pack that declares nothing here is valid. It gets a candidate graph built from its
    rules alone, and a report saying in as many words which five generators did not run and
    what each one would need.
    """

    proximity_windows: tuple[ProximityWindowSpec, ...] = ()
    structural_max_hops: int | None = Field(default=None, ge=1)
    minimum_support_count: int | None = Field(default=None, ge=1)
    minimum_lift: float | None = Field(default=None, gt=0.0)
    per_effect_candidate_cap: int | None = Field(default=None, ge=1)

    # ---------------------------------------------------------------------------------
    # Authored evidence weights, one per generator that has no other declaration to draw
    # one from. The rule-based generator needs none: it uses the firing rule's own
    # `base_strength`, which the rule author already wrote down.
    #
    # These are REQUIRED for their generator to run, and absence makes it NOT_RUNNABLE
    # rather than unweighted. That is the whole point: `EvidenceItem.strength` is a real
    # number a reader will see, module 9 is forbidden from assigning judgement, and a
    # default written here would be judgement wearing a schema default's clothes.
    # ---------------------------------------------------------------------------------
    shared_entity_strength: float | None = Field(default=None, ge=0.0, le=1.0)
    shared_identifier_strength: float | None = Field(default=None, ge=0.0, le=1.0)
    #: Which `Event.metadata` keys carry a domain IDENTIFIER, as opposed to the traceability
    #: pairs the Event Generator stamps on every event (`observation_mode`, `emission`,
    #: `occurred_at_policy`). Declared rather than inferred because nothing in the metadata
    #: shape distinguishes the two, and a generator that matched on all of them would pair
    #: every two events sharing an observation mode -- a fact about how the events were MADE,
    #: not about the domain. Empty means the shared-identifier generator cannot run.
    identifier_metadata_keys: tuple[str, ...] = ()
    structural_path_strength: float | None = Field(default=None, ge=0.0, le=1.0)
    historical_frequency_strength: float | None = Field(default=None, ge=0.0, le=1.0)
    statistical_association_strength: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_windows(self) -> CandidateGenerationSpec:
        """Refuse a repeated sequenced pair, and refuse a self-pair."""
        pairs = [
            (entry.cause_event_type, entry.effect_event_type) for entry in self.proximity_windows
        ]
        duplicated = sorted({pair for pair in pairs if pairs.count(pair) > 1})
        if duplicated:
            raise ContractViolationError(
                f"CandidateGenerationSpec declares two proximity windows for {duplicated}; "
                "two widths for one sequenced pair means the generator would have to choose, "
                "and a choice made by iteration sequence is not a declaration."
            )
        for cause_type, effect_type in pairs:
            if cause_type == effect_type:
                raise ContractViolationError(
                    f"CandidateGenerationSpec declares a proximity window from "
                    f"{cause_type} to itself; an event type causing its own type is not "
                    "expressible as one sequenced pair and needs a rule that names both."
                )
        return self

    def window_entry_for(
        self, cause_event_type: str, effect_event_type: str
    ) -> ProximityWindowSpec | None:
        """Return the whole declaration for one sequenced pair, or None if none is declared.

        The whole entry rather than its window alone, because a consumer needs the authored
        `evidence_strength` beside the width and fetching them separately would let the two
        come from different entries.
        """
        for entry in self.proximity_windows:
            if (
                entry.cause_event_type == cause_event_type
                and entry.effect_event_type == effect_event_type
            ):
                return entry
        return None


class ConfidenceBandSpec(_Spec):
    """One published confidence band: a floor, a name, and what it means in plain words.

    prd.md §49 forbids an unexplained number. A band is the half of that promise the
    interface keeps -- "0.42" tells a reader nothing they can act on, and "suggestive --
    corroborated, but precedence is not established" tells them what to do next.

    **The threshold and the wording live here, in the pack, and never in UI code.** A band
    boundary written into a component is a policy no reviewer of this repository can find,
    that no test can pin, and that differs silently between two screens showing the same
    edge. `plain_language` is authored per domain for the same reason `rationale` is: a
    supply-chain analyst and a clinician do not want the same sentence, and the engine has
    no business writing either.
    """

    name: str = Field(pattern=SYMBOL_PATTERN)
    #: The lowest scalar this band admits, inclusive. Bands are read from the highest
    #: floor down, so the floors partition `[0, 1]` without any band declaring a ceiling.
    minimum_scalar: float = Field(ge=0.0, le=1.0)
    plain_language: str = Field(min_length=1)


class ConfidenceScoringSpec(_Spec):
    """Every domain-tunable number module 10 reads (schema 1.2.0, ADR-0053).

    **What is here and what is deliberately NOT here.** The aggregation strategy -- the six
    addend weights and the two gate ceilings -- lives in `causalog.core.aggregation` under a
    versioned function name, and not in this block. That is not an oversight and not a
    LAW-DOMAIN exception. `ConfidenceVector.aggregation` records the function that produced
    a scalar precisely so any consumer can recompute it and disagree; if a pack could supply
    the weights, `gated_weighted_mean_v1` would compute two different things in two packs
    and the recorded name would no longer determine the number. The strategy name has to be
    a complete description of the arithmetic, so the arithmetic is versioned with the name.

    What IS here is everything that describes the DOMAIN rather than the strategy: how large
    a lift is impressive in this domain, how many process instances make a count worth
    believing, how far apart two events normally sit, and what a band should be called when
    it is shown to this domain's users.

    **Every field is optional and absent by default, and an absent field means the scorer
    that needs it CANNOT RUN.** Identical to `CandidateGenerationSpec` (ADR-0049) and for
    the identical reason: a default written here is a judgement wearing a schema default's
    clothes, and `NOT_SCORABLE` must never read as a component that scored zero.
    """

    #: The lift at which `historical_support` and `statistical_support` reach 1.0. Lift 1.0
    #: is independence and always scores 0; the scale between them is logarithmic, so this
    #: number answers "how much more often than chance is remarkable HERE".
    lift_reference: float | None = Field(default=None, gt=1.0)
    #: The pseudo-count in the small-sample shrinkage `n / (n + prior)`. A pattern seen in
    #: three instances and one seen in three thousand do not deserve the same score even at
    #: identical lift, and this is the number that separates them. Larger means more
    #: sceptical of small samples.
    small_sample_prior_count: int | None = Field(default=None, ge=1)
    #: The `k` in the saturating evidence count `n / (n + k)`. Saturating rather than
    #: linear-to-a-cap so that the tenth justification for a claim adds less than the second.
    evidence_count_saturation_k: int | None = Field(default=None, ge=1)
    #: The separation width, in seconds, at which temporal tightness has decayed to one
    #: half. A pair known only to within a day scores far below one known to the second.
    temporal_reference_seconds: int | None = Field(default=None, ge=1)
    #: What `temporal_support` is worth when the verdict is `UNDETERMINED` -- the data
    #: placed both events and could not separate them. Deliberately declared rather than
    #: derived: it is a statement about how much this domain trusts an unresolvable tie,
    #: and on a day-granular source it governs most of the graph (`CONTEXT.md` R-14).
    undetermined_temporal_support: float | None = Field(default=None, ge=0.0, le=1.0)
    #: The CEILING on `temporal_support` when the source COMPUTED the later instant from the
    #: earlier one -- a derivation module 1 measured over every evaluable row rather than
    #: assumed. Such a pair satisfies strict precedence by arithmetic, so a `CERTAIN` verdict
    #: over it establishes nothing, however wide the separation looks.
    #:
    #: Declared rather than derived, for the reason `undetermined_temporal_support` is: how
    #: much a domain trusts an instant its own source computed is a judgement about the
    #: domain. Absent, an edge resting on a confirmed derivation is NOT SCORABLE on this
    #: component -- never silently scored as though the precedence had been observed.
    #:
    #: This is a COMPONENT value, not a scalar ceiling. It reaches the scalar through
    #: `TEMPORAL_CEILING_ANCHORS`, which is not the identity: 0.15 here caps the scalar near
    #: 0.4, and 0.5 here caps it near 0.72. Author it against the anchors, not against the
    #: score you want to see.
    derived_precedence_temporal_support: float | None = Field(default=None, ge=0.0, le=1.0)
    #: How many of the eight components must carry real, non-missing support before an edge
    #: is called scored at all. Below it the edge is `INSUFFICIENT_EVIDENCE`, which is a
    #: different finding from a low score and is never shown as one.
    minimum_scored_components: int | None = Field(default=None, ge=1, le=8)
    #: The band an edge must reach before `INFERRED` may be assigned. Names a band declared
    #: below. Promotion is a judgement, and this is where the judgement is written down.
    promotion_band: str | None = Field(default=None, pattern=SYMBOL_PATTERN)
    #: The published bands, in any authored sequence; the loader sorts them. Empty means
    #: this pack publishes no bands, and every edge is reported with its scalar and no
    #: label rather than with a label the engine invented.
    confidence_bands: tuple[ConfidenceBandSpec, ...] = ()

    @model_validator(mode="after")
    def _check_bands(self) -> ConfidenceScoringSpec:
        """Refuse repeated band names, repeated floors, and a promotion band that is absent."""
        names = [band.name for band in self.confidence_bands]
        duplicated = sorted({name for name in names if names.count(name) > 1})
        if duplicated:
            raise ContractViolationError(
                f"ConfidenceScoringSpec declares band name(s) {duplicated} more than once; "
                "two floors under one name means the band shown to a reader depends on "
                "iteration sequence, which is not a declaration."
            )
        floors = [band.minimum_scalar for band in self.confidence_bands]
        repeated_floors = sorted({floor for floor in floors if floors.count(floor) > 1})
        if repeated_floors:
            raise ContractViolationError(
                f"ConfidenceScoringSpec declares two bands at floor(s) {repeated_floors}; "
                "bands are read from the highest floor down, so two at one floor have no "
                "defined precedence."
            )
        if self.promotion_band is not None and self.promotion_band not in names:
            raise ContractViolationError(
                f"ConfidenceScoringSpec names '{self.promotion_band}' as its promotion "
                f"band, but declares only {sorted(names)}. A promotion threshold pointing "
                "at a band nobody declared would admit nothing and would look like a "
                "dataset finding rather than a pack defect."
            )
        return self

    def bands_high_to_low(self) -> tuple[ConfidenceBandSpec, ...]:
        """Return the declared bands from the highest floor down, which is read sequence."""
        return tuple(sorted(self.confidence_bands, key=lambda band: -band.minimum_scalar))

    def band_for(self, scalar: float) -> ConfidenceBandSpec | None:
        """Return the band this scalar falls in, or None if the pack declares none.

        None is returned for a scalar below every declared floor as well. A pack whose
        lowest floor is above zero has left a range unlabelled, and inventing a label for
        it here would be the engine writing the sentence the pack refused to.
        """
        for band in self.bands_high_to_low():
            if scalar >= band.minimum_scalar:
                return band
        return None


# =========================================================================================
# Graph construction (ADR-0055, schema 1.3.0) -- the Causal Graph Builder's declarations.
#
# ADR-0053 stated the rule for deciding where a number lives, and this block applies it:
# a number that must be identical across domains for a finding to mean the same thing lives
# in engine code under a versioned name; a number that would legitimately differ between two
# packs lives here.
#
# By that rule the thresholds, the competition policy, the attribution mapping and the
# enumeration bound are all pack declarations -- and **cycle classification is not**.
# Whether a circuit whose links are UNDETERMINED is a discovered feedback loop or a data
# artifact is not a domain judgement, and if a pack could decide it then "the engine
# detected a reinforcing loop" would mean two different things in two packs. That decision
# lives in `causal_graph_builder/cycles.py` and no field below can override it.
# =========================================================================================


class CompetingEffectPolicy(str, Enum):
    """What to do when several causes are proposed for one effect.

    Every member keeps the losers: a candidate that does not become an edge becomes a
    `DemotionRecord` with a reason, because "what did you consider and reject?" is a
    question the graph must be able to answer.
    """

    RETAIN_ALL = "RETAIN_ALL"
    """Every candidate over its kind's threshold is promoted. Multiple causes are normal."""

    RETAIN_ABOVE_THRESHOLD = "RETAIN_ABOVE_THRESHOLD"
    """Identical to RETAIN_ALL, named separately so a pack states the intent it holds."""

    RETAIN_TOP_N = "RETAIN_TOP_N"
    """Only the `competing_retain_count` strongest per effect. Needs that count declared."""


class WeightNormalization(str, Enum):
    """How propagation weights over competing incoming edges are made to sum to one."""

    SHARE_OF_INCOMING = "SHARE_OF_INCOMING"
    """Each contributing edge's share of the summed confidence over one effect's incoming
    contributing edges. The only admissible value at schema 1.3.0. Present as an enum with
    one member so that the normalization is a DECLARATION a reviewer can find, rather than
    an unnamed convention inside the arithmetic -- the same argument
    `ConfidenceVector.aggregation` makes about the scalar."""


class PromotionThresholdSpec(_Spec):
    """The band one edge kind must reach before the engine will stand behind it.

    **Per kind, not global.** A `DIRECT` claim and an `AMPLIFYING` claim are not the same
    kind of assertion, and a domain may reasonably demand more of one than the other. One
    global number forces a single answer and hides that a choice was made.

    `rationale` is required for the same reason `Rule.rationale` and
    `ProximityWindowSpec.rationale` are: a threshold nobody justified is a threshold nobody
    can argue with, and this one governs whether an assertion is made at all.

    **A kind with no entry promotes nothing**, and the graph quality report names it and
    says what it would need. That is ADR-0049's absent-means-NOT-RUNNABLE rule applied to
    the most consequential number in the pack: a defaulted promotion threshold would be the
    engine deciding, on its own authority, what it is willing to assert.
    """

    edge_kind: str = Field(pattern=SYMBOL_PATTERN)
    #: Names a band declared in `confidence_scoring.confidence_bands`. Checked there.
    minimum_band: str = Field(pattern=SYMBOL_PATTERN)
    rationale: str = Field(min_length=1)


class MagnitudeAttributionSpec(_Spec):
    """Which declared measurement supplies the magnitude being apportioned for one effect.

    A propagation weight answers "how much of the effect's magnitude is attributable to this
    cause". That sentence has no meaning until someone says what the effect's magnitude IS,
    and in this system a magnitude is whatever `measurement_definitions` declares it to be
    (ADR-0026). This is the mapping from an effect's event type to that declaration.

    An effect type with no entry gets no measured magnitude. Its incoming weights fall back
    to normalized confidence share, the report names every effect that fell back, and the
    fallback is labelled as what it is -- a share of belief, not a share of a quantity.
    """

    effect_event_type: str = Field(pattern=SYMBOL_PATTERN)
    #: Names an id in the ontology pack's `measurement_definitions`. Checked at load when a
    #: vocabulary is supplied; unchecked and reported NOT_RUNNABLE when one is not.
    measurement_id: str = Field(pattern=SYMBOL_PATTERN)
    rationale: str = Field(min_length=1)


class GraphConstructionSpec(_Spec):
    """Every domain-tunable number the Causal Graph Builder reads (schema 1.3.0, ADR-0055).

    **Every field is optional and absent by default, and an absent field means the policy
    that needs it CANNOT RUN.** Identical to `CandidateGenerationSpec` (ADR-0049) and
    `ConfidenceScoringSpec` (ADR-0053), and for the identical reason: a default written here
    is a judgement wearing a schema default's clothes, and this block's judgements decide
    what the system asserts rather than merely how loudly.

    A pack that declares nothing here is valid. It gets an empty causal graph and a report
    saying in as many words which policy did not run and what each one would need.
    """

    #: One entry per `CausalEdgeKind` the pack is willing to promote. A kind absent here is
    #: never promoted, and the report names it. Empty means the graph is empty by
    #: declaration -- which is a legitimate thing for a pack to say and is reported as a
    #: declaration rather than as a finding about the data.
    promotion_thresholds: tuple[PromotionThresholdSpec, ...] = ()
    competing_effect_policy: CompetingEffectPolicy | None = None
    #: Required by, and only by, `RETAIN_TOP_N`.
    competing_retain_count: int | None = Field(default=None, ge=1)
    #: The most a claim may gain, in the tie-break among competing candidates for one
    #: effect, from having been reached by several independent generators.
    #:
    #: **This is a tie-break, never an addend to a score.** Module 10 has already fused
    #: parallel candidates, deduplicated their evidence by content address, and scored
    #: `evidence_diversity` and `evidence_count` as components of the vector. Letting
    #: multiplicity move a scalar a second time here would be counting one fact twice. It
    #: is capped and declared so that the size of what it CAN do is visible.
    diversity_credit_ceiling: float | None = Field(default=None, ge=0.0, le=1.0)
    magnitude_attributions: tuple[MagnitudeAttributionSpec, ...] = ()
    weight_normalization: WeightNormalization | None = None
    #: The most elementary circuits to enumerate per strongly connected component. Absent
    #: means loop detection cannot run. A combinatorial component reports truncation rather
    #: than running until someone kills it -- module 9's `TruncationRecord` idiom.
    circuit_enumeration_cap: int | None = Field(default=None, ge=1)
    #: The fewest participants a circuit must have to be reported as a loop at all. Two is
    #: the smallest meaningful value; a pack wanting to ignore mutual pairs declares three.
    loop_minimum_participants: int | None = Field(default=None, ge=2)

    @model_validator(mode="after")
    def _check_shape(self) -> GraphConstructionSpec:
        """Refuse a repeated edge kind, a repeated effect type, and an unusable count."""
        kinds = [entry.edge_kind for entry in self.promotion_thresholds]
        duplicated = sorted({kind for kind in kinds if kinds.count(kind) > 1})
        if duplicated:
            raise ContractViolationError(
                f"GraphConstructionSpec declares two promotion thresholds for {duplicated}; "
                "two floors for one edge kind means the threshold applied depends on "
                "iteration sequence, which is not a declaration."
            )
        effects = [entry.effect_event_type for entry in self.magnitude_attributions]
        repeated = sorted({effect for effect in effects if effects.count(effect) > 1})
        if repeated:
            raise ContractViolationError(
                f"GraphConstructionSpec attributes two magnitudes to effect type(s) "
                f"{repeated}; a weight is a share of ONE quantity, and two candidate "
                "quantities for one effect make the share meaningless."
            )
        if (
            self.competing_effect_policy is CompetingEffectPolicy.RETAIN_TOP_N
            and self.competing_retain_count is None
        ):
            raise ContractViolationError(
                "GraphConstructionSpec declares RETAIN_TOP_N and no competing_retain_count; "
                "a policy that keeps the strongest N without saying what N is would have to "
                "choose one, and a number chosen by the engine is the thing this block "
                "exists to prevent."
            )
        if (
            self.competing_retain_count is not None
            and self.competing_effect_policy is not CompetingEffectPolicy.RETAIN_TOP_N
        ):
            raise ContractViolationError(
                "GraphConstructionSpec declares competing_retain_count under policy "
                f"{self.competing_effect_policy}, which does not read it. A number nothing "
                "reads is a policy its author believes is in force and is not."
            )
        return self

    def threshold_for(self, edge_kind: str) -> PromotionThresholdSpec | None:
        """Return the declared threshold for one edge kind, or None if none is declared."""
        for entry in self.promotion_thresholds:
            if entry.edge_kind == edge_kind:
                return entry
        return None

    def attribution_for(self, effect_event_type: str) -> MagnitudeAttributionSpec | None:
        """Return the declared magnitude attribution for one effect type, or None."""
        for entry in self.magnitude_attributions:
            if entry.effect_event_type == effect_event_type:
                return entry
        return None


# =========================================================================================
# Root cause, propagation and pattern mining (schema 1.5.0) -- modules 11 and 12, and the
# structural pattern miner prd.md §36 names no owner for.
#
# ADR-0053 stated the rule for deciding where a number lives and ADR-0055 applied it; this
# block applies it for the fourth time. A number that must be identical across domains for
# a finding to mean the same thing lives in engine code under a versioned name; a number
# that would legitimately differ between two packs lives here.
#
# By that rule the traversal bounds, the combination operators, the composition and ranking
# function NAMES and the support thresholds are all pack declarations -- and the composition
# and ranking FUNCTIONS themselves are not. `core.composition` and `core.ranking` hold those
# under versioned names for the reason `core.aggregation` holds the confidence strategies:
# if a pack could supply the arithmetic, "the engine ranked this cause first" would mean two
# different things in two packs, and the sentence would stop being comparable across domains.
# A pack chooses WHICH named function; it never supplies one.
#
# Every field here is optional and absent by default, and **an absent field means the policy
# that needs it CANNOT RUN**. It is reported with what it would need, and never defaulted.
# That is ADR-0049's rule, carried for the fourth time, and the reason is unchanged: a
# default written into the engine is a judgement wearing a schema default's clothes.
# =========================================================================================


class ImpactAggregationSpec(_Spec):
    """How one measurement's readings combine across a set of affected consequences.

    Propagation reports a total over everything downstream of a seed. That total has no
    meaning until someone says how two readings combine, and the answer is genuinely domain
    knowledge rather than arithmetic: two currency figures over distinct subjects add, two
    elapsed-time figures over overlapping periods do not, and a capacity figure may be
    bounded by its largest member rather than by their total. A pack that declares nothing
    for a measurement gets no total for it, and the report names the measurement that lost
    one.

    `operator` names a member of `causalog.core.attribution.COMBINATION_OPERATORS` -- a
    strict subset of the ontology's nine expression operators, named identically so a pack
    author reads one vocabulary rather than two. The four omitted operators are omitted
    because they are not n-ary over an unordered set.
    """

    measurement_id: str = Field(pattern=SYMBOL_PATTERN)
    operator: str = Field(pattern=SYMBOL_PATTERN)
    rationale: str = Field(min_length=1)


class PropagationAnalysisSpec(_Spec):
    """Every domain-tunable number module 12 reads (schema 1.5.0).

    A pack that declares nothing here is valid. It gets a propagation report that traverses
    nothing and says, per policy, exactly what it would have needed.
    """

    #: The furthest the traversal may walk from a seed. Absent means no traversal runs at
    #: all: prd.md §30's example is six deep and a different domain's is not, so there is no
    #: cross-domain number to fall back on. Reaching this bound is reported as TRUNCATION,
    #: never as a completed sweep.
    maximum_depth: int | None = Field(default=None, ge=1)
    #: The most nodes one traversal may visit, whatever the depth. A separate bound from
    #: `maximum_depth` because a shallow, very wide graph and a deep, narrow one are
    #: different shapes and one number cannot bound both.
    traversal_node_cap: int | None = Field(default=None, ge=1)
    #: One entry per measurement whose readings this domain knows how to combine.
    impact_aggregation: tuple[ImpactAggregationSpec, ...] = ()
    #: Names a member of `causalog.core.composition.PATH_COMPOSERS`. Absent means no path
    #: confidence is composed and every chain reports its per-link values alone.
    path_confidence_composition: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")

    @model_validator(mode="after")
    def _check_shape(self) -> PropagationAnalysisSpec:
        """Refuse a repeated measurement and a cap that cannot bound anything."""
        named = [entry.measurement_id for entry in self.impact_aggregation]
        repeated = sorted({name for name in named if named.count(name) > 1})
        if repeated:
            raise ContractViolationError(
                f"propagation_analysis.impact_aggregation repeats measurement(s) "
                f"{repeated}. Two combination operators for one measurement is a "
                "disagreement rather than a declaration, and picking one would make the "
                "total depend on document sequence."
            )
        if named != sorted(named):
            raise ContractViolationError(
                "propagation_analysis.impact_aggregation is unsequenced; entries are read "
                "in document sequence and an unsorted block hashes differently from an "
                "identical one written in sorted sequence (CONVENTIONS.md §11)."
            )
        return self

    def aggregation_for(self, measurement_id: str) -> ImpactAggregationSpec | None:
        """Return the declared combination for one measurement, or None if undeclared."""
        for entry in self.impact_aggregation:
            if entry.measurement_id == measurement_id:
                return entry
        return None


class RootCauseAnalysisSpec(_Spec):
    """Every domain-tunable number module 11 reads (schema 1.5.0).

    Note what is NOT here, deliberately: there is no weighting between earliness and
    prevented consequence. ADR-0008 ruled that the two are not commensurable and that any
    weighting between them would be an unexplainable constant, so earliness is a tie-break
    and never a term. A pack cannot supply that weighting because the ADR says the number
    must not exist -- not because nobody has got round to adding the field.
    """

    #: Names a member of `causalog.core.ranking.RANKERS`. Absent means the ranked view
    #: cannot be produced; the structural views (earliest, and the actionable SET) still
    #: can, because neither needs a sequencing.
    ranking_function: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")
    #: A chain composing below this is reported but never recommended. Absent means no
    #: floor is applied and every chain that exists is eligible, which is reported so a
    #: reader knows the absence of weak candidates is not evidence there were none.
    minimum_chain_scalar: float | None = Field(default=None, ge=0.0, le=1.0)
    #: The most candidate causes one ranking may consider. Reaching it is truncation.
    candidate_cap: int | None = Field(default=None, ge=1)
    #: How many times a cause-to-outcome pattern must recur before it is called structural
    #: rather than incidental. Absent means recurrence is COUNTED and never CLASSIFIED --
    #: the count is a measurement and the word "structural" is a judgement, and only the
    #: judgement needs a declared threshold.
    recurrence_minimum_support: int | None = Field(default=None, ge=1)


class PatternMiningSpec(_Spec):
    """Every domain-tunable number the structural pattern miner reads (schema 1.5.0)."""

    #: How often a cause-type-to-effect-type motif must appear to be reported.
    motif_minimum_support: int | None = Field(default=None, ge=1)
    #: The longest motif enumerated. Enumeration over a dense type projection is
    #: exponential in this bound, so it is a bound and not a preference.
    motif_maximum_length: int | None = Field(default=None, ge=2)
    #: The degree at which a node in the type projection is reported as a chronic
    #: bottleneck. A bottleneck is a claim about a domain's shape and the number that makes
    #: it true differs between domains.
    bottleneck_minimum_degree: int | None = Field(default=None, ge=1)


class CounterfactualSimulationSpec(_Spec):
    """Every domain-tunable number module 13 reads (schema 1.6.0, ADR-0071).

    prd.md §55 gives a counterfactual query five seconds and says nothing about how to stay
    inside it. Every bound below is a judgement, and ADR-0049, ADR-0053, ADR-0055 and
    ADR-0063 have all ruled where a judgement lives: in the pack, declared, with an absent
    declaration meaning the policy CANNOT RUN rather than meaning a default.
    """

    #: How far a change may propagate from the events it touched. Bounded above by the
    #: module's named ceiling; a declaration above the ceiling is clamped and reported, so
    #: a pack can tighten the bound and can never loosen it past what the budget admits.
    maximum_simulation_depth: int | None = Field(default=None, ge=1)
    #: The largest number of events one simulation may touch. prd.md §55's five seconds is
    #: a product requirement, and an unbounded sweep over a dense graph does not meet it.
    affected_subgraph_node_cap: int | None = Field(default=None, ge=1)
    #: How far outside the range a run actually witnessed a changed value may go before the
    #: outcome is returned as EXTRAPOLATION instead of as a figure, as a fraction of the
    #: witnessed range. Zero means any value outside the witnessed range extrapolates.
    support_envelope_tolerance: float | None = Field(default=None, ge=0.0)
    #: The multipliers applied to a simulated outcome to see whether it survives a change in
    #: assumptions the data cannot adjudicate. Each is a fraction of the outcome; an outcome
    #: that inverts under one of these is reported as unstable rather than as an answer.
    sensitivity_perturbations: tuple[float, ...] = ()
    #: Which registered `core.composition` function composes belief along a simulated chain.
    #: A pack chooses a named function; it never supplies one.
    path_composition: str | None = None

    @model_validator(mode="after")
    def _check_perturbations(self) -> CounterfactualSimulationSpec:
        """Refuse a perturbation set that is unsequenced, repeating, or degenerate."""
        for perturbation in self.sensitivity_perturbations:
            if perturbation <= 0.0:
                raise ContractViolationError(
                    f"sensitivity_perturbations holds {perturbation}, which is not a "
                    "positive multiplier. A perturbation scales an outcome to test whether "
                    "the answer survives it; zero or a negative factor tests nothing."
                )
            if perturbation == 1.0:
                raise ContractViolationError(
                    "sensitivity_perturbations holds 1.0, which perturbs nothing and would "
                    "be reported as a sensitivity finding that found the answer stable."
                )
        if len(set(self.sensitivity_perturbations)) != len(self.sensitivity_perturbations):
            raise ContractViolationError(
                "sensitivity_perturbations repeats a multiplier; the sweep would report one "
                "finding twice and read as though two assumptions had been tested."
            )
        if list(self.sensitivity_perturbations) != sorted(self.sensitivity_perturbations):
            raise ContractViolationError(
                "sensitivity_perturbations is out of canonical sequence; two packs differing "
                "only in authoring sequence must hash alike (CONVENTIONS.md §11)."
            )
        return self


class ObjectiveWeightSpec(_Spec):
    """One objective's weight in the scalarization.

    A list of pairs rather than a mapping, for the reason every other ordinal list in this
    DSL is a list: a sequence has a canonical form that hashes stably, and the validator
    above can then refuse an unsequenced one rather than quietly sorting it and hiding that
    two packs were authored differently.
    """

    objective: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    weight: float = Field(ge=0.0)


class RecommendationSpec(_Spec):
    """Every domain-tunable number module 14 reads (schema 1.7.0, ADR-0079).

    prd.md §50 prints a ranking function in three lines and gives no weights; prd.md §55
    gives recommendation generation five seconds and gives no bounds. Both gaps are
    judgements, and ADR-0049, ADR-0053, ADR-0055, ADR-0063 and ADR-0071 have all ruled where
    a judgement lives: in the pack, declared, with an absent declaration meaning the policy
    CANNOT RUN rather than meaning a default. This is the sixth application of that rule.

    The weights are the sharpest of these. They decide which intervention an operator is
    shown first, and there is no arithmetic anywhere that can establish them -- they are a
    statement of what this organisation would rather have. Declaring them here means a
    reader can see the statement, disagree with it, and change it; and because the pack
    participates in `run_id`, a ranking produced under one set of weights can never be
    mistaken for a ranking produced under another.
    """

    #: Names a member of `core.scalarization.SCALARIZERS`. A pack chooses a named function;
    #: it never supplies one.
    scalarization: str | None = None
    #: Weight per objective, keyed by a member of `core.scalarization.OBJECTIVES`. Every
    #: objective is weighted EXPLICITLY, including at zero -- an omitted weight and a zero
    #: weight mean the same thing to the arithmetic and completely different things to a
    #: reader, and only one of the two can be reviewed.
    objective_weights: tuple[ObjectiveWeightSpec, ...] = ()
    #: The candidate count below which cut sets are enumerated exactly. Above it the search
    #: falls back to greedy set cover and the result is labelled NOT_PROVEN_MINIMAL
    #: (ADR-0076). Exact enumeration is exponential and prd.md §55 allows five seconds.
    cut_set_exact_ceiling: int | None = Field(default=None, ge=1)
    #: The largest number of nodes the cut-set search may consider at all.
    cut_set_node_cap: int | None = Field(default=None, ge=1)
    #: The largest number of interventions one recommended SET may hold. A set an operator
    #: cannot execute as a unit is not a recommendation, it is a project.
    portfolio_size_cap: int | None = Field(default=None, ge=1)
    #: How many recommendations one run may publish. prd.md §51's Workspace 6 is a ranked
    #: list a human reads, and a list nobody reaches the end of is a list nobody reads.
    maximum_recommendations: int | None = Field(default=None, ge=1)
    #: Principle 5's floor, on the DERIVED scalar of a recommendation's `ConfidenceVector`.
    #: Named `belief` rather than `confidence` for the reason `core.ranking` names its own
    #: parameter `chain_scalar`: LAW-EVIDENCE reserves the second word for the vector, and
    #: `check_confidence_is_a_vector.py` refuses a float that borrows it. A candidate below
    #: this is WITHHELD to the ledger naming the threshold, never published at a low score.
    #: Declared rather than hardcoded, because "how sure is sure enough to tell an operator
    #: to act" is the most domain-specific number in this file.
    minimum_belief_to_publish: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_weights(self) -> RecommendationSpec:
        """Refuse a weighting that is incomplete, repeating, unsequenced or degenerate."""
        if not self.objective_weights:
            return self
        names = [weight.objective for weight in self.objective_weights]
        if len(set(names)) != len(names):
            raise ContractViolationError(
                "objective_weights names an objective twice; one of the two would be "
                "silently discarded and the ranking would not be the declared one."
            )
        if names != sorted(names):
            raise ContractViolationError(
                "objective_weights is out of canonical sequence; two packs differing only "
                "in authoring sequence must hash alike (CONVENTIONS.md §11)."
            )
        missing = tuple(sorted(set(OBJECTIVES) - set(names)))
        if missing:
            raise ContractViolationError(
                f"objective_weights declares no weight for {', '.join(missing)}. Every "
                "objective is weighted explicitly, including at zero: an omitted weight and "
                "a zero weight mean the same thing to the arithmetic and completely "
                "different things to a reviewer of this pack."
            )
        unknown = tuple(sorted(set(names) - set(OBJECTIVES)))
        if unknown:
            raise ContractViolationError(
                f"objective_weights names {', '.join(unknown)}, which is not an objective "
                f"this engine trades off. Known: {', '.join(OBJECTIVES)}."
            )
        if sum(weight.weight for weight in self.objective_weights) <= 0.0:
            raise ContractViolationError(
                "objective_weights sums to zero; every candidate would score identically "
                "and the sequencing would be whatever the input happened to arrive in."
            )
        return self

    @model_validator(mode="after")
    def _check_cut_set_bounds(self) -> RecommendationSpec:
        """Refuse a ceiling that cannot bind, which would read as a bound and be none."""
        if (
            self.cut_set_exact_ceiling is not None
            and self.cut_set_node_cap is not None
            and self.cut_set_exact_ceiling > self.cut_set_node_cap
        ):
            raise ContractViolationError(
                f"cut_set_exact_ceiling ({self.cut_set_exact_ceiling}) exceeds "
                f"cut_set_node_cap ({self.cut_set_node_cap}), so the exact search would "
                "never yield to the greedy one and every result would claim minimality the "
                "search was never bounded enough to establish."
            )
        return self


class RulePackSpec(_Spec):
    """One authored rule pack: the whole document.

    `rule_pack_schema_version` is the DSL's version, not the pack's. `rule_pack_version` is
    the pack's own, and it participates in `run_id` (ADR-0013) -- so editing any rule
    changes the Run and therefore every artifact derived under it.
    """

    rule_pack_schema_version: str
    rule_pack_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    rule_pack_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    ontology_pack: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(min_length=1)
    rules: tuple[Rule, ...] = Field(min_length=1)
    #: Module 9's generator parameters. Additive at schema 1.1.0 and defaulted, so a
    #: pack authored against 1.0.0 still loads and simply runs no generator that needs one.
    candidate_generation: CandidateGenerationSpec = CandidateGenerationSpec()
    #: Module 10's domain knobs. Additive at schema 1.2.0 and defaulted on the same terms:
    #: a pack authored against 1.1.0 still loads, scores no component that needs a
    #: declaration, and says which knob was missing rather than supplying one (ADR-0053).
    confidence_scoring: ConfidenceScoringSpec = ConfidenceScoringSpec()
    #: The Causal Graph Builder's selection policy. Additive at schema 1.3.0 and defaulted
    #: on the same terms again: a pack authored against 1.2.0 still loads, constructs an
    #: empty causal graph, and says which policy did not run (ADR-0055).
    graph_construction: GraphConstructionSpec = GraphConstructionSpec()
    #: Module 12's traversal bounds and combination operators. Additive at schema 1.5.0 and
    #: defaulted on the same terms as the three blocks above: a pack authored against 1.4.0
    #: still loads, traverses nothing, and says which bound it would have needed.
    propagation_analysis: PropagationAnalysisSpec = PropagationAnalysisSpec()
    #: Module 11's ranking function and thresholds. Additive at schema 1.5.0, defaulted.
    root_cause_analysis: RootCauseAnalysisSpec = RootCauseAnalysisSpec()
    #: The structural pattern miner's support thresholds. Additive at schema 1.5.0,
    #: defaulted. The miner is not one of the prd.md §36 modules; see its README.
    pattern_mining: PatternMiningSpec = PatternMiningSpec()
    #: Module 13's simulation bounds. Additive at schema 1.6.0, defaulted, ADR-0049's
    #: absent-means-CANNOT-RUN rule for the fifth time: a pack authored against 1.5.0
    #: still loads, simulates nothing, and says which declaration it would have needed.
    counterfactual_simulation: CounterfactualSimulationSpec = CounterfactualSimulationSpec()
    #: Module 14's ranking weights and search bounds. Additive at schema 1.7.0, defaulted,
    #: ADR-0049's absent-means-CANNOT-RUN rule for the sixth time: a pack authored against
    #: 1.6.0 still loads, recommends nothing, and says which declaration it would have
    #: needed rather than ranking under weights nobody chose.
    recommendation: RecommendationSpec = RecommendationSpec()

    @model_validator(mode="before")
    @classmethod
    def _sequence_rules(cls, data: object) -> object:
        """Sort the rules by identifier, so one pack has one canonical form and one hash.

        Sorted HERE rather than demanded of the author. The hash is taken over the
        validated model, not the file bytes, so canonicalizing at load gives the
        determinism guarantee `CONVENTIONS.md` §11 needs while leaving a pack free to group
        its rules the way a reader wants them -- constraints together, then a chain in the
        sequence it actually runs in. Refusing an unsorted file would buy nothing and would
        force every pack into an sequence nobody can follow.
        """
        if not isinstance(data, dict):
            return data
        rules = data.get("rules")
        if not isinstance(rules, list):
            return data
        if not all(isinstance(rule, dict) and "id" in rule for rule in rules):
            return data
        return {**data, "rules": sorted(rules, key=lambda rule: str(rule["id"]))}

    @model_validator(mode="after")
    def _check_identifiers(self) -> RulePackSpec:
        """Refuse a duplicate rule identifier."""
        identifiers = [rule.id for rule in self.rules]
        duplicated = sorted({name for name in identifiers if identifiers.count(name) > 1})
        if duplicated:
            raise ContractViolationError(
                f"RulePackSpec repeats rule identifier(s) {duplicated}; every inferred edge "
                "records which rules fired, and two rules under one identifier make that "
                "record ambiguous (CONVENTIONS.md §8)."
            )
        if identifiers != sorted(identifiers):
            raise ContractViolationError(
                "RulePackSpec.rules is unsequenced after canonicalization; a caller "
                "constructed the model directly and bypassed `_sequence_rules`."
            )
        return self

    def enabled_rules(self) -> tuple[Rule, ...]:
        """Return the rules that may be evaluated, in canonical sequence."""
        return tuple(rule for rule in self.rules if rule.enabled)
