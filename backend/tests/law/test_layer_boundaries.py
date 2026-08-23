"""Forbidden dependency edges must fail the build, not merely be documented."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.law


def _plant(
    layer_lint: ModuleType,
    tmp_path: Path,
    package: str,
    source: str,
    monkeypatch: pytest.MonkeyPatch,
) -> int:
    target = tmp_path / package
    target.mkdir(parents=True, exist_ok=True)
    planted = target / "planted.py"
    planted.write_text(source)
    monkeypatch.setattr(layer_lint, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(layer_lint, "PACKAGE_ROOT", tmp_path)
    return layer_lint.check_file(planted)


@pytest.mark.parametrize(
    ("package", "source", "rule"),
    [
        ("core", "from causalog.causal_engine import scorer\n", "F1"),
        ("graph_engine", "import causalog.causal_engine\n", "F6"),
        ("causal_engine", "from causalog.persistence.neo4j import driver\n", "F4"),
        ("api", "from causalog.graph_engine import builder\n", "F5"),
        ("causal_engine", "from causalog.ontology_runtime import loader\n", "F3"),
        ("causal_engine", "import pandas\n", "F7"),
        ("core", "import redis\n", "F8"),
        ("causal_engine", "import torch\n", "F9"),
    ],
)
def test_forbidden_edge_is_rejected(
    layer_lint: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    package: str,
    source: str,
    rule: str,
) -> None:
    assert _plant(layer_lint, tmp_path, package, source, monkeypatch) >= 1, rule


@pytest.mark.parametrize(
    ("package", "source"),
    [
        ("causal_engine", "from causalog.core.types import Event\n"),  # downward: allowed
        ("orchestration", "from causalog.persistence.postgres import repo\n"),  # F4 carve-out
        ("core", "import hashlib\n"),  # stdlib: always allowed
        ("core", "from pydantic import BaseModel\n"),  # F8 carve-out
        ("api", "from causalog.orchestration import facade\n"),  # F5 carve-out
        ("extraction", "from causalog.ontology_runtime import loader\n"),  # F3 carve-out
    ],
)
def test_permitted_edge_is_accepted(
    layer_lint: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    package: str,
    source: str,
) -> None:
    assert _plant(layer_lint, tmp_path, package, source, monkeypatch) == 0


def test_rank_table_matches_the_architecture_document(
    layer_lint: ModuleType, repo_root: Path
) -> None:
    """The document's layer table and the lint's rank table are two copies of one rule."""
    document = (repo_root / "docs" / "architecture.md").read_text()
    for package in layer_lint.LAYER_RANKS:
        assert f"`{package}`" in document, package
