"""`Entity` -- something that exists (prd.md §20)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from causalog.core.provenance import ProvenanceClass

__all__ = ["Entity"]


class Entity(BaseModel):
    """A participant in events, identified by a content-addressed identifier.

    `entity_type` is an ontology concept name, carried as an opaque string. No reasoning
    package may branch on its value -- doing so reintroduces the domain into the core
    (LAW-DOMAIN, ADR-0002).

    Invariants:
      * `entity_id == digest(ENTITY, ontology_hash | entity_type | natural_key)`.
      * `attributes` keys are ontology attribute names, sorted.
      * Immutable. A correction is a new entity version, never a mutation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_id: str
    entity_type: str
    natural_key: str
    attributes: tuple[tuple[str, str], ...]
    provenance_class: ProvenanceClass
    evidence_record_ids: tuple[str, ...]
