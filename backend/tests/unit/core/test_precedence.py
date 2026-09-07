"""Derived precedence is a directed, opaque-keyed measurement (ADR-0057).

Three properties make this carrier safe for a scorer to consult, and each has a way of
failing quietly if it is not pinned:

  * the pair is DIRECTED -- a reversed lookup must miss, or the index would flag a
    precedence the measurement never claimed;
  * the join key is OPAQUE -- lookup is string equality, so a locator that merely resembles
    another must not match;
  * the sequence is CANONICAL -- an unsequenced index serializes differently on two runs,
    which is a determinism defect that no assertion about behaviour would catch.

Nothing here asserts a rate is *right*. Whether a derivation holds is module 1's
measurement; this file asserts only that the measurement survives the trip intact.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from causalog.core.precedence import (
    DerivedPrecedence,
    DerivedPrecedenceIndex,
    temporal_binding_source,
)

EARLIER = temporal_binding_source("column_a")
LATER = temporal_binding_source("column_b")


def _entry(
    cause: str = EARLIER,
    effect: str = LATER,
    check_id: str = "CHECK_ONE",
    agreement_rate: float = 0.9461,
    evaluated: int = 180519,
) -> DerivedPrecedence:
    """Return one measured entry, varying only what a test cares about."""
    return DerivedPrecedence(
        check_id=check_id,
        cause_interval_source=cause,
        effect_interval_source=effect,
        agreement_rate=agreement_rate,
        evaluated=evaluated,
        residual_seconds=((43200, 5080), (-43200, 4657)),
        rationale="the later instant is suspected of being computed from the earlier one",
    )


def test_the_locator_recipe_has_one_definition() -> None:
    """The helper is the recipe module 2 stamps onto every interval it binds."""
    assert temporal_binding_source("a column") == "mapping.temporal_bindings[a column]"


def test_a_declared_pair_is_found_in_the_direction_it_was_measured() -> None:
    """The measured direction hits."""
    index = DerivedPrecedenceIndex.of((_entry(),))

    found = index.precedence_for(EARLIER, LATER)

    assert found is not None
    assert found.check_id == "CHECK_ONE"
    assert found.agreement_rate == pytest.approx(0.9461)


def test_the_reverse_of_a_declared_pair_is_not_found() -> None:
    """A derivation claims one direction; the reverse is a different claim and must miss.

    Without this the index would depress confidence on precedence the source really did
    record, which is the opposite error from the one this feature corrects.
    """
    index = DerivedPrecedenceIndex.of((_entry(),))

    assert index.precedence_for(LATER, EARLIER) is None


def test_lookup_is_string_equality_and_never_a_partial_match() -> None:
    """A locator that CONTAINS a declared one is a different locator.

    This is the regression guard on the module's standing constraint: the day `precedence_for`
    starts splitting or matching prefixes is the day engine code begins reading the source
    description, which no vocabulary lint can see.
    """
    index = DerivedPrecedenceIndex.of((_entry(),))

    assert index.precedence_for(EARLIER, LATER + "_suffix") is None
    assert index.precedence_for(EARLIER[:-1], LATER) is None


def test_an_empty_index_answers_none_without_claiming_anything() -> None:
    """Supplied-and-empty is a legitimate state: measured, and nothing confirmed."""
    assert DerivedPrecedenceIndex().precedence_for(EARLIER, LATER) is None


def test_entries_are_sequenced_canonically_however_they_arrive() -> None:
    """`of()` sorts, so two runs that discover entries in different sequences serialize alike."""
    third = _entry(effect=temporal_binding_source("column_c"), check_id="CHECK_THREE")
    second = _entry(effect=temporal_binding_source("column_bb"), check_id="CHECK_TWO")

    forwards = DerivedPrecedenceIndex.of((_entry(), second, third))
    backwards = DerivedPrecedenceIndex.of((third, second, _entry()))

    assert forwards == backwards
    assert [entry.check_id for entry in forwards.entries] == [
        "CHECK_ONE",
        "CHECK_TWO",
        "CHECK_THREE",
    ]


def test_an_unsequenced_index_is_refused_rather_than_sorted() -> None:
    """Constructing around `of()` is a defect, not something to repair silently."""
    later_first = _entry(effect=temporal_binding_source("column_z"), check_id="CHECK_Z")

    with pytest.raises(ValidationError, match="canonical sequence"):
        DerivedPrecedenceIndex(entries=(later_first, _entry()))


def test_one_locator_pair_may_not_appear_twice() -> None:
    """Two entries for one pair have no defined answer, so the index refuses to hold them."""
    with pytest.raises(ValidationError, match="twice"):
        DerivedPrecedenceIndex.of((_entry(), _entry(check_id="CHECK_OTHER")))


def test_a_check_with_no_evaluable_rows_cannot_be_carried() -> None:
    """`evaluated == 0` yields a division-guard rate of zero, which is NOT a measurement.

    Admitting it would let "never tested" arrive downstream wearing the clothes of "tested
    and found false".
    """
    with pytest.raises(ValidationError):
        _entry(evaluated=0)


def test_a_locator_may_not_be_both_sides_of_the_pair() -> None:
    """An interval derived from itself is not a precedence claim."""
    with pytest.raises(ValidationError, match="both sides"):
        _entry(cause=LATER, effect=LATER)
