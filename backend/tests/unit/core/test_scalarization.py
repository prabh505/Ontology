"""The trade-off arithmetic, and the two different things it does with a missing objective.

`core.scalarization` deliberately treats absence one way in the scalar and another way on
the frontier, and the difference is the most likely thing for a later reader to "fix". These
tests pin both, with the reason in each docstring.
"""

from __future__ import annotations

import pytest

from causalog.core.errors import ContractViolationError
from causalog.core.scalarization import (
    DEFAULT_SCALARIZER,
    OBJECTIVES,
    SCALARIZERS,
    inverted_rank,
    pareto_front_v1,
    scalarize,
    weighted_desirability_v1,
)

WEIGHTS = {"benefit": 0.4, "confidence": 0.2, "cost": 0.25, "risk": 0.15}


def _score(**overrides: object) -> float | None:
    """Score a perfect candidate, with named inputs replaced."""
    fields: dict[str, object] = {
        "benefit": 10.0,
        "benefit_ceiling": 10.0,
        "cost_rank": 0,
        "cost_span": 5,
        "risk_rank": 0,
        "risk_span": 5,
        "belief_scalar": 1.0,
        "weights": WEIGHTS,
    }
    fields.update(overrides)
    return weighted_desirability_v1(**fields)  # type: ignore[arg-type]


def test_the_best_possible_candidate_scores_one() -> None:
    """The scale is anchored, so two rankings under two weightings are comparable."""
    assert _score() == 1.0


def test_doubling_every_weight_does_not_change_any_score() -> None:
    """The weighted sum is divided by the total weight.

    Without it a pack that doubled its weights would double every score and look like it
    had found better acts.
    """
    doubled = {name: value * 2 for name, value in WEIGHTS.items()}

    assert _score(weights=doubled) == _score()


def test_an_undeclared_risk_costs_exactly_the_risk_weight() -> None:
    """Module 10's `graph_connectivity` ruling: a missing component COSTS the score.

    Renormalizing the term away would rank a candidate whose risk nobody declared ABOVE one
    that declared a low risk honestly, which rewards the absent declaration.
    """
    scored = _score(risk_rank=None)

    assert scored is not None
    assert scored == pytest.approx(1.0 - WEIGHTS["risk"])


def test_an_unmeasurable_benefit_ranks_nowhere_rather_than_at_zero() -> None:
    """`core.ranking.Ranker`'s rule, restated here because it is easy to "fix" away.

    Zero would place an unmeasured candidate BELOW candidates that were measured and found
    small, which is a different claim from "this could not be measured".
    """
    assert _score(benefit=None) is None
    assert _score(benefit_ceiling=None) is None
    assert _score(benefit_ceiling=0.0) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [("belief_scalar", 1.5), ("belief_scalar", -0.1), ("cost_span", 0)],
)
def test_a_degenerate_input_is_refused_rather_than_clamped(field: str, value: float) -> None:
    """A belief beyond one amplifies the objective it was meant to temper."""
    with pytest.raises(ContractViolationError):
        _score(**{field: value})


def test_an_omitted_weight_is_refused_rather_than_read_as_zero() -> None:
    """An omitted weight is refused rather than quietly read as zero.

    The two mean the same thing to the arithmetic and completely different things to a
    reader of the pack that declared them, and only one of the two can be reviewed.
    """
    with pytest.raises(ContractViolationError):
        _score(weights={"benefit": 1.0, "cost": 1.0, "confidence": 1.0})


def test_weights_that_sum_to_zero_are_refused() -> None:
    """Every candidate would score identically and the sequencing would be arbitrary."""
    with pytest.raises(ContractViolationError):
        _score(weights=dict.fromkeys(OBJECTIVES, 0.0))


def test_a_negative_weight_is_refused() -> None:
    """It inverts one objective while the artifact still reports it as that objective."""
    with pytest.raises(ContractViolationError):
        _score(weights={**WEIGHTS, "cost": -1.0})


def test_the_frontier_excludes_an_unmeasured_point_rather_than_ranking_it_worst() -> None:
    """The one place absence is treated differently from the scalar, and why.

    A scalar is a preference, so scoring an unmeasured objective at its worst is a
    defensible pessimism. Frontier membership is a CLAIM -- "nothing beats this" -- and that
    claim cannot be made about a candidate whose coordinates are partly unmeasured.
    """
    front, excluded = pareto_front_v1([(1.0, 1.0), (0.5, 0.5), (1.0, 0.2), (None, 9.9)])

    assert front == (0,)
    assert excluded == (3,)


def test_domination_requires_being_at_least_as_good_everywhere() -> None:
    """Two points that each win on one axis are both on the frontier."""
    front, excluded = pareto_front_v1([(1.0, 0.0), (0.0, 1.0)])

    assert front == (0, 1)
    assert excluded == ()


def test_points_of_different_dimension_are_refused() -> None:
    """Domination between different-sized points compares two different trade-offs."""
    with pytest.raises(ContractViolationError):
        pareto_front_v1([(1.0, 1.0), (1.0,)])


def test_an_empty_frontier_is_empty_rather_than_an_error() -> None:
    """A run with no candidates is a run with no candidates."""
    assert pareto_front_v1([]) == ((), ())


def test_inverting_a_rank_re_points_it_without_going_negative() -> None:
    """Better-low becomes better-high by distance from the worst member, not by negation."""
    assert inverted_rank(0, 5) == 4.0
    assert inverted_rank(4, 5) == 0.0
    assert inverted_rank(None, 5) is None


def test_the_registry_is_named_and_the_default_is_a_member() -> None:
    """The name travels with the artifact so a reader can recompute and disagree."""
    assert DEFAULT_SCALARIZER in SCALARIZERS
    assert (
        scalarize(
            benefit=1.0,
            benefit_ceiling=1.0,
            cost_rank=0,
            cost_span=2,
            risk_rank=0,
            risk_span=2,
            belief_scalar=1.0,
            weights=WEIGHTS,
        )
        == 1.0
    )


def test_an_unregistered_scalarizer_is_refused_rather_than_defaulted() -> None:
    """Falling back would produce a ranking whose stated function did not produce it."""
    with pytest.raises(ContractViolationError):
        scalarize(
            benefit=1.0,
            benefit_ceiling=1.0,
            cost_rank=0,
            cost_span=2,
            risk_rank=0,
            risk_span=2,
            belief_scalar=1.0,
            weights=WEIGHTS,
            scalarizer_name="does_not_exist_v9",
        )
