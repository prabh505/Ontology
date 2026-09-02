"""`SchemaMappingSpec` -- the declarative binding from source columns to ontology concepts.

**Layer rank L2, and in LAW-DOMAIN scope.** Nothing in this file names a column, a value, or
a concept of any domain. It declares the SHAPE of a binding; the bindings themselves are
data at `ontology/packs/<domain>/mapping.yaml`.

Three rules make this a mapping rather than a suggestion
--------------------------------------------------------
**No expression strings.** A transform is a member of a closed registry, exactly as a
measurement is a closed operator tree (ADR-0026). A transform the registry cannot express
needs a new registry member and an ADR, not an escape hatch -- an eval'd string in a data
file is executable code in a data file, and it defeats both determinism and review.

**No silent defaults.** `unmapped_value_policy` exists and its only admissible value is
`ERROR`. It is written as a field rather than assumed so that a future proposal to default
an unmapped value has to change a declared contract in a diff somebody reads.

**No unlisted columns.** Every column in the source header either carries a binding or
appears under `dropped_columns` with a reason (`docs/architecture.md` §5.2, step 3). An
unlisted column is a hard error, because "we did not map it" and "we did not notice it" are
indistinguishable otherwise, and only one of them is a decision.

The proposal guard
------------------
A document carrying `status: PROPOSED_UNCONFIRMED` is refused by the loader. Auto-suggestion
writes that header; a human removes it in a commit. That is the whole confirmation
mechanism, and it is a refusal rather than a warning because a warning is a thing that gets
read once.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalog.core.errors import ContractViolationError
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import Precision

__all__ = [
    "COMPARISON_OPERATORS",
    "JUNCTION_OPERATORS",
    "MAPPING_SCHEMA_VERSION",
    "NUMERIC_OPERATORS",
    "PRESENCE_OPERATORS",
    "PROPOSED_STATUS",
    "AttributeRef",
    "ColumnBindingSpec",
    "ConditionExpression",
    "ConditionOperator",
    "DropReasonSpec",
    "EventEmissionSpec",
    "IdentityBindingSpec",
    "MappingStatus",
    "OccurredAtPolicy",
    "OccurredAtSpec",
    "PrecedencePairSpec",
    "ReferentialConstraintSpec",
    "SchemaMappingSpec",
    "TargetKind",
    "TemporalBindingSpec",
    "TemporalDerivationCheckSpec",
    "TimezonePolicy",
    "Transform",
    "UnmappedValuePolicy",
    "ValueBindingSpec",
]

#: The DSL's own version, shared by every mapping. A mapping's own semver is
#: `mapping_version`, exactly as a pack has `pack_schema_version` and `ontology_version`.
MAPPING_SCHEMA_VERSION: Final[str] = "1.1.0"

SYMBOL_PATTERN: Final[str] = r"^[A-Z][A-Z0-9_]*$"
LOWER_SYMBOL_PATTERN: Final[str] = r"^[a-z][a-z0-9_]*$"


class _Spec(BaseModel):
    """Base for every mapping node: immutable and closed."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class AttributeRef(_Spec):
    """A reference to one mapped value, by ontology address rather than by source column.

    Emission rules speak ontology vocabulary throughout. Which column supplies
    `CONCEPT.attribute` is `column_bindings`' business and nothing above L2 needs to know
    it -- naming a column here would put source vocabulary into the input of the module
    that IS the LAW-EVENT boundary, for no gain.
    """

    concept: str = Field(pattern=SYMBOL_PATTERN)
    attribute: str = Field(pattern=LOWER_SYMBOL_PATTERN)

    @property
    def address(self) -> str:
        """Return the `CONCEPT.attribute` address this reference resolves against."""
        return f"{self.concept}.{self.attribute}"


class MappingStatus(str, Enum):
    """Whether a mapping document is a human commitment or a machine proposal."""

    CONFIRMED = "CONFIRMED"
    PROPOSED_UNCONFIRMED = "PROPOSED_UNCONFIRMED"


