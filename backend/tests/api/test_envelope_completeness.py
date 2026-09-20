"""Every body carries its envelope, and no confidence ever arrives without components.

The second property is LAW-EVIDENCE at the wire: "Every confidence number decomposes into
named, inspectable components with the evidence records that produced them. A bare float is
a defect." `ConfidenceView` enforces it at construction, so the interesting question is not
whether the type holds -- it does -- but whether anything in a real response body slips
past it. A nested payload rendered through `canonical_form` from a `draft` artifact is not
a `ConfidenceView` and could carry a bare float under a confidence-shaped key.

So the check walks the whole JSON body, at every depth, and flags any object that looks
like a confidence and has no non-empty `components`. That mirrors
`scripts/check_confidence_is_a_vector.py`, which does the same over source code.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from causalog.core.ports.identity import Role
from causalog.core.run import OutputEnvelope

#: (method, path template, body) for every route that returns a RUN_SCOPED body.
RUN_SCOPED_REQUESTS: tuple[tuple[str, str, dict[str, Any] | None], ...] = (
    ("GET", "/v1/runs/{run_id}/events", None),
    ("GET", "/v1/runs/{run_id}/timelines/nonexistent", None),
    ("GET", "/v1/runs/{run_id}/graph", None),
    ("GET", "/v1/runs/{run_id}/ontology", None),
    ("GET", "/v1/runs/{run_id}/rule-pack", None),
)

#: The nine fields `CONVENTIONS.md` §11 requires on every artifact and API response.
ENVELOPE_FIELDS = frozenset(OutputEnvelope.model_fields)


def _confidence_shaped(value: dict[str, Any]) -> bool:
    """Return whether a mapping is claiming to be a confidence number.

    Keyed on `scalar` + `aggregation`, which is what `ConfidenceVector` uniquely carries.
    Matching on the key name `confidence` instead would miss a vector nested under another
    name and would falsely flag a field that merely counts confident things.
    """
    return "scalar" in value and "aggregation" in value


def _violations(node: Any, path: str = "$") -> list[str]:
    """Walk a JSON body and return every confidence-shaped object lacking components."""
    found: list[str] = []
    if isinstance(node, dict):
        if _confidence_shaped(node) and not node.get("components"):
            found.append(path)
        for key, item in node.items():
            found.extend(_violations(item, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(_violations(item, f"{path}[{index}]"))
    return found


@pytest.mark.parametrize(
    ("method", "path", "body"),
    RUN_SCOPED_REQUESTS,
    ids=[f"{method}:{path}" for method, path, _ in RUN_SCOPED_REQUESTS],
)
def test_run_scoped_bodies_carry_a_complete_envelope(
    client: TestClient,
    token: Any,
    run_id: str,
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    """A RUN_SCOPED body carries all nine envelope fields, and its run_id agrees."""
    response = client.request(
        method, path.format(run_id=run_id), headers=token(Role.DATA_SCIENTIST), json=body
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["scope"] == "RUN_SCOPED"
    assert (
        payload["envelope"] is not None
    ), "A RUN_SCOPED body with no envelope cannot be verified (CONVENTIONS.md §11)."
    assert set(payload["envelope"]) == ENVELOPE_FIELDS
    assert payload["run_id"] == payload["envelope"]["run_id"]
    assert payload["provenance"]["present"], "Provenance is never an empty claim."
    assert payload["standing"] in {"STATED", "UNPROMOTED_DIAGNOSTIC"}
    assert payload["stage_status"] in {"COMPLETE", "PARTIAL", "NOT_RUNNABLE"}
    assert payload["generated_at"]
    assert payload["timing"]["operation"]


@pytest.mark.parametrize(
    ("method", "path", "body"),
    RUN_SCOPED_REQUESTS,
    ids=[f"{method}:{path}" for method, path, _ in RUN_SCOPED_REQUESTS],
)
def test_no_body_carries_a_confidence_without_components(
    client: TestClient,
    token: Any,
    run_id: str,
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    """LAW-EVIDENCE at the wire, checked at every depth of the body."""
    response = client.request(
        method, path.format(run_id=run_id), headers=token(Role.DATA_SCIENTIST), json=body
    )
    assert response.status_code == 200, response.text
    offenders = _violations(response.json())
    assert not offenders, (
        "These paths carry a confidence-shaped object with no components, which is a bare "
        f"float wearing a confidence's name (LAW-EVIDENCE): {offenders}"
    )


def test_the_component_walk_rejects_a_bare_confidence() -> None:
    """The walk is observed to FAIL on a planted violation (DEF-0001's lesson).

    Without this, `_violations` returning `[]` for every input would make both tests above
    pass while checking nothing.
    """
    planted = {
        "data": {"nested": [{"confidence": {"scalar": 0.5, "aggregation": "weighted_mean_v1"}}]}
    }
    assert _violations(planted) == ["$.data.nested[0].confidence"]

    decomposed = {
        "confidence": {
            "scalar": 0.5,
            "aggregation": "weighted_mean_v1",
            "components": [{"component_name": "rule_support", "value": 0.5}],
        }
    }
    assert _violations(decomposed) == []


def test_events_carry_real_decomposed_confidence(
    client: TestClient, token: Any, run_id: str
) -> None:
    """The positive case: a real event's confidence names its components.

    A body containing no confidence at all would satisfy the walk above vacuously, so this
    asserts that the suite is actually looking at decomposed confidence somewhere.
    """
    response = client.get(f"/v1/runs/{run_id}/events?limit=1", headers=token(Role.DATA_SCIENTIST))
    items = response.json()["data"]["items"]
    assert items, "The shared run produced no events, so this suite proves nothing."
    components = items[0]["confidence"]["components"]
    assert components, "An event arrived with an undecomposed confidence."
    assert all(component["component_name"] for component in components)
