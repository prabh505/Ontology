"""Each class of invalid pack fails with its own specific, located diagnostic.

Two things are asserted for every fixture, and the second is the one that matters:

  * the **code** -- so a test failure names the rule that broke, and so rewording a message
    is never a test failure;
  * the **line** -- by reading the reported line back out of the file and checking it holds
    the defect. A validator that reports the wrong line is worse than one that reports no
    line, because the author trusts it and looks in the wrong place.

Every fixture in `fixtures/ontology/invalid/` is `valid_minimal.yaml` with exactly one
defect, so a failure here is about the rule and never about the scaffolding.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from causalog.core.errors import ContractViolationError
from causalog.ontology_runtime import inspect_pack, load_pack
from causalog.ontology_runtime.diagnostics import Severity

# fixture file -> (expected code, text that must appear on the reported line)
LOCATED_CASES: tuple[tuple[str, str, str], ...] = (
    ("orphan_participant.yaml", "ONT-E-UNKNOWN-ENTITY-TYPE", "NO_SUCH_THING"),
    ("orphan_category.yaml", "ONT-E-UNKNOWN-CATEGORY", "NO_SUCH_CATEGORY"),
    ("unreachable_state.yaml", "ONT-E-UNREACHABLE-STATE", "STRANDED"),
    ("terminal_state_has_exit.yaml", "ONT-E-TERMINAL-STATE-HAS-EXIT", "terminal_states"),
    ("duplicate_transition.yaml", "ONT-E-DUPLICATE-TRANSITION", "from: NEW"),
    ("undeclared_process_step.yaml", "ONT-E-UNKNOWN-EVENT-TYPE", "ABANDONED"),
    ("causal_relationship.yaml", "ONT-E-CAUSAL-RELATIONSHIP", "CAUSES"),
    ("external_event_referenced.yaml", "ONT-E-EXTERNAL-REFERENCED", "OUTSIDE"),
    ("duplicate_event_type_id.yaml", "ONT-E-DUPLICATE-ID", "STARTED"),
    ("unknown_state_in_condition.yaml", "ONT-E-UNKNOWN-STATE", "NOT_A_STATE"),
    ("unknown_role_in_condition.yaml", "ONT-E-UNKNOWN-ROLE", "GHOST"),
    ("measurement_unknown_attribute.yaml", "ONT-E-UNKNOWN-ATTRIBUTE", "never_declared"),
    ("step_not_in_sequence.yaml", "ONT-E-STEP-NOT-IN-SEQUENCE", "OUTSIDE_THE_SEQUENCE"),
    ("unknown_cost_class.yaml", "ONT-E-UNKNOWN-COST-CLASS", "EXTRAVAGANT"),
    ("unknown_confidence_component.yaml", "ONT-E-UNKNOWN-CONFIDENCE-COMPONENT", "vibes_support"),
)


@pytest.mark.parametrize(("fixture", "code", "expected_on_line"), LOCATED_CASES)
def test_invalid_pack_reports_its_own_code_at_its_own_line(
    fixtures_root: Path, fixture: str, code: str, expected_on_line: str
) -> None:
    path = fixtures_root / "invalid" / fixture

    _, findings = inspect_pack(path)

    errors = [item for item in findings if item.severity is Severity.ERROR]
    matching = [item for item in errors if item.code == code]
    assert matching, f"{fixture} produced {sorted({item.code for item in errors})}, not {code}"

    located = matching[0]
    assert located.file == path
    assert located.line is not None
    source_line = path.read_text(encoding="utf-8").splitlines()[located.line - 1]
    assert expected_on_line in source_line, (
        f"{fixture} pointed at line {located.line} ({source_line.strip()!r}), which does not "
        f"hold {expected_on_line!r}."
    )


@pytest.mark.parametrize(("fixture", "code", "_expected"), LOCATED_CASES)
def test_load_pack_refuses_every_invalid_pack(
    fixtures_root: Path, fixture: str, code: str, _expected: str
) -> None:
    with pytest.raises(ContractViolationError) as raised:
        load_pack(fixtures_root / "invalid" / fixture)

    assert code in str(raised.value)


def test_all_errors_are_reported_together_not_just_the_first(fixtures_root: Path) -> None:
    """One reload must reveal every problem, not the next one.

    An author who reloads once per message stops reading the messages.
    """
    source = (fixtures_root / "valid_minimal.yaml").read_text(encoding="utf-8")
    broken = source.replace("entity_type: THING}", "entity_type: NOPE}")
    path = fixtures_root / "invalid" / "_generated_many_errors.yaml"
    path.write_text(broken, encoding="utf-8")
    try:
        _, findings = inspect_pack(path)
    finally:
        path.unlink()

    errors = [item for item in findings if item.severity is Severity.ERROR]
    orphans = [item for item in errors if item.code == "ONT-E-UNKNOWN-ENTITY-TYPE"]
    assert len(orphans) > 1, "only the first orphan reference was reported"
    assert len({item.line for item in orphans}) > 1, "every report pointed at one line"


def test_a_derived_event_without_a_basis_is_refused(fixtures_root: Path) -> None:
    """ADR-0029: a reconstructed occurrence must say what it was reconstructed from."""
    with pytest.raises(ContractViolationError) as raised:
        load_pack(fixtures_root / "invalid" / "derived_without_basis.yaml")

    message = str(raised.value)
    assert "derived_without_basis.yaml" in message
    assert "ADR-0029" in message


def test_an_undeclared_key_is_refused_rather_than_ignored(fixtures_root: Path) -> None:
    """A typo in a key is otherwise indistinguishable from a deliberate omission."""
    with pytest.raises(ContractViolationError) as raised:
        load_pack(fixtures_root / "invalid" / "undeclared_key.yaml")

    assert "ONT-E-SCHEMA" in str(raised.value)


def test_a_missing_base_pack_is_named(fixtures_root: Path) -> None:
    with pytest.raises(ContractViolationError) as raised:
        load_pack(fixtures_root / "invalid" / "missing_base_pack.yaml")

    assert "no_such_base" in str(raised.value)


def test_a_withdrawal_that_removes_nothing_is_refused(fixtures_root: Path) -> None:
    """Omission and decision must not be the same text (ADR-0027)."""
    with pytest.raises(ContractViolationError) as raised:
        load_pack(fixtures_root / "invalid" / "withdrawal_removes_nothing.yaml")

    assert "NEVER_DECLARED" in str(raised.value)


def test_an_empty_document_is_refused(fixtures_root: Path, tmp_path: Path) -> None:
    empty = tmp_path / "ontology.yaml"
    empty.write_text("", encoding="utf-8")

    with pytest.raises(ContractViolationError):
        load_pack(empty)


def test_malformed_yaml_is_refused_rather_than_partially_parsed(tmp_path: Path) -> None:
    broken = tmp_path / "ontology.yaml"
    broken.write_text("pack_id: [unclosed\n", encoding="utf-8")

    with pytest.raises(ContractViolationError) as raised:
        load_pack(broken)

    assert "not valid YAML" in str(raised.value)
