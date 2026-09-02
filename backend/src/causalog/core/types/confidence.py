"""LAW-EVIDENCE: confidence is a decomposition, never a bare float."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from causalog.core.errors import ContractViolationError, LawViolationError
from causalog.core.provenance import ProvenanceClass

__all__ = ["ConfidenceComponent", "ConfidenceVector"]


class ConfidenceComponent(BaseModel):
    """One named, inspectable contribution to a confidence figure.

    The set of component names is part of the `confidence_schema_version` contract
    (`CONTEXT.md` §7); adding, removing, or renaming one is a breaking change.

    Invariants:
      * `component_name` is non-empty.
      * `value` lies in `[0.0, 1.0]`. A component expressing a count (for example the
        evidence count of prd.md §49) is normalized to that range *before* it becomes a
        component, so that no aggregation function has to know which components are
        counts and which are proportions.
      * `evidence_record_ids` is the trace that makes the value re-derivable from an audit
        record alone. A component with no evidence is a defect, not a weak component.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    component_name: str
    value: float
    provenance_class: ProvenanceClass
    evidence_record_ids: tuple[str, ...]

    @model_validator(mode="after")
    def _check_invariants(self) -> ConfidenceComponent:
        """Enforce the documented invariants at construction."""
        if not self.component_name.strip():
            raise LawViolationError(
                "ConfidenceComponent.component_name is empty; every component is named "
                "and inspectable (LAW-EVIDENCE)."
            )
        if not 0.0 <= self.value <= 1.0:
            raise ContractViolationError(
                f"ConfidenceComponent.value {self.value} for "
                f"'{self.component_name}' lies outside [0.0, 1.0]; normalize counts "
                "before constructing a component (prd.md §28)."
            )
        return self


class ConfidenceVector(BaseModel):
    """The authoritative representation of confidence (ADR-0009).

    Invariants:
      * `components` is non-empty. An empty vector is a defect, not zero confidence.
      * `components` is sorted by `component_name` (`CONVENTIONS.md` §11), and no name
        appears twice -- two values under one name have no defined combination.
      * `scalar` is a DERIVED, non-authoritative rollup. It may be displayed; it may
        never be the sole persisted representation, and no module may reconstruct a
        judgement from it alone.
      * `aggregation` names the function that produced `scalar`, so the rollup can be
        recomputed and checked. A scalar whose aggregation function is unnamed is exactly
        the unexplained number LAW-EVIDENCE forbids.
      * `provenance_class` is the weakest class among the components (ADR-0005). A
        rollup is never more certain about its origin than its weakest input.
      * Every component traces to evidence record identifiers, so that the value can be
        reconstructed from an audit record alone (`CONVENTIONS.md` §8).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    components: tuple[ConfidenceComponent, ...]
    scalar: float
    aggregation: str
    provenance_class: ProvenanceClass

    @model_validator(mode="after")
    def _check_invariants(self) -> ConfidenceVector:
        """Enforce the documented invariants at construction."""
        if not self.components:
            raise LawViolationError(
                "ConfidenceVector.components is empty; an empty vector is a defect, not "
                "zero confidence (LAW-EVIDENCE)."
            )
        names = [component.component_name for component in self.components]
        if names != sorted(names):
            raise ContractViolationError(
                "ConfidenceVector.components must be sorted by component_name "
                "(CONVENTIONS.md §11); an unsequenced vector serializes two ways."
            )
        if len(set(names)) != len(names):
            raise ContractViolationError(
                "ConfidenceVector.components contains a repeated component_name; two "
                "values under one name have no defined combination."
            )
        if not 0.0 <= self.scalar <= 1.0:
            raise ContractViolationError(
                f"ConfidenceVector.scalar {self.scalar} lies outside [0.0, 1.0] " "(prd.md §28)."
            )
        if not self.aggregation.strip():
            raise LawViolationError(
                "ConfidenceVector.aggregation is empty; the scalar must name the "
                "function that produced it or it cannot be rechecked (ADR-0009)."
            )
        return self
