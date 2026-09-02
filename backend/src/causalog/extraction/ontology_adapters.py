"""Adapt a `ResolvedPack` into the plain views `graph_engine` consumes.

`extraction` is one of the three packages permitted to import `ontology_runtime`
(`scripts/check_layers.py` F3, ADR-0002); `graph_engine` is not. This module is the one
place that boundary is crossed for modules 5 and 6 -- everything downstream of it works
with `causalog.core.ontology_view` types, never with the DSL models directly.

Not part of Entity Extractor or Event Generator: this is new, orthogonal wiring for
modules 5/6, not a change to either already-built module.
"""

from __future__ import annotations

from causalog.core.ontology_view import (
    DurationExpressionOperator,
    DurationExpressionView,
    DurationMeasurementView,
    EntityTypeView,
    EventTypeView,
    LifecycleTransitionView,
    LifecycleView,
    ParticipantView,
    ProcessDefinitionView,
    ProcessVariantView,
    RelationshipTypeView,
    VocabularyView,
)
from causalog.ontology_runtime import ResolvedPack
from causalog.ontology_runtime.dsl import ExpressionOperator, MeasurementExpression, MeasurementKind

__all__ = [
    "duration_measurements_of",
    "lifecycles_of",
    "process_definitions_of",
    "vocabulary_of",
]


def process_definitions_of(pack: ResolvedPack) -> tuple[ProcessDefinitionView, ...]:
    """Return every declared process definition, as plain views."""
    return tuple(
        ProcessDefinitionView(
            id=definition.id,
            anchor_entity_type=definition.anchor_entity_type,
            canonical_sequence=definition.canonical_sequence,
            variants=tuple(
                ProcessVariantView(id=variant.id, sequence=variant.sequence)
                for variant in definition.variants
            ),
            optional_steps=definition.optional_steps,
            repeatable_steps=definition.repeatable_steps,
        )
        for definition in pack.process_definitions
    )


def lifecycles_of(pack: ResolvedPack) -> tuple[LifecycleView, ...]:
    """Return every entity type's declared lifecycle, as plain views.

    An entity type with no declared `lifecycle` is simply absent from the result.
    """
    views = []
    for entity_type in pack.entity_types:
        if entity_type.lifecycle is None:
            continue
        views.append(
            LifecycleView(
                entity_type=entity_type.id,
                initial_states=entity_type.lifecycle.initial_states,
                transitions=tuple(
                    LifecycleTransitionView(
                        from_state=transition.from_state,
                        to_state=transition.to_state,
                        triggered_by=transition.triggered_by,
                    )
                    for transition in entity_type.lifecycle.transitions
                    if transition.triggered_by is not None
                ),
            )
        )
    return tuple(views)


_DURATION_OPERATOR_MIRROR = {
    ExpressionOperator.CONSTANT: DurationExpressionOperator.CONSTANT,
    ExpressionOperator.ATTRIBUTE: DurationExpressionOperator.ATTRIBUTE,
    ExpressionOperator.SUM: DurationExpressionOperator.SUM,
    ExpressionOperator.DIFFERENCE: DurationExpressionOperator.DIFFERENCE,
    ExpressionOperator.DURATION_BETWEEN: DurationExpressionOperator.DURATION_BETWEEN,
    ExpressionOperator.MINIMUM: DurationExpressionOperator.MINIMUM,
    ExpressionOperator.MAXIMUM: DurationExpressionOperator.MAXIMUM,
}


def _view_of(expression: MeasurementExpression) -> DurationExpressionView:
    return DurationExpressionView(
        op=_DURATION_OPERATOR_MIRROR[expression.op],
        event_type=expression.event_type,
        attribute=expression.attribute,
        value=expression.value,
        operands=tuple(_view_of(operand) for operand in expression.operands),
    )


def duration_measurements_of(pack: ResolvedPack) -> tuple[DurationMeasurementView, ...]:
    """Return every `DURATION`/`DELAY` measurement whose tree this evaluator can mirror.

    A measurement using an operator outside `_DURATION_OPERATOR_MIRROR` (e.g. `PRODUCT`,
    `RATIO` on a plain numeric metric, not a duration) is not a duration measurement and is
    excluded here rather than mistranslated.
    """
    views = []
    for measurement in pack.measurement_definitions:
        if measurement.kind not in (MeasurementKind.DURATION, MeasurementKind.DELAY):
            continue
        views.append(
            DurationMeasurementView(
                id=measurement.id,
                unit=measurement.unit,
                expression=_view_of(measurement.expression),
            )
        )
    return tuple(views)


def vocabulary_of(pack: ResolvedPack) -> VocabularyView:
    """Return every name the pack declares, as the plain view `rule_engine` reads (ADR-0046).

    `rule_engine` is L5 and forbidden edge F3 blocks it from importing this module's
    `ontology_runtime` import. This function is that boundary's one crossing for the rule
    layer, exactly as `process_definitions_of` and `lifecycles_of` are for modules 5 and 6.

    Everything is sorted by identifier so the result is one value for one pack
    (`CONVENTIONS.md` §11). Nothing is defaulted: an entity type with no declared lifecycle
    gets empty state tuples, which is what the pack says, not a guess about what it meant.
    """
    event_types = tuple(
        EventTypeView(
            id=declared.id,
            participants=tuple(
                ParticipantView(
                    role=participant.role,
                    entity_type=participant.entity_type,
                    required=participant.required,
                )
                for participant in sorted(declared.participants, key=lambda item: item.role)
            ),
            required_attributes=tuple(
                sorted(attribute.name for attribute in declared.required_attributes)
            ),
        )
        for declared in sorted(pack.event_types, key=lambda item: item.id)
    )
    entity_types = tuple(
        EntityTypeView(
            id=declared.id,
            state_names=(
                () if declared.lifecycle is None else tuple(sorted(declared.lifecycle.states))
            ),
            terminal_state_names=(
                ()
                if declared.lifecycle is None
                else tuple(sorted(declared.lifecycle.terminal_states))
            ),
            attribute_names=tuple(sorted(attribute.name for attribute in declared.attributes)),
        )
        for declared in sorted(pack.entity_types, key=lambda item: item.id)
    )
    relationship_types = tuple(
        RelationshipTypeView(
            id=declared.id,
            from_entity_type=declared.from_entity_type,
            to_entity_type=declared.to_entity_type,
        )
        for declared in sorted(pack.relationship_types, key=lambda item: item.id)
    )
    return VocabularyView(
        event_types=event_types,
        entity_types=entity_types,
        relationship_types=relationship_types,
    )
