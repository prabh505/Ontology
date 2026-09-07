"""A count is not a finding until you know what it was drawn from.

These tests pin the one property that separates this module from a counter: **a pattern
that occurs everywhere scores nothing.** Support and lift are computed from the same table
and answer different questions, and the historical component reads the second.
"""

from __future__ import annotations

import pytest

from causalog.causal_engine.confidence_scorer import PairBaseRates
from causalog.causal_engine.confidence_scorer.scorers.shared import (
    saturating,
    shrinkage,
    squashed_lift,
)
from causalog.core.types import Event, Timeline
from fixtures.candidates import linear_process


def _instances(*shapes: tuple[str, ...]) -> tuple[tuple[Event, ...], tuple[Timeline, ...]]:
    """Return one process instance per shape, each over its own participant."""
    events: list[Event] = []
    timelines: list[Timeline] = []
    for index, shape in enumerate(shapes):
        _, produced, built = linear_process(*shape, subject=f"S{index}")
        events.extend(produced)
        timelines.append(built)
    return tuple(events), tuple(timelines)


def _rates(*shapes: tuple[str, ...]) -> PairBaseRates:
    """Return the base rates over these instances."""
    events, timelines = _instances(*shapes)
    return PairBaseRates.of(timelines, {event.event_id: event for event in events})


def test_the_denominator_is_carried_not_implied() -> None:
    """`both` alone is meaningless; the table carries all four cells and the total.

    Four instances, three of which run ONE then TWO. The table must report both=3,
    instances=4, and reconcile: 3 + 0 + 0 + 1 == 4.
    """
    rates = _rates(
        ("STAGE_ONE", "STAGE_TWO"),
        ("STAGE_ONE", "STAGE_TWO"),
        ("STAGE_ONE", "STAGE_TWO"),
        ("STAGE_THREE",),
    )
    table = rates.table_for("STAGE_ONE", "STAGE_TWO")
    assert table is not None
    assert (table.both, table.cause_only, table.effect_only, table.neither) == (3, 0, 0, 1)
    assert table.instances == 4
    assert rates.instances == 4


def test_a_pattern_present_in_every_instance_has_lift_exactly_one() -> None:
    """The base-rate case. Enormous support, no association, and it must score zero.

    Every instance runs ONE then TWO, so P(TWO follows | ONE present) == 1.0 and
    P(TWO present) == 1.0. Lift is 1.0 -- independence -- and `squashed_lift` maps that
    to exactly 0.0 however large the count is. This is the property that makes "occurs in
    84 orders" an honest number rather than a persuasive one.
    """
    rates = _rates(*[("STAGE_ONE", "STAGE_TWO")] * 40)
    table = rates.table_for("STAGE_ONE", "STAGE_TWO")
    assert table is not None
    assert table.both == 40
    assert table.conditional_rate == 1.0
    assert table.baseline_rate == 1.0
    assert table.lift == 1.0
    assert squashed_lift(table.lift, reference=3.0) == 0.0


def test_a_pattern_that_beats_its_base_rate_scores_above_zero() -> None:
    """The same count means something different when the baseline is lower.

    Four instances: two run ONE then TWO, one runs TWO alone, one runs THREE alone. So
    P(TWO follows | ONE) == 2/2 == 1.0 and P(TWO present) == 3/4 == 0.75, giving a lift of
    1.333 -- above independence, and scoring above zero.
    """
    rates = _rates(
        ("STAGE_ONE", "STAGE_TWO"),
        ("STAGE_ONE", "STAGE_TWO"),
        ("STAGE_TWO",),
        ("STAGE_THREE",),
    )
    table = rates.table_for("STAGE_ONE", "STAGE_TWO")
    assert table is not None
    assert table.conditional_rate == 1.0
    assert table.baseline_rate == 0.75
    assert table.lift == pytest.approx(4 / 3)
    assert squashed_lift(table.lift, reference=3.0) > 0.0


def test_an_unobservable_ratio_is_none_rather_than_a_number() -> None:
    """A ratio nobody could compute is a missing component, never a substituted value.

    Folding an undefined lift into 1.0 or 0.0 would report a measurement where none was
    possible, which is the exact confusion this module refuses everywhere else.
    """
    rates = _rates(("STAGE_ONE", "STAGE_TWO"))
    assert rates.table_for("STAGE_TWO", "STAGE_ONE") is None
    assert rates.table_for("STAGE_ONE", "STAGE_NINE") is None


def test_lift_below_independence_is_not_evidence_for_the_claim() -> None:
    """Negative association scores zero, not a negative number.

    This component measures SUPPORT. A pair that co-occurs less than chance is not weak
    support for the claim; it is no support for it, and the score floor says so.
    """
    assert squashed_lift(0.5, reference=3.0) == 0.0
    assert squashed_lift(1.0, reference=3.0) == 0.0


def test_lift_reaches_one_only_at_the_declared_reference() -> None:
    """The declared reference is what 1.0 means; nothing reaches it by accident."""
    assert squashed_lift(3.0, reference=3.0) == 1.0
    assert squashed_lift(9.0, reference=3.0) == 1.0  # clamped, never above
    assert 0.0 < squashed_lift(2.0, reference=3.0) < 1.0


def test_small_samples_are_discounted_rather_than_rounded_up() -> None:
    """The same ratio over four instances and four thousand is not the same finding.

    `shrinkage(n, prior)` is exactly 0.5 at `n == prior`, which is what makes the declared
    prior readable: it is the sample size at which the pack is half convinced.
    """
    assert shrinkage(20, 20) == 0.5
    assert shrinkage(4, 20) == pytest.approx(4 / 24)
    assert shrinkage(4000, 20) > 0.99
    assert shrinkage(0, 20) == 0.0
    # Monotone: more sample is never less believable.
    assert shrinkage(5, 20) > shrinkage(4, 20)


def test_volume_saturates_rather_than_growing_without_bound() -> None:
    """The tenth justification adds less than the second, and 1.0 is never reached."""
    assert saturating(3, 3) == 0.5
    assert saturating(0, 3) == 0.0
    assert saturating(1000, 3) < 1.0
    first_step = saturating(2, 3) - saturating(1, 3)
    later_step = saturating(10, 3) - saturating(9, 3)
    assert first_step > later_step
