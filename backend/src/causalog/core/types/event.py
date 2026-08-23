"""`Event` -- something that happened. The atomic computational unit (ADR-0004)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import TimeInterval

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
      * `extraction_confidence` is how sure we are that this event was correctly derived
        from its evidence. It is NOT the confidence of a causal claim, and it does not
        weaken `provenance_class` (OQ-005).
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
    extraction_confidence: float
    is_actionable: bool
    evidence_record_ids: tuple[str, ...]