#: Convenience alias for the status the loader refuses.
PROPOSED_STATUS: Final[MappingStatus] = MappingStatus.PROPOSED_UNCONFIRMED


class TargetKind(str, Enum):
    """What an ontology-side binding target is."""

    ENTITY_ATTRIBUTE = "ENTITY_ATTRIBUTE"
    EVENT_ATTRIBUTE = "EVENT_ATTRIBUTE"
    EVENT_OCCURRED_AT = "EVENT_OCCURRED_AT"


class Transform(str, Enum):
    """The closed set of value transforms a binding may declare.

    Every member is total, deterministic, and either succeeds or reports a defect -- none
    of them guesses. The temporal members are the load-bearing ones: `PARSE_DATE_TO_DAY`
    WIDENS a date into the interval it actually denotes, and there is deliberately no
    member that narrows anything, because narrowing an absent or coarse instant is
    imputation (`CONVENTIONS.md` §10, ADR-0021).
    """

    IDENTITY = "IDENTITY"
    TRIM_WHITESPACE = "TRIM_WHITESPACE"
    NORMALIZE_UNICODE_NFC = "NORMALIZE_UNICODE_NFC"
    UPPERCASE = "UPPERCASE"
    EMPTY_TO_NULL = "EMPTY_TO_NULL"
    PARSE_INTEGER = "PARSE_INTEGER"
    PARSE_DECIMAL = "PARSE_DECIMAL"
    PARSE_BOOLEAN_FLAG = "PARSE_BOOLEAN_FLAG"
    PARSE_DATE_TO_DAY = "PARSE_DATE_TO_DAY"
    PARSE_DATETIME_TO_MINUTE = "PARSE_DATETIME_TO_MINUTE"


#: Transforms that produce a `TimeInterval`. Listed so the no-imputation law test can
#: enumerate exactly what it must check rather than trusting a naming convention.
TEMPORAL_TRANSFORMS: Final[frozenset[Transform]] = frozenset(
    {Transform.PARSE_DATE_TO_DAY, Transform.PARSE_DATETIME_TO_MINUTE}
)


class TimezonePolicy(str, Enum):
    """How a source instant with no stated offset is treated.

    `ASSUME_UTC` is the only member, and it stamps `ASSUMED` provenance on the interval it
    produces. There is no `ASSUME_LOCAL`: a local time with no named zone is not
    convertible, and picking a zone is a guess wearing a configuration field.
    """

    ASSUME_UTC = "ASSUME_UTC"


class UnmappedValuePolicy(str, Enum):
    """What happens to a source value with no binding. One member, on purpose."""

    ERROR = "ERROR"


class ColumnBindingSpec(_Spec):
    """One source column bound to one ontology target, through a transform chain."""

    column: str = Field(min_length=1)
    target_kind: TargetKind
    entity_type: str | None = Field(default=None, pattern=SYMBOL_PATTERN)
    event_type: str | None = Field(default=None, pattern=SYMBOL_PATTERN)
    attribute: str | None = Field(default=None, pattern=LOWER_SYMBOL_PATTERN)
    transforms: tuple[Transform, ...] = (Transform.IDENTITY,)
    required: bool = True
    """When true, a row whose value fails the transform chain is quarantined rather than
    carried forward with a hole."""

    @model_validator(mode="after")
    def _check_target(self) -> ColumnBindingSpec:
        """Refuse a binding whose target fields do not match its declared kind."""
        if self.target_kind is TargetKind.ENTITY_ATTRIBUTE:
            if self.entity_type is None or self.attribute is None:
                raise ValueError(
                    f"Column binding for {self.column!r} targets an entity attribute but "
                    "does not name both `entity_type` and `attribute`."
                )
            if self.event_type is not None:
                raise ValueError(
                    f"Column binding for {self.column!r} targets an entity attribute and "
                    "also names an `event_type`; a binding has exactly one target."
                )
            return self
        if self.event_type is None:
            raise ValueError(
                f"Column binding for {self.column!r} targets an event but does not name an "
                "`event_type`."
            )
        if self.entity_type is not None:
            raise ValueError(
                f"Column binding for {self.column!r} targets an event and also names an "
                "`entity_type`; a binding has exactly one target."
            )
        if self.target_kind is TargetKind.EVENT_ATTRIBUTE and self.attribute is None:
            raise ValueError(
                f"Column binding for {self.column!r} targets an event attribute but does "
                "not name the `attribute`."
            )
        if self.target_kind is TargetKind.EVENT_OCCURRED_AT and self.attribute is not None:
            raise ValueError(
                f"Column binding for {self.column!r} supplies an event's `occurred_at` and "
                f"also names attribute {self.attribute!r}; `occurred_at` is not an attribute."
            )
        return self


