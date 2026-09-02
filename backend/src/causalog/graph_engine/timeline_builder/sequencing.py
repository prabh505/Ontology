"""Canonical sequencing, the tie-break rule, and process-definition-relative detection.

**The tie-break rule (recorded in an ADR, not invented here in prose alone).** Events are
sorted by `(occurred_at.t_earliest, occurred_at.t_latest, event_id)`
(`docs/architecture.md` §Module 5, `CONVENTIONS.md` §11). For each adjacent pair, this
module asks `causalog.core.temporal.verdict` whether the *data itself* separates them:

  * `CERTAIN` -- the position reflects a real, data-supported sequence. `sequence_provenance`
    is `OBSERVED`.
  * `UNDETERMINED` (identical or overlapping intervals -- the day-granularity tie case
    named in ADR-0007) -- the position is decided by `event_id` alone, purely so the
    output is deterministic. `sequence_provenance` is `ASSUMED`: **this is not a claim
    about real-world sequence**, and every consumer of a `Timeline` must treat an `ASSUMED`
    adjacency as unverified.

`VIOLATION` cannot occur between two entries already sorted by `t_earliest` unless the
process definition itself is contradicted by the data; if the verdict function ever
returns it here, that pair is folded into the sequence-violation findings rather than
silently accepted.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from causalog.core.ontology_view import ProcessDefinitionView
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import TemporalVerdict, verdict
from causalog.core.types import Event, TimelineEntry, TimelineEntryKind
from causalog.graph_engine.timeline_builder.quality import (
    SequenceViolation,
    SequenceViolationKind,
)

__all__ = [
    "SequencedInstance",
    "sequence_events",
    "sequence_violations_for",
    "sort_events",
    "step_coverage_for",
]


def sort_events(events: tuple[Event, ...]) -> tuple[Event, ...]:
    """Return `events` in the canonical key `(t_earliest, t_latest, event_id)`."""
    return tuple(sorted(events, key=lambda event: (*event.occurred_at.sort_key(), event.event_id)))


def sequence_events(events: tuple[Event, ...]) -> tuple[TimelineEntry, ...]:
    """Return `events` as canonically sequenced `EVENT` entries, tie-break rule applied.

    The observed sequence is never altered by anything downstream of this function --
    detection functions in this module read the result, they do not feed back into it.
    """
    sequenced = sort_events(events)
    entries: list[TimelineEntry] = []
    previous: Event | None = None
    for event in sequenced:
        if previous is None:
            provenance = ProvenanceClass.OBSERVED
        else:
            pair_verdict = verdict(previous.occurred_at, event.occurred_at)
            provenance = (
                ProvenanceClass.OBSERVED
                if pair_verdict is TemporalVerdict.CERTAIN
                else ProvenanceClass.ASSUMED
            )
        entries.append(
            TimelineEntry(
                kind=TimelineEntryKind.EVENT,
                event_id=event.event_id,
                occurred_at=event.occurred_at,
                sequence_provenance=provenance,
            )
        )
        previous = event
    return tuple(entries)


def _step_index_map(process_definition: ProcessDefinitionView) -> dict[str, int]:
    """Return an approximate canonical-sequence index for every step this definition names.

    `canonical_sequence` is indexed first; any variant step absent from it is appended
    after, in the sequence variants are declared. This is an approximation used only for
    sequencing diagnostics -- it never decides what a `Timeline`'s entries contain.
    """
    index: dict[str, int] = {}
    for position, step in enumerate(process_definition.canonical_sequence):
        index.setdefault(step, position)
    cursor = len(process_definition.canonical_sequence)
    for variant in process_definition.variants:
        for step in variant.sequence:
            if step not in index:
                index[step] = cursor
                cursor += 1
    return index


def sequence_violations_for(
    process_definition: ProcessDefinitionView,
    anchor_entity_id: str,
    sequenced_events: tuple[Event, ...],
) -> tuple[SequenceViolation, ...]:
    """Return every adjacent pair that departs from the declared canonical sequence.

    Never corrects the sequence; only reports it. A pair inside `repeatable_steps` is exempt
    from the "no going backward" check -- a repeatable step legitimately recurs.
    """
    index = _step_index_map(process_definition)
    repeatable = set(process_definition.repeatable_steps)
    violations: list[SequenceViolation] = []
    for earlier, later in pairwise(sequenced_events):
        if earlier.event_type in repeatable or later.event_type in repeatable:
            continue
        earlier_index = index.get(earlier.event_type)
        later_index = index.get(later.event_type)
        if earlier_index is None or later_index is None:
            continue
        if later_index >= earlier_index:
            continue
        kind = (
            SequenceViolationKind.OUT_OF_SEQUENCE
            if later.event_type in process_definition.canonical_sequence
            and earlier.event_type in process_definition.canonical_sequence
            else SequenceViolationKind.IMPOSSIBLE
        )
        violations.append(
            SequenceViolation(
                kind=kind,
                process_definition_id=process_definition.id,
                anchor_entity_id=anchor_entity_id,
                earlier_event_id=earlier.event_id,
                earlier_event_type=earlier.event_type,
                later_event_id=later.event_id,
                later_event_type=later.event_type,
            )
        )
    return tuple(violations)


@dataclass(frozen=True)
class SequencedInstance:
    """The result of sequencing and gap-checking one process instance."""

    entries: tuple[TimelineEntry, ...]
    gap_witnessable: int
    gap_unwitnessable: int
    unterminated: bool


def step_coverage_for(
    process_definition: ProcessDefinitionView,
    event_entries: tuple[TimelineEntry, ...],
    sequenced_events: tuple[Event, ...],
    producible_types: frozenset[str],
) -> SequencedInstance:
    """Insert `GAP` markers for unwitnessed required steps and flag non-termination.

    A gap is never given a fabricated timestamp (ADR-0040): it is positioned at its
    expected canonical index, interleaved with the observed `EVENT` entries, never
    reordering them.
    """
    matched_types = {event.event_type for event in sequenced_events}
    index = _step_index_map(process_definition)
    optional = set(process_definition.optional_steps)
    required_steps = [
        step for step in process_definition.canonical_sequence if step not in optional
    ]

    gap_entries: list[tuple[int, TimelineEntry]] = []
    witnessable = 0
    unwitnessable = 0
    for step in required_steps:
        if step in matched_types:
            continue
        is_witnessable = step in producible_types
        if is_witnessable:
            witnessable += 1
        else:
            unwitnessable += 1
        gap_entries.append(
            (
                index.get(step, len(process_definition.canonical_sequence)),
                TimelineEntry(
                    kind=TimelineEntryKind.GAP,
                    expected_event_type=step,
                    process_definition_id=process_definition.id,
                    step_witnessable=is_witnessable,
                ),
            )
        )

    merged: list[TimelineEntry] = list(event_entries)
    for gap_index, gap_entry in gap_entries:
        insert_at = len(merged)
        for position, entry in enumerate(merged):
            if entry.kind is TimelineEntryKind.EVENT:
                entry_type_index = index.get(_event_type_of(entry, sequenced_events), len(index))
                if entry_type_index > gap_index:
                    insert_at = position
                    break
        merged.insert(insert_at, gap_entry)

    unterminated = bool(required_steps) and required_steps[-1] not in matched_types

    return SequencedInstance(
        entries=tuple(merged),
        gap_witnessable=witnessable,
        gap_unwitnessable=unwitnessable,
        unterminated=unterminated,
    )


def _event_type_of(entry: TimelineEntry, sequenced_events: tuple[Event, ...]) -> str:
    """Look up the event type behind an `EVENT` entry, for gap-placement only."""
    for event in sequenced_events:
        if event.event_id == entry.event_id:
            return event.event_type
    return ""
