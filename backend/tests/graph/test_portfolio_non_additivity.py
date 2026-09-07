"""Two acts on one chain are not worth the two figures added up (ADR-0077).

The error this asserts against, stated as an operator would experience it: shown two
recommendations worth forty units each, they plan for eighty. If both acts lie on one chain
the second saves what the first already saved, and the true figure is forty. Every part of
the system upstream is correct and the operator is still wrong.

The overlapping case and the independent case are BOTH asserted. A test that only checked
"joint is below naive" would pass against a function that always returned less than the sum;
pairing it with a pair that genuinely does not interact proves the mechanism instead.
"""

from __future__ import annotations

from causalog.causal_engine.causal_graph_builder import PromotedGraph
from causalog.core.types import Event
from causalog.recommendation_engine import (
    BenefitEstimate,
    Candidate,
    InteractionKind,
    RecommendationContext,
    discover,
    estimate,
    interactions_within,
    portfolio_benefit,
)
from fixtures.candidates import envelope
from fixtures.recommendation import (
    disjoint_shape,
    recommendation_context,
    serial_chain_shape,
)


def _members_and_estimates(
    events: tuple[Event, ...], graph: PromotedGraph, identifiers: tuple[str, ...]
) -> tuple[RecommendationContext, tuple[Candidate, ...], dict[str, BenefitEstimate]]:
    """Return the candidates named, with one individual estimate each."""
    context = recommendation_context(events, graph)
    by_id = {candidate.event_id: candidate for candidate in discover(context).candidates}
    members = tuple(by_id[event_id] for event_id in identifiers if event_id in by_id)
    individual = {
        candidate.event_id: estimate((candidate.event_id,), context, envelope())
        for candidate in members
    }
    return context, members, individual


def test_two_acts_on_one_chain_are_worth_strictly_less_than_their_sum() -> None:
    """The whole point of the module. Asserted as a strict inequality, not a tolerance."""
    events, graph, identifiers = serial_chain_shape(magnitude=40.0)
    context, members, individual = _members_and_estimates(events, graph, identifiers)

    combined = portfolio_benefit(members, individual, context, envelope())

    assert len(members) == 2
    assert combined.naive_total_high == 80.0
    assert combined.joint_high == 40.0
    assert combined.joint_high < combined.naive_total_high
    assert combined.overlap_loss == 40.0


def test_the_naive_total_is_published_beside_the_joint_figure_not_instead_of_it() -> None:
    """The overlap is the finding. A report that silently corrected it teaches nothing."""
    events, graph, identifiers = serial_chain_shape()
    context, members, individual = _members_and_estimates(events, graph, identifiers)

    combined = portfolio_benefit(members, individual, context, envelope())

    assert combined.naive_total_high is not None
    assert combined.joint_high is not None
    assert combined.overlap_loss is not None
    assert combined.naive_aggregation == "SUM"


def test_an_independent_pair_reports_no_interaction_and_no_overlap_loss() -> None:
    """The control. Two chains sharing nothing are not double-counting anything.

    No loss figure is published, and its absence carries a reason rather than reading as a
    loss of zero -- the two totals are not comparable when the members touch different
    consequences. See `portfolio.py`'s docstring.
    """
    events, graph, identifiers = disjoint_shape()
    context, members, individual = _members_and_estimates(events, graph, identifiers)

    combined = portfolio_benefit(members, individual, context, envelope())

    assert combined.interactions == ()
    assert combined.overlap_loss is None
    assert combined.loss_absent_because is not None
    assert "do not interact" in combined.loss_absent_because


def test_an_overlapping_pair_names_why_it_overlaps() -> None:
    """The interaction is detected by set intersection, and its kind is on the artifact."""
    events, graph, identifiers = serial_chain_shape()
    context, members, _ = _members_and_estimates(events, graph, identifiers)

    found = interactions_within(members, context)

    assert len(found) == 1
    assert found[0][2] is InteractionKind.SHARED_CONSEQUENCE


def test_no_source_file_in_the_package_calls_sum() -> None:
    """ADR-0077 structurally: the naive total goes through a named operator, never `sum`.

    Over the **AST**, not the text. `CONVENTIONS.md` §6a gives the reason and this test
    learned it the hard way: a textual matcher fires on the sentence in `portfolio.py`'s own
    docstring that promises `sum` appears nowhere, so the first version of this test failed
    on the prose asserting the property it was checking.

    Asserted over the source rather than over an output, because an output assertion still
    passes on the day someone adds a second, summed path beside the first.
    """
    import ast
    from pathlib import Path

    import causalog.recommendation_engine as package

    for path in sorted(Path(package.__file__).parent.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "sum" not in called, (
            f"{path.name} calls sum(); benefit arithmetic belongs in core.attribution "
            "under a named operator (ADR-0077, CONVENTIONS.md §6a)"
        )
