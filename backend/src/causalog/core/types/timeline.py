"""`Timeline` -- a sequenced view of events belonging to one or more entities.

Adjacency on a timeline is SEQUENCING, never causation (`GLOSSARY.md` §2.1,
`docs/architecture.md` §Module 5). A timeline never emits an edge of any kind; the only
claim it makes is "these events sequence this way, and here is how sure we are of that
sequence."

Every `TimelineEntry` in `Timeline.entries` is either an observed `EVENT` or an explicit
`GAP` marker for a process step the ontology expected and no record supplied -- a gap is
reported, never bridged, never given a fabricated timestamp (ADR-0040, R-02).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from causalog.core.errors import ContractViolationError
from causalog.core.identifiers import (
    IdentifierPrefix,
    canonical_payload,
    canonical_sequence,
    canonical_text,
    digest,
)
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import TimeInterval

__all__ = ["Timeline", "TimelineEntry", "TimelineEntryKind", "TimelineView"]


class TimelineView(str, Enum):
    """The three ways the same events may be grouped and sequenced.

    None is more authoritative than another -- they are different questions asked of the
    same observed events, and a Timeline Builder consumer picks the view its question
    needs.
    """

    PROCESS_INSTANCE = "PROCESS_INSTANCE"
    """One process definition's anchor entity, sequenced against its declared steps."""

    ENTITY = "ENTITY"
    """One entity's full observed participation, with no process definition involved."""

    JOINED = "JOINED"
    """The merge of two or more already-built timelines by their shared sort key."""


class TimelineEntryKind(str, Enum):
    """What one position on a timeline holds."""

    EVENT = "EVENT"
    GAP = "GAP"


