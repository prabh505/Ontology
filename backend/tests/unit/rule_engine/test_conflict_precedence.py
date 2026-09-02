"""Constraints beat generators, and every suppression is reported (ADR-0047).

Two properties, and the second matters as much as the first. An absent edge is the one kind
of error this system cannot otherwise surface -- `docs/architecture.md` §8 carries it as the
second open risk. A suppression that is reported is one absence that is no longer silent.
"""

from __future__ import annotations

from causalog.rule_engine import evaluate
from tests.fixtures.rules import STAGE_THREE, constraint, pack, rule, two_stage_facts


def test_a_constraint_suppresses_the_generator_it_contradicts() -> None:
    """The precedence policy, stated once and asserted here.

    Not weighed, not averaged, not decided by the larger weight: a weight is a strength of
    belief about a claim and a constraint is a statement of impossibility, and comparing the
    two would make impossibility purchasable.
    """
    facts, _, _, _ = two_stage_facts(closed=True)
    result = evaluate(pack(rule(), constraint()), facts)

    assert (
        result.firings_of("R-ONE") == ()
    ), "the generator survived a constraint that forbids its consequent"


def test_the_suppression_is_reported_rather_than_silent() -> None:
    """The conflict is REPORTED, not resolved silently. Both rules are named."""
    facts, _, _, _ = two_stage_facts(closed=True)
    result = evaluate(pack(rule(), constraint()), facts)

    assert not result.conflicts.is_empty()
    finding = result.conflicts.findings[0]
    assert finding.suppressed_rule_id == "R-ONE"
    assert finding.constraint_rule_id == "C-ONE"
    assert finding.shared_bindings, "a conflict naming no bindings cannot be investigated"


def test_the_suppressed_firing_is_carried_whole_with_its_trace() -> None:
    """A reader deciding whether the constraint was right needs the firing's own reasoning.

    Summarizing it would force exactly the reconstruction the trace exists to save.
    """
    facts, _, _, _ = two_stage_facts(closed=True)
    result = evaluate(pack(rule(), constraint()), facts)

    suppressed = result.conflicts.findings[0].suppressed_firing
    assert suppressed.rule_id == "R-ONE"
    assert suppressed.matched_event_ids
    assert suppressed.explains()


def test_a_constraint_that_does_not_apply_suppresses_nothing() -> None:
    """The negative case: no state, no prohibition, no suppression, and an empty report."""
    facts, _, _, _ = two_stage_facts(closed=False)
    result = evaluate(pack(rule(), constraint()), facts)

    assert len(result.firings_of("R-ONE")) == 1
    assert result.conflicts.is_empty()


def test_a_constraint_forbidding_a_different_type_suppresses_nothing() -> None:
    """Precedence is scoped to the consequent type, not applied to every firing."""
    facts, _, _, _ = two_stage_facts(closed=True)
    unrelated = constraint(forbidden_event_type=STAGE_THREE)
    result = evaluate(pack(rule(), unrelated), facts)

    assert len(result.firings_of("R-ONE")) == 1
    assert result.conflicts.is_empty()


def test_the_constraint_itself_still_fires_and_carries_its_own_trace() -> None:
    """A constraint that fired is a rule that fired, and owes the same explanation."""
    facts, _, _, _ = two_stage_facts(closed=True)
    result = evaluate(pack(rule(), constraint()), facts)

    fired = result.firings_of("C-ONE")
    assert len(fired) == 1
    assert fired[0].bindings
    assert fired[0].condition_was_trivial or fired[0].evaluated_conditions


def test_an_empty_conflict_report_is_returned_rather_than_omitted() -> None:
    """An empty report is a finding, not an omission: no generator met a constraint."""
    facts, _, _, _ = two_stage_facts()
    result = evaluate(pack(rule()), facts)

    assert result.conflicts.is_empty()
    assert result.conflicts.suppressed_rule_ids() == ()
