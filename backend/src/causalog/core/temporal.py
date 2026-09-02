"""Time representation and the LAW-TIME verdict.

`CONVENTIONS.md` §10: every event timestamp is an *interval*, all instants are UTC, a
naive datetime is a defect, and local time never exists inside the engine. A missing
instant is never imputed.

Comparison semantics under uncertainty -- read this before touching LAW-TIME
---------------------------------------------------------------------------
An interval timestamp is a partial precedence relation, not a total one. Two intervals may
be genuinely incomparable, and the whole point of ADR-0007 is that the engine says so
rather than guessing.

    strictly_before(cause, effect)  is  cause.t_latest < effect.t_earliest

That is the entire definition. It is deliberately the most conservative reading available:
precedence holds only when the *latest* moment the cause could have happened is still
before the *earliest* moment the effect could have happened, so no assignment of true
instants within the two intervals could reverse it.

**Overlap is never "before".** If the intervals share even one instant, the data cannot
separate them, and the answer is `UNDETERMINED` -- not `CERTAIN`, not `VIOLATION`, and
never a tie broken by an interval midpoint, a start bound, or a sequence position. Every
one of those tie-breaks manufactures precedence the source never recorded, which is the
exact failure LAW-TIME exists to prevent.

The verdict is total over the interval space -- every pair yields exactly one of three
answers -- while the precedence relation underneath it is partial. That asymmetry is
intentional: `UNDETERMINED` is the name for the pairs where precedence has no answer.

    +-------------------------------------------+---------------+
    | condition                                  | verdict       |
    +-------------------------------------------+---------------+
    | either interval is UNKNOWN precision       | UNDETERMINED  |
    | cause.t_earliest >= effect.t_latest        | VIOLATION     |
    | cause.t_latest < effect.t_earliest,        | CERTAIN       |
    |   and neither interval is INFERRED         |               |
    | anything else (the intervals overlap)      | UNDETERMINED  |
    +-------------------------------------------+---------------+

`VIOLATION` is checked before `CERTAIN` and both are checked after the `UNKNOWN` guard,
because an unknown bound cannot support any assertion at all -- including the negative
one. With no information you cannot claim a violation any more than you can claim
precedence.

An `INFERRED` interval never yields `CERTAIN` (ADR-0021). Its bounds were derived rather
than observed, so promoting an edge to `INFERRED` on the strength of them would let one
inference certify another with no observation anywhere underneath.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Final

from pydantic import BaseModel, ConfigDict, model_validator

from causalog.core.identifiers import COLLECTION_SEPARATOR, canonical_instant
from causalog.core.provenance import ProvenanceClass

__all__ = [
    "TIMESTAMP_PROVENANCE_CLASSES",
    "UNKNOWN_EARLIEST",
    "UNKNOWN_LATEST",
    "DurationBound",
    "Precision",
    "TemporalVerdict",
    "TimeInterval",
    "TimestampKind",
    "canonical_interval",
    "is_unverifiable",
    "strictly_before",
    "verdict",
]

#: The bounds standing in for the unbounded interval of an `UNKNOWN` timestamp.
#: `CONVENTIONS.md` §10 writes these as -inf and +inf; a `datetime` has no infinity, so
#: the representable extremes carry the same meaning: "nothing is excluded".
UNKNOWN_EARLIEST: Final[datetime] = datetime.min.replace(tzinfo=UTC)
UNKNOWN_LATEST: Final[datetime] = datetime.max.replace(tzinfo=UTC)

#: The provenance classes a timestamp may carry (ADR-0021, superseding ADR-0007).
#: `STATISTICAL` and `SIMULATED` are excluded: a timestamp derived from a frequency
#: distribution or invented inside a hypothetical world is imputation, which
#: `CONVENTIONS.md` §10 forbids outright.
TIMESTAMP_PROVENANCE_CLASSES: Final[frozenset[ProvenanceClass]] = frozenset(
    {ProvenanceClass.OBSERVED, ProvenanceClass.ASSUMED, ProvenanceClass.INFERRED}
)


class Precision(str, Enum):
    """How finely the source pinned the instant down."""

    EXACT = "EXACT"
    SECOND = "SECOND"
    MINUTE = "MINUTE"
    HOUR = "HOUR"
    DAY = "DAY"
    UNKNOWN = "UNKNOWN"


class TimestampKind(str, Enum):
    """The four shapes a timestamp takes, as one derived label.

    Derived from `precision` and `provenance` rather than stored, so it can never
    contradict them. Reading this is a convenience; the two underlying fields remain
    authoritative.
    """

    EXACT = "EXACT"
    """A single observed instant: `precision == EXACT`, bounds equal."""

    INTERVAL = "INTERVAL"
    """Observed or assumed, pinned only to a coarser granularity."""

    INFERRED = "INFERRED"
    """Bounds narrowed by derivation from other evidence, not read from the source."""

    UNKNOWN = "UNKNOWN"
    """The source recorded no instant. Nothing is excluded and nothing is claimed."""


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
    """A closed UTC interval, the precision that produced it, and where it came from.

    Invariants (enforced here, and asserted again in `tests/law/`):
      * `t_earliest` and `t_latest` are timezone-aware and in UTC; naive is a defect.
      * `t_earliest <= t_latest`.
      * `precision == EXACT` implies `t_earliest == t_latest`.
      * `precision == UNKNOWN` implies `provenance == ASSUMED` and the unbounded bounds.
      * `provenance` is one of `TIMESTAMP_PROVENANCE_CLASSES`.
      * `provenance == INFERRED` implies `precision != EXACT`. An inference may *narrow*
        bounds from other evidence; it may never manufacture a point instant, which is
        imputation under another name (ADR-0021).
      * `source` is non-empty. It names the derivation or locator that produced these
        bounds, so an interval can be traced without consulting the module that built it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    t_earliest: datetime
    t_latest: datetime
    precision: Precision
    provenance: ProvenanceClass
    source: str

    @property
    def kind(self) -> TimestampKind:
        """Return the derived timestamp shape.

        Sequence matters: `UNKNOWN` outranks everything because an absent instant is not
        an inference about one, and `INFERRED` outranks `EXACT`/`INTERVAL` because how the
        bounds were obtained governs what may be concluded from them.
        """
        if self.precision is Precision.UNKNOWN:
            return TimestampKind.UNKNOWN
        if self.provenance is ProvenanceClass.INFERRED:
            return TimestampKind.INFERRED
        if self.precision is Precision.EXACT:
            return TimestampKind.EXACT
        return TimestampKind.INTERVAL

    def sort_key(self) -> tuple[datetime, datetime]:
        """Return the canonical sort key for a stable display sequence.

        `CONVENTIONS.md` §11 sequences events by `(t_earliest, t_latest, event_id)`; this
        supplies the first two members.

        **This is not a precedence claim.** Two intervals that sort adjacently may be
        temporally incomparable. Use `strictly_before` or `verdict` for any question about
        which happened first; using a sort position to answer it silently converts a
        rendering choice into a causal assertion.
        """
        return (self.t_earliest, self.t_latest)

    @model_validator(mode="after")
    def _check_invariants(self) -> TimeInterval:
        """Enforce every documented invariant at construction."""
        for label, moment in (("t_earliest", self.t_earliest), ("t_latest", self.t_latest)):
            if moment.tzinfo is None or moment.utcoffset() is None:
                raise ValueError(
                    f"TimeInterval.{label} is naive; all instants are timezone-aware UTC "
                    "(CONVENTIONS.md §10)."
                )
            if moment.utcoffset() != timedelta(0):
                raise ValueError(
                    f"TimeInterval.{label} carries offset {moment.utcoffset()}; all "
                    "instants are stored in UTC (CONVENTIONS.md §10)."
                )
        if self.t_earliest > self.t_latest:
            raise ValueError(
                "TimeInterval bounds are reversed: t_earliest must not exceed t_latest."
            )
        if self.precision is Precision.EXACT and self.t_earliest != self.t_latest:
            raise ValueError(
                "TimeInterval with EXACT precision must have equal bounds; a range is by "
                "definition not exact (CONVENTIONS.md §10)."
            )
        if self.precision is Precision.UNKNOWN:
            if self.provenance is not ProvenanceClass.ASSUMED:
                raise ValueError(
                    "TimeInterval with UNKNOWN precision must carry ASSUMED provenance; "
                    "an absent instant was not observed and was not inferred (ADR-0007)."
                )
            if (self.t_earliest, self.t_latest) != (UNKNOWN_EARLIEST, UNKNOWN_LATEST):
                raise ValueError(
                    "TimeInterval with UNKNOWN precision must span UNKNOWN_EARLIEST to "
                    "UNKNOWN_LATEST; narrowing an absent instant to a guessed window is "
                    "imputation (CONVENTIONS.md §10)."
                )
        if self.provenance not in TIMESTAMP_PROVENANCE_CLASSES:
            raise ValueError(
                f"TimeInterval.provenance {self.provenance.value} is inadmissible; a "
                "timestamp may only be OBSERVED, ASSUMED, or INFERRED (ADR-0021)."
            )
        if self.provenance is ProvenanceClass.INFERRED and self.precision is Precision.EXACT:
            raise ValueError(
                "TimeInterval with INFERRED provenance may not claim EXACT precision; "
                "narrowing bounds is admissible, manufacturing a point instant is "
                "imputation (ADR-0021, CONVENTIONS.md §10)."
            )
        if not self.source.strip():
            raise ValueError(
                "TimeInterval.source is empty; every interval names the derivation or "
                "locator that produced its bounds (ADR-0021)."
            )
        return self


