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
    ActionabilityView,
    AttributeView,
    DurationExpressionOperator,
    DurationExpressionView,
    DurationMeasurementView,
    EntityTypeView,
    EventTypeView,
    LifecycleTransitionView,
    LifecycleView,
    MagnitudeMeasurementView,
    MeasurementExpressionOperator,
    MeasurementExpressionView,
    MeasurementKindView,
    MutabilityView,
    OrdinalClassView,
    ParticipantView,
    ProcessDefinitionView,
    ProcessVariantView,
    RelationshipTypeView,
    VocabularyView,
)
from causalog.ontology_runtime import ResolvedPack
from causalog.ontology_runtime.dsl import ExpressionOperator, MeasurementExpression, MeasurementKind

__all__ = [
    "actionability_of",
    "cost_classes_of",
    "duration_measurements_of",
    "lifecycles_of",
    "magnitude_measurements_of",
    "mutable_attributes_of",
    "process_definitions_of",
    "risk_classes_of",
    "severity_classes_of",
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


# ---------------------------------------------------------------------------------------
# Magnitude mirrors (ADR-0056). Unlike the duration mirror above, these exclude nothing:
# every operator and every kind is carried, because a propagation-weight attribution may
# legitimately reference an `IMPACT`, a `COST` or a `QUANTITY`, and refusing one here would
# make a declared measurement invisible to the module that needs it rather than reporting
# that it could not be evaluated.
#
# Written as explicit member-to-member tables rather than `Enum(value)` lookups so that a
# member added to the DSL enum and not to the mirror fails HERE, at the boundary, naming the
# member -- instead of at evaluation time inside a package that may not import the DSL.
# ---------------------------------------------------------------------------------------

_MAGNITUDE_OPERATOR_MIRROR = {
    ExpressionOperator.CONSTANT: MeasurementExpressionOperator.CONSTANT,
    ExpressionOperator.ATTRIBUTE: MeasurementExpressionOperator.ATTRIBUTE,
    ExpressionOperator.SUM: MeasurementExpressionOperator.SUM,
    ExpressionOperator.DIFFERENCE: MeasurementExpressionOperator.DIFFERENCE,
    ExpressionOperator.PRODUCT: MeasurementExpressionOperator.PRODUCT,
    ExpressionOperator.RATIO: MeasurementExpressionOperator.RATIO,
    ExpressionOperator.DURATION_BETWEEN: MeasurementExpressionOperator.DURATION_BETWEEN,
    ExpressionOperator.MINIMUM: MeasurementExpressionOperator.MINIMUM,
    ExpressionOperator.MAXIMUM: MeasurementExpressionOperator.MAXIMUM,
}

_MAGNITUDE_KIND_MIRROR = {
    MeasurementKind.DELAY: MeasurementKindView.DELAY,
    MeasurementKind.DURATION: MeasurementKindView.DURATION,
    MeasurementKind.COST: MeasurementKindView.COST,
    MeasurementKind.IMPACT: MeasurementKindView.IMPACT,
    MeasurementKind.COUNT: MeasurementKindView.COUNT,
    MeasurementKind.RATIO: MeasurementKindView.RATIO,
    MeasurementKind.QUANTITY: MeasurementKindView.QUANTITY,
}


def _magnitude_view_of(expression: MeasurementExpression) -> MeasurementExpressionView:
    """Mirror one node of any measurement tree, recursively."""
    return MeasurementExpressionView(
        op=_MAGNITUDE_OPERATOR_MIRROR[expression.op],
        event_type=expression.event_type,
        attribute=expression.attribute,
        value=expression.value,
        operands=tuple(_magnitude_view_of(operand) for operand in expression.operands),
    )


def magnitude_measurements_of(pack: ResolvedPack) -> tuple[MagnitudeMeasurementView, ...]:
    """Return every declared measurement, of every kind, as a plain view.

    The counterpart to `duration_measurements_of` for propagation-weight attribution
    (ADR-0056). Nothing is filtered: a measurement this consumer cannot use is reported as
    unevaluable at attribution time, where the report can say which effect type lost its
    magnitude and why, rather than vanishing at the boundary where nobody counts it.
    """
    return tuple(
        MagnitudeMeasurementView(
            id=measurement.id,
            kind=_MAGNITUDE_KIND_MIRROR[measurement.kind],
            unit=measurement.unit,
            expression=_magnitude_view_of(measurement.expression),
        )
        for measurement in pack.measurement_definitions
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


def actionability_of(pack: ResolvedPack) -> tuple[ActionabilityView, ...]:
    """Return every event type's actionability declaration, as plain views.

    ADR-0008 stamps the BOOLEAN onto each `Event` at generation time so that the Root Cause
    Analyzer never reads the ontology (forbidden edge F3). This function carries the rest of
    the declaration -- the cost and severity classes -- across the same boundary and in the
    same direction, because a boolean is enough to filter on and not enough to rank on.

    Nothing is filtered and nothing is defaulted. A pack that declares a type
    `actionable: false` appears here saying so, which is a different fact from a type that
    is absent, and a consumer that dropped the false rows could not tell the two apart.

    Sequenced by `event_type`, so two adapters over one pack produce one value.
    """
    return tuple(
        ActionabilityView(
            event_type=event_type.id,
            actionable=event_type.actionability.actionable,
            cost_class=event_type.actionability.cost_class,
            severity_class=event_type.actionability.severity_class,
            risk_class=event_type.actionability.risk_class,
        )
        for event_type in sorted(pack.event_types, key=lambda declared: declared.id)
    )


def cost_classes_of(pack: ResolvedPack) -> tuple[OrdinalClassView, ...]:
    """Return the declared cost vocabulary as name-and-rank pairs, sequenced by rank.

    Sequenced by rank rather than by name because rank is what a consumer compares, and a
    sequence in rank sequence lets a reader of the artifact check the sequencing by eye.
    Ties in rank are impossible -- the pack loader refuses them -- so the sequence is total.
    """
    return tuple(
        OrdinalClassView(id=declared.id, rank=declared.rank)
        for declared in sorted(pack.cost_classes, key=lambda member: (member.rank, member.id))
    )


def severity_classes_of(pack: ResolvedPack) -> tuple[OrdinalClassView, ...]:
    """Return the declared severity vocabulary as name-and-rank pairs, sequenced by rank."""
    return tuple(
        OrdinalClassView(id=declared.id, rank=declared.rank)
        for declared in sorted(pack.severity_classes, key=lambda member: (member.rank, member.id))
    )


def risk_classes_of(pack: ResolvedPack) -> tuple[OrdinalClassView, ...]:
    """Return the declared operational-risk vocabulary as name-and-rank pairs, by rank.

    ADR-0073. An EMPTY tuple is a pack that declares no risk vocabulary at all, and is
    returned as such rather than as an error: module 14 reports the objective as
    `NOT_DECLARED` and ranks on the remaining three. A vocabulary that exists while no
    event type names a member is the same situation one level down and is reported the
    same way.
    """
    return tuple(
        OrdinalClassView(id=declared.id, rank=declared.rank)
        for declared in sorted(pack.risk_classes, key=lambda member: (member.rank, member.id))
    )


def mutable_attributes_of(pack: ResolvedPack) -> tuple[MutabilityView, ...]:
    """Return, per event type, the attributes a pack declares a hypothetical may change.

    ADR-0067. Whether an attribute is a lever is a claim about the domain, so it is read
    from the pack and never derived here -- deriving it would be an unfalsifiable domain
    judgement in engine code, the R-16 shape.

    **Every event type appears, including those declaring no changeable attribute.** An
    absent view and an empty one are different facts: the first says the type is not in this
    pack, the second says the pack was asked and declared nothing, and a consumer that
    dropped the empty rows could not tell them apart. This is the rule `actionability_of`
    already keeps for `actionable: false`.

    Sequenced by `event_type`, and each type's attributes sequenced by name, so two adapters
    over one pack produce one value and a digest over it is stable (`CONVENTIONS.md` §11).
    """
    return tuple(
        MutabilityView(
            event_type=event_type.id,
            mutable_attributes=tuple(
                AttributeView(
                    name=attribute.name,
                    type_name=attribute.type.value,
                    unit=attribute.unit,
                    admissible_values=attribute.admissible_values,
                    admissible_range=attribute.admissible_range,
                )
                for attribute in sorted(
                    (declared for declared in event_type.required_attributes if declared.mutable),
                    key=lambda declared: declared.name,
                )
            ),
        )
        for event_type in sorted(pack.event_types, key=lambda declared: declared.id)
    )
