"""Place an emitted event in time, under the policy its emission rule declares.

The single rule this file exists to keep: **no policy here manufactures precision the
source did not have.** Every one either reads an interval the mapping built, widens the gap
between two it built, offsets one by a count the source recorded, or returns the unbounded
UNKNOWN interval. There is no path from a coarse instant to a fine one and no path from an
absent instant to a present one (`CONVENTIONS.md` §10, ADR-0021).

Why a derived interval is INFERRED and not ASSUMED
--------------------------------------------------
`CONVENTIONS.md` §10 separates them and the separation is load-bearing. `ASSUMED` is for
configuration and declared process constraints -- a value somebody typed into a file.
`INFERRED` is for a bound COMPUTED from other evidence. Conflating them would make a window
derived from two observed instants indistinguishable from a window somebody chose, and only
one of those is re-derivable.

An `INFERRED` interval never yields a `CERTAIN` verdict (`core.temporal.verdict`). That is
the guard that makes `BOUNDED_BETWEEN` and `OFFSET_FROM` safe to use freely: they narrow a
window, which helps a human read a timeline, and they can never certify a causal edge --
which would be one inference standing on another with no observation underneath.
"""

from __future__ import annotations

from datetime import timedelta

from causalog.core.errors import ContractViolationError
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import (
    UNKNOWN_EARLIEST,
    UNKNOWN_LATEST,
    Precision,
    TimeInterval,
)
from causalog.ingestion.schema_mapper.apply import RecordView
from causalog.ingestion.schema_mapper.dsl import OccurredAtPolicy, OccurredAtSpec

__all__ = ["PRECISION_RANK", "coarser", "occurred_at", "unknown_interval"]

#: How coarse each precision is. Used to answer "what is the precision of a window spanning
#: two instants" -- the COARSER of the two, always. A window bounded by a minute-granular
#: instant and a day-granular one is known no better than a day; claiming the minute would
#: assert a bound the second instant never supplied.
PRECISION_RANK: dict[Precision, int] = {
    Precision.EXACT: 0,
    Precision.SECOND: 1,
    Precision.MINUTE: 2,
    Precision.HOUR: 3,
    Precision.DAY: 4,
    Precision.UNKNOWN: 5,
}


def coarser(left: Precision, right: Precision) -> Precision:
    """Return the coarser of two precisions."""
    return left if PRECISION_RANK[left] >= PRECISION_RANK[right] else right


def unknown_interval(source: str) -> TimeInterval:
    """Return the unbounded interval, with `source` naming why it is unbounded."""
    return TimeInterval(
        t_earliest=UNKNOWN_EARLIEST,
        t_latest=UNKNOWN_LATEST,
        precision=Precision.UNKNOWN,
        provenance=ProvenanceClass.ASSUMED,
        source=source,
    )


def occurred_at(spec: OccurredAtSpec, record: RecordView, event_type: str) -> TimeInterval:
    """Return the interval one emitted event occupies, under its declared policy.

    Raises:
        ContractViolationError: if a policy's required reference is absent from the spec.
            The DSL validates that at load, so reaching it here is a programming error
            rather than a data one, and it is not repaired.
    """
    label = f"emission[{event_type}].occurred_at"
    if spec.policy is OccurredAtPolicy.UNKNOWN:
        return unknown_interval(f"{label}=UNKNOWN: {spec.derivation}")
    if spec.policy is OccurredAtPolicy.FROM_TEMPORAL_BINDING:
        return _from_binding(spec, record, label)
    if spec.policy is OccurredAtPolicy.BOUNDED_BETWEEN:
        return _bounded_between(spec, record, label)
    return _offset_from(spec, record, label)


def _require(reference: object, label: str, name: str) -> object:
    """Return a policy reference, refusing an absent one."""
    if reference is None:  # pragma: no cover - the DSL refuses this at load
        raise ContractViolationError(
            f"{label} declares a policy requiring {name!r} and does not supply it."
        )
    return reference


