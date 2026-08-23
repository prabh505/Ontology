"""Every enforcement script must be observed to fail, not merely to pass.

DEF-0001: the LAW-DOMAIN lint passed review for a week while catching almost nothing,
because its only negative evidence was a self-test asserting the wrong invariant. A check
that has never been seen to reject anything is not evidence of a law being enforced.

`check_layers.py` already has planted-case coverage in `test_layer_boundaries.py`. This
module covers the two that had none: the law-copy check (positive-only) and the dependency
policy (no tests at all).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.law

SCRIPTS = (
    "check_domain_independence",
    "check_layers",
    "check_law_copies",
    "check_dependency_policy",
    "check_governance_consistency",
)


@pytest.mark.parametrize("script", SCRIPTS)
def test_every_law_script_has_a_passing_self_test(repo_root: Path, script: str) -> None:
    """`--self-test` exists on all four and passes. A missing flag exits non-zero here."""
    result = subprocess.run(  # noqa: S603 -- fixed argv, no user input
        [sys.executable, str(repo_root / "scripts" / f"{script}.py"), "--self-test"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"{script} --self-test failed:\n{result.stdout}{result.stderr}"
    assert "self-test passed" in result.stdout, result.stdout


# --------------------------------------------------------------------------------------
# check_law_copies.py
# --------------------------------------------------------------------------------------


def _laws(text_per_law: list[str]) -> list[str]:
    names = ("EVENT", "TIME", "PROVENANCE", "DOMAIN", "EVIDENCE")
    return [f"{n}. **LAW-{names[n - 1]}** — {body}" for n, body in enumerate(text_per_law, start=1)]


def test_divergence_is_detected(law_copies: ModuleType) -> None:
    """The check the repository relies on must actually reject a diverged copy."""
    left = _laws(["a", "b", "c", "d", "e"])
    right = _laws(["a", "b", "CHANGED", "d", "e"])
    assert law_copies.compare(left, right) == 1


def test_missing_law_is_detected(law_copies: ModuleType) -> None:
    """Four laws is a defect even if both files agree on the four."""
    four = _laws(["a", "b", "c", "d"])
    assert law_copies.compare(four, four) == 1


def test_identical_copies_are_accepted(law_copies: ModuleType) -> None:
    """Without this, a check that rejected everything would look correct."""
    five = _laws(["a", "b", "c", "d", "e"])
    assert law_copies.compare(five, five) == 0


def test_law_line_parser_ignores_prose(law_copies: ModuleType, tmp_path: Path) -> None:
    """Only the numbered law lines count; surrounding prose must not be mistaken for one."""
    document = tmp_path / "probe.md"
    document.write_text(
        "# Heading\n\nSome prose mentioning LAW-EVENT in passing.\n\n"
        + "\n".join(_laws(["a", "b", "c", "d", "e"]))
        + "\n\nMore prose.\n"
    )
    assert len(law_copies.law_block(document)) == 5


# --------------------------------------------------------------------------------------
# check_dependency_policy.py
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "requirement", ["fastapi>=0.115.6", "fastapi", "fastapi~=0.115", "fastapi==latest"]
)
def test_range_pin_rejected(dependency_policy: ModuleType, requirement: str) -> None:
    """`CONVENTIONS.md` §12: pin exact versions. No ranges, no `latest`."""
    assert dependency_policy.check_pins([requirement]) == 1


def test_exact_pin_accepted(dependency_policy: ModuleType) -> None:
    assert dependency_policy.check_pins(["pydantic==2.10.4", "neo4j==5.27.0"]) == 0


def test_undeclared_package_rejected(dependency_policy: ModuleType) -> None:
    """A dependency nobody wrote an ADR for is a defect, not a convenience."""
    adr = "ADR-0015 names pydantic."
    assert dependency_policy.check_adr_coverage(["requests==2.32.3"], adr) == 1


def test_missing_adr_rejected(dependency_policy: ModuleType) -> None:
    assert dependency_policy.check_adr_coverage(["pydantic==2.10.4"], "no adr log here") == 1


@pytest.mark.parametrize(
    "requirement", ["torch==2.5.1", "pgmpy==0.1.26", "dowhy==0.12", "torch-geometric==2.6.1"]
)
def test_blocked_declaration_rejected(dependency_policy: ModuleType, requirement: str) -> None:
    """ADR-0003 defers every ML library to V2+."""
    assert dependency_policy.check_blocked_declarations([requirement]) == 1


def test_blocked_import_rejected(dependency_policy: ModuleType, tmp_path: Path) -> None:
    """The ban covers imports too; a declaration-only check would miss a vendored copy."""
    package = tmp_path / "src"
    package.mkdir()
    (package / "probe.py").write_text("import torch\nfrom dowhy import CausalModel\n")
    assert dependency_policy.check_blocked_imports(("src",), tmp_path) == 2


def test_clean_tree_has_no_blocked_imports(dependency_policy: ModuleType, tmp_path: Path) -> None:
    package = tmp_path / "src"
    package.mkdir()
    (package / "probe.py").write_text("import networkx\nfrom pydantic import BaseModel\n")
    assert dependency_policy.check_blocked_imports(("src",), tmp_path) == 0


# --------------------------------------------------------------------------------------
# check_governance_consistency.py
# --------------------------------------------------------------------------------------

_DECISIONS = (
    "## ADR-0006 — a\n\n- **Status:** accepted\n- **Supersedes:** —\n\n"
    "## ADR-0010 — b\n\n- **Status:** superseded by ADR-0019\n- **Supersedes:** —\n\n"
    "## ADR-0019 — c\n\n- **Status:** accepted\n- **Supersedes:** ADR-0010\n"
)


def test_open_question_answered_by_an_accepted_adr_is_rejected(governance: ModuleType) -> None:
    """The OQ-004 / OQ-008 defect class, which occurred twice before it got a check."""
    context = "| OQ-008 | q | d | c | ADR-0006 |\n"
    assert governance.check(context, _DECISIONS) == 1


def test_question_both_struck_and_open_is_rejected(governance: ModuleType) -> None:
    context = (
        "| ~~OQ-001~~ **RESOLVED by ADR-0006** | q | d | c | ADR-0006 |\n"
        "| OQ-001 | q | d | c | ADR-0006 |\n"
    )
    assert governance.check(context, _DECISIONS) >= 1


def test_closure_naming_a_nonexistent_adr_is_rejected(governance: ModuleType) -> None:
    context = "| ~~OQ-002~~ **RESOLVED by ADR-0099** | q | d | c | ADR-0099 |\n"
    assert governance.check(context, _DECISIONS) == 1


def test_unacknowledged_supersession_is_rejected(governance: ModuleType) -> None:
    """A supersession must be visible from both ADRs, or history reads wrong from one side."""
    decisions = (
        "## ADR-0010 — b\n\n- **Status:** accepted\n- **Supersedes:** —\n\n"
        "## ADR-0019 — c\n\n- **Status:** accepted\n- **Supersedes:** ADR-0010\n"
    )
    assert governance.check("", decisions) == 1


def test_the_real_repository_record_is_consistent(governance: ModuleType, repo_root: Path) -> None:
    context = (repo_root / "CONTEXT.md").read_text()
    decisions = (repo_root / "DECISIONS.md").read_text()
    assert governance.check(context, decisions) == 0