class ValueBindingSpec(_Spec):
    """Source values of one column mapped onto ontology symbols.

    `values` is an exhaustive map. A source value absent from it is an error under
    `unmapped_value_policy`, never a pass-through and never a default -- risk R-07 is
    precisely the failure where an unrecognised value quietly becomes something plausible.
    """

    column: str = Field(min_length=1)
    values: tuple[tuple[str, str], ...] = Field(min_length=1)
    unmapped_value_policy: UnmappedValuePolicy = UnmappedValuePolicy.ERROR
    describes_lifecycle_state_of: str | None = Field(default=None, pattern=SYMBOL_PATTERN)
    """When set, every mapped symbol must be a declared lifecycle state of that entity type.
    This is what turns the contradiction check from a heuristic into a check."""

    @model_validator(mode="after")
    def _check_values_are_unique(self) -> ValueBindingSpec:
        """Refuse a duplicated source value, making the map sequence-dependent."""
        seen = [source for source, _ in self.values]
        duplicates = sorted({item for item in seen if seen.count(item) > 1})
        if duplicates:
            raise ValueError(
                f"Value binding for column {self.column!r} maps {duplicates} more than once; "
                "which mapping wins would depend on document sequence."
            )
        return self


class IdentityBindingSpec(_Spec):
    """The columns whose values form one entity type's identifying key."""

    entity_type: str = Field(pattern=SYMBOL_PATTERN)
    key_columns: tuple[str, ...] = Field(min_length=1)
    observed_at: AttributeRef | None = None
    """The instant at which a record's statement ABOUT this entity was true.

    Attribute history needs an "as of", and a row rarely carries one per participant: a
    line on a purchase describes the buyer as they were when the purchase was made, not
    when the file was exported. Which instant that is, is domain knowledge, so it is
    declared rather than guessed. Omitted means the source dates its statements about this
    entity type not at all, and every attribute version carries the unbounded UNKNOWN
    interval -- which is honest, and is what a consumer needs to know before sequencing two
    versions by time."""


class TemporalBindingSpec(_Spec):
    """How one column becomes a `TimeInterval`, and what is being assumed to do it."""

    column: str = Field(min_length=1)
    source_format: str = Field(min_length=1)
    """The `strptime` pattern the source actually uses. DECLARED, never sniffed: the
    difference between `%m/%d/%Y` and `%d/%m/%Y` is silent for eleven days of every month,
    and a detector that guesses wrong produces a plausible date rather than an error."""
    precision: Precision
    timezone_policy: TimezonePolicy = TimezonePolicy.ASSUME_UTC
    source_states_offset: bool = False
    """Whether the source text carries an explicit UTC offset. When false the interval's
    provenance is `ASSUMED` and the report says so."""

    @model_validator(mode="after")
    def _check_precision_is_representable(self) -> TemporalBindingSpec:
        """Refuse a temporal binding that claims more precision than a transform can give.

        `EXACT` is refused outright. No parse of a source string yields a point instant that
        the engine is entitled to treat as exact; claiming it here would let imputation in
        through a configuration field (ADR-0021).
        """
        if self.precision is Precision.EXACT:
            raise ValueError(
                f"Temporal binding for column {self.column!r} declares EXACT precision. A "
                "parsed source instant is never exact; declare the granularity the source "
                "actually carries (CONVENTIONS.md §10, ADR-0021)."
            )
        return self

    @property
    def provenance(self) -> ProvenanceClass:
        """Return the provenance an interval built from this binding carries."""
        if self.precision is Precision.UNKNOWN:
            return ProvenanceClass.ASSUMED
        return ProvenanceClass.OBSERVED if self.source_states_offset else ProvenanceClass.ASSUMED


