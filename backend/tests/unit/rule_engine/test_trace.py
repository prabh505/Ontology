"""A firing carries its whole reasoning, or it does not exist (ADR-0047).

The task this module was built for states that a rule firing with no explanation is a
defect. These tests assert that "defect" is enforced by the type rather than by convention:
the untraced shapes cannot be CONSTRUCTED, so they cannot be persisted, scored or shown.
"""

from __future__ import annotations

import pytest

from causalog.core.errors import ContractViolationError
from causalog.core.temporal import TemporalVerdict
from causalog.rule_engine import evaluate
from causalog.rule_engine.dsl import ConditionOperator, KnowledgeProvenance, RuleKind
from causalog.rule_engine.trace import ConditionTraceEntry, RuleFiring
from tests.fixtures.rules import STAGE_ONE, pack, rule, two_stage_facts


def _firing(**overrides: object) -> RuleFiring:
    """Build a valid firing, with fields overridden."""
    document: dict[str, object] = {
        "rule_id": "R-ONE",
        "rule_kind": RuleKind.CAUSAL,
        "rule_pack_version": "1.0.0",
        "knowledge_provenance": KnowledgeProvenance.DOMAIN_EXPERTISE,
        "bindings": (("CAUSE", "evt:a"), ("EFFECT", "evt:b")),
        "matched_event_ids": ("evt:a", "evt:b"),
        "evaluated_conditions": (),
        "condition_was_trivial": True,
        "temporal_verdict": TemporalVerdict.CERTAIN,
        "temporally_unverifiable": False,
        "base_strength": 0.5,
    }
    document.update(overrides)
    return RuleFiring.model_validate(document)


def test_a_firing_with_a_condition_and_no_trace_cannot_be_constructed() -> None:
    """The central assertion of ADR-0047. This firing does not exist."""
    with pytest.raises(ContractViolationError, match="may not fire"):
        _firing(condition_was_trivial=False, evaluated_conditions=())


def test_a_firing_claiming_a_trivial_condition_while_carrying_a_trace_is_refused() -> None:
    """The two disagree, and a reader cannot tell which one is stale."""
    entry = ConditionTraceEntry(path="root", operator=ConditionOperator.ALWAYS, result=True)
    with pytest.raises(ContractViolationError, match="disagree"):
        _firing(condition_was_trivial=True, evaluated_conditions=(entry,))


def test_a_firing_with_no_bindings_is_refused() -> None:
    """Without bindings a reader cannot tell which participants the rule matched."""
    with pytest.raises(ContractViolationError, match="no bindings"):
        _firing(bindings=())


def test_a_firing_with_no_matched_events_is_refused() -> None:
    """A firing over nothing cites nothing and cannot be re-derived."""
    with pytest.raises(ContractViolationError, match="matched no event"):
        _firing(matched_event_ids=(), bindings=(("CAUSE", "evt:a"),))


def test_a_firing_carrying_a_violation_verdict_is_refused() -> None:
    """A pair LAW-TIME rejects is never emitted, so this verdict means a bypassed test."""
    with pytest.raises(ContractViolationError, match="VIOLATION"):
        _firing(temporal_verdict=TemporalVerdict.VIOLATION)


def test_unsequenced_bindings_are_refused() -> None:
    """`CONVENTIONS.md` §11: one firing has one canonical form."""
    with pytest.raises(ContractViolationError, match="unsequenced bindings"):
        _firing(bindings=(("EFFECT", "evt:b"), ("CAUSE", "evt:a")))


def test_a_repeated_binding_label_is_refused() -> None:
    """A trace that reads two ways is not a trace."""
    with pytest.raises(ContractViolationError, match="binds one label twice"):
        _firing(bindings=(("CAUSE", "evt:a"), ("CAUSE", "evt:b")))


def test_every_visited_condition_node_appears_in_the_trace() -> None:
    """No short-circuiting: an operand that did not change the outcome is still traced.

    A reader seeing three of five operands cannot tell whether the other two were false or
    were never looked at, which makes the trace uncheckable.
    """
    facts, _, _, _ = two_stage_facts()
    conditions = {
        "op": "AND",
        "operands": [
            {
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
                    {"op": "CONSTANT", "value": STAGE_ONE},
                ],
            },
            {
                "op": "IS_PRESENT",
                "operands": [
                    {
                        "op": "ATTRIBUTE",
                        "address": {
                            "binding": "EFFECT",
                            "role": "SUBJECT",
                            "attribute": "stage",
                        },
                    }
                ],
            },
        ],
    }
    result = evaluate(pack(rule(kind="CONDITIONAL", body={"conditions": conditions})), facts)

    assert len(result.firings) == 1
    trace = result.firings[0].evaluated_conditions
    operators = [entry.operator for entry in trace]
    assert ConditionOperator.EQUALS in operators
    assert ConditionOperator.IS_PRESENT in operators
    assert ConditionOperator.AND in operators
    assert all(entry.path for entry in trace), "a trace entry with no path cannot be located"


def test_a_trace_entry_records_the_value_the_condition_actually_read() -> None:
    """The value, not merely the verdict. A verdict with no value cannot be re-derived."""
    facts, _, _, _ = two_stage_facts()
    conditions = {
        "op": "IS_PRESENT",
        "operands": [
            {
                "op": "ATTRIBUTE",
                "address": {"binding": "CAUSE", "role": "SUBJECT", "attribute": "stage"},
            }
        ],
    }
    result = evaluate(pack(rule(kind="CONDITIONAL", body={"conditions": conditions})), facts)

    entry = result.firings[0].evaluated_conditions[0]
    assert entry.observed == STAGE_ONE
    assert entry.address == "CAUSE.SUBJECT.stage"
    assert entry.result is True


def test_an_absent_value_is_distinguishable_from_an_empty_one() -> None:
    """`observed is None` means absent; collapsing it would make IS_ABSENT untestable."""
    facts, _, _, _ = two_stage_facts()
    conditions = {
        "op": "IS_ABSENT",
        "operands": [
            {
                "op": "ATTRIBUTE",
                "address": {
                    "binding": "CAUSE",
                    "role": "SUBJECT",
                    "attribute": "never_recorded",
                },
            }
        ],
    }
    result = evaluate(pack(rule(kind="CONDITIONAL", body={"conditions": conditions})), facts)

    entry = result.firings[0].evaluated_conditions[0]
    assert entry.observed is None
    assert entry.result is True


def test_every_firing_the_evaluator_emits_can_explain_itself() -> None:
    """The property stated over the evaluator's whole output, not one construction."""
    facts, _, _, _ = two_stage_facts()
    conditions = {
        "op": "IS_PRESENT",
        "operands": [
            {
                "op": "ATTRIBUTE",
                "address": {"binding": "CAUSE", "role": "SUBJECT", "attribute": "stage"},
            }
        ],
    }
    result = evaluate(
        pack(rule(), rule("R-TWO", kind="CONDITIONAL", body={"conditions": conditions})),
        facts,
    )

    assert result.firings
    for firing in result.firings:
        assert firing.condition_was_trivial or firing.evaluated_conditions
        assert firing.bindings
        assert firing.matched_event_ids
        assert firing.explains()
