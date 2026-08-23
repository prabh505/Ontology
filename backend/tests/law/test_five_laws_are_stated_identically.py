"""`HANDOFF.md` §2 check 1, executed rather than eyeballed."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.law


def test_law_copies_agree(repo_root: Path) -> None:
    result = subprocess.run(  # noqa: S603 -- fixed argv, no user input
        [sys.executable, str(repo_root / "scripts" / "check_law_copies.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout
