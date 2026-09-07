"""Structural validation: every reference resolves, every state machine is well-formed.

Structural findings are always `ERROR`. They are not matters of judgement -- a participant
naming an entity type the pack never declares is wrong however the domain works, and a pack
carrying one would fail later, further from the cause, as a mapping miss or a silently empty
timeline.

Every check here is domain-blind. It reads the shape of the declarations and never their
names (LAW-DOMAIN). The one exception is the literal `CAUSES`, which is refused as a
relationship identifier -- and `CAUSES` is an engine concept, not a domain one.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Iterator

from causalog.core.aggregation import AGGREGATORS, DEFAULT_COMPONENT_WEIGHTS
from causalog.ontology_runtime.diagnostics import Diagnostic, Severity
from causalog.ontology_runtime.dsl import (
    AttributeSpec,
    DomainPack,
    EntityTypeSpec,
    EventTypeSpec,
    ExpressionOperator,
    MeasurementDefinitionSpec,
    MeasurementExpression,
    ObservationMode,
    ProcessDefinitionSpec,
    ResolvedPack,
)
from causalog.ontology_runtime.locator import Address, PackLocator

__all__ = [
    "CAUSAL_RELATIONSHIP_ID",
    "validate_authored_uniqueness",
    "validate_structure",
]

#: Refused as a relationship identifier. `docs/contracts.md` §5 forbids `CAUSES` on
#: `Relationship`: causal edges are produced only by the causal engine, and a pack is the
#: one place a structural edge could be renamed into a causal claim.
CAUSAL_RELATIONSHIP_ID = "CAUSES"

_ATTRIBUTE_INSTANT_OPERATORS = frozenset({ExpressionOperator.DURATION_BETWEEN})


def _finding(locator: PackLocator, code: str, address: Address, message: str) -> Diagnostic:
    """Build one ERROR diagnostic located against the authored source."""
    file, line = locator.locate(address)
    return Diagnostic(
        severity=Severity.ERROR,
        code=code,
        message=message,
        path=_render_address(address),
        file=file,
        line=line,
    )


def _render_address(address: Address) -> str:
    """Render an address as the dotted-and-bracketed form an author reads."""
    if not address:
        return ""
    rendered = str(address[0])
    for part in address[1:]:
        rendered += f"[{part}]" if isinstance(part, int) else f".{part}"
    return rendered


def _duplicates(identifiers: Iterable[str]) -> list[str]:
    """Return identifiers appearing more than once, in first-seen sequence."""
    seen: set[str] = set()
    repeated: list[str] = []
    for identifier in identifiers:
        if identifier in seen and identifier not in repeated:
            repeated.append(identifier)
        seen.add(identifier)
    return repeated


def _walk(
    expression: MeasurementExpression, prefix: Address = ()
) -> Iterator[tuple[MeasurementExpression, Address]]:
    """Yield every node of an expression tree with the address that reaches it.

    The address is what lets a diagnostic point at the offending operand rather than at the
    expression that contains it. An author with a four-node tree and a message about "the
    expression" has to find the defect themselves, which is most of the work.
    """
    yield expression, prefix
    for position, operand in enumerate(expression.operands):
        yield from _walk(operand, (*prefix, "operands", position))


def validate_structure(pack: ResolvedPack, locator: PackLocator) -> tuple[Diagnostic, ...]:
    """Return every structural error in a resolved pack.

    All of them, not the first. An author fixing a pack one message per reload learns to
    distrust the messages.
    """
    findings: list[Diagnostic] = []

    categories = {item.id for item in pack.event_categories}
    cost_classes = {item.id for item in pack.cost_classes}
    severity_classes = {item.id for item in pack.severity_classes}
    risk_classes = {item.id for item in pack.risk_classes}
    entity_types = {item.id: item for item in pack.entity_types}
    event_types = {item.id: item for item in pack.event_types}
    external_types = {item.id for item in pack.external_event_types}

    findings.extend(_check_namespaces_disjoint(pack, locator))

    for entity_type in pack.entity_types:
        findings.extend(_check_entity_type(entity_type, event_types, locator))

    for relationship in pack.relationship_types:
        address: Address = ("relationship_types", relationship.id)
        if relationship.id == CAUSAL_RELATIONSHIP_ID:
            findings.append(
                _finding(
                    locator,
                    "ONT-E-CAUSAL-RELATIONSHIP",
                    address,
                    f"'{CAUSAL_RELATIONSHIP_ID}' is not admissible as a relationship type. "
                    "Relationships are structural; causal edges are a separate artifact "
                    "produced only by the causal engine (docs/contracts.md §5).",
                )
            )
        for side, referenced in (
            ("from", relationship.from_entity_type),
            ("to", relationship.to_entity_type),
        ):
            if referenced not in entity_types:
                findings.append(
                    _finding(
                        locator,
                        "ONT-E-UNKNOWN-ENTITY-TYPE",
                        (*address, side),
                        f"'{referenced}' is not a declared entity_type.",
                    )
                )

    for event_type in pack.event_types:
        findings.extend(
            _check_event_type(
                event_type,
                categories,
                cost_classes,
                severity_classes,
                risk_classes,
                entity_types,
                locator,
            )
        )

    for external in pack.external_event_types:
        if external.category not in categories:
            findings.append(
                _finding(
                    locator,
                    "ONT-E-UNKNOWN-CATEGORY",
                    ("external_event_types", external.id, "category"),
                    f"'{external.category}' is not a declared event category.",
                )
            )

    for process in pack.process_definitions:
        findings.extend(_check_process(process, event_types, external_types, entity_types, locator))

    for measurement in pack.measurement_definitions:
        findings.extend(_check_measurement(measurement, event_types, external_types, locator))

    return tuple(findings)


def validate_authored_uniqueness(pack: DomainPack, locator: PackLocator) -> tuple[Diagnostic, ...]:
    """Refuse a repeated identifier inside any one namespace of ONE AUTHORED pack.

    This runs before resolution, and it has to. Resolution merges namespaces into a mapping
    keyed by identifier (ADR-0027), so a pack declaring the same identifier twice would
    silently lose one declaration and resolve clean -- the quietest possible way to load
    something other than what the author wrote.
    """
    findings: list[Diagnostic] = []
    namespaces = (
        ("event_categories", [item.id for item in pack.event_categories]),
        ("cost_classes", [item.id for item in pack.cost_classes]),
        ("severity_classes", [item.id for item in pack.severity_classes]),
        ("risk_classes", [item.id for item in pack.risk_classes]),
        ("entity_types", [item.id for item in pack.entity_types]),
        ("relationship_types", [item.id for item in pack.relationship_types]),
        ("event_types", [item.id for item in pack.event_types]),
        ("external_event_types", [item.id for item in pack.external_event_types]),
        ("process_definitions", [item.id for item in pack.process_definitions]),
        ("measurement_definitions", [item.id for item in pack.measurement_definitions]),
    )
    for namespace, identifiers in namespaces:
        for repeated in _duplicates(identifiers):
            findings.append(
                _finding(
                    locator,
                    "ONT-E-DUPLICATE-ID",
                    (namespace, repeated),
                    f"'{repeated}' is declared more than once in {namespace}; two "
                    "declarations under one identifier have no defined combination.",
                )
            )
    return tuple(findings)


def _check_namespaces_disjoint(pack: ResolvedPack, locator: PackLocator) -> list[Diagnostic]:
    """Refuse an identifier shared by the internal and external event namespaces."""
    external = {item.id for item in pack.external_event_types}
    shared = sorted({item.id for item in pack.event_types} & external)
    return [
        _finding(
            locator,
            "ONT-E-DUPLICATE-ID",
            ("external_event_types", identifier),
            f"'{identifier}' is declared as both an event_type and an "
            "external_event_type; one identifier cannot be both populated and unpopulated.",
        )
        for identifier in shared
    ]


def _check_entity_type(
    entity_type: EntityTypeSpec,
    event_types: dict[str, EventTypeSpec],
    locator: PackLocator,
) -> list[Diagnostic]:
    """Check identifying keys, attribute uniqueness, and the state machine."""
    findings: list[Diagnostic] = []
    base: Address = ("entity_types", entity_type.id)

    attribute_names = [attribute.name for attribute in entity_type.attributes]
    for repeated in _duplicates(attribute_names):
        findings.append(
            _finding(
                locator,
                "ONT-E-DUPLICATE-ATTRIBUTE",
                (*base, "attributes", repeated),
                f"attribute '{repeated}' is declared more than once.",
            )
        )
    for key in entity_type.identifying_keys:
        if key not in attribute_names:
            findings.append(
                _finding(
                    locator,
                    "ONT-E-UNKNOWN-ATTRIBUTE",
                    (*base, "identifying_keys"),
                    f"identifying key '{key}' is not a declared attribute of "
                    f"'{entity_type.id}'.",
                )
            )

    lifecycle = entity_type.lifecycle
    if lifecycle is None:
        return findings

    states = set(lifecycle.states)
    for repeated in _duplicates(lifecycle.states):
        findings.append(
            _finding(
                locator,
                "ONT-E-DUPLICATE-STATE",
                (*base, "lifecycle", "states"),
                f"state '{repeated}' is declared more than once.",
            )
        )
    for label, declared in (
        ("initial_states", lifecycle.initial_states),
        ("terminal_states", lifecycle.terminal_states),
    ):
        for state in declared:
            if state not in states:
                findings.append(
                    _finding(
                        locator,
                        "ONT-E-UNKNOWN-STATE",
                        (*base, "lifecycle", label),
                        f"'{state}' is not among the declared states of '{entity_type.id}'.",
                    )
                )

    seen_transitions: set[tuple[str, str]] = set()
    outgoing: dict[str, list[str]] = {state: [] for state in lifecycle.states}
    for position, transition in enumerate(lifecycle.transitions):
        address: Address = (*base, "lifecycle", "transitions", position)
        for side, state in (("from", transition.from_state), ("to", transition.to_state)):
            if state not in states:
                findings.append(
                    _finding(
                        locator,
                        "ONT-E-UNKNOWN-STATE",
                        (*address, side),
                        f"'{state}' is not among the declared states of '{entity_type.id}'.",
                    )
                )
        pair = (transition.from_state, transition.to_state)
        if pair in seen_transitions:
            findings.append(
                _finding(
                    locator,
                    "ONT-E-DUPLICATE-TRANSITION",
                    address,
                    f"transition '{pair[0]}' -> '{pair[1]}' is declared more than once.",
                )
            )
        seen_transitions.add(pair)
        if transition.from_state in outgoing:
            outgoing[transition.from_state].append(transition.to_state)
        if transition.triggered_by is not None and transition.triggered_by not in event_types:
            findings.append(
                _finding(
                    locator,
                    "ONT-E-UNKNOWN-EVENT-TYPE",
                    (*address, "triggered_by"),
                    f"'{transition.triggered_by}' is not a declared event_type.",
                )
            )

    for terminal in lifecycle.terminal_states:
        if outgoing.get(terminal):
            findings.append(
                _finding(
                    locator,
                    "ONT-E-TERMINAL-STATE-HAS-EXIT",
                    (*base, "lifecycle", "terminal_states"),
                    f"'{terminal}' is declared terminal and has an outgoing transition; a "
                    "terminal state that can be left is not terminal.",
                )
            )

    reached: set[str] = set()
    queue = deque(state for state in lifecycle.initial_states if state in states)
    reached.update(queue)
    while queue:
        current = queue.popleft()
        for successor in outgoing.get(current, ()):
            if successor not in reached and successor in states:
                reached.add(successor)
                queue.append(successor)
    for unreachable in sorted(states - reached):
        findings.append(
            _finding(
                locator,
                "ONT-E-UNREACHABLE-STATE",
                (*base, "lifecycle", "states"),
                f"'{unreachable}' cannot be reached from any initial state of "
                f"'{entity_type.id}'. An unreachable state is either a missing transition "
                "or a state that does not exist; the pack must say which.",
            )
        )
    return findings


def _check_event_type(
    event_type: EventTypeSpec,
    categories: set[str],
    cost_classes: set[str],
    severity_classes: set[str],
    risk_classes: set[str],
    entity_types: dict[str, EntityTypeSpec],
    locator: PackLocator,
) -> list[Diagnostic]:
    """Check an event type's category, participants, conditions, and actionability."""
    findings: list[Diagnostic] = []
    base: Address = ("event_types", event_type.id)

    if event_type.category not in categories:
        findings.append(
            _finding(
                locator,
                "ONT-E-UNKNOWN-CATEGORY",
                (*base, "category"),
                f"'{event_type.category}' is not a declared event category.",
            )
        )

    roles: dict[str, str] = {}
    for position, participant in enumerate(event_type.participants):
        address: Address = (*base, "participants", position)
        if participant.entity_type not in entity_types:
            findings.append(
                _finding(
                    locator,
                    "ONT-E-UNKNOWN-ENTITY-TYPE",
                    (*address, "entity_type"),
                    f"'{participant.entity_type}' is not a declared entity_type.",
                )
            )
        if participant.role in roles:
            findings.append(
                _finding(
                    locator,
                    "ONT-E-DUPLICATE-ROLE",
                    address,
                    f"role '{participant.role}' is declared twice on '{event_type.id}'; a "
                    "condition naming it could not say which participant it meant.",
                )
            )
        roles[participant.role] = participant.entity_type

    for repeated in _duplicates(attribute.name for attribute in event_type.required_attributes):
        findings.append(
            _finding(
                locator,
                "ONT-E-DUPLICATE-ATTRIBUTE",
                (*base, "required_attributes", repeated),
                f"attribute '{repeated}' is declared more than once.",
            )
        )

    findings.extend(_check_conditions(event_type, roles, entity_types, locator))

    if event_type.actionability.severity_class not in severity_classes:
        findings.append(
            _finding(
                locator,
                "ONT-E-UNKNOWN-SEVERITY-CLASS",
                (*base, "actionability", "severity_class"),
                f"'{event_type.actionability.severity_class}' is not a declared " "severity class.",
            )
        )
    cost_class = event_type.actionability.cost_class
    if cost_class is not None and cost_class not in cost_classes:
        findings.append(
            _finding(
                locator,
                "ONT-E-UNKNOWN-COST-CLASS",
                (*base, "actionability", "cost_class"),
                f"'{cost_class}' is not a declared cost class.",
            )
        )
    # ADR-0073. An ABSENT risk_class is legitimate and is not checked here -- it is reported
    # as NOT_DECLARED by the consumer. A PRESENT one that names nothing is a dangling
    # reference, and a dangling ordinal would resolve to no rank and rank the type nowhere
    # while looking declared, which is the quietest of the two failures.
    risk_class = event_type.actionability.risk_class
    if risk_class is not None and risk_class not in risk_classes:
        findings.append(
            _finding(
                locator,
                "ONT-E-UNKNOWN-RISK-CLASS",
                (*base, "actionability", "risk_class"),
                f"'{risk_class}' is not a declared risk class.",
            )
        )

    if event_type.observation is ObservationMode.DERIVED and event_type.derivation is not None:
        confidence = event_type.derivation.default_confidence
        if confidence.aggregation not in AGGREGATORS:
            findings.append(
                _finding(
                    locator,
                    "ONT-E-UNKNOWN-AGGREGATION",
                    (*base, "derivation", "default_confidence", "aggregation"),
                    f"'{confidence.aggregation}' is not a registered aggregation function; "
                    f"the registry holds {sorted(AGGREGATORS)}.",
                )
            )
        for component in confidence.components:
            if component.component_name not in DEFAULT_COMPONENT_WEIGHTS:
                findings.append(
                    _finding(
                        locator,
                        "ONT-E-UNKNOWN-CONFIDENCE-COMPONENT",
                        (*base, "derivation", "default_confidence", "components"),
                        f"'{component.component_name}' is not a weighted component name. "
                        "The admissible names are part of confidence_schema_version "
                        f"(docs/contracts.md §5): {sorted(DEFAULT_COMPONENT_WEIGHTS)}.",
                    )
                )
    return findings


