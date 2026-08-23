"""`State` -- an entity's condition immediately after an event (prd.md §20)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import TimeInterval

__all__ = ["State"]


class State(BaseModel):
    """A named condition holding of one entity over one interval.

    `state_name` is an ontology concept. A state name absent from the active ontology is
    an `OntologyMappingError`, never a silently accepted new state.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    state_id: str
    entity_id: str
    state_name: str
    held_over: TimeInterval
    provenance_class: ProvenanceClass
    evidence_record_ids: tuple[str, ...]
