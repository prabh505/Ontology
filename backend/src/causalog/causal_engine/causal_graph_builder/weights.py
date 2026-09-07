"""Propagation weight: how much of an effect's magnitude a cause is credited with.

**Say the caveat before the method.** This is an attribution estimate and not a
measurement. Nothing in this repository identifies a causal effect: no counterfactual was
observed, no confounder was adjusted for, and a cause the engine never proposed receives no
share -- so the shares sum to one over the *modelled* causes and not over the real ones. Two
weights are comparable with each other; neither is a quantity of anything in the world. The
sentence is fixed text on `graph.ATTRIBUTION_NOT_MEASUREMENT_NOTICE`, is a property rather
than a field so a revision cannot soften it, and is printed above every weight in the report.

The method, in three parts.

**The magnitude.** A magnitude in this system is whatever the ontology's
`measurement_definitions` declare it to be (ADR-0026). The pack's
`graph_construction.magnitude_attributions` maps an effect's event type to one declared
measurement; `core.measurement` evaluates its operator tree over the process instance the
effect belongs to. No formula appears here -- if one did, swapping the pack would change the
declaration and not the arithmetic, which is LAW-DOMAIN defeated by a value
(`CONVENTIONS.md` §6a).

**The basis, and what is excluded from it.** Normalization runs over an effect's incoming
`DIRECT`, `CONDITIONAL` and `CONTRIBUTING` edges. `AMPLIFYING` and `INHIBITING` are
**modifiers, not contributors**: prd.md §26 defines them as changing the magnitude of a
relation that already exists rather than originating it. Giving a modifier a share of the
magnitude would present it as one of the causes, and would take that share away from the
causes that are. They are weighted separately under `MODIFIER_MULTIPLIER`.

**The fallback, reported as a different thing.** When no magnitude is declared or the
declared one cannot be evaluated for this instance, the weight is the edge's share of the
summed CONFIDENCE over the same basis. That is a share of belief, not a share of a quantity.
It is carried under a distinct `WeightBasis` and the report names every effect that fell
back, because printing the two under one heading would be the LAW-EVIDENCE defect: one
number meaning two things.
"""

from __future__ import annotations

from causalog.causal_engine.causal_graph_builder.context import GraphBuildContext
from causalog.causal_engine.causal_graph_builder.graph import PropagationWeight, WeightBasis
from causalog.causal_engine.confidence_scorer import ScoredEdge
from causalog.core.errors import OntologyMappingError
from causalog.core.measurement import evaluate_measurement
from causalog.core.ontology_view import MagnitudeMeasurementView
from causalog.core.types import Event
from causalog.core.types.causal_edge import AmplifyingCause, CausalEdgeKind, InhibitingCause

__all__ = [
    "CONTRIBUTING_KINDS",
    "MODIFIER_KINDS",
    "MagnitudeReading",
    "weights_for_effect",
]

#: The kinds that share out an effect's magnitude. Contributors in the ordinary sense: each
#: one is claimed to have produced some of the effect.
CONTRIBUTING_KINDS = frozenset(
    {CausalEdgeKind.DIRECT, CausalEdgeKind.CONDITIONAL, CausalEdgeKind.CONTRIBUTING}
)

#: The kinds that modify a magnitude rather than producing it (prd.md §26). Excluded from
#: the normalization basis; see this module's docstring for why that is not an oversight.
MODIFIER_KINDS = frozenset({CausalEdgeKind.AMPLIFYING, CausalEdgeKind.INHIBITING})


class MagnitudeReading:
    """One effect's magnitude, or the stated reason there is none.

    A small immutable holder rather than a model: it never leaves this module, and
    `PropagationWeight` is the artifact that does.
    """

    __slots__ = ("measurement_id", "reading", "unavailable_because", "unit")

    def __init__(
        self,
        *,
        measurement_id: str | None,
        unit: str | None,
        reading: float | None,
        unavailable_because: str | None,
    ) -> None:
        """Record a magnitude reading, or the stated reason there is none."""
        self.measurement_id = measurement_id
        self.unit = unit
        self.reading = reading
        self.unavailable_because = unavailable_because

    @property
    def available(self) -> bool:
        """Return whether a declared measurement produced a usable reading."""
        return self.reading is not None and self.measurement_id is not None


def _measurement_by_id(
    identifier: str, declared: tuple[MagnitudeMeasurementView, ...]
) -> MagnitudeMeasurementView | None:
    for measurement in declared:
        if measurement.id == identifier:
            return measurement
    return None


def _instance_events(
    target_event_id: str, context: GraphBuildContext, events_by_id: dict[str, Event]
) -> dict[str, Event]:
    """Return one event per type from the process instance the effect belongs to.

    A measurement is defined over one instance (`state_engine` evaluates them the same way),
    so the tree is walked against the instance that witnessed the effect. When the effect
    belongs to several instances the first by sorted identifier is used, which is a
    deterministic choice and is stated rather than left to iteration sequence.

    An effect in no process instance yields the effect alone, which will usually leave the
    tree unevaluable -- reported as unavailable, never as a magnitude of zero.
    """
    instances = context.instances_by_event_id().get(target_event_id, ())
    if not instances:
        target = events_by_id.get(target_event_id)
        return {target.event_type: target} if target is not None else {}
    chosen: dict[str, Event] = {}
    for event_id in context.events_of_instance(instances[0]):
        event = events_by_id.get(event_id)
        if event is not None and event.event_type not in chosen:
            chosen[event.event_type] = event
    return chosen


