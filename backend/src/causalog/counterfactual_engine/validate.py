"""Refuse an impossible world before anything is simulated (ADR-0066).

A hypothetical the domain does not admit is the most dangerous input this module can take,
because every downstream check passes on it. The propagation is arithmetic and will be
correct. The belief composes correctly. The report renders correctly. The premise is
unreachable, and nothing after this file can tell.

So validation is a SEPARATE PASS over the whole set, before propagation begins. A set
holding one inadmissible change never partially executes: a world built from four admitted
changes and one silently dropped is a world nobody asked for, described by an artifact that
names five.

FOUR GATES, EACH NAMING A DECLARATION
--------------------------------------
1. **The target exists.** A change naming an occurrence or participant the base world does
   not hold is refused. `docs/architecture.md` §2 calls this a hard error for this module,
   and it is: silently ignoring it would report a world in which the change was made.
2. **Lifecycle legality.** A state change is checked against the participant type's declared
   `LifecycleView.transitions`. A state machine is exactly the structure that makes "this
   world is impossible" decidable rather than a matter of taste.
3. **Process legality and mutability.** An insertion is checked against every declared
   process sequence, its variants and its optional steps. An attribute change is checked
   against the pack's `mutable` declaration and, where one exists, the declared bound.
4. **LAW-TIME.** A move that would place an antecedent at or after its own consequent is
   refused. LAW-TIME is not suspended inside a hypothetical.

**An absent declaration refuses and is reported as `DECLARATION_ABSENT`**, distinct from
every other reason. Those say the change was checked and refused; this says it could not be
checked at all. Collapsing the two would let an unconfigured run read as a validated one,
which is the `NOT_RUNNABLE` distinction every report in this engine keeps.

**No domain vocabulary appears below.** Nothing here reads a type name.
"""

from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel, ConfigDict

from causalog.core.ontology_view import AttributeView
from causalog.core.perturbation import carry_instant, precedes, shift_instant
from causalog.core.temporal import TemporalVerdict
from causalog.counterfactual_engine.context import SimulationContext
from causalog.counterfactual_engine.intervention import (
    ChangeAttribute,
    ChangeEntityState,
    InsertEvent,
    Intervention,
    InterventionKind,
    RejectedIntervention,
    RejectionReason,
    RemoveEvent,
    ShiftTiming,
)

__all__ = ["Admission", "admit"]