class PrecedencePairSpec(_Spec):
    """A declared "this instant may not precede that one" constraint between two columns.

    The domain knowledge lives here, in data. The checker reads a pair of column names and
    compares two instants; it does not know, and must not know, that one of them is a
    dispatch and the other a receipt.
    """

    id: str = Field(pattern=SYMBOL_PATTERN)
    earlier_column: str = Field(min_length=1)
    later_column: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    allow_equal: bool = True
    """Day-granular sources routinely record both instants on one date. Equality is
    admissible by default and is counted separately from a true inversion."""


class TemporalDerivationCheckSpec(_Spec):
    """A declared suspicion that one temporal column is ARITHMETIC on another.

    A column can carry more precision than it observed. If `finished_at` is really
    `started_at` plus a recorded day count, then its minutes and seconds were copied, not
    measured -- and sequencing two events by them would be sequencing them by a number the
    source manufactured. That is the failure LAW-TIME exists to prevent, arriving through a
    column that looks precise rather than through one that looks coarse.

    Nothing here guesses. A mapping author who suspects a derivation declares it, and the
    adapter MEASURES the agreement rate and the residual deltas over every row. The finding
    reports what was measured; it never asserts the derivation on the strength of a name.
    """

    id: str = Field(pattern=SYMBOL_PATTERN)
    column: str = Field(min_length=1)
    """The column suspected of carrying derived precision."""
    equals_column: str = Field(min_length=1)
    """The column its value is suspected of being computed from."""
    plus_days_column: str | None = Field(default=None, min_length=1)
    """An integer column added as whole days, when the derivation includes an offset."""
    rationale: str = Field(min_length=1)


class ReferentialConstraintSpec(_Spec):
    """A declared foreign key from one column onto an entity type's identifying key."""

    id: str = Field(pattern=SYMBOL_PATTERN)
    column: str = Field(min_length=1)
    references_entity_type: str = Field(pattern=SYMBOL_PATTERN)
    rationale: str = Field(min_length=1)


class DropReasonSpec(_Spec):
    """A source column deliberately not mapped, and why."""

    column: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ConditionOperator(str, Enum):
    """The closed operator set an emission condition may be built from.

    Closed, and shaped deliberately like `ontology_runtime.dsl.ExpressionOperator`. The
    alternative -- a predicate string evaluated at run time -- is executable code inside a
    data file, which ADR-0026 refused for measurements and which is refused here for the
    same reasons: it defeats review, it defeats hashing, and it cannot be checked before it
    runs. A condition that needs an operator absent here needs the operator added, with an
    ADR, and every mapping revalidated.
    """

    ALWAYS = "ALWAYS"
    """Holds for every record. The honest way to say "this occurrence is implied by the
    record existing at all" -- which is a real derivation, and one an author should have to
    write down rather than express as an omitted condition."""

    ATTRIBUTE = "ATTRIBUTE"
    """A leaf reading one mapped concept attribute."""

    CONSTANT = "CONSTANT"
    """A leaf carrying one literal value."""

    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    GREATER_THAN = "GREATER_THAN"
    LESS_THAN = "LESS_THAN"

    IN = "IN"
    """The operand's value is a member of the declared `values` set."""

    IS_PRESENT = "IS_PRESENT"
    IS_ABSENT = "IS_ABSENT"

    AND = "AND"
    OR = "OR"
    NOT = "NOT"


