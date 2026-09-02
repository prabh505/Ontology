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

__all__ = [
    "COMPARISON_OPERATORS",
    "JUNCTION_OPERATORS",
    "PRESENCE_OPERATORS",
    "RULE_PACK_SCHEMA_VERSION",
    "AmplificationBody",
    "CausalBody",
    "ConditionExpression",
    "ConditionOperator",
    "ConstraintBody",
    "EntityRelation",
    "EventPattern",
    "InhibitionBody",
    "JointBody",
    "KnowledgeProvenance",
    "ModifierBody",
    "RelationDirection",
    "RoleAddress",
    "Rule",
    "RuleBody",
    "RuleKind",
    "RulePackSpec",
    "TemporalWindow",
]

#: The version of THIS schema, not of any pack authored against it. A pack states the
#: version it was written for and the loader refuses a mismatch, so a pack written against
#: an older DSL cannot be silently reinterpreted under a newer one.
RULE_PACK_SCHEMA_VERSION: Final[str] = "1.0.0"

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
