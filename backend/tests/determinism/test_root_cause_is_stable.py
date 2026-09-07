"""Two runs of one input produce one ranking and one rendered report, byte for byte.

The dangerous non-determinism in these two modules is dictionary iteration: every index --
forward adjacency, backward adjacency, per-depth tallies, per-type tallies, the consequence
set -- is built by accumulating into a dict and read back out. `PYTHONHASHSEED` is pinned in
the Makefile for exactly that reason, and every read is sorted so the pin is a safety net
rather than the mechanism.

The inputs are handed over in two different sequences, because a module that happened to
sort its output while reading its input in insertion sequence would pass a naive rerun test
and fail the moment a caller iterated a set.
"""

from __future__ import annotations

import pytest

from causalog.causal_engine.pattern_miner import StructuralPatternReport, mine_patterns
from causalog.causal_engine.pattern_miner import render_markdown as render_patterns
from causalog.causal_engine.propagation_analyzer import PropagationResult, analyze_propagation
from causalog.causal_engine.propagation_analyzer import render_markdown as render_propagation
from causalog.causal_engine.root_cause_analyzer import (
    RootCauseContext,
    RootCauseResult,
    analyze_root_causes,
)
from causalog.causal_engine.root_cause_analyzer import render_markdown as render_ranking
from causalog.core.serialization import to_canonical_json
from causalog.rule_engine import PatternMiningSpec
from fixtures.candidates import RUN_ID, envelope
from fixtures.propagation import (
    actionability,
    cost_classes,
    diamond_chain,
    promoted_graph,
    propagation_context,
    root_cause_parameters,
    severity_classes,
)

pytestmark = pytest.mark.determinism

PATTERN_PARAMETERS = PatternMiningSpec(
    motif_minimum_support=1, motif_maximum_length=4, bottleneck_minimum_degree=1
)


def _run(
    reverse: bool,
) -> tuple[RootCauseResult, PropagationResult, StructuralPatternReport]:
    """Build one fixed input, optionally handing the links over in reverse sequence."""
    events, lines = diamond_chain()
    origin, left, right, shared = events
    links = ((origin, left), (origin, right), (left, shared), (right, shared))
    graph = promoted_graph(events, lines, tuple(reversed(links)) if reverse else links)
    propagation = propagation_context(events, lines, graph)
    context = RootCauseContext(
        propagation=propagation,
        actionability=actionability(),
        cost_classes=cost_classes(),
        severity_classes=severity_classes(),
        parameters=root_cause_parameters(),
        run_id=RUN_ID,
    )
    return (
        analyze_root_causes(shared.event_id, context, envelope()),
        analyze_propagation(origin.event_id, propagation, envelope()),
        mine_patterns(propagation, PATTERN_PARAMETERS, envelope()),
    )


def test_two_rankings_of_one_input_are_byte_identical() -> None:
    """The artifact itself, through the one canonical serializer."""
    first, _, _ = _run(reverse=False)
    second, _, _ = _run(reverse=True)
    assert to_canonical_json(first.ranking) == to_canonical_json(second.ranking)


def test_two_propagation_trees_of_one_input_are_byte_identical() -> None:
    """Module 12's artifact, including its consequence set and its truncation records."""
    _, first, _ = _run(reverse=False)
    _, second, _ = _run(reverse=True)
    assert to_canonical_json(first.tree) == to_canonical_json(second.tree)


def test_two_pattern_reports_of_one_input_are_byte_identical() -> None:
    """The type projection is built from two dicts, so it is the likeliest to drift."""
    _, _, first = _run(reverse=False)
    _, _, second = _run(reverse=True)
    assert to_canonical_json(first) == to_canonical_json(second)


def test_the_rendered_markdown_is_byte_identical() -> None:
    """Render both reports twice and compare byte for byte.

    Prose is an artifact too: a report that resequenced its own tables between runs would
    make every committed report a spurious diff.
    """
    first_ranking, first_tree, first_patterns = _run(reverse=False)
    second_ranking, second_tree, second_patterns = _run(reverse=True)
    assert render_ranking(first_ranking.ranking, first_ranking.report) == render_ranking(
        second_ranking.ranking, second_ranking.report
    )
    assert render_propagation(first_tree.report) == render_propagation(second_tree.report)
    assert render_patterns(first_patterns) == render_patterns(second_patterns)


def test_the_run_actually_produced_something() -> None:
    """Two empty artifacts are trivially identical, so emptiness is refused here."""
    ranking, tree, patterns = _run(reverse=False)
    assert ranking.ranking.considered
    assert tree.tree.nodes
    assert patterns.motifs
    assert patterns.bottlenecks
