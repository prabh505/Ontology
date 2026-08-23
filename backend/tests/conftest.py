"""Shared fixtures.

`scripts/` is not part of the installed distribution -- the enforcement scripts are
standard-library only and deliberately importable without it (ADR-0016). They are loaded
here by path so that the checks which guard the Five Laws are themselves tested.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def domain_lint() -> ModuleType:
    return _load("check_domain_independence")


@pytest.fixture(scope="session")
def layer_lint() -> ModuleType:
    return _load("check_layers")


@pytest.fixture(scope="session")
def law_copies() -> ModuleType:
    return _load("check_law_copies")


@pytest.fixture(scope="session")
def dependency_policy() -> ModuleType:
    return _load("check_dependency_policy")


@pytest.fixture(scope="session")
def governance() -> ModuleType:
    return _load("check_governance_consistency")
