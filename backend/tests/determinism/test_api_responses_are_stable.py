"""`CONVENTIONS.md` §11: two identical requests produce byte-identical bodies.

The section names what is excluded and this file excludes exactly that and nothing more:
`execution_id`, `correlation_id`, wall-clock timestamps, and performance measurements. Any
other difference between two responses to the same request is a determinism defect.

Excluding by KEY rather than by value is deliberate. Stripping "anything that looks like a
timestamp" would also strip `occurred_at`, which is engine output and must be stable; the
exclusion list is therefore the four named things, applied at every depth.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from causalog.core.ports.identity import Role

#: Exactly `CONVENTIONS.md` §11's exclusions. `generated_at` is the response's own wall
#: clock; `timing` holds performance measurements; the two identifiers are the ones §9
#: permits to be random.
EXCLUDED_KEYS = frozenset({"execution_id", "correlation_id", "generated_at", "timing"})

REQUESTS = (
    "/v1/runs/{run_id}/events?limit=5",
    "/v1/runs/{run_id}/graph",
    "/v1/runs/{run_id}/ontology",
    "/v1/runs/{run_id}/rule-pack",
    "/v1/runs/{run_id}/root-causes/evt:absent00000000",
)


def _stripped(node: Any) -> Any:
    """Return a body with the declared exclusions removed at every depth."""
    if isinstance(node, dict):
        return {
            key: _stripped(value) for key, value in sorted(node.items()) if key not in EXCLUDED_KEYS
        }
    if isinstance(node, list):
        return [_stripped(item) for item in node]
    return node


def _canonical(body: Any) -> str:
    """Render a body for comparison, sorted and separator-fixed."""
    return json.dumps(_stripped(body), sort_keys=True, separators=(",", ":"))


@pytest.mark.determinism
@pytest.mark.parametrize("path", REQUESTS, ids=lambda path: path.split("/")[-1])
def test_two_identical_requests_agree(
    client: TestClient, token: Any, run_id: str, path: str
) -> None:
    """The same request twice yields the same body, modulo the declared exclusions."""
    headers = token(Role.DATA_SCIENTIST)
    url = path.format(run_id=run_id)
    first = client.get(url, headers=headers)
    second = client.get(url, headers=headers)
    assert first.status_code == second.status_code == 200, first.text
    assert _canonical(first.json()) == _canonical(second.json()), (
        f"Two identical requests to {url} produced different bodies. Only "
        f"{sorted(EXCLUDED_KEYS)} may differ (CONVENTIONS.md §11)."
    )


@pytest.mark.determinism
def test_the_comparison_would_notice_a_real_difference(
    client: TestClient, token: Any, run_id: str
) -> None:
    """The stripper is observed to preserve a real difference.

    Without this, `_stripped` returning a constant would make every assertion above pass.
    """
    response = client.get(f"/v1/runs/{run_id}/events?limit=5", headers=token(Role.DATA_SCIENTIST))
    body = response.json()
    altered = json.loads(response.text)
    altered["data"]["sequenced_by"] = "something-else"
    assert _canonical(body) != _canonical(altered)


@pytest.mark.determinism
def test_excluded_keys_really_do_vary(client: TestClient, token: Any, run_id: str) -> None:
    """The exclusions are not decorative: `correlation_id` genuinely differs per request.

    If it did not, excluding it would be hiding nothing and the test above would be
    stronger than it claims. This asserts the exclusion list earns its place.
    """
    headers = token(Role.DATA_SCIENTIST)
    first = client.get(f"/v1/runs/{run_id}/events", headers=headers)
    second = client.get(f"/v1/runs/{run_id}/events", headers=headers)
    assert (
        first.headers["X-Correlation-Id"] != second.headers["X-Correlation-Id"]
    ), "Two requests shared a correlation id, so it does not identify a request."


@pytest.mark.determinism
def test_pagination_is_stable_across_requests(client: TestClient, token: Any, run_id: str) -> None:
    """A cursor names a position in a canonical sequence, so paging is reproducible."""
    headers = token(Role.DATA_SCIENTIST)
    first = client.get(f"/v1/runs/{run_id}/events?limit=3", headers=headers).json()
    cursor = first["data"]["next_cursor"]
    if cursor is None:
        pytest.skip("The shared run holds fewer events than one page.")
    page_a = client.get(f"/v1/runs/{run_id}/events?limit=3&cursor={cursor}", headers=headers).json()
    page_b = client.get(f"/v1/runs/{run_id}/events?limit=3&cursor={cursor}", headers=headers).json()
    assert _canonical(page_a) == _canonical(page_b)
    assert [item["event_id"] for item in page_a["data"]["items"]] != [
        item["event_id"] for item in first["data"]["items"]
    ], "The second page repeated the first, so the cursor advanced nothing."
