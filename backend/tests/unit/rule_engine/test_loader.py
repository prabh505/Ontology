"""Loading: content addressing, the conflict refusal, and the checks that could not run."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from causalog.core.errors import ContractViolationError, RuleConflictError
from causalog.rule_engine import (
    Severity,
    inspect_rule_pack,
    load_rule_pack,
    rule_pack_hash,
)
from tests.fixtures.rules import STAGE_ONE, pack, rule, vocabulary


def _write(tmp_path: Path, *rules: dict[str, Any], **header: Any) -> Path:
    """Write a pack document to disk and return its path."""
    document: dict[str, Any] = {
        "rule_pack_schema_version": "1.0.0",
        "rule_pack_id": "fixture",
        "rule_pack_version": "1.0.0",
        "ontology_pack": "fixture",
        "description": "synthetic pack",
        "rules": list(rules),
    }
    document.update(header)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


def _modifier(identifier: str, kind: str, multiplier: float) -> dict[str, Any]:
    """Return a modifier rule targeting `R-ONE`."""
    return rule(
        identifier,
        kind=kind,
        replace_body={
            "modifier": {"binding": "MODIFIER", "event_type": STAGE_ONE},
            "modifies": "R-ONE",
            "window": {"minimum_seconds": 0, "maximum_seconds": 60},
            "relation": {
                "direction": "SHARED_PARTICIPANT",
                "cause_role": "SUBJECT",
                "effect_role": "SUBJECT",
            },
            "magnitude_multiplier": multiplier,
        },
    )


# ---------------------------------------------------------------------------
# Content addressing
# ---------------------------------------------------------------------------


def test_the_hash_is_stable_across_two_loads() -> None:
    """Determinism: one pack has one address (`CONVENTIONS.md` §9, §11)."""
    assert rule_pack_hash(pack(rule())) == rule_pack_hash(pack(rule()))


def test_the_hash_is_invariant_to_the_authored_rule_sequence() -> None:
    """A pack groups its rules for a reader; grouping must not change its identity."""
    forwards = rule_pack_hash(pack(rule("R-ALPHA"), rule("R-ZULU")))
    backwards = rule_pack_hash(pack(rule("R-ZULU"), rule("R-ALPHA")))
    assert forwards == backwards


def test_the_hash_moves_when_a_weight_moves_by_one_hundredth() -> None:
    """Sensitive to every declared value: editing a rule creates a new Run (ADR-0013)."""
    before = rule_pack_hash(pack(rule()))
    after = rule_pack_hash(pack(rule(base_strength=0.51)))
    assert before != after


def test_the_hash_carries_the_declared_prefix() -> None:
    """One hashing scheme, one prefix registry (ADR-0046)."""
    assert rule_pack_hash(pack(rule())).startswith("rul:")


# ---------------------------------------------------------------------------
# Conflicts -- at load, never at evaluation
# ---------------------------------------------------------------------------


def test_opposed_modifiers_are_refused_at_load(tmp_path: Path) -> None:
    """One trigger raising and lowering one claim is the coin-flip CONVENTIONS.md §7 bans."""
    path = _write(
        tmp_path,
        rule(),
        _modifier("M-UP", "AMPLIFICATION", 1.5),
        _modifier("M-DOWN", "INHIBITION", 0.5),
    )
    with pytest.raises(RuleConflictError, match="depend on evaluation sequence"):
        load_rule_pack(path, vocabulary=vocabulary())


def test_duplicated_rules_are_refused_at_load(tmp_path: Path) -> None:
    """Two rules identical but for identity double-count every candidate they propose."""
    path = _write(tmp_path, rule("R-ONE"), rule("R-TWO"))
    with pytest.raises(RuleConflictError, match="counted twice"):
        load_rule_pack(path, vocabulary=vocabulary())


def test_a_constraint_and_a_generator_over_one_type_are_not_a_conflict(
    tmp_path: Path,
) -> None:
    """They are complementary: the generator proposes, the constraint prunes.

    A first draft of the loader refused this pair, which would have refused the exact pack
    this seam exists to support. Pinned so nobody reaches for the appealing wrong check
    again (ADR-0047).
    """
    from tests.fixtures.rules import constraint

    path = _write(tmp_path, rule(), constraint())
    loaded = load_rule_pack(path, vocabulary=vocabulary())
    assert len(loaded.pack.rules) == 2


def test_modifiers_separated_by_a_condition_are_not_a_conflict(tmp_path: Path) -> None:
    """A condition is what separates two opposed modifiers into two cases."""
    conditioned = _modifier("M-DOWN", "INHIBITION", 0.5)
    conditioned["body"]["conditions"] = {
        "op": "IS_PRESENT",
        "operands": [
            {
                "op": "ATTRIBUTE",
                "address": {"binding": "MODIFIER", "role": "SUBJECT", "attribute": "stage"},
            }
        ],
    }
    path = _write(tmp_path, rule(), _modifier("M-UP", "AMPLIFICATION", 1.5), conditioned)
    assert len(load_rule_pack(path, vocabulary=vocabulary()).pack.rules) == 3


# ---------------------------------------------------------------------------
# Checks that could not run
# ---------------------------------------------------------------------------


def test_no_vocabulary_reports_not_runnable_and_never_passes(tmp_path: Path) -> None:
    """DEF-0001, OQ-014: a check that could not run must not read as one that passed."""
    path = _write(tmp_path, rule())
    loaded = load_rule_pack(path, vocabulary=None)

    codes = {item.code for item in loaded.diagnostics}
    assert "RUL-N-VOCABULARY" in codes
    not_runnable = [item for item in loaded.diagnostics if item.severity is Severity.NOT_RUNNABLE]
    assert not_runnable, "the loader reported a clean load without having checked anything"


def test_the_undecidable_conflict_class_is_reported_on_every_load(tmp_path: Path) -> None:
    """What the static check does NOT cover is stated rather than left to be assumed."""
    path = _write(tmp_path, rule())
    loaded = load_rule_pack(path, vocabulary=vocabulary())
    assert "RUL-N-CONDITIONAL-CONFLICT" in {item.code for item in loaded.diagnostics}


# ---------------------------------------------------------------------------
# Reference checking
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("description", "document", "expected_code"),
    [
        (
            "an undeclared event type",
            rule(body={"effect": {"binding": "EFFECT", "event_type": "NOT_DECLARED"}}),
            "RUL-E-UNDECLARED-EVENT-TYPE",
        ),
        (
            "a role the event type does not declare",
            rule(
                body={
                    "relation": {
                        "direction": "SHARED_PARTICIPANT",
                        "cause_role": "NOT_A_ROLE",
                        "effect_role": "SUBJECT",
                    }
                }
            ),
            "RUL-E-UNDECLARED-ROLE",
        ),
        (
            "an undeclared relationship type",
            rule(
                body={
                    "relation": {
                        "direction": "FROM_TO",
                        "cause_role": "SUBJECT",
                        "effect_role": "SUBJECT",
                        "relationship_type": "NOT_DECLARED",
                    }
                }
            ),
            "RUL-E-UNDECLARED-RELATIONSHIP-TYPE",
        ),
        (
            "a condition over an attribute nothing declares",
            rule(
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
                                    "attribute": "not_declared",
                                },
                            }
                        ],
                    }
                },
            ),
            "RUL-E-UNDECLARED-ATTRIBUTE",
        ),
    ],
)
def test_an_undeclared_reference_is_an_error(
    tmp_path: Path, description: str, document: dict[str, Any], expected_code: str
) -> None:
    """Every reference a rule makes is checked against the declared vocabulary."""
    path = _write(tmp_path, document)
    _, findings = inspect_rule_pack(path, vocabulary=vocabulary())

    codes = {item.code for item in findings if item.severity is Severity.ERROR}
    assert expected_code in codes, f"{description} was not reported: {codes}"


def test_a_modifier_pointing_at_a_missing_rule_is_an_error(tmp_path: Path) -> None:
    """A modifier rescaling nothing would load as if it worked."""
    path = _write(tmp_path, _modifier("M-ORPHAN", "AMPLIFICATION", 1.5))
    _, findings = inspect_rule_pack(path, vocabulary=vocabulary())
    assert "RUL-E-UNDECLARED-TARGET-RULE" in {item.code for item in findings}


def test_an_error_refuses_the_pack_and_names_every_one(tmp_path: Path) -> None:
    """An author who reloads ten times learns to distrust the tenth message."""
    path = _write(
        tmp_path,
        rule("R-ONE", body={"effect": {"binding": "EFFECT", "event_type": "MISSING_ONE"}}),
        rule("R-TWO", body={"cause": {"binding": "CAUSE", "event_type": "MISSING_TWO"}}),
    )
    with pytest.raises(ContractViolationError) as caught:
        load_rule_pack(path, vocabulary=vocabulary())

    message = str(caught.value)
    assert "MISSING_ONE" in message
    assert "MISSING_TWO" in message


# ---------------------------------------------------------------------------
# Malformed input
# ---------------------------------------------------------------------------


def test_a_pack_written_against_another_schema_version_is_refused(tmp_path: Path) -> None:
    """Reinterpreting it under a newer DSL silently changes what its rules mean."""
    path = _write(tmp_path, rule(), rule_pack_schema_version="0.9.0")
    with pytest.raises(ContractViolationError, match="rule_pack_schema_version"):
        load_rule_pack(path, vocabulary=vocabulary())


def test_a_non_mapping_document_is_refused(tmp_path: Path) -> None:
    """A pack is one document declaring `rules`, not a list and not a scalar."""
    path = tmp_path / "rules.yaml"
    path.write_text("- not a mapping\n", encoding="utf-8")
    with pytest.raises(ContractViolationError, match="not a mapping"):
        load_rule_pack(path, vocabulary=vocabulary())


def test_an_absent_file_is_refused_naming_the_path(tmp_path: Path) -> None:
    """The message names the file, because that is what the reader has to go and look at."""
    path = tmp_path / "absent.yaml"
    with pytest.raises(ContractViolationError, match="could not be read"):
        load_rule_pack(path, vocabulary=vocabulary())


def test_produced_event_types_excludes_a_disabled_rule() -> None:
    """Crediting a disabled rule would make switching one off invisible in coverage."""
    from causalog.rule_engine.loader import LoadedRulePack

    enabled = LoadedRulePack(pack=pack(rule()), rule_pack_hash="rul:0", diagnostics=())
    assert enabled.produced_event_types() != ()

    disabled = LoadedRulePack(
        pack=pack(rule(enabled=False, disabled_reason="retired")),
        rule_pack_hash="rul:0",
        diagnostics=(),
    )
    assert disabled.produced_event_types() == ()
