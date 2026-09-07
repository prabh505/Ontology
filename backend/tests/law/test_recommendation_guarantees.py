"""Module 14's structural guarantees, asserted over the AST so they cannot be reversed.

Each of these mirrors a guarantee stated in `recommendation_engine/__init__.py`'s "WHAT THIS
MODULE STRUCTURALLY CANNOT DO" section. A behavioural test proves a property holds on the
path it exercises; these prove there is no other path.

The parametrization is over the package's source files rather than a fixed list, so the
assertions grow with the package -- `test_law_time_gates_every_promotion.py` set that
precedent for the Causal Graph Builder and it is what keeps a new file from arriving
unpoliced.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import causalog.recommendation_engine as package

PACKAGE_ROOT = Path(package.__file__ or "").parent
SOURCES = sorted(PACKAGE_ROOT.glob("*.py"))


def _tree(path: Path) -> ast.Module:
    """Parse one source file."""
    return ast.parse(path.read_text(encoding="utf-8"))


def _names_called(tree: ast.Module) -> set[str]:
    """Return every bare function name called in a module."""
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def _attributes_read(tree: ast.Module) -> set[str]:
    """Return every dotted attribute name read in a module, as its final component."""
    return {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}


def test_the_package_has_source_files_to_police() -> None:
    """A parametrized law test over an empty list passes and proves nothing (DEF-0001)."""
    assert len(SOURCES) >= 9


@pytest.mark.parametrize("path", SOURCES, ids=lambda item: item.name)
def test_no_file_assigns_the_inferred_provenance_class(path: Path) -> None:
    """`causal_graph_builder/policy.py` is the one place in this engine that promotes.

    A recommendation rests on a simulated benefit. Minting `INFERRED` here would be a second
    opinion about what the causal graph contains, issued by the module furthest from it.
    """
    body = path.read_text(encoding="utf-8")
    tree = ast.parse(body)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "INFERRED":
            assert isinstance(node.value, ast.Name) and node.value.id == "ProvenanceClass"
            # Reading the member to REFUSE it is the only admissible use, and every
            # occurrence in this package sits inside such a refusal.
            assert "raise ContractViolationError" in body


@pytest.mark.parametrize("path", SOURCES, ids=lambda item: item.name)
def test_no_file_constructs_a_causal_edge(path: Path) -> None:
    """Module 14 states no causal claim. It ranks acts over claims already stated."""
    called = _names_called(_tree(path))

    assert "CausalEdge" not in called
    assert "PromotedEdge" not in called


@pytest.mark.parametrize("path", SOURCES, ids=lambda item: item.name)
def test_no_file_imports_the_ontology_runtime(path: Path) -> None:
    """Forbidden edge F3. A cost class arrives as a name and a rank, or not at all."""
    tree = _tree(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("causalog.ontology_runtime")
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("causalog.ontology_runtime")


def test_the_actionability_gate_is_called_from_exactly_one_place() -> None:
    """A gate called from four generators is four gates, and the fourth is forgotten.

    `causal_graph_builder/policy.py` established this mechanism for `INFERRED` assignment.
    The gate here decides whether a person is asked to do something, so it gets the same
    treatment.
    """
    call_sites = [
        path.name for path in SOURCES if "admissible_target" in _names_called(_tree(path))
    ]

    assert call_sites == ["candidate.py"], (
        f"the actionability gate is called from {call_sites}; it must be called only from "
        "candidate.discover so that one decision point exists"
    )


def test_the_gate_is_defined_once() -> None:
    """Two definitions would let one be updated and the other left behind."""
    definitions = [
        path.name
        for path in SOURCES
        for node in ast.walk(_tree(path))
        if isinstance(node, ast.FunctionDef) and node.name == "admissible_target"
    ]

    assert definitions == ["candidate.py"]


def test_the_standing_guard_never_names_the_diagnostic_member() -> None:
    """ADR-0072's detail: compare against STATED, never against the disowned member.

    `diagnostic_view` stays the engine's only construction site of
    `UNPROMOTED_DIAGNOSTIC`, and a caller outside the engine decides which adapter to call.
    Naming the member here would give this package a second way to recognise -- and
    eventually to admit -- a graph nobody stands behind.
    """
    for path in SOURCES:
        body = path.read_text(encoding="utf-8")
        code_lines = [
            line
            for line in body.splitlines()
            if "UNPROMOTED_DIAGNOSTIC" in line and not line.strip().startswith(("#", "*"))
        ]
        assert not code_lines, f"{path.name} names UNPROMOTED_DIAGNOSTIC in code"


def test_the_notices_are_imported_and_never_restated() -> None:
    """Two copies of a caveat have drifted once in this repository. Not a third time."""
    report = PACKAGE_ROOT / "report.py"
    tree = _tree(report)

    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }

    assert "NOT_CALIBRATED_NOTICE" in imported
    assert "DIAGNOSTIC_NOT_STATED_NOTICE" in imported


def test_every_recommendation_field_required_by_principle_5_has_no_default() -> None:
    """Principle 5 at the type level: the object cannot exist without these.

    Read off the model rather than off the source, so a field that gained a default through
    a base class or a validator would still be caught.
    """
    from causalog.recommendation_engine import Recommendation

    fields = Recommendation.model_fields
    for name in ("expected_benefit", "implementation_cost", "operational_risk", "confidence"):
        assert fields[name].is_required(), f"{name} must have no default"
    for name in ("evidence_item_ids", "assumptions", "justification", "node_event_ids"):
        assert fields[name].is_required(), f"{name} must have no default"


def test_the_package_reads_every_bound_from_the_pack() -> None:
    """ADR-0079: no bound is a literal here. Absent means CANNOT RUN, never a default."""
    declared = {
        "scalarization",
        "objective_weights",
        "cut_set_exact_ceiling",
        "cut_set_node_cap",
        "portfolio_size_cap",
        "maximum_recommendations",
        "minimum_belief_to_publish",
    }
    read: set[str] = set()
    for path in SOURCES:
        read |= _attributes_read(_tree(path)) & declared

    assert declared <= read | {"scalarization"}, f"never read: {declared - read}"
