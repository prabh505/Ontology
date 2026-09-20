"""prd.md §54 hardening: typed errors that never leak internals in production.

The production/development split is behavioural, so it is tested on both sides. Testing
only production would not show that the detail exists at all; testing only development
would not show that it is withheld.

`CAUSALOG_ENV` is read at request time rather than captured at import, which is what makes
`monkeypatch.setenv` work here -- and is also why `is_production()` defaults to True: an
unset variable most likely means somebody deployed without setting it, and the failure
modes are asymmetric.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from causalog.api.schemas.errors import ERROR_STATUS, PUBLIC_MESSAGES
from causalog.core.errors import CausaLogError
from causalog.core.ports.identity import Role

#: Substrings that must never appear in a production error body. Each is a real leak shape:
#: a traceback, an internal module path, SQL, a filesystem path, a driver name.
FORBIDDEN_IN_PRODUCTION = (
    "Traceback",
    "causalog.",
    "SELECT ",
    "INSERT ",
    "psycopg",
    "/home/",
    "site-packages",
)


def _assert_clean(body: str) -> None:
    """Fail naming the leak, rather than merely failing."""
    for needle in FORBIDDEN_IN_PRODUCTION:
        assert needle not in body, (
            f"A production error body contains {needle!r}, which exposes an internal: "
            f"{body[:400]}"
        )


def test_every_taxonomy_member_has_a_status_and_a_public_message() -> None:
    """The mapping is total over the closed taxonomy (`CONVENTIONS.md` §7)."""
    assert set(ERROR_STATUS) == set(PUBLIC_MESSAGES), (
        "Every declared error status needs a public message and vice versa; a member with "
        "one and not the other would either leak or say nothing."
    )
    for error_type in ERROR_STATUS:
        assert issubclass(error_type, CausaLogError)
        assert PUBLIC_MESSAGES[error_type].strip()


def test_absent_run_is_a_404_naming_no_internals(
    client: TestClient, token: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`docs/architecture.md` §2: an absent run is a 404, never an empty success."""
    monkeypatch.setenv("CAUSALOG_ENV", "production")
    response = client.get(
        "/v1/runs/run:absent0000000000/events", headers=token(Role.DATA_SCIENTIST)
    )
    assert response.status_code == 404
    body = response.json()
    assert body["error_code"] == "RunNotAvailableError"
    assert body["remediation"]
    assert body["correlation_id"]
    _assert_clean(response.text)


def test_production_withholds_the_engine_message(
    client: TestClient, token: Any, run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In production the body is the fixed public sentence, not the engine's own text."""
    monkeypatch.setenv("CAUSALOG_ENV", "production")
    response = client.get(
        f"/v1/runs/{run_id}/events?cursor=evt:notinthisrun",
        headers=token(Role.DATA_SCIENTIST),
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "ContractViolationError"
    assert "notinthisrun" not in response.text, (
        "The production body echoed a caller-supplied identifier from the engine's "
        "message. Production replaces the message wholesale rather than filtering it."
    )
    _assert_clean(response.text)


def test_development_returns_the_engine_message(
    client: TestClient, token: Any, run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Outside production the engine's diagnostic message is returned.

    `CONVENTIONS.md` §7 requires an error to name the offending identifier and the contract
    violated. That text is the fastest route to a diagnosis and is safe where the caller is
    a developer; the production test above is what keeps it from reaching anyone else.
    """
    monkeypatch.setenv("CAUSALOG_ENV", "development")
    response = client.get(
        f"/v1/runs/{run_id}/events?cursor=evt:notinthisrun",
        headers=token(Role.DATA_SCIENTIST),
    )
    assert response.status_code == 422
    assert "notinthisrun" in response.text, (
        "Outside production the engine's message should be returned; without it a "
        "developer cannot tell which identifier was rejected."
    )


def test_malformed_body_is_a_typed_422_not_a_pydantic_dump(
    client: TestClient, token: Any, run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A schema violation uses the same error vocabulary as every other failure.

    Without the handler, FastAPI returns its own `{"detail": [...]}` shape, which both
    names internal field paths and forces a client to understand two error formats.
    """
    monkeypatch.setenv("CAUSALOG_ENV", "production")
    response = client.post(
        f"/v1/runs/{run_id}/counterfactuals",
        headers=token(Role.DATA_SCIENTIST),
        json={"interventions": [{"payload": {}}]},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "ContractViolationError"
    assert "detail" not in body
    _assert_clean(response.text)


def test_unauthenticated_does_not_distinguish_why(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, run_id: str
) -> None:
    """Every 401 is the same body, whatever was wrong with the credential.

    Distinguishing "no credential" from "bad signature" from "expired" would tell an
    unauthenticated caller which of its guesses was closest.
    """
    monkeypatch.setenv("CAUSALOG_ENV", "production")
    bodies = set()
    for headers in (
        {},
        {"Authorization": "Bearer not-a-token"},
        {"Authorization": "Basic abc"},
        {"Authorization": "Bearer aaaa.bbbb"},
    ):
        response = client.get(f"/v1/runs/{run_id}/events", headers=headers)
        assert response.status_code == 401
        payload = response.json()
        bodies.add((payload["error_code"], payload["message"]))
        _assert_clean(response.text)
    assert len(bodies) == 1, f"401 bodies differ by cause: {bodies}"


def test_error_bodies_always_carry_a_correlation_id(
    client: TestClient, token: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The id is the only link between a production body and the log that explains it."""
    monkeypatch.setenv("CAUSALOG_ENV", "production")
    for path, headers in (
        ("/v1/runs/run:absent0000000000/events", token(Role.DATA_SCIENTIST)),
        ("/v1/runs/run:absent0000000000/graph", token(Role.EXECUTIVE)),
        ("/v1/runs/run:absent0000000000/rule-pack", token(Role.EXECUTIVE)),
    ):
        response = client.get(path, headers=headers)
        assert response.status_code >= 400
        assert response.json()["correlation_id"]
        assert response.headers["X-Correlation-Id"]


def test_the_leak_detector_rejects_a_planted_leak() -> None:
    """The detector is observed to FAIL, so the assertions above mean something."""
    with pytest.raises(AssertionError):
        _assert_clean('{"message": "Traceback (most recent call last): ..."}')
    with pytest.raises(AssertionError):
        _assert_clean('{"message": "causalog.orchestration.facade failed"}')
    _assert_clean('{"message": "The request violates an interface contract."}')


def test_no_error_body_contains_a_raw_source_record(
    client: TestClient, token: Any, run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`CONVENTIONS.md` §7: reference the evidence record id, never the record.

    Checked structurally: an error body is small and flat, so a body carrying a row's worth
    of values would be conspicuous by size alone.
    """
    monkeypatch.setenv("CAUSALOG_ENV", "production")
    response = client.get(
        "/v1/runs/run:absent0000000000/events", headers=token(Role.DATA_SCIENTIST)
    )
    assert len(response.text) < 1_000, (
        "A production error body large enough to contain a source record: "
        f"{len(response.text)} bytes."
    )
    assert not re.search(r"\d{4,}\s*,\s*\d{4,}", response.text), (
        "The error body contains a comma-separated run of numbers, which is what a leaked "
        "source row looks like."
    )
