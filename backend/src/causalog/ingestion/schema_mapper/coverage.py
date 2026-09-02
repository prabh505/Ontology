"""Mapping coverage: what the ontology requires, what the mapping supplies, what breaks.

Two halves, and the second is the one that matters.

**Does every binding resolve?** A binding naming a concept the pack does not declare is an
error, and so is a bound column absent from the source header. That half is bookkeeping.

**Does every ontology-required field have a binding, and if not, what stops working?** A
coverage report that says "3 concepts unmapped" tells a reader nothing they can act on. Every
finding here carries a `downstream_consequence` naming the module that fails and what it
fails to produce -- and the field is `min_length=1` on the model, so the requirement is
structural rather than a habit that erodes.

Derived event types are `NOT_RUNNABLE`, not clean
-------------------------------------------------
ADR-0029: in a source that logs one occurrence and implies twenty, only the observed event
types can have a column supplying `occurred_at`. The rest are reconstructed by module 4.
Their coverage therefore **cannot be checked here** -- and this repository has twice mistaken
a check that could not run for one that passed (DEF-0001, OQ-014), so it is reported at
`NOT_RUNNABLE` rather than skipped into silence.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field

from causalog.ingestion.schema_mapper.apply import mapped_addresses
from causalog.ingestion.schema_mapper.dsl import (
    ConditionExpression,
    ConditionOperator,
    EventEmissionSpec,
    OccurredAtPolicy,
    SchemaMappingSpec,
    TargetKind,
)
from causalog.ontology_runtime.diagnostics import Severity
from causalog.ontology_runtime.dsl import (
    AttributeOrigin,
    EventTypeSpec,
    ExpressionOperator,
    MeasurementExpression,
    ObservationMode,
    ResolvedPack,
)

__all__ = ["CoverageReport", "MappingFinding", "assess_coverage"]


class MappingFinding(BaseModel):
    """One statement about the mapping, and what it costs downstream."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    severity: Severity
    code: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    """The concept or column the finding is about, as a dotted address."""
    message: str = Field(min_length=1)
    downstream_consequence: str = Field(min_length=1)
    """What stops working. Never empty: a finding without a consequence is an observation,
    and observations are what reports get ignored for."""

    def render(self) -> str:
        """Return the one-line form: severity, code, subject, message, consequence."""
        return (
            f"[{self.severity.value}] {self.code} {self.subject}: {self.message} "
            f"=> {self.downstream_consequence}"
        )


