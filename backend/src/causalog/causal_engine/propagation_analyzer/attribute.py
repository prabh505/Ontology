"""What a consequence is worth, and what a route is credited with of it.

**Say the caveat before the method**, as `causal_graph_builder.weights` does. Every figure
this module produces is an attribution estimate and not a measurement, for the reason stated
there and repeated on `MagnitudeShare.notice`: nothing in this repository identifies a
causal effect, so a share is comparable with another share and is not a quantity of anything
in the world.

The method, in three parts.

**The quantity.** A magnitude is whatever the ontology's `measurement_definitions` declare
it to be (ADR-0026). The pack's `graph_construction.magnitude_attributions` nominates one
declared measurement per effect type and `core.measurement` evaluates its operator tree over
the process instance that witnessed the consequence. **No formula appears below** -- if one
did, swapping the pack would change the declaration and not the arithmetic, which is
LAW-DOMAIN defeated by a value (`CONVENTIONS.md` §6a). The nomination is READ FROM THE
`graph_construction` BLOCK rather than duplicated into module 12's own, because the quantity
a propagation weight apportions and the quantity a consequence is worth are the same
quantity, and two declarations of it could disagree with no way to tell which was meant.

**The share.** A route reaching a consequence is credited with that consequence's own
`PropagationWeight` -- the share the Causal Graph Builder already attributed among the links
arriving there, which sums to one over them. This module recomputes none of it. Under the
diagnostic standing no weight was ever attributed, so the view hands out an equal share and
says so; a reader is never shown an attributed share and an equal one under one heading.

**The combination, which is declared and not assumed.** Whether two consequences' magnitudes
add is domain policy: two currency figures over distinct subjects add, two elapsed-time
figures over overlapping periods do not. The operator arrives from the pack's
`propagation_analysis.impact_aggregation` and the arithmetic lives in `core.attribution`.
A measurement with no declared operator yields no total and the set says which one lost it.

**Nothing below is ever read as zero.** A consequence whose measurement could not be
evaluated carries `unavailable_because` and is excluded from the total, and the set reports
how many of its members were measured against how many it holds -- because a total over
three of forty consequences is a different claim from a total over forty.
"""

from __future__ import annotations

from causalog.causal_engine.propagation_analyzer.context import PropagationContext
from causalog.causal_engine.propagation_analyzer.graph import ConsequenceSet, MagnitudeShare
from causalog.core.attribution import combine_magnitudes, share_of
from causalog.core.errors import ContractViolationError, OntologyMappingError
from causalog.core.measurement import evaluate_measurement
from causalog.core.types import Event

__all__ = ["consequence_set", "share_for"]


def _instance_events(event_id: str, context: PropagationContext) -> dict[str, Event]:
    """Return one event per type from the process instance that witnessed this consequence.

    A measurement is defined over one instance -- `state_engine` and
    `causal_graph_builder.weights` both evaluate them that way -- so the tree is walked
    against the instance that witnessed the consequence. When a consequence belongs to
    several instances the first by sorted identifier is used, which is a deterministic
    choice and is stated rather than left to iteration sequence.

    A consequence in no process instance yields itself alone, which will usually leave the
    tree unevaluable and is reported as unavailable, never as a magnitude of zero.
    """
    instances = context.instances_by_event_id().get(event_id, ())
    events = context.events_by_id()
    if not instances:
        target = events.get(event_id)
        return {target.event_type: target} if target is not None else {}
    chosen: dict[str, Event] = {}
    for member_id in context.events_of_instance(instances[0]):
        member = events.get(member_id)
        if member is not None and member.event_type not in chosen:
            chosen[member.event_type] = member
    return chosen