class DurationBound(BaseModel):
    """A duration in whole seconds, kept as bounds rather than a point estimate.

    Collapsing the bound for display is permitted; collapsing it for computation is a
    defect (`CONVENTIONS.md` §10).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    minimum_seconds: int
    maximum_seconds: int


def is_unverifiable(interval: TimeInterval) -> bool:
    """Return whether this interval can support no temporal assertion at all.

    True exactly when the precision is `UNKNOWN`. Distinct from an overlap: an overlap
    means the data placed both intervals and they could not be separated; unverifiable
    means the data never placed this one.
    """
    return interval.precision is Precision.UNKNOWN


def strictly_before(cause: TimeInterval, effect: TimeInterval) -> bool:
    """Return whether `cause` provably precedes `effect`.

    The definition is `cause.t_latest < effect.t_earliest` and nothing else. Overlap is
    not precedence. An unverifiable interval is not precedence. See the module docstring.
    """
    if is_unverifiable(cause) or is_unverifiable(effect):
        return False
    return cause.t_latest < effect.t_earliest


def verdict(cause: TimeInterval, effect: TimeInterval) -> TemporalVerdict:
    """Return the LAW-TIME verdict for a proposed cause/effect pair.

    Total over the interval space: every pair yields exactly one verdict. See the module
    docstring for the table and for why the `UNKNOWN` guard precedes the `VIOLATION` test.
    """
    if is_unverifiable(cause) or is_unverifiable(effect):
        return TemporalVerdict.UNDETERMINED
    if cause.t_earliest >= effect.t_latest:
        return TemporalVerdict.VIOLATION
    if strictly_before(cause, effect) and ProvenanceClass.INFERRED not in (
        cause.provenance,
        effect.provenance,
    ):
        return TemporalVerdict.CERTAIN
    return TemporalVerdict.UNDETERMINED


def canonical_interval(interval: TimeInterval) -> str:
    """Return the canonical payload encoding of an interval (`CONVENTIONS.md` §9).

    `t_earliest,t_latest,precision`. Provenance and source are deliberately excluded: they
    record how the bounds were obtained, not which moment is being described, and an event
    whose interval was later re-derived from better evidence should keep its identity if
    the bounds did not move.

    The bounds themselves DO participate, so narrowing an interval mints a new identifier.
    That is content addressing working correctly -- a different claim about when something
    happened is a different claim.
    """
    return COLLECTION_SEPARATOR.join(
        (
            canonical_instant(interval.t_earliest),
            canonical_instant(interval.t_latest),
            interval.precision.value,
        )
    )
