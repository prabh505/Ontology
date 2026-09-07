"""Edge typing against prd.md §26, and the two vocabularies staying in step."""

from __future__ import annotations

import pytest

from causalog.causal_engine.causal_graph_builder import (
    RULE_KIND_TO_EDGE_KIND,
    TypingBasis,
    TypingRecord,
    group_joint_causes,
    type_edge,
)
from causalog.core.errors import ContractViolationError
from causalog.core.types.causal_edge import CausalEdgeKind, ConditionalCause, ContributingCause
from causalog.rule_engine import RuleKind
from fixtures.candidates import linear_process
from fixtures.graphs import candidate, scored_graph


def test_the_rule_and_edge_vocabularies_mirror_each_other() -> None:
    """`RuleKind`'s docstring promises one vocabulary for §26, not two. Checked, not assumed.

    A member added to either enum without the other fails here, on the day it is written.
    `CONSTRAINT` is deliberately absent: it produces a prohibition rather than a claim, and
    mapping it to an edge kind would make impossibility rankable.
    """
    assert set(RULE_KIND_TO_EDGE_KIND) == set(RuleKind) - {RuleKind.CONSTRAINT}
    assert set(RULE_KIND_TO_EDGE_KIND.values()) == set(CausalEdgeKind)


def test_a_direct_edge_with_no_rule_is_typed_by_default_not_structurally() -> None:
    """`UNTYPED_DEFAULT` is evidence that nothing said otherwise, not evidence of directness."""
    _, events, line = linear_process("STAGE_ONE", "STAGE_TWO", subject="A")
    candidates = (candidate(events[0], events[1]),)
    graph = scored_graph(candidates, events, (line,))
    record = type_edge(graph.edges[0], None)
    assert record.basis is TypingBasis.UNTYPED_DEFAULT
    assert not record.supporting_rule_ids


def test_a_qualified_edge_with_no_rule_is_typed_structurally() -> None:
    """A CONDITIONAL payload is a structural claim even when no rule named the pair."""
    _, events, line = linear_process("STAGE_ONE", "STAGE_TWO", subject="A")
    candidates = (
        candidate(
            events[0],
            events[1],
            payload=ConditionalCause(
                condition_expression="FIXTURE == 'value'", condition_holds=True
            ),
        ),
    )
    graph = scored_graph(candidates, events, (line,))
    record = type_edge(graph.edges[0], None)
    assert record.basis is TypingBasis.STRUCTURAL


def test_a_typing_record_claiming_a_rule_basis_must_name_a_rule() -> None:
    """A basis nobody can look up is not a basis."""
    with pytest.raises(ContractViolationError, match="names no rule"):
        TypingRecord(edge_kind="DIRECT", basis=TypingBasis.RULE_DECLARED)


def test_a_structural_typing_may_not_cite_rules() -> None:
    """Citing a rule that did not establish the kind would misattribute the authority."""
    with pytest.raises(ContractViolationError, match="must not be cited"):
        TypingRecord(
            edge_kind="DIRECT",
            basis=TypingBasis.STRUCTURAL,
            supporting_rule_ids=("R-FIXTURE-1",),
        )


def test_a_joint_group_is_assembled_from_its_payloads() -> None:
    """The group, not N independent edges, is what intervention analysis later needs."""
    _, first, line_a = linear_process("STAGE_ONE", "STAGE_EFFECT", subject="A")
    _, second, line_b = linear_process("STAGE_TWO", "STAGE_EFFECT", subject="B")
    effect = first[1]
    events = (*first, *second)
    candidates = (
        candidate(
            first[0],
            effect,
            payload=ContributingCause(
                joint_cause_group_id="GROUP_ONE", co_cause_event_ids=(second[0].event_id,)
            ),
        ),
        candidate(
            second[0],
            effect,
            payload=ContributingCause(
                joint_cause_group_id="GROUP_ONE", co_cause_event_ids=(first[0].event_id,)
            ),
        ),
    )
    graph = scored_graph(candidates, events, (line_a, line_b))
    groups = group_joint_causes(graph.edges)
    assert len(groups) == 1
    assert groups[0].joint_cause_group_id == "GROUP_ONE"
    assert groups[0].member_source_event_ids == tuple(
        sorted((first[0].event_id, second[0].event_id))
    )
    assert groups[0].promoted is False, "membership is assembled here; the decision is not"


def test_a_group_declaring_an_absent_co_cause_says_so() -> None:
    """A group whose declared membership exceeds the graph is the case promotion must refuse."""
    _, events, line = linear_process("STAGE_ONE", "STAGE_EFFECT", subject="A")
    absent = "evt:0000000000000000"
    candidates = (
        candidate(
            events[0],
            events[1],
            payload=ContributingCause(
                joint_cause_group_id="GROUP_ONE", co_cause_event_ids=(absent,)
            ),
        ),
    )
    graph = scored_graph(candidates, events, (line,))
    groups = group_joint_causes(graph.edges)
    assert absent in groups[0].member_source_event_ids
    assert "Absent" in groups[0].detail
