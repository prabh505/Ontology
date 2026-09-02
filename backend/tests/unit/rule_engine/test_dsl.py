"""The DSL's refusals. Every one of them is a defect this schema exists to make impossible.

`CONVENTIONS.md` §14: one test per stated failure mode. These are the failure modes of
`causalog.rule_engine.dsl`, and each asserts the shape is REFUSED -- a schema that merely
documents a constraint has not enforced it.
"""

from __future__ import annotations

import pytest

from causalog.core.errors import ContractViolationError
from causalog.rule_engine.dsl import (
    AmplificationBody,
    ConditionExpression,
    ConditionOperator,
    InhibitionBody,
    Rule,
    RulePackSpec,
    TemporalWindow,
)
from tests.fixtures.rules import STAGE_ONE, STAGE_TWO, constraint, pack, rule


def test_there_is_no_escape_hatch_in_the_schema() -> None:
    """No field anywhere admits an expression string, a callable, or an import path.

    This is the load-bearing property of the whole seam (prd.md §46): a pack with an escape
    hatch is executable code. Asserted over the generated JSON Schema rather than by reading
    the models, so a field added later is caught without anyone remembering to update a list.
    """
    schema = RulePackSpec.model_json_schema()
    names: set[str] = set()

    def walk(node: object) -> None:
        """Collect every declared property name anywhere in the schema."""
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                names.update(str(key) for key in properties)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    assert names, "the schema declared no properties; this assertion checked nothing"
    # Matched per snake_case COMPONENT, not as a substring: `description` contains
    # "script" and is not an escape hatch, and a matcher that cried wolf about it would be
    # deleted within a week (the DEF-0001 lesson, applied to a test).
    forbidden = {"eval", "exec", "callable", "code", "script", "import", "plugin", "hook"}
    offending = sorted(name for name in names if forbidden & set(name.lower().split("_")))
    assert not offending, (
        f"the rule DSL declares field(s) {offending}, which could carry executable code. "
        "A pack that can carry code is the failure prd.md §46 forbids."
    )


def test_a_condition_operator_outside_the_closed_set_is_refused() -> None:
    """An unknown operator is refused, not passed through as an opaque string."""
    with pytest.raises(ValueError, match="op"):
        ConditionExpression.model_validate({"op": "REGEX_MATCH", "value": ".*"})


def test_a_comparison_over_a_junction_is_refused() -> None:
    """Nesting AND inside EQUALS has no defined truth value, so the shape cannot exist."""
    leaf = {
        "op": "ATTRIBUTE",
        "address": {"binding": "CAUSE", "role": "SUBJECT", "attribute": "stage"},
    }
    with pytest.raises(ContractViolationError, match="compares leaves only"):
        ConditionExpression.model_validate(
            {
                "op": "EQUALS",
                "operands": [leaf, {"op": "AND", "operands": [leaf, leaf]}],
            }
        )


def test_an_operator_carrying_a_field_it_ignores_is_refused() -> None:
    """A field the operator never reads makes a rule read differently from how it runs."""
    with pytest.raises(ContractViolationError, match="does not admit"):
        ConditionExpression.model_validate({"op": "ALWAYS", "value": "ignored"})


def test_an_empty_membership_set_is_refused() -> None:
    """`IN` over nothing is always false, which is a defect and not a strict rule."""
    with pytest.raises(ContractViolationError, match="empty"):
        ConditionExpression.model_validate(
            {
                "op": "IN",
                "values": [],
                "operands": [
                    {
                        "op": "ATTRIBUTE",
                        "address": {"binding": "CAUSE", "role": "SUBJECT", "attribute": "stage"},
                    }
                ],
            }
        )


def test_an_unsorted_membership_set_is_refused() -> None:
    """One membership set has one canonical form, so it has one hash (CONVENTIONS.md §11)."""
    with pytest.raises(ContractViolationError, match="sorted"):
        ConditionExpression.model_validate(
            {
                "op": "IN",
                "values": ["b", "a"],
                "operands": [
                    {
                        "op": "ATTRIBUTE",
                        "address": {"binding": "CAUSE", "role": "SUBJECT", "attribute": "stage"},
                    }
                ],
            }
        )


