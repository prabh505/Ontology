"""LAW-EVENT: a row and a DataFrame stop at L2. Nothing above `ingestion` may see one.

The two boundaries `docs/architecture.md` §1 calls load-bearing, checked at the level a lint
cannot reach: forbidden edge F7 bans a tabular IMPORT above rank 3, and this file bans the
TYPE from a public signature -- a module could hold a `RawRecord` without importing `csv`.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import causalog
from causalog.core.ports.source import RawRecord, RawRecordBatch

pytestmark = pytest.mark.law

PACKAGE_ROOT = Path(causalog.__file__).resolve().parent

#: Packages that may name a raw record. `core.ports` DECLARES the types; `ingestion` and
#: `persistence.sources` are the only consumers LAW-EVENT admits.
PERMITTED = ("core", "ingestion", "persistence")

FORBIDDEN_NAMES = (RawRecord.__name__, RawRecordBatch.__name__)


def _python_files_above_l2() -> list[Path]:
    """Return every distribution file outside the packages permitted to hold a row."""
    found = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        relative = path.relative_to(PACKAGE_ROOT).as_posix()
        if relative.split("/")[0] in PERMITTED:
            continue
        found.append(path)
    return found


def test_the_scan_covers_something() -> None:
    """Zero files scanned is not the same answer as zero violations found (DEF-0001)."""
    assert (
        _python_files_above_l2()
    ), "this law test scanned no file, which reads identically to passing"


def test_no_package_above_l2_names_a_raw_record() -> None:
    offenders = []
    for path in _python_files_above_l2():
        text = path.read_text(encoding="utf-8")
        for name in FORBIDDEN_NAMES:
            if name in text:
                offenders.append(f"{path.relative_to(PACKAGE_ROOT)}: {name}")
    assert not offenders, (
        "LAW-EVENT: the reasoning core computes over Event, Entity, State, Transition and "
        f"Relationship, never over rows. Found: {offenders}"
    )


def test_the_data_adapter_returns_no_raw_record_across_its_public_surface() -> None:
    """Module 1's output is a report and a layer on disk, never the rows it read."""
    from causalog.ingestion.data_adapter import import_dataset

    signature = inspect.signature(import_dataset)
    annotation = str(signature.return_annotation)
    for name in FORBIDDEN_NAMES:
        assert name not in annotation


def test_no_package_above_rank_two_imports_a_tabular_library() -> None:
    """F7 at the type level: `csv` may be imported by `persistence`, and nowhere above L2."""
    offenders = []
    for path in _python_files_above_l2():
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import csv", "from csv", "import pandas", "from pandas")):
                offenders.append(f"{path.relative_to(PACKAGE_ROOT)}: {stripped}")
    assert not offenders, f"tabular import above rank 2: {offenders}"
