"""Replay one entity's timeline against its declared lifecycle.

Design notes on two tensions the frozen `State`/`TimeInterval` contracts create, resolved
here and recorded rather than left implicit:

1. `State.derived_from_event_id` is mandatory -- every `State` traces to an event, never to
   "nothing." An entity's condition *before its first observed transition* therefore still
   needs a `State` record, and it is grounded in the same event that reveals it was needed
   (the precondition of the first legal transition). That bootstrap state's
   `provenance_class` is always `ASSUMED`: nothing produced it, the first transition's
   precondition merely requires it to have held. Whether the guess is the clean case (the
   entity's declared `initial_states`) or a genuine mid-lifecycle guess only changes
   whether it is counted as a data-quality signal (`docs/architecture.md` §Module 6),
   never whether it is `ASSUMED`.

2. Two adjacent states must not share their boundary instant, because
   `core.derivation.states_holding_at` treats both bounds as inclusive and
   `current_state` raises on genuine overlap. When the two transitions bounding a state are
   `verdict()`-`CERTAIN`, the shared boundary instant is unambiguous and the state's own
   `provenance_class` stays `OBSERVED` throughout -- only its `held_over.provenance`
   reflects boundary timing. When the verdict is `UNDETERMINED` (the transitions' causing
   events tie or overlap), the boundary is *not* pinned with unwarranted confidence: the
   state's `held_over.provenance` is set to `ASSUMED` and the uncertainty is counted in the
   `StateQualityReport` rather than asserted away.
"""

from __future__ import annotations

from dataclasses import dataclass

from causalog.core.errors import ContractViolationError
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import (
    UNKNOWN_EARLIEST,
    UNKNOWN_LATEST,
    Precision,
    TemporalVerdict,
    TimeInterval,
    verdict,
)
from causalog.core.types import Entity, Event, EvidenceRecord, State, Transition
from causalog.graph_engine.state_engine.legality import LifecycleIndex
from causalog.graph_engine.state_engine.quality import IllegalTransitionFinding

__all__ = ["EntityReplayResult", "replay_entity"]


@dataclass(frozen=True)
class EntityReplayResult:
    """One entity's replay: its states, transitions, and what stopped it if anything did."""

    states: tuple[State, ...] = ()
    transitions: tuple[Transition, ...] = ()
    evidence_records: tuple[EvidenceRecord, ...] = ()
    illegal_transition: IllegalTransitionFinding | None = None
    assumed_mid_lifecycle: bool = False
    uncertain_boundaries: int = 0


def _boundary_interval(start_event: Event, end_event: Event | None) -> tuple[TimeInterval, bool]:
    """Return the `held_over` interval for a state and whether its boundary is uncertain."""
    if end_event is None:
        return (
            TimeInterval(
                t_earliest=start_event.occurred_at.t_earliest,
                t_latest=UNKNOWN_LATEST,
                precision=start_event.occurred_at.precision,
                provenance=ProvenanceClass.ASSUMED,
                source="state_engine:still_holding",
            ),
            False,
        )
    pair_verdict = verdict(start_event.occurred_at, end_event.occurred_at)
    uncertain = pair_verdict is not TemporalVerdict.CERTAIN
    precision = (
        start_event.occurred_at.precision
        if start_event.occurred_at.precision == end_event.occurred_at.precision
        else Precision.DAY
    )
    if (
        precision is Precision.EXACT
        and start_event.occurred_at.t_earliest != end_event.occurred_at.t_earliest
    ):
        precision = Precision.DAY
    return (
        TimeInterval(
            t_earliest=start_event.occurred_at.t_earliest,
            t_latest=end_event.occurred_at.t_earliest,
            precision=precision,
            provenance=ProvenanceClass.ASSUMED if uncertain else ProvenanceClass.OBSERVED,
            source="state_engine:replay",
        ),
        uncertain,
    )