#: Operators comparing exactly two leaves.
COMPARISON_OPERATORS: Final[frozenset[ConditionOperator]] = frozenset(
    {
        ConditionOperator.EQUALS,
        ConditionOperator.NOT_EQUALS,
        ConditionOperator.GREATER_THAN,
        ConditionOperator.LESS_THAN,
    }
)

#: Operators whose two operands are compared as NUMBERS rather than as text. Listed so the
#: evaluator never has to guess which comparison a mapping meant, and so a non-numeric
#: operand under one of them is a loud defect rather than a lexicographic surprise --
#: `'9' > '10'` is true as text and false as arithmetic.
NUMERIC_OPERATORS: Final[frozenset[ConditionOperator]] = frozenset(
    {ConditionOperator.GREATER_THAN, ConditionOperator.LESS_THAN}
)

#: Operators taking two or more sub-conditions.
JUNCTION_OPERATORS: Final[frozenset[ConditionOperator]] = frozenset(
    {ConditionOperator.AND, ConditionOperator.OR}
)

#: Operators taking exactly one `ATTRIBUTE` leaf.
PRESENCE_OPERATORS: Final[frozenset[ConditionOperator]] = frozenset(
    {ConditionOperator.IS_PRESENT, ConditionOperator.IS_ABSENT}
)


