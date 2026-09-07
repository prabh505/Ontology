"""Path composition: monotone along a path, named on the artifact, and refusing nonsense.

The monotonicity property is the load-bearing one and is asserted over generated inputs
rather than over examples, for the reason `strategies.py` gives about the rest of the core:
a composition that could RISE as a chain lengthens would let the engine claim more
confidence about a longer inferential leap than about a shorter one, and an example-based
test would only find that on the examples somebody thought of.

It is asserted for **every registered composer**, not just the default, so a composer added
later is held to the same property by a test that already exists.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from causalog.core.composition import (
    DEFAULT_COMPOSER,
    PATH_COMPOSERS,
    compose,
    independent_product_v1,
    weakest_link_v1,
)
from causalog.core.errors import ContractViolationError
from tests.unit.core.strategies import quantized_unit_floats

pytestmark = pytest.mark.property

#: Every registered name, so a composer added later is covered by these tests on the day it
#: is registered rather than on the day somebody remembers to add a case.
COMPOSER_NAMES = sorted(PATH_COMPOSERS)


def _link_values(min_size: int = 1, max_size: int = 12) -> st.SearchStrategy[list[float]]:
    """Generate a path's per-link scalars, already quantized as every artifact must be."""
    return st.lists(quantized_unit_floats(), min_size=min_size, max_size=max_size)


@pytest.mark.parametrize("name", COMPOSER_NAMES)
@given(values=_link_values(), extra=quantized_unit_floats())
def test_composition_is_monotonically_non_increasing_along_a_path(
    name: str, values: list[float], extra: float
) -> None:
    """Extending a path may never raise its composed confidence.

    The property the `PathComposer` protocol declares and the reason any composer is
    admissible at all. Asserted at a tolerance of one quantum, because both registered
    composers quantize their result and a comparison at exact equality would fail on the
    rounding rather than on the property.
    """
    before = compose(values, name)
    after = compose([*values, extra], name)
    assert after <= before + 1e-6


@pytest.mark.parametrize("name", COMPOSER_NAMES)
@given(values=_link_values())
def test_every_composition_stays_inside_the_unit_interval(name: str, values: list[float]) -> None:
    """A composed value outside [0, 1] would break every consumer's own range invariant."""
    composed = compose(values, name)
    assert 0.0 <= composed <= 1.0


@given(values=_link_values())
def test_the_weakest_link_is_the_minimum_and_is_idempotent(values: list[float]) -> None:
    """Assert the weakest-link claim literally: the composition IS the minimum.

    Idempotence is the half worth pinning: extending a path by a link at least as strong as
    the current minimum changes nothing, which is what the sentence actually claims and is
    what separates the minimum from every averaging rule.
    """
    composed = weakest_link_v1(values)
    assert composed == pytest.approx(min(values), abs=1e-6)
    assert weakest_link_v1([*values, composed]) == pytest.approx(composed, abs=1e-6)


@given(values=_link_values(min_size=2))
def test_the_product_is_never_stronger_than_the_weakest_link(values: list[float]) -> None:
    """The two registered composers are reported side by side, so their relation is pinned.

    Not an argument that one is better: the product is registered precisely so a reader who
    wants length sensitivity can have it. This pins that the two never cross, so a report
    printing both never shows the alternative above the headline.
    """
    assert independent_product_v1(values) <= weakest_link_v1(values) + 1e-6


def test_the_default_is_the_weakest_link() -> None:
    """Pinned, because changing it silently would reinterpret every report's headline."""
    assert DEFAULT_COMPOSER == "weakest_link_v1"
    assert PATH_COMPOSERS[DEFAULT_COMPOSER] is weakest_link_v1


def test_an_empty_path_is_refused_rather_than_composed_to_zero() -> None:
    """A path with no links is not a path, and zero would report an absence as a value."""
    with pytest.raises(ContractViolationError, match="at least one link"):
        compose([])


def test_a_value_outside_the_unit_interval_is_refused() -> None:
    """Every composer's monotonicity guarantee rests on the range, so it is checked."""
    with pytest.raises(ContractViolationError, match=r"outside \[0.0, 1.0\]"):
        compose([0.5, 1.5])


def test_an_unregistered_composer_is_refused_rather_than_defaulted() -> None:
    """A silent substitution would leave the artifact naming a function it did not use."""
    with pytest.raises(ContractViolationError, match="unknown composer"):
        compose([0.5], "geometric_mean_v1")


def test_every_registered_composer_agrees_with_its_registry_entry() -> None:
    """`compose` must dispatch to the function the name maps to, or the name is a label.

    The whole contract is that the name travels with the data and lets a consumer recompute.
    A dispatch that ignored the registry would make every recorded name unverifiable.
    """
    values = [0.9, 0.4, 0.7]
    for name, function in PATH_COMPOSERS.items():
        assert compose(values, name) == function(values)
