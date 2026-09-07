"""LAW-TIME and LAW-PROVENANCE at the promotion boundary, asserted over the SOURCE.

A behavioural test proves the policy works on the inputs it was given. This file proves
something stronger and more durable: that there is **no second path** to an `INFERRED` edge.
It reads the package's AST and asserts that `ProvenanceClass.INFERRED` and
`core.immutability.revise` appear in `policy.py` and nowhere else in the package.

That matters because the behavioural guarantee decays the moment somebody adds a second
selection strategy. A structural assertion does not: a new module that promoted an edge of
its own would fail here on the day it was written, naming the file.

Same technique as `tests/law/test_law_time_gates_every_candidate.py`, one layer on, and for
the same reason. It is also applied to the whole of `causal_engine`, not just this package,
because ADR-0054's decision is that promotion happens in exactly one place in the engine.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from causalog.causal_engine.causal_graph_builder import (
    DemotionReason,
    build_causal_graph,
    decide,
    select,
)
from causalog.core.errors import LawViolationError
from causalog.core.immutability import revise
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import TemporalVerdict
from fixtures.candidates import envelope, linear_process, unknown_time_event
from fixtures.graphs import build_context, candidate, scored_graph

BACKEND = Path(__file__).resolve().parents[2]
PACKAGE = BACKEND / "src" / "causalog" / "causal_engine" / "causal_graph_builder"
ENGINE = BACKEND / "src" / "causalog" / "causal_engine"

#: The one module permitted to promote. Everything else must go through it.
SANCTIONED_PROMOTION_SITE = "policy.py"


def _python_files(root: Path) -> tuple[Path, ...]:
    return tuple(sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts))


def test_the_package_has_source_to_check() -> None:
    """An empty scan reports identically to a clean one, so emptiness is refused here.

    The DEF-0001 / OQ-014 shape: a check that cannot run must never read as a check that
    passed. Nine docstring-only files would satisfy every assertion below.
    """
    files = _python_files(PACKAGE)
    assert len(files) >= 9
    assert sum(len(path.read_text().splitlines()) for path in files) > 800


def _assigns_inferred(tree: ast.AST) -> list[ast.AST]:
    """Return every site that ASSIGNS `ProvenanceClass.INFERRED` to a provenance field.

    Assignment, not mention. `graph.py` compares against `INFERRED` in the invariant that
    refuses an unpromoted edge in the promoted set, and module 10's `temporal_support`
    scorer stamps `INFERRED` on a COMPONENT it derived -- neither is a promotion, and a
    check that conflated them would fire on the code that enforces the rule.

    What counts is `provenance_class=ProvenanceClass.INFERRED` passed into a call, which is
    the one shape that puts the class onto an artifact.
    """
    found: list[ast.AST] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg != "provenance_class":
                continue
            value = keyword.value
            if (
                isinstance(value, ast.Attribute)
                and value.attr == "INFERRED"
                and isinstance(value.value, ast.Name)
                and value.value.id == "ProvenanceClass"
            ):
                found.append(node)
    return found


@pytest.mark.parametrize("path", _python_files(PACKAGE), ids=lambda path: path.name)
def test_only_the_policy_module_assigns_inferred(path: Path) -> None:
    """`provenance_class=ProvenanceClass.INFERRED` is written in `policy.py` alone."""
    tree = ast.parse(path.read_text(), filename=str(path))
    assigned = _assigns_inferred(tree)
    if path.name == SANCTIONED_PROMOTION_SITE:
        assert assigned, "the sanctioned promotion site must actually promote"
        return
    assert not assigned, (
        f"{path} assigns ProvenanceClass.INFERRED. Promotion is a single decision with a "
        f"single home ({SANCTIONED_PROMOTION_SITE}, ADR-0054); a second site would mean two "
        "modules deciding what the engine asserts, and one of them would win by import "
        "sequence."
    )


def test_no_edge_outside_this_package_is_built_as_inferred() -> None:
    """ADR-0054 across the whole engine: no other package may stamp INFERRED onto an edge.

    Scoped to calls that also pass a `payload` or an `edge`, so a scorer stamping a class
    onto one of its own components is not swept up -- a component's provenance is a
    statement about how that component was derived, not about whether the engine asserts
    the edge.
    """
    offenders: list[str] = []
    for path in _python_files(ENGINE):
        if path.parent == PACKAGE:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for call in _assigns_inferred(tree):
            names = {keyword.arg for keyword in call.keywords}  # type: ignore[union-attr]
            if names & {"payload", "edge", "confidence"}:
                offenders.append(f"{path}:{call.lineno}")
    assert not offenders, (
        "promotion happens in causal_graph_builder/policy.py alone (ADR-0054); found "
        f"{offenders}"
    )


@pytest.mark.parametrize("path", _python_files(PACKAGE), ids=lambda path: path.name)
def test_only_the_policy_module_revises_an_edge(path: Path) -> None:
    """`revise` is the promotion path, and it is called from one file."""
    tree = ast.parse(path.read_text(), filename=str(path))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "revise"
    ]
    if path.name == SANCTIONED_PROMOTION_SITE:
        assert calls
        return
    assert not calls, f"{path} calls revise; promotion belongs in {SANCTIONED_PROMOTION_SITE}."


@pytest.mark.parametrize("path", _python_files(PACKAGE), ids=lambda path: path.name)
def test_no_threshold_is_a_literal_in_a_decision_module(path: Path) -> None:
    """Selection thresholds are configuration, never literals in code.

    Scoped to the three modules that make decisions. A numeric literal in a comparison there
    is a policy no reviewer of this repository can find and no pack can change, which is
    LAW-DOMAIN defeated by a value rather than by a word (`CONVENTIONS.md` §6a).

    `0.0` and `1.0` are admitted: they are the bounds of the `[0, 1]` range every weight and
    scalar is declared over, not thresholds anybody could tune.
    """
    if path.name not in {"policy.py", "select.py", "weights.py"}:
        pytest.skip("not a decision module")
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        for operand in (node.left, *node.comparators):
            if not isinstance(operand, ast.Constant):
                continue
            if isinstance(operand.value, bool) or not isinstance(operand.value, int | float):
                continue
            assert operand.value in (0, 1, 0.0, 1.0), (
                f"{path}:{operand.lineno} compares against the literal {operand.value!r}. "
                "Every threshold is a rule-pack declaration (ADR-0055)."
            )


def test_an_undetermined_edge_cannot_be_promoted_through_any_path() -> None:
    """The behavioural half: LAW-TIME bars promotion whatever the thresholds say."""
    from fixtures.facts import entity, event, evidence_record, interval, timeline

    citation = evidence_record("row-law-time")
    participant = entity("A", citation=citation)
    earlier = event(
        "STAGE_ONE", interval(0, span_days=2), citation=citation, participants=(participant,)
    )
    later = event(
        "STAGE_TWO", interval(1, span_days=2), citation=citation, participants=(participant,)
    )
    events = (earlier, later)
    line = timeline(*events)
    candidates = (candidate(earlier, later),)
    graph = scored_graph(candidates, events, (line,))
    assert graph.edges[0].edge.temporal_verdict is TemporalVerdict.UNDETERMINED
    context = build_context(events, (line,), candidates)
    result = build_causal_graph(graph, context, envelope())
    assert not result.graph.edges
    assert result.graph.demotions[0].reason is DemotionReason.TEMPORAL_NOT_CERTAIN


def test_the_frozen_type_refuses_a_forced_promotion() -> None:
    """The second belt-and-braces check, exercised directly on the artifact.

    Even if `decide` were bypassed entirely, `revise` re-validates the model and the frozen
    `CausalEdge` invariant `INFERRED => CERTAIN and not unverifiable` raises.
    """
    participant, events, line = linear_process("STAGE_ONE", "STAGE_TWO", subject="A")
    unplaced = unknown_time_event("STAGE_THREE", participant=participant)
    facts = (*events, unplaced)
    candidates = (candidate(events[0], unplaced),)
    graph = scored_graph(candidates, facts, (line,))
    edge = graph.edges[0].edge
    assert edge.temporally_unverifiable
    with pytest.raises(LawViolationError, match="INFERRED"):
        revise(edge, provenance_class=ProvenanceClass.INFERRED)


def test_promotion_never_touches_an_observed_artifact() -> None:
    """LAW-PROVENANCE: `revise` refuses an OBSERVED artifact, so the path itself is guarded."""
    _, events, line = linear_process("STAGE_ONE", "STAGE_TWO", subject="A")
    assert events[0].provenance_class is ProvenanceClass.OBSERVED
    with pytest.raises(LawViolationError, match="LAW-PROVENANCE"):
        revise(events[0], event_type="STAGE_TAMPERED")


def test_the_source_events_are_unchanged_by_a_whole_build() -> None:
    """Inference never overwrites observation: the inputs are byte-identical afterwards."""
    from causalog.core.serialization import to_canonical_json

    _, events, line = linear_process("STAGE_ONE", "STAGE_TWO", "STAGE_THREE", subject="A")
    candidates = (candidate(events[0], events[1]), candidate(events[1], events[2]))
    before = tuple(to_canonical_json(item) for item in events)
    graph = scored_graph(candidates, events, (line,))
    context = build_context(events, (line,), candidates)
    result = build_causal_graph(graph, context, envelope())
    after = tuple(to_canonical_json(item) for item in events)
    assert before == after
    assert result.graph.edges, "the build must actually have promoted, or this proves nothing"


def test_scored_edges_are_not_mutated_by_promotion() -> None:
    """Promotion produces a new version; module 10's artifact is untouched (ADR-0004)."""
    _, events, line = linear_process("STAGE_ONE", "STAGE_TWO", subject="A")
    candidates = (candidate(events[0], events[1]),)
    graph = scored_graph(candidates, events, (line,))
    original = graph.edges[0].edge.provenance_class
    promoted = select(graph, build_context(events, (line,), candidates))
    assert promoted.edges
    assert graph.edges[0].edge.provenance_class is original
    assert original is not ProvenanceClass.INFERRED


def test_module_ten_no_longer_promotes() -> None:
    """ADR-0054's other half: the decision moved, so the old site must not still make it."""
    _, events, line = linear_process("STAGE_ONE", "STAGE_TWO", subject="A")
    candidates = (candidate(events[0], events[1]),)
    graph = scored_graph(candidates, events, (line,))
    assert all(edge.edge.provenance_class is not ProvenanceClass.INFERRED for edge in graph.edges)


def test_decide_is_the_only_gate_and_it_reports_every_refusal() -> None:
    """Every refusal carries a reason and a sentence; a bare rejection is unactionable."""
    _, events, line = linear_process("STAGE_ONE", "STAGE_TWO", subject="A")
    candidates = (candidate(events[0], events[1]),)
    graph = scored_graph(candidates, events, (line,))
    context = build_context(events, (line,), candidates)
    verdict = decide(graph.edges[0], context.parameters, context.bands, {})
    assert not verdict.promotes
    assert verdict.reason is not None
    assert len(verdict.detail) > 40
