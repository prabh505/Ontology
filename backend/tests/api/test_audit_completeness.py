"""prd.md §54: every mutating action and every read of a sensitive result is audited.

The two halves fail differently and are asserted separately.

A **mutation** that is not audited leaves no record that state changed. A **read** that is
not audited leaves no record that an inference was disclosed -- and `CONVENTIONS.md` §8
names that explicitly: "Access to any endpoint returning inferences -- actor, role,
endpoint, correlation_id".

The third assertion is the one that is easy to skip and matters most: a **refused** request
must NOT produce an access record. A trail that claims disclosures which did not happen
cannot be relied on for the ones that did, so over-recording is a defect of the same kind
as under-recording rather than a safe margin.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from causalog.core.ports.identity import Role
from causalog.core.ports.persistence import AUDITABLE_ACTIONS
from causalog.orchestration.wiring import Adapters


def _entries(adapters: Adapters) -> list[dict[str, Any]]:
    """Return the audit entries recorded so far."""
    return list(adapters.audit.entries)  # type: ignore[attr-defined]


def test_reading_inferences_is_audited(
    client: TestClient, token: Any, run_id: str, adapters: Adapters
) -> None:
    """A permitted read of the causal graph records actor, role, endpoint and correlation."""
    response = client.get(f"/v1/runs/{run_id}/graph", headers=token(Role.DATA_SCIENTIST, "grace"))
    assert response.status_code == 200

    accesses = [
        entry for entry in _entries(adapters) if entry["action"] == "INFERENCE_ENDPOINT_ACCESSED"
    ]
    assert len(accesses) == 1, (
        "One permitted inference read should produce exactly one access record; got "
        f"{len(accesses)}."
    )
    entry = accesses[0]
    assert entry["actor"] == "grace"
    assert entry["target"].endswith("/graph")
    assert entry["target_kind"] == "endpoint"
    assert entry["correlation_id"]
    assert dict(entry["payload"])["role"] == Role.DATA_SCIENTIST.value
    assert entry["correlation_id"] == response.headers["X-Correlation-Id"]


def test_reading_observed_facts_is_not_audited_as_an_inference(
    client: TestClient, token: Any, run_id: str, adapters: Adapters
) -> None:
    """A fact is not an inference.

    Auditing every read of observed data would bury the entries that matter under the ones
    that do not, which is how an audit trail stops being read. `AUDITED_CAPABILITIES`
    deliberately omits `READ_OBSERVED`.
    """
    client.get(f"/v1/runs/{run_id}/events", headers=token(Role.OPERATIONS_MANAGER))
    assert not [
        entry for entry in _entries(adapters) if entry["action"] == "INFERENCE_ENDPOINT_ACCESSED"
    ]


def test_a_refused_read_is_not_recorded_as_an_access(
    client: TestClient, token: Any, run_id: str, adapters: Adapters
) -> None:
    """A 403 discloses nothing, so it must not be recorded as a disclosure.

    This is the regression guard for a defect found while building this surface: the
    diagnostic-standing check ran AFTER the audit was written, so an executive refused the
    disowned view was recorded as having read it.
    """
    response = client.get(
        f"/v1/runs/{run_id}/graph?standing=UNPROMOTED_DIAGNOSTIC",
        headers=token(Role.EXECUTIVE, "erin"),
    )
    assert response.status_code == 403
    assert not [
        entry for entry in _entries(adapters) if entry["action"] == "INFERENCE_ENDPOINT_ACCESSED"
    ], (
        "A refused request produced an inference-access record. A trail that claims "
        "disclosures which did not happen cannot be relied on for the ones that did."
    )


def test_starting_a_pipeline_is_audited(client: TestClient, token: Any, adapters: Adapters) -> None:
    """A mutating call produces an audit record naming its actor and its execution."""
    response = client.post(
        "/v1/jobs",
        headers=token(Role.DATA_SCIENTIST, "dana"),
        json={"dataset_id": "dataco", "rows": 1},
    )
    assert response.status_code == 202, response.text
    started = [
        entry for entry in _entries(adapters) if entry["action"] == "PIPELINE_EXECUTION_STARTED"
    ]
    assert len(started) == 1
    assert started[0]["actor"] == "dana"
    assert started[0]["target"] == response.json()["data"]["execution_id"]
    assert started[0]["correlation_id"]


def test_deleting_inferred_artifacts_is_audited_with_before_and_after(
    client: TestClient, token: Any, run_id: str, adapters: Adapters
) -> None:
    """The one destructive operation records what went, not merely that something did.

    Migration 0014 added `before_state`/`after_state` precisely so a change is inspectable
    without re-deriving it; an entry saying only "artifacts deleted" would not be.
    """
    response = client.delete(
        f"/v1/runs/{run_id}/inferred-artifacts", headers=token(Role.DATA_SCIENTIST)
    )
    assert response.status_code == 200, response.text
    deletions = [
        entry for entry in _entries(adapters) if entry["action"] == "INFERRED_ARTIFACTS_DELETED"
    ]
    assert len(deletions) == 1
    entry = deletions[0]
    assert entry["run_id"] == run_id
    assert entry["before_state"] is not None
    assert dict(entry["after_state"]) == {
        "causal_edges": "0",
        "projection_nodes": "0",
        "cache_entries": "0",
    }


def test_every_recorded_action_is_in_the_closed_vocabulary(
    client: TestClient, token: Any, run_id: str, adapters: Adapters
) -> None:
    """No call site invents an action name.

    `CONVENTIONS.md` §8 keeps the action list closed so the trail can be filtered and
    reconciled. Both the PostgreSQL sink and the in-memory fake refuse an unknown action --
    the fake only since module 16, which is why this test is worth having.
    """
    client.get(f"/v1/runs/{run_id}/graph", headers=token(Role.DATA_SCIENTIST))
    client.post(
        "/v1/jobs", headers=token(Role.DATA_SCIENTIST), json={"dataset_id": "dataco", "rows": 1}
    )
    recorded = {entry["action"] for entry in _entries(adapters)}
    assert recorded, "No audit entries were produced at all."
    assert (
        recorded <= AUDITABLE_ACTIONS
    ), f"Actions outside the closed list were recorded: {recorded - AUDITABLE_ACTIONS}"
