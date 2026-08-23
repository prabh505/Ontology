"""Time representation and the LAW-TIME verdict.

`CONVENTIONS.md` §10: every event timestamp is an *interval*, all instants are UTC, a
naive datetime is a defect, and local time never exists inside the engine. A missing
instant is never imputed.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict

from causalog.core.provenance import ProvenanceClass

__all__ = ["DurationBound", "Precision", "TemporalVerdict", "TimeInterval"]


class Precision(str, Enum):
    """How finely the source pinned the instant down."""

    EXACT = "EXACT"
    SECOND = "SECOND"
    MINUTE = "MINUTE"
    HOUR = "HOUR"
    DAY = "DAY"
    UNKNOWN = "UNKNOWN"


class TemporalVerdict(str, Enum):
    """The three-valued LAW-TIME test over two intervals.

    `CONVENTIONS.md` §10. `UNDETERMINED` is retained rather than discarded so that a
    data-quality problem stays visible instead of silently shrinking the graph.
    """

    CERTAIN = "CERTAIN"
    """cause.t_latest < effect.t_earliest -- admissible, may be promoted to INFERRED."""

    UNDETERMINED = "UNDETERMINED"
    """Intervals overlap -- candidate is retained, blocked from INFERRED promotion."""

    VIOLATION = "VIOLATION"
    """cause.t_earliest >= effect.t_latest -- the edge is rejected and never created."""


class TimeInterval(BaseModel):
    """A closed UTC interval plus the precision that produced it.

    Invariants (asserted by the owning module, tested in `tests/law/`):
      * `t_earliest` and `t_latest` are timezone-aware and in UTC; naive is a defect.
      * `t_earliest <= t_latest`.
      * `precision == EXACT` implies `t_earliest == t_latest`.
      * `precision == UNKNOWN` implies `provenance == ASSUMED`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    t_earliest: datetime
    t_latest: datetime
    precision: Precision
    provenance: ProvenanceClass


class DurationBound(BaseModel):
    """A duration in whole seconds, kept as bounds rather than a point estimate.

    Collapsing the bound for display is permitted; collapsing it for computation is a
    defect (`CONVENTIONS.md` §10).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    minimum_seconds: int
    maximum_seconds: int