def _from_binding(spec: OccurredAtSpec, record: RecordView, label: str) -> TimeInterval:
    """Return the mapping's own interval for the declared address, unchanged.

    Unchanged is the point. This is the only policy an OBSERVED event type may use, and the
    interval it returns is exactly what the temporal binding produced -- widened to the
    declared precision by module 2 and touched by nothing since.
    """
    reference = _require(spec.anchor, label, "anchor")
    address = reference.address  # type: ignore[attr-defined]
    found = record.interval(address)
    if found is None:
        return unknown_interval(
            f"{label}=FROM_TEMPORAL_BINDING({address}): this record supplies no interval "
            "at that address"
        )
    return found


def _bounded_between(spec: OccurredAtSpec, record: RecordView, label: str) -> TimeInterval:
    """Return the window between two observed instants, as an INFERRED interval.

    Both bounds must be known. If either is `UNKNOWN` the window is not bounded at all --
    narrowing an occurrence to "before an instant we do not have" is imputation, and the
    honest answer is the unbounded interval.

    The bounds are taken WIDE: the earliest moment the earlier instant could be, and the
    latest moment the later one could be. Taking them narrow would produce a window smaller
    than the evidence supports, which is the same defect as claiming a finer precision.
    """
    earliest_ref = _require(spec.earliest, label, "earliest")
    latest_ref = _require(spec.latest, label, "latest")
    earliest_address = earliest_ref.address  # type: ignore[attr-defined]
    latest_address = latest_ref.address  # type: ignore[attr-defined]
    lower = record.interval(earliest_address)
    upper = record.interval(latest_address)
    derivation = f"{label}=BOUNDED_BETWEEN({earliest_address}, {latest_address}): {spec.derivation}"
    if lower is None or upper is None:
        return unknown_interval(
            f"{derivation} -- this record supplies no interval at one of those addresses"
        )
    if lower.precision is Precision.UNKNOWN or upper.precision is Precision.UNKNOWN:
        return unknown_interval(
            f"{derivation} -- one of the two bounding instants is itself UNKNOWN, so the "
            "window is unbounded"
        )
    if lower.t_earliest > upper.t_latest:
        # The source contradicts the declared sequence. Module 1 already reports this as a
        # precedence inversion; here it means the window would run backwards, and
        # `TimeInterval` would refuse it. The unbounded interval is what is actually known.
        return unknown_interval(
            f"{derivation} -- the declared earlier instant falls after the later one in "
            "this record, so no window between them exists"
        )
    return TimeInterval(
        t_earliest=lower.t_earliest,
        t_latest=upper.t_latest,
        precision=coarser(lower.precision, upper.precision),
        provenance=ProvenanceClass.INFERRED,
        source=derivation,
    )


def _offset_from(spec: OccurredAtSpec, record: RecordView, label: str) -> TimeInterval:
    """Return an anchor instant advanced by a whole-day count the source recorded.

    The result keeps the ANCHOR's precision. Adding whole days to a day-granular instant
    yields a day-granular instant; the arithmetic adds no information about the time of day,
    and a policy that returned a finer precision here would manufacture one.
    """
    anchor_ref = _require(spec.anchor, label, "anchor")
    days_ref = _require(spec.plus_days, label, "plus_days")
    anchor_address = anchor_ref.address  # type: ignore[attr-defined]
    days_address = days_ref.address  # type: ignore[attr-defined]
    derivation = f"{label}=OFFSET_FROM({anchor_address} + {days_address} days): {spec.derivation}"
    anchor = record.interval(anchor_address)
    days_text = record.value(days_address)
    if anchor is None or days_text is None:
        return unknown_interval(
            f"{derivation} -- this record supplies no anchor interval or no offset"
        )
    if anchor.precision is Precision.UNKNOWN:
        return unknown_interval(
            f"{derivation} -- the anchor instant is itself UNKNOWN, so the offset has "
            "nothing to advance"
        )
    try:
        days = int(float(days_text))
    except ValueError:
        return unknown_interval(
            f"{derivation} -- the offset value {days_text!r} is not a whole-day count"
        )
    shift = timedelta(days=days)
    return TimeInterval(
        t_earliest=anchor.t_earliest + shift,
        t_latest=anchor.t_latest + shift,
        precision=anchor.precision,
        provenance=ProvenanceClass.INFERRED,
        source=derivation,
    )
