"""Evaluation: a positive and a negative case for every rule kind, and the window edges.

`CONVENTIONS.md` §14 forbids asserting that a causal conclusion is CORRECT -- there is no
ground truth for causality in this dataset. Every assertion here is structural: did the rule
match what it declared it would match, did it refuse what it declared it would refuse, and
does the firing carry what a reader needs.
"""

from __future__ import annotations

import pytest

from causalog.core.temporal import TemporalVerdict
from causalog.rule_engine import evaluate
from tests.fixtures.rules import (
    STAGE_ONE,
    STAGE_THREE,
    STAGE_TWO,
    constraint,
    pack,
    rule,
    two_stage_facts,
)

# ---------------------------------------------------------------------------
# CAUSAL
# ---------------------------------------------------------------------------


def test_a_causal_rule_fires_on_a_matching_pair() -> None:
    """The positive case: two events, the declared types, inside the window, one subject."""
    facts, first, second, _ = two_stage_facts(cause_day=0, effect_day=2)
    result = evaluate(pack(rule()), facts)

    assert len(result.firings) == 1
    firing = result.firings[0]
    assert firing.rule_id == "R-ONE"
    assert firing.matched_event_ids == tuple(sorted((first.event_id, second.event_id)))
    assert firing.temporal_verdict is TemporalVerdict.CERTAIN


def test_a_causal_rule_does_not_fire_when_the_participants_differ() -> None:
    """The negative case for the linkage: no shared entity, no candidate pair."""
    facts, _, _, _ = two_stage_facts(shared=False)
    result = evaluate(pack(rule()), facts)

    assert result.firings == ()
    assert (
        result.statistics.pair_comparisons > 0
    ), "the pair was never examined, so this test proves nothing about the linkage"


def test_a_causal_rule_does_not_fire_when_the_consequent_type_is_absent() -> None:
    """A rule whose consequent nothing witnesses produces nothing, and does not raise."""
    facts, _, _, _ = two_stage_facts()
    changed = rule(body={"effect": {"binding": "EFFECT", "event_type": STAGE_THREE}})
    assert evaluate(pack(changed), facts).firings == ()


# ---------------------------------------------------------------------------
# Temporal windows and LAW-TIME
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("maximum_seconds", "inclusive", "should_fire"),
    [
        (172800, True, True),  # exactly two days, inclusive -- admitted
        (172800, False, False),  # exactly two days, exclusive -- refused
        (172799, True, False),  # one second short -- refused
        (172801, True, True),  # one second over -- admitted
    ],
)
def test_the_upper_window_boundary_is_data(
    maximum_seconds: int, inclusive: bool, should_fire: bool
) -> None:
    """`inclusive` is carried per end, so "within 2 days" and "under 2 days" differ.

    Exercised at the exact boundary in both directions: a window test asserted only well
    inside its bounds would pass against an off-by-one comparison.
    """
    facts, _, _, _ = two_stage_facts(cause_day=0, effect_day=2)
    changed = rule(
        body={
            "window": {
                "minimum_seconds": 0,
                "maximum_seconds": maximum_seconds,
                "maximum_inclusive": inclusive,
            }
        }
    )
    assert bool(evaluate(pack(changed), facts).firings) is should_fire


@pytest.mark.parametrize(
    ("minimum_seconds", "inclusive", "should_fire"),
    [
        (172800, True, True),
        (172800, False, False),
    ],
)
def test_the_lower_window_boundary_is_data(
    minimum_seconds: int, inclusive: bool, should_fire: bool
) -> None:
    """The same assertion at the other end of the window."""
    facts, _, _, _ = two_stage_facts(cause_day=0, effect_day=2)
    changed = rule(
        body={
            "window": {
                "minimum_seconds": minimum_seconds,
                "maximum_seconds": 864000,
                "minimum_inclusive": inclusive,
            }
        }
    )
    assert bool(evaluate(pack(changed), facts).firings) is should_fire


def test_a_reversed_pair_is_refused_and_counted_never_emitted() -> None:
    """LAW-TIME: `cause.t_earliest >= effect.t_latest` is a VIOLATION and never created."""
    facts, _, _, _ = two_stage_facts(cause_day=5, effect_day=0)
    result = evaluate(pack(rule()), facts)

    assert result.firings == ()
    assert result.statistics.temporal_violations_refused == 1, (
        "the violation was not counted; a refused pair that is not reported looks "
        "identical to a pair that never existed"
    )


