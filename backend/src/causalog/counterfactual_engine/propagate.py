r"""Push a change through the stated graph, one edge kind at a time (ADR-0069).

prd.md §26's five kinds are five different claims, and a propagation that treats them alike
gets the most important case backwards.

THE ERROR THIS FILE EXISTS TO NOT MAKE
---------------------------------------
**Removing one of three contributing causes does not prevent the outcome.** The other two
still hold it up. `GLOSSARY.md`'s Joint Cause Group entry states it, and
`causal_graph_builder.graph.JointCauseGroup` names this module directly: over an independent
link the answer to "what if this were removed" is that the consequence does not occur; over
one member of a joint group the honest answer is that it may still occur, because the others
remain. A simulator that answers the first question in the second situation overstates the
change by the whole of the group's contribution, and does so with every downstream check
passing.

So elimination and reduction are separate findings, computed separately:

* **Elimination is a re-reachability question.** A consequence stops occurring when NOTHING
  transmits into it any more -- not when the removed shares happen to sum to one. Shares
  summing to one under an apportionment is an arithmetic coincidence; nothing reaching the
  consequence is a fact about the graph. Reading the first as the second is exactly how a
  partial removal comes to be reported as a prevention (ADR-0061's diff, not a subtraction,
  which is also what makes it correct on a diamond).
* **Reduction is what is left over.** The consequence still occurs and is smaller by the
  share the removed causes were apportioned.

THE FIVE KINDS
--------------
| kind          | under a hypothetical                                              |
|---------------|-------------------------------------------------------------------|
| `DIRECT`      | transmits while its antecedent survives                            |
| `CONDITIONAL` | transmits only while its recorded condition still holds            |
| `CONTRIBUTING`| transmits per member; a surviving member keeps the consequence     |
| `AMPLIFYING`  | not transmission -- scales magnitude; removing it undoes the scale |
| `INHIBITING`  | the same, on the same scale, in the other direction                |

Modifiers are excluded from the transmission basis, mirroring the `CONTRIBUTING_KINDS` /
`MODIFIER_KINDS` split `causal_graph_builder.weights` already draws. An amplifier removed
from the graph makes the consequence smaller; it does not make it absent.

HOW A CONDITION IS RE-EVALUATED, AND WHAT THAT TEST CANNOT SEE
---------------------------------------------------------------
`ConditionalCause.condition_expression` is the exact expression the rule engine evaluated,
recorded as text. This module cannot re-evaluate it: the rule DSL holds condition TREES and
what reaches a promoted edge is their rendering, so re-running one here would mean parsing a
rendering -- the thing `core/precedence.py` refuses for the same reason.

What it does instead is a **containment test, stated as one**: a condition whose recorded
expression names an attribute or a state the hypothetical changed is treated as INVALIDATED
and stops transmitting. The test is conservative by construction -- it stops transmission it
cannot prove should continue, so it UNDER-claims consequences rather than over-claiming
them, which is the direction this project errs in everywhere else. **It cannot see a
condition that should have been invalidated and names nothing that changed**, and every
outcome resting on such a link is flagged so the reader knows which way the uncertainty
runs.

HOW TIME MOVES, AND WHERE IT DOES NOT
--------------------------------------
The graph gives no transfer function for time. A causal link says one occurrence produced
another; it does not say by how much the second moves when the first does, and inventing a
figure would be the manufactured precision R-20 names.

What the run does supply is module 1's measurement of which instants the source COMPUTED
rather than recorded (`core.precedence`). **An occurrence's instant moves under a change
exactly when that measurement says the source derived it from the moved one**, and by the
same amount. Everything else keeps its instant and is reported as `NOT_RETIMED` -- an
absence stated, so that a reader never concludes the timing was checked and found
unaffected.

**No domain vocabulary appears below.** Nothing here reads a type name.
"""

from __future__ import annotations

import re
from datetime import timedelta
from enum import Enum
from typing import Final

