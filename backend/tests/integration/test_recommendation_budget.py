"""prd.md §55: recommendation generation completes in under five seconds. Measured.

The fifth and last of §55's targets to become a measurement rather than a quotation. Written
to the shape `test_root_cause_budget.py` established and `test_counterfactual_budget.py`
followed: the number is printed whether or not the assertion passes, because a benchmark
whose figure nobody can read is a benchmark nobody reads.

WHY THIS ONE IS THE HARDEST OF THE FIVE. A recommendation run is not one query. It discovers
candidates, then simulates EACH one through module 13, then searches cut sets over them, then
simulates each surviving set again as a set. The counterfactual budget covers one simulation;
this budget covers N of them plus a subset search, so the pack's `cut_set_node_cap` and
`portfolio_size_cap` are not decorations -- they are what makes the target reachable, and the
run reports truncation rather than quietly exceeding the budget.

WHAT IS MEASURED, AND AT WHAT SCALE. The same synthetic graph the counterfactual budget uses,
at the scale of the committed bounded run: 1,224 occurrences and roughly 9,700 promoted
links. **That slice is three orders of magnitude below the reference dataset** (150 rows of
180,519) and the gap is OQ-023's, not this file's.

WHY A SYNTHETIC GRAPH. The committed promoted graph has ZERO edges (R-22), so a real run
returns instantly with nothing to recommend and would measure nothing at all.

The budget is deliberately left able to fail. If it does, the honest responses are to make
the run faster, to tighten a declared bound in the pack, or to change the requirement --
never to raise the constant until the test goes green, which converts a known miss into an
unknown one.
"""

from __future__ import annotations

import time

import pytest

from causalog.recommendation_engine import optimize
from fixtures.candidates import envelope
from fixtures.recommendation import recommendation_context, recommendation_parameters
from fixtures.simulation import scale_shape

pytestmark = pytest.mark.slow

#: prd.md §55. One number, in one place, quoted in the failure message.
RECOMMENDATION_BUDGET_SECONDS = 5.0

#: The scale of the committed bounded run, matching `test_counterfactual_budget.py` exactly
#: so the two figures are comparable and the difference between them is the work module 14
#: adds on top of one simulation.
SLICE_EVENTS = 1224
LINKS_PER_EVENT = 8

#: The reference file's row count, carried so the printed block can state the gap this
#: measurement does NOT cover (OQ-023).
DATASET_ROWS = 180_519
SLICE_ROWS = 150

#: The bounds this run is measured under. Stated here rather than left at the fixture
#: default so the printed block can name them: a benchmark that met its budget under bounds
#: nobody can see is a benchmark that says nothing about the pack that will be used.
NODE_CAP = 40
SIZE_CAP = 2
EXACT_CEILING = 12