class TimelineEntry(BaseModel):
    """One position on a `Timeline`: an observed event, or an explicit gap.

    Exactly one of the two field groups is populated, selected by `kind`.

    `sequence_provenance` names how the *position of this entry relative to the previous
    one* was decided -- not how the event itself was observed. `OBSERVED` means
    `causalog.core.temporal.verdict` returned `CERTAIN` for the pair; `ASSUMED` means the
    verdict was `UNDETERMINED` (the intervals tied or overlapped) and the position was
    settled by the documented, stable tie-break rule rather than by any evidence of true
    sequence (see `graph_engine/timeline_builder/sequencing.py` and the ADR it cites). A
    `GAP` entry carries no sequencing claim of its own; it is positioned at its expected
    index in the process definition's declared sequence.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: TimelineEntryKind
    event_id: str | None = None
    occurred_at: TimeInterval | None = None
    expected_event_type: str | None = None
    process_definition_id: str | None = None
    step_witnessable: bool | None = None
    sequence_provenance: ProvenanceClass | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> TimelineEntry:
        """Enforce that exactly one field group is populated, per `kind`."""
        if self.kind is TimelineEntryKind.EVENT:
            if self.event_id is None or self.occurred_at is None:
                raise ContractViolationError(
                    "TimelineEntry.kind is EVENT but event_id/occurred_at is missing; "
                    "an event entry must carry both."
                )
            if self.expected_event_type is not None or self.step_witnessable is not None:
                raise ContractViolationError(
                    "TimelineEntry.kind is EVENT but a GAP-only field is populated; the "
                    "two field groups are mutually exclusive."
                )
        else:
            if self.expected_event_type is None or self.process_definition_id is None:
                raise ContractViolationError(
                    "TimelineEntry.kind is GAP but expected_event_type/"
                    "process_definition_id is missing; a gap entry must carry both."
                )
            if self.step_witnessable is None:
                raise ContractViolationError(
                    "TimelineEntry.kind is GAP but step_witnessable is unset; a gap must "
                    "say whether any record could ever have witnessed the missing step."
                )
            if self.event_id is not None or self.occurred_at is not None:
                raise ContractViolationError(
                    "TimelineEntry.kind is GAP but an EVENT-only field is populated; the "
                    "two field groups are mutually exclusive."
                )
            if self.sequence_provenance is not None:
                raise ContractViolationError(
                    "TimelineEntry.kind is GAP but sequence_provenance is set; a gap "
                    "carries no sequencing claim of its own."
                )
        return self


class Timeline(BaseModel):
    """A sequenced view over one or more entities' events (`GLOSSARY.md` §2.1).

    `entries` is already in canonical sequence at construction -- this type checks the sequence,
    it does not decide it. Deciding sequence (including the tie-break rule) is
    `graph_engine.timeline_builder`'s responsibility.

    Invariants:
      * `entries` is non-empty.
      * `EVENT` entries are strictly sequenced by `(occurred_at.t_earliest,
        occurred_at.t_latest, event_id)` -- the documented canonical key
        (`CONVENTIONS.md` §11, `docs/architecture.md` §Module 5). `GAP` entries may sit
        between any two `EVENT` entries and do not participate in this check.
      * `subject_entity_ids` is non-empty and sorted.
      * `process_definition_id` is set for `PROCESS_INSTANCE` and may be set for `JOINED`;
        it is always `None` for `ENTITY`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    timeline_id: str
    view: TimelineView
    process_definition_id: str | None
    subject_entity_ids: tuple[str, ...]
    entries: tuple[TimelineEntry, ...]
    provenance_class: ProvenanceClass

    @model_validator(mode="after")
    def _check_invariants(self) -> Timeline:
        """Enforce the documented invariants at construction."""
        if not self.entries:
            raise ContractViolationError(
                "Timeline.entries is empty; a timeline with no positions is not a "
                "timeline (a single-event timeline is legal, an empty one is not)."
            )
        if not self.subject_entity_ids:
            raise ContractViolationError(
                "Timeline.subject_entity_ids is empty; every timeline names at least one "
                "subject entity."
            )
        if list(self.subject_entity_ids) != sorted(self.subject_entity_ids):
            raise ContractViolationError(
                "Timeline.subject_entity_ids must be sorted (CONVENTIONS.md §11)."
            )
        if self.view is TimelineView.ENTITY and self.process_definition_id is not None:
            raise ContractViolationError(
                "Timeline.view is ENTITY but process_definition_id is set; an entity "
                "view is not anchored to any one process definition."
            )
        if self.view is TimelineView.PROCESS_INSTANCE and self.process_definition_id is None:
            raise ContractViolationError(
                "Timeline.view is PROCESS_INSTANCE but process_definition_id is unset; a "
                "process-instance view must name the definition it was grouped against."
            )
        previous_key: tuple[object, object, str] | None = None
        for entry in self.entries:
            if entry.kind is not TimelineEntryKind.EVENT:
                continue
            if entry.occurred_at is None or entry.event_id is None:
                raise ContractViolationError(
                    "Timeline.entries holds an EVENT entry with no occurred_at/event_id; "
                    "TimelineEntry's own invariant should already have refused this."
                )
            key = (entry.occurred_at.t_earliest, entry.occurred_at.t_latest, entry.event_id)
            if previous_key is not None and key <= previous_key:
                raise ContractViolationError(
                    "Timeline.entries is not in canonical sequence: event entries must be "
                    "strictly increasing by (t_earliest, t_latest, event_id) "
                    "(CONVENTIONS.md §11). Timeline construction checks sequence; it never "
                    "corrects it."
                )
            previous_key = key
        return self

    @classmethod
    def address(
        cls,
        ontology_hash: str,
        view: TimelineView,
        process_definition_id: str | None,
        subject_entity_ids: tuple[str, ...],
        event_ids: tuple[str, ...],
    ) -> str:
        """Return the content-addressed identifier for a timeline (`CONVENTIONS.md` §9).

        Payload recipe: `ontology_hash | view | process_definition_id |
        subject_entity_ids(sorted) | event_ids(sorted)`. Gap markers are excluded from the
        payload: they are derived from the process definition and the placed events, not
        an independent fact, so their presence never changes the timeline's identity.
        """
        return digest(
            IdentifierPrefix.TIMELINE,
            canonical_payload(
                canonical_text(ontology_hash),
                canonical_text(view.value),
                canonical_text(process_definition_id or ""),
                canonical_sequence(sorted(subject_entity_ids)),
                canonical_sequence(sorted(event_ids)),
            ),
        )