class CoverageReport(BaseModel):
    """Every finding about one mapping against one pack, plus the counts behind them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mapping_id: str
    mapping_version: str
    ontology_pack: str
    ontology_version: str
    findings: tuple[MappingFinding, ...] = ()
    #: DISTINCT source columns bound, not binding entries. Several bindings routinely name
    #: one column, so the two differ (DataCo: 55 bindings over 40 columns). This is the one
    #: that reconciles against the header, and it is printed beside the header count.
    bound_column_count: int = 0
    #: Binding entries declared. Reported separately so `bound + dropped == header` holds
    #: on the face of the report instead of appearing to overshoot it.
    binding_count: int = 0
    dropped_column_count: int = 0
    header_column_count: int | None = None

    @property
    def errors(self) -> tuple[MappingFinding, ...]:
        """Return the findings that make the mapping unusable."""
        return tuple(item for item in self.findings if item.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[MappingFinding, ...]:
        """Return the findings that do not block use."""
        return tuple(item for item in self.findings if item.severity is Severity.WARNING)

    @property
    def not_runnable(self) -> tuple[MappingFinding, ...]:
        """Return the checks that could not be performed."""
        return tuple(item for item in self.findings if item.severity is Severity.NOT_RUNNABLE)

    def render(self) -> str:
        """Render every finding, most severe first, one per line."""
        sequence = {Severity.ERROR: 0, Severity.NOT_RUNNABLE: 1, Severity.WARNING: 2}
        ranked = sorted(
            self.findings,
            key=lambda item: (sequence[item.severity], item.code, item.subject),
        )
        return "\n".join(item.render() for item in ranked)


def _as_clause(text: str) -> str:
    """Return `text` ending in exactly one period, for embedding mid-sentence.

    Pack-authored prose sometimes ends in a period and sometimes does not, and a finding is
    a committed document. Normalising here is cheaper than asking every pack author to end
    a field consistently, and far cheaper than a reader wondering whether `..` means
    something.
    """
    stripped = text.strip() or "its declared basis"
    return stripped if stripped.endswith(".") else stripped + "."


def _attribute_leaves(expression: MeasurementExpression) -> Iterable[tuple[str, str]]:
    """Yield every `(event_type, attribute)` an operator tree reads."""
    if expression.op is ExpressionOperator.ATTRIBUTE:
        if expression.event_type and expression.attribute:
            yield (expression.event_type, expression.attribute)
        return
    for operand in expression.operands:
        yield from _attribute_leaves(operand)


def _event_attribute_targets(mapping: SchemaMappingSpec) -> set[tuple[str, str]]:
    """Return every `(event_type, attribute)` the mapping binds."""
    return {
        (binding.event_type, binding.attribute)
        for binding in mapping.column_bindings
        if binding.target_kind is TargetKind.EVENT_ATTRIBUTE
        and binding.event_type
        and binding.attribute
    }


def _entity_attribute_targets(mapping: SchemaMappingSpec) -> set[tuple[str, str]]:
    """Return every `(entity_type, attribute)` the mapping binds."""
    return {
        (binding.entity_type, binding.attribute)
        for binding in mapping.column_bindings
        if binding.target_kind is TargetKind.ENTITY_ATTRIBUTE
        and binding.entity_type
        and binding.attribute
    }


def _occurred_at_targets(mapping: SchemaMappingSpec) -> set[str]:
    """Return every event type the mapping supplies an `occurred_at` for."""
    return {
        binding.event_type
        for binding in mapping.column_bindings
        if binding.target_kind is TargetKind.EVENT_OCCURRED_AT and binding.event_type
    }


def _check_targets_resolve(mapping: SchemaMappingSpec, pack: ResolvedPack) -> list[MappingFinding]:
    """Report every binding whose ontology target the pack does not declare."""
    findings: list[MappingFinding] = []
    entity_attributes = {
        (entity.id, attribute.name)
        for entity in pack.entity_types
        for attribute in entity.attributes
    }
    entity_ids = {entity.id for entity in pack.entity_types}
    event_attributes = {
        (event.id, attribute.name)
        for event in pack.event_types
        for attribute in event.required_attributes
    }
    event_ids = {event.id for event in pack.event_types}

    for binding in mapping.column_bindings:
        address = f"column_bindings[{binding.column}]"
        if binding.target_kind is TargetKind.ENTITY_ATTRIBUTE:
            target = (binding.entity_type or "", binding.attribute or "")
            if target not in entity_attributes:
                findings.append(
                    MappingFinding(
                        severity=Severity.ERROR,
                        code="MAP-E-UNKNOWN-ENTITY-ATTRIBUTE",
                        subject=address,
                        message=(
                            f"binds to {target[0]}.{target[1]}, which pack "
                            f"'{pack.pack_id}' does not declare"
                        ),
                        downstream_consequence=(
                            "Module 3 (Entity Extractor) would write an attribute no "
                            "consumer can interpret; the mapping is refused instead."
                        ),
                    )
                )
            continue
        if (binding.event_type or "") not in event_ids:
            findings.append(
                MappingFinding(
                    severity=Severity.ERROR,
                    code="MAP-E-UNKNOWN-EVENT-TYPE",
                    subject=address,
                    message=(
                        f"binds to event type {binding.event_type!r}, which pack "
                        f"'{pack.pack_id}' does not declare"
                    ),
                    downstream_consequence=(
                        "Module 4 (Event Generator) would emit an event of a type the "
                        "ontology cannot validate against a process definition."
                    ),
                )
            )
            continue
        if binding.target_kind is TargetKind.EVENT_ATTRIBUTE:
            target = (binding.event_type or "", binding.attribute or "")
            if target not in event_attributes:
                findings.append(
                    MappingFinding(
                        severity=Severity.ERROR,
                        code="MAP-E-UNKNOWN-EVENT-ATTRIBUTE",
                        subject=address,
                        message=(
                            f"binds to {target[0]}.{target[1]}, which is not a declared "
                            "required attribute of that event type"
                        ),
                        downstream_consequence=(
                            "Module 4 would carry an attribute no measurement may read; "
                            "a measurement may only read attributes an event type "
                            "guarantees (docs/ontology.md §4 step 7)."
                        ),
                    )
                )

    for identity in mapping.identity_bindings:
        if identity.entity_type not in entity_ids:
            findings.append(
                MappingFinding(
                    severity=Severity.ERROR,
                    code="MAP-E-UNKNOWN-ENTITY-TYPE",
                    subject=f"identity_bindings[{identity.entity_type}]",
                    message=f"pack '{pack.pack_id}' declares no such entity type",
                    downstream_consequence=(
                        "Module 3 cannot mint an entity identifier for a type that does "
                        "not exist; every relationship referencing it would be an orphan."
                    ),
                )
            )

    for constraint in mapping.referential_constraints:
        if constraint.references_entity_type not in entity_ids:
            findings.append(
                MappingFinding(
                    severity=Severity.ERROR,
                    code="MAP-E-UNKNOWN-REFERENCE-TARGET",
                    subject=f"referential_constraints[{constraint.id}]",
                    message=(
                        f"references entity type {constraint.references_entity_type!r}, "
                        "which the pack does not declare"
                    ),
                    downstream_consequence=(
                        "The orphan-key check cannot run, so orphan foreign keys would "
                        "reach module 3 uncounted."
                    ),
                )
            )
    return findings


def _check_lifecycle_states(mapping: SchemaMappingSpec, pack: ResolvedPack) -> list[MappingFinding]:
    """Report a value binding that maps onto a state the entity's lifecycle does not have."""
    findings: list[MappingFinding] = []
    states_by_entity = {
        entity.id: set(entity.lifecycle.states) if entity.lifecycle else set()
        for entity in pack.entity_types
    }
    for binding in mapping.value_bindings:
        target_entity = binding.describes_lifecycle_state_of
        if target_entity is None:
            continue
        declared = states_by_entity.get(target_entity)
        if declared is None:
            findings.append(
                MappingFinding(
                    severity=Severity.ERROR,
                    code="MAP-E-UNKNOWN-ENTITY-TYPE",
                    subject=f"value_bindings[{binding.column}]",
                    message=(
                        f"declares lifecycle states of {target_entity!r}, which the pack "
                        "does not declare"
                    ),
                    downstream_consequence=(
                        "The state-machine contradiction check cannot run for this column."
                    ),
                )
            )
            continue
        for source_value, symbol in binding.values:
            if symbol not in declared:
                findings.append(
                    MappingFinding(
                        severity=Severity.ERROR,
                        code="MAP-E-UNKNOWN-LIFECYCLE-STATE",
                        subject=f"value_bindings[{binding.column}][{source_value}]",
                        message=(
                            f"maps to {symbol!r}, which is not a declared lifecycle state "
                            f"of {target_entity}"
                        ),
                        downstream_consequence=(
                            "Module 6 (State Engine) would be handed a state with no "
                            "transitions into or out of it, producing a lifecycle no "
                            "process definition can validate."
                        ),
                    )
                )
    return findings


