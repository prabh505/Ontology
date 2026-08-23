"""`Relationship` -- structural association between entities (prd.md §22)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import TimeInterval

__all__ = ["Relationship"]


class Relationship(BaseModel):
    """A non-causal, structural edge between two entities.

    `relationship_type` is an ontology concept drawn from the structural relationship
    vocabulary (prd.md §47: BELONGS_TO, LOCATED_AT, PART_OF, ...). `CAUSES` is NOT a
    relationship type and may never appear here -- causal edges are a separate artifact
    produced only by the causal engine.

    `valid_over` bounds the interval across which the association holds, because
    structural facts are themselves temporal.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    relationship_id: str
    relationship_type: str
    source_entity_id: str
    target_entity_id: str
    valid_over: TimeInterval
    provenance_class: ProvenanceClass
    evidence_record_ids: tuple[str, ...]