def share_for(event_id: str, weight: float, context: PropagationContext) -> MagnitudeShare:
    """Read one consequence's declared magnitude and the share a route is credited with.

    Five distinct failure sentences, each naming exactly what was missing, following
    `causal_graph_builder.weights._magnitude_of`. None of them is a zero.
    """
    target = context.events_by_id().get(event_id)
    if target is None:
        return MagnitudeShare(
            event_id=event_id,
            weight=weight,
            unavailable_because=(
                f"the consequence {event_id} is not in this run's fact set, so no "
                "measurement could be evaluated over the instance that witnessed it."
            ),
        )
    measurement_id = context.measurement_for(target.event_type)
    if measurement_id is None:
        return MagnitudeShare(
            event_id=event_id,
            weight=weight,
            unavailable_because=(
                "the pack declares no graph_construction.magnitude_attributions entry for "
                f"type {target.event_type}, so no quantity is nominated for this "
                "consequence and there is nothing to apportion."
            ),
        )
    measurement = context.measurement_by_id(measurement_id)
    if measurement is None:
        return MagnitudeShare(
            event_id=event_id,
            weight=weight,
            unavailable_because=(
                f"the pack nominates measurement {measurement_id!r} for type "
                f"{target.event_type}, which the ontology pack does not declare. The "
                "rule-pack loader cannot check this (VocabularyView carries no measurement "
                "ids), so it is reported here, naming the consequence that lost its "
                "magnitude."
            ),
        )
    try:
        reading = evaluate_measurement(
            measurement.expression,
            _instance_events(event_id, context),
            caller="propagation_analyzer.attribute",
        )
    except OntologyMappingError as error:
        return MagnitudeShare(
            event_id=event_id,
            weight=weight,
            unavailable_because=f"measurement {measurement.id} could not be evaluated: {error}",
        )
    if reading is None:
        return MagnitudeShare(
            event_id=event_id,
            weight=weight,
            unavailable_because=(
                f"measurement {measurement.id} is declared for type {target.event_type} but "
                "evaluated to nothing for this process instance -- an operand it names was "
                "not witnessed here. Reported rather than read as a magnitude of zero, "
                "which would put a quantity nobody measured into the total."
            ),
        )
    return MagnitudeShare(
        event_id=event_id,
        measurement_id=measurement.id,
        unit=measurement.unit,
        reading=reading,
        weight=weight,
        attributed=share_of(reading, weight),
    )


def consequence_set(
    shares: tuple[MagnitudeShare, ...], context: PropagationContext
) -> ConsequenceSet:
    """Combine one share per consequence into a set-level total under a declared operator.

    **The caller must hand one share per CONSEQUENCE, never one per route.** That is the
    whole no-double-counting guarantee and this function asserts it rather than trusting
    it: a repeated identifier raises here instead of silently doubling a total.

    All the shares must name one measurement. A set mixing two measurements has no single
    unit and its total would be a number with no name; the traversal groups by measurement
    before calling, and a mixed set is refused rather than combined.

    Raises:
        ContractViolationError: if two shares name one consequence, or if the measured
            shares name more than one measurement.
    """
    identifiers = [share.event_id for share in shares]
    if len(set(identifiers)) != len(identifiers):
        repeated = sorted({name for name in identifiers if identifiers.count(name) > 1})
        raise ContractViolationError(
            f"consequence_set received two shares for consequence(s) {repeated}. The set is "
            "the unit of attribution precisely so that a consequence reachable by several "
            "routes contributes once (prd.md §30); combining a per-route list here would "
            "double count it."
        )
    event_ids = tuple(sorted(identifiers))
    measured = tuple(share for share in shares if share.attributed is not None)
    named = sorted({share.measurement_id for share in measured if share.measurement_id})
    if len(named) > 1:
        raise ContractViolationError(
            f"consequence_set received shares naming measurements {named}. A set combining "
            "two measurements has no single unit, and its total would be a figure whose "
            "name nobody could write down."
        )
    if not measured:
        return ConsequenceSet(
            event_ids=event_ids,
            measured_member_count=0,
            combination_absent_because=(
                f"none of the {len(event_ids)} consequence(s) in this set carried an "
                "evaluable magnitude, so there is nothing to combine. Each one's own reason "
                "is on its share; this is not a total of zero."
            ),
        )
    measurement_id = named[0]
    declared = context.parameters.aggregation_for(measurement_id)
    unit = next((share.unit for share in measured if share.unit), None)
    if declared is None:
        return ConsequenceSet(
            event_ids=event_ids,
            measurement_id=measurement_id,
            unit=unit,
            measured_member_count=len(measured),
            combination_absent_because=(
                "the pack declares no propagation_analysis.impact_aggregation entry for "
                f"measurement {measurement_id}, so it does not say how two of these "
                "readings combine. Whether they add is domain policy -- currency over "
                "distinct subjects adds, elapsed time over overlapping periods does not -- "
                "and defaulting to a sum here would be a judgement wearing a schema "
                "default's clothes (ADR-0049)."
            ),
        )
    readings = tuple(share.attributed for share in measured if share.attributed is not None)
    return ConsequenceSet(
        event_ids=event_ids,
        measurement_id=measurement_id,
        unit=unit,
        combination=declared.operator,
        combined=combine_magnitudes(readings, declared.operator),
        measured_member_count=len(measured),
    )
