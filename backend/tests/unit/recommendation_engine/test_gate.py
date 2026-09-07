"""The actionability gate: what it refuses, and that a refusal is never a silent absence.

"Never recommend an intervention on a non-actionable event type" is one line of the module
contract and four distinct refusals in practice: the pack says no, the pack says nothing,
the pack and the stamp disagree, and the pack declares an act with no cost. Each is a
different statement about a domain and each has its own member of `RefusalReason`, so a
reader of the ledger learns which.
"""

from __future__ import annotations

from causalog.core.ontology_view import ActionabilityView
from causalog.recommendation_engine import (
    RecommendationContext,
    RefusalReason,
    admissible_target,
    discover,
)
from fixtures.propagation import LEVER, MEASURED, ORIGIN
from fixtures.recommendation import (
    actionable_everywhere,
    recommendation_context,
    serial_chain_shape,
)
from fixtures.simulation import linear_shape


def _context(
    actionability: tuple[ActionabilityView, ...] | None = None,
) -> tuple[RecommendationContext, tuple[str, str]]:
    events, graph, identifiers = serial_chain_shape()
    return recommendation_context(events, graph, actionability=actionability), identifiers


def test_a_non_actionable_type_is_refused_and_the_refusal_names_the_declaration() -> None:
    """The headline constraint. `MEASURED` is the outcome and can never be acted on."""
    context, _ = _context()
    outcome = context.outcome_event_ids[0]

    view, refusal = admissible_target(outcome, context)

    assert view is None
    assert refusal is not None
    assert refusal.reason is RefusalReason.NOT_ACTIONABLE
    assert MEASURED in refusal.checked_against


def test_an_undeclared_type_is_a_gap_and_not_a_refusal() -> None:
    """ADR-0049's distinction: "checked and refused" is not "could not be checked".

    Collapsing them would let an unconfigured pack read as one that had considered every
    event type and ruled them all out.
    """
    context, identifiers = _context(actionability=())

    _, refusal = admissible_target(identifiers[0], context)

    assert refusal is not None
    assert refusal.reason is RefusalReason.ACTIONABILITY_NOT_DECLARED
    assert refusal.reason is not RefusalReason.NOT_ACTIONABLE


def test_a_stamp_that_disagrees_with_the_pack_is_reported_and_not_resolved() -> None:
    """R-15. Choosing a winner would decide which declaration about a domain is right.

    `linear_shape` stamps `is_actionable=False` by default while `actionable_everywhere`
    declares True, which is the disagreement the real pipeline produces whenever a pack
    changes after the events were generated.
    """
    events, graph = linear_shape(actionable=False)
    context = recommendation_context(events, graph)
    antecedent = next(event.event_id for event in events if event.event_type == ORIGIN)

    _, refusal = admissible_target(antecedent, context)

    assert refusal is not None
    assert refusal.reason is RefusalReason.STAMP_DISAGREES_WITH_PACK
    assert "Event.is_actionable" in refusal.checked_against
    assert "not resolved" in refusal.detail.lower() or "NOT resolved" in refusal.detail


def test_an_actionable_type_with_no_cost_is_refused_rather_than_ranked_free() -> None:
    """An absent cost would place the candidate above everything that declared one."""
    declared = (
        ActionabilityView(event_type=ORIGIN, actionable=True, severity_class="MINOR"),
        ActionabilityView(event_type=LEVER, actionable=False, severity_class="MINOR"),
        ActionabilityView(event_type=MEASURED, actionable=False, severity_class="CRITICAL"),
    )
    context, identifiers = _context(actionability=declared)

    _, refusal = admissible_target(identifiers[0], context)

    assert refusal is not None
    assert refusal.reason in {
        RefusalReason.COST_NOT_DECLARED,
        RefusalReason.STAMP_DISAGREES_WITH_PACK,
    }


def test_an_admissible_target_returns_its_declaration_and_no_refusal() -> None:
    """Exactly one of the two is ever populated, on both branches."""
    events, graph, identifiers = serial_chain_shape()
    context = recommendation_context(events, graph, actionability=actionable_everywhere())

    view, refusal = admissible_target(identifiers[0], context)

    assert refusal is None
    assert view is not None
    assert view.actionable is True
    assert view.cost_class is not None


def test_every_refused_node_appears_in_the_ledger_rather_than_vanishing() -> None:
    """Found-nothing and found-and-refused are different findings about a domain.

    A list that showed only the first would read as an absence of opportunity.
    """
    events, graph, _ = serial_chain_shape()
    context = recommendation_context(events, graph, actionability=())

    found = discover(context)

    assert found.candidates == ()
    assert found.proposed_count > 0
    assert len(found.refused) == found.proposed_count
