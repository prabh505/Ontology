"""The complexity bound, proved by measurement rather than asserted in a docstring.

`causalog.rule_engine.index` claims evaluation is linear in the inputs plus the output and
never quadratic in the event count. A claim like that in a comment is worth nothing: the
naive `O(n^2)` implementation passes every correctness test in this directory and differs
only in how long it takes, which no functional assertion notices.

`EvaluationStatistics.pair_comparisons` is incremented at the single site where a
cause/consequent pair is examined, and is returned rather than logged. These tests read it.
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from causalog.core.temporal import Precision
from causalog.rule_engine import evaluate
from causalog.rule_engine.facts import FactSet
from tests.fixtures.facts import entity, evidence_record, interval
from tests.fixtures.facts import event as build_event
from tests.fixtures.rules import PARTICIPANT, STAGE_ONE, STAGE_TWO, pack, rule

#: Doubling the input must not quadruple the work. A quadratic scan grows by 4.0 between
#: successive doublings; a linear-plus-output one grows by about 2.0. The threshold sits
#: between them and well clear of both, so the test distinguishes the two implementations
#: without being brittle about constant factors.
MAXIMUM_GROWTH_RATIO = 3.0


def _facts(pair_count: int) -> FactSet:
    """Return `pair_count` independent (STAGE_ONE, STAGE_TWO) pairs, one subject each.

    Independent by construction: each pair has its own participant, so the linkage admits
    exactly one consequent per antecedent and the output grows linearly with the input. Any
    superlinear growth in `pair_comparisons` is therefore the evaluator scanning, not the
    fixture generating more matches.
    """
    citation = evidence_record("fixture/0001")
    events = []
    for index in range(pair_count):
        subject = entity(f"subject-{index:05d}", PARTICIPANT, citation=citation)
        events.append(
            build_event(
                STAGE_ONE,
                interval(index * 2, precision=Precision.DAY),
                citation=citation,
                participants=(subject,),
            )
        )
        events.append(
            build_event(
                STAGE_TWO,
                interval(index * 2 + 1, precision=Precision.DAY),
                citation=citation,
                participants=(subject,),
            )
        )
    return FactSet.of(events=tuple(events))


def _comparisons(pair_count: int) -> int:
    """Return the pair comparisons one evaluation performed over `pair_count` pairs."""
    narrow = rule(body={"window": {"minimum_seconds": 0, "maximum_seconds": 172800}})
    return evaluate(pack(narrow), _facts(pair_count)).statistics.pair_comparisons


@pytest.mark.parametrize("pair_count", [50, 100, 200, 400])
def test_the_fixture_produces_the_matches_it_claims_to(pair_count: int) -> None:
    """Guard the guard: a fixture that stopped matching would make the bound trivially true.

    Without this, an evaluator bug that emitted nothing would sail through the scaling
    assertion below -- zero comparisons grow perfectly linearly.
    """
    narrow = rule(body={"window": {"minimum_seconds": 0, "maximum_seconds": 172800}})
    result = evaluate(pack(narrow), _facts(pair_count))
    assert len(result.firings) == pair_count


def test_comparisons_do_not_grow_quadratically_with_the_event_count() -> None:
    """Doubling the events must not quadruple the comparisons.

    This is the assertion the indexing exists to satisfy. Against a naive nested scan the
    observed ratio is ~4.0 and this fails; against the bisected index it is ~2.0.
    """
    sizes = [50, 100, 200, 400]
    measured = {size: _comparisons(size) for size in sizes}

    assert all(
        count > 0 for count in measured.values()
    ), f"no pair was ever examined, so this measurement proves nothing: {measured}"

    for smaller, larger in pairwise(sizes):
        ratio = measured[larger] / measured[smaller]
        assert ratio < MAXIMUM_GROWTH_RATIO, (
            f"doubling {smaller} -> {larger} events multiplied pair comparisons by "
            f"{ratio:.2f}, at or above the quadratic signature. Measured: {measured}. "
            "The evaluator is scanning rather than indexing."
        )


def test_the_measurement_would_fail_against_a_quadratic_scan() -> None:
    """Prove the threshold discriminates, rather than passing whatever it is given.

    A test that cannot fail is not evidence (DEF-0001). This computes what a nested scan
    over the same fixture WOULD cost and asserts the same threshold rejects it -- so the
    bound above is known to be measuring something.
    """
    sizes = [50, 100, 200, 400]
    # A nested scan compares every antecedent against every consequent: n * n.
    quadratic = {size: size * size for size in sizes}

    ratios = [quadratic[larger] / quadratic[smaller] for smaller, larger in pairwise(sizes)]
    assert all(ratio >= MAXIMUM_GROWTH_RATIO for ratio in ratios), (
        f"the threshold {MAXIMUM_GROWTH_RATIO} does not reject a quadratic scan, so the "
        f"bound test above would pass against one. Quadratic ratios: {ratios}"
    )


def test_a_narrow_window_examines_fewer_pairs_than_a_wide_one() -> None:
    """The bisection is what makes the window cheap, not merely correct.

    A window applied after the fact would give identical firings and identical comparison
    counts. Different counts are the evidence that the cut happens before the comparison.
    """
    facts = _facts(200)
    narrow = rule(body={"window": {"minimum_seconds": 0, "maximum_seconds": 172800}})
    wide = rule(body={"window": {"minimum_seconds": 0, "maximum_seconds": 864000 * 400}})

    narrow_count = evaluate(pack(narrow), facts).statistics.pair_comparisons
    wide_count = evaluate(pack(wide), facts).statistics.pair_comparisons

    assert narrow_count < wide_count, (
        f"narrow and wide windows examined {narrow_count} and {wide_count} pairs; the "
        "window is being applied after the comparison rather than before it"
    )
