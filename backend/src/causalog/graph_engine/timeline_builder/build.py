"""The Timeline Builder's public entrypoint (module 5)."""

from __future__ import annotations

from dataclasses import dataclass

from causalog.core.ontology_view import ProcessDefinitionView
from causalog.core.provenance import ProvenanceClass, combine
from causalog.core.run import OutputEnvelope
from causalog.core.types import Entity, Event, Timeline, TimelineView
from causalog.graph_engine.timeline_builder.grouping import (
    group_by_entity,
    group_by_process_instance,
)
from causalog.graph_engine.timeline_builder.quality import (
    ProcessDefinitionConformance,
    SequenceViolation,
    TimelineQualityReport,
)
from causalog.graph_engine.timeline_builder.sequencing import (
    sequence_events,
    sequence_violations_for,
    sort_events,
    step_coverage_for,
)

__all__ = ["TimelineBuildResult", "TimelineBuilder"]


@dataclass(frozen=True)
class TimelineBuildResult:
    """One run's `Timeline` output and its quality report."""

    timelines: tuple[Timeline, ...]
    report: TimelineQualityReport


class TimelineBuilder:
    """Group events into per-process sequenced timelines (module 5).

    Reads `process_definitions` (a `causalog.core.ontology_view` view of the ontology
    pack, adapted by `causalog.extraction.ontology_adapters` -- this package may never
    import `ontology_runtime` directly, ADR-0002) for grouping keys and canonical
    sequences; never hardcodes an entity type or event type. Every entity view and every
    process-instance view is built from the same `events`/`entities` input -- this module
    never emits an edge of any kind, only a sequenced arrangement of what was already
    observed.
    """

    def __init__(
        self, process_definitions: tuple[ProcessDefinitionView, ...], ontology_hash: str
    ) -> None:
        """Store the pack's process definitions, already adapted to plain views."""
        self._process_definitions = process_definitions
        self._ontology_hash = ontology_hash

    def build(
        self,
        events: tuple[Event, ...],
        entities: tuple[Entity, ...],
        envelope: OutputEnvelope,
    ) -> TimelineBuildResult:
        """Group, sequence, and gap-check `events` into `Timeline` values plus a report."""
        producible_types = frozenset(event.event_type for event in events)
        timelines: list[Timeline] = []
        per_definition: dict[str, dict[str, float | int]] = {}
        conformance_scores: dict[str, list[float]] = {}
        violations: list[SequenceViolation] = []
        uncertain_sequence = 0

        instance_groups = group_by_process_instance(events, entities, self._process_definitions)
        for group in instance_groups:
            definition = group.process_definition
            stats = per_definition.setdefault(
                definition.id,
                {
                    "instances": 0,
                    "gap_witnessable": 0,
                    "gap_unwitnessable": 0,
                    "sequence_violations": 0,
                    "unterminated_instances": 0,
                },
            )
            stats["instances"] += 1

            sequenced_events = sort_events(group.events)
            event_entries = sequence_events(group.events)
            coverage = step_coverage_for(
                definition, event_entries, sequenced_events, producible_types
            )
            stats["gap_witnessable"] += coverage.gap_witnessable
            stats["gap_unwitnessable"] += coverage.gap_unwitnessable
            if coverage.unterminated:
                stats["unterminated_instances"] += 1

            found_violations = sequence_violations_for(
                definition, group.anchor_entity_id, sequenced_events
            )
            stats["sequence_violations"] += len(found_violations)
            violations.extend(found_violations)

            required = len(
                [
                    step
                    for step in definition.canonical_sequence
                    if step not in definition.optional_steps
                ]
            )
            if required:
                matched = required - (coverage.gap_witnessable + coverage.gap_unwitnessable)
                conformance_scores.setdefault(definition.id, []).append(matched / required)

            has_uncertain = any(
                entry.sequence_provenance is ProvenanceClass.ASSUMED for entry in event_entries
            )
            if has_uncertain:
                uncertain_sequence += 1

            event_ids = tuple(entry.event_id for entry in event_entries if entry.event_id)
            timelines.append(
                Timeline(
                    timeline_id=Timeline.address(
                        ontology_hash=self._ontology_hash,
                        view=TimelineView.PROCESS_INSTANCE,
                        process_definition_id=definition.id,
                        subject_entity_ids=(group.anchor_entity_id,),
                        event_ids=event_ids,
                    ),
                    view=TimelineView.PROCESS_INSTANCE,
                    process_definition_id=definition.id,
                    subject_entity_ids=(group.anchor_entity_id,),
                    entries=coverage.entries,
                    provenance_class=combine(
                        *(
                            entry.sequence_provenance
                            for entry in event_entries
                            if entry.sequence_provenance is not None
                        )
                    )
                    if event_entries
                    else ProvenanceClass.ASSUMED,
                )
            )

        entity_view_count = 0
        for entity_id, entity_events in group_by_entity(events, entities):
            if not entity_events:
                continue
            event_entries = sequence_events(entity_events)
            has_uncertain = any(
                entry.sequence_provenance is ProvenanceClass.ASSUMED for entry in event_entries
            )
            if has_uncertain:
                uncertain_sequence += 1
            event_ids = tuple(entry.event_id for entry in event_entries if entry.event_id)
            timelines.append(
                Timeline(
                    timeline_id=Timeline.address(
                        ontology_hash=self._ontology_hash,
                        view=TimelineView.ENTITY,
                        process_definition_id=None,
                        subject_entity_ids=(entity_id,),
                        event_ids=event_ids,
                    ),
                    view=TimelineView.ENTITY,
                    process_definition_id=None,
                    subject_entity_ids=(entity_id,),
                    entries=event_entries,
                    provenance_class=combine(
                        *(
                            entry.sequence_provenance
                            for entry in event_entries
                            if entry.sequence_provenance is not None
                        )
                    ),
                )
            )
            entity_view_count += 1

        per_definition_reports = tuple(
            ProcessDefinitionConformance(
                process_definition_id=definition_id,
                instances=int(stats["instances"]),
                required_steps=len(
                    [
                        step
                        for definition in self._process_definitions
                        if definition.id == definition_id
                        for step in definition.canonical_sequence
                        if step not in definition.optional_steps
                    ]
                ),
                gap_witnessable=int(stats["gap_witnessable"]),
                gap_unwitnessable=int(stats["gap_unwitnessable"]),
                sequence_violations=int(stats["sequence_violations"]),
                unterminated_instances=int(stats["unterminated_instances"]),
                conformance_scores=tuple(conformance_scores.get(definition_id, ())),
            )
            for definition_id, stats in per_definition.items()
        )

        report = TimelineQualityReport(
            envelope=envelope,
            events_read=len(events),
            timelines_built=len(timelines),
            entity_view_timelines=entity_view_count,
            process_instance_timelines=len(instance_groups),
            uncertain_sequence_timelines=uncertain_sequence,
            per_process_definition=per_definition_reports,
            violations=tuple(violations),
            not_checked=(
                "Sequence-violation and impossible-sequence detection uses an "
                "approximate step index (canonical sequence, then unmatched variant "
                "steps appended) rather than a full variant-DAG match; a departure that "
                "a specific declared variant would explain may still be reported.",
                "Cross-entity JOINED timelines are not built automatically here -- "
                "join(...) composes any two already-built timelines on request.",
            ),
        )
        return TimelineBuildResult(timelines=tuple(timelines), report=report)
