"""A consequence reachable two ways is one consequence, asserted against a hand constant.

The diamond is the shape that separates a correct attribution from a plausible one, and it
is the shape most likely to be got wrong by code that looks right: accumulate along paths
instead of over the reachable SET and a graph with parallel routes reports a total larger
than any quantity anyone measured, with no exception raised and no number obviously wrong.

The fixture plants:

    ORIGIN -> LEFT  -> SHARED
    ORIGIN -> RIGHT -> SHARED

with a magnitude on each of the three consequences. The two answers differ by exactly the
shared node's attributed share, and both are computed below from the fixture's own inputs
rather than typed in, so the test states the relationship rather than a magic number.

This file also pins the counterfactual's diamond behaviour, which is the same idea asked in
the other direction: removing ONE arm prevents nothing, because the shared consequence is
still reachable through the other. A subtraction would have said otherwise.
"""

from __future__ import annotations

from causalog.causal_engine.causal_graph_builder.graph import PromotedGraph
from causalog.causal_engine.propagation_analyzer import (
    PropagationContext,
    analyze_propagation,
    prevented_by_removing,
)
from causalog.core.types import Event
from fixtures.candidates import envelope
from fixtures.propagation import (
    diamond_chain,
    promoted_graph,
    propagation_context,
)

#: The three planted magnitudes. Named here so every expected figure below is derived from
#: them rather than written as a constant nobody can trace back to the fixture.
LEFT_MAGNITUDE = 3.0
RIGHT_MAGNITUDE = 5.0
SHARED_MAGNITUDE = 7.0


def _diamond() -> tuple[tuple[Event, ...], PromotedGraph, PropagationContext]:
    """Build the diamond, promote it for real, and return the events with a context."""
    events, lines = diamond_chain(
        left=LEFT_MAGNITUDE, right=RIGHT_MAGNITUDE, shared=SHARED_MAGNITUDE
    )
    origin, left, right, shared = events
    graph = promoted_graph(
        events, lines, ((origin, left), (origin, right), (left, shared), (right, shared))
    )
    return events, graph, propagation_context(events, lines, graph)


def test_the_fixture_actually_built_a_diamond() -> None:
    """Emptiness and a degenerate shape both satisfy the assertions below, so refuse them."""
    _, graph, context = _diamond()
    assert len(graph.edges) == 4
    tree = analyze_propagation(
        next(iter(graph.edges)).edge.source_event_id, context, envelope()
    ).tree
    assert tree.nodes


def test_the_shared_consequence_appears_exactly_once_in_the_set() -> None:
    """The membership guarantee, held by a type rather than by care at a call site."""
    events, _, context = _diamond()
    origin, _, _, shared = events
    tree = analyze_propagation(origin.event_id, context, envelope()).tree
    assert tree.consequences.event_ids.count(shared.event_id) == 1
    assert len(tree.consequences.event_ids) == 3
    assert len(set(tree.consequences.event_ids)) == 3


def test_the_shared_consequence_records_two_routes_and_is_still_counted_once() -> None:
    """`route_count` is structure. It is reported and it multiplies nothing."""
    events, _, context = _diamond()
    origin, _, _, shared = events
    tree = analyze_propagation(origin.event_id, context, envelope()).tree
    node = next(item for item in tree.nodes if item.event_id == shared.event_id)
    assert node.route_count == 2
    assert node.magnitude.reading == SHARED_MAGNITUDE
    # Two routes reach it and its magnitude is apportioned among the two claims arriving
    # there -- not doubled by the two routes.
    assert node.magnitude.attributed == SHARED_MAGNITUDE * node.magnitude.weight


def test_the_total_is_over_the_node_set_and_not_over_the_routes() -> None:
    """The headline assertion: set total, and the per-route total it is NOT.

    Both figures are derived from the tree's own nodes, so the test states the relationship
    between two ways of adding rather than pinning a constant that would have to be
    re-derived by hand whenever the fixture's magnitudes changed.
    """
    events, _, context = _diamond()
    origin, _, _, shared = events
    tree = analyze_propagation(origin.event_id, context, envelope()).tree
    per_node = sum(
        node.magnitude.attributed for node in tree.nodes if node.magnitude.attributed is not None
    )
    per_route = sum((node.magnitude.attributed or 0.0) * node.route_count for node in tree.nodes)
    shared_node = next(item for item in tree.nodes if item.event_id == shared.event_id)
    assert tree.consequences.combined == per_node
    # The two ways of adding differ by exactly the shared node's one extra route.
    assert per_route - per_node == shared_node.magnitude.attributed
    assert tree.consequences.combined != per_route


def test_removing_one_arm_of_the_diamond_prevents_nothing() -> None:
    """Counterfactual-lite by re-reachability. A subtraction would have said otherwise.

    The shared consequence is downstream of LEFT, so a naive "everything downstream of the
    candidate" answer would credit LEFT with preventing it. The graph says it still occurs,
    because RIGHT survives the removal and also reaches it.
    """
    events, _, context = _diamond()
    origin, left, _, _ = events
    prevented = prevented_by_removing(origin.event_id, (left.event_id,), context)
    assert prevented.prevented_count == 0
    assert prevented.prevented_total is None
    assert prevented.absent_because is not None
    assert "survives the removal" in prevented.absent_because


def test_removing_both_arms_prevents_the_shared_consequence_at_full_magnitude() -> None:
    """A joint removal deletes the group at once, not its members one at a time.

    Intersecting two single-member removals would keep the shared consequence, because it
    survives each of them separately. Removing both together is what the graph says the
    group's absence means.
    """
    events, _, context = _diamond()
    origin, left, right, shared = events
    prevented = prevented_by_removing(origin.event_id, (left.event_id, right.event_id), context)
    assert prevented.prevented_event_ids == (shared.event_id,)
    # Full magnitude, not the apportioned share: a consequence that stops occurring stops
    # occurring entirely rather than by its share of the causes claimed for it.
    assert prevented.prevented_total == SHARED_MAGNITUDE