def _check_required_concepts(
    mapping: SchemaMappingSpec, pack: ResolvedPack
) -> list[MappingFinding]:
    """Report every ontology-required field the mapping does not supply."""
    findings: list[MappingFinding] = []
    bound_entity_attributes = _entity_attribute_targets(mapping)
    bound_event_attributes = _event_attribute_targets(mapping)
    bound_occurred_at = _occurred_at_targets(mapping)
    identity_entities = {identity.entity_type for identity in mapping.identity_bindings}

    for entity in pack.entity_types:
        if entity.identifying_keys and entity.id not in identity_entities:
            findings.append(
                MappingFinding(
                    severity=Severity.ERROR,
                    code="MAP-E-IDENTITY-UNBOUND",
                    subject=f"entity_types[{entity.id}]",
                    message="declares identifying keys but the mapping binds no identity",
                    downstream_consequence=(
                        "Module 3 cannot mint a content-addressed entity_id, so every "
                        "event participating in this entity type is unattributable and "
                        "no timeline can be grouped by it."
                    ),
                )
            )
        for attribute in entity.attributes:
            if attribute.origin is not AttributeOrigin.SOURCE_COLUMN:
                continue
            if (entity.id, attribute.name) in bound_entity_attributes:
                continue
            is_key = attribute.name in entity.identifying_keys
            findings.append(
                MappingFinding(
                    severity=Severity.ERROR if is_key else Severity.WARNING,
                    code="MAP-E-KEY-UNBOUND" if is_key else "MAP-W-ENTITY-ATTRIBUTE-UNBOUND",
                    subject=f"entity_types[{entity.id}].{attribute.name}",
                    message=(
                        f"declares origin SOURCE_COLUMN ({attribute.source_column!r}) but "
                        "the mapping binds no column to it"
                    ),
                    downstream_consequence=(
                        "The entity's identifying key cannot be assembled, so module 3 "
                        "cannot mint its identifier."
                        if is_key
                        else "Module 3 emits the entity without this attribute; anything "
                        "reading it -- a measurement, a label, a relationship key -- has "
                        "nothing to read."
                    ),
                )
            )

    for event in pack.event_types:
        _append_event_findings(event, bound_occurred_at, bound_event_attributes, findings)

    for measurement in pack.measurement_definitions:
        for event_type, leaf_name in sorted(set(_attribute_leaves(measurement.expression))):
            if (event_type, leaf_name) in bound_event_attributes:
                continue
            findings.append(
                MappingFinding(
                    severity=Severity.ERROR,
                    code="MAP-E-MEASUREMENT-INPUT-UNBOUND",
                    subject=f"measurement_definitions[{measurement.id}]",
                    message=(
                        f"reads {event_type}.{leaf_name}, which the mapping binds no " "column to"
                    ),
                    downstream_consequence=(
                        f"The measurement {measurement.id} cannot be computed, so any "
                        "ranking, threshold or explanation that cites it is unavailable "
                        "for every run over this dataset."
                    ),
                )
            )
    return findings


