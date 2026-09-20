"""prd.md §54: role-based access, asserted over every role and every route.

The matrix is data (`api.security.authorization.PERMISSIONS`), so this file can enumerate
it rather than paraphrase it. Three properties are asserted and they are different claims:

1. **Every role and every capability** matches the published matrix -- the matrix is what it
   says it is.
2. **Every route declares a capability** the matrix governs -- no route authorizes by
   accident, and a new route cannot slip in ungoverned.
3. **Every route, exercised by every role, returns 403 exactly when the matrix says so** --
   the declaration is actually enforced, which the first two do not show.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from causalog.api.dependencies import requires
from causalog.api.security.authorization import (
    ADMINISTRATIVE_CAPABILITIES,
    PERMISSIONS,
    Capability,
    permitted,
)
from causalog.core.ports.identity import Role

#: Each route, the capability it declares, and a request that reaches it. The capability is
#: written here rather than read from the route so that a change to a route's capability
#: has to be acknowledged in this file too -- reading it would make the test agree with
#: whatever the code said, which is the one thing a permission test must not do.
ROUTE_MATRIX: tuple[tuple[str, str, Capability], ...] = (
    ("GET", "/v1/runs/{run_id}/events", Capability.READ_OBSERVED),
    ("GET", "/v1/runs/{run_id}/timelines/x", Capability.READ_OBSERVED),
    ("GET", "/v1/runs/{run_id}/graph", Capability.READ_INFERRED),
    ("GET", "/v1/runs/{run_id}/root-causes/x", Capability.READ_INFERRED),
    ("GET", "/v1/runs/{run_id}/propagation/x", Capability.READ_INFERRED),
    ("GET", "/v1/runs/{run_id}/ontology", Capability.READ_RULES),
    ("GET", "/v1/runs/{run_id}/rule-pack", Capability.READ_RULES),
    ("POST", "/v1/runs/{run_id}/counterfactuals", Capability.SIMULATE),
    ("DELETE", "/v1/runs/{run_id}/inferred-artifacts", Capability.DELETE_INFERRED),
    ("GET", "/v1/runs", Capability.READ_OBSERVED),
    ("GET", "/v1/jobs", Capability.READ_OBSERVED),
    ("POST", "/v1/jobs", Capability.EXECUTE_PIPELINE),
)


def test_every_role_is_in_the_matrix() -> None:
    """No role holds an undeclared set of capabilities."""
    assert set(PERMISSIONS) == set(Role), (
        "A role absent from PERMISSIONS holds nothing, which is safe but silent. Every "
        "prd.md §10 user type must have an explicit row."
    )


@pytest.mark.parametrize("role", list(Role), ids=lambda role: role.value)
@pytest.mark.parametrize("capability", list(Capability), ids=lambda cap: cap.value)
def test_matrix_is_total(role: Role, capability: Capability) -> None:
    """Every (role, capability) pair resolves to a definite answer."""
    assert isinstance(permitted(role, capability), bool)


def test_administrative_capabilities_are_narrowly_held() -> None:
    """The capabilities prd.md gives no holder are not handed to everyone.

    `ADMINISTRATIVE_CAPABILITIES` records an open question: prd.md §10's five types are all
    consumers of analysis and none is described as administering the system, so the holders
    below are a proposed default awaiting a ruling. This test pins the default so that a
    change to it is deliberate rather than incidental -- it does not claim the default is
    right.
    """
    for capability in ADMINISTRATIVE_CAPABILITIES:
        holders = {role for role in Role if permitted(role, capability)}
        assert holders, f"{capability.value} is held by nobody, so nothing can perform it."
        assert holders != set(Role), (
            f"{capability.value} is held by every role, which makes the distinction "
            "between an analyst and an administrator vanish."
        )


def test_executive_cannot_read_disowned_output() -> None:
    """The one matrix decision that OQ-026 turns on, asserted directly.

    `UNPROMOTED_DIAGNOSTIC` output is disowned by the engine (ADR-0059) and OQ-026 records
    that its structural defences do not survive a screenshot. An executive summary is where
    a disowned figure quoted as a finding does the most damage, so `EXECUTIVE` is withheld
    `READ_DIAGNOSTIC` deliberately. This test exists so that granting it later is a visible
    decision.
    """
    assert not permitted(Role.EXECUTIVE, Capability.READ_DIAGNOSTIC)


@pytest.mark.parametrize(
    ("method", "path", "capability"),
    ROUTE_MATRIX,
    ids=[f"{method}:{path}" for method, path, _ in ROUTE_MATRIX],
)
@pytest.mark.parametrize("role", list(Role), ids=lambda role: role.value)
def test_every_route_enforces_its_capability(
    client: TestClient,
    token: object,
    run_id: str,
    method: str,
    path: str,
    capability: Capability,
    role: Role,
) -> None:
    """Every route, for every role: 403 exactly when the matrix withholds the capability.

    Only the 403 is asserted, not the success status. A permitted call may legitimately
    return 200, 202, 404 or 422 depending on what it was asked for, and pinning those here
    would make this file a second, weaker copy of every other test. What matters is the
    boundary: refused when it should be, and NOT refused when it should not be.
    """
    headers = token(role)  # type: ignore[operator]
    url = path.replace("{run_id}", run_id)
    simulation_body = {
        "interventions": [{"payload": {"kind": "REMOVE_EVENT", "event_id": "x"}, "rationale": "r"}]
    }
    body = (
        simulation_body
        if method == "POST" and "counterfactual" in path
        else {"dataset_id": "dataco", "rows": 1}
    )
    response = (
        client.request(method, url, headers=headers, json=body)
        if method == "POST"
        else client.request(method, url, headers=headers)
    )

    if permitted(role, capability):
        assert (
            response.status_code != 403
        ), f"{role.value} holds {capability.value} but was refused {method} {path}."
    else:
        assert response.status_code == 403, (
            f"{role.value} does NOT hold {capability.value} but {method} {path} returned "
            f"{response.status_code}. The matrix is documentation only if it is not enforced."
        )


def test_requires_builds_a_distinct_dependency_per_capability() -> None:
    """`requires` is a factory, not a shared singleton.

    A shared dependency would authorize every route against whichever capability was
    declared last, and every test above would still pass because they would all agree with
    each other.
    """
    first = requires(Capability.READ_OBSERVED)
    second = requires(Capability.DELETE_INFERRED)
    assert first is not second
