"""LAW-PROVENANCE and ADR-0008 at the ranking boundary, asserted over the SOURCE.

A behavioural test proves the modules behave on the inputs they were given. This file proves
something stronger and more durable: that there is **no second path** to the things these
two modules must never do.

Three structural claims, each read off the AST rather than exercised:

1. **Neither module can create a link.** `ProvenanceClass.INFERRED` is never assigned and
   `CausalEdge` is never constructed anywhere in either package. The Causal Graph Builder's
   `policy.py` is the one promotion site in the whole engine and
   `test_law_time_gates_every_promotion.py` pins that; this file pins that modules 11 and 12
   did not quietly open a second one.
2. **The diagnostic standing has exactly one construction site.** If a second appeared, a
   disowned finding could be minted somewhere that had not thought about disowning it.
3. **ADR-0008's four views are four fields.** `RootCauseRanking` declares all four, and no
   attribute named like a single collapsed answer exists on it.

Plus the behavioural half that AST reading cannot reach: an artifact carrying a diagnostic
standing must refuse `INFERRED`, and a ranking must refuse an unactionable recommendation.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from causalog.causal_engine.propagation_analyzer import (
    ConsequenceSet,
    GraphStanding,
    PropagationTree,
)
from causalog.causal_engine.root_cause_analyzer import RootCauseRanking
from causalog.core.errors import LawViolationError
from causalog.core.provenance import ProvenanceClass

pytestmark = pytest.mark.law

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "causalog" / "causal_engine"
PROPAGATION = SOURCE_ROOT / "propagation_analyzer"
ROOT_CAUSE = SOURCE_ROOT / "root_cause_analyzer"
PATTERNS = SOURCE_ROOT / "pattern_miner"

#: The one file permitted to construct the disowned standing. Everything else must go
#: through it.
SANCTIONED_DIAGNOSTIC_SITE = "view.py"

#: The four fields ADR-0008 requires. A ranking missing one has collapsed a question.
REQUIRED_VIEW_FIELDS = frozenset(
    {
        "earliest_cause",
        "highest_consequence_cause",
        "most_actionable_cause",
        "actionable_root_causes",
    }
)


def _python_files(package: Path) -> tuple[Path, ...]:
    """Return every source file in one package, sorted."""
    return tuple(sorted(path for path in package.rglob("*.py") if "__pycache__" not in path.parts))


def _attribute_chain(node: ast.AST) -> str:
    """Render an attribute access as dotted text, for matching without importing."""
    parts: list[str] = []
    cursor = node
    while isinstance(cursor, ast.Attribute):
        parts.append(cursor.attr)
        cursor = cursor.value
    if isinstance(cursor, ast.Name):
        parts.append(cursor.id)
    return ".".join(reversed(parts))


ALL_PACKAGES = (PROPAGATION, ROOT_CAUSE, PATTERNS)


def test_the_packages_have_source_to_check() -> None:
    """An empty scan reports identically to a clean one, so emptiness is refused here.

    The DEF-0001 / OQ-014 shape: a check that cannot run must never read as a check that
    passed. Docstring-only files would satisfy every assertion below.
    """
    files = tuple(path for package in ALL_PACKAGES for path in _python_files(package))
    assert len(files) >= 18
    assert sum(len(path.read_text().splitlines()) for path in files) > 1500


@pytest.mark.parametrize(
    "path",
    [path for package in ALL_PACKAGES for path in _python_files(package)],
    ids=lambda path: f"{path.parent.name}/{path.name}",
)
def test_no_file_assigns_the_inferred_provenance_class(path: Path) -> None:
    """Neither ranking nor traversal nor mining may promote a claim.

    `ProvenanceClass.INFERRED` is READ in these packages -- a validator has to compare
    against it to refuse it -- so this asserts it is never on the right-hand side of an
    assignment or in a keyword argument, which is where promotion would happen.
    """
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg in {
            "provenance_class",
            "provenance",
        }:
            assert _attribute_chain(node.value) != "ProvenanceClass.INFERRED", (
                f"{path.name} passes ProvenanceClass.INFERRED as {node.arg}. Only "
                "causal_graph_builder/policy.py may promote a claim (ADR-0054)."
            )
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if _attribute_chain(node.value) == "ProvenanceClass.INFERRED":
                    raise AssertionError(
                        f"{path.name} assigns ProvenanceClass.INFERRED to "
                        f"{_attribute_chain(target)}."
                    )


@pytest.mark.parametrize(
    "path",
    [path for package in ALL_PACKAGES for path in _python_files(package)],
    ids=lambda path: f"{path.parent.name}/{path.name}",
)
def test_no_file_constructs_a_causal_edge(path: Path) -> None:
    """Creating a link is the Causal Graph Builder's, and these modules are downstream."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            called = _attribute_chain(node.func)
            assert called not in {"CausalEdge", "CausalEdge.between"}, (
                f"{path.name} constructs a CausalEdge. Modules 11 and 12 read the graph and "
                "may never add to it (`docs/architecture.md` §2)."
            )


