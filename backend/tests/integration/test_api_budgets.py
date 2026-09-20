"""prd.md §55 budgets, measured through the HTTP surface rather than at the module.

The three module-level budget tests (`test_root_cause_budget.py` and its siblings) measure
a reasoning call. This one measures the same operation as a CLIENT experiences it --
including authentication, authorization, the audit write, view conversion and JSON
serialization. That gap is the point: a query inside its budget at the module and outside
it at the boundary is still a missed budget.

**What is measured, and at what scale.** A synthetic run of 40 rows. The committed bounded
run is 150 rows of 180,519, and this is smaller still, so these numbers are *not* a
measurement of the dataset and are printed with that caveat attached. OQ-023 tracks the
gap; this file does not close it and does not pretend to.

**Two of the five §55 budgets are absent here on purpose.** "Dataset loading < 30 seconds"
and "graph generation < 60 seconds" have no agreed definition (OQ-018/OQ-019) and no full
producer -- modules 7 and 8 are not built. `orchestration.timing` marks both
`enforced=False` with the reason, and asserting them would be choosing the reading that
passes.

The budgets are deliberately left able to fail. If one ever does, the honest responses are
to make the endpoint faster or to change the requirement -- never to raise the constant
until the test goes green, which converts a known miss into an unknown one.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api_support import SLICE_NOTICE
from causalog.core.ports.identity import Role
from causalog.orchestration.timing import BUDGETS, BudgetName, budget_for


def _measure(client: TestClient, url: str, headers: dict[str, str]) -> tuple[float, Any]:
    """Return the wall-clock cost of one request and its body."""
    started = time.perf_counter()
    response = client.get(url, headers=headers)
    return time.perf_counter() - started, response


def _traversable_outcome(executed_run: tuple[Any, str]) -> str:
    """Return an event the scored graph actually reaches, so the query does real work.

    The committed promoted graph on this dataset is EMPTY, so a root-cause query under the
    STATED standing returns immediately whatever it is asked -- and a budget test over that
    would pass because there was nothing to traverse. That is the "passed on having no work
    to do" failure this repository's own budget tests are written to avoid (R-22), and it is
    the reason the measurement below uses the UNPROMOTED_DIAGNOSTIC standing over a target
    the scored graph genuinely reaches.
    """
    state = executed_run[0]
    targets = sorted({edge.edge.target_event_id for edge in state.scored.edges})
    assert targets, (
        "The shared run scored no edges, so there is no traversal to measure and this "
        "budget test would pass on having no work to do."
    )
    return targets[0]


@pytest.mark.slow
def test_root_cause_query_is_within_its_budget(
    client: TestClient,
    token: Any,
    run_id: str,
    executed_run: tuple[Any, str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """prd.md §55: a root cause query answers in under three seconds.

    Measured over a traversal that actually happens -- see `_traversable_outcome`.
    """
    budget = budget_for(BudgetName.ROOT_CAUSE_QUERY)
    headers = token(Role.DATA_SCIENTIST)
    outcome_event_id = _traversable_outcome(executed_run)
    elapsed, response = _measure(
        client,
        f"/v1/runs/{run_id}/root-causes/{outcome_event_id}" "?standing=UNPROMOTED_DIAGNOSTIC",
        headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    considered = body["data"]["earliest"] or body["data"]["most_actionable"]
    assert considered is not None, (
        "The measured query ranked nothing, so it measured no traversal. A budget test "
        "that passes on an empty result is worse than no budget test."
    )

    with capsys.disabled():
        print(
            f"\nprd.md §55 root-cause query over HTTP: {elapsed:.3f}s against a "
            f"{budget.seconds}s budget.\n{SLICE_NOTICE}"
        )
    assert elapsed < budget.seconds, (
        f"A root-cause query took {elapsed:.3f}s against prd.md §55's {budget.seconds}s "
        "budget. Make it faster or change the requirement; do not raise the constant."
    )


@pytest.mark.slow
def test_the_response_reports_its_own_timing(client: TestClient, token: Any, run_id: str) -> None:
    """The body carries the measurement and the budget it was measured against.

    Reported rather than merely enforced: a client that knows a call came in at 2.9s of a
    3s budget can act on it, and a client told only "200 OK" cannot.
    """
    response = client.get(
        f"/v1/runs/{run_id}/root-causes/evt:absent00000000",
        headers=token(Role.DATA_SCIENTIST),
    )
    assert response.status_code == 200
    timing = response.json()["timing"]
    assert timing["budget_name"] == BudgetName.ROOT_CAUSE_QUERY.value
    assert timing["budget_seconds"] == 3.0
    assert timing["budget_enforced"] is True
    assert timing["within_budget"] is True
    assert timing["elapsed_seconds"] >= 0.0


def test_the_two_unmeasurable_budgets_are_declared_unenforced() -> None:
    """The honest limit, asserted so it cannot be quietly removed.

    If someone later marks these `enforced=True` without resolving OQ-018/OQ-019, this
    fails -- which is the point. The budgets are not being ignored; they are being reported
    as undecided.
    """
    for name in (BudgetName.DATASET_LOADING, BudgetName.GRAPH_GENERATION):
        budget = BUDGETS[name]
        assert not budget.enforced
        assert budget.reason_if_unenforced


@pytest.mark.slow
def test_unbudgeted_endpoints_report_no_false_compliance(
    client: TestClient, token: Any, run_id: str
) -> None:
    """An endpoint with no §55 budget says so rather than claiming to be within one."""
    response = client.get(f"/v1/runs/{run_id}/events", headers=token(Role.OPERATIONS_MANAGER))
    timing = response.json()["timing"]
    assert timing["budget_name"] is None
    assert timing["within_budget"] is None, (
        "An unbudgeted endpoint reported compliance with a budget it was never measured " "against."
    )
