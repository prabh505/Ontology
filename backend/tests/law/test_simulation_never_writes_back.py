"""Module 13 cannot write to history, state a claim, or own the diagnostic standing.

A behavioural test proves the simulator behaved on the inputs it was given. This file proves
something stronger and more durable: that **there is no second path**. A future module that
promoted an edge of its own, or revised an observed fact, or minted the disowned standing,
would fail here on the day it was written, naming the file -- which is the shape
`test_law_time_gates_every_promotion.py` established and the reason it is worth the
awkwardness of asserting over an AST.

Four structural claims, each mapping to a decision that would otherwise be re-derived badly:

1. `ProvenanceClass.INFERRED` is never assigned. `causal_graph_builder/policy.py` is the
   engine's one promotion site (ADR-0054), and a simulator promoting anything would be a
   second opinion about what the engine asserts.
2. `CausalEdge` is never constructed. Module 13 holds no `Event` pair to gate with, and
   minting a link would be an assertion nobody scored (ADR-0068).
3. `core.immutability.revise` is never called. Copy-on-write is structural: a simulated
   occurrence is a NEW value, not a modified copy of a historical one. `revise` also refuses
   an `OBSERVED` artifact, so this is the first of two independent mechanisms.
4. `UNPROMOTED_DIAGNOSTIC` is never named. `propagation_analyzer.view.diagnostic_view` stays
   the engine's only construction site of that member (ADR-0072); this package compares
   against `STATED` instead, so opting in is the caller's act and not a value this module
   can produce for itself.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.law

BACKEND = Path(__file__).resolve().parents[2]
PACKAGE = BACKEND / "src" / "causalog" / "counterfactual_engine"


def _python_files(root: Path) -> tuple[Path, ...]:
    """Return every source file in the package, canonically sequenced."""
    return tuple(sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts))


def _tree(path: Path) -> ast.Module:
    """Return the parsed module."""
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_the_package_has_source_to_check() -> None:
    """An empty scan reports identically to a clean one, so emptiness is refused here.

    The DEF-0001 / OQ-014 shape: a check that cannot run must never read as a check that
    passed. Nine docstring-only files would satisfy every assertion below.
    """
    files = _python_files(PACKAGE)
    assert len(files) >= 8, "module 13 ships at least eight source files"
    total = sum(len(path.read_text(encoding="utf-8").splitlines()) for path in files)
    assert total > 800, f"the package holds only {total} lines; there is nothing to scan"


def _inferred_references(tree: ast.Module) -> tuple[list[ast.Attribute], list[ast.Attribute]]:
    """Return `(compared, assigned)` references to `ProvenanceClass.INFERRED`.

    The distinction is load-bearing and was learned the hard way. `unpromoted_links` REFUSES
    an edge carrying `INFERRED` -- the mirror image of `propagation_analyzer.diagnostic_view`,
    and the exact opposite of promoting one. A test that flagged every mention would have
    forced that guard to be deleted or allowlisted, which would have removed a safety check
    to satisfy a law about not doing the thing the check prevents.

    So a mention inside a COMPARISON is permitted and every other mention is not. That is a
    narrower rule than "never name it" and it is the rule the law actually intends: promotion
    is assigning the class, not reading it.
    """
    compared: list[ast.Attribute] = []
    assigned: list[ast.Attribute] = []

    def _is_inferred(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "INFERRED"
            and isinstance(node.value, ast.Name)
            and node.value.id == "ProvenanceClass"
        )

    def _walk(node: ast.AST, *, inside_comparison: bool) -> None:
        if _is_inferred(node):
            assert isinstance(node, ast.Attribute)
            (compared if inside_comparison else assigned).append(node)
            return
        nested = inside_comparison or isinstance(node, ast.Compare)
        for child in ast.iter_child_nodes(node):
            _walk(child, inside_comparison=nested)

    _walk(tree, inside_comparison=False)
    return compared, assigned


@pytest.mark.parametrize("path", _python_files(PACKAGE), ids=lambda path: path.name)
def test_nothing_here_assigns_inferred(path: Path) -> None:
    """`ProvenanceClass.INFERRED` is never ASSIGNED in this package.

    Comparing against it is permitted and is exactly what a refusal does; see
    `_inferred_references`.
    """
    _, assigned = _inferred_references(_tree(path))
    if assigned:
        pytest.fail(
            f"{path} line {assigned[0].lineno} assigns ProvenanceClass.INFERRED. Promotion "
            "is a single decision with a single home (causal_graph_builder/policy.py, "
            "ADR-0054); a simulator asserting a claim would be a second opinion about what "
            "this engine stands behind."
        )


def test_the_refusal_of_promoted_links_is_actually_present() -> None:
    """The permitted comparison EXISTS, so the rule above is not vacuously satisfied.

    A law that only forbids can be satisfied by deleting the code it was written around.
    `unpromoted_links` must genuinely refuse a promoted edge, and this asserts that the
    comparison is there rather than trusting the absence of an assignment to imply it.
    """
    compared, _ = _inferred_references(_tree(PACKAGE / "context.py"))
    assert compared, (
        "context.py no longer compares against ProvenanceClass.INFERRED, so nothing stops a "
        "caller handing a promoted graph to unpromoted_links and getting a disowned finding "
        "about an asserted link."
    )


@pytest.mark.parametrize("path", _python_files(PACKAGE), ids=lambda path: path.name)
def test_nothing_here_constructs_a_causal_edge(path: Path) -> None:
    """`CausalEdge(...)` and `CausalEdge.between(...)` appear nowhere in this package."""
    for node in ast.walk(_tree(path)):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if isinstance(target, ast.Name) and target.id == "CausalEdge":
            pytest.fail(f"{path} constructs a CausalEdge; module 10 does that (ADR-0068).")
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "CausalEdge"
        ):
            pytest.fail(f"{path} calls CausalEdge.{target.attr}; a hypothetical states no claim.")


@pytest.mark.parametrize("path", _python_files(PACKAGE), ids=lambda path: path.name)
def test_nothing_here_revises_a_base_world_artifact(path: Path) -> None:
    """`core.immutability.revise` is never called from this package.

    The first of two independent mechanisms. The second is `revise` itself, which raises on
    an `OBSERVED` artifact -- so a call slipping past this test would still fail at runtime.
    Neither depends on a call site remembering.
    """
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Name) and target.id == "revise":
                pytest.fail(
                    f"{path} calls revise(). A simulated occurrence is a NEW value, never a "
                    "modified copy of a historical one (ADR-0068); copy-on-write here is "
                    "structural rather than careful."
                )
        if isinstance(node, ast.ImportFrom) and node.module == "causalog.core.immutability":
            pytest.fail(f"{path} imports from core.immutability; this package revises nothing.")


@pytest.mark.parametrize("path", _python_files(PACKAGE), ids=lambda path: path.name)
def test_nothing_here_names_the_diagnostic_standing(path: Path) -> None:
    """`UNPROMOTED_DIAGNOSTIC` appears in no expression in this package.

    Module 12's `diagnostic_view` stays the engine's only construction site of that member.
    This package compares against `STATED`, so a caller opting in to a disowned graph does
    it at a named call site outside the engine -- which is what makes OQ-026's guarantee
    survive the opt-in ADR-0072 added.
    """
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Attribute) and node.attr == "UNPROMOTED_DIAGNOSTIC":
            pytest.fail(
                f"{path} names GraphStanding.UNPROMOTED_DIAGNOSTIC. Compare against STATED "
                "instead; diagnostic_view is the engine's one construction site (ADR-0072)."
            )
        if isinstance(node, ast.Constant) and node.value == "UNPROMOTED_DIAGNOSTIC":
            pytest.fail(f"{path} holds the diagnostic standing as a string literal.")


@pytest.mark.parametrize("path", _python_files(PACKAGE), ids=lambda path: path.name)
def test_no_threshold_is_a_numeric_literal_in_this_package(path: Path) -> None:
    """Every bound comes from the pack; the only in-code numbers are named ceilings.

    A literal compared against here would be domain policy written into engine code, which
    is what `check_metrics_are_declared.py` refuses one class of and this refuses the rest.
    `0` and `1` are admitted as structural constants -- an empty check and a single element
    are not thresholds.
    """
    admitted = {0, 1, -1}
    for node in ast.walk(_tree(path)):
        if not isinstance(node, ast.Compare):
            continue
        for operand in [node.left, *node.comparators]:
            if isinstance(operand, ast.Constant) and isinstance(operand.value, int | float):
                if isinstance(operand.value, bool) or operand.value in admitted:
                    continue
                pytest.fail(
                    f"{path} line {operand.lineno} compares against the literal "
                    f"{operand.value!r}. Every bound module 13 reads is declared in the "
                    "pack's counterfactual_simulation block (ADR-0071); the only in-code "
                    "number is MAX_SIMULATION_DEPTH, which is a ceiling and is not compared "
                    "against here."
                )


def test_the_fixed_notices_are_imported_rather_than_restated() -> None:
    """One caveat, one home. Two copies of a caveat have already drifted once here.

    `report.py` shows `DIAGNOSTIC_NOT_STATED_NOTICE` and
    `ATTRIBUTION_NOT_MEASUREMENT_NOTICE`, and it must show the constants themselves rather
    than a paraphrase that a later edit could soften independently.
    """
    source = (PACKAGE / "report.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "DIAGNOSTIC_NOT_STATED_NOTICE" in imported
    assert "ATTRIBUTION_NOT_MEASUREMENT_NOTICE" in imported
    assert "NOT THE ENGINE'S VIEW" not in source, (
        "the disowning notice is quoted rather than imported; a paraphrase can be softened "
        "on its own, which is exactly the drift this rule exists to stop"
    )
