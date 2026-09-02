"""`State` -- an entity's condition immediately after an event (prd.md §20)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from causalog.core.identifiers import (
    IdentifierPrefix,
    canonical_payload,
    canonical_text,
    digest,
)
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import TimeInterval, canonical_interval

__all__ = ["State"]


class State(BaseModel):
    """A named condition holding of one entity over one interval.

    `state_name` is an ontology concept. A state name absent from the active ontology is
    an `OntologyMappingError`, never a silently accepted new state.

    `held_over` IS the validity interval: `held_over.t_earliest` is the moment the state
    began to hold and `held_over.t_latest` the moment it stopped. There are deliberately
    not also `valid_from` and `valid_to` fields -- one interval, carrying its own precision
    and provenance, says everything two bare instants would and cannot disagree with
    itself. A state still holding at the end of the dataset has `t_latest` at
    `UNKNOWN_LATEST`, which is the honest statement that no end was recorded.

    `derived_from_event_id` names the event whose occurrence produced this state. Every
    state comes from an event (prd.md §20: a state is "an entity's condition immediately
    after an event"); a state with no such event was not derived, it was assumed, and it
    should say so through its provenance class rather than by omitting the link.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    state_id: str
    entity_id: str
    state_name: str
    held_over: TimeInterval
    derived_from_event_id: str
    provenance_class: ProvenanceClass
    evidence_record_ids: tuple[str, ...]

    @classmethod
    def address(cls, entity_id: str, state_name: str, held_over: TimeInterval) -> str:
        """Return the content-addressed identifier for a state (`CONVENTIONS.md` §9).

        Payload recipe: `entity_id | state_name | timestamp_interval`.
        """
        return digest(
            IdentifierPrefix.STATE,
            canonical_payload(
                canonical_text(entity_id),
                canonical_text(state_name),
                canonical_interval(held_over),
            ),
        )