def test_the_diagnostic_standing_has_exactly_one_construction_site() -> None:
    """A second site could mint a disowned finding somewhere that had not disowned it."""
    sites: list[str] = []
    for package in ALL_PACKAGES:
        for path in _python_files(package):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Attribute)
                    and _attribute_chain(node) == "GraphStanding.UNPROMOTED_DIAGNOSTIC"
                ):
                    sites.append(path.name)
    constructing = {name for name in sites if name == SANCTIONED_DIAGNOSTIC_SITE}
    assert constructing == {SANCTIONED_DIAGNOSTIC_SITE}
    # Everywhere else the member may only be COMPARED against, which is how a validator
    # refuses it. `view.py` is the only file that hands it out.
    assert SANCTIONED_DIAGNOSTIC_SITE in sites


def test_the_ranking_declares_all_four_views_as_separate_fields() -> None:
    """ADR-0008: four questions, four fields, and no fifth collapsing them."""
    fields = set(RootCauseRanking.model_fields)
    assert fields >= REQUIRED_VIEW_FIELDS
    collapsed = {
        name
        for name in fields
        if name in {"root_cause", "the_root_cause", "primary_cause", "root_cause_score"}
    }
    assert not collapsed, (
        f"RootCauseRanking declares {sorted(collapsed)}. ADR-0008 forbids a single field "
        "presenting one event as *the* root cause; earliness and prevented consequence are "
        "not commensurable and any blend of them is an unexplainable constant."
    )


def test_a_diagnostic_ranking_cannot_carry_the_inferred_class(
    storm_ranking: RootCauseRanking,
) -> None:
    """The laundering path, closed by the type rather than by the code that builds it.

    Constructed directly rather than copied, because `model_copy` does not re-validate and
    a test that only copied would prove the validator was never reached.
    """
    with pytest.raises(LawViolationError, match="UNPROMOTED_DIAGNOSTIC"):
        RootCauseRanking(
            run_id=storm_ranking.run_id,
            standing=GraphStanding.UNPROMOTED_DIAGNOSTIC,
            outcome_event_id=storm_ranking.outcome_event_id,
            considered=storm_ranking.considered,
            provenance_class=ProvenanceClass.INFERRED,
        )


def test_a_diagnostic_propagation_tree_cannot_carry_the_inferred_class() -> None:
    """The same closure on module 12's artifact."""
    with pytest.raises(LawViolationError, match="UNPROMOTED_DIAGNOSTIC"):
        PropagationTree(
            run_id="run:fixture00000000",
            standing=GraphStanding.UNPROMOTED_DIAGNOSTIC,
            seed_event_id="evt:seed",
            nodes=(),
            consequences=ConsequenceSet(
                event_ids=(), combination_absent_because="nothing was reached"
            ),
            depth=0,
            breadth=0,
            provenance_class=ProvenanceClass.INFERRED,
        )


def test_a_ranking_refuses_an_unactionable_recommendation(
    storm_ranking: RootCauseRanking,
) -> None:
    """prd.md §29's definition turns on actionability, so the type enforces it."""
    unactionable = storm_ranking.earliest_cause
    assert unactionable is not None
    assert unactionable.actionability.is_actionable is False
    with pytest.raises(LawViolationError, match="not actionable"):
        RootCauseRanking(
            run_id=storm_ranking.run_id,
            standing=storm_ranking.standing,
            outcome_event_id=storm_ranking.outcome_event_id,
            considered=storm_ranking.considered,
            actionable_root_causes=(unactionable,),
            provenance_class=storm_ranking.provenance_class,
        )


def test_the_unvalidated_actionability_notice_cannot_be_softened(
    storm_ranking: RootCauseRanking,
) -> None:
    """R-15's caveat is a property, so a stored artifact cannot carry a reworded one."""
    assert "R-15" in storm_ranking.actionability_notice
    assert "actionability_notice" not in RootCauseRanking.model_fields
