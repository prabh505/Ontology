"""LAW-PROVENANCE: no heuristic may silently create an OBSERVED event.

Three levels, because two of them can be satisfied by a module that is still one edit away
from breaking the law.

  1. **Structural.** Every `Event(...)` construction in `event_generator` takes its
     `provenance_class` from the pack's `EventTypeSpec`, never from a literal and never from
     a parameter. An AST check, so a comment or a string cannot satisfy it.
  2. **Declarative.** The pack refuses `OBSERVED` on a type declared `DERIVED` (ADR-0029),
     so there is nothing for a rule to read that would produce one.
  3. **Observed.** Run the fixture and check every event.

The check is also observed to REJECT, not merely to pass (`CONVENTIONS.md` §6): a planted
pack that tries to declare a derived type observed is refused, and a planted constructor
that hard-codes a provenance class is detected by the AST rule.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import causalog
from causalog.core.errors import ContractViolationError
from causalog.core.provenance import ProvenanceClass
from causalog.ontology_runtime.dsl import ObservationMode
from extraction_harness import build_batches, envelope_for, harness_for
from fixtures.dataco.expansion import GROUND_TRUTH_DATASET_VERSION, rows

pytestmark = pytest.mark.law

GENERATOR_ROOT = Path(causalog.__file__).resolve().parent / "extraction" / "event_generator"

#: The one expression an `Event(...)` construction may pass as `provenance_class`. It reads
#: the pack. Anything else -- a literal, a parameter, a conditional -- is a path by which a
#: rule could name its own provenance, which is the whole failure this file exists to stop.
PERMITTED_PROVENANCE_SOURCE = "spec.provenance_class"


def _event_constructions(tree: ast.AST) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Event"
    ]


def _provenance_arguments(path: Path) -> list[tuple[Path, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for call in _event_constructions(tree):
        for keyword in call.keywords:
            if keyword.arg == "provenance_class":
                found.append((path, ast.unparse(keyword.value)))
    return found


def test_the_scan_covers_something() -> None:
    """Zero constructions scanned reads identically to zero violations found (DEF-0001)."""
    found = [
        item
        for path in sorted(GENERATOR_ROOT.rglob("*.py"))
        for item in _provenance_arguments(path)
    ]
    assert found, "no Event construction was found in the event generator"


def test_every_event_construction_reads_its_provenance_from_the_pack() -> None:
    offenders = [
        f"{path.name}: provenance_class={expression}"
        for path in sorted(GENERATOR_ROOT.rglob("*.py"))
        for path, expression in _provenance_arguments(path)
        if expression != PERMITTED_PROVENANCE_SOURCE
    ]
    assert not offenders, (
        "LAW-PROVENANCE: an emitted event must take the provenance class its ontology event "
        "type declares. A literal or a parameter here is a path by which a heuristic names "
        f"its own provenance. Found: {offenders}"
    )


def test_the_ast_rule_is_observed_to_reject_a_planted_construction(tmp_path: Path) -> None:
    """The DEF-0001 guard: a check with only positive evidence is not evidence."""
    planted = tmp_path / "planted.py"
    planted.write_text(
        "from causalog.core.provenance import ProvenanceClass\n"
        "def build():\n"
        "    return Event(provenance_class=ProvenanceClass.OBSERVED)\n",
        encoding="utf-8",
    )
    found = _provenance_arguments(planted)
    assert found, "the scan did not see the planted construction at all"
    assert all(expression != PERMITTED_PROVENANCE_SOURCE for _path, expression in found)


def test_a_pack_declaring_a_derived_type_observed_is_refused() -> None:
    """The declarative gate, observed to reject (ADR-0029)."""
    from causalog.ontology_runtime.dsl import (
        ActionabilitySpec,
        DefaultConfidenceComponentSpec,
        DefaultConfidenceSpec,
        DerivationSpec,
        EventTypeSpec,
        ParticipantSpec,
    )

    derivation = DerivationSpec(
        basis="a planted basis",
        default_confidence=DefaultConfidenceSpec(
            components=(DefaultConfidenceComponentSpec(component_name="rule_support", value=0.5),),
            aggregation="weighted_mean_v1",
            provenance_class=ProvenanceClass.ASSUMED,
        ),
    )
    with pytest.raises(ContractViolationError, match="masquerad"):
        EventTypeSpec(
            id="THING_HAPPENED",
            description="a planted violation",
            category="BUSINESS",
            observation=ObservationMode.DERIVED,
            provenance_class=ProvenanceClass.OBSERVED,
            participants=(ParticipantSpec(role="SUBJECT", entity_type="THING"),),
            actionability=ActionabilitySpec(actionable=False, severity_class="INFORMATIONAL"),
            derivation=derivation,
        )


def test_no_derived_event_type_produces_an_observed_event() -> None:
    """The observed gate: run the fixture and check every event against its declaration."""
    harness = harness_for()
    batches = build_batches(rows(), harness, GROUND_TRUTH_DATASET_VERSION)
    envelope = envelope_for(harness, GROUND_TRUTH_DATASET_VERSION)
    extraction = harness.extract(batches, envelope)
    generation = harness.generate(batches, extraction, envelope)
    declared = {item.id: item for item in harness.pack.event_types}

    assert generation.events, "the fixture produced no events, so this proved nothing"
    for event in generation.events:
        spec = declared[event.event_type]
        assert event.provenance_class is spec.provenance_class
        if spec.observation is ObservationMode.DERIVED:
            assert (
                event.provenance_class is not ProvenanceClass.OBSERVED
            ), f"{event.event_type} is DERIVED and claims OBSERVED provenance"


def test_the_dataco_pack_declares_exactly_one_observed_event_type() -> None:
    """ADR-0029's ratio, pinned so it cannot be quietly promoted."""
    harness = harness_for()
    observed = [
        item.id for item in harness.pack.event_types if item.observation is ObservationMode.OBSERVED
    ]
    assert observed == ["ORDER_PLACED"]
    assert len(harness.pack.event_types) == 20
