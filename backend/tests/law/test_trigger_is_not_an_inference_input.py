"""ADR-0020: `Event.trigger` is observed evidence, never an input to inference.

The moment a causal-engine code path reads `trigger`, an `OBSERVED` field has become a
causal assertion that skipped the LAW-TIME gate and the LAW-EVIDENCE gate at once. That is
LAW-PROVENANCE violated by construction, and it would look like a fact rather than a claim.

**Limit of this test, stated so it is not mistaken for more than it is:** no module is
implemented yet, so today it passes vacuously. It exists to fail the moment module 9 is
written against the field. Re-read it when the Candidate Cause Generator lands.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.law

# Packages that draw or score edges. None of them may reference the trigger field.
INFERENCE_PACKAGES = ("causal_engine", "counterfactual_engine", "recommendation_engine")


def _inference_sources(repo_root: Path) -> list[Path]:
    package_root = repo_root / "backend" / "src" / "causalog"
    return [
        path
        for package in INFERENCE_PACKAGES
        for path in sorted((package_root / package).rglob("*.py"))
    ]


def test_no_inference_package_reads_the_trigger_field(repo_root: Path) -> None:
    offenders: list[str] = []
    for path in _inference_sources(repo_root):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            reads_attribute = isinstance(node, ast.Attribute) and node.attr == "trigger"
            reads_key = (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value == "trigger"
            )
            if reads_attribute or reads_key:
                relative = path.relative_to(repo_root).as_posix()
                offenders.append(f"{relative}:{node.lineno}")

    assert not offenders, (
        "ADR-0020: these inference code paths reference `trigger`, which turns an OBSERVED "
        f"field into an unscored causal claim: {offenders}. If the recorded mechanism is "
        "genuinely informative, promote it through the scoring path as a named "
        "ConfidenceVector component -- never by reading the field directly."
    )


def test_the_guard_covers_the_packages_that_can_draw_edges(repo_root: Path) -> None:
    """A guard scoped to a package that does not exist would pass and prove nothing."""
    package_root = repo_root / "backend" / "src" / "causalog"
    for package in INFERENCE_PACKAGES:
        assert (package_root / package).is_dir(), package