class ConditionExpression(_Spec):
    """One node of an emission condition tree.

    Recursive, closed, and inert. Nothing here is evaluated by this module; the tree is data
    that `event_generator` walks. A condition expressed as a tree can be inspected, diffed
    and hashed before anyone runs it. A condition expressed as a string has to be executed
    before anyone knows what it says.

    `concept` is an ontology symbol -- an entity type or an event type -- and `attribute` is
    the attribute name declared on it. The pair addresses one value of a mapped record. The
    tree therefore speaks ONTOLOGY vocabulary, never source-column vocabulary: which column
    supplies `SOME_TYPE.some_attribute` is `column_bindings`' business, and which source
    value means `SOME_SYMBOL` is `value_bindings`' business. That separation is what keeps a
    condition readable against the pack it targets rather than against the file it came
    from.
    """

    op: ConditionOperator
    concept: str | None = Field(default=None, pattern=SYMBOL_PATTERN)
    attribute: str | None = Field(default=None, pattern=LOWER_SYMBOL_PATTERN)
    value: str | None = None
    values: tuple[str, ...] = ()
    operands: tuple[ConditionExpression, ...] = ()

    @property
    def address(self) -> str:
        """Return the `CONCEPT.attribute` address of an `ATTRIBUTE` leaf."""
        if self.op is not ConditionOperator.ATTRIBUTE:
            raise ContractViolationError(
                f"ConditionExpression.address read on a {self.op.value} node; only an "
                "ATTRIBUTE leaf addresses a mapped value."
            )
        return f"{self.concept}.{self.attribute}"

    @model_validator(mode="after")
    def _check_shape(self) -> ConditionExpression:
        """Enforce the arity and leaf shape each operator admits."""
        leaf_fields_used = bool(self.concept or self.attribute or self.value is not None)
        if self.op is ConditionOperator.ALWAYS:
            if leaf_fields_used or self.values or self.operands:
                raise ContractViolationError(
                    "an ALWAYS condition carries nothing else -- no operands, no leaf "
                    "fields, no 'values'."
                )
            return self
        if self.op is ConditionOperator.ATTRIBUTE:
            if not (self.concept and self.attribute) or self.operands or self.values:
                raise ContractViolationError(
                    "an ATTRIBUTE condition carries 'concept' and 'attribute' alone."
                )
            if self.value is not None:
                raise ContractViolationError(
                    "an ATTRIBUTE condition carries no 'value'; it READS a value."
                )
            return self
        if self.op is ConditionOperator.CONSTANT:
            if self.value is None or self.concept or self.attribute or self.operands:
                raise ContractViolationError("a CONSTANT condition carries 'value' alone.")
            return self
        if leaf_fields_used:
            raise ContractViolationError(
                f"a {self.op.value} condition is an operator node and carries only "
                "'operands' (and 'values' for IN); leaf fields belong on ATTRIBUTE and "
                "CONSTANT nodes."
            )
        if self.op in COMPARISON_OPERATORS:
            if len(self.operands) != 2:
                raise ContractViolationError(
                    f"a {self.op.value} condition compares exactly two leaves; it was given "
                    f"{len(self.operands)}."
                )
            for operand in self.operands:
                if operand.op not in (ConditionOperator.ATTRIBUTE, ConditionOperator.CONSTANT):
                    raise ContractViolationError(
                        f"a {self.op.value} condition compares leaves; operand "
                        f"{operand.op.value} is an operator node."
                    )
            if self.values:
                raise ContractViolationError(
                    f"a {self.op.value} condition declares 'values'; only IN admits them."
                )
            return self
        if self.op is ConditionOperator.IN:
            if len(self.operands) != 1 or self.operands[0].op is not ConditionOperator.ATTRIBUTE:
                raise ContractViolationError("an IN condition takes exactly one ATTRIBUTE operand.")
            if not self.values:
                raise ContractViolationError(
                    "an IN condition declares no 'values'; membership of an empty set is "
                    "false for every record, which is a rule that never fires written as a "
                    "rule that looks like it might."
                )
            if len(set(self.values)) != len(self.values):
                raise ContractViolationError("an IN condition repeats a member of 'values'.")
            if list(self.values) != sorted(self.values):
                raise ContractViolationError(
                    "an IN condition's 'values' must be sequenced (CONVENTIONS.md §11); an "
                    "unsequenced set serializes two ways and changes mapping_hash for no "
                    "change in meaning."
                )
            return self
        if self.op in PRESENCE_OPERATORS:
            if len(self.operands) != 1 or self.operands[0].op is not ConditionOperator.ATTRIBUTE:
                raise ContractViolationError(
                    f"a {self.op.value} condition takes exactly one ATTRIBUTE operand."
                )
            if self.values:
                raise ContractViolationError(
                    f"a {self.op.value} condition declares 'values'; only IN admits them."
                )
            return self
        if self.op is ConditionOperator.NOT:
            if len(self.operands) != 1:
                raise ContractViolationError(
                    f"a NOT condition takes exactly one operand; it was given "
                    f"{len(self.operands)}."
                )
            if self.values:
                raise ContractViolationError("a NOT condition declares 'values'.")
            return self
        if len(self.operands) < 2:
            raise ContractViolationError(
                f"a {self.op.value} condition takes two or more operands; it was given "
                f"{len(self.operands)}. A junction of one is the operand itself, written so "
                "as to look like a decision."
            )
        if self.values:
            raise ContractViolationError(f"a {self.op.value} condition declares 'values'.")
        return self


class OccurredAtPolicy(str, Enum):
    """How an emitted event's `TimeInterval` is obtained.

    Declared per emission, never chosen by the generator. Every member either READS an
    instant the source supplied or WIDENS/OFFSETS one; none narrows, and none manufactures
    a bound from nothing (`CONVENTIONS.md` §10, ADR-0021).
    """

    FROM_TEMPORAL_BINDING = "FROM_TEMPORAL_BINDING"
    """The interval the declared temporal binding produced, unchanged. The only policy
    admissible for an OBSERVED event type: an observed occurrence is placed by the source
    or it is not observed."""

    BOUNDED_BETWEEN = "BOUNDED_BETWEEN"
    """The occurrence is known to fall between two instants the source did supply:
    `t_earliest` from the earlier reference's lower bound, `t_latest` from the later
    reference's upper bound. The result carries INFERRED provenance and therefore never
    yields a CERTAIN verdict -- narrowing a window from other evidence is admissible,
    certifying an edge on it is not."""

    OFFSET_FROM = "OFFSET_FROM"
    """The occurrence is a whole-day offset from an observed instant, the offset read from
    an integer attribute. INFERRED provenance, and the ANCHOR's precision -- adding whole
    days to a day-granular instant yields a day-granular instant and never a finer one."""

    UNKNOWN = "UNKNOWN"
    """No field places this occurrence. The unbounded interval with ASSUMED provenance, the
    representation that claims nothing. An event carrying it may sit on a timeline and may
    never participate in an INFERRED causal edge."""


