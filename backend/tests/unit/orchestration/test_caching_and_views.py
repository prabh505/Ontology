"""The cache contract, and the view conversions the API's guarantees rest on."""

from __future__ import annotations

import pytest

from causalog.core.provenance import ProvenanceClass
from causalog.orchestration import caching, views
from causalog.orchestration.timing import BUDGETS, BudgetName, TimingMeta, budget_for
from causalog.persistence.memory.fakes import InMemoryDerivedCache


def test_cache_key_is_insensitive_to_parameter_sequence() -> None:
    """Two callers asking one question in different sequence share a key.

    This is the whole reason the key is a content address rather than a formatted string:
    otherwise the cache would hold two entries for one question and hit on neither.
    """
    first = caching.cache_key("graph", (("depth", "2"), ("seed", "evt:1")))
    second = caching.cache_key("graph", (("seed", "evt:1"), ("depth", "2")))
    assert first == second


def test_cache_key_separates_different_questions() -> None:
    """Different query names and different parameters address differently."""
    assert caching.cache_key("graph", ()) != caching.cache_key("events", ())
    assert caching.cache_key("graph", (("depth", "2"),)) != caching.cache_key(
        "graph", (("depth", "3"),)
    )


def test_an_absent_cache_is_a_supported_configuration() -> None:
    """A cache whose absence raised could stop answers, which it must never do."""
    assert caching.read_cached(None, "run:x", "k") is None
    caching.write_cached(None, "run:x", "k", b"payload")
    assert caching.invalidate_run(None, "run:x") == 0


def test_invalidation_drops_only_the_named_run() -> None:
    """Run scoping is what makes a cached answer safe to serve at all."""
    cache = InMemoryDerivedCache()
    caching.write_cached(cache, "run:a", "k", b"a")
    caching.write_cached(cache, "run:b", "k", b"b")
    caching.invalidate_run(cache, "run:a")
    assert caching.read_cached(cache, "run:a", "k") is None
    assert caching.read_cached(cache, "run:b", "k") == b"b"


def test_a_cached_read_round_trips() -> None:
    """The positive case, so the invalidation test above is not vacuous."""
    cache = InMemoryDerivedCache()
    key = caching.cache_key("events", (("limit", "10"),))
    caching.write_cached(cache, "run:a", key, b"payload")
    assert caching.read_cached(cache, "run:a", key) == b"payload"


# -- budgets ----------------------------------------------------------------------------


def test_every_budget_name_is_declared() -> None:
    """The prd.md §55 table is total over the enum."""
    assert set(BUDGETS) == set(BudgetName)


def test_unenforced_budgets_state_why() -> None:
    """A budget that is not a gate says so, and says why, where a reader will see it.

    prd.md §55's dataset-loading and graph-generation targets have no agreed definition
    (OQ-018/OQ-019) and no full producer. Asserting them would be picking the reading that
    passes.
    """
    for budget in BUDGETS.values():
        if budget.enforced:
            assert budget.reason_if_unenforced is None
        else:
            assert (
                budget.reason_if_unenforced
            ), f"{budget.name.value} is advisory and does not say why."
    unenforced = {name for name, budget in BUDGETS.items() if not budget.enforced}
    assert unenforced == {BudgetName.DATASET_LOADING, BudgetName.GRAPH_GENERATION}


def test_timing_distinguishes_unbudgeted_from_within_budget() -> None:
    """`within_budget=None` is a third state, not a quiet `True`.

    "This was fast enough" and "nobody said how fast this should be" are different claims,
    and collapsing them would let an unbudgeted endpoint report compliance it was never
    measured for.
    """
    unbudgeted = TimingMeta.measured(operation="x", elapsed_seconds=99.0, budget=None)
    assert unbudgeted.within_budget is None

    budgeted = TimingMeta.measured(
        operation="x",
        elapsed_seconds=99.0,
        budget=budget_for(BudgetName.ROOT_CAUSE_QUERY),
    )
    assert budgeted.within_budget is False


# -- views ------------------------------------------------------------------------------


def test_a_confidence_view_cannot_be_built_without_components() -> None:
    """LAW-EVIDENCE, enforced by the type rather than by a later filter."""
    with pytest.raises(ValueError, match="components"):
        views.ConfidenceView(
            scalar=0.5,
            aggregation="weighted_mean_v1",
            provenance_class=ProvenanceClass.INFERRED,
            components=(),
        )


def test_provenance_summary_never_flattens_the_five_classes() -> None:
    """`weakest` and `present` are both carried; either alone misleads."""
    summary = views.provenance_summary(
        (ProvenanceClass.OBSERVED, ProvenanceClass.OBSERVED, ProvenanceClass.SIMULATED)
    )
    assert summary.weakest is ProvenanceClass.SIMULATED
    assert set(summary.present) == {ProvenanceClass.OBSERVED, ProvenanceClass.SIMULATED}


def test_an_empty_payload_is_observed_not_inferred() -> None:
    """A payload containing no assertion makes no claim.

    Reporting `INFERRED` for an empty result would attach an epistemic warning to the
    absence of any claim.
    """
    summary = views.provenance_summary(())
    assert summary.weakest is ProvenanceClass.OBSERVED


def test_the_standing_mirror_is_total() -> None:
    """Every `GraphStanding` has a presentation mirror, and vice versa.

    `causalog.api` cannot import `GraphStanding` (forbidden edge F5), so the enum is
    mirrored. A member added to one and not the other would surface as a 500 on the first
    response carrying it; this fails at test time instead.
    """
    from causalog.causal_engine.propagation_analyzer import GraphStanding

    assert {member.value for member in GraphStanding} == {
        member.value for member in views.GraphStandingView
    }
    for member in GraphStanding:
        assert views.standing_view(member).value == member.value
