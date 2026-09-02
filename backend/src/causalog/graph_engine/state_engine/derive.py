"""The State Engine's public entrypoint (module 6)."""

from __future__ import annotations

from dataclasses import dataclass

from causalog.core.ontology_view import DurationMeasurementView, LifecycleView
from causalog.core.run import OutputEnvelope
from causalog.core.types import (
    Entity,
    Event,
    EvidenceRecord,
    State,
    Timeline,
    TimelineEntryKind,
    TimelineView,
    Transition,
)
from causalog.graph_engine.state_engine.legality import build_lifecycle_index
from causalog.graph_engine.state_engine.measurement import evaluate_duration_seconds
from causalog.graph_engine.state_engine.quality import DurationStatistic, StateQualityReport
from causalog.graph_engine.state_engine.replay import replay_entity

__all__ = ["StateDerivationResult", "StateEngine"]


@dataclass(frozen=True)
class StateDerivationResult:
    """One run's `State`/`Transition` output, its citations, and its quality report."""

    states: tuple[State, ...]
    transitions: tuple[Transition, ...]
    evidence_records: tuple[EvidenceRecord, ...]
    report: StateQualityReport


class StateEngine:
    """Derive `State` and `Transition` values from events (module 6).

    Reads the ontology's declared lifecycles, as plain `LifecycleView`/
    `DurationMeasurementView` values adapted by `causalog.extraction.ontology_adapters`
    (this package may never import `ontology_runtime` directly, ADR-0002), to check legal
    transitions and derive state names; never invents a state absent from the ontology.
    """

    def __init__(
        self,
        lifecycles: tuple[LifecycleView, ...],
        duration_measurements: tuple[DurationMeasurementView, ...],
        ontology_hash: str,
    ) -> None:
        """Build the lifecycle index once, from the plain ontology views supplied."""
        self._ontology_hash = ontology_hash
        self._lifecycles = build_lifecycle_index(lifecycles)
        self._duration_measurements = duration_measurements

    def derive(
        self,
        timelines: tuple[Timeline, ...],
        entities: tuple[Entity, ...],
        events: tuple[Event, ...],
        envelope: OutputEnvelope,
    ) -> StateDerivationResult:
        """Replay every `ENTITY`-view timeline and return states, transitions, and a report."""
        entities_by_id = {entity.entity_id: entity for entity in entities}
        events_by_id = {event.event_id: event for event in events}
        entity_timelines = tuple(t for t in timelines if t.view is TimelineView.ENTITY)

        states: list[State] = []
        transitions: list[Transition] = []
        evidence_records: list[EvidenceRecord] = []
        illegal_findings = []
        assumed_initial = 0
        uncertain_boundaries = 0
        by_entity_type: dict[str, int] = {}

        for timeline in entity_timelines:
            entity_id = timeline.subject_entity_ids[0]
            entity = entities_by_id.get(entity_id)
            if entity is None:
                continue
            lifecycle_index = self._lifecycles.get(entity.entity_type)
            if lifecycle_index is None:
                continue
            sequenced_events = tuple(
                events_by_id[entry.event_id]
                for entry in timeline.entries
                if entry.kind is TimelineEntryKind.EVENT and entry.event_id in events_by_id
            )
            result = replay_entity(
                entity, lifecycle_index, sequenced_events, envelope.dataset_version
            )
            states.extend(result.states)
            transitions.extend(result.transitions)
            evidence_records.extend(result.evidence_records)
            if result.states:
                by_entity_type[entity.entity_type] = by_entity_type.get(
                    entity.entity_type, 0
                ) + len(result.states)
            if result.illegal_transition is not None:
                illegal_findings.append(result.illegal_transition)
            if result.assumed_mid_lifecycle:
                assumed_initial += 1
            uncertain_boundaries += result.uncertain_boundaries

        duration_statistics = self._duration_statistics(timelines, events_by_id)

        report = StateQualityReport(
            envelope=envelope,
            timelines_read=len(timelines),
            states_produced=len(states),
            transitions_produced=len(transitions),
            assumed_initial_states=assumed_initial,
            uncertain_boundary_states=uncertain_boundaries,
            illegal_transitions=tuple(illegal_findings),
            by_entity_type=tuple(sorted(by_entity_type.items())),
            duration_statistics=duration_statistics,
            not_checked=(
                "Duration measurements are evaluated per PROCESS_INSTANCE timeline using "
                "the first event of each referenced type; a process definition whose "
                "measurement leaves recur (repeatable steps) is evaluated against only "
                "the first occurrence of each.",
            ),
        )
        return StateDerivationResult(
            states=tuple(states),
            transitions=tuple(transitions),
            evidence_records=tuple(evidence_records),
            report=report,
        )

    def _duration_statistics(
        self, timelines: tuple[Timeline, ...], events_by_id: dict[str, Event]
    ) -> tuple[DurationStatistic, ...]:
        instance_timelines = tuple(t for t in timelines if t.view is TimelineView.PROCESS_INSTANCE)
        statistics: list[DurationStatistic] = []
        for measurement in self._duration_measurements:
            samples: list[float] = []
            for timeline in instance_timelines:
                events_by_type: dict[str, Event] = {}
                for entry in timeline.entries:
                    if entry.kind is not TimelineEntryKind.EVENT or entry.event_id is None:
                        continue
                    event = events_by_id.get(entry.event_id)
                    if event is not None and event.event_type not in events_by_type:
                        events_by_type[event.event_type] = event
                value = evaluate_duration_seconds(measurement.expression, events_by_type)
                if value is not None:
                    samples.append(value)
            if not samples:
                statistics.append(
                    DurationStatistic(
                        measurement_id=measurement.id, unit=measurement.unit, samples=0
                    )
                )
                continue
            statistics.append(
                DurationStatistic(
                    measurement_id=measurement.id,
                    unit=measurement.unit,
                    samples=len(samples),
                    minimum_seconds=int(min(samples)),
                    maximum_seconds=int(max(samples)),
                    mean_seconds=sum(samples) / len(samples),
                )
            )
        return tuple(statistics)