def _append_event_findings(
    event: EventTypeSpec,
    bound_occurred_at: set[str],
    bound_event_attributes: set[tuple[str, str]],
    findings: list[MappingFinding],
) -> None:
    """Add the occurrence and attribute findings for one event type."""
    if event.observation is ObservationMode.OBSERVED:
        if event.id not in bound_occurred_at:
            findings.append(
                MappingFinding(
                    severity=Severity.ERROR,
                    code="MAP-E-OCCURRED-AT-UNBOUND",
                    subject=f"event_types[{event.id}]",
                    message=(
                        "is declared OBSERVED but the mapping binds no column to its " "occurred_at"
                    ),
                    downstream_consequence=(
                        "Module 4 cannot place this event in time. Without an instant "
                        "there is no interval, so LAW-TIME can return no verdict and the "
                        "event can participate in no causal edge at all."
                    ),
                )
            )
    elif event.id not in bound_occurred_at:
        findings.append(
            MappingFinding(
                severity=Severity.NOT_RUNNABLE,
                code="MAP-N-DERIVED-OCCURRENCE-DEFERRED",
                subject=f"event_types[{event.id}]",
                message=(
                    "is declared DERIVED, so its occurrence is reconstructed rather than "
                    "read from a column; coverage of its instant was NOT CHECKED here"
                ),
                downstream_consequence=(
                    "Module 4 derives this event and its interval from "
                    f"{_as_clause(event.derivation.basis if event.derivation else '')} "
                    "Whether that derivation is sound is risk R-16 and is checked by "
                    "nothing in this repository."
                ),
            )
        )

    for attribute in event.required_attributes:
        if attribute.origin is not AttributeOrigin.SOURCE_COLUMN:
            continue
        if (event.id, attribute.name) in bound_event_attributes:
            continue
        findings.append(
            MappingFinding(
                severity=Severity.ERROR,
                code="MAP-E-EVENT-ATTRIBUTE-UNBOUND",
                subject=f"event_types[{event.id}].{attribute.name}",
                message=(
                    f"is a required attribute with origin SOURCE_COLUMN "
                    f"({attribute.source_column!r}) and the mapping binds no column to it"
                ),
                downstream_consequence=(
                    "Module 4 cannot construct this event type at all: a required "
                    "attribute is required, and filling it with a default would be an "
                    "invented observation."
                ),
            )
        )


