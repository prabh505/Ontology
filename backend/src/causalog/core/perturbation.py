"""What a hypothetical does to an instant and to a magnitude (ADR-0068, ADR-0069).

This module holds two things that belong together and belong at L0.

**A simulated instant is not a `TimeInterval`.** `TIMESTAMP_PROVENANCE_CLASSES` excludes
`SIMULATED` and `TimeInterval` is frozen (ADR-0021), so a simulated time cannot wear the
observed type. That exclusion is not an obstacle to route around: prd.md §37 requires that
observed facts and counterfactual simulations "never be conflated in the implementation or
the user interface", and one type carrying both is that conflation at the level where it is
hardest to see. `SimulatedInstant` is therefore a separate shape. A consumer holding one
cannot mistake it for history, and neither can a serializer -- which is where the cheaper
answer (reuse the interval, carry the class on the container) fails, because values escape
their containers.

**The arithmetic lives here rather than in the simulator**, for the reason ADR-0061 put
`core/attribution.py` here. `scripts/check_metrics_are_declared.py` scans
`counterfactual_engine/` and refuses arithmetic over a domain-metric name, and it is right
to: a formula written into a reasoning package makes the pack's declaration decorative, and
swapping the pack then changes the declaration and not the sum. Every *domain* magnitude is
still read by walking a declared `MeasurementExpression` tree through `core.measurement`.
What is here operates on a reading that walk has already produced, and knows nothing about
what the reading measures.

LAW-TIME IS NOT SUSPENDED INSIDE A HYPOTHETICAL
-----------------------------------------------
`precedes` applies exactly the rule `core.temporal.verdict` applies, on the same conservative
reading: precedence holds only when the latest moment the antecedent could occupy is still
before the earliest moment the consequent could. Overlap is `UNDETERMINED`, never a tie broken
on a bound or a midpoint. The one difference is what it does NOT check -- a simulated instant
has no timestamp provenance to disqualify it, because every simulated instant carries exactly
one class and `SimulatedInstant` makes that structural rather than checked.

There is no `SIMULATED` escape hatch anywhere below: a hypothetical that would place an
antecedent at or after its consequent is a `VIOLATION` here, and the caller refuses it rather
than simulating it and attaching a flag.

**No domain vocabulary appears below.**
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final

from pydantic import BaseModel, ConfigDict, model_validator

from causalog.core.errors import ContractViolationError, LawViolationError
from causalog.core.identifiers import FLOAT_QUANTIZATION_PLACES
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import Precision, TemporalVerdict, TimeInterval

__all__ = [
    "SIMULATION_IS_NOT_A_PREDICTION_NOTICE",
    "SimulatedInstant",
    "carry_instant",
    "precedes",
    "refuse_violation",
    "scale_reading",
    "shift_instant",
    "surviving_share",
    "transmitted_reading",
    "unscale_reading",
]

#: Fixed text. Held here so that the one sentence stating what a simulated value is has a
#: single home, and imported wherever it is shown -- `propagation_analyzer/graph.py` already
#: imports `ATTRIBUTION_NOT_MEASUREMENT_NOTICE` rather than restating it, with a note that two
#: copies of a caveat have drifted once in this repository already.
SIMULATION_IS_NOT_A_PREDICTION_NOTICE: Final[str] = (
    "SIMULATED. This is a hypothetical about the PAST, not a forecast of the future and not "
    "a measurement of anything. It is what the stated graph implies under the stated change, "
    "propagated along links that were derived from rules, temporal structure and frequency "
    "rather than identified as causal effects. No counterfactual was observed and no "
    "confounder was adjusted for, so the figure has no identification argument behind it. It "
    "may never be written back into history, and it may never be read as a prediction."
)


def _quantize(value: float) -> float:
    """Return the value at the one admissible precision (`CONVENTIONS.md` §11).

    Two boundaries that round differently produce two identifiers for one quantity, which
    surfaces as an unreproducible artifact rather than as an exception.
    """
    return round(value, FLOAT_QUANTIZATION_PLACES)


class SimulatedInstant(BaseModel):
    """When something happens in a hypothetical world, and what moved it there.

    Deliberately NOT a `TimeInterval` (ADR-0068). It carries no `provenance` field and no
    `source` field, so the two shapes are not interchangeable by accident or by a
    structurally-typed helper; what it carries instead is the base locator it derives from
    and the signed shift that produced it, which is what a reader needs to check the move.

    Invariants:
      * both bounds are timezone-aware UTC, and `t_earliest <= t_latest`.
      * `precision` is carried from the base interval and is never narrowed. A hypothetical
        may move an instant; it may not make the source more precise about it than the source
        was, which would be imputation under another name (`CONVENTIONS.md` §10).
      * `derivation` is non-empty, so no simulated instant exists without a stated reason.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    t_earliest: datetime
    t_latest: datetime
    precision: Precision
    #: The `TimeInterval.source` of the historical interval this derives from. A locator,
    #: never parsed here -- parsing it would make engine code a reader of the source
    #: description (the rule `core/precedence.py` states for the same reason).
    base_source: str
    #: Signed seconds applied to both bounds. `0.0` means the instant was carried through a
    #: hypothetical unchanged, which is a different statement from never having been touched.
    shifted_by_seconds: float
    #: Why this instant is where it is, in a sentence a reader can check.
    derivation: str

    @property
    def provenance_class(self) -> ProvenanceClass:
        """Return `SIMULATED`, always.

        A property rather than a field: a field could be set to something else on a
        deserialization path, and there is no admissible second value. `SIMULATED` is the
        weakest member of `WEAKEST_FIRST`, so `core.provenance.combine` makes containment
        structural -- anything combined with this is simulated too.
        """
        return ProvenanceClass.SIMULATED

    @property
    def notice(self) -> str:
        """Return the fixed statement of what this value is and is not.

        A property rather than a field so that no revision can soften it and it enters no
        content address.
        """
        return SIMULATION_IS_NOT_A_PREDICTION_NOTICE

    @property
    def is_unplaced(self) -> bool:
        """Return whether the base interval never placed this occurrence at all.

        An unplaced instant shifted by an hour is still unplaced. Reporting it as moved
        would claim the hypothetical did something the data cannot witness.
        """
        return self.precision is Precision.UNKNOWN

    @model_validator(mode="after")
    def _check_invariants(self) -> SimulatedInstant:
        """Enforce the documented invariants at construction."""
        for label, moment in (("t_earliest", self.t_earliest), ("t_latest", self.t_latest)):
            if moment.tzinfo is None:
                raise ContractViolationError(
                    f"SimulatedInstant.{label} is naive. Local time never exists inside the "
                    "engine (CONVENTIONS.md §10), and a hypothetical is not an exemption."
                )
        if self.t_earliest > self.t_latest:
            raise ContractViolationError(
                "SimulatedInstant.t_earliest is after t_latest; the bounds name no interval."
            )
        if not self.derivation.strip():
            raise ContractViolationError(
                "SimulatedInstant.derivation is empty. A simulated instant whose reason "
                "nobody can read is a number with a timestamp's shape and no standing."
            )
        return self

    def sort_key(self) -> tuple[datetime, datetime, str]:
        """Return the canonical sequencing key (`CONVENTIONS.md` §11)."""
        return (self.t_earliest, self.t_latest, self.base_source)