def _magnitude_of(
    target_event_id: str, context: GraphBuildContext, events_by_id: dict[str, Event]
) -> MagnitudeReading:
    """Read the declared magnitude for one effect, or say why there is none."""
    target = events_by_id.get(target_event_id)
    if target is None:
        return MagnitudeReading(
            measurement_id=None,
            unit=None,
            reading=None,
            unavailable_because=(
                f"the effect event {target_event_id} is not in this run's fact set, so no "
                "measurement could be evaluated over the instance that witnessed it."
            ),
        )
    attribution = context.parameters.attribution_for(target.event_type)
    if attribution is None:
        return MagnitudeReading(
            measurement_id=None,
            unit=None,
            reading=None,
            unavailable_because=(
                f"the pack declares no graph_construction.magnitude_attributions entry for "
                f"effect type {target.event_type}, so no quantity is nominated for this "
                "effect and there is nothing to apportion."
            ),
        )
    measurement = _measurement_by_id(attribution.measurement_id, context.magnitude_measurements)
    if measurement is None:
        return MagnitudeReading(
            measurement_id=None,
            unit=None,
            reading=None,
            unavailable_because=(
                f"the pack attributes {target.event_type}'s magnitude to measurement "
                f"{attribution.measurement_id!r}, which the ontology pack does not declare. "
                "The rule-pack loader cannot check this (VocabularyView carries no "
                "measurement ids), so it is reported here, naming the effect that lost its "
                "magnitude."
            ),
        )
    try:
        reading = evaluate_measurement(
            measurement.expression,
            _instance_events(target_event_id, context, events_by_id),
            caller="causal_graph_builder.weights",
        )
    except OntologyMappingError as error:
        return MagnitudeReading(
            measurement_id=None,
            unit=None,
            reading=None,
            unavailable_because=(f"measurement {measurement.id} could not be evaluated: {error}"),
        )
    if reading is None:
        return MagnitudeReading(
            measurement_id=None,
            unit=None,
            reading=None,
            unavailable_because=(
                f"measurement {measurement.id} is declared for effect type "
                f"{target.event_type} but evaluated to nothing for this process instance -- "
                "an operand it names was not witnessed here. Reported rather than read as a "
                "magnitude of zero, which would apportion a quantity nobody measured."
            ),
        )
    return MagnitudeReading(
        measurement_id=measurement.id,
        unit=measurement.unit,
        reading=reading,
        unavailable_because=None,
    )


def weights_for_effect(
    incoming: tuple[ScoredEdge, ...],
    context: GraphBuildContext,
    events_by_id: dict[str, Event],
) -> dict[tuple[str, str, str], PropagationWeight]:
    """Return one propagation weight per incoming claim over a single effect.

    Keyed by `(source, target, kind)` so a caller matches weights to claims by the same key
    everything else in this module is sequenced by.

    The contributing edges' weights sum to 1.0 whenever the basis is non-empty and its total
    is positive -- checked by a test rather than asserted here, because a sum that drifts by
    a float epsilon is not a defect and a sum that drifts by a tenth is.
    """
    if not incoming:
        return {}
    target_event_id = incoming[0].edge.target_event_id
    contributors = tuple(
        item for item in incoming if item.edge.payload.edge_kind in CONTRIBUTING_KINDS
    )
    modifiers = tuple(item for item in incoming if item.edge.payload.edge_kind in MODIFIER_KINDS)
    reading = _magnitude_of(target_event_id, context, events_by_id)
    normalization = (
        context.parameters.weight_normalization.value
        if context.parameters.weight_normalization is not None
        else None
    )

    basis_total = sum(item.edge.confidence.scalar for item in contributors)
    weights: dict[tuple[str, str, str], PropagationWeight] = {}
    for item in contributors:
        key = (
            item.edge.source_event_id,
            item.edge.target_event_id,
            item.edge.payload.edge_kind.value,
        )
        # The share is over confidence in BOTH bases. What differs is what is being shared
        # out: a declared quantity, or belief itself. The distinction is carried in `basis`
        # and stated in the report, never inferred from the number.
        share = (
            item.edge.confidence.scalar / basis_total
            if basis_total > 0.0
            else 1.0 / len(contributors)
        )
        if reading.available:
            weights[key] = PropagationWeight(
                weight=min(1.0, max(0.0, share)),
                basis=WeightBasis.MEASURED_MAGNITUDE,
                measurement_id=reading.measurement_id,
                measurement_unit=reading.unit,
                effect_magnitude=reading.reading,
                normalization=normalization,
                competing_edge_count=len(contributors),
            )
        else:
            weights[key] = PropagationWeight(
                weight=min(1.0, max(0.0, share)),
                basis=WeightBasis.CONFIDENCE_SHARE,
                normalization=normalization,
                competing_edge_count=len(contributors),
            )

    for item in modifiers:
        payload = item.edge.payload
        multiplier = (
            payload.magnitude_multiplier
            if isinstance(payload, AmplifyingCause | InhibitingCause)
            else None
        )
        key = (
            item.edge.source_event_id,
            item.edge.target_event_id,
            item.edge.payload.edge_kind.value,
        )
        # A modifier's weight is the multiplier's own effect, clamped into the field's
        # range. It is NOT a share and is not part of the sum: `competing_edge_count` is
        # zero to say so, and the basis names it. An amplifier's multiplier exceeds 1.0 by
        # its type's own invariant, so the clamp saturates -- the multiplier itself is
        # readable on the payload, which is where a reader who needs the real figure looks.
        weights[key] = PropagationWeight(
            weight=min(1.0, max(0.0, multiplier if multiplier is not None else 0.0)),
            basis=WeightBasis.MODIFIER_MULTIPLIER,
            normalization=normalization,
            competing_edge_count=0,
        )
    return weights