def _check_columns(
    mapping: SchemaMappingSpec, header: Sequence[str] | None
) -> list[MappingFinding]:
    """Report columns bound but absent, and columns present but neither bound nor dropped."""
    if header is None:
        return [
            MappingFinding(
                severity=Severity.NOT_RUNNABLE,
                code="MAP-N-HEADER-UNAVAILABLE",
                subject="column_bindings",
                message=(
                    "no source header was supplied, so 'every column is bound or "
                    "justified' was NOT CHECKED"
                ),
                downstream_consequence=(
                    "A column the source carries and the mapping never mentions would "
                    "reach nobody's attention. Supply the probed header to run this check."
                ),
            )
        ]
    present = set(header)
    accounted = {binding.column for binding in mapping.column_bindings}
    accounted |= {entry.column for entry in mapping.dropped_columns}
    findings: list[MappingFinding] = []
    for column in sorted(accounted - present):
        findings.append(
            MappingFinding(
                severity=Severity.ERROR,
                code="MAP-E-COLUMN-ABSENT",
                subject=f"column[{column}]",
                message="is named by the mapping but is not in the source header",
                downstream_consequence=(
                    "Every binding through this column yields nothing, silently, for "
                    "every row in the dataset."
                ),
            )
        )
    for column in sorted(present - accounted):
        findings.append(
            MappingFinding(
                severity=Severity.ERROR,
                code="MAP-E-COLUMN-UNLISTED",
                subject=f"column[{column}]",
                message=(
                    "is in the source header and is neither bound nor listed under "
                    "dropped_columns"
                ),
                downstream_consequence=(
                    "'We decided not to map it' and 'we did not notice it' are "
                    "indistinguishable, and only one of them is a decision "
                    "(docs/architecture.md §5.2 step 3)."
                ),
            )
        )
    for reference in _referenced_columns(mapping):
        if reference[1] not in present:
            findings.append(
                MappingFinding(
                    severity=Severity.ERROR,
                    code="MAP-E-CHECK-COLUMN-ABSENT",
                    subject=reference[0],
                    message=f"names column {reference[1]!r}, absent from the source header",
                    downstream_consequence=(
                        "The validation rule declared here cannot run, so the defect it "
                        "exists to catch would go uncounted."
                    ),
                )
            )
    return findings