def carry_instant(base: TimeInterval, *, derivation: str) -> SimulatedInstant:
    """Return the base interval carried into a hypothetical world unchanged.

    Used for every occurrence a hypothetical does not move. It exists so that a simulated
    world holds one shape throughout: a world mixing `TimeInterval` for untouched
    occurrences and `SimulatedInstant` for moved ones would put the burden of telling them
    apart on every consumer, which is the conflation ADR-0068 refuses.

    Args:
        base: the historical interval this derives from.
        derivation: why this instant is where it is.

    Returns:
        The same bounds and precision, under the simulated shape, with a zero shift.
    """
    return SimulatedInstant(
        t_earliest=base.t_earliest,
        t_latest=base.t_latest,
        precision=base.precision,
        base_source=base.source,
        shifted_by_seconds=0.0,
        derivation=derivation,
    )


def shift_instant(base: TimeInterval, delta: timedelta, *, derivation: str) -> SimulatedInstant:
    """Return the base interval moved by a signed delta, both bounds together.

    Both bounds move by the same amount, so the interval's WIDTH is preserved. Widening or
    narrowing it would change what the source is claimed to have recorded, which a
    hypothetical about an occurrence's timing has no standing to do.

    An `UNKNOWN`-precision interval is returned unmoved with a zero shift: the data never
    placed the occurrence, so there is nothing to move, and shifting the sentinel bounds
    would manufacture a placement out of an absence. The caller sees `is_unplaced` and
    reports it rather than presenting an unmoved instant as a moved one.

    Args:
        base: the historical interval this derives from.
        delta: the signed amount to move both bounds by.
        derivation: why the instant is being moved.

    Returns:
        The moved interval under the simulated shape.

    Raises:
        ContractViolationError: if the shift would carry a bound outside the representable
            range, which is a bound the caller must catch rather than saturate silently.
    """
    if base.precision is Precision.UNKNOWN:
        return SimulatedInstant(
            t_earliest=base.t_earliest,
            t_latest=base.t_latest,
            precision=base.precision,
            base_source=base.source,
            shifted_by_seconds=0.0,
            derivation=(
                f"{derivation} -- NOT MOVED: the source never placed this occurrence, so "
                "there is no instant for a hypothetical to move. Shifting the unbounded "
                "sentinel would manufacture a placement out of an absence."
            ),
        )
    try:
        moved_earliest = base.t_earliest + delta
        moved_latest = base.t_latest + delta
    except (OverflowError, ValueError) as overflow:
        raise ContractViolationError(
            f"shifting {base.source!r} by {delta} carries a bound outside the representable "
            "range. Saturating at the extreme would silently turn a stated move into a "
            "different one, so it is refused here."
        ) from overflow
    return SimulatedInstant(
        t_earliest=moved_earliest,
        t_latest=moved_latest,
        precision=base.precision,
        base_source=base.source,
        shifted_by_seconds=_quantize(delta.total_seconds()),
        derivation=derivation,
    )


