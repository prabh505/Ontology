"""The cut-set search, asserted against a shape whose answer is provable by inspection.

`CONVENTIONS.md` §14 requires a synthetic case with a known optimum for any search this
engine ships. `fixtures.recommendation.bottleneck_shape` is that case: every chain runs
through one node, so the optimal single act is that node and no arithmetic is needed to see
it. A test written against a shape whose answer had to be computed would be a restatement of
the implementation.
"""

from __future__ import annotations

import pytest

from causalog.recommendation_engine import (
    SearchRegime,
    chains_of,
    discover,
    find_cut_sets,
    optimize,
)
from fixtures.candidates import envelope
from fixtures.recommendation import (
    bottleneck_shape,
    recommendation_context,
    recommendation_parameters,
)
from fixtures.simulation import joint_cause_shape


def test_the_known_optimal_intervention_is_found_and_ranked_first() -> None:
    """One node lies on every chain, so it alone breaks them all and nothing else does.

    The assertion is on BOTH halves. That the optimum breaks everything is half the claim;
    that no single other node does is the half that would still pass if the search were
    returning its input unchanged.
    """
    events, graph, optimum = bottleneck_shape()
    context = recommendation_context(events, graph)
    found = discover(context)

    cut_sets, gap, _oversized = find_cut_sets(found.candidates, context)

    assert gap is None
    assert cut_sets, "a shape with four links and three actionable nodes yields cut sets"
    best = cut_sets[0]
    assert best.member_event_ids == (optimum,)
    assert best.chains_broken == best.chains_considered
    assert best.regime is SearchRegime.EXACT

    singletons = [item for item in cut_sets if len(item.member_event_ids) == 1]
    others = [item for item in singletons if item.member_event_ids != (optimum,)]
    assert others, "the shape has other single acts, or this asserts nothing"
    assert all(item.chains_broken < best.chains_broken for item in others)


def test_a_singleton_cut_set_is_not_described_as_a_set() -> None:
    """`is_set_because` is for memberships an operator could wrongly split. One cannot."""
    events, graph, optimum = bottleneck_shape()
    context = recommendation_context(events, graph)

    cut_sets, _, _oversized = find_cut_sets(discover(context).candidates, context)

    singleton = next(item for item in cut_sets if item.member_event_ids == (optimum,))
    assert singleton.is_set_because is None


def test_a_cut_set_touching_a_joint_group_contains_the_whole_group() -> None:
    """Removing one contributor of a conjunctive cause does not prevent the effect.

    ADR-0069. This is the property that makes a recommendation a SET rather than a list an
    operator may do part of, and it is asserted on membership rather than on a message: a
    set that named the requirement and shipped two of four members would pass a text check.
    """
    # The cap is raised to admit the whole group. At the fixture default of three a
    # four-member group is refused instead, which is the sibling test below.
    events, graph, members = joint_cause_shape(actionable=True)
    context = recommendation_context(
        events, graph, parameters=recommendation_parameters(size_cap=len(members))
    )

    cut_sets, _, _oversized = find_cut_sets(discover(context).candidates, context)

    assert cut_sets
    for cut_set in cut_sets:
        touching = set(cut_set.member_event_ids) & set(members)
        if touching:
            assert set(members) <= set(
                cut_set.member_event_ids
            ), "a cut set holding one member of a joint cause group must hold all of them"
            assert cut_set.is_set_because is not None
            assert "joint cause group" in cut_set.is_set_because


def test_a_greedy_search_says_it_did_not_prove_minimality() -> None:
    """Above the declared ceiling the label changes, and the label is the whole point.

    A greedy cover is often minimal. This module cannot say so, and ADR-0076 requires the
    difference between a proved claim and a plausible one to be visible on the artifact.
    """
    events, graph, _ = bottleneck_shape()
    context = recommendation_context(
        events, graph, parameters=recommendation_parameters(exact_ceiling=1)
    )

    cut_sets, _, _oversized = find_cut_sets(discover(context).candidates, context)

    assert cut_sets
    assert all(item.regime is SearchRegime.GREEDY_NOT_PROVEN_MINIMAL for item in cut_sets)
    for cut_set in cut_sets:
        assert cut_set.not_minimal_because is not None
        assert "cut_set_exact_ceiling" in cut_set.not_minimal_because


def test_an_undeclared_bound_yields_a_named_gap_and_no_search() -> None:
    """ADR-0049: absent means CANNOT RUN, and the gap names the declaration it needed."""
    events, graph, _ = bottleneck_shape()
    context = recommendation_context(
        events, graph, parameters=recommendation_parameters(exact_ceiling=None)
    )

    cut_sets, gap, _oversized = find_cut_sets(discover(context).candidates, context)

    assert cut_sets == ()
    assert gap is not None
    assert "cut_set_exact_ceiling" in gap

    published = optimize(context, envelope())
    assert any("cut_set_exact_ceiling" in entry for entry in published.policy_gaps)


def test_chains_are_counted_as_pairs_not_as_routes() -> None:
    """A node reaching one outcome by several routes contributes ONE chain.

    ADR-0061's ruling, in a new place. Counting routes would make a diamond look like twice
    the opportunity and would inflate every coverage figure on the artifact.
    """
    events, graph, _ = bottleneck_shape()
    context = recommendation_context(events, graph)

    pairs = chains_of(discover(context).candidates, context)

    assert len(pairs) == len(set(pairs))
    for source_event_id, outcome_event_id in pairs:
        assert source_event_id != outcome_event_id


@pytest.mark.parametrize("size_cap", [1, 2, 3])
def test_no_cut_set_exceeds_the_declared_size_cap(size_cap: int) -> None:
    """A set an operator cannot execute as one act is a project, not a recommendation."""
    events, graph, _ = bottleneck_shape()
    context = recommendation_context(
        events, graph, parameters=recommendation_parameters(size_cap=size_cap)
    )

    cut_sets, _, _oversized = find_cut_sets(discover(context).candidates, context)

    assert cut_sets
    assert all(len(item.member_event_ids) <= size_cap for item in cut_sets)


def test_a_joint_group_larger_than_the_size_cap_is_refused_by_name() -> None:
    """A declared bound that quietly does not hold is the worst kind of bound.

    Joint expansion is the only way a set can exceed `portfolio_size_cap`. Admitting it
    would leave an artifact that looks bounded and is not; truncating it to fit would ship
    an act that cannot work, because a partial joint cause buys nothing (ADR-0069). So the
    set is dropped and the refusal is named, which leaves a pack author the two real
    choices.
    """
    from fixtures.simulation import joint_cause_shape as shape

    events, graph, members = shape(actionable=True, members=4)
    context = recommendation_context(
        events, graph, parameters=recommendation_parameters(size_cap=2)
    )

    cut_sets, gap, oversized = find_cut_sets(discover(context).candidates, context)

    assert gap is None
    assert all(len(item.member_event_ids) <= 2 for item in cut_sets)
    assert len(oversized) == 1
    assert "portfolio_size_cap" in oversized[0]
    assert str(len(members)) in oversized[0]

    published = optimize(context, envelope())
    assert any("portfolio_size_cap" in entry for entry in published.policy_gaps)
