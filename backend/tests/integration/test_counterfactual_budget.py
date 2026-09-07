"""prd.md §55: a counterfactual query answers in under five seconds. Measured, not assumed.

`make bench` has printed the §55 targets since P0. Modules 11 and 12 made the root-cause one
real; this file makes the counterfactual one real, and it is written to the shape
`test_root_cause_budget.py` established: the number is printed whether or not the assertion
passes, because a benchmark whose figure nobody can read is a benchmark nobody reads.

WHAT IS MEASURED, AND AT WHAT SCALE. The graph is synthetic and is built at the scale of the
committed bounded run: 1,224 occurrences and roughly 9,700 promoted links, which is what
`docs/reports/dataco/.../causal-graph.json` describes in claims considered. **That slice is
three orders of magnitude below the reference dataset** (150 rows of 180,519) and the gap is
OQ-023's, not this file's.

WHY A SYNTHETIC GRAPH RATHER THAN THE COMMITTED ARTIFACT. The committed promoted graph has
**zero edges** (R-22). A hypothetical over it returns instantly and would measure nothing. A
benchmark that passed because there was no work to do would be worse than no benchmark.

WHY THE KINDS ARE MIXED. Module 13 branches on the edge kind -- a contributing link and a
direct one make different claims about what a removal does -- so a benchmark over one kind
would time a branch the real work does not take.

The budget is deliberately left able to fail. If it ever does, the honest responses are to
make the query faster or to change the requirement, never to raise the constant until the
test goes green, which converts a known miss into an unknown one.
"""

from __future__ import annotations

import time

import pytest

from causalog.counterfactual_engine import Intervention, RemoveEvent, ShiftTiming, simulate
from fixtures.candidates import envelope
from fixtures.simulation import scale_shape, simulation_context

pytestmark = pytest.mark.slow

#: prd.md §55. One number, in one place, quoted in the failure message.
COUNTERFACTUAL_BUDGET_SECONDS = 5.0

#: The scale of the committed bounded run.
SLICE_EVENTS = 1224
LINKS_PER_EVENT = 8

#: The reference file's row count, carried so the printed block can state the gap this
#: measurement does NOT cover (OQ-023).
DATASET_ROWS = 180_519
SLICE_ROWS = 150


def test_a_counterfactual_query_meets_the_prd_55_budget(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One change in, a world and a validity assessment out, inside five seconds."""
    construction_started = time.monotonic()
    events, graph = scale_shape(SLICE_EVENTS, LINKS_PER_EVENT)
    context = simulation_context(events, graph)
    construction = time.monotonic() - construction_started

    removal = Intervention.of(
        RemoveEvent(target_event_id=events[0].event_id), rationale="benchmark"
    )
    move = Intervention.of(
        ShiftTiming(target_event_id=events[1].event_id, shift_seconds=-1800.0),
        rationale="benchmark",
    )

    started = time.monotonic()
    result = simulate((removal, move), context, envelope())
    elapsed = time.monotonic() - started

    world = result.world
    assert world is not None

    with capsys.disabled():
        print(
            f"\n  prd.md §55 counterfactual query"
            f"\n    occurrences in graph     {len(context.events_by_id()):>10,}"
            f"\n    promoted links           {len(graph.edges):>10,}"
            f"\n    changes admitted         {result.report.interventions_admitted:>10,}"
            f"\n"
            f"\n    COUNTERFACTUAL QUERY (budgeted)"
            f"\n      elapsed                {elapsed:>10.3f}s   budget "
            f"{COUNTERFACTUAL_BUDGET_SECONDS:.0f}s"
            f"\n"
            f"\n    WHAT THE QUERY DID"
            f"\n      occurrences reached    {world.diff.reached_count:>10,}"
            f"\n      changed                {len(world.diff.deltas):>10,}"
            f"\n      reached and unchanged  {world.diff.unchanged_count:>10,}"
            f"\n      would not have happened{len(world.diff.eliminated_event_ids):>10,}"
            f"\n      smaller, still happened{len(world.diff.reduced_event_ids):>10,}"
            f"\n      truncations            {len(result.report.truncations):>10,}"
            f"\n      validity verdict       {result.validity.verdict.value:>10}"
            f"\n"
            f"\n    FIXTURE CONSTRUCTION (not budgeted; setup, not query)"
            f"\n      elapsed                {construction:>10.3f}s"
            f"\n"
            f"\n  THE TWO COUNTS ABOVE ARE NEVER ADDED. A consequence that would have been"
            f"\n    smaller is not one that would have been prevented."
            f"\n"
            f"\n  WHAT THIS DOES NOT MEASURE (OQ-023): the graph above is built at the"
            f"\n    scale of the committed bounded run, which is {SLICE_ROWS} rows of"
            f"\n    {DATASET_ROWS:,} -- three orders of magnitude below the reference"
            f"\n    dataset. A query over the whole dataset is NOT measured here and this"
            f"\n    number must not be read as though it were."
            f"\n"
        )

    assert world.diff.reached_count > 0, (
        "The benchmark measured a hypothetical that reached nothing, which would pass on "
        "having no work to do. Emptiness is refused here for the same reason it is refused "
        "in every determinism test."
    )
    assert elapsed < COUNTERFACTUAL_BUDGET_SECONDS, (
        f"The counterfactual query took {elapsed:.3f}s against the "
        f"{COUNTERFACTUAL_BUDGET_SECONDS:.0f}s prd.md §55 budget.\n\n"
        "This assertion is deliberately left able to fail. The number is a measurement of "
        "a product requirement, so the honest responses are to make the query faster or to "
        "change the requirement -- never to raise the constant until the test goes green, "
        "which converts a known miss into an unknown one."
    )
