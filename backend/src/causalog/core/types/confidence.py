"""LAW-EVIDENCE: confidence is a decomposition, never a bare float."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from causalog.core.provenance import ProvenanceClass

__all__ = ["ConfidenceComponent", "ConfidenceVector"]


class ConfidenceComponent(BaseModel):
    """One named, inspectable contribution to a confidence figure.

    The set of component names is part of the `confidence_schema_version` contract
    (`CONTEXT.md` §7); adding, removing, or renaming one is a breaking change.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    component_name: str
    value: float
    provenance_class: ProvenanceClass
    evidence_record_ids: tuple[str, ...]


class ConfidenceVector(BaseModel):
    """The authoritative representation of confidence (OQ-005 proposed default).

    Invariants:
      * `components` is non-empty. An empty vector is a defect, not zero confidence.
      * `components` is sorted by `component_name` (`CONVENTIONS.md` §11).
      * `scalar` is a DERIVED, non-authoritative rollup. It may be displayed; it may
        never be the sole persisted representation, and no module may reconstruct a
        judgement from it alone.
      * Every component traces to evidence record identifiers, so that the value can be
        reconstructed from an audit record alone (`CONVENTIONS.md` §8).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    components: tuple[ConfidenceComponent, ...]
    scalar: float
    provenance_class: ProvenanceClass
