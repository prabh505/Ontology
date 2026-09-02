"""`Entity` -- something that exists (prd.md §20)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from causalog.core.identifiers import (
    IdentifierPrefix,
    canonical_payload,
    canonical_text,
    digest,
)
from causalog.core.provenance import ProvenanceClass

__all__ = ["Entity", "Lifecycle"]


class Lifecycle(BaseModel):
    """The declared state space an entity type may move through.

    Ontology-supplied configuration, not an observation: the ontology declares which state
    names exist and which moves between them are legal, and the engine checks observations
    against that declaration rather than learning it. Provenance is therefore always
    `ASSUMED` (ADR-0005) -- a lifecycle nobody declared is not a lifecycle the engine
    discovered, it is a defect in the ontology.

    Invariants:
      * `state_names` is non-empty, sorted, and free of repeats.
      * every member of `legal_transitions` names two states drawn from `state_names`; a
        transition to an undeclared state is an `OntologyMappingError` at load time, never
        a silently accepted new state.
      * `legal_transitions` is sorted, so the lifecycle serializes exactly one way.
      * `provenance_class` is `ASSUMED`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    state_names: tuple[str, ...]
    legal_transitions: tuple[tuple[str, str], ...]
    provenance_class: ProvenanceClass

    @model_validator(mode="after")
    def _check_invariants(self) -> Lifecycle:
        """Enforce the documented invariants at construction."""
        if not self.state_names:
            raise ValueError(
                "Lifecycle.state_names is empty; an entity type with no declared states "
                "has no lifecycle to check observations against."
            )
        if list(self.state_names) != sorted(self.state_names):
            raise ValueError("Lifecycle.state_names must be sorted (CONVENTIONS.md §11).")
        if len(set(self.state_names)) != len(self.state_names):
            raise ValueError("Lifecycle.state_names contains a repeated name.")
        if list(self.legal_transitions) != sorted(self.legal_transitions):
            raise ValueError("Lifecycle.legal_transitions must be sorted (CONVENTIONS.md §11).")
        declared = set(self.state_names)
        for from_state, to_state in self.legal_transitions:
            undeclared = {from_state, to_state} - declared
            if undeclared:
                raise ValueError(
                    f"Lifecycle.legal_transitions names undeclared state(s) "
                    f"{sorted(undeclared)}; every endpoint must appear in state_names."
                )
        if self.provenance_class is not ProvenanceClass.ASSUMED:
            raise ValueError(
                "Lifecycle.provenance_class must be ASSUMED; a lifecycle is declared "
                "configuration, never an observation (ADR-0005)."
            )
        return self


class Entity(BaseModel):
    """A participant in events, identified by a content-addressed identifier.

    `entity_type` is an ontology concept name, carried as an opaque string. No reasoning
    package may branch on its value -- doing so reintroduces the domain into the core
    (LAW-DOMAIN, ADR-0002).

    There is deliberately **no `current_state` field.** The condition an entity is in is a
    function of the `State` records that hold at a chosen instant, and it is computed by
    `causalog.core.derivation.current_state`. Storing it would force one of two defects:
    either the entity mutates as history advances, which contradicts LAW-PROVENANCE's
    guarantee that an observed fact is never overwritten, or its content-addressed
    identifier changes every time the world moves, which makes every reference to it stale.
    A derived view has neither problem and is the same information.

    Invariants:
      * `entity_id == digest(ENTITY, ontology_hash | entity_type | natural_key)`.
        `lifecycle` and `attributes` are deliberately absent from that payload: the
        identity of an entity is what it *is*, not what has been recorded about it, so
        enriching an entity's attributes must not rename it.
      * `attributes` keys are ontology attribute names, sorted.
      * Immutable. A correction is a new entity version, never a mutation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_id: str
    entity_type: str
    natural_key: str
    attributes: tuple[tuple[str, str], ...]
    lifecycle: Lifecycle
    provenance_class: ProvenanceClass
    evidence_record_ids: tuple[str, ...]

    @classmethod
    def address(cls, ontology_hash: str, entity_type: str, natural_key: str) -> str:
        """Return the content-addressed identifier for an entity (`CONVENTIONS.md` §9).

        Payload recipe: `ontology_hash | entity_type | natural_key`. The ontology hash
        participates because the same natural key means a different thing under a
        different ontology, and two runs that disagree about the vocabulary must not
        silently share identifiers.
        """
        return digest(
            IdentifierPrefix.ENTITY,
            canonical_payload(
                canonical_text(ontology_hash),
                canonical_text(entity_type),
                canonical_text(natural_key),
            ),
        )
