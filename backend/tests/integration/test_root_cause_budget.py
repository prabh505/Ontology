"""prd.md §55: a root cause query answers in under three seconds. Measured, not assumed.

`make bench` has printed the §55 targets since P0 and measured none of them. This file
measures the root-cause one, and it is written to the shape
`test_bulk_load_budget.py` established: the number is printed whether or not the assertion
passes, because a benchmark whose figure nobody can read is a benchmark nobody reads.

WHAT IS MEASURED, AND AT WHAT SCALE. The graph is synthetic and is built at the scale of the
committed bounded run: 1,224 events and roughly 9,500 claims, which is what
`docs/reports/dataco/.../causal-graph.json` describes. **That slice is three orders of
magnitude below the reference dataset** (150 rows of 180,519) and the gap is OQ-023's, not
this file's. The measurement is therefore honest about what it covers: a query over a graph
of this size, not a query over the dataset.

WHY A SYNTHETIC GRAPH RATHER THAN THE COMMITTED ARTIFACT. The committed promoted graph has
**zero edges** -- 0 of 9,492 claims promoted, 79.3% stopped by the temporal verdict (R-22).
A traversal over it returns instantly and would measure nothing. A benchmark that passed
because there was no work to do would be worse than no benchmark, so this builds a graph
that actually has to be walked.

The budget is deliberately left able to fail. If it ever does, the honest responses are to
make the query faster or to change the requirement -- never to raise the constant until the
test goes green, which converts a known miss into an unknown one.
"""

from __future__ import annotations

import time

import pytest

from causalog.causal_engine.propagation_analyzer import analyze_propagation
from causalog.causal_engine.root_cause_analyzer import RootCauseContext, analyze_root_causes
from fixtures.candidates import RUN_ID, envelope
from fixtures.propagation import (
    actionability,
    cost_classes,
    root_cause_parameters,
    scale_graph,
    severity_classes,
)

pytestmark = pytest.mark.slow

#: prd.md §55. One number, in one place, quoted in the failure message.
ROOT_CAUSE_BUDGET_SECONDS = 3.0

#: The scale of the committed bounded run (`docs/reports/dataco/.../candidate-graph.json`):
#: 1,224 events and 9,492 claims that reached the promotion decision.
SLICE_EVENTS = 1224
CLAIMS_PER_EVENT = 8

#: The reference file's row count, carried so the printed block can state the gap this
#: measurement does NOT cover (OQ-023).
DATASET_ROWS = 180_519
SLICE_ROWS = 150


def test_a_root_cause_query_meets_the_prd_55_budget(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One outcome in, four labelled views out, inside three seconds."""
    construction_started = time.monotonic()
    context, seed, outcome = scale_graph(SLICE_EVENTS, CLAIMS_PER_EVENT)
    construction = time.monotonic() - construction_started
    ranking_context = RootCauseContext(
        propagation=context,
        actionability=actionability(),
        cost_classes=cost_classes(),
        severity_classes=severity_classes(),
        parameters=root_cause_parameters(),
        run_id=RUN_ID,
    )

    started = time.monotonic()
    result = analyze_root_causes(outcome, ranking_context, envelope())
    elapsed = time.monotonic() - started

    propagation_started = time.monotonic()
    tree = analyze_propagation(seed, context, envelope()).tree
    propagation_elapsed = time.monotonic() - propagation_started

    with capsys.disabled():
        print(
            f"\n  prd.md §55 root cause query"
            f"\n    events in graph          {len(context.events_by_id()):>10,}"
            f"\n    links in graph           {context.view.link_count():>10,}"
            f"\n    candidates considered    {len(result.ranking.considered):>10,}"
            f"\n    recommended              {len(result.ranking.actionable_root_causes):>10,}"
            f"\n"
            f"\n    ROOT CAUSE QUERY (budgeted)"
            f"\n      elapsed                {elapsed:>10.3f}s   budget "
            f"{ROOT_CAUSE_BUDGET_SECONDS:.0f}s"
            f"\n"
            f"\n    PROPAGATION ALONE (module 12, inside the above)"
            f"\n      elapsed                {propagation_elapsed:>10.3f}s"
            f"\n      consequences reached   {len(tree.nodes):>10,}"
            f"\n      depth / breadth        {tree.depth:>10,} / {tree.breadth:,}"
            f"\n"
            f"\n    FIXTURE CONSTRUCTION (not budgeted; setup, not query)"
            f"\n      elapsed                {construction:>10.3f}s"
            f"\n"
            f"\n  WHAT THIS DOES NOT MEASURE (OQ-023): the graph above is built at the"
            f"\n    scale of the committed bounded run, which is {SLICE_ROWS} rows of"
            f"\n    {DATASET_ROWS:,} -- three orders of magnitude below the reference"
            f"\n    dataset. A query over the whole dataset is NOT measured here and this"
            f"\n    number must not be read as though it were."
            f"\n"
        )

    assert result.ranking.considered, (
        "The benchmark measured a query that found no candidate, which would pass on "
        "having no work to do. Emptiness is refused here for the same reason it is refused "
        "in every determinism test."
    )
    assert elapsed < ROOT_CAUSE_BUDGET_SECONDS, (
        f"The root cause query took {elapsed:.3f}s against the "
        f"{ROOT_CAUSE_BUDGET_SECONDS:.0f}s prd.md §55 budget.\n\n"
        "This assertion is deliberately left able to fail. The number is a measurement of "
        "a product requirement, so the honest responses are to make the query faster or to "
        "change the requirement -- never to raise ROOT_CAUSE_BUDGET_SECONDS until the test "
        "goes green, which converts a known miss into an unknown one.\n\n"
        "The bounds that keep this query bounded are declared in the pack: "
        "`propagation_analysis.maximum_depth`, `propagation_analysis.traversal_node_cap` "
        "and `root_cause_analysis.candidate_cap`. Tightening one of those is a change to "
        "what the engine claims to have measured, and it is reported as truncation, so it "
        "is a legitimate response only if the report keeps saying so."
    )
