"""Shared fixtures and the Hypothesis seed contract.

`scripts/` is not part of the installed distribution -- the enforcement scripts are
standard-library only and deliberately importable without it (ADR-0016). They are loaded
here by path so that the checks which guard the Five Laws are themselves tested.

Hypothesis seed contract (ADR-0024, CONVENTIONS.md §11 and §12)
--------------------------------------------------------------
Hypothesis is a randomized generator, and `CONVENTIONS.md` §11 requires byte-identical
reruns. The `derandomize=True` profile resolves that: Hypothesis derives its choices from
a hash of the test itself rather than from entropy, so a given commit explores the same
inputs on every machine and a failure reproduces from the test name alone.

The cost is real and accepted: a derandomized suite stops finding *new* counterexamples on
reruns, so it is a regression net rather than a search. Widening the search is a deliberate
act -- run with `--hypothesis-seed=random` locally -- and never the CI default, because a
gate that fails on a different input each week cannot be told apart from a flaky one.

`print_blob` is off because its output embeds a random-looking token that would make two
otherwise identical failure reports differ.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from hypothesis import HealthCheck, Verbosity, settings

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"

settings.register_profile(
    "deterministic",
    derandomize=True,
    print_blob=False,
    verbosity=Verbosity.normal,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
settings.load_profile("deterministic")


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
def confidence_lint() -> ModuleType:
    return _load("check_confidence_is_a_vector")


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


@pytest.fixture(scope="session")
def stack_preflight() -> ModuleType:
    return _load("check_stack_preflight")


@pytest.fixture(scope="session")
def metric_lint() -> ModuleType:
    return _load("check_metrics_are_declared")


# ---------------------------------------------------------------------------------------
# Ingestion fixtures (modules 1 and 2).
#
# They live at the root rather than under `tests/unit/ingestion/` because the determinism
# and law suites need the same real pack, real mapping and committed sample. Duplicating
# them per directory would let two copies drift, and a determinism test running against a
# different mapping from the unit tests would be measuring something else.
# ---------------------------------------------------------------------------------------


def _repository_root() -> Path:
    """Walk up to the directory holding `ontology/packs`.

    A hard-coded `parents[N]` is silently wrong the moment this file moves one directory,
    and it fails as "file not found" rather than as "your index is off by one".
    """
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "ontology" / "packs").is_dir():
            return candidate
    raise RuntimeError("no repository root above this file holds ontology/packs")


DATACO_PACK_DIRECTORY = _repository_root() / "ontology" / "packs" / "dataco"


@pytest.fixture(scope="session")
def dataco_pack() -> Any:
    """The real DataCo ontology pack.

    The real one, not a stub. A mapping test against a hand-written pack would only prove
    the mapping loads against a pack somebody wrote to make it load.
    """
    from causalog.ontology_runtime import load_pack

    return load_pack(DATACO_PACK_DIRECTORY / "ontology.yaml").pack


@pytest.fixture(scope="session")
def sample_probe() -> Any:
    """The probe of the committed sample, stored in `cp1252` like the real distribution."""
    from causalog.persistence.sources.delimited import probe_source
    from tests.fixtures.dataco import SAMPLE_CSV

    return probe_source(SAMPLE_CSV)


@pytest.fixture(scope="session")
def dataco_mapping(dataco_pack: Any, sample_probe: Any) -> Any:
    """The real, CONFIRMED DataCo mapping, loaded against the sample's header."""
    from causalog.ingestion.schema_mapper import load_mapping

    return load_mapping(
        DATACO_PACK_DIRECTORY / "mapping.yaml", dataco_pack, header=sample_probe.header
    ).mapping


@pytest.fixture(scope="session")
def dataco_coverage(dataco_pack: Any, sample_probe: Any) -> Any:
    """The coverage assessment of the real mapping against the real pack."""
    from causalog.ingestion.schema_mapper import inspect_mapping

    _mapping, coverage = inspect_mapping(
        DATACO_PACK_DIRECTORY / "mapping.yaml", dataco_pack, header=sample_probe.header
    )
    return coverage
