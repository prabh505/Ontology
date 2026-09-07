"""LAW-TIME, asserted over module 9's SOURCE rather than only over its behaviour.

A behavioural test proves the gate works on the inputs it was given. This file proves
something stronger and more durable: that there is no second path to a candidate. It reads
the package's AST and asserts that `CandidateEdge.between` -- the only constructor that can
evaluate LAW-TIME -- is called from exactly one module, `gate.py`.

That matters because the behavioural guarantee decays the moment somebody adds an eighth
generator. A structural assertion does not: a new generator that constructed its own
candidate would fail here on the day it was written, naming the file.

This is the same technique `tests/law/test_trigger_is_not_an_inference_input.py` already
applies to `Event.trigger`, and it is applied here for the same reason.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "causalog"
    / "causal_engine"
    / "candidate_cause_generator"
)

#: The one module permitted to construct a candidate. Everything else must go through it.
SANCTIONED_CONSTRUCTOR_SITE = "gate.py"


def _python_files() -> tuple[Path, ...]:
    """Return every source file in module 9, sorted."""
    return tuple(sorted(PACKAGE.rglob("*.py")))


def test_the_package_has_source_to_check() -> None:
    """An empty scan reports identically to a clean one, so emptiness is refused here.

    The DEF-0001 / OQ-014 shape: a check that cannot run must never read as a check that
    passed. Twelve docstring-only files would satisfy every assertion below.
    """
    files = _python_files()
    assert len(files) >= 8
    assert sum(len(path.read_text().splitlines()) for path in files) > 500


@pytest.mark.parametrize("path", _python_files(), ids=lambda path: path.name)
def test_only_the_gate_constructs_a_candidate_edge(path: Path) -> None:
    """`CandidateEdge.between` and `CandidateEdge(...)` appear in `gate.py` alone."""
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        called = ""
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
            called = f"{target.value.id}.{target.attr}"
        elif isinstance(target, ast.Name):
            called = target.id
        if called in ("CandidateEdge.between", "CandidateEdge"):
            assert path.name == SANCTIONED_CONSTRUCTOR_SITE, (
                f"{path.name}:{node.lineno} constructs a CandidateEdge. Only "
                f"{SANCTIONED_CONSTRUCTOR_SITE} may: it is the single chokepoint where "
                "LAW-TIME is evaluated, and a second construction site is a second path "
                "an ungated pair can take into the graph."
            )


@pytest.mark.parametrize("path", _python_files(), ids=lambda path: path.name)
def test_no_generator_reads_event_trigger(path: Path) -> None:
    """ADR-0020: an OBSERVED mechanism may not become an unscored causal claim.

    Checked over the AST rather than the text, so the word `trigger` in prose is fine and
    an attribute access is not.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "trigger":
            pytest.fail(
                f"{path.name}:{node.lineno} reads `.trigger`. Inference may never read "
                "Event.trigger (ADR-0020): the mechanism recorded ON an event is not a "
                "cause BETWEEN two, and matching on it would promote an observation to an "
                "unscored causal claim."
            )


def test_no_module_in_the_package_assigns_confidence() -> None:
    """`CandidateEdge` has no confidence field, and nothing here builds a vector either.

    The structural guarantee is the absent field. This asserts the second half: module 9
    does not construct a `ConfidenceVector` for any other purpose, which would be a
    judgement made under another name.
    """
    for path in _python_files():
        source = path.read_text()
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in ("ConfidenceVector", "ConfidenceComponent"), (
                    f"{path.name}:{node.lineno} builds a confidence value. Module 9 "
                    "assigns no confidence -- generation and judgement are separate "
                    "concerns in separate modules, by design "
                    "(docs/architecture.md §Module 9)."
                )