def test_a_recommendation_run_meets_the_prd_55_budget(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Discovery, per-candidate simulation, cut-set search and ranking, inside five seconds."""
    construction_started = time.monotonic()
    events, graph = scale_shape(SLICE_EVENTS, LINKS_PER_EVENT, actionable=True)
    context = recommendation_context(
        events,
        graph,
        # Outcomes taken from NEAR THE FRONT, not from the tail. The pack's propagation
        # depth bound stops a traversal well short of 1,224 nodes, so tail occurrences are
        # unreachable from any candidate and every (source, outcome) pair would be empty --
        # the cut-set search would then never run and the budget would not cover it. An
        # earlier revision of this file made exactly that mistake and reported zero cut sets.
        outcomes=tuple(sorted(event.event_id for event in events[20:23])),
        parameters=recommendation_parameters(
            node_cap=NODE_CAP, size_cap=SIZE_CAP, exact_ceiling=EXACT_CEILING
        ),
    )
    construction = time.monotonic() - construction_started

    started = time.monotonic()
    result = optimize(context, envelope())
    elapsed = time.monotonic() - started

    with capsys.disabled():
        print(
            f"\n  prd.md §55 recommendation generation"
            f"\n    occurrences in graph     {len(context.propagation.events_by_id()):>10,}"
            f"\n    promoted links           {len(graph.edges):>10,}"
            f"\n"
            f"\n    RECOMMENDATION RUN (budgeted)"
            f"\n      elapsed                {elapsed:>10.3f}s   budget "
            f"{RECOMMENDATION_BUDGET_SECONDS:.0f}s"
            f"\n"
            f"\n    WHAT THE RUN DID"
            f"\n      nodes proposed         {result.discovery.proposed_count:>10,}"
            f"\n      refused at the gate    {len(result.discovery.refused):>10,}"
            f"\n      candidates gated in    {len(result.discovery.candidates):>10,}"
            f"\n      cut sets considered    {len(result.cut_sets):>10,}"
            f"\n      published              {len(result.recommendations):>10,}"
            f"\n      withheld with a reason {len(result.withheld):>10,}"
            f"\n      policy gaps reported   {len(result.policy_gaps):>10,}"
            f"\n"
            f"\n    THE BOUNDS THIS RUN WAS MEASURED UNDER (all pack-declared)"
            f"\n      cut_set_node_cap       {NODE_CAP:>10,}"
            f"\n      portfolio_size_cap     {SIZE_CAP:>10,}"
            f"\n      cut_set_exact_ceiling  {EXACT_CEILING:>10,}"
            f"\n"
            f"\n    FIXTURE CONSTRUCTION (not budgeted; setup, not run)"
            f"\n      elapsed                {construction:>10.3f}s"
            f"\n"
            f"\n  THIS RUN SIMULATED ONCE PER CANDIDATE, plus once per multi-node set. The"
            f"\n    counterfactual budget covers ONE simulation; the difference between the"
            f"\n    two figures is the work module 14 adds, and the declared caps above are"
            f"\n    what keeps it bounded."
            f"\n"
            f"\n  WHAT THIS DOES NOT MEASURE (OQ-023): the graph above is built at the"
            f"\n    scale of the committed bounded run, which is {SLICE_ROWS} rows of"
            f"\n    {DATASET_ROWS:,} -- three orders of magnitude below the reference"
            f"\n    dataset. A run over the whole dataset is NOT measured here and this"
            f"\n    number must not be read as though it were."
            f"\n"
        )

    # Emptiness is refused at BOTH stages. An earlier revision of this file asserted only
    # that nodes were proposed; the run then refused all 1,223 of them at the actionability
    # gate, simulated nothing, and passed in 37ms -- measuring precisely the "passed on
    # having no work to do" failure this file's own docstring warns about. The gated-in
    # count is the one that governs how many simulations the budget actually covers.
    assert result.discovery.proposed_count > 0, "the run discovered nothing to consider"
    assert len(result.discovery.candidates) > 0, (
        "Every proposed node was refused at the actionability gate, so the run simulated "
        "nothing and the elapsed figure measures discovery alone. A benchmark that passes "
        "on having no work to do is worse than no benchmark."
    )
    assert (
        len(result.recommendations) + len(result.withheld) > 0
    ), "No candidate reached the ranking stage, so the scalarization was not measured."
    assert result.cut_sets, (
        "The cut-set search produced nothing, so the most expensive stage of the run was "
        "not measured. This happens when no outcome is reachable from any candidate; see "
        "the note on the outcome selection above."
    )
    assert elapsed < RECOMMENDATION_BUDGET_SECONDS, (
        f"Recommendation generation took {elapsed:.3f}s against the "
        f"{RECOMMENDATION_BUDGET_SECONDS:.0f}s prd.md §55 budget.\n\n"
        "This assertion is deliberately left able to fail. The number measures a product "
        "requirement, so the honest responses are to make the run faster, to tighten a "
        "declared bound in the pack, or to change the requirement -- never to raise the "
        "constant until the test goes green, which converts a known miss into an unknown "
        "one."
    )
