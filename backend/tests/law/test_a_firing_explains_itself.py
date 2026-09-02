"""LAW-EVIDENCE for the rule layer: a firing that cannot explain itself does not exist.

`CONVENTIONS.md` §14: a failure here is `CRITICAL`. These assert the structural properties
the whole seam rests on, over the evaluator's real output rather than over one hand-built
value:

  * every emitted firing carries its bindings, its cited events, and its condition trace;
  * no firing carries a bare-float confidence (LAW-EVIDENCE);
  * no firing survives a LAW-TIME violation;
  * `Event.trigger` is never read to create or filter a firing (ADR-0020).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from causalog.core.temporal import TemporalVerdict
from causalog.rule_engine import evaluate
from causalog.rule_engine.trace import RuleFiring
from tests.fixtures.rules import constraint, pack, rule, two_stage_facts

RULE_ENGINE_ROOT = Path(__file__).resolve().parents[2] / "src" / "causalog" / "rule_engine"


def _conditional() -> dict[str, object]:
    """Return a CONDITIONAL rule whose condition holds over the standard fixture."""
    return rule(
        "R-COND",
        kind="CONDITIONAL",
        body={
            "conditions": {
                "op": "IS_PRESENT",
                "operands": [
                    {
                        "op": "ATTRIBUTE",
                        "address": {
                            "binding": "CAUSE",
                            "role": "SUBJECT",
                            "attribute": "stage",
                        },
                    }
                ],
            }
        },
    )


def test_every_emitted_firing_carries_its_whole_reasoning() -> None:
    """The law, asserted over the evaluator's output rather than over a constructed value."""
    facts, _, _, _ = two_stage_facts(closed=True)
    result = evaluate(pack(rule(), _conditional(), constraint()), facts)

    assert result.firings, "no firing was emitted, so this law test asserted nothing"
    for firing in result.firings:
        assert firing.bindings, f"{firing.rule_id} bound nothing"
        assert firing.matched_event_ids, f"{firing.rule_id} cited no event"
        assert (
            firing.condition_was_trivial or firing.evaluated_conditions
        ), f"{firing.rule_id} carries a condition and no trace"
        assert firing.rule_pack_version, f"{firing.rule_id} names no pack version"


def test_a_suppressed_firing_keeps_its_reasoning_too() -> None:
    """A conflict report a reader cannot investigate is not a report (ADR-0047)."""
    facts, _, _, _ = two_stage_facts(closed=True)
    result = evaluate(pack(rule(), constraint()), facts)

    assert not result.conflicts.is_empty()
    for finding in result.conflicts.findings:
        suppressed = finding.suppressed_firing
        assert suppressed.bindings
        assert suppressed.matched_event_ids
        assert finding.constraint_rule_id and finding.suppressed_rule_id


def test_no_firing_carries_a_bare_float_confidence() -> None:
    """LAW-EVIDENCE: a bare float where a judgement belongs is a defect.

    `base_strength` is the one admissible bare float here and is named so it is not mistaken
    for a confidence -- the same choice `EvidenceItem.strength` makes (`docs/contracts.md`
    §5). This asserts no OTHER float-valued field has crept onto the type under a name that
    reads like a judgement.
    """
    judgement_names = {
        name
        for name, field in RuleFiring.model_fields.items()
        if "confidence" in name or "score" in name or "probability" in name
    }
    assert judgement_names == set(), (
        f"RuleFiring declares {sorted(judgement_names)}; assembling named components into a "
        "ConfidenceVector is module 10's job, and a scalar here would pre-empt it"
    )
    assert "base_strength" in RuleFiring.model_fields


def test_no_firing_survives_a_temporal_violation() -> None:
    """LAW-TIME, at the layer that proposes the pair."""
    facts, _, _, _ = two_stage_facts(cause_day=9, effect_day=0)
    result = evaluate(pack(rule()), facts)

    assert result.firings == ()
    assert result.statistics.temporal_violations_refused >= 1
    for firing in result.firings:
        assert firing.temporal_verdict is not TemporalVerdict.VIOLATION


def test_an_undetermined_firing_is_retained_and_flagged_never_dropped() -> None:
    """`CONTEXT.md` R-14: a data-quality problem stays visible, it does not shrink the graph."""
    facts, _, _, _ = two_stage_facts(cause_day=0, effect_day=1, span_days=5)
    result = evaluate(pack(rule()), facts)

    assert len(result.firings) == 1
    assert result.firings[0].temporal_verdict is TemporalVerdict.UNDETERMINED


@pytest.mark.parametrize(
    "source_file", sorted(RULE_ENGINE_ROOT.glob("*.py")), ids=lambda path: path.name
)
def test_the_rule_engine_never_reads_event_trigger(source_file: Path) -> None:
    """ADR-0020: an OBSERVED mechanism may not become an unscored causal claim.

    Asserted over the AST rather than by grepping, so a comment mentioning the field does
    not fail the build and an attribute access cannot hide inside a string.
    """
    tree = ast.parse(source_file.read_text(encoding="utf-8"))
    offending = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "trigger"
    ]
    assert not offending, (
        f"{source_file.name} reads `.trigger` at line(s) {offending}. An observed mechanism "
        "recorded on an event may not create, filter, or score a causal candidate "
        "(ADR-0020)."
    )


def test_the_rule_engine_declares_no_causal_edge() -> None:
    """The inference boundary: Module 9 owns edge construction, not this layer.

    Asserted over the package's own imports: a layer that cannot import `CausalEdge` cannot
    construct one, whatever anybody later intends.
    """
    imported: set[str] = set()
    for source_file in RULE_ENGINE_ROOT.glob("*.py"):
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.update(alias.name for alias in node.names)

    forbidden = {"CausalEdge", "DirectCause", "ConditionalCause", "ContributingCause"}
    assert not (imported & forbidden), (
        f"rule_engine imports {sorted(imported & forbidden)}. `docs/architecture.md` "
        "§Module 9 gives the Candidate Cause Generator the LAW-TIME gate and CausalEdge "
        "construction; this layer returns fired rule identifiers to it."
    )
