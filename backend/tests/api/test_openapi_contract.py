"""The published OpenAPI document is the contract, and it matches the application.

`CONVENTIONS.md` §14 names `tests/api/` the place response schema is asserted. Two claims
here, and they are different:

1. The document committed at `docs/openapi.json` is what the application produces. A
   contract that has drifted from the code is worse than none, because clients trust it.
2. Real responses validate against the schemas the document declares -- which is what makes
   claim 1 worth anything, since a document can be current and still describe the code
   wrongly if the response models lie about what handlers return.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from causalog.api.routes.health import API_SCHEMA_VERSION
from causalog.core.ports.identity import Role

DOCUMENT_PATH = Path(__file__).resolve().parents[3] / "docs" / "openapi.json"


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    """The committed OpenAPI document."""
    assert (
        DOCUMENT_PATH.is_file()
    ), f"{DOCUMENT_PATH} is missing. Run `python scripts/export_openapi.py --write`."
    return json.loads(DOCUMENT_PATH.read_text(encoding="utf-8"))


def test_the_published_document_is_current(document: dict[str, Any]) -> None:
    """`docs/openapi.json` is what the application produces, byte for byte."""
    import sys

    sys.path.insert(0, str(DOCUMENT_PATH.parents[1] / "scripts"))
    from export_openapi import render_document

    assert DOCUMENT_PATH.read_text(encoding="utf-8") == render_document(), (
        "The published OpenAPI document is stale. It is generated, never hand-edited: run "
        "`python scripts/export_openapi.py --write` and commit the result."
    )
    assert document["paths"], "The document declares no paths."


def test_every_declared_path_is_reachable(document: dict[str, Any], client: TestClient) -> None:
    """Every path the document declares exists on the running application.

    A document naming a route that does not exist sends clients to a 404 and is the most
    expensive kind of documentation error, because it looks authoritative.
    """
    declared = set(document["paths"])
    live = {
        route.path
        for route in client.app.routes  # type: ignore[attr-defined]
        if getattr(route, "methods", None)
    }
    missing = declared - live
    assert not missing, f"The document declares paths the application does not serve: {missing}"


def test_the_response_envelope_is_in_the_schema(document: dict[str, Any]) -> None:
    """The envelope's required fields are published, so a client can rely on them."""
    schemas = document["components"]["schemas"]
    envelope_models = [name for name in schemas if name.startswith("ApiResponse")]
    assert envelope_models, "No ApiResponse schema is published."
    sample = schemas[envelope_models[0]]
    for field in ("scope", "provenance", "standing", "stage_status", "timing", "generated_at"):
        assert field in sample["properties"], (
            f"The published ApiResponse schema omits {field!r}, so a client cannot know it "
            "is guaranteed."
        )


def test_confidence_schema_requires_components(document: dict[str, Any]) -> None:
    """LAW-EVIDENCE is visible in the contract, not only in the implementation.

    A client generating types from this document must end up with a confidence type that
    cannot be built without components; otherwise the guarantee stops at our boundary.
    """
    confidence = document["components"]["schemas"].get("ConfidenceView")
    assert confidence is not None, "ConfidenceView is not published in the contract."
    assert "components" in confidence.get("required", []), (
        "The published ConfidenceView does not require `components`, so the contract "
        "permits a bare confidence even though the implementation does not."
    )
    assert confidence["properties"]["components"].get("minItems") == 1


def test_health_publishes_the_frozen_shell_version(client: TestClient) -> None:
    """The frozen API shell version is reachable without credentials.

    Unauthenticated on purpose: a client needs to know which contract it is talking to
    before it can construct a credential the server will accept.
    """
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["api_schema_version"] == API_SCHEMA_VERSION


def test_real_responses_match_their_declared_schema(
    client: TestClient, token: Any, run_id: str, document: dict[str, Any]
) -> None:
    """A live response carries every property its schema marks required.

    Deliberately checks required-field presence rather than running a full JSON Schema
    validator: adding a validator would be a new dependency (`CONVENTIONS.md` §12) to check
    a property pydantic already enforces on the way out. What pydantic does NOT catch is a
    handler returning a model whose schema was never published, which this does.
    """
    response = client.get(f"/v1/runs/{run_id}/rule-pack", headers=token(Role.DATA_SCIENTIST))
    assert response.status_code == 200
    body = response.json()

    schemas = document["components"]["schemas"]
    name = next(key for key in schemas if key.startswith("ApiResponse_") and "RulePackView" in key)
    for field in schemas[name].get("required", []):
        assert (
            field in body
        ), f"The live response omits {field!r}, which its published schema requires."