def precedes(antecedent: SimulatedInstant, consequent: SimulatedInstant) -> TemporalVerdict:
    """Return the LAW-TIME verdict between two simulated instants.

    Exactly `core.temporal.verdict`'s rule, on the same conservative reading, with the
    timestamp-provenance disqualification omitted because it cannot apply: every
    `SimulatedInstant` carries one class and the type makes that structural.

    | condition                                       | verdict        |
    |-------------------------------------------------|----------------|
    | either instant is unplaced (`UNKNOWN`)          | `UNDETERMINED` |
    | `antecedent.t_earliest >= consequent.t_latest`  | `VIOLATION`    |
    | `antecedent.t_latest < consequent.t_earliest`   | `CERTAIN`      |
    | anything else (the intervals overlap)           | `UNDETERMINED` |

    `VIOLATION` is checked before `CERTAIN` and both after the unplaced guard, matching
    `core.temporal.verdict` so the two can never disagree about one pair of bounds.

    Args:
        antecedent: the instant claimed to come first.
        consequent: the instant claimed to come second.

    Returns:
        One of the three verdicts. Never a tie broken on a bound or a midpoint.
    """
    if antecedent.is_unplaced or consequent.is_unplaced:
        return TemporalVerdict.UNDETERMINED
    if antecedent.t_earliest >= consequent.t_latest:
        return TemporalVerdict.VIOLATION
    if antecedent.t_latest < consequent.t_earliest:
        return TemporalVerdict.CERTAIN
    return TemporalVerdict.UNDETERMINED


def scale_reading(reading: float, multiplier: float) -> float:
    """Return a reading rescaled by a modifier's declared multiplier.

    The one operation an `AMPLIFYING` or `INHIBITING` link performs. Both kinds express
    themselves on one scale so that the arithmetic never branches on the kind -- which is
    why `AmplifyingCause` refuses a multiplier at or below 1.0 and `InhibitingCause` refuses
    one at or above it. Nothing here re-checks that; the payload types already did, at
    construction, and re-checking would put the invariant in two places.

    Args:
        reading: a magnitude a declared measurement tree already produced.
        multiplier: the modifier's declared multiplier.

    Returns:
        The rescaled reading, quantized.

    Raises:
        ContractViolationError: on a negative multiplier. A negative one would flip the sign
            of a magnitude, which is neither amplification nor inhibition and has no
            declared meaning.
    """
    if multiplier < 0.0:
        raise ContractViolationError(
            f"scale_reading received multiplier {multiplier}; a modifier scales a magnitude "
            "and may not invert its sign. Below 1.0 is inhibition and above it is "
            "amplification; there is no declared meaning below zero."
        )
    return _quantize(reading * multiplier)


