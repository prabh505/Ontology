"""The provenance algebra never increases certainty (ADR-0005, LAW-PROVENANCE).

`combine` is the one place mixed provenance is resolved. If it can ever return a class
stronger than one of its inputs, then an `ASSUMED` value can be laundered into an
`OBSERVED` one by being combined with something, and LAW-PROVENANCE's "never silently
promoted" becomes a convention rather than a property.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from causalog.core.errors import ContractViolationError
from causalog.core.provenance import (
    PROVENANCE_STRENGTH,
    WEAKEST_FIRST,
    ProvenanceClass,
    combine,
)
from tests.unit.core.strategies import provenance_classes

pytestmark = pytest.mark.property


@given(st.lists(provenance_classes(), min_size=1, max_size=5))
def test_the_result_is_never_stronger_than_any_input(
    classes: list[ProvenanceClass],
) -> None:
    """This is the whole law: combination never manufactures certainty."""
    result = combine(*classes)
    assert all(PROVENANCE_STRENGTH[result] <= PROVENANCE_STRENGTH[member] for member in classes)


@given(st.lists(provenance_classes(), min_size=1, max_size=5))
def test_the_result_is_one_of_the_inputs(classes: list[ProvenanceClass]) -> None:
    """Combination selects; it never invents a class nobody supplied."""
    assert combine(*classes) in classes


@given(provenance_classes(), provenance_classes())
def test_combination_is_commutative(left: ProvenanceClass, right: ProvenanceClass) -> None:
    """Argument sequence must not change the answer, or callers would have to care."""
    assert combine(left, right) == combine(right, left)


@given(provenance_classes(), provenance_classes(), provenance_classes())
def test_combination_is_associative(
    first: ProvenanceClass, second: ProvenanceClass, third: ProvenanceClass
) -> None:
    """Grouping must not change the answer: a pipeline folds these in an arbitrary shape."""
    assert combine(combine(first, second), third) == combine(first, combine(second, third))


@given(provenance_classes())
def test_combination_is_idempotent(member: ProvenanceClass) -> None:
    """Combining a class with itself is a no-op, so re-aggregation cannot drift."""
    assert combine(member, member) == member


@given(provenance_classes())
def test_combining_with_observed_never_strengthens_the_other_input(
    member: ProvenanceClass,
) -> None:
    """Combining with the strongest class never promotes the weaker one.

    The failure this guards is specific: OBSERVED is the strongest class, so a naive
    implementation that took the *first* or the *strongest* input would promote everything
    it touched.
    """
    assert combine(member, ProvenanceClass.OBSERVED) == member


def test_an_empty_combination_is_refused() -> None:
    """Returning OBSERVED for no inputs would mint the strongest class out of nothing."""
    with pytest.raises(ContractViolationError):
        combine()


def test_the_strength_ranking_covers_every_class_exactly_once() -> None:
    """A class missing from the ranking would raise KeyError deep inside an aggregation."""
    assert set(PROVENANCE_STRENGTH) == set(ProvenanceClass)
    assert len(set(PROVENANCE_STRENGTH.values())) == len(ProvenanceClass)
    assert WEAKEST_FIRST[-1] is ProvenanceClass.OBSERVED