from causalog.causal_engine.propagation_analyzer import TruncationReason, TruncationRecord
from causalog.core.measurement import evaluate_measurement
from causalog.core.perturbation import (
    SimulatedInstant,
    carry_instant,
    shift_instant,
    transmitted_reading,
    unscale_reading,
)
from causalog.core.types import Event
from causalog.core.types.causal_edge import (
    AmplifyingCause,
    CausalEdgeKind,
    InhibitingCause,
)
from causalog.counterfactual_engine.context import SimulationContext, SimulationLink
from causalog.counterfactual_engine.intervention import (
    ChangeAttribute,
    ChangeEntityState,
    Intervention,
    RemoveEvent,
    ShiftTiming,
)
from causalog.counterfactual_engine.world import DeltaKind, EventDelta, SimulatedEvent

__all__ = [
    "MAX_SIMULATION_DEPTH",
    "ConditionStanding",
    "Propagation",
    "propagate",
]

#: The absolute ceiling on how far a hypothetical travels, whatever a pack declares. A
#: CEILING and not a default: the pack's `maximum_simulation_depth` is the operative bound
#: and this only stops one being declared that prd.md §55's five seconds cannot honour.
#: `MAX_PROPAGATION_DEPTH` is module 12's equivalent and is named the same way for the same
#: reason (`CONVENTIONS.md` §5: no magic literal inline).
MAX_SIMULATION_DEPTH: Final[int] = 32

#: The kinds that carry a consequence's occurrence. Mirrors
#: `causal_graph_builder.weights.CONTRIBUTING_KINDS`; imported would be better and is not
#: possible without making that module's private split public, so the two are kept
#: identical and this comment names the pair.
TRANSMISSION_KINDS: Final[frozenset[CausalEdgeKind]] = frozenset(
    {CausalEdgeKind.DIRECT, CausalEdgeKind.CONDITIONAL, CausalEdgeKind.CONTRIBUTING}
)

#: The kinds that scale a consequence's size without carrying its occurrence.
MODIFIER_KINDS: Final[frozenset[CausalEdgeKind]] = frozenset(
    {CausalEdgeKind.AMPLIFYING, CausalEdgeKind.INHIBITING}
)

#: Fixed text. Printed beside every consequence whose survival rests on a qualified link,
#: because the containment test below is conservative in one direction only.
CONDITION_TEST_NOTICE: Final[str] = (
    "A qualified link's condition was re-checked by asking whether its recorded expression "
    "NAMES anything this change touched. That test is conservative: it stops a link it "
    "cannot prove should keep transmitting, so consequences are under-claimed rather than "
    "over-claimed. It cannot see a condition that should have stopped holding and names "
    "nothing that changed."
)


class ConditionStanding(str, Enum):
    """What a hypothetical did to a qualified link's condition."""

    HOLDS_UNCHANGED = "HOLDS_UNCHANGED"
    """The condition held in the base world and names nothing the change touched."""

    INVALIDATED = "INVALIDATED"
    """The condition's recorded expression names something the change touched."""

    DID_NOT_HOLD = "DID_NOT_HOLD"
    """The condition did not hold in the base world either, so the link never transmitted."""


class Propagation:
    """What a hypothetical did to every occurrence it reached.

    A small immutable holder rather than a model. The artifacts that leave this package are
    `SimulatedEvent` and `EventDelta`, both built here; publishing a third model would put
    one fact into two types that could drift apart -- the reason
    `propagation_analyzer.counterfactual.PreventedConsequence` is a holder too.
    """

    __slots__ = (
        "condition_findings",
        "deltas",
        "events",
        "reached_count",
        "truncations",
        "unchanged_count",
    )

    def __init__(
        self,
        *,
        events: tuple[SimulatedEvent, ...],
        deltas: tuple[EventDelta, ...],
        truncations: tuple[TruncationRecord, ...],
        reached_count: int,
        unchanged_count: int,
        condition_findings: tuple[tuple[str, ConditionStanding], ...],
    ) -> None:
        """Record one propagation and everything it observed on the way."""
        self.events = events
        self.deltas = deltas
        self.truncations = truncations
        self.reached_count = reached_count
        self.unchanged_count = unchanged_count
        self.condition_findings = condition_findings

    @property
    def rests_on_a_qualified_link(self) -> bool:
        """Return whether any finding depends on the conservative condition test."""
        return any(
            standing is not ConditionStanding.HOLDS_UNCHANGED
            for _, standing in self.condition_findings
        )


