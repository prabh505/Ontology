"""Generic cross-timeline composition.

`join` never names an entity type. It merges the `EVENT` entries of any timelines handed to
it by the same canonical sort key those timelines were each built with -- any one entity's
timeline is composable with any other entity's, whatever kind of thing either one is,
because the function never looks at what kind of entity produced either input.
"""

from __future__ import annotations

from causalog.core.errors import ContractViolationError
from causalog.core.provenance import ProvenanceClass, combine
from causalog.core.types import Timeline, TimelineEntry, TimelineEntryKind, TimelineView

__all__ = ["join"]


def _event_sort_key(entry: TimelineEntry) -> tuple[object, object, str]:
    """Return the canonical sort key for an `EVENT` entry; never called on a `GAP` one."""
    if entry.occurred_at is None or entry.event_id is None:
        raise ContractViolationError(
            "timeline_builder.join._event_sort_key received an entry with no occurred_at/"
            "event_id; only EVENT entries reach this function."
        )
    return (entry.occurred_at.t_earliest, entry.occurred_at.t_latest, entry.event_id)


def join(*timelines: Timeline, ontology_hash: str) -> Timeline:
    """Merge two or more timelines into one `JOINED` view, by canonical sort key.

    `GAP` entries are dropped from the merge input's sequencing key (they carry no
    timestamp) but retained in the output, appended after every `EVENT` entry in whichever
    source timeline they came from -- merging two independently gap-marked timelines does
    not attempt to interleave gaps from different sources against each other, since neither
    carries a comparable position.
    """
    if len(timelines) < 2:
        raise ContractViolationError(
            "timeline_builder.join requires at least two timelines; joining one timeline "
            "with itself is not a join."
        )
    event_entries: list[TimelineEntry] = []
    gap_entries: list[TimelineEntry] = []
    subject_entity_ids: set[str] = set()
    process_definition_ids: set[str | None] = set()
    provenances: list[ProvenanceClass] = []
    for timeline in timelines:
        subject_entity_ids.update(timeline.subject_entity_ids)
        process_definition_ids.add(timeline.process_definition_id)
        provenances.append(timeline.provenance_class)
        for entry in timeline.entries:
            (event_entries if entry.kind is TimelineEntryKind.EVENT else gap_entries).append(entry)

    event_entries.sort(key=_event_sort_key)
    merged_entries = tuple(event_entries) + tuple(gap_entries)

    process_definition_id = (
        next(iter(process_definition_ids)) if len(process_definition_ids) == 1 else None
    )
    event_ids = tuple(entry.event_id for entry in event_entries if entry.event_id)
    sorted_entity_ids = tuple(sorted(subject_entity_ids))

    return Timeline(
        timeline_id=Timeline.address(
            ontology_hash=ontology_hash,
            view=TimelineView.JOINED,
            process_definition_id=process_definition_id,
            subject_entity_ids=sorted_entity_ids,
            event_ids=event_ids,
        ),
        view=TimelineView.JOINED,
        process_definition_id=process_definition_id,
        subject_entity_ids=sorted_entity_ids,
        entries=merged_entries,
        provenance_class=combine(*provenances),
    )
