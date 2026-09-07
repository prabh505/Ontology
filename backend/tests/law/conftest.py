"""Fixtures shared by the law tests that need a real ranking to attack."""

from __future__ import annotations

import pytest

from causalog.causal_engine.root_cause_analyzer import (
    RootCauseContext,
    RootCauseRanking,
    analyze_root_causes,
)
from fixtures.candidates import RUN_ID, envelope
from fixtures.propagation import (
    actionability,
    cost_classes,
    promoted_graph,
    propagation_context,
    root_cause_parameters,
    severity_classes,
    storm_shaped_chain,
)


@pytest.fixture
def storm_ranking() -> RootCauseRanking:
    """Return a real ranking over the planted three-node chain.

    Built by running the modules rather than by hand: a hand-assembled ranking could satisfy
    a law test that the real artifact would fail, which is the one thing a law test must not
    do.
    """
    events, lines = storm_shaped_chain()
    origin, lever, measured = events
    graph = promoted_graph(events, lines, ((origin, lever), (lever, measured)))
    context = RootCauseContext(
        propagation=propagation_context(events, lines, graph),
        actionability=actionability(),
        cost_classes=cost_classes(),
        severity_classes=severity_classes(),
        parameters=root_cause_parameters(),
        run_id=RUN_ID,
    )
    return analyze_root_causes(measured.event_id, context, envelope()).ranking
