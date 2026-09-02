"""Paths the ontology-boundary tests share."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def packs_root() -> Path:
    """The directory holding the shipped domain packs."""
    return REPO_ROOT / "ontology" / "packs"


@pytest.fixture(scope="session")
def runtime_source_root() -> Path:
    """The source of the loader, which must name no domain concept."""
    return REPO_ROOT / "backend" / "src" / "causalog" / "ontology_runtime"