def _check_conditions(
    event_type: EventTypeSpec,
    roles: dict[str, str],
    entity_types: dict[str, EntityTypeSpec],
    locator: PackLocator,
) -> list[Diagnostic]:
    """Check that every pre/postcondition names a declared role and a declared state."""
    findings: list[Diagnostic] = []
    base: Address = ("event_types", event_type.id)

    def states_of(role: str) -> set[str] | None:
        entity_type = entity_types.get(roles.get(role, ""))
        if entity_type is None or entity_type.lifecycle is None:
            return None
        return set(entity_type.lifecycle.states)

    checks: tuple[tuple[str, tuple[tuple[str, tuple[str, ...]], ...]], ...] = (
        (
            "preconditions",
            tuple((item.role, item.state_in) for item in event_type.preconditions),
        ),
        (
            "postconditions",
            tuple((item.role, (item.state,)) for item in event_type.postconditions),
        ),
    )
    for label, entries in checks:
        for position, (role, declared_states) in enumerate(entries):
            address: Address = (*base, label, position)
            if role not in roles:
                findings.append(
                    _finding(
                        locator,
                        "ONT-E-UNKNOWN-ROLE",
                        (*address, "role"),
                        f"'{role}' is not a participant role of '{event_type.id}'.",
                    )
                )
                continue
            available = states_of(role)
            if available is None:
                findings.append(
                    _finding(
                        locator,
                        "ONT-E-LIFECYCLE-REQUIRED",
                        address,
                        f"role '{role}' resolves to entity type '{roles[role]}', which "
                        "declares no lifecycle; a condition cannot assert a state that "
                        "the entity type does not have.",
                    )
                )
                continue
            for state in declared_states:
                if state not in available:
                    findings.append(
                        _finding(
                            locator,
                            "ONT-E-UNKNOWN-STATE",
                            address,
                            f"'{state}' is not a declared state of '{roles[role]}'.",
                        )
                    )
    return findings