class Admission(BaseModel):
    """What survived validation, and the ledger of what did not.

    Both halves travel. A simulator that returned only the admitted set would let a caller
    believe five changes were applied when four were, and the fifth would be invisible in
    every artifact downstream.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    admitted: tuple[Intervention, ...] = ()
    rejected: tuple[RejectedIntervention, ...] = ()

    @property
    def nothing_admitted(self) -> bool:
        """Return whether every proposed change was refused.

        The caller publishes the ledger and NO world in that case. Publishing an unchanged
        world would read as "the change was simulated and had no effect", which is a much
        stronger claim than "the change was never admissible".
        """
        return not self.admitted


def _reject(
    intervention: Intervention,
    reason: RejectionReason,
    checked_against: str,
    detail: str,
) -> RejectedIntervention:
    """Return one ledger entry for a refused change."""
    return RejectedIntervention(
        intervention_id=intervention.intervention_id,
        kind=intervention.kind,
        reason=reason,
        checked_against=checked_against,
        detail=detail,
    )


def _check_shift(
    intervention: Intervention, payload: ShiftTiming, context: SimulationContext
) -> RejectedIntervention | None:
    """Refuse a move whose target is absent or which would reverse a stated precedence."""
    events = context.events_by_id()
    target = events.get(payload.target_event_id)
    if target is None:
        return _reject(
            intervention,
            RejectionReason.UNKNOWN_TARGET,
            "the occurrences this run holds",
            f"{payload.target_event_id} is not an occurrence in the base world. A change "
            "against an absent target would be reported as applied and would have moved "
            "nothing.",
        )
    moved = shift_instant(
        target.occurred_at,
        timedelta(seconds=payload.shift_seconds),
        derivation=f"proposed move of {payload.target_event_id}",
    )
    # Both directions. A move backwards can overtake an antecedent and a move forwards can
    # be overtaken by a consequent, and a gate checking one direction would admit the other.
    for link in context.links_into(payload.target_event_id):
        antecedent = events.get(link.source_event_id)
        if antecedent is None:
            continue
        if (
            precedes(carry_instant(antecedent.occurred_at, derivation="unmoved antecedent"), moved)
            is TemporalVerdict.VIOLATION
        ):
            return _reject(
                intervention,
                RejectionReason.WOULD_VIOLATE_LAW_TIME,
                "LAW-TIME, re-checked over the moved bounds",
                f"moving {payload.target_event_id} by {payload.shift_seconds} second(s) "
                f"would place it at or before {link.source_event_id}, which the stated "
                "graph holds as its antecedent. A hypothetical is not an exemption from "
                "LAW-TIME, so the change is refused rather than simulated and flagged.",
            )
    for link in context.links_from(payload.target_event_id):
        consequent = events.get(link.target_event_id)
        if consequent is None:
            continue
        if (
            precedes(moved, carry_instant(consequent.occurred_at, derivation="unmoved consequent"))
            is TemporalVerdict.VIOLATION
        ):
            return _reject(
                intervention,
                RejectionReason.WOULD_VIOLATE_LAW_TIME,
                "LAW-TIME, re-checked over the moved bounds",
                f"moving {payload.target_event_id} by {payload.shift_seconds} second(s) "
                f"would place it at or after {link.target_event_id}, which the stated "
                "graph holds as its consequence.",
            )
    return None


def _check_removal(
    intervention: Intervention, payload: RemoveEvent, context: SimulationContext
) -> RejectedIntervention | None:
    """Refuse a removal whose target the base world does not hold."""
    if payload.target_event_id not in context.events_by_id():
        return _reject(
            intervention,
            RejectionReason.UNKNOWN_TARGET,
            "the occurrences this run holds",
            f"{payload.target_event_id} is not an occurrence in the base world; there is "
            "nothing to remove, and reporting the removal would describe a world in which "
            "something absent was taken away.",
        )
    return None


def _admissible_positions(context: SimulationContext, event_type: str) -> tuple[str, ...]:
    """Return every declared sequence naming this kind of occurrence, as readable text."""
    named: list[str] = []
    for process in context.processes:
        if event_type in process.canonical_sequence:
            named.append(f"{process.id}.canonical_sequence")
        if event_type in process.optional_steps:
            named.append(f"{process.id}.optional_steps")
        for variant in process.variants:
            if event_type in variant.sequence:
                named.append(f"{process.id}.variants.{variant.id}")
    return tuple(sorted(set(named)))


def _check_insertion(
    intervention: Intervention, payload: InsertEvent, context: SimulationContext
) -> RejectedIntervention | None:
    """Refuse an insertion no declared process admits, or one anchored to an absent step."""
    if not context.processes:
        return _reject(
            intervention,
            RejectionReason.DECLARATION_ABSENT,
            "ontology process definitions",
            "the pack declares no process, so there is no sequence this insertion could be "
            "checked against. The change is refused rather than admitted: an unchecked "
            "insertion is not a validated one, and reporting it would make an unconfigured "
            "run look like a validated one.",
        )
    events = context.events_by_id()
    for anchor in (payload.after_event_id, payload.before_event_id):
        if anchor is not None and anchor not in events:
            return _reject(
                intervention,
                RejectionReason.UNKNOWN_TARGET,
                "the occurrences this run holds",
                f"{anchor} anchors this insertion and is not an occurrence in the base "
                "world, so the position the insertion claims cannot be checked.",
            )
    admissible = _admissible_positions(context, payload.event_type)
    if not admissible:
        return _reject(
            intervention,
            RejectionReason.STEP_NOT_ADMITTED_BY_PROCESS,
            "every declared canonical sequence, variant and optional step",
            f"no declared process admits {payload.event_type} at any position. Inserting it "
            "would simulate a world whose flow the domain description says cannot happen, "
            "and every check after this one would pass on it.",
        )
    return None


def _value_is_admissible(declared: AttributeView, value: str) -> str | None:
    """Return why the value is outside the attribute's declared bound, or None if inside.

    Two bounds, checked in the sequence a pack would read them. A declared vocabulary is a
    membership test on text. A declared range is a numeric test, and a value that will not
    parse as a number against a range-bounded attribute is outside the bound rather than
    unchecked -- admitting it would be the substitution this whole gate exists to prevent.
    """
    if declared.admissible_values and value not in declared.admissible_values:
        admitted = ", ".join(declared.admissible_values)
        return f"{value!r} is not one of the declared values ({admitted})"
    if declared.admissible_range is not None:
        low, high = declared.admissible_range
        try:
            reading = float(value)
        except ValueError:
            return (
                f"{value!r} does not parse as a number, and this attribute declares the "
                f"numeric bound [{low}, {high}]. An unparseable value against a numeric "
                "bound is outside it, not exempt from it"
            )
        if not low <= reading <= high:
            return f"{reading} lies outside the declared bound [{low}, {high}]"
    return None


def _check_attribute(
    intervention: Intervention, payload: ChangeAttribute, context: SimulationContext
) -> RejectedIntervention | None:
    """Refuse a change to an attribute the ontology does not declare changeable."""
    events = context.events_by_id()
    target = events.get(payload.target_event_id)
    if target is None:
        return _reject(
            intervention,
            RejectionReason.UNKNOWN_TARGET,
            "the occurrences this run holds",
            f"{payload.target_event_id} is not an occurrence in the base world.",
        )
    view = context.mutability_for(target.event_type)
    if view is None:
        return _reject(
            intervention,
            RejectionReason.DECLARATION_ABSENT,
            f"the ontology declaration for {target.event_type}",
            f"the pack declares nothing about {target.event_type}, so whether "
            f"{payload.attribute_name!r} may be set differently is unknown. An absent "
            "declaration refuses (ADR-0067): deciding it here would be an unfalsifiable "
            "claim about the domain made in engine code.",
        )
    declared = view.attribute(payload.attribute_name)
    if declared is None:
        return _reject(
            intervention,
            RejectionReason.ATTRIBUTE_NOT_DECLARED_CHANGEABLE,
            f"'mutable: true' on {target.event_type}.{payload.attribute_name}",
            f"{target.event_type}.{payload.attribute_name} is not declared changeable. "
            "Whether an operator could have set it differently is a claim about the domain, "
            "so it is read from the pack and never decided here; add 'mutable: true' to the "
            "attribute if the domain says otherwise.",
        )
    current = dict(target.changed_attributes).get(payload.attribute_name)
    if current is not None and current == payload.new_value:
        return _reject(
            intervention,
            RejectionReason.CHANGES_NOTHING,
            "the value the base world already holds",
            f"{target.event_type}.{payload.attribute_name} already holds "
            f"{payload.new_value!r}. Simulating it would produce an identical world, which a "
            "reader would take as evidence that the attribute does not matter.",
        )
    outside = _value_is_admissible(declared, payload.new_value)
    if outside is not None:
        return _reject(
            intervention,
            RejectionReason.VALUE_OUTSIDE_DECLARED_BOUND,
            f"the declared bound on {target.event_type}.{payload.attribute_name}",
            f"{outside}. The bound is what the DOMAIN says is possible; it is not the range "
            "this run witnessed, which is measured separately and reported as a support "
            "envelope (ADR-0070). A value can be possible and unsupported, and the two are "
            "kept apart so that case stays visible.",
        )
    return None


def _check_state(
    intervention: Intervention, payload: ChangeEntityState, context: SimulationContext
) -> RejectedIntervention | None:
    """Refuse a transition the participant type's declared state machine does not hold."""
    entity = context.entity(payload.target_entity_id)
    if entity is None:
        return _reject(
            intervention,
            RejectionReason.UNKNOWN_TARGET,
            "the participants this run holds",
            f"{payload.target_entity_id} is not a participant in the base world.",
        )
    lifecycle = context.lifecycle_for(entity.entity_type)
    if lifecycle is None:
        return _reject(
            intervention,
            RejectionReason.DECLARATION_ABSENT,
            f"the declared lifecycle for {entity.entity_type}",
            f"the pack declares no state machine for {entity.entity_type}, so no transition "
            "can be checked. An unchecked transition is not a legal one.",
        )
    legal = any(
        transition.from_state == payload.from_state and transition.to_state == payload.to_state
        for transition in lifecycle.transitions
    )
    if not legal:
        available = ", ".join(
            sorted(
                f"{transition.from_state}->{transition.to_state}"
                for transition in lifecycle.transitions
            )
        )
        return _reject(
            intervention,
            RejectionReason.TRANSITION_NOT_DECLARED,
            f"the declared lifecycle of {entity.entity_type}",
            f"{payload.from_state}->{payload.to_state} is not a declared transition. The "
            f"declared ones are: {available}. Simulating a condition the domain says cannot "
            "be reached produces an answer every later check will confirm and no reader "
            "could falsify.",
        )
    return None


