"""Timestamp comparison semantics under uncertainty (ADR-0007, ADR-0021).

The properties here are the ones LAW-TIME rests on. `strictly_before` is the conservative
reading of interval precedence, and the danger it guards against is a plausible-looking
implementation that compares start bounds, or midpoints, or falls back to a sort position
when the intervals overlap. Every one of those would answer "before" for pairs the source
never separated, and every downstream causal claim would inherit the invention.
"""

from __future__ import annotations

import pytest
from hypothesis import given

from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import (
    Precision,
    TemporalVerdict,
    TimeInterval,
    TimestampKind,
    is_unverifiable,
    strictly_before,
    verdict,
)
from tests.unit.core.strategies import intervals, placed_intervals, unknown_intervals

pytestmark = pytest.mark.property


# ---------------------------------------------------------------------------------------
# strictly_before: the precedence relation
# ---------------------------------------------------------------------------------------


@given(intervals())
def test_no_interval_strictly_precedes_itself(interval: TimeInterval) -> None:
    """Irreflexive. An event does not happen before itself, whatever its precision."""
    assert not strictly_before(interval, interval)


@given(intervals(), intervals())
def test_precedence_is_asymmetric(left: TimeInterval, right: TimeInterval) -> None:
    """Two intervals cannot each precede the other."""
    assert not (strictly_before(left, right) and strictly_before(right, left))


@given(placed_intervals(), placed_intervals(), placed_intervals())
def test_precedence_is_transitive(
    first: TimeInterval, second: TimeInterval, third: TimeInterval
) -> None:
    """Transitive over placed intervals, which is what makes a chain of edges coherent."""
    if strictly_before(first, second) and strictly_before(second, third):
        assert strictly_before(first, third)


@given(intervals(), intervals())
def test_overlapping_intervals_never_precede_each_other(
    left: TimeInterval, right: TimeInterval
) -> None:
    """Overlap is never "before" -- the property the whole design turns on.

    If the intervals share any instant, no assignment of true instants within them settles
    the question, so precedence must be false in both directions.
    """
    overlaps = left.t_earliest <= right.t_latest and right.t_earliest <= left.t_latest
    if overlaps:
        assert not strictly_before(left, right)
        assert not strictly_before(right, left)


@given(placed_intervals(), placed_intervals())
def test_precedence_holds_only_when_the_bounds_cannot_be_reversed(
    cause: TimeInterval, effect: TimeInterval
) -> None:
    """`strictly_before` is exactly `cause.t_latest < effect.t_earliest` and nothing more."""
    assert strictly_before(cause, effect) == (cause.t_latest < effect.t_earliest)


# ---------------------------------------------------------------------------------------
# verdict: the three-valued LAW-TIME test
# ---------------------------------------------------------------------------------------


@given(intervals(), intervals())
def test_the_verdict_is_total(cause: TimeInterval, effect: TimeInterval) -> None:
    """Every pair yields exactly one verdict; there is no undefined region."""
    assert verdict(cause, effect) in set(TemporalVerdict)


@given(intervals(), intervals())
def test_certain_implies_strict_precedence(cause: TimeInterval, effect: TimeInterval) -> None:
    """A CERTAIN verdict never outruns the precedence relation.

    A CERTAIN verdict is the only one that may be promoted to INFERRED, so it must
    never outrun the precedence relation underneath it.
    """
    if verdict(cause, effect) is TemporalVerdict.CERTAIN:
        assert strictly_before(cause, effect)


@given(intervals(), intervals())
def test_an_unverifiable_interval_yields_no_assertion_either_way(
    cause: TimeInterval, effect: TimeInterval
) -> None:
    """With no recorded instant you can claim neither precedence nor violation.

    The guard runs before the VIOLATION test for exactly this reason: an implementation
    that compared the sentinel bounds directly would report a violation for pairs the
    source simply never placed.
    """
    if is_unverifiable(cause) or is_unverifiable(effect):
        assert verdict(cause, effect) is TemporalVerdict.UNDETERMINED


@given(placed_intervals(), placed_intervals())
def test_an_inferred_interval_never_yields_certain(
    cause: TimeInterval, effect: TimeInterval
) -> None:
    """Derived bounds may narrow a window but may never certify an inference.

    ADR-0021: derived bounds may narrow a window but may never certify an inference,
    or one inference would stand on another with no observation underneath.
    """
    inferred = ProvenanceClass.INFERRED in (cause.provenance, effect.provenance)
    if inferred:
        assert verdict(cause, effect) is not TemporalVerdict.CERTAIN


@given(placed_intervals(), placed_intervals())
def test_verdict_is_antisymmetric_between_certain_and_violation(
    cause: TimeInterval, effect: TimeInterval
) -> None:
    """CERTAIN one way implies VIOLATION the other.

    If the pair is CERTAIN one way it must be a VIOLATION the other, because a cause
    that provably precedes an effect provably does not follow it.
    """
    if verdict(cause, effect) is TemporalVerdict.CERTAIN:
        assert verdict(effect, cause) is TemporalVerdict.VIOLATION


# ---------------------------------------------------------------------------------------
# the derived kind
# ---------------------------------------------------------------------------------------


@given(intervals())
def test_the_derived_kind_agrees_with_the_stored_fields(interval: TimeInterval) -> None:
    """`kind` is derived, so it can never contradict precision and provenance."""
    if interval.precision is Precision.UNKNOWN:
        assert interval.kind is TimestampKind.UNKNOWN
    elif interval.provenance is ProvenanceClass.INFERRED:
        assert interval.kind is TimestampKind.INFERRED
    elif interval.precision is Precision.EXACT:
        assert interval.kind is TimestampKind.EXACT
        assert interval.t_earliest == interval.t_latest
    else:
        assert interval.kind is TimestampKind.INTERVAL


@given(unknown_intervals())
def test_an_unknown_interval_excludes_nothing(interval: TimeInterval) -> None:
    """The absent instant spans everything.

    The absent instant spans everything, which is the honest encoding of "not recorded"
    and the reason it can never be narrowed by imputation.
    """
    assert is_unverifiable(interval)
    assert interval.provenance is ProvenanceClass.ASSUMED


@given(intervals())
def test_the_sort_key_is_not_a_precedence_claim(interval: TimeInterval) -> None:
    """The sort key is a display sequence, not a causal claim.

    The sort key exists for a stable display sequence. Two intervals may sort adjacently
    and still be temporally incomparable; this test records that they are different
    questions so that nobody wires the sort into a causal check.
    """
    assert interval.sort_key() == (interval.t_earliest, interval.t_latest)