def test_an_overlapping_pair_is_retained_and_flagged_never_dropped() -> None:
    """`UNDETERMINED` is kept and reported (ADR-0007, R-14), never tuned away.

    A day-granularity dataset produces these constantly. Dropping them would silently shrink
    the graph; admitting them as CERTAIN would manufacture precedence the source never
    recorded. The third option is to keep them and say so.
    """
    facts, _, _, _ = two_stage_facts(cause_day=0, effect_day=1, span_days=5)
    result = evaluate(pack(rule()), facts)

    assert len(result.firings) == 1
    assert result.firings[0].temporal_verdict is TemporalVerdict.UNDETERMINED
    assert result.statistics.undetermined_firings == 1


# ---------------------------------------------------------------------------
# CONDITIONAL
# ---------------------------------------------------------------------------


def _conditional(value: str) -> dict[str, object]:
    """Return a CONDITIONAL rule comparing the cause's `stage` attribute to `value`."""
    return rule(
        kind="CONDITIONAL",
        body={
            "conditions": {
                "op": "EQUALS",
                "operands": [
                    {
                        "op": "ATTRIBUTE",
                        "address": {
                            "binding": "CAUSE",
                            "role": "SUBJECT",
                            "attribute": "stage",
                        },
                    },
                    {"op": "CONSTANT", "value": value},
                ],
            }
        },
    )


def test_a_conditional_rule_fires_when_its_condition_holds() -> None:
    """The positive case, and the condition's evaluated value reaches the trace."""
    facts, _, _, _ = two_stage_facts()
    result = evaluate(pack(_conditional(STAGE_ONE)), facts)

    assert len(result.firings) == 1
    firing = result.firings[0]
    assert firing.condition_was_trivial is False
    assert firing.evaluated_conditions[0].result is True


def test_a_conditional_rule_does_not_fire_when_its_condition_fails() -> None:
    """The negative case. The condition is data, so changing it changes the outcome."""
    facts, _, _, _ = two_stage_facts()
    assert evaluate(pack(_conditional("SOMETHING_ELSE")), facts).firings == ()


def test_an_absent_attribute_makes_every_comparison_false() -> None:
    """Including NOT_EQUALS: a claim about a value nobody recorded is not supported.

    The conservative reading, and the deliberate one. `IS_ABSENT` is what tests for absence.
    """
    facts, _, _, _ = two_stage_facts()
    changed = rule(
        kind="CONDITIONAL",
        body={
            "conditions": {
                "op": "NOT_EQUALS",
                "operands": [
                    {
                        "op": "ATTRIBUTE",
                        "address": {
                            "binding": "CAUSE",
                            "role": "SUBJECT",
                            "attribute": "never_recorded",
                        },
                    },
                    {"op": "CONSTANT", "value": "anything"},
                ],
            }
        },
    )
    assert evaluate(pack(changed), facts).firings == ()


# ---------------------------------------------------------------------------
# JOINT
# ---------------------------------------------------------------------------


def _joint(*contributor_types: str) -> dict[str, object]:
    """Return a JOINT rule over the given contributor event types."""
    return rule(
        kind="JOINT",
        replace_body={
            "contributors": [
                {"binding": f"C{position}", "event_type": name}
                for position, name in enumerate(contributor_types)
            ],
            "effect": {"binding": "EFFECT", "event_type": STAGE_TWO},
            "window": {"minimum_seconds": 0, "maximum_seconds": 864000},
            "relation": {
                "direction": "SHARED_PARTICIPANT",
                "cause_role": "SUBJECT",
                "effect_role": "SUBJECT",
            },
            "joint_cause_group_id": "GROUP_ONE",
        },
    )


def test_a_joint_rule_fires_only_when_every_contributor_is_present() -> None:
    """Conjunctive: one contributor present out of two produces nothing.

    Emitting a partial group would turn a joint claim into a set of weak direct ones nobody
    authored, which is the opposite of what prd.md §26's contributing cause means.
    """
    facts, _, _, _ = two_stage_facts()

    both_present = evaluate(pack(_joint(STAGE_ONE, STAGE_ONE)), facts)
    assert len(both_present.firings) == 1

    one_missing = evaluate(pack(_joint(STAGE_ONE, STAGE_THREE)), facts)
    assert one_missing.firings == ()


# ---------------------------------------------------------------------------
# AMPLIFICATION / INHIBITION
# ---------------------------------------------------------------------------