def admit(interventions: tuple[Intervention, ...], context: SimulationContext) -> Admission:
    """Return the changes that may be simulated, and the ledger of those refused.

    Validation runs over the WHOLE set before propagation begins, so a set holding one
    inadmissible change never partially executes.

    Both collections are canonically sequenced, so two callers proposing one set in two
    sequences produce one admission and one address.

    Args:
        interventions: the proposed changes.
        context: the run's inputs, including the three declarations changes are checked
            against.

    Returns:
        The admitted changes and the rejection ledger.
    """
    admitted: list[Intervention] = []
    rejected: list[RejectedIntervention] = []
    for intervention in sorted(interventions, key=lambda item: item.sort_key()):
        payload = intervention.payload
        refusal: RejectedIntervention | None
        if payload.kind is InterventionKind.SHIFT_TIMING:
            refusal = _check_shift(intervention, payload, context)
        elif payload.kind is InterventionKind.REMOVE_EVENT:
            refusal = _check_removal(intervention, payload, context)
        elif payload.kind is InterventionKind.INSERT_EVENT:
            refusal = _check_insertion(intervention, payload, context)
        elif payload.kind is InterventionKind.CHANGE_ATTRIBUTE:
            refusal = _check_attribute(intervention, payload, context)
        else:
            refusal = _check_state(intervention, payload, context)
        if refusal is None:
            admitted.append(intervention)
        else:
            rejected.append(refusal)
    return Admission(
        admitted=tuple(admitted),
        rejected=tuple(sorted(rejected, key=lambda item: item.sort_key())),
    )
