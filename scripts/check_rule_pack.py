#!/usr/bin/env python3
"""Validate a rule pack against its ontology and its schema mapping, and report coverage.

This script lives in `scripts/` rather than in a package because it needs three things no
single layer may hold at once: the rule pack (L5), the ontology (L1), and the schema mapping
(L2). Forbidden edge F3 blocks `rule_engine` from importing `ontology_runtime` at all
(`docs/architecture.md` §1.4), so the one place that can hold all three is outside the layer
map entirely.

What it checks
--------------
  ERROR         a rule naming an event type, entity type, state, role, attribute or
                relationship type the ontology does not declare; a duplicate rule
                identifier; a modifier pointing at a rule that does not exist. Any of these
                fails the build.
  RULE CONFLICT the pack contradicts itself. Raised by the loader, not collected here: a
                self-contradictory pack is a load failure, never a judgement a caller weighs
                (`CONVENTIONS.md` §7).
  WARNING       a rule whose consequent event type has no emission rule in `mapping.yaml`,
                so no record can ever witness it. The rule is dead data: it will load, it
                will never fire, and nothing else would say so.
  NOT_RUNNABLE  a check this script could not perform, named rather than skipped.

What it reports
---------------
Coverage: which declared event types have a rule explaining them, and which do not. **The
ones that do not are the blind spots of the whole system.** `docs/architecture.md` §8 carries
it as the second open risk -- recall is bounded by rule coverage, and the system cannot
report what it missed. This report does not fix that. It makes the measurable part loud.

`--self-test` proves each rule rejects the violation it exists to catch, before the scan
runs. Every enforcement script in this repository does this: a check observed only to pass
has not been observed to work (DEF-0001, ADR-0019).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

import yaml  # noqa: E402

from causalog.core.errors import ContractViolationError, RuleConflictError  # noqa: E402
from causalog.core.ontology_view import VocabularyView  # noqa: E402
from causalog.extraction.ontology_adapters import vocabulary_of  # noqa: E402
from causalog.ontology_runtime import load_pack  # noqa: E402
from causalog.rule_engine import (  # noqa: E402
    CoverageReport,
    Diagnostic,
    Severity,
    inspect_rule_pack,
    measure_coverage,
    render,
    render_markdown,
    rule_pack_hash,
)
from causalog.rule_engine.dsl import RulePackSpec  # noqa: E402


def _ontology_path(domain: str) -> Path:
    """Return the ontology pack path for a domain."""
    return REPO_ROOT / "ontology" / "packs" / domain / "ontology.yaml"


def _mapping_path(domain: str) -> Path:
    """Return the schema mapping path for a domain."""
    return REPO_ROOT / "ontology" / "packs" / domain / "mapping.yaml"


def _rules_path(domain: str) -> Path:
    """Return the rule pack path for a domain (extension seam 4, architecture §5.1)."""
    return REPO_ROOT / "rule_engine" / domain / "rules.yaml"


def witnessable_event_types(mapping_path: Path) -> frozenset[str] | None:
    """Return the event types some emission rule can produce, or None if unreadable.

    `None` is returned rather than an empty set, and the difference matters: an empty set
    would mean "the mapping emits nothing", which would mark every declared type
    unwitnessable and make every blind spot vanish from the report. `None` means the check
    could not run, and is reported as such.
    """
    if not mapping_path.exists():
        return None
    document = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        return None
    emissions = document.get("event_emissions")
    if not isinstance(emissions, list):
        return None
    return frozenset(
        str(rule["event_type"])
        for rule in emissions
        if isinstance(rule, dict) and "event_type" in rule
    )


def check_reachability(
    pack: RulePackSpec, witnessable: frozenset[str] | None, path: Path
) -> tuple[Diagnostic, ...]:
    """Return a finding for every rule whose consequent no record can witness.

    A rule matching an event type the mapping never emits is dead data: it loads, it
    validates, and it can never fire. Nothing else in the system reports that, because the
    ontology legitimately declares types this dataset cannot witness and the rule pack
    legitimately names declared types.
    """
    if witnessable is None:
        return (
            Diagnostic(
                severity=Severity.NOT_RUNNABLE,
                code="RUL-N-REACHABILITY",
                message=(
                    "no schema mapping was readable, so 'every rule matches an event type "
                    "some record can witness' was NOT CHECKED. Reported rather than "
                    "skipped (DEF-0001, OQ-014)."
                ),
                file=path,
            ),
        )
    findings: list[Diagnostic] = []
    for rule in pack.enabled_rules():
        unwitnessable = sorted(set(rule.event_types()) - witnessable)
        if unwitnessable:
            findings.append(
                Diagnostic(
                    severity=Severity.WARNING,
                    code="RUL-W-UNREACHABLE-RULE",
                    message=(
                        f"rule '{rule.id}' matches event type(s) {unwitnessable}, for which "
                        "the schema mapping carries no emission rule. No record can witness "
                        "them, so this rule can never fire. Either the mapping is missing an "
                        "emission or the rule is dead data."
                    ),
                    path=f"rules[{rule.id}]",
                    file=path,
                )
            )
    return tuple(findings)


def check(
    rules_path: Path, ontology_path: Path, mapping_path: Path
) -> tuple[int, CoverageReport | None, tuple[Diagnostic, ...]]:
    """Run every check. Returns (error count, coverage report or None, all findings)."""
    ontology = load_pack(ontology_path)
    vocabulary = vocabulary_of(ontology.pack)
    return _check_against(rules_path, vocabulary, mapping_path)


def _check_against(
    rules_path: Path, vocabulary: VocabularyView, mapping_path: Path
) -> tuple[int, CoverageReport | None, tuple[Diagnostic, ...]]:
    """Check one rule pack against an already-resolved vocabulary."""
    try:
        pack, findings = inspect_rule_pack(rules_path, vocabulary=vocabulary)
    except RuleConflictError as error:
        print(f"RULE CONFLICT: {error}")
        return 1, None, ()
    except ContractViolationError as error:
        print(f"INVALID RULE PACK: {error}")
        return 1, None, ()

    witnessable = witnessable_event_types(mapping_path)
    findings = (*findings, *check_reachability(pack, witnessable, rules_path))
    errors = sum(1 for item in findings if item.severity is Severity.ERROR)
    report = measure_coverage(pack, vocabulary, witnessable_event_types=witnessable)
    return errors, report, findings


def _write_reports(domain: str, report: CoverageReport, rules_path: Path) -> Path:
    """Write the coverage report beside the dataset's other reports, and return its path."""
    directory = REPO_ROOT / "docs" / "reports" / domain
    directory.mkdir(parents=True, exist_ok=True)
    document = directory / "rule-coverage.md"
    document.write_text(render_markdown(report), encoding="utf-8")
    payload = {
        "rule_pack_id": report.rule_pack_id,
        "rule_pack_version": report.rule_pack_version,
        "rule_pack_hash": rule_pack_hash(
            RulePackSpec.model_validate(
                yaml.safe_load(rules_path.read_text(encoding="utf-8"))
            )
        ),
        "ontology_pack": report.ontology_pack,
        "rules_total": report.rules_total,
        "rules_enabled": report.rules_enabled,
        "rules_by_knowledge_provenance": dict(report.rules_by_knowledge_provenance),
        "event_types_declared": len(report.entries),
        "event_types_explained": report.explained_count,
        "coverage_ratio": round(report.coverage_ratio, 6),
        "witnessability_checked": report.witnessability_checked,
        "blind_spots": [entry.event_type for entry in report.blind_spots()],
        "unwitnessable": list(report.unwitnessable()),
        "entries": [
            {
                "event_type": entry.event_type,
                "explained_by": list(entry.explained_by),
                "reasoned_from_by": list(entry.reasoned_from_by),
                "witnessable": entry.witnessable,
            }
            for entry in report.entries
        ],
    }
    (directory / "rule-coverage.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return document


# ---------------------------------------------------------------------------
# Self-test (ADR-0019): observed to reject, not merely to pass.
# ---------------------------------------------------------------------------

_BASE_RULE = {
    "id": "R-A",
    "kind": "CAUSAL",
    "description": "d",
    "rationale": "r",
    "author": "a",
    "knowledge_provenance": "DOMAIN_EXPERTISE",
    "evidence_basis": "b",
    "base_strength": 0.5,
    "body": {
        "cause": {"binding": "CAUSE", "event_type": "T_ALPHA"},
        "effect": {"binding": "EFFECT", "event_type": "T_BETA"},
        "window": {"minimum_seconds": 0, "maximum_seconds": 60},
        "relation": {
            "direction": "SHARED_PARTICIPANT",
            "cause_role": "SUBJECT",
            "effect_role": "SUBJECT",
        },
    },
}


def _pack(*rules: dict[str, object]) -> dict[str, object]:
    """Build a minimal, domain-free pack document around the given rules."""
    return {
        "rule_pack_schema_version": "1.0.0",
        "rule_pack_id": "selftest",
        "rule_pack_version": "1.0.0",
        "ontology_pack": "selftest",
        "description": "self-test pack",
        "rules": list(rules),
    }


def _vocabulary() -> VocabularyView:
    """Build a domain-free vocabulary the self-test's packs are checked against."""
    return VocabularyView.model_validate(
        {
            "event_types": [
                {
                    "id": "T_ALPHA",
                    "participants": [
                        {"role": "SUBJECT", "entity_type": "E_ONE", "required": True}
                    ],
                    "required_attributes": ["alpha_value"],
                },
                {
                    "id": "T_BETA",
                    "participants": [
                        {"role": "SUBJECT", "entity_type": "E_ONE", "required": True}
                    ],
                    "required_attributes": [],
                },
            ],
            "entity_types": [
                {
                    "id": "E_ONE",
                    "state_names": ["S_OPEN", "S_SHUT"],
                    "terminal_state_names": ["S_SHUT"],
                    "attribute_names": ["alpha_value"],
                }
            ],
            "relationship_types": [
                {
                    "id": "R_LINKS",
                    "from_entity_type": "E_ONE",
                    "to_entity_type": "E_ONE",
                }
            ],
        }
    )


def _modifier(identifier: str, kind: str, multiplier: float) -> dict[str, object]:
    """Build a modifier rule for the opposed-modifier self-test case."""
    return {
        **_BASE_RULE,
        "id": identifier,
        "kind": kind,
        "body": {
            "modifier": {"binding": "MODIFIER", "event_type": "T_ALPHA"},
            "modifies": "R-A",
            "window": {"minimum_seconds": 0, "maximum_seconds": 60},
            "relation": {
                "direction": "SHARED_PARTICIPANT",
                "cause_role": "SUBJECT",
                "effect_role": "SUBJECT",
            },
            "magnitude_multiplier": multiplier,
        },
    }


def _replace(path: tuple[str, ...], value: object) -> dict[str, object]:
    """Return `_BASE_RULE` with one nested field replaced."""
    rule = json.loads(json.dumps(_BASE_RULE))
    target = rule
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return rule


#: (description, pack document, must the check fail?). Every ERROR shape this script exists
#: to catch appears here as a MUST-REJECT, and the well-formed pack appears as a MUST-ACCEPT
#: -- a check that rejects everything is as useless as one that rejects nothing.
_CASES: tuple[tuple[str, dict[str, object], bool], ...] = (
    ("a well-formed pack", _pack(_BASE_RULE), False),
    (
        "a rule naming an undeclared event type",
        _pack(
            _replace(
                ("body", "effect"), {"binding": "EFFECT", "event_type": "T_MISSING"}
            )
        ),
        True,
    ),
    (
        "a rule binding a role its event type does not declare",
        _pack(
            _replace(
                ("body", "relation"),
                {
                    "direction": "SHARED_PARTICIPANT",
                    "cause_role": "NOT_A_ROLE",
                    "effect_role": "SUBJECT",
                },
            )
        ),
        True,
    ),
    (
        "a rule traversing an undeclared relationship type",
        _pack(
            _replace(
                ("body", "relation"),
                {
                    "direction": "FROM_TO",
                    "cause_role": "SUBJECT",
                    "effect_role": "SUBJECT",
                    "relationship_type": "R_MISSING",
                },
            )
        ),
        True,
    ),
    (
        "a condition reading an attribute nothing declares",
        _pack(
            _replace(
                ("body", "conditions"),
                {
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
                },
            )
        ),
        True,
    ),
    (
        "a modifier pointing at a rule that does not exist",
        _pack(_modifier("M-X", "AMPLIFICATION", 1.5)),
        True,
    ),
    (
        "a duplicate rule identifier",
        _pack(_BASE_RULE, {**_BASE_RULE, "base_strength": 0.9}),
        True,
    ),
    (
        "an amplification and an inhibition opposing each other unconditionally",
        _pack(
            _BASE_RULE,
            _modifier("M-UP", "AMPLIFICATION", 1.5),
            _modifier("M-DOWN", "INHIBITION", 0.5),
        ),
        True,
    ),
    (
        "two rules identical in everything but identity",
        _pack(_BASE_RULE, {**_BASE_RULE, "id": "R-B"}),
        True,
    ),
    (
        "a constraint and a generator naming one event type",
        _pack(
            _BASE_RULE,
            {
                **_BASE_RULE,
                "id": "C-A",
                "kind": "CONSTRAINT",
                "body": {
                    "subject_entity_type": "E_ONE",
                    "subject_state": "S_SHUT",
                    "subject_role": "SUBJECT",
                    "forbidden_event_type": "T_BETA",
                },
            },
        ),
        False,
    ),
)


def self_test() -> int:
    """Prove every rule rejects its violation and accepts a well-formed pack."""
    failures = 0
    vocabulary = _vocabulary()
    scratch = Path(tempfile.mkdtemp(prefix="rulepack-selftest-"))
    try:
        for index, (description, document, must_fail) in enumerate(_CASES):
            rules_path = scratch / f"case{index}.yaml"
            rules_path.write_text(yaml.safe_dump(document), encoding="utf-8")
            # The checks print their diagnostics, and a self-test that dumped eight
            # deliberate violations would bury the one line that matters. Captured, not
            # suppressed: a failing case prints everything it produced.
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                errors, _, findings = _check_against(
                    rules_path, vocabulary, scratch / "absent.yaml"
                )
            observed = errors > 0
            if observed != must_fail:
                verb = "reject" if must_fail else "accept"
                print(f"SELF-TEST FAILED: the check did not {verb} -- {description}")
                print(captured.getvalue())
                if findings:
                    print(render(findings))
                failures += 1
    finally:
        for leftover in scratch.glob("*"):
            leftover.unlink()
        scratch.rmdir()

    if failures:
        return failures
    rejected = sum(1 for _, _, must_fail in _CASES if must_fail)
    accepted = len(_CASES) - rejected
    # The banner wording is the repository's convention, asserted by
    # `tests/law/test_enforcement_scripts_prove_themselves.py`: an exit code alone is not
    # evidence a self-test ran.
    print(
        f"self-test passed: {rejected} rule-pack violation shape(s) rejected, "
        f"{accepted} legitimate pack(s) accepted."
    )
    return 0


def main() -> int:
    """Run the self-test, or check one domain's rule pack and write its coverage report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="dataco", help="the domain to check")
    parser.add_argument(
        "--self-test", action="store_true", help="prove the checks reject"
    )
    parser.add_argument(
        "--no-write", action="store_true", help="check and print, but write no report"
    )
    arguments = parser.parse_args()

    if arguments.self_test:
        return 1 if self_test() else 0

    domain = arguments.dataset
    rules_path = _rules_path(domain)
    if not rules_path.exists():
        print(f"NOT-RUNNABLE: no rule pack at {rules_path.relative_to(REPO_ROOT)}.")
        return 2

    errors, report, findings = check(
        rules_path, _ontology_path(domain), _mapping_path(domain)
    )
    if findings:
        print(render(findings))
        print()
    if errors or report is None:
        print(f"{errors} error(s). The rule pack is refused.")
        return 1

    print(
        f"rule pack '{report.rule_pack_id}' v{report.rule_pack_version}: "
        f"{report.rules_enabled} of {report.rules_total} rule(s) enabled, "
        f"{report.explained_count} of {len(report.entries)} declared event type(s) "
        f"explained ({report.coverage_ratio:.0%})."
    )
    spots = report.blind_spots()
    if spots:
        print(
            f"\nBLIND SPOTS -- {len(spots)} declared event type(s) with no explanatory rule:"
        )
        for entry in spots:
            print(f"  {entry.event_type}")
    if not arguments.no_write:
        written = _write_reports(domain, report, rules_path)
        print(f"\ncoverage report: {written.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