def _referenced_columns(mapping: SchemaMappingSpec) -> list[tuple[str, str]]:
    """Return every `(address, column)` a non-binding declaration refers to."""
    references: list[tuple[str, str]] = []
    for pair in mapping.precedence_pairs:
        address = f"precedence_pairs[{pair.id}]"
        references.append((address, pair.earlier_column))
        references.append((address, pair.later_column))
    for constraint in mapping.referential_constraints:
        references.append((f"referential_constraints[{constraint.id}]", constraint.column))
    for check in mapping.temporal_derivation_checks:
        address = f"temporal_derivation_checks[{check.id}]"
        references.append((address, check.column))
        references.append((address, check.equals_column))
        if check.plus_days_column is not None:
            references.append((address, check.plus_days_column))
    for temporal in mapping.temporal_bindings:
        references.append((f"temporal_bindings[{temporal.column}]", temporal.column))
    for value_binding in mapping.value_bindings:
        references.append((f"value_bindings[{value_binding.column}]", value_binding.column))
    for identity in mapping.identity_bindings:
        address = f"identity_bindings[{identity.entity_type}]"
        references.extend((address, column) for column in identity.key_columns)
    return references


def _value_symbols_by_address(mapping: SchemaMappingSpec) -> dict[str, frozenset[str]]:
    """Return, per ontology address, the closed symbol set its column's value map admits.

    An address fed by a column with no value binding is absent from the result: its values
    are open, and a literal compared against it cannot be checked here.
    """
    per_column = {
        binding.column: frozenset(dict(binding.values).values())
        for binding in mapping.value_bindings
    }
    found: dict[str, frozenset[str]] = {}
    for binding in mapping.column_bindings:
        symbols = per_column.get(binding.column)
        if symbols is None or binding.target_kind is TargetKind.EVENT_OCCURRED_AT:
            continue
        concept = binding.entity_type or binding.event_type
        if concept is None or binding.attribute is None:
            continue
        found[f"{concept}.{binding.attribute}"] = symbols
    return found


def _temporal_addresses(mapping: SchemaMappingSpec) -> set[str]:
    """Return every ontology address a declared temporal binding can supply an interval to."""
    temporal_columns = {binding.column for binding in mapping.temporal_bindings}
    found: set[str] = set()
    for binding in mapping.column_bindings:
        if binding.column not in temporal_columns or binding.attribute is None:
            continue
        concept = binding.entity_type or binding.event_type
        if concept is not None:
            found.add(f"{concept}.{binding.attribute}")
    return found


def _condition_leaves(condition: ConditionExpression) -> Iterable[ConditionExpression]:
    """Yield every node of a condition tree, parents before children."""
    yield condition
    for operand in condition.operands:
        yield from _condition_leaves(operand)


