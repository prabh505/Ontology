"""`Event` -- something that happened. The atomic computational unit (ADR-0004)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from causalog.core.errors import ContractViolationError, LawViolationError
from causalog.core.identifiers import (
    IdentifierPrefix,
    canonical_pairs,
    canonical_payload,
    canonical_sequence,
    canonical_text,
    digest,
)
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import TimeInterval, canonical_interval
from causalog.core.types.confidence import ConfidenceVector

__all__ = ["Event"]


class Event(BaseModel):
    """The unit every reasoning package computes over.

    A raw record is *evidence*; it emits zero or more events, each with its own interval,
    type, participants, and provenance (ADR-0004). Downstream of the Event Generator no
    package may accept, return, or hold a row, a DataFrame, or a column (LAW-EVENT).

    Field notes:
      * `trigger` is the proximate mechanism recorded ON the event -- intrinsic and
        `OBSERVED`. It is NOT a cause; a cause is an inferred edge BETWEEN events
        (ADR-0020, `GLOSSARY.md` §2.1). **No module may read this field to create, filter,
        or score a candidate edge**: doing so turns an OBSERVED field into a causal claim
        that skipped both the LAW-TIME and LAW-EVIDENCE gates.
      * `confidence` is how sure we are that this event was correctly derived from its
        evidence. It is NOT the confidence of a causal claim, and it does not weaken
        `provenance_class` (ADR-0009). It is a full `ConfidenceVector` rather than a
        scalar: LAW-EVIDENCE holds that a bare float is a defect, and it holds here for
        the same reason it holds on an edge -- a number nobody can decompose is a number
        nobody can check.
      * `source_record_ref` is the evidence record this event was derived from, and is
        always a member of `evidence_record_ids`. It names the *originating* record where
        the others are corroborating ones, which is what an explanation needs to cite
        first.
      * `is_actionable` is ontology-declared configuration, stamped here at generation time
        with provenance `ASSUMED` (ADR-0008). It exists on the event, rather than being
        looked up where it is used, because the module that needs it (Root Cause Analyzer,
        L6) may not read the ontology -- forbidden edge F3. A mis-declared flag silently
        changes the headline ranking and nothing can detect it; that cost is accepted and
        recorded in ADR-0008.
      * `changed_attributes` is sorted by attribute name.

    Invariants:
      * Immutable. A correction emits a new event; it never mutates this one.
      * `evidence_record_ids` is non-empty for `OBSERVED` events.
      * An event whose `occurred_at.precision` is `UNKNOWN` may exist on a timeline but
        may never participate in an `INFERRED` causal edge (`CONVENTIONS.md` §10).
      * `source_record_ref` appears in `evidence_record_ids`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    event_type: str
    occurred_at: TimeInterval
    trigger: str | None
    source_entity_ids: tuple[str, ...]
    target_entity_ids: tuple[str, ...]
    changed_attributes: tuple[tuple[str, str], ...]
    metadata: tuple[tuple[str, str], ...]
    provenance_class: ProvenanceClass
    confidence: ConfidenceVector
    is_actionable: bool
    source_record_ref: str
    evidence_record_ids: tuple[str, ...]

    @model_validator(mode="after")
    def _check_invariants(self) -> Event:
        """Enforce the documented invariants at construction."""
        if self.source_record_ref not in self.evidence_record_ids:
            raise ContractViolationError(
                "Event.source_record_ref must appear in evidence_record_ids; the "
                "originating record is one of the event's citations, not a separate "
                "claim (ADR-0004)."
            )
        if self.provenance_class is ProvenanceClass.OBSERVED and not self.evidence_record_ids:
            raise LawViolationError(
                "Event with OBSERVED provenance carries no evidence_record_ids; an "
                "observation with no citation was not observed (LAW-EVIDENCE)."
            )
        return self

    @classmethod
    def address(
        cls,
        ontology_hash: str,
        event_type: str,
        entity_ids: tuple[str, ...],
        occurred_at: TimeInterval,
        changed_attributes: tuple[tuple[str, str], ...],
        evidence_record_ids: tuple[str, ...],
    ) -> str:
        """Return the content-addressed identifier for an event (`CONVENTIONS.md` §9).

        Payload recipe: `ontology_hash | event_type | entity_ids(sorted) |
        timestamp_interval | changed_attributes(sorted) | evidence_record_ids(sorted)`.

        The collections are sorted here rather than trusted from the caller, because the
        recipe names sorting as part of the address: two callers that assembled the same
        participants in a different sequence must reach the same identifier, or a rerun
        that iterates differently mints a duplicate event.

        `trigger` is absent from the payload. It is an `OBSERVED` mechanism recorded on the
        event (ADR-0020), and two events identical in every other respect are the same
        event whether or not the source labelled the mechanism.
        """
        return digest(
            IdentifierPrefix.EVENT,
            canonical_payload(
                canonical_text(ontology_hash),
                canonical_text(event_type),
                canonical_sequence(sorted(entity_ids)),
                canonical_interval(occurred_at),
                canonical_pairs(changed_attributes),
                canonical_sequence(sorted(evidence_record_ids)),
            ),
        )
