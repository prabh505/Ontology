"""Two builds of one input are byte-identical (`CONVENTIONS.md` §11).

Following `test_confidence_is_stable.py`, one layer on. Determinism here is not an abstract
nicety: promotion is the engine's assertion, and an assertion that differs between two runs
over one dataset cannot be audited -- the claim a reader is disagreeing with is not the
claim that will be recomputed.

The dangerous non-determinism in this module is dictionary iteration: selection groups by
effect in a dict, weights are keyed in one, lineage and typings are indexed in two more, and
the loop detector walks an adjacency map. `PYTHONHASHSEED` is pinned in the Makefile for
exactly that reason, and this file is what would notice if a sort were dropped anyway.
"""

from __future__ import annotations

from causalog.causal_engine.causal_graph_builder import (
    GraphBuildResult,
    build_causal_graph,
    render_markdown,
)
from causalog.core.serialization import to_canonical_json
from fixtures.candidates import envelope, linear_process
from fixtures.graphs import build_context, candidate, scored_graph


def _run(reverse: bool) -> GraphBuildResult:
    """Build one fixed input, optionally handing the proposals over in reverse sequence."""
    events: list = []
    timelines: list = []
    for subject in ("A", "B", "C"):
        _, produced, line = linear_process("STAGE_ONE", "STAGE_TWO", "STAGE_THREE", subject=subject)
        events.extend(produced)
        timelines.append(line)
    facts, lines = tuple(events), tuple(timelines)

    proposals = []
    for index in range(0, len(facts), 3):
        proposals.append(candidate(facts[index], facts[index + 1]))
        proposals.append(candidate(facts[index + 1], facts[index + 2]))
        proposals.append(candidate(facts[index], facts[index + 2]))
    ordered = tuple(reversed(proposals)) if reverse else tuple(proposals)

    graph = scored_graph(ordered, facts, lines)
    context = build_context(facts, lines, ordered)
    return build_causal_graph(graph, context, envelope())


def test_two_builds_of_one_input_are_byte_identical() -> None:
    """The whole artifact, serialized canonically."""
    first, second = _run(reverse=False), _run(reverse=True)
    assert to_canonical_json(first.graph) == to_canonical_json(second.graph)


def test_the_rendered_report_is_byte_identical() -> None:
    """A report that differs between runs cannot be diffed to find what changed."""
    first, second = _run(reverse=False), _run(reverse=True)
    assert render_markdown(first.report) == render_markdown(second.report)


def test_loop_detection_is_byte_identical() -> None:
    """Circuit enumeration walks an adjacency map; its output must not depend on it."""
    first, second = _run(reverse=False), _run(reverse=True)
    assert to_canonical_json(first.loops) == to_canonical_json(second.loops)


def test_the_build_actually_produced_something() -> None:
    """Two empty artifacts are trivially identical, so emptiness is refused here."""
    result = _run(reverse=False)
    assert result.graph.claims_considered > 0
    assert result.graph.edges or result.graph.demotions