def _check_emission_addresses(
    emission: EventEmissionSpec,
    supplied: set[str],
    temporal: set[str],
    symbols: dict[str, frozenset[str]],
    findings: list[MappingFinding],
) -> None:
    """Check that every address an emission rule reads is one the mapping can supply."""
    subject = f"event_emissions[{emission.event_type}]"
    for node in _condition_leaves(emission.when):
        if node.op is not ConditionOperator.ATTRIBUTE:
            continue
        if node.address not in supplied:
            findings.append(
                MappingFinding(
                    severity=Severity.ERROR,
                    code="MAP-E-EMISSION-ADDRESS-UNSUPPLIED",
                    subject=f"{subject}.when",
                    message=(f"reads {node.address!r}, which no column binding supplies"),
                    downstream_consequence=(
                        "The condition would read an absent value on every record, so this "
                        "event type would never be emitted. A rule that cannot fire and a "
                        "rule that never matched are indistinguishable at run time; only "
                        "one of them is a finding about the data."
                    ),
                )
            )
    for parent in _condition_leaves(emission.when):
        admissible: frozenset[str] | None = None
        literals: tuple[str, ...] = ()
        if parent.op is ConditionOperator.IN and parent.operands:
            admissible = symbols.get(parent.operands[0].address)
            literals = parent.values
        elif parent.op in (ConditionOperator.EQUALS, ConditionOperator.NOT_EQUALS):
            attributes = [
                item for item in parent.operands if item.op is ConditionOperator.ATTRIBUTE
            ]
            constants = [item for item in parent.operands if item.op is ConditionOperator.CONSTANT]
            if len(attributes) == 1 and len(constants) == 1 and constants[0].value is not None:
                admissible = symbols.get(attributes[0].address)
                literals = (constants[0].value,)
        if admissible is None:
            continue
        unknown = sorted(set(literals) - admissible)
        if unknown:
            findings.append(
                MappingFinding(
                    severity=Severity.ERROR,
                    code="MAP-E-EMISSION-LITERAL-UNMAPPED",
                    subject=f"{subject}.when",
                    message=(
                        f"compares against {unknown}, which the value binding feeding that "
                        f"attribute does not produce; it admits {sorted(admissible)}"
                    ),
                    downstream_consequence=(
                        "The comparison is false for every record, so the event type is "
                        "never emitted -- silently, because a rule that never matches "
                        "raises nothing. A typo in a symbol is the commonest way an event "
                        "type disappears from a run with no error anywhere."
                    ),
                )
            )
    for reference in (
        emission.occurred_at.anchor,
        emission.occurred_at.earliest,
        emission.occurred_at.latest,
    ):
        if reference is None:
            continue
        if reference.address not in temporal:
            findings.append(
                MappingFinding(
                    severity=Severity.ERROR,
                    code="MAP-E-EMISSION-INSTANT-UNBOUND",
                    subject=f"{subject}.occurred_at",
                    message=(
                        f"reads an instant at {reference.address!r}, which no temporal "
                        "binding supplies"
                    ),
                    downstream_consequence=(
                        "Module 4 would place this event with the unbounded UNKNOWN "
                        "interval while the mapping claims it has a bound one. The claim "
                        "and the artifact would disagree, and only the artifact is read."
                    ),
                )
            )
    offset = emission.occurred_at.plus_days
    if offset is not None and offset.address not in supplied:
        findings.append(
            MappingFinding(
                severity=Severity.ERROR,
                code="MAP-E-EMISSION-OFFSET-UNSUPPLIED",
                subject=f"{subject}.occurred_at",
                message=(f"offsets by {offset.address!r}, which no column binding supplies"),
                downstream_consequence=(
                    "The offset would be absent on every record, so the derived instant "
                    "could never be computed and the event would fall back to UNKNOWN."
                ),
            )
        )