def _modifier(
    kind: str, multiplier: float, *, condition: dict[str, object] | None = None
) -> dict[str, object]:
    """Return a modifier rule targeting `R-ONE`."""
    body: dict[str, object] = {
        "modifier": {"binding": "MODIFIER", "event_type": STAGE_ONE},
        "modifies": "R-ONE",
        "window": {"minimum_seconds": 0, "maximum_seconds": 864000},
        "relation": {
            "direction": "SHARED_PARTICIPANT",
            "cause_role": "SUBJECT",
            "effect_role": "SUBJECT",
        },
        "magnitude_multiplier": multiplier,
    }
    if condition is not None:
        body["conditions"] = condition
    return rule("M-ONE", kind=kind, replace_body=body)


def test_a_modifier_fires_and_carries_its_target_and_multiplier() -> None:
    """A modifier proposes no edge; it says which claim it rescales, and by how much."""
    facts, first, _, _ = two_stage_facts()
    result = evaluate(pack(rule(), _modifier("AMPLIFICATION", 1.4)), facts)

    modifier_firings = result.firings_of("M-ONE")
    assert len(modifier_firings) == 1
    assert modifier_firings[0].modifies_rule_id == "R-ONE"
    assert modifier_firings[0].magnitude_multiplier == pytest.approx(1.4)
    assert modifier_firings[0].matched_event_ids == (first.event_id,)


def test_a_modifier_does_not_fire_when_its_condition_fails() -> None:
    """The negative case, and the inhibition bound at the same time."""
    facts, _, _, _ = two_stage_facts()
    condition = {
        "op": "EQUALS",
        "operands": [
            {
                "op": "ATTRIBUTE",
                "address": {"binding": "MODIFIER", "role": "SUBJECT", "attribute": "stage"},
            },
            {"op": "CONSTANT", "value": "NOT_THE_STAGE"},
        ],
    }
    result = evaluate(pack(rule(), _modifier("INHIBITION", 0.6, condition=condition)), facts)
    assert result.firings_of("M-ONE") == ()


# ---------------------------------------------------------------------------
# CONSTRAINT
# ---------------------------------------------------------------------------


def test_a_constraint_fires_on_the_state_it_names() -> None:
    """The positive case: the subject is in the named state, so the prohibition applies."""
    facts, _, _, _ = two_stage_facts(closed=True)
    result = evaluate(pack(constraint()), facts)

    assert len(result.firings_of("C-ONE")) == 1


def test_a_constraint_does_not_fire_when_the_state_does_not_hold() -> None:
    """The negative case. A constraint over a state nothing reaches prunes nothing."""
    facts, _, _, _ = two_stage_facts(closed=False)
    assert evaluate(pack(constraint()), facts).firings_of("C-ONE") == ()


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def test_a_disabled_rule_is_never_evaluated() -> None:
    """A disabled rule keeps its identifier and produces nothing."""
    facts, _, _, _ = two_stage_facts()
    disabled = rule(enabled=False, disabled_reason="retired for this test")
    result = evaluate(pack(disabled), facts)

    assert result.firings == ()
    assert result.statistics.rules_evaluated == 0


def test_statistics_report_what_the_evaluation_actually_did() -> None:
    """The counters are returned, not logged, so a claim about cost can be checked."""
    facts, _, _, _ = two_stage_facts()
    statistics = evaluate(pack(rule()), facts).statistics

    assert statistics.events_examined == 2
    assert statistics.rules_evaluated == 1
    assert statistics.firings_emitted == 1
    assert statistics.conditions_evaluated >= 1


def test_an_overlapping_pair_that_starts_earlier_is_retained() -> None:
    """Regression: the indexing prefilter must not drop an admissible overlapping pair.

    A consequent that STARTS before the antecedent but ENDS after it overlaps, so its
    verdict is `UNDETERMINED` and it must be kept and flagged. A first version of
    `FactIndex.admissible_slice` bisected on `t_earliest` and dropped it silently -- the
    "silently shrinking the graph" failure `CONTEXT.md` R-14 exists to prevent, hidden
    inside a performance optimization. This test fails against that version.
    """
    facts, _, _, _ = two_stage_facts(cause_day=5, effect_day=0, span_days=10)
    result = evaluate(
        pack(rule(body={"window": {"minimum_seconds": 0, "maximum_seconds": 2592000}})), facts
    )

    assert (
        len(result.firings) == 1
    ), "an overlapping pair was dropped rather than retained and flagged"
    assert result.firings[0].temporal_verdict is TemporalVerdict.UNDETERMINED


def test_the_violation_count_is_exact_not_a_sample() -> None:
    """Every pair the LAW-TIME cut removes is counted, including ones never examined."""
    facts, _, _, _ = two_stage_facts(cause_day=5, effect_day=0)
    result = evaluate(pack(rule()), facts)

    assert result.firings == ()
    assert result.statistics.temporal_violations_refused == 1