def replay_entity(
    entity: Entity,
    index: LifecycleIndex,
    sequenced_events: tuple[Event, ...],
    dataset_version: str,
) -> EntityReplayResult:
    """Walk `sequenced_events` (already canonically sorted) and derive this entity's states.

    Stops at the first illegal transition -- the offending event is reported, and every
    state legitimately derived before it is still returned. An event whose type triggers
    no declared transition is a no-op and is skipped (`docs/architecture.md`: "an event
    that changes nothing yields no transition").
    """
    taken_events: list[Event] = []
    taken_to_states: list[str] = []
    current_state: str | None = None
    illegal: IllegalTransitionFinding | None = None

    for event in sequenced_events:
        outcome = index.outcome_for(current_state, event.event_type)
        if outcome is None:
            continue
        # The entity's very first observed transition has no prior recorded state to
        # check against -- `current_state is None` never equals a declared `from_state`,
        # so `outcome_for` cannot report this as "legal" the normal way. Bootstrapping
        # (choosing/assuming the state that must have preceded it) happens once, below,
        # after this loop; here it is simply accepted.
        if current_state is None:
            taken_events.append(event)
            taken_to_states.append(outcome.to_state)
            current_state = outcome.to_state
            continue
        if not outcome.legal_from_current:
            illegal = IllegalTransitionFinding(
                entity_id=entity.entity_id,
                entity_type=entity.entity_type,
                offending_event_id=event.event_id,
                event_type=event.event_type,
                attempted_from_state=current_state,
                declared_from_states=outcome.candidate_from_states,
                attempted_to_state=outcome.to_state,
            )
            break
        taken_events.append(event)
        taken_to_states.append(outcome.to_state)
        current_state = outcome.to_state

    if not taken_events:
        return EntityReplayResult(illegal_transition=illegal)

    first_outcome = index.outcome_for(None, taken_events[0].event_type)
    if first_outcome is None:
        raise ContractViolationError(
            f"replay_entity: {taken_events[0].event_type!r} was accepted into "
            "taken_events by the loop above, so outcome_for must not return None for it "
            "on re-lookup; this indicates the lifecycle index changed between calls."
        )
    bootstrap_candidates = first_outcome.candidate_from_states
    assumed_mid_lifecycle = not any(
        candidate in index.lifecycle.initial_states for candidate in bootstrap_candidates
    )
    bootstrap_name = sorted(bootstrap_candidates)[0] if bootstrap_candidates else "UNKNOWN"

    bootstrap_interval = TimeInterval(
        t_earliest=UNKNOWN_EARLIEST,
        t_latest=taken_events[0].occurred_at.t_earliest,
        precision=Precision.DAY,
        provenance=ProvenanceClass.ASSUMED,
        source="state_engine:assumed_initial",
    )
    bootstrap_locator = f"state_engine:assumed_initial:{entity.entity_id}"
    bootstrap_evidence = EvidenceRecord(
        evidence_record_id=EvidenceRecord.address(dataset_version, bootstrap_locator),
        dataset_version=dataset_version,
        source_locator=bootstrap_locator,
        source_timezone=None,
    )
    bootstrap_state = State(
        state_id=State.address(entity.entity_id, bootstrap_name, bootstrap_interval),
        entity_id=entity.entity_id,
        state_name=bootstrap_name,
        held_over=bootstrap_interval,
        derived_from_event_id=taken_events[0].event_id,
        provenance_class=ProvenanceClass.ASSUMED,
        evidence_record_ids=(bootstrap_evidence.evidence_record_id,),
    )

    states: list[State] = [bootstrap_state]
    transitions: list[Transition] = []
    uncertain_boundaries = 0
    previous_state = bootstrap_state

    for position, (to_state_name, causing_event) in enumerate(
        zip(taken_to_states, taken_events, strict=False)
    ):
        next_event = taken_events[position + 1] if position + 1 < len(taken_events) else None
        interval, uncertain = _boundary_interval(causing_event, next_event)
        if uncertain:
            uncertain_boundaries += 1
        state = State(
            state_id=State.address(entity.entity_id, to_state_name, interval),
            entity_id=entity.entity_id,
            state_name=to_state_name,
            held_over=interval,
            derived_from_event_id=causing_event.event_id,
            provenance_class=ProvenanceClass.OBSERVED,
            evidence_record_ids=causing_event.evidence_record_ids,
        )
        transitions.append(
            Transition(
                transition_id=Transition.address(
                    previous_state.state_id, state.state_id, causing_event.event_id
                ),
                from_state_id=previous_state.state_id,
                to_state_id=state.state_id,
                causing_event_id=causing_event.event_id,
                provenance_class=ProvenanceClass.OBSERVED,
            )
        )
        states.append(state)
        previous_state = state

    return EntityReplayResult(
        states=tuple(states),
        transitions=tuple(transitions),
        evidence_records=(bootstrap_evidence,),
        illegal_transition=illegal,
        assumed_mid_lifecycle=assumed_mid_lifecycle,
        uncertain_boundaries=uncertain_boundaries,
    )
