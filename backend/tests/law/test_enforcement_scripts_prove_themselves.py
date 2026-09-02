"""Every enforcement script must be observed to fail, not merely to pass.

DEF-0001: the LAW-DOMAIN lint passed review for a week while catching almost nothing,
because its only negative evidence was a self-test asserting the wrong invariant. A check
that has never been seen to reject anything is not evidence of a law being enforced.

`check_layers.py` already has planted-case coverage in `test_layer_boundaries.py`, and the
stack preflight has its own in `tests/unit/test_stack_preflight.py`. This module covers the
rest: the law-copy check (positive-only before this), the dependency policy (no tests at
all), and the governance-record consistency check.

The script list is **derived from the directory**, not written out. It was a literal tuple
until 2026-08-29, which made it the trap ADR-0030 removed from ontology pack discovery: a
script added without editing that tuple would be covered by nothing, and zero parameterised
cases report exactly like a clean run. Two scripts landed with the persistence layer and
would have been silently uncovered.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.law

#: Scripts whose self-test reports in a different voice, with the marker each must print.
#: Named individually, so an exemption is a decision somebody made rather than a pattern
#: that quietly swallows a new script -- and each is still REQUIRED to print something, so
#: no entry here degrades to "trust the exit code".
_EXPECTED_MARKER = {
    # Added 2026-08-29 with the persistence layer.
    "check_migration_pairs": (0, "SELF-TEST:"),
    "check_projection_drift": (0, "SELF-TEST:"),
    # `check_determinism.py` is the one enforcement script with no self-test, and that is
    # its honest state rather than an omission: the gate cannot run at all until an
    # orchestration pipeline exists (OQ-014), so there is no behaviour to prove. It exits
    # 2 -- NOT-YET-RUNNABLE, the repository's established code for "this check could not
    # run", deliberately distinct from 0 so a missing gate never looks like a passing one.
    #
    # Asserting BOTH the code and the banner is what stops the exemption becoming a hole,
    # and it is what will fail here the day the pipeline lands and the banner stops being
    # true -- which is the point at which somebody must decide what its self-test proves.
    "check_determinism": (2, "NOT-YET-RUNNABLE"),
}


def _enforcement_scripts(repo_root: Path) -> tuple[str, ...]:
    """Return every `scripts/check_*.py`, DERIVED from the directory.

    Derived, never a checked-in list. This tuple was a literal until 2026-08-29, which made
    it the same trap ADR-0030 removed from ontology pack discovery: a script added without
    editing the list here would be covered by nothing, and zero parameterised cases report
    exactly like a clean run. Two scripts landed with the persistence layer and would have
    been silently uncovered.

    Raises on an empty result for the same reason: an empty parametrize is a pass.
    """
    found = tuple(
        sorted(path.stem for path in (repo_root / "scripts").glob("check_*.py") if path.is_file())
    )
    if not found:
        raise AssertionError(
            "No enforcement scripts discovered under scripts/. An empty parametrize "
            "reports as a pass, which is exactly the unrunnable-check-reads-as-passing "
            "failure this module exists to prevent (DEF-0001)."
        )
    return found


def test_every_enforcement_script_is_discovered(repo_root: Path) -> None:
    """The derived list is non-empty and contains the checks this repository relies on."""
    discovered = set(_enforcement_scripts(repo_root))
    for expected in (
        "check_domain_independence",
        "check_layers",
        "check_law_copies",
        "check_dependency_policy",
        "check_governance_consistency",
        "check_metrics_are_declared",
        "check_migration_pairs",
        "check_projection_drift",
    ):
        assert expected in discovered, (
            f"{expected} was not discovered under scripts/. Either it was removed without "
            "an ADR, or the discovery glob no longer matches the naming convention."
        )


@pytest.mark.parametrize("script", _enforcement_scripts(Path(__file__).resolve().parents[3]))
def test_every_law_script_has_a_passing_self_test(repo_root: Path, script: str) -> None:
    """`--self-test` exists on every enforcement script and passes.

    A missing flag exits non-zero, so a script that never grew one fails here rather than
    being quietly trusted.
    """
    result = subprocess.run(  # noqa: S603 -- fixed argv, no user input
        [sys.executable, str(repo_root / "scripts" / f"{script}.py"), "--self-test"],
        capture_output=True,
        text=True,
        check=False,
    )
    expected_code, expected_line = _EXPECTED_MARKER.get(script, (0, "self-test passed"))
    assert result.returncode == expected_code, (
        f"{script} --self-test exited {result.returncode}, expected {expected_code}:\n"
        f"{result.stdout}{result.stderr}"
    )
    assert expected_line in result.stdout, (
        f"{script} --self-test exited {expected_code} without reporting why. An exit code "
        f"alone is not evidence the self-test ran; expected {expected_line!r} in:\n"
        f"{result.stdout}"
    )


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


# --------------------------------------------------------------------------------------
# check_metrics_are_declared.py
# --------------------------------------------------------------------------------------
#
# The self-test above proves the matcher on snippets. These prove what a snippet cannot:
# that the SCAN rejects a real file, that a scaffold-only package does not count as
# scanned, and that the scan is genuinely runnable now that `graph_engine` holds
# implementation (modules 5-6, the P2 exit).


def test_a_planted_metric_computation_is_rejected(metric_lint: ModuleType) -> None:
    """The defect in its commonest shape: a metric named on the left, a formula on the right."""
    source = "def f(arrival: float, promised: float) -> float:\n    delay = arrival - promised\n"

    assert [name for _, name, _ in metric_lint.violations_in(source)] == ["delay"]


def test_a_metric_operand_is_rejected_wherever_it_appears(metric_lint: ModuleType) -> None:
    """Naming the result something innocuous must not launder the arithmetic."""
    source = "value = unit_cost * units\n"

    assert [name for _, name, _ in metric_lint.violations_in(source)] == ["unit_cost"]


def test_ordinary_bookkeeping_is_not_rejected(metric_lint: ModuleType) -> None:
    """Without this, a lint that rejected everything would look correct."""
    source = "total = 0\nfor index in range(10):\n    total += index + 1\n"

    assert metric_lint.violations_in(source) == []


def test_a_scaffold_only_package_does_not_count_as_scanned(
    metric_lint: ModuleType, tmp_path: Path
) -> None:
    """DEF-0001, structurally: a docstring-only module must not make the scan look run."""
    scaffold = tmp_path / "__init__.py"
    scaffold.write_text('"""Single responsibility: nothing yet."""\n', encoding="utf-8")
    real = tmp_path / "engine.py"
    real.write_text("def f() -> int:\n    return 1\n", encoding="utf-8")

    assert not metric_lint.carries_implementation(scaffold)
    assert metric_lint.carries_implementation(real)


def test_the_scan_is_runnable_now_that_a_reasoning_module_exists(repo_root: Path) -> None:
    """Exit 0, not 2. `graph_engine` (modules 5-6) is the P2 exit -- reasoning code exists.

    This test replaces `test_the_scan_reports_not_runnable_while_the_engine_is_unbuilt`,
    which asserted `NOT-YET-RUNNABLE` and documented its own expiry: "This assertion is
    expected to fail the day the first reasoning module lands, which is the point." Timeline
    Builder and State Engine are that day. The CI job's `|| test $? -eq 2` tolerance was
    removed in the same change (`.github/workflows/ci.yml`) -- a real violation must now
    fail the build rather than being swallowed alongside the exemption.
    """
    result = subprocess.run(  # noqa: S603 -- fixed argv, no user input
        [sys.executable, str(repo_root / "scripts" / "check_metrics_are_declared.py")],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "clean across" in result.stdout


# --- ADR-0031: taint tracking and hard-coded thresholds --------------------------------


def test_a_metric_laundered_through_an_unnamed_variable_is_rejected(
    metric_lint: ModuleType,
) -> None:
    """The hole ADR-0030 left open: nothing in the arithmetic is named for a metric.

    The metric is named in a string key, which is where a declared quantity actually enters
    engine code. Under the name-only matcher this file was clean.
    """
    source = 'raw = event["shipping_delay"]\nvalue = raw - baseline\n'

    assert [name for _, name, _ in metric_lint.violations_in(source)] == ["raw"]


def test_taint_survives_a_chain_of_rebindings(metric_lint: ModuleType) -> None:
    """One rename must not launder it; three must not either."""
    source = 'a = row["delay_hours"]\nb = a\nc = b + 1\n'

    assert metric_lint.violations_in(source)


def test_taint_does_not_cross_a_function_boundary(metric_lint: ModuleType) -> None:
    """Per-scope taint. A lint that invents violations is disabled as fast as one that misses.

    `value` holds a metric in `f` and an index in `g`. Sharing one taint set across the file
    would report the second as a violation, and the report would be wrong.
    """
    source = (
        'def f(row):\n    value = row["delay_hours"]\n    return value\n\n\n'
        "def g(i):\n    value = i - 1\n    return value\n"
    )

    assert metric_lint.violations_in(source) == []


def test_a_metric_compared_against_a_literal_is_rejected(metric_lint: ModuleType) -> None:
    """A hard-coded threshold is domain policy written into engine code."""
    source = "if delay > 48:\n    pass\n"

    assert [name for _, name, _ in metric_lint.violations_in(source)] == ["delay"]


def test_a_metric_compared_against_a_variable_is_not_rejected(metric_lint: ModuleType) -> None:
    """The deliberate limit, pinned. Matching this would fire on every guard clause."""
    source = "if delay > threshold:\n    pass\n"

    assert metric_lint.violations_in(source) == []


def test_a_metric_compared_against_a_non_numeric_literal_is_not_rejected(
    metric_lint: ModuleType,
) -> None:
    """`cost_class == 'CHEAP'` reads a declared vocabulary member; it bounds nothing."""
    source = "if cost_class == 'CHEAP':\n    pass\n"

    assert metric_lint.violations_in(source) == []