def _names(expression: str, token: str) -> bool:
    """Return whether an expression names this token, on a word boundary.

    A word boundary rather than a substring, so an attribute called `mode` does not match
    every expression containing the letters. The test's limits are stated in this module's
    docstring and printed beside every finding that rests on it.
    """
    pattern = rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])"
    return re.search(pattern, expression) is not None


def _effective_depth(context: SimulationContext) -> int | None:
    """Return the depth a hypothetical may travel, or None when the pack declares none.

    `None` is the refusal, not a default. An absent declaration means the policy cannot run
    and is reported as a `PolicyGap` (ADR-0049, ADR-0071); supplying a number here would
    make an unconfigured run look like a configured one.
    """
    declared = context.parameters.maximum_simulation_depth
    if declared is None:
        return None
    return min(declared, MAX_SIMULATION_DEPTH)


def _magnitude_of(
    event: Event, context: SimulationContext
) -> tuple[float | None, str | None, str | None, str | None]:
    """Return `(reading, measurement_id, unit, absent_because)` for one occurrence.

    A walk of the pack's declared operator tree through `core.measurement`, never a formula.
    No arithmetic over a domain metric appears in this package
    (`scripts/check_metrics_are_declared.py`, ADR-0026).
    """
    measurement_id = context.propagation.measurement_for(event.event_type)
    if measurement_id is None:
        return (
            None,
            None,
            None,
            f"the pack declares no magnitude measurement for {event.event_type}, so this "
            "consequence has no size to change. The COUNT is still a measurement and is "
            "reported; the size is not, and is not reported as zero.",
        )
    measurement = context.propagation.measurement_by_id(measurement_id)
    if measurement is None:
        return (
            None,
            measurement_id,
            None,
            f"the pack attributes {measurement_id} to {event.event_type} and declares no "
            "measurement by that name, so the attribution resolves to nothing.",
        )
    instance_events = {held.event_type: held for held in _instance_events(event, context)}
    reading = evaluate_measurement(
        measurement.expression, instance_events, caller="counterfactual_engine.propagate"
    )
    if reading is None:
        return (
            None,
            measurement_id,
            measurement.unit,
            f"{measurement_id} could not be evaluated over this process instance: an "
            "occurrence or an attribute its declared tree names is absent.",
        )
    return (reading, measurement_id, measurement.unit, None)


def _instance_events(event: Event, context: SimulationContext) -> tuple[Event, ...]:
    """Return the occurrences of the process instance this consequence belongs to.

    An occurrence belonging to several instances resolves to the first by sorted identifier,
    which is the deterministic, stated choice `causal_graph_builder.weights` makes for the
    same situation. A different choice would be defensible; an undeclared one would not.
    """
    instances = context.propagation.instances_by_event_id().get(event.event_id, ())
    if not instances:
        return (event,)
    chosen = sorted(instances)[0]
    events = context.events_by_id()
    return tuple(
        events[identifier]
        for identifier in context.propagation.events_of_instance(chosen)
        if identifier in events
    )


def _seed_state(
    admitted: tuple[Intervention, ...],
) -> tuple[frozenset[str], dict[str, float], dict[str, dict[str, str]], tuple[str, ...]]:
    """Return the direct effect of the admitted changes, before anything propagates.

    Four things, kept apart because they behave differently downstream: what was removed,
    what moved and by how much, which attributes hold new values, and which tokens a
    hypothetical touched (used by the condition test).
    """
    removed: set[str] = set()
    shifted: dict[str, float] = {}
    attributes: dict[str, dict[str, str]] = {}
    touched: set[str] = set()
    for intervention in admitted:
        payload = intervention.payload
        if isinstance(payload, RemoveEvent):
            removed.add(payload.target_event_id)
        elif isinstance(payload, ShiftTiming):
            shifted[payload.target_event_id] = payload.shift_seconds
        elif isinstance(payload, ChangeAttribute):
            attributes.setdefault(payload.target_event_id, {})[payload.attribute_name] = (
                payload.new_value
            )
            touched.add(payload.attribute_name)
        elif isinstance(payload, ChangeEntityState):
            touched.add(payload.from_state)
            touched.add(payload.to_state)
    return frozenset(removed), shifted, attributes, tuple(sorted(touched))