def _check_event_emissions(mapping: SchemaMappingSpec, pack: ResolvedPack) -> list[MappingFinding]:
    """Check that every emission rule resolves, and that every event type has one.

    The second half is the one that changes what a run produces. An event type the pack
    declares and the mapping never witnesses is not an error -- a dataset may legitimately
    carry no evidence of an occurrence the domain has -- but it is the difference between an
    event log and a partial one, and module 4's coverage report is built on knowing which is
    which. It is reported here, before a single record is read.
    """
    findings: list[MappingFinding] = []
    declared = {event.id: event for event in pack.event_types}
    supplied = set(mapped_addresses(mapping))
    temporal = _temporal_addresses(mapping)
    symbols = _value_symbols_by_address(mapping)

    for emission in mapping.event_emissions:
        subject = f"event_emissions[{emission.event_type}]"
        event = declared.get(emission.event_type)
        if event is None:
            findings.append(
                MappingFinding(
                    severity=Severity.ERROR,
                    code="MAP-E-EMISSION-TYPE-UNDECLARED",
                    subject=subject,
                    message=(
                        f"names event type {emission.event_type!r}, which pack "
                        f"{pack.pack_id!r} does not declare"
                    ),
                    downstream_consequence=(
                        "Module 4 would emit events of a type nothing downstream can "
                        "interpret: no participants, no actionability, no confidence."
                    ),
                )
            )
            continue
        _check_emission_addresses(emission, supplied, temporal, symbols, findings)
        if (
            event.observation is ObservationMode.OBSERVED
            and emission.occurred_at.policy is not OccurredAtPolicy.FROM_TEMPORAL_BINDING
        ):
            findings.append(
                MappingFinding(
                    severity=Severity.ERROR,
                    code="MAP-E-EMISSION-OBSERVED-WITHOUT-INSTANT",
                    subject=f"{subject}.occurred_at",
                    message=(
                        f"is OBSERVED but declares occurred_at policy "
                        f"{emission.occurred_at.policy.value}"
                    ),
                    downstream_consequence=(
                        "An OBSERVED occurrence is one the source placed in time. Deriving "
                        "its instant would make the event OBSERVED and its timestamp not, "
                        "which reads downstream as an observation nobody can date."
                    ),
                )
            )
        if event.observation is ObservationMode.DERIVED:
            findings.append(
                MappingFinding(
                    severity=Severity.NOT_RUNNABLE,
                    code="MAP-N-EMISSION-SEMANTICS-UNCHECKED",
                    subject=subject,
                    message=(
                        "declares WHICH records witness a DERIVED occurrence; whether they "
                        "actually do was NOT CHECKED and cannot be checked here"
                    ),
                    downstream_consequence=(
                        "Every event of this type inherits the rule's correctness. A rule "
                        "that resolves cleanly can still witness the wrong thing, and it "
                        "would produce silently wrong causality rather than an error. This "
                        "is risk R-16, now with a second surface: the pack's basis prose "
                        f"({_as_clause(event.derivation.basis if event.derivation else '')}) "
                        "and this rule must be read against each other by a human."
                    ),
                )
            )

    witnessed = {emission.event_type for emission in mapping.event_emissions}
    for event in pack.event_types:
        if event.id in witnessed:
            continue
        findings.append(
            MappingFinding(
                severity=Severity.WARNING,
                code="MAP-W-EVENT-TYPE-NEVER-EMITTED",
                subject=f"event_types[{event.id}]",
                message="is declared by the pack and no emission rule witnesses it",
                downstream_consequence=(
                    "No event of this type can ever be produced from this dataset. Where "
                    "the type appears in a process definition, every instance of that "
                    "process carries a coverage gap at this step -- which module 4 reports "
                    "rather than fills."
                ),
            )
        )
    return findings


def assess_coverage(
    mapping: SchemaMappingSpec,
    pack: ResolvedPack,
    *,
    header: Sequence[str] | None = None,
) -> CoverageReport:
    """Return every finding about this mapping against this pack.

    Args:
        mapping: the mapping to assess.
        pack: the resolved ontology pack it claims to bind to.
        header: the source header, when one has been probed. `None` makes the
            every-column-accounted-for check report `NOT_RUNNABLE` rather than pass.

    Every finding is reported, not just the first: an author who reloads ten times to see
    ten problems learns to distrust the tenth message (`docs/ontology.md` §3).
    """
    findings: list[MappingFinding] = []
    if mapping.ontology_pack != pack.pack_id:
        findings.append(
            MappingFinding(
                severity=Severity.ERROR,
                code="MAP-E-PACK-MISMATCH",
                subject="ontology_pack",
                message=(
                    f"mapping declares pack {mapping.ontology_pack!r} but was assessed "
                    f"against {pack.pack_id!r}"
                ),
                downstream_consequence=(
                    "Every concept address in the mapping would be resolved against the "
                    "wrong vocabulary, and most would resolve."
                ),
            )
        )
    findings.extend(_check_targets_resolve(mapping, pack))
    findings.extend(_check_lifecycle_states(mapping, pack))
    findings.extend(_check_required_concepts(mapping, pack))
    findings.extend(_check_event_emissions(mapping, pack))
    findings.extend(_check_columns(mapping, header))
    return CoverageReport(
        mapping_id=mapping.mapping_id,
        mapping_version=mapping.mapping_version,
        ontology_pack=pack.pack_id,
        ontology_version=pack.ontology_version,
        findings=tuple(findings),
        bound_column_count=len({binding.column for binding in mapping.column_bindings}),
        binding_count=len(mapping.column_bindings),
        dropped_column_count=len(mapping.dropped_columns),
        header_column_count=None if header is None else len(header),
    )
