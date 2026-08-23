"""LAW-PROVENANCE: the closed, disjoint provenance classes.

Every assertion the system holds or emits carries exactly one of these. The classes are
never merged and never silently promoted; promotion is an explicit, logged,
evidence-bearing operation (ADR-0005).
"""

from __future__ import annotations

from enum import Enum

__all__ = ["WEAKEST_FIRST", "ProvenanceClass"]


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