def _condition_standing(link: SimulationLink, touched: tuple[str, ...]) -> ConditionStanding:
    """Return what a hypothetical did to one qualified link's condition."""
    payload = link.payload
    if payload.edge_kind is not CausalEdgeKind.CONDITIONAL:
        return ConditionStanding.HOLDS_UNCHANGED
    if not payload.condition_holds:
        return ConditionStanding.DID_NOT_HOLD
    for token in touched:
        if _names(payload.condition_expression, token):
            return ConditionStanding.INVALIDATED
    return ConditionStanding.HOLDS_UNCHANGED


def _retiming(
    event: Event,
    shifted: dict[str, float],
    settled: dict[str, SimulatedInstant],
    context: SimulationContext,
) -> tuple[SimulatedInstant, bool]:
    """Return this occurrence's instant in the hypothetical, and whether it moved.

    A directly moved occurrence moves by the stated amount. Anything else moves only when
    module 1's measurement says the source COMPUTED this instant from a moved one -- see
    the module docstring for why no other transfer function is invented.
    """
    direct = shifted.get(event.event_id)
    if direct is not None:
        return (
            shift_instant(
                event.occurred_at,
                timedelta(seconds=direct),
                derivation=f"moved directly by the stated change of {direct} second(s)",
            ),
            True,
        )
    index = context.derived_precedence
    if index is not None:
        for moved_id, seconds in sorted(shifted.items()):
            moved = context.events_by_id().get(moved_id)
            if moved is None:
                continue
            entry = index.precedence_for(moved.occurred_at.source, event.occurred_at.source)
            if entry is None:
                continue
            settled_shift = settled.get(moved_id)
            carried = settled_shift.shifted_by_seconds if settled_shift is not None else seconds
            return (
                shift_instant(
                    event.occurred_at,
                    timedelta(seconds=carried),
                    derivation=(
                        f"moved with {moved_id}: check {entry.check_id} measured that the "
                        f"source COMPUTED this instant from that one, agreeing on "
                        f"{entry.agreement_rate:.4f} of {entry.evaluated} evaluable record(s)"
                    ),
                ),
                True,
            )
    return (
        carry_instant(
            event.occurred_at,
            derivation=(
                "not moved: no measurement says the source computed this instant from one "
                "the change moved, and the graph declares no transfer function for time. An "
                "instant moved without one would be manufactured precision (R-20)."
            ),
        ),
        False,
    )