def surviving_share(removed_shares: tuple[float, ...]) -> float:
    """Return the share of an effect that survives after removing some of its causes.

    Args:
        removed_shares: the apportioned shares of the causes removed. Each is one link's
            `PropagationWeight.weight`, which is an APPORTIONMENT and not a measurement of
            anything in the world -- `ATTRIBUTION_NOT_MEASUREMENT_NOTICE` states the limit
            and the caller carries it onto every figure derived here.

    Returns:
        The surviving share, in `[0.0, 1.0]`.

    Raises:
        ContractViolationError: if any share lies outside `[0.0, 1.0]`, or if the shares sum
            to more than one plus a rounding allowance. Over-subscription means the caller
            assembled a set that double-counts a cause, and continuing would return a
            negative survival that reads as a magnitude.
    """
    for share in removed_shares:
        if not 0.0 <= share <= 1.0:
            raise ContractViolationError(
                f"surviving_share received share {share}, outside [0.0, 1.0]. A share is an "
                "apportionment of one effect among the causes stated for it."
            )
    total = sum(removed_shares)
    allowance = 10.0**-FLOAT_QUANTIZATION_PLACES
    if total > 1.0 + allowance:
        raise ContractViolationError(
            f"surviving_share received shares summing to {total}, above 1.0. The removed set "
            "double-counts a cause; continuing would return a negative survival, which would "
            "then be rendered as a magnitude."
        )
    return _quantize(max(0.0, 1.0 - total))


def transmitted_reading(
    reading: float,
    removed_shares: tuple[float, ...],
    *,
    eliminated: bool,
) -> float:
    """Return what a reading becomes once some of its causes are removed.

    **The single most common counterfactual error is answered here.** Removing one of
    several joint causes does NOT eliminate the outcome: the remaining members still hold it
    up, so the reading is reduced by the removed share and no further. Elimination is a
    separate, explicit statement -- `eliminated` is passed by the caller only when the graph
    says nothing reaches the effect any more, which is a re-reachability question
    (ADR-0061's diff, not a subtraction) and is settled before this is called.

    That split is why `eliminated` is a keyword argument rather than something inferred from
    the shares summing to one. Shares summing to one under an apportionment is an arithmetic
    coincidence; nothing reaching the effect is a fact about the graph, and reading the first
    as the second is how a partial removal comes to be reported as a prevention.

    Args:
        reading: a magnitude a declared measurement tree already produced.
        removed_shares: the apportioned shares of the causes removed.
        eliminated: whether the graph says the effect is no longer reached at all.

    Returns:
        `0.0` when eliminated; otherwise the reading scaled by the surviving share.
    """
    if eliminated:
        return 0.0
    return _quantize(reading * surviving_share(removed_shares))


def refuse_violation(
    antecedent: SimulatedInstant,
    consequent: SimulatedInstant,
    *,
    detail: str,
) -> None:
    """Raise if a hypothetical would place an antecedent at or after its consequent.

    LAW-TIME holds inside a hypothetical exactly as it holds outside one. A world in which
    an antecedent follows its consequent is not a world this engine can reason about, and
    simulating it and attaching a flag would produce a confidently wrong answer through
    machinery that looks like it is working.

    Args:
        antecedent: the instant claimed to come first.
        consequent: the instant claimed to come second.
        detail: what the caller was attempting, named in the message.

    Raises:
        LawViolationError: if the verdict is `VIOLATION`.
    """
    if precedes(antecedent, consequent) is TemporalVerdict.VIOLATION:
        raise LawViolationError(
            f"LAW-TIME: {detail} would place an antecedent at or after its consequent "
            f"({antecedent.t_earliest.isoformat()} against "
            f"{consequent.t_latest.isoformat()}). A hypothetical is not an exemption from "
            "LAW-TIME; the change is refused rather than simulated and flagged."
        )


def unscale_reading(reading: float, multiplier: float) -> float | None:
    """Return what a reading would have been had a modifier not applied to it.

    A measured magnitude already CONTAINS whatever really modified it. So removing a
    modifier from a hypothetical does not multiply the reading -- it undoes the multiply,
    and the same inverse serves both kinds. That symmetry is the point of expressing
    amplification and inhibition on one scale: removing an amplifier makes the consequence
    smaller and removing an inhibitor makes it larger, and neither needs its own branch.

    Returns `None` for a multiplier of zero, which is total suppression. A consequence that
    was suppressed entirely has a measured magnitude of nothing, and what it *would* have
    been without the suppressor is not recoverable from that -- it is unbounded, not
    infinite, and returning a number here would invent one. The caller reports it as
    unmeasurable with the reason, and never as zero.

    Args:
        reading: a magnitude a declared measurement tree already produced.
        multiplier: the removed modifier's declared multiplier.

    Returns:
        The reading with the modifier undone, or `None` when it cannot be recovered.

    Raises:
        ContractViolationError: on a negative multiplier, for `scale_reading`'s reason.
    """
    if multiplier < 0.0:
        raise ContractViolationError(
            f"unscale_reading received multiplier {multiplier}; a modifier scales a "
            "magnitude and may not invert its sign."
        )
    if multiplier == 0.0:
        return None
    return _quantize(reading / multiplier)
