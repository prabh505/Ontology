"""Paths the ontology-runtime tests share."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="session")
def packs_root() -> Path:
    """The directory holding the shipped domain packs."""
    return REPO_ROOT / "ontology" / "packs"


@pytest.fixture(scope="session")
def fixtures_root() -> Path:
    """The directory holding the valid and invalid pack fixtures."""
    return Path(__file__).resolve().parents[2] / "fixtures" / "ontology"