def test_an_assumption_with_no_basis_is_refused() -> None:
    """ADR-0045: an assumption nobody wrote down cannot be shown to a user."""
    with pytest.raises(ContractViolationError, match="empty evidence_basis"):
        Rule.model_validate(rule(knowledge_provenance="ASSUMPTION", evidence_basis="   "))


def test_a_conditional_rule_with_no_condition_is_refused() -> None:
    """prd.md §26's conditional cause IS the condition; one without is a mislabelled direct."""
    with pytest.raises(ContractViolationError, match="CONDITIONAL and carries no condition"):
        Rule.model_validate(rule(kind="CONDITIONAL"))


def test_a_disabled_rule_with_no_reason_is_refused() -> None:
    """A rule switched off for a reason nobody recorded is off for no reason anybody checks."""
    with pytest.raises(ContractViolationError, match="disabled_reason"):
        Rule.model_validate(rule(enabled=False))


def test_an_enabled_rule_carrying_a_disabled_reason_is_refused() -> None:
    """The two fields disagree, and a reader cannot tell which one is stale."""
    with pytest.raises(ContractViolationError, match="enabled and carries a disabled_reason"):
        Rule.model_validate(rule(disabled_reason="stale"))


def test_a_joint_rule_needs_at_least_two_contributors() -> None:
    """A joint cause with one member is a direct cause under another name."""
    with pytest.raises(ValueError, match="contributors"):
        Rule.model_validate(
            rule(
                kind="JOINT",
                replace_body={
                    "contributors": [{"binding": "ONE", "event_type": STAGE_ONE}],
                    "effect": {"binding": "EFFECT", "event_type": STAGE_TWO},
                    "window": {"minimum_seconds": 0, "maximum_seconds": 60},
                    "relation": {
                        "direction": "SHARED_PARTICIPANT",
                        "cause_role": "SUBJECT",
                        "effect_role": "SUBJECT",
                    },
                    "joint_cause_group_id": "GROUP",
                },
            )
        )


@pytest.mark.parametrize("multiplier", [1.0, 0.5, 0.0])
def test_an_amplification_multiplier_must_exceed_one(multiplier: float) -> None:
    """Matching the bound `core.types.causal_edge.AmplifyingCause` enforces."""
    with pytest.raises(ContractViolationError, match="strictly above 1.0"):
        AmplificationBody.model_validate(_modifier_body(multiplier))


@pytest.mark.parametrize("multiplier", [1.0, 1.5])
def test_an_inhibition_multiplier_must_be_below_one(multiplier: float) -> None:
    """Matching the bound `core.types.causal_edge.InhibitingCause` enforces."""
    with pytest.raises(ContractViolationError, match=r"\[0.0, 1.0\)"):
        InhibitionBody.model_validate(_modifier_body(multiplier))


def test_a_mislabelled_modifier_is_refused_by_kind_not_by_union_luck() -> None:
    """AMPLIFICATION and INHIBITION share a field set; the declared kind is authoritative.

    A plain union would resolve these by whichever multiplier bound happens to pass, which
    picks the right class for the wrong reason and accepts a rule labelled one thing and
    shaped like the other.
    """
    with pytest.raises(ContractViolationError, match="strictly above 1.0"):
        Rule.model_validate(rule(kind="AMPLIFICATION", replace_body=_modifier_body(0.4)))


def test_a_reversed_temporal_window_is_refused() -> None:
    """A window whose minimum exceeds its maximum admits no pair at all."""
    with pytest.raises(ContractViolationError, match="reversed"):
        TemporalWindow(minimum_seconds=100, maximum_seconds=10)


def test_a_single_instant_window_with_an_exclusive_end_is_refused() -> None:
    """It admits nothing, which is a defect rather than a very strict rule."""
    with pytest.raises(ContractViolationError, match="admits no pair"):
        TemporalWindow(minimum_seconds=10, maximum_seconds=10, maximum_inclusive=False)