def propagate(admitted: tuple[Intervention, ...], context: SimulationContext) -> Propagation:
    """Push the admitted changes through the stated graph and return what they did.

    Breadth-first from the occurrences the changes touched, so each consequence settles at
    its shortest distance on first reach -- module 12's `walk` makes the same choice for the
    same reason. Bounded by the pack's declared depth and node cap under
    `MAX_SIMULATION_DEPTH`; reaching a bound is a `TruncationRecord` and never a completed
    sweep.

    Args:
        admitted: the changes validation let through. Already canonically sequenced.
        context: the run's inputs.

    Returns:
        Every occurrence reached, in the hypothetical's terms, with the diff entries for
        those that changed and the truncations for where the sweep stopped.
    """
    removed, shifted, attribute_changes, touched = _seed_state(admitted)
    events = context.events_by_id()
    depth_bound = _effective_depth(context)
    node_cap = context.parameters.affected_subgraph_node_cap
    if depth_bound is None or node_cap is None:
        return Propagation(
            events=(),
            deltas=(),
            truncations=(),
            reached_count=0,
            unchanged_count=0,
            condition_findings=(),
        )

    seeds = sorted(set(removed) | set(shifted) | set(attribute_changes))
    settled_instants: dict[str, SimulatedInstant] = {}
    present: dict[str, bool] = {}
    truncations: list[TruncationRecord] = []
    condition_findings: list[tuple[str, ConditionStanding]] = []
    simulated: list[SimulatedEvent] = []
    deltas: list[EventDelta] = []
    unchanged = 0

    frontier: list[tuple[str, int]] = [(identifier, 0) for identifier in seeds]
    seen: set[str] = set(seeds)
    sequence: list[tuple[str, int]] = []
    while frontier:
        if len(seen) > node_cap:
            truncations.append(
                TruncationRecord(
                    reason=TruncationReason.NODE_CAP,
                    at_event_id=frontier[0][0],
                    depth=frontier[0][1],
                    unwalked_event_ids=tuple(sorted(identifier for identifier, _ in frontier)),
                    detail=(
                        f"the sweep reached the declared cap of {node_cap} occurrence(s). "
                        "What follows describes part of the change's reach and is reported "
                        "as truncated, never as the whole of it."
                    ),
                )
            )
            break
        identifier, depth = frontier.pop(0)
        sequence.append((identifier, depth))
        if depth >= depth_bound:
            onward = tuple(
                sorted(
                    link.target_event_id
                    for link in context.links_from(identifier)
                    if link.target_event_id not in seen
                )
            )
            if onward:
                truncations.append(
                    TruncationRecord(
                        reason=TruncationReason.DEPTH_BOUND,
                        at_event_id=identifier,
                        depth=depth,
                        unwalked_event_ids=onward,
                        detail=(
                            f"the sweep reached the declared depth of {depth_bound}. Belief "
                            "composes under the weakest link, so a further step could not "
                            "have raised any figure here -- but the consequences beyond it "
                            "are unwalked and are named rather than omitted."
                        ),
                    )
                )
            continue
        for link in context.links_from(identifier):
            onward_id = link.target_event_id
            if onward_id not in seen:
                seen.add(onward_id)
                frontier.append((onward_id, depth + 1))

    for identifier, _ in sequence:
        event = events.get(identifier)
        if event is None:
            continue
        instant, moved = _retiming(event, shifted, settled_instants, context)
        settled_instants[identifier] = instant

        incoming = context.links_into(identifier)
        transmitted_in_base: list[SimulationLink] = []
        stopped: list[SimulationLink] = []
        for link in incoming:
            if link.payload.edge_kind not in TRANSMISSION_KINDS:
                continue
            standing = _condition_standing(link, touched)
            if link.payload.edge_kind is CausalEdgeKind.CONDITIONAL:
                condition_findings.append((identifier, standing))
            if standing is ConditionStanding.DID_NOT_HOLD:
                continue
            transmitted_in_base.append(link)
            source_gone = link.source_event_id in removed or not present.get(
                link.source_event_id, True
            )
            if source_gone or standing is ConditionStanding.INVALIDATED:
                stopped.append(link)

        is_removed = identifier in removed
        eliminated = bool(transmitted_in_base) and len(stopped) == len(transmitted_in_base)
        occurs = not is_removed and not eliminated
        present[identifier] = occurs

        reading, measurement_id, unit, absent = _magnitude_of(event, context)
        simulated_reading: float | None = None
        simulated_absent: str | None = absent
        removed_shares = tuple(sorted(link.weight for link in stopped))
        scaled = False
        if occurs and reading is not None:
            carried = transmitted_reading(reading, removed_shares, eliminated=False)
            for link in incoming:
                # `isinstance` rather than a membership test on the kind: the two modifier
                # payloads are the only ones carrying `magnitude_multiplier`, and narrowing
                # the union by the field's own type is what lets the reader -- and the type
                # checker -- see that the attribute below always exists.
                modifier = link.payload
                if not isinstance(modifier, AmplifyingCause | InhibitingCause):
                    continue
                if link.source_event_id not in removed and present.get(link.source_event_id, True):
                    continue
                undone = unscale_reading(carried, modifier.magnitude_multiplier)
                if undone is None:
                    carried = 0.0
                    simulated_absent = (
                        "a link that suppressed this consequence entirely (multiplier 0.0) "
                        "was removed, so what the consequence would have been without it is "
                        "not recoverable from a measured nothing. It is unbounded rather "
                        "than infinite, and is reported as unmeasurable rather than as zero."
                    )
                    break
                carried = undone
                scaled = True
            simulated_reading = None if simulated_absent is not None else carried
        elif not occurs:
            simulated_absent = (
                "this occurrence does not happen in the hypothetical, so it has no size."
            )

        attributes = tuple(sorted(dict(event.changed_attributes).items()))
        changed_here = attribute_changes.get(identifier)
        if changed_here:
            merged = dict(attributes)
            merged.update(changed_here)
            attributes = tuple(sorted(merged.items()))

        simulated.append(
            SimulatedEvent(
                event_id=identifier,
                base_event_id=identifier,
                event_type=event.event_type,
                occurred_at=instant,
                attributes=attributes,
                present=occurs,
                magnitude=simulated_reading,
                measurement_id=measurement_id,
                unit=unit,
                magnitude_absent_because=simulated_absent,
            )
        )

        kinds: set[DeltaKind] = set()
        if is_removed:
            kinds.add(DeltaKind.REMOVED)
        elif eliminated:
            kinds.add(DeltaKind.ELIMINATED)
        if moved:
            kinds.add(DeltaKind.RETIMED)
        elif identifier not in seeds and shifted:
            kinds.add(DeltaKind.NOT_RETIMED)
        if changed_here:
            kinds.add(DeltaKind.ATTRIBUTE_CHANGED)
        if occurs and stopped and not eliminated:
            kinds.add(DeltaKind.MAGNITUDE_REDUCED)
        if scaled:
            kinds.add(DeltaKind.MAGNITUDE_SCALED)
        if any(
            standing is ConditionStanding.INVALIDATED
            for held, standing in condition_findings
            if held == identifier
        ):
            kinds.add(DeltaKind.CONDITION_INVALIDATED)

        if not kinds:
            unchanged += 1
            continue

        deltas.append(
            EventDelta(
                event_id=identifier,
                event_type=event.event_type,
                kinds=tuple(sorted(kinds, key=lambda kind: kind.value)),
                present_in_base=True,
                present_in_simulated=occurs,
                base_instant=event.occurred_at.t_earliest.isoformat(),
                simulated_instant=instant.t_earliest.isoformat(),
                shifted_by_seconds=instant.shifted_by_seconds if moved else None,
                base_magnitude=reading,
                simulated_magnitude=simulated_reading,
                measurement_id=measurement_id,
                unit=unit,
                detail=_delta_detail(identifier, kinds, removed_shares, len(transmitted_in_base)),
            )
        )

    return Propagation(
        events=tuple(sorted(simulated, key=lambda item: item.sort_key())),
        deltas=tuple(sorted(deltas, key=lambda item: item.sort_key())),
        truncations=tuple(truncations),
        reached_count=len(sequence),
        unchanged_count=unchanged,
        condition_findings=tuple(sorted(set(condition_findings))),
    )


