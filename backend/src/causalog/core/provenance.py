"""LAW-PROVENANCE: the closed, disjoint provenance classes.

Every assertion the system holds or emits carries exactly one of these. The classes are
never merged and never silently promoted; promotion is an explicit, logged,
evidence-bearing operation (ADR-0005).
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from types import MappingProxyType
from typing import Final

from causalog.core.errors import ContractViolationError

__all__ = ["PROVENANCE_STRENGTH", "WEAKEST_FIRST", "ProvenanceClass", "combine"]


class ProvenanceClass(str, Enum):
    """How a thing came to be known. Orthogonal to how confident we are in it."""

    OBSERVED = "OBSERVED"
    """Present in the source data. Never produced by an inference module."""

    ASSUMED = "ASSUMED"
    """Supplied by configuration or narrowed by a process constraint, not observed."""

    STATISTICAL = "STATISTICAL"
    """A deterministic frequency association. Never by itself a causal claim."""

    INFERRED = "INFERRED"
    """Derived by rule or temporal reasoning. Never overwrites an OBSERVED value."""

    SIMULATED = "SIMULATED"
    """Produced inside a hypothetical world. Never written back to history."""


#: Aggregation across mixed provenance takes the WEAKEST class present (ADR-0005).
#: Sequenced weakest to strongest; this tuple is the only admissible ranking.
WEAKEST_FIRST: tuple[ProvenanceClass, ...] = (
    ProvenanceClass.SIMULATED,
    ProvenanceClass.ASSUMED,
    ProvenanceClass.STATISTICAL,
    ProvenanceClass.INFERRED,
    ProvenanceClass.OBSERVED,
)


#: Strength ranking derived from `WEAKEST_FIRST`, which stays the single source of truth.
#: A higher number is a stronger claim about how the value came to be known.
PROVENANCE_STRENGTH: Final[Mapping[ProvenanceClass, int]] = MappingProxyType(
    {member: rank for rank, member in enumerate(WEAKEST_FIRST)}
)


def combine(*classes: ProvenanceClass) -> ProvenanceClass:
    """Return the weakest provenance class among the inputs (ADR-0005).

    This is the provenance algebra. Combining two inputs never produces a result stronger
    than the weaker of them: an assertion built on an `ASSUMED` input is `ASSUMED`, no
    matter how strong its other inputs are. There is no promotion path here, and there is
    deliberately no argument that supplies one -- promotion is a separate, explicit,
    evidence-bearing operation performed by a named module, never a side effect of
    combining.

    Invariants (asserted in `tests/unit/core/test_provenance_algebra.py`):
      * The result equals one of the inputs.
      * The result is never stronger than any input.
      * Commutative, associative, and idempotent.

    Raises:
        ContractViolationError: if called with no arguments. An empty combination has no
            defensible answer, and returning `OBSERVED` for it would silently manufacture
            the strongest class in the system out of nothing.
    """
    if not classes:
        raise ContractViolationError(
            "causalog.core.provenance.combine requires at least one provenance class; "
            "an empty combination has no weakest member (ADR-0005)."
        )
    return min(classes, key=lambda member: PROVENANCE_STRENGTH[member])
