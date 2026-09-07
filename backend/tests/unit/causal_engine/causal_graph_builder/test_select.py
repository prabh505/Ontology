"""Selection, lineage and the rejection ledger.

The ledger is the half of this module a user actually interrogates: "what did you consider
and reject?" is a question about causal claims that a graph asserting only its winners
cannot answer. These tests hold it to that.
"""

from __future__ import annotations

import pytest

from causalog.causal_engine.causal_graph_builder import (
    DemotionReason,
    build_causal_graph,
    select,
)
from causalog.core.errors import ContractViolationError
from causalog.core.provenance import ProvenanceClass
from causalog.core.types import Event, Timeline
from causalog.core.types.causal_edge import ContributingCause
from causalog.rule_engine import CompetingEffectPolicy
from fixtures.candidates import envelope, linear_process
from fixtures.graphs import (
    build_context,
    candidate,
    graph_parameters,
    permissive_scoring,
    scored_graph,
)


def _converging(count: int = 3) -> tuple[tuple[Event, ...], tuple[Timeline, ...]]:
    """Return `count` causes over one shared effect, all cleanly ordered before it."""
    events = []
    timelines = []
    for index in range(count):
        _, produced, line = linear_process(
            f"STAGE_{index}", "STAGE_EFFECT", subject=chr(ord("A") + index)
        )
        events.extend(produced)
        timelines.append(line)
    return tuple(events), tuple(timelines)


def test_every_claim_is_either_asserted_or_accounted_for() -> None:
    """`promoted + demoted == considered`, enforced at construction, not by a report."""
    _, events, line = linear_process("STAGE_ONE", "STAGE_TWO", "STAGE_THREE", subject="A")
    candidates = (
        candidate(events[0], events[1]),
        candidate(events[1], events[2]),
        candidate(events[0], events[2]),
    )
    graph = scored_graph(candidates, events, (line,))
    context = build_context(events, (line,), candidates)
    promoted = select(graph, context)
    assert promoted.claims_considered == len(graph.edges)
    assert len(promoted.edges) + len(promoted.demotions) == promoted.claims_considered


def test_lineage_names_every_candidate_and_generator_behind_a_claim() -> None:
    """Two generators over one pair fuse to one claim whose lineage keeps both."""
    _, events, line = linear_process("STAGE_ONE", "STAGE_TWO", subject="A")
    candidates = (
        candidate(events[0], events[1], generator_id="alpha_generator"),
        candidate(events[0], events[1], generator_id="beta_generator"),
    )
    graph = scored_graph(candidates, events, (line,))
    assert len(graph.edges) == 1, "module 10 fuses parallel candidates over one pair"
    promoted = select(graph, build_context(events, (line,), candidates))
    lineage = (promoted.edges or promoted.demotions)[0].lineage
    assert lineage.generator_ids == ("alpha_generator", "beta_generator")
    assert len(lineage.candidate_edge_ids) == 2


def test_lineage_survives_demotion() -> None:
    """A rejected claim keeps its full trail, or a reader cannot tell a near miss from a void."""
    _, events, line = linear_process("STAGE_ONE", "STAGE_TWO", subject="A")
    candidates = (candidate(events[0], events[1]),)
    bands = permissive_scoring(strong_floor=0.99)
    graph = scored_graph(candidates, events, (line,), bands)
    promoted = select(graph, build_context(events, (line,), candidates, bands=bands))
    assert not promoted.edges
    record = promoted.demotions[0]
    assert record.reason is DemotionReason.BELOW_KIND_THRESHOLD
    assert record.lineage.candidate_edge_ids
    assert record.lineage.generator_ids


def test_retain_all_keeps_every_cause_of_one_effect() -> None:
    """Multiple causes are the normal case (prd.md §27), not a competition to resolve."""
    events, timelines = _converging(3)
    candidates = tuple(candidate(events[index * 2], events[index * 2 + 1]) for index in range(3))
    graph = scored_graph(candidates, events, timelines)
    context = build_context(events, timelines, candidates)
    promoted = select(graph, context)
    assert len(promoted.edges) == 3
    assert not promoted.demotions