class OccurredAtSpec(_Spec):
    """The declared derivation of one emitted event's interval."""

    policy: OccurredAtPolicy
    anchor: AttributeRef | None = None
    """FROM_TEMPORAL_BINDING and OFFSET_FROM: the instant read."""
    earliest: AttributeRef | None = None
    latest: AttributeRef | None = None
    """BOUNDED_BETWEEN: the two instants the occurrence is known to fall between."""
    plus_days: AttributeRef | None = None
    """OFFSET_FROM: the integer attribute carrying the whole-day offset."""
    derivation: str = Field(min_length=1)
    """Prose naming what was done, carried verbatim into `TimeInterval.source` so a bound
    can be traced without reading the module that produced it (ADR-0021)."""

    @model_validator(mode="after")
    def _check_policy_references(self) -> OccurredAtSpec:
        """Require exactly the references the declared policy reads, and no others."""
        required: dict[OccurredAtPolicy, tuple[str, ...]] = {
            OccurredAtPolicy.FROM_TEMPORAL_BINDING: ("anchor",),
            OccurredAtPolicy.BOUNDED_BETWEEN: ("earliest", "latest"),
            OccurredAtPolicy.OFFSET_FROM: ("anchor", "plus_days"),
            OccurredAtPolicy.UNKNOWN: (),
        }
        expected = set(required[self.policy])
        for name in ("anchor", "earliest", "latest", "plus_days"):
            supplied = getattr(self, name) is not None
            if name in expected and not supplied:
                raise ContractViolationError(
                    f"occurred_at policy {self.policy.value} requires {name!r}."
                )
            if name not in expected and supplied:
                raise ContractViolationError(
                    f"occurred_at policy {self.policy.value} does not read {name!r}; an "
                    "anchor the policy ignores is a statement nobody checks."
                )
        if self.policy is OccurredAtPolicy.BOUNDED_BETWEEN and self.earliest == self.latest:
            raise ContractViolationError(
                "occurred_at BOUNDED_BETWEEN names one reference twice; bounding an "
                "occurrence between an instant and itself claims a precision no field "
                "supplied."
            )
        return self


class EventEmissionSpec(_Spec):
    """When one ontology event type is witnessed by one mapped record.

    This is the machine-readable half of the pack's `derivation.basis`, which is prose. The
    pack says WHAT was reconstructed and how sure it is; this says WHICH RECORDS witness it.
    The two live apart because the basis is a claim about the domain and the condition is a
    claim about one dataset's encoding of it -- a second dataset for the same domain reuses
    the pack unchanged and writes its own conditions.

    **The rule cannot promote provenance.** Nothing here names a provenance class. The
    emitted event takes the class its event type declares, and the pack refuses OBSERVED on
    a DERIVED type (ADR-0029). A heuristic therefore has no path to an OBSERVED event, by
    construction rather than by review.

    **Participants are not declared here either.** The pack's `ParticipantSpec` already
    states role -> entity type, and the mapping declares exactly one identity binding per
    entity type, so participant resolution is fully determined. Restating it would create a
    second place for the two to disagree.
    """

    event_type: str = Field(pattern=SYMBOL_PATTERN)
    when: ConditionExpression
    occurred_at: OccurredAtSpec
    rationale: str = Field(min_length=1)
    """Why these records witness this occurrence, in the author's words. Read against the
    pack's `derivation.basis` for the same event type; a divergence between the two is the
    thing a reviewer is looking for."""
    trigger_attribute: str | None = Field(default=None, pattern=LOWER_SYMBOL_PATTERN)
    """An attribute of this event type whose value is the proximate mechanism, recorded on
    `Event.trigger` (ADR-0020). No inference path may read it."""