def test_a_shared_participant_linkage_may_not_name_a_relationship_type() -> None:
    """There is no edge to name when two roles must resolve to one entity."""
    with pytest.raises(ContractViolationError, match="no edge to name"):
        Rule.model_validate(
            rule(
                body={
                    "relation": {
                        "direction": "SHARED_PARTICIPANT",
                        "cause_role": "SUBJECT",
                        "effect_role": "SUBJECT",
                        "relationship_type": "BELONGS_TO",
                    }
                }
            )
        )


def test_a_directed_linkage_must_name_a_relationship_type() -> None:
    """A directed traversal that names no edge cannot say what it traverses."""
    with pytest.raises(ContractViolationError, match="names no relationship_type"):
        Rule.model_validate(
            rule(
                body={
                    "relation": {
                        "direction": "FROM_TO",
                        "cause_role": "SUBJECT",
                        "effect_role": "SUBJECT",
                    }
                }
            )
        )


def test_a_constraint_states_exactly_one_prohibition() -> None:
    """Two prohibitions in one rule cannot be reported separately when one fires."""
    with pytest.raises(ContractViolationError, match="exactly one"):
        Rule.model_validate(
            constraint(body={"forbidden_state": "CLOSED", "forbidden_event_type": STAGE_TWO})
        )


def test_a_duplicate_rule_identifier_is_refused() -> None:
    """Every inferred edge records which rules fired; two rules under one id is ambiguous."""
    with pytest.raises(ContractViolationError, match="repeats rule identifier"):
        pack(rule("R-ONE"), rule("R-ONE", base_strength=0.9))


def test_an_unsorted_pack_is_canonicalized_rather_than_refused() -> None:
    """A pack groups its rules for a reader; the loader sorts them for the hash.

    Demanding a sorted file would force every pack into a sequence nobody can follow and
    would buy nothing -- the hash is taken over the model, not the file bytes.
    """
    built = pack(rule("R-ZULU"), rule("R-ALPHA"))
    assert [item.id for item in built.rules] == ["R-ALPHA", "R-ZULU"]


def test_a_typo_in_a_pack_key_is_a_hard_error_naming_the_key() -> None:
    """`extra=forbid` is the load-bearing half: an ignored key is a rule that lies."""
    with pytest.raises(ValueError, match="confidence_wieght"):
        Rule.model_validate({**rule(), "confidence_wieght": 0.5})


def test_condition_addresses_are_reported_in_traversal_sequence() -> None:
    """The loader checks every address a tree reads, so the tree must enumerate them all."""
    expression = ConditionExpression.model_validate(
        {
            "op": "AND",
            "operands": [
                {
                    "op": "IS_PRESENT",
                    "operands": [
                        {
                            "op": "ATTRIBUTE",
                            "address": {
                                "binding": "CAUSE",
                                "role": "SUBJECT",
                                "attribute": "stage",
                            },
                        }
                    ],
                },
                {
                    "op": "IS_ABSENT",
                    "operands": [
                        {
                            "op": "ATTRIBUTE",
                            "address": {
                                "binding": "EFFECT",
                                "role": "SUBJECT",
                                "attribute": "label",
                            },
                        }
                    ],
                },
            ],
        }
    )
    assert [address.rendered() for address in expression.addresses()] == [
        "CAUSE.SUBJECT.stage",
        "EFFECT.SUBJECT.label",
    ]
    assert expression.op is ConditionOperator.AND


def _modifier_body(multiplier: float) -> dict[str, object]:
    """Return a modifier body with the given multiplier."""
    return {
        "modifier": {"binding": "MODIFIER", "event_type": STAGE_ONE},
        "modifies": "R-ONE",
        "window": {"minimum_seconds": 0, "maximum_seconds": 60},
        "relation": {
            "direction": "SHARED_PARTICIPANT",
            "cause_role": "SUBJECT",
            "effect_role": "SUBJECT",
        },
        "magnitude_multiplier": multiplier,
    }