def test_retain_top_n_demotes_the_losers_rather_than_dropping_them() -> None:
    """A loser becomes a ledger entry with `LOST_COMPETITION`; nothing disappears."""
    events, timelines = _converging(3)
    candidates = tuple(candidate(events[index * 2], events[index * 2 + 1]) for index in range(3))
    graph = scored_graph(candidates, events, timelines)
    context = build_context(
        events,
        timelines,
        candidates,
        graph_parameters(policy=CompetingEffectPolicy.RETAIN_TOP_N, retain=1),
    )
    promoted = select(graph, context)
    # All three converge on distinct effect events (one per subject), so the cap applies per
    # effect and each effect keeps its single cause. The assertion that matters is the
    # invariant: nothing was dropped.
    assert len(promoted.edges) + len(promoted.demotions) == promoted.claims_considered


def test_top_n_over_one_effect_keeps_exactly_n_and_ledgers_the_rest() -> None:
    """The competition is per effect, so a shared effect is where the cap actually bites."""
    _, first, line_a = linear_process("STAGE_ONE", "STAGE_EFFECT", subject="A")
    _, second, line_b = linear_process("STAGE_TWO", "STAGE_EFFECT", subject="B")
    effect = first[1]
    events = (*first, *second)
    candidates = (
        candidate(first[0], effect),
        candidate(second[0], effect),
    )
    graph = scored_graph(candidates, events, (line_a, line_b))
    assert len(graph.edges) == 2
    context = build_context(
        events,
        (line_a, line_b),
        candidates,
        graph_parameters(policy=CompetingEffectPolicy.RETAIN_TOP_N, retain=1),
    )
    promoted = select(graph, context)
    assert len(promoted.edges) == 1
    assert len(promoted.demotions) == 1
    assert promoted.demotions[0].reason is DemotionReason.LOST_COMPETITION


def test_a_joint_group_is_promoted_all_or_nothing() -> None:
    """Two of three contributors is not a partial answer; it is the wrong answer."""
    _, first, line_a = linear_process("STAGE_ONE", "STAGE_EFFECT", subject="A")
    _, second, line_b = linear_process("STAGE_TWO", "STAGE_EFFECT", subject="B")
    effect = first[1]
    events = (*first, *second)
    absent = "evt:0000000000000000"
    candidates = (
        candidate(
            first[0],
            effect,
            payload=ContributingCause(
                joint_cause_group_id="GROUP_ONE",
                co_cause_event_ids=tuple(sorted((second[0].event_id, absent))),
            ),
        ),
        candidate(
            second[0],
            effect,
            payload=ContributingCause(
                joint_cause_group_id="GROUP_ONE",
                co_cause_event_ids=tuple(sorted((first[0].event_id, absent))),
            ),
        ),
    )
    graph = scored_graph(candidates, events, (line_a, line_b))
    context = build_context(
        events, (line_a, line_b), candidates, graph_parameters(kinds=("CONTRIBUTING",))
    )
    promoted = select(graph, context)
    assert not promoted.edges, "a group with a member the graph does not hold is not promoted"
    assert {record.reason for record in promoted.demotions} == {
        DemotionReason.JOINT_GROUP_INCOMPLETE
    }
    assert len(promoted.joint_groups) == 1
    assert promoted.joint_groups[0].promoted is False
    assert "all or nothing" in promoted.joint_groups[0].detail


def test_a_complete_joint_group_is_promoted_whole() -> None:
    """The other half of the rule: every member present and clearing, so the group stands."""
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
    context = build_context(
        events, (line_a, line_b), candidates, graph_parameters(kinds=("CONTRIBUTING",))
    )
    promoted = select(graph, context)
    assert len(promoted.edges) == 2
    assert promoted.joint_groups[0].promoted is True
    assert all(edge.joint_cause_group_id == "GROUP_ONE" for edge in promoted.edges)


def test_the_graph_refuses_to_publish_totals_that_disagree_with_itself() -> None:
    """The arithmetic check is on the type, not in the builder, so no caller can bypass it."""
    from causalog.causal_engine.causal_graph_builder import PromotedGraph

    with pytest.raises(ContractViolationError, match="dropped silently"):
        PromotedGraph(
            run_id="run:test", edges=(), demotions=(), joint_groups=(), claims_considered=7
        )


def test_every_promoted_edge_carries_inferred_and_the_run() -> None:
    """The two properties that make the collection's name true."""
    _, events, line = linear_process("STAGE_ONE", "STAGE_TWO", subject="A")
    candidates = (candidate(events[0], events[1]),)
    graph = scored_graph(candidates, events, (line,))
    context = build_context(events, (line,), candidates)
    result = build_causal_graph(graph, context, envelope())
    assert result.graph.edges
    for edge in result.graph.edges:
        assert edge.edge.provenance_class is ProvenanceClass.INFERRED
        assert edge.edge.run_id == context.run_id