def _check_process(
    process: ProcessDefinitionSpec,
    event_types: dict[str, EventTypeSpec],
    external_types: set[str],
    entity_types: dict[str, EntityTypeSpec],
    locator: PackLocator,
) -> list[Diagnostic]:
    """Check a process definition's anchor, steps, variants, and step annotations."""
    findings: list[Diagnostic] = []
    base: Address = ("process_definitions", process.id)

    if process.anchor_entity_type not in entity_types:
        findings.append(
            _finding(
                locator,
                "ONT-E-UNKNOWN-ENTITY-TYPE",
                (*base, "anchor_entity_type"),
                f"'{process.anchor_entity_type}' is not a declared entity_type.",
            )
        )

    def check_steps(label: str, steps: tuple[str, ...], address: Address) -> None:
        for step in steps:
            if step in external_types:
                findings.append(
                    _finding(
                        locator,
                        "ONT-E-EXTERNAL-REFERENCED",
                        address,
                        f"'{step}' is an external_event_type and is declared unpopulated in "
                        "this version; a process may not depend on it (CONTEXT.md §10).",
                    )
                )
            elif step not in event_types:
                findings.append(
                    _finding(
                        locator,
                        "ONT-E-UNKNOWN-EVENT-TYPE",
                        address,
                        f"'{step}' in {label} is not a declared event_type.",
                    )
                )

    check_steps("canonical_sequence", process.canonical_sequence, (*base, "canonical_sequence"))
    for position, variant in enumerate(process.variants):
        check_steps(
            f"variants[{variant.id}].sequence",
            variant.sequence,
            (*base, "variants", position, "sequence"),
        )

    canonical = set(process.canonical_sequence)
    for label, annotated in (
        ("optional_steps", process.optional_steps),
        ("repeatable_steps", process.repeatable_steps),
    ):
        for step in annotated:
            if step not in canonical:
                findings.append(
                    _finding(
                        locator,
                        "ONT-E-STEP-NOT-IN-SEQUENCE",
                        (*base, label),
                        f"'{step}' is annotated {label} but is not part of the canonical "
                        "sequence it annotates.",
                    )
                )
    return findings


