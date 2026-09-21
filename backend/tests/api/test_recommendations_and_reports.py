"""The §53 surface this API completes: recommendations, reports, dataset validation.

The recommendation tests carry more weight than most in this suite, because
`RecommendationView` is where **prd.md Principle 5** stops being a requirement and becomes
a type: "Every recommendation must identify: expected benefit, confidence, supporting
evidence, assumptions." All four are required fields, so an unsupported recommendation is
unconstructable rather than filtered out somewhere downstream.

`test_simulating_an_intervention_succeeds` is a **regression guard**. The counterfactual
endpoint shipped broken: `_simulation_context` read `joint_cause_groups` from
`PromotedGraph`, which carries `joint_groups`, and every POST to `/counterfactuals` raised
`AttributeError` and surfaced as a 500. Nothing caught it because no test had ever sent a
well-formed intervention — the permission-matrix test sends one, but only asserts it is not
a 403. A route that is only ever exercised for its status code is a route nobody has run.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from causalog.core.ports.identity import Role


def _first_event_id(client: TestClient, token: Any, run_id: str) -> str:
    """Return a real event id from the shared run."""
    response = client.get(f"/v1/runs/{run_id}/events?limit=1", headers=token(Role.DATA_SCIENTIST))
    items = response.json()["data"]["items"]
    assert items, "The shared run produced no events."
    return str(items[0]["event_id"])


# -- recommendations ---------------------------------------------------------------------


def test_recommendations_publish_what_was_withheld(
    client: TestClient, token: Any, run_id: str
) -> None:
    """A ranked set that is empty says how many candidates fell short, and at which test.

    On this dataset the engine recommends nothing. An empty list on its own says "we found
    nothing"; the true statement is "we found candidates and every one failed a named
    test", and the withheld set with its reason tally is what carries that.
    """
    response = client.get(
        f"/v1/runs/{run_id}/recommendations", headers=token(Role.PROCESS_IMPROVEMENT)
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    if data["recommendations"]:
        assert data["empty_because"] is None
        return

    assert data["empty_because"], (
        "Nothing was recommended and nothing says why. An empty list without its reason "
        "invites the wrong reading of a correct result."
    )
    if data["withheld"]:
        assert data["withheld_by_reason"], (
            "Candidates were withheld but no reason tally was published, so a reader "
            "cannot tell a confidence floor from an unmeasurable benefit."
        )
        counted = sum(count for _, count in data["withheld_by_reason"])
        assert counted == len(data["withheld"])
        for item in data["withheld"]:
            assert item["reason"] and item["checked_against"] and item["detail"]


def test_every_recommendation_carries_principle_5(
    client: TestClient, token: Any, run_id: str
) -> None:
    """prd.md Principle 5's four requirements are present on every published act.

    Asserted over whatever the run publishes. When the set is empty the structural
    guarantee is asserted against the TYPE instead, below, so this file proves the
    property either way rather than passing vacuously.
    """
    response = client.get(
        f"/v1/runs/{run_id}/recommendations?standing=UNPROMOTED_DIAGNOSTIC",
        headers=token(Role.DATA_SCIENTIST),
    )
    assert response.status_code == 200, response.text
    for item in response.json()["data"]["recommendations"]:
        assert item["expected_benefit"] is not None, "Principle 5: expected benefit."
        assert item["confidence"]["components"], "Principle 5: confidence, decomposed."
        assert item["evidence_item_ids"], "Principle 5: supporting evidence."
        assert item["assumptions"], "Principle 5: assumptions."
        for assumption in item["assumptions"]:
            assert assumption["falsified_by"], (
                "An assumption nobody can test is not an assumption. `falsified_by` is "
                "what makes Principle 5's fourth bullet actionable."
            )


def test_an_unsupported_recommendation_cannot_be_constructed() -> None:
    """Principle 5 is enforced by the TYPE, not by a filter downstream.

    This is the guarantee that survives an empty result set: whatever the engine publishes,
    it cannot publish an act without a benefit, a decomposed confidence, evidence and
    assumptions, because the model refuses to instantiate.
    """
    from causalog.orchestration.views import RecommendationView

    fields = RecommendationView.model_fields
    for required in ("expected_benefit", "confidence", "evidence_item_ids", "assumptions"):
        assert fields[required].is_required(), (
            f"{required!r} is optional on RecommendationView, so a recommendation missing "
            "it would serialize. prd.md Principle 5 requires all four."
        )
    for non_empty in ("evidence_item_ids", "assumptions"):
        assert any(
            getattr(item, "min_length", None) == 1 for item in fields[non_empty].metadata
        ), f"{non_empty!r} permits an empty tuple, which satisfies Principle 5 in name only."


def test_recommendations_are_within_their_budget(
    client: TestClient, token: Any, run_id: str
) -> None:
    """prd.md §55: recommendation generation answers in under five seconds."""
    response = client.get(
        f"/v1/runs/{run_id}/recommendations", headers=token(Role.PROCESS_IMPROVEMENT)
    )
    timing = response.json()["timing"]
    assert timing["budget_name"] == "RECOMMENDATION_GENERATION"
    assert timing["budget_seconds"] == 5.0
    assert (
        timing["within_budget"] is True
    ), f"Recommendation generation took {timing['elapsed_seconds']}s against a 5s budget."


# -- counterfactuals: the regression guard ------------------------------------------------


def test_simulating_an_intervention_succeeds(client: TestClient, token: Any, run_id: str) -> None:
    """A well-formed intervention simulates and comes back labelled as a simulation.

    REGRESSION GUARD. This endpoint shipped raising `AttributeError` on every call --
    `_simulation_context` read a field name `PromotedGraph` does not have -- and surfaced
    as a 500. No test caught it because none had ever sent a well-formed body.
    """
    target = _first_event_id(client, token, run_id)
    response = client.post(
        f"/v1/runs/{run_id}/counterfactuals",
        headers=token(Role.DATA_SCIENTIST),
        json={
            "interventions": [
                {
                    "payload": {"kind": "REMOVE_EVENT", "target_event_id": target},
                    "rationale": "Regression guard: this must simulate, not raise.",
                }
            ],
            "standing": "STATED",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provenance"]["weakest"] == "SIMULATED", (
        "A counterfactual result is SIMULATED (LAW-PROVENANCE); anything else would let a "
        "hypothetical be read as an observation."
    )
    assert body["data"], "The simulation returned an empty body."


def test_a_malformed_intervention_is_a_typed_422(
    client: TestClient, token: Any, run_id: str
) -> None:
    """An unknown kind is refused at the boundary with the five admissible ones named.

    Refused by the parse, before the engine sees it: the union is discriminated on `kind`,
    so a shape error is reported as a shape error rather than surfacing later as a domain
    refusal about something else.
    """
    response = client.post(
        f"/v1/runs/{run_id}/counterfactuals",
        headers=token(Role.DATA_SCIENTIST),
        json={"interventions": [{"payload": {"kind": "NOT_A_KIND"}, "rationale": "r"}]},
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "ContractViolationError"


def test_an_intervention_needs_a_rationale(client: TestClient, token: Any, run_id: str) -> None:
    """prd.md Principle 5: assumptions are explicit. An unexplained act is not reviewable."""
    target = _first_event_id(client, token, run_id)
    response = client.post(
        f"/v1/runs/{run_id}/counterfactuals",
        headers=token(Role.DATA_SCIENTIST),
        json={
            "interventions": [
                {"payload": {"kind": "REMOVE_EVENT", "target_event_id": target}, "rationale": ""}
            ]
        },
    )
    assert response.status_code == 422


# -- reports and dataset validation --------------------------------------------------------


def test_the_report_endpoint_is_declared_not_runnable(
    client: TestClient, token: Any, run_id: str
) -> None:
    """Module 15 is not-started, so the route exists and says so rather than 404ing.

    A missing ROUTE is indistinguishable from a route that ran and found nothing to say.
    A declared one names the module and points at the endpoints that already carry the
    same findings without the prose.
    """
    response = client.get(
        f"/v1/runs/{run_id}/reports/anything", headers=token(Role.OPERATIONS_MANAGER)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["stage_status"] == "NOT_RUNNABLE"
    assert "Module 15" in (
        body["stage_detail"] or ""
    ), "A NOT_RUNNABLE endpoint must name the module responsible."
    assert body["envelope"] is not None, (
        "A NOT_RUNNABLE response still carries its envelope; it is a real answer about a "
        "real run, not an error."
    )


def test_dataset_validation_separates_described_from_usable(client: TestClient, token: Any) -> None:
    """Mapping coverage and data quality are reported separately, never as one verdict.

    A dataset whose every column binds can still be unusable, and one with mapping gaps
    can still measure clean over what it does bind. A single `valid: true/false` would
    collapse the difference.
    """
    response = client.get("/v1/datasets/dataco/validation", headers=token(Role.OPERATIONS_MANAGER))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scope"] == "CATALOG", (
        "A dataset is not a run: it has no rule pack, engine version or seed, so it has no "
        "OutputEnvelope and must not claim one."
    )
    assert body["envelope"] is None

    data = body["data"]
    assert data["dataset_version"]
    assert data["binding_count"] >= 0
    assert isinstance(data["quality_report_available"], bool)
    if not data["quality_report_available"]:
        assert data["quality_report_absent_because"], (
            "An absent quality report is a third state, not a quiet false: a report that "
            "was never produced and one that found nothing are different, and only one is "
            "a reason to proceed."
        )


def test_an_unknown_dataset_is_refused_not_invented(client: TestClient, token: Any) -> None:
    """Asking about a dataset with no pack is an error, never an empty clean bill."""
    response = client.get(
        "/v1/datasets/no-such-domain/validation", headers=token(Role.OPERATIONS_MANAGER)
    )
    assert response.status_code >= 400
    assert response.json()["error_code"]
