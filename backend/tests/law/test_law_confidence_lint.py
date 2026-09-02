"""LAW-EVIDENCE's new enforcement must itself be tested.

`scripts/check_confidence_is_a_vector.py` closes the gap the core audit found: every
confidence in the repository is a `ConfidenceVector` today, but nothing *made* it one. The
guarantee held by discipline, and discipline is what LAW-EVIDENCE exists to replace.

`CONVENTIONS.md` §1 binds every enforcement script: a check that has never been observed to
reject has not been tested. These tests observe it rejecting.

The `strength` case is the one that decides whether this lint survives contact with the
codebase. `EvidenceItem.strength` is a bare float sitting one field away from a confidence,
and `docs/contracts.md` §5 explicitly sanctions it as one item's own weight. A lint that
fired on it would be disabled inside a week -- which is exactly how DEF-0001 happened.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.law

# Every shape the defect takes. A bare `confidence: float` field leads, because it is both
# the likeliest form and the one the first draft of the matcher missed.
VIOLATION_LINES = (
    "    confidence: float",
    "    confidence: int",
    "    confidence: float = 0.0",
    "    confidence: float | None = None",
    "    confidence: Optional[float]",
    "    edge_confidence: float",
    "    confidence_score: float",
    "    causal_confidence_value: Decimal",
    "    component_confidences: list[float]",
    "    CONFIDENCE: float = 0.5",
    "def edge_confidence(edge: object) -> float:",
)

# Lines that must stay clean. `strength` first, deliberately.
LEGITIMATE_LINES = (
    "    strength: float",
    "    propagation_weight: float",
    "    magnitude_multiplier: float",
    "    value: float",
    "    scalar: float",
    "    confidence: ConfidenceVector",
    "    confidence: ConfidenceVector | None = None",
    "    edge_confidence: ConfidenceVector",
    "def build_confidence(components: object) -> ConfidenceVector:",
    "    confidence_schema_version: str",
)


@pytest.mark.parametrize("line", VIOLATION_LINES)
def test_every_bare_float_shape_fires(confidence_lint: ModuleType, line: str) -> None:
    assert confidence_lint.violations_in(line), line


@pytest.mark.parametrize("line", LEGITIMATE_LINES)
def test_legitimate_lines_stay_clean(confidence_lint: ModuleType, line: str) -> None:
    assert confidence_lint.violations_in(line) == [], line


def test_evidence_item_strength_is_not_a_confidence(confidence_lint: ModuleType) -> None:
    """The false positive that would get this lint disabled.

    `docs/contracts.md` §5 sanctions `strength` as one item's own weight, distinct from a
    confidence. Asserted against the real source line, not a synthetic one, so a rename in
    `evidence.py` cannot make this test pass vacuously.
    """
    source = Path(confidence_lint.REPO_ROOT) / "backend/src/causalog/core/types/evidence.py"
    strength_lines = [
        line for line in source.read_text().splitlines() if line.strip().startswith("strength:")
    ]
    assert strength_lines, "EvidenceItem.strength has been renamed; update this test"
    for line in strength_lines:
        assert confidence_lint.violations_in(line) == []


def test_the_shipped_self_test_passes(confidence_lint: ModuleType) -> None:
    assert confidence_lint.self_test() == 0


def test_a_poisoned_must_not_fire_list_is_refused(
    confidence_lint: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DEF-0001's root cause, guarded against here before it can recur.

    A claimed false positive that is really a violation must be caught by something other
    than the matcher, so weakening the matcher cannot certify the hole as correct.
    """
    monkeypatch.setattr(
        confidence_lint,
        "MUST_NOT_FIRE",
        ("    strength: float", "    confidence: float", "    edge_confidence: int"),
    )
    assert confidence_lint.no_must_not_fire_entry_is_actually_a_violation() == 2


def test_a_planted_violation_is_detected(
    confidence_lint: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plant a bare-float confidence in a scanned tree and assert the lint reports it."""
    package = tmp_path / "causalog"
    package.mkdir()
    (package / "scorer.py").write_text("class Score:\n    confidence: float\n    strength: float\n")
    monkeypatch.setattr(confidence_lint, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(confidence_lint, "SCAN_ROOTS", (package,))
    monkeypatch.setattr(confidence_lint, "ALLOWLIST_PATH", tmp_path / ".lawevidence-allowlist")

    assert confidence_lint.scan() == 1  # confidence fires; strength does not


def test_the_allowlist_exempts_the_exact_symbol_only(
    confidence_lint: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An entry exempts one binding, never a family."""
    package = tmp_path / "causalog"
    package.mkdir()
    (package / "scorer.py").write_text(
        "legacy_confidence: float = 0.0\nlegacy_confidence_v2: float = 0.0\n"
    )
    allowlist = tmp_path / ".lawevidence-allowlist"
    allowlist.write_text(
        "causalog/scorer.py::legacy_confidence  # reviewed: frozen V0 payload, ADR pending\n"
    )
    monkeypatch.setattr(confidence_lint, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(confidence_lint, "SCAN_ROOTS", (package,))
    monkeypatch.setattr(confidence_lint, "ALLOWLIST_PATH", allowlist)

    assert confidence_lint.scan() == 1  # legacy_confidence_v2 is NOT covered


def test_an_allowlist_entry_without_justification_fails(
    confidence_lint: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The allowlist is a pressure valve, not a bypass."""
    allowlist = tmp_path / ".lawevidence-allowlist"
    allowlist.write_text("causalog/scorer.py::confidence\n")
    monkeypatch.setattr(confidence_lint, "ALLOWLIST_PATH", allowlist)

    with pytest.raises(SystemExit):
        confidence_lint.load_allowlist()


def test_the_repository_is_clean(confidence_lint: ModuleType) -> None:
    assert confidence_lint.scan() == 0
