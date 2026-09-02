"""The two new enforcement scripts prove themselves, under pytest as well as in `make laws`.

ADR-0019 established the rule: every enforcement script ships `--self-test` and is observed
to REJECT before it is trusted, because a check observed only to pass has not been observed
to work (DEF-0001). `tests/law/test_enforcement_scripts_prove_themselves.py` holds that
rule for the existing scripts; these are the two this change adds.

Driving the rules as functions rather than shelling out is deliberate and follows the shape
`check_layers.check_file` already uses -- a self-test that can only run as a subprocess
cannot be debugged from a failure, and cannot assert anything about which rule fired.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture(scope="module")
def migration_pairs(repo_root: Path) -> None:
    """Load `scripts/check_migration_pairs.py` by path, as `conftest` does for the rest."""
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "check_migration_pairs", repo_root / "scripts" / "check_migration_pairs.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_migration_pairs"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def projection_drift(repo_root: Path) -> None:
    """Load `scripts/check_projection_drift.py` by path."""
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "check_projection_drift", repo_root / "scripts" / "check_projection_drift.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_projection_drift"] = module
    spec.loader.exec_module(module)
    return module


def test_the_migration_pair_self_test_passes(
    migration_pairs: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert migration_pairs.self_test() == 0
    assert "observed to reject and to accept" in capsys.readouterr().out


def test_the_real_migration_tree_is_paired(migration_pairs: ModuleType) -> None:
    """The scan itself, against the repository. Not a self-test -- the actual claim."""
    assert migration_pairs.check(migration_pairs.SQL_ROOT) == 0


def test_the_drift_self_test_passes(
    projection_drift: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert projection_drift.self_test() == 0
    assert "observed to reject a mismatch" in capsys.readouterr().out


def test_drift_is_reported_for_a_missing_node(projection_drift: ModuleType) -> None:
    drift = projection_drift.compare_counts(
        {"Entity": 3, "Event": 8, "State": 4, "CAUSES": 7},
        {"entity": 3, "event": 9, "state": 4, "causal_edge": 7},
        ("CAUSES",),
    )
    assert any("Event" in line for line in drift)


def test_additional_labels_are_not_counted_as_extra_nodes(projection_drift: ModuleType) -> None:
    """`Location` and `ExternalEvent` are subsets of Entity and Event, not additions.

    Planted because it is the mistake this check would most plausibly make: a comparison
    that summed every label would report drift on a projection that is perfectly correct,
    and a check that cries wolf gets routed around -- which is how LAW-DOMAIN lost a year
    of enforcement in DEF-0001.
    """
    assert (
        projection_drift.compare_counts(
            {
                "Entity": 3,
                "Event": 9,
                "State": 4,
                "CAUSES": 7,
                "Location": 2,
                "ExternalEvent": 3,
            },
            {"entity": 3, "event": 9, "state": 4, "causal_edge": 7},
            ("CAUSES",),
        )
        == []
    )