class SchemaMappingSpec(_Spec):
    """One dataset's complete binding to one ontology pack.

    Stability: `draft`. Module 2 owns it and module 2 has just been built; freezing it now
    would be the assertion-not-specification error OQ-009 exists to prevent.
    """

    mapping_schema_version: str = Field(min_length=1)
    mapping_id: str = Field(pattern=LOWER_SYMBOL_PATTERN)
    mapping_version: str = Field(min_length=1)
    ontology_pack: str = Field(pattern=LOWER_SYMBOL_PATTERN)
    description: str = Field(min_length=1)
    status: MappingStatus = MappingStatus.CONFIRMED

    column_bindings: tuple[ColumnBindingSpec, ...] = ()
    value_bindings: tuple[ValueBindingSpec, ...] = ()
    identity_bindings: tuple[IdentityBindingSpec, ...] = ()
    temporal_bindings: tuple[TemporalBindingSpec, ...] = ()
    precedence_pairs: tuple[PrecedencePairSpec, ...] = ()
    temporal_derivation_checks: tuple[TemporalDerivationCheckSpec, ...] = ()
    referential_constraints: tuple[ReferentialConstraintSpec, ...] = ()
    dropped_columns: tuple[DropReasonSpec, ...] = ()
    event_emissions: tuple[EventEmissionSpec, ...] = ()

    @model_validator(mode="after")
    def _check_no_column_is_both_bound_and_dropped(self) -> SchemaMappingSpec:
        """Refuse a column that is both mapped and declared dropped."""
        bound = {binding.column for binding in self.column_bindings}
        dropped = {entry.column for entry in self.dropped_columns}
        overlap = sorted(bound & dropped)
        if overlap:
            raise ValueError(
                f"Columns {overlap} are both bound and listed under `dropped_columns`. A "
                "column is mapped or it is dropped; being both means one of the two "
                "statements is untrue and nothing says which."
            )
        return self

    @model_validator(mode="after")
    def _check_one_identity_per_entity_type(self) -> SchemaMappingSpec:
        """Refuse two identifying keys for one entity type.

        Load-bearing, not tidiness. An emission rule declares no participants precisely
        because the pack's `ParticipantSpec` names a role's entity type and the mapping
        names that type's key, so the participant is fully determined. Two keys would make
        it two participants, and which one an event named would depend on document sequence.
        """
        declared = [binding.entity_type for binding in self.identity_bindings]
        repeated = sorted({name for name in declared if declared.count(name) > 1})
        if repeated:
            raise ValueError(
                f"Entity types {repeated} carry more than one identity binding. Participant "
                "resolution reads exactly one key per entity type; two would make which "
                "participant an event names a function of document sequence."
            )
        return self

    @model_validator(mode="after")
    def _check_one_emission_per_event_type(self) -> SchemaMappingSpec:
        """Refuse two emission rules for one event type.

        Two rules for one type would make "did this occurrence happen" a disjunction
        assembled by document sequence, and the two could disagree about `occurred_at`
        while both fired. An author who means a disjunction writes one rule with an `OR`,
        which is visible in the diff and hashes as one thing.
        """
        declared = [emission.event_type for emission in self.event_emissions]
        repeated = sorted({name for name in declared if declared.count(name) > 1})
        if repeated:
            raise ValueError(
                f"Event types {repeated} carry more than one emission rule. One event type "
                "has one rule; a disjunction is written with OR inside it, not as two "
                "entries whose combination depends on document sequence."
            )
        return self
