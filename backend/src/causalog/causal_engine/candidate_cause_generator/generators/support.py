"""Shared, generator-neutral helpers. No generator logic lives here.

Three things every generator needs and none of them should implement twice: minting a
content-addressed `EvidenceItem`, measuring the separation between two intervals as
BOUNDS, and grouping events by the timeline that holds them.
"""

from __future__ import annotations

from causalog.core.identifiers import (
    IdentifierPrefix,
    canonical_payload,
    canonical_sequence,
    canonical_text,
    digest,
)
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import TimeInterval, is_unverifiable
from causalog.core.types import Event, EvidenceItem, EvidenceKind, Timeline, TimelineEntryKind

__all__ = [
    "SeparationBounds",
    "events_of_timeline",
    "evidence_item",
    "separation_bounds",
]


class SeparationBounds:
    """The separation between two intervals, as bounds rather than as a point.

    Collapsing an interval for computation is a defect (`CONVENTIONS.md` §10), so this
    carries both ends and never a midpoint. `unbounded` is True when either interval is
    unverifiable, in which case the numbers mean nothing and the caller must not compare
    them against a window -- a comparison against a bound derived from an absent instant
    is a comparison against a number the source never recorded.
    """

    __slots__ = ("maximum_seconds", "minimum_seconds", "unbounded")

    def __init__(self, minimum_seconds: int, maximum_seconds: int, unbounded: bool) -> None:
        """Bind the two bounds and whether either interval was ever placed."""
        self.minimum_seconds = minimum_seconds
        self.maximum_seconds = maximum_seconds
        self.unbounded = unbounded

    def within(
        self,
        window_minimum: int,
        window_maximum: int,
        minimum_inclusive: bool,
        maximum_inclusive: bool,
    ) -> bool:
        """Return whether the observed separation can lie inside the declared window.

        Deliberately permissive at the boundary of UNCERTAINTY and strict at the boundary
        of the DECLARATION: the test is whether the two ranges overlap at all, because a
        pair whose separation is only known to lie in `[0, 86400]` might genuinely lie
        inside a `[0, 3600]` window, and excluding it would be a claim the data does not
        support. The inclusivity flags are honoured exactly as authored, because "within
        24 hours" and "within 24 hours, exclusive" are different declarations.
        """
        if self.unbounded:
            return False
        low_ok = (
            self.maximum_seconds >= window_minimum
            if minimum_inclusive
            else self.maximum_seconds > window_minimum
        )
        high_ok = (
            self.minimum_seconds <= window_maximum
            if maximum_inclusive
            else self.minimum_seconds < window_maximum
        )
        return low_ok and high_ok


def separation_bounds(cause: TimeInterval, effect: TimeInterval) -> SeparationBounds:
    """Return how far apart two intervals could be, in whole seconds.

    The minimum is the closest the two could be (`effect.t_earliest - cause.t_latest`,
    floored at zero), the maximum the furthest (`effect.t_latest - cause.t_earliest`). A
    negative minimum is clamped to zero rather than reported: a negative separation is a
    statement about sequence, and sequence is `core.temporal.verdict`'s answer to give, not
    this function's.
    """
    if is_unverifiable(cause) or is_unverifiable(effect):
        return SeparationBounds(0, 0, unbounded=True)
    closest = int((effect.t_earliest - cause.t_latest).total_seconds())
    furthest = int((effect.t_latest - cause.t_earliest).total_seconds())
    return SeparationBounds(max(closest, 0), max(furthest, 0), unbounded=False)


def evidence_item(
    *,
    kind: EvidenceKind,
    description: str,
    verification: str,
    supporting_ids: tuple[str, ...],
    strength: float,
    provenance_class: ProvenanceClass,
) -> EvidenceItem:
    """Return one content-addressed, re-verifiable justification.

    The identifier is a digest over the item's own content, so two runs over one dataset
    mint one identifier and a rerun is byte-identical (`CONVENTIONS.md` §9, §11).
    `EvidenceItem` carried a free-form identifier until now because nothing had needed to
    mint one; this module mints thousands.

    `strength` is this item's own weight and is NOT a confidence (`docs/contracts.md` §5).
    Nothing here aggregates it, compares it, or ranks on it -- module 10 assembles named
    components from these, and this module hands them over untouched.
    """
    sorted_ids = tuple(sorted(supporting_ids))
    return EvidenceItem(
        evidence_item_id=digest(
            IdentifierPrefix.EVIDENCE_ITEM,
            canonical_payload(
                canonical_text(kind.value),
                canonical_text(description),
                canonical_text(verification),
                canonical_sequence(sorted_ids),
                canonical_text(provenance_class.value),
            ),
        ),
        kind=kind,
        description=description,
        supporting_ids=sorted_ids,
        strength=strength,
        verification=verification,
        provenance_class=provenance_class,
    )


def events_of_timeline(timeline: Timeline, events_by_id: dict[str, Event]) -> tuple[Event, ...]:
    """Return the events one timeline actually holds, in the timeline's own sequence.

    Entries that mark a gap rather than an occurrence are skipped: a gap has no event
    identifier, and a generator that treated one as an occurrence would be proposing a
    cause the source never recorded. An entry naming an event the fact set does not hold is
    also skipped -- that is a caller assembling mismatched inputs, and it is reported by the
    module's own totals reconciliation rather than papered over here.
    """
    held: list[Event] = []
    for entry in timeline.entries:
        if entry.kind is not TimelineEntryKind.EVENT or entry.event_id is None:
            continue
        event = events_by_id.get(entry.event_id)
        if event is not None:
            held.append(event)
    return tuple(held)
