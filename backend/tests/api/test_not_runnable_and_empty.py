"""An endpoint whose module does not exist says so, and an empty result says why.

Two failure modes this API is built to avoid, and they are different:

* **`NOT_RUNNABLE`** -- modules 7, 8 and 15 are `not-started`. An endpoint backed by one of
  them must return its envelope and state that the stage cannot run, naming the module.
  `docs/architecture.md` §2: "a partially computed run returns what exists with the stage
  stated, never a silently truncated graph."
* **Empty with a reason** -- on this dataset the promoted graph is genuinely empty, because
  thousands of claims were proposed and every one was refused. An empty `edges` list reads
  as "this event causes nothing"; the true statement is about what the engine ASSERTS. The
  body carries `empty_because` so a correct result cannot be read as the wrong one.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from causalog.core.ports.identity import Role
from causalog.orchestration.stages import PIPELINE_STAGES


def test_the_pipeline_declares_its_unbuilt_stages() -> None:
    """Modules 7, 8 and 15 are declared and named, not omitted.

    An omitted stage is indistinguishable from a stage that ran and found nothing.
    """
    unbuilt = {
        stage.stage_id: stage.not_runnable_because
        for stage in PIPELINE_STAGES
        if not stage.is_runnable
    }
    assert set(unbuilt) == {"relationships", "temporal_graph", "explanations"}
    for stage_id, reason in unbuilt.items():
        assert (
            reason and "Module" in reason
        ), f"Stage {stage_id} is NOT_RUNNABLE without naming the module responsible."


def test_graph_reports_why_it_is_empty(client: TestClient, token: Any, run_id: str) -> None:
    """An empty graph carries its reason and the count of refused claims."""
    response = client.get(f"/v1/runs/{run_id}/graph", headers=token(Role.DATA_SCIENTIST))
    assert response.status_code == 200
    data = response.json()["data"]
    if data["edges"]:
        return  # A non-empty graph needs no explanation; nothing to assert.
    assert data["empty_because"], (
        "The graph is empty and says nothing about why. An empty edge list reads as "
        "'this causes nothing', which is not what an unpromoted graph means."
    )
    assert data["rejected_claim_count"] >= 0
    if data["rejected_claim_count"]:
        assert "refused promotion" in data["empty_because"]


def test_root_cause_under_the_stated_standing_explains_silence(
    client: TestClient, token: Any, run_id: str
) -> None:
    """No cause under STATED is reported as a claim about assertion, not about the data."""
    response = client.get(
        f"/v1/runs/{run_id}/root-causes/evt:nonexistent000", headers=token(Role.DATA_SCIENTIST)
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["earliest"] is None
    assert data["empty_because"], "Silence was returned with no explanation."
    assert data[
        "actionability_notice"
    ], "The R-15 caveat is a required field so that a ranking cannot travel without it."


def test_diagnostic_output_always_carries_its_disowning_notice(
    client: TestClient, token: Any, run_id: str
) -> None:
    """ADR-0059 / OQ-026: a disowned figure never travels without its notice.

    The notice is a required field on the response rather than an optional annotation,
    because an optional notice is one a client will drop.
    """
    response = client.get(
        f"/v1/runs/{run_id}/graph?standing=UNPROMOTED_DIAGNOSTIC",
        headers=token(Role.HISTORICAL_ANALYST),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["standing"] == "UNPROMOTED_DIAGNOSTIC"
    assert body["standing_notice"], "Disowned output arrived with no disowning notice."
    assert "DISOWNED" in body["standing_notice"]


def test_stated_output_carries_no_disowning_notice(
    client: TestClient, token: Any, run_id: str
) -> None:
    """The converse: a stated result is not labelled as disowned.

    Without this, a notice attached unconditionally would satisfy the test above while
    telling every reader that everything is disowned -- which would make the notice
    meaningless exactly when it matters.
    """
    response = client.get(f"/v1/runs/{run_id}/graph", headers=token(Role.DATA_SCIENTIST))
    body = response.json()
    assert body["standing"] == "STATED"
    assert body["standing_notice"] is None


def test_simulated_events_are_not_shaped_like_observed_events() -> None:
    """OQ-031 and prd.md §37: the API cannot serialize a simulation as an observation.

    Asserted over the types rather than over a response, because the guarantee is
    structural: `SimulatedEventView` has no `occurred_at`, so a client cannot deserialize
    one into an `EventView` and no interface can render them identically by accident.
    """
    from causalog.orchestration.views import EventView, SimulatedEventView

    assert "occurred_at" in EventView.model_fields
    assert "occurred_at" not in SimulatedEventView.model_fields, (
        "A simulated event acquired an observed event's timestamp field, which is exactly "
        "the conflation ADR-0068 removed at the type level."
    )
    assert SimulatedEventView.model_fields["provenance_class"].default.value == "SIMULATED"
