"""Evidence: the citation, and the re-verifiable justification built on top of it.

LAW-EVIDENCE. Two distinct things live here and must not be conflated:

  * `EvidenceRecord` is a **citation** -- an opaque pointer at one record in one versioned
    dataset. It answers "where did this come from".
  * `EvidenceItem` is a **justification** -- one named reason an assertion is believed,
    carrying the exact rule or query that produced it. It answers "why should anyone
    accept this", and it answers it in a form the reader can re-execute.

An evidence record is the citation an inference points at; it is never the thing an
inference computes over (LAW-EVENT).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from causalog.core.errors import ContractViolationError, LawViolationError
from causalog.core.identifiers import (
    IdentifierPrefix,
    canonical_payload,
    canonical_text,
    digest,
)
from causalog.core.provenance import ProvenanceClass

__all__ = ["EvidenceItem", "EvidenceKind", "EvidenceRecord"]


class EvidenceKind(str, Enum):
    """The closed set of justification sources (prd.md §27).

    Closed rather than free text so that a consumer can reason about *what kind* of
    support an assertion rests on without parsing prose. A justification that fits none of
    these is not a weak justification; it is an unmodelled one, and it needs an ADR.
    """

    RULE = "RULE"
    """An explicit rule in the active rule pack fired."""

    TEMPORAL_PROXIMITY = "TEMPORAL_PROXIMITY"
    """The two events sit close together in time, within a stated window."""

    SHARED_ENTITY = "SHARED_ENTITY"
    """The two events name a participant in common."""

    SHARED_IDENTIFIER = "SHARED_IDENTIFIER"
    """The two events carry an identifier in common that is not itself a participant."""

    HISTORICAL_FREQUENCY = "HISTORICAL_FREQUENCY"
    """The pattern recurred across the dataset at a stated rate."""

    ONTOLOGY = "ONTOLOGY"
    """The active ontology declares the relationship admissible."""

    STATISTICAL_ASSOCIATION = "STATISTICAL_ASSOCIATION"
    """A deterministic association measure crossed a stated threshold."""


class EvidenceRecord(BaseModel):
    """A citation into a versioned dataset.

    `source_locator` is an opaque, dataset-version-scoped pointer (for example a file
    identifier plus a record offset). The raw record itself is never carried here and
    never appears in a log or an error message (`CONVENTIONS.md` §7, §8).

    `source_timezone` records the timezone the source expressed, or its absence. It lives
    here and never on an `Event` (`CONVENTIONS.md` §10).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_record_id: str
    dataset_version: str
    source_locator: str
    source_timezone: str | None

    @classmethod
    def address(cls, dataset_version: str, source_locator: str) -> str:
        """Return the content-addressed identifier for a citation (`CONVENTIONS.md` §9).

        Payload recipe: `dataset_version | source_locator`. The dataset version is part of
        the address because the same locator points at different bytes in a different
        dataset version, and a citation that silently followed the data would make an old
        explanation cite a record it never saw.
        """
        return digest(
            IdentifierPrefix.EVIDENCE_RECORD,
            canonical_payload(canonical_text(dataset_version), canonical_text(source_locator)),
        )


class EvidenceItem(BaseModel):
    """One independently re-verifiable reason an assertion is believed.

    The load-bearing field is `verification`: the exact rule identifier or query text that
    produced this item. An item a reader cannot re-execute is a defect, not a weak item --
    "the model found this convincing" is not evidence, and an explanation assembled from
    such items cannot be audited by anyone who was not present when it ran.

    Invariants:
      * `description` and `verification` are non-empty.
      * `supporting_ids` is non-empty and sorted. These are the artifact identifiers --
        evidence records, events, entities -- that re-executing `verification` must
        reproduce. Sorted because an unsequenced collection serializes two ways and breaks
        the determinism guarantee.
      * `strength` lies in `[0.0, 1.0]`. It is this item's own weight, not a confidence:
        confidence is a `ConfidenceVector` assembled from many items.
      * `provenance_class` is the class of the item itself. A `RULE` item is typically
        `ASSUMED` (a rule is a declaration, not an observation) and a
        `STATISTICAL_ASSOCIATION` item is `STATISTICAL`; neither is ever `OBSERVED` merely
        because the records it cites are.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_item_id: str
    kind: EvidenceKind
    description: str
    supporting_ids: tuple[str, ...]
    strength: float
    verification: str
    provenance_class: ProvenanceClass

    @model_validator(mode="after")
    def _check_invariants(self) -> EvidenceItem:
        """Enforce the documented invariants at construction."""
        if not self.description.strip():
            raise LawViolationError(
                "EvidenceItem.description is empty; an unlabelled justification cannot be "
                "read by the person it exists for (LAW-EVIDENCE)."
            )
        if not self.verification.strip():
            raise LawViolationError(
                "EvidenceItem.verification is empty; an item nobody can re-execute is a "
                "defect, not a weak item (LAW-EVIDENCE)."
            )
        if not self.supporting_ids:
            raise LawViolationError(
                "EvidenceItem.supporting_ids is empty; re-executing the verification must "
                "reproduce something (LAW-EVIDENCE)."
            )
        if list(self.supporting_ids) != sorted(self.supporting_ids):
            raise ContractViolationError(
                "EvidenceItem.supporting_ids must be sorted (CONVENTIONS.md §11); an "
                "unsequenced collection serializes two ways."
            )
        if not 0.0 <= self.strength <= 1.0:
            raise ContractViolationError(
                f"EvidenceItem.strength {self.strength} lies outside [0.0, 1.0]."
            )
        return self