def _check_measurement(
    measurement: MeasurementDefinitionSpec,
    event_types: dict[str, EventTypeSpec],
    external_types: set[str],
    locator: PackLocator,
) -> list[Diagnostic]:
    """Check that every expression leaf names a declared event type and attribute."""
    findings: list[Diagnostic] = []
    base: Address = ("measurement_definitions", measurement.id, "expression")

    def attributes_of(event_type_id: str) -> dict[str, AttributeSpec]:
        event_type = event_types.get(event_type_id)
        if event_type is None:
            return {}
        return {attribute.name: attribute for attribute in event_type.required_attributes}

    for node, path in _walk(measurement.expression):
        if node.op is not ExpressionOperator.ATTRIBUTE:
            continue
        here: Address = (*base, *path)
        event_type_id = node.event_type or ""
        attribute_name = node.attribute or ""
        if event_type_id in external_types:
            findings.append(
                _finding(
                    locator,
                    "ONT-E-EXTERNAL-REFERENCED",
                    here,
                    f"'{event_type_id}' is an external_event_type and is declared "
                    "unpopulated in this version; a measurement may not depend on it "
                    "(CONTEXT.md §10).",
                )
            )
            continue
        if event_type_id not in event_types:
            findings.append(
                _finding(
                    locator,
                    "ONT-E-UNKNOWN-EVENT-TYPE",
                    here,
                    f"'{event_type_id}' is not a declared event_type.",
                )
            )
            continue
        available = attributes_of(event_type_id)
        if attribute_name not in available:
            findings.append(
                _finding(
                    locator,
                    "ONT-E-UNKNOWN-ATTRIBUTE",
                    here,
                    f"'{attribute_name}' is not a required attribute of "
                    f"'{event_type_id}'; a measurement may only read attributes the event "
                    "type guarantees to carry.",
                )
            )

    for node, path in _walk(measurement.expression):
        if node.op not in _ATTRIBUTE_INSTANT_OPERATORS:
            continue
        for position, operand in enumerate(node.operands):
            here = (*base, *path, "operands", position)
            if operand.op is not ExpressionOperator.ATTRIBUTE:
                findings.append(
                    _finding(
                        locator,
                        "ONT-E-EXPRESSION-TYPE",
                        here,
                        f"a {node.op.value} expression takes two ATTRIBUTE operands; one "
                        f"operand is {operand.op.value}.",
                    )
                )
                continue
            attribute = attributes_of(operand.event_type or "").get(operand.attribute or "")
            if attribute is not None and attribute.semantics.value != "INSTANT":
                findings.append(
                    _finding(
                        locator,
                        "ONT-E-EXPRESSION-TYPE",
                        here,
                        f"a {node.op.value} expression takes operands with INSTANT "
                        f"semantics; '{operand.attribute}' is "
                        f"{attribute.semantics.value}.",
                    )
                )
    return findings
