"""The Graph Quality Report: the gaps before the findings, and no gap left unsaid."""

from __future__ import annotations

from causalog.causal_engine.causal_graph_builder import (
    DemotionReason,
    GraphBuildResult,
    build_causal_graph,
    render_markdown,
)
from fixtures.candidates import envelope, linear_process
from fixtures.graphs import (
    build_context,
    candidate,
    graph_parameters,
    permissive_scoring,
    scored_graph,
)


def _run(
    *, strong_floor: float = 0.0, kinds: tuple[str, ...] = ("DIRECT",), **kwargs: object
) -> GraphBuildResult:
    """Run the whole module over a two-step chain and return its result."""
    _, events, line = linear_process("STAGE_ONE", "STAGE_TWO", "STAGE_THREE", subject="A")
    candidates = (candidate(events[0], events[1]), candidate(events[1], events[2]))
    bands = permissive_scoring(strong_floor)
    graph = scored_graph(candidates, events, (line,), bands)
    context = build_context(
        events, (line,), candidates, graph_parameters(kinds=kinds, **kwargs), bands=bands
    )
    return build_causal_graph(graph, context, envelope())


def test_the_report_opens_with_what_the_graph_does_not_contain() -> None:
    """Section order is the argument: a small edge count is usually a fact about the source."""
    rendered = render_markdown(_run().report)
    gaps = rendered.index("## What this graph does not contain")
    counts = rendered.index("## Promoted edges by kind and band")
    assert gaps < counts


def test_an_empty_graph_says_so_before_any_number() -> None:
    """The honest headline when nothing clears, and it names the ledger as the explanation."""
    result = _run(strong_floor=0.99)
    assert result.report.graph_is_empty
    rendered = render_markdown(result.report)
    assert "**THE STATED VIEW IS EMPTY.**" in rendered
    assert "lowering a threshold until something appeared" in rendered


def test_undeclared_kinds_are_reported_as_a_policy_gap_not_as_a_finding() -> None:
    """A kind with no threshold is a statement about the pack (ADR-0049's rule)."""
    result = _run(kinds=("DIRECT",))
    policies = {gap.policy for gap in result.report.policy_gaps}
    assert "graph_construction.promotion_thresholds" in policies
    gap = next(
        gap
        for gap in result.report.policy_gaps
        if gap.policy == "graph_construction.promotion_thresholds"
    )
    assert "CONDITIONAL" in gap.requirement
    assert "never about the claim" in gap.consequence


def test_demotion_reasons_that_did_not_occur_are_listed_as_zero() -> None:
    """A zero must be visible as a zero, not as an absent row a reader has to notice."""
    report = _run(strong_floor=0.99).report
    assert DemotionReason.BELOW_KIND_THRESHOLD.value in dict(report.demotions_by_reason)
    assert DemotionReason.LOST_COMPETITION.value in report.unused_demotion_reasons
    rendered = render_markdown(report)
    assert "occurred **zero** times this run" in rendered


def test_orphan_effects_separate_never_proposed_from_fell_short() -> None:
    """Two different problems with two different fixes, so never one number."""
    report = _run(strong_floor=0.99).report
    assert report.orphan_effects
    assert report.orphan_effect_share > 0.0
    rendered = render_markdown(report)
    assert "Orphan effects" in rendered
    assert "nothing was ever proposed" in rendered or "considered and rejected" in rendered


def test_the_assumed_share_is_stated_rather_than_discoverable_per_edge() -> None:
    """LAW-PROVENANCE keeps assumptions on the claim; this is their weight in the whole."""
    report = _run().report
    rendered = render_markdown(report)
    assert "How much of this graph rests on `ASSUMED` inputs" in rendered
    assert 0.0 <= report.assumed_input_share <= 1.0


def test_the_rejection_ledger_is_never_summed_into_one_number() -> None:
    """Each reason answers a different question a reader might be asking."""
    rendered = render_markdown(_run(strong_floor=0.99).report)
    ledger = rendered.split("## The rejection ledger")[1]
    assert "Never summed into a single 'rejected' count" in ledger


def test_the_report_states_that_absence_from_the_graph_is_not_a_ruling_out() -> None:
    """The one thing every reader of this artifact must understand about it."""
    rendered = render_markdown(_run().report)
    assert "It asserts nothing about what it omits." in rendered


def test_degree_distributions_are_published_for_both_directions() -> None:
    """In-degree answers 'how many causes'; out-degree answers 'how much does this explain'."""
    report = _run().report
    assert report.in_degree_histogram
    assert report.out_degree_histogram
    rendered = render_markdown(report)
    assert "in-degree (causes per effect)" in rendered
    assert "out-degree (effects per cause)" in rendered


def test_typing_bases_are_tallied_so_default_typing_is_visible() -> None:
    """`UNTYPED_DEFAULT`'s size is a coverage statement about the rule pack."""
    report = _run().report
    assert dict(report.typing_bases).get("UNTYPED_DEFAULT")
    rendered = render_markdown(report)
    assert "not evidence of directness" in rendered