def _delta_detail(
    identifier: str,
    kinds: set[DeltaKind],
    removed_shares: tuple[float, ...],
    basis_size: int,
) -> str:
    """Return plain language for one delta, naming the identifier and what happened."""
    if DeltaKind.REMOVED in kinds:
        return f"{identifier} was removed by the stated change."
    if DeltaKind.ELIMINATED in kinds:
        return (
            f"nothing transmits into {identifier} any more: all {basis_size} link(s) that "
            "carried it stopped. This is a re-reachability finding and not a subtraction -- "
            "a consequence with any surviving antecedent would still be here."
        )
    if DeltaKind.MAGNITUDE_REDUCED in kinds:
        return (
            f"{identifier} STILL OCCURS and is smaller: {len(removed_shares)} of "
            f"{basis_size} link(s) that carried it stopped, and the rest still hold it up. "
            "The share removed is an apportionment the Causal Graph Builder attributed, not "
            "a measurement of anything in the world."
        )
    if DeltaKind.RETIMED in kinds:
        return f"{identifier} happens at a different instant in this hypothetical."
    if DeltaKind.NOT_RETIMED in kinds:
        return (
            f"{identifier} was reached by the change and its instant did NOT move: no "
            "measurement says the source computed it from an instant the change moved."
        )
    if DeltaKind.ATTRIBUTE_CHANGED in kinds:
        return f"{identifier} holds a different value for a declared changeable attribute."
    return f"{identifier} was reached by the change."
