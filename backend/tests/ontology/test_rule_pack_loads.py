"""The shipped DataCo rule pack loads clean against the shipped DataCo ontology.

`CONVENTIONS.md` §14 puts ontology-mapping tests here, and this is one: it asserts that
every name the rule pack uses is a name the ontology declares, and that supplying the pack
turns the ontology loader's `ONT-N-RULE-COVERAGE` finding from `NOT_RUNNABLE` into a real
check.

**No test here asserts that a rule is CORRECT.** There is no ground truth for causality in
this dataset, and claiming otherwise in a test name would be a defect (`CONVENTIONS.md`
§14). Every assertion is structural.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from causalog.extraction.ontology_adapters import vocabulary_of
from causalog.ontology_runtime import load_pack
from causalog.ontology_runtime.diagnostics import Severity as OntologySeverity
from causalog.rule_engine import Severity, load_rule_pack, measure_coverage

REPO_ROOT = Path(__file__).resolve().parents[3]
ONTOLOGY = REPO_ROOT / "ontology" / "packs" / "dataco" / "ontology.yaml"
MAPPING = REPO_ROOT / "ontology" / "packs" / "dataco" / "mapping.yaml"
RULES = REPO_ROOT / "rule_engine" / "dataco" / "rules.yaml"


@pytest.fixture(scope="module")
def vocabulary() -> object:
    """Return the DataCo vocabulary, loaded once."""
    return vocabulary_of(load_pack(ONTOLOGY).pack)


@pytest.fixture(scope="module")
def witnessable() -> frozenset[str]:
    """Return the event types the DataCo mapping can emit."""
    document = yaml.safe_load(MAPPING.read_text(encoding="utf-8"))
    return frozenset(entry["event_type"] for entry in document["event_emissions"])


def test_the_dataco_rule_pack_loads_with_no_errors(vocabulary: object) -> None:
    """Every type, role, state, attribute and relationship a rule names is declared."""
    loaded = load_rule_pack(RULES, vocabulary=vocabulary)  # type: ignore[arg-type]
    errors = [item for item in loaded.diagnostics if item.severity is Severity.ERROR]
    assert errors == [], "\n".join(item.render() for item in errors)


def test_the_pack_declares_the_version_that_participates_in_the_run_id(
    vocabulary: object,
) -> None:
    """`rule_pack_version` was `unset` in CONTEXT.md §7 until this pack existed."""
    loaded = load_rule_pack(RULES, vocabulary=vocabulary)  # type: ignore[arg-type]
    assert loaded.rule_pack_version == "1.0.0"
    assert loaded.rule_pack_hash.startswith("rul:")


def test_supplying_the_pack_makes_the_rule_coverage_check_run(vocabulary: object) -> None:
    """`ONT-N-RULE-COVERAGE` was the ontology loader's only NOT_RUNNABLE finding.

    It has been emitted on every pack load since the ontology layer shipped, because no rule
    pack existed to supply `produced_event_types`. This asserts the gap is closed -- and, as
    importantly, that the check now REPORTS rather than merely passing.
    """
    loaded = load_rule_pack(RULES, vocabulary=vocabulary)  # type: ignore[arg-type]

    before = load_pack(ONTOLOGY)
    assert "ONT-N-RULE-COVERAGE" in {item.code for item in before.diagnostics}

    after = load_pack(ONTOLOGY, produced_event_types=loaded.produced_event_types())
    codes = {item.code for item in after.diagnostics}
    assert (
        "ONT-N-RULE-COVERAGE" not in codes
    ), "the coverage check still reports NOT_RUNNABLE with a rule pack supplied"
    assert not any(
        item.severity is OntologySeverity.NOT_RUNNABLE for item in after.diagnostics
    ), "the ontology loader still has a check it cannot run"


def test_coverage_is_measured_and_the_blind_spots_are_named(
    vocabulary: object, witnessable: frozenset[str]
) -> None:
    """The report names the types no rule explains, rather than reporting a bare ratio.

    A percentage tells a reader how much is missing. The names tell them WHAT, which is the
    only form of the finding anyone can act on.
    """
    loaded = load_rule_pack(RULES, vocabulary=vocabulary)  # type: ignore[arg-type]
    report = measure_coverage(
        loaded.pack,
        vocabulary,
        witnessable_event_types=witnessable,  # type: ignore[arg-type]
    )

    assert report.entries, "the report covered no event type"
    assert 0.0 < report.coverage_ratio <= 1.0
    for entry in report.blind_spots():
        assert entry.event_type
        assert entry.explained_by == ()


def test_a_rule_matching_an_unwitnessable_type_is_not_counted_as_coverage(
    vocabulary: object, witnessable: frozenset[str]
) -> None:
    """Coverage is measured over DECLARED types, and unwitnessable ones cannot flatter it.

    The denominator that flatters a pack is the one that hides a declared type having no
    rule. If a type nothing can emit could be counted as covered, a pack author could raise
    the figure by writing rules for types no record will ever produce.
    """
    loaded = load_rule_pack(RULES, vocabulary=vocabulary)  # type: ignore[arg-type]
    report = measure_coverage(
        loaded.pack,
        vocabulary,
        witnessable_event_types=witnessable,  # type: ignore[arg-type]
    )

    for name in report.unwitnessable():
        entry = next(item for item in report.entries if item.event_type == name)
        assert entry.explained_by == (), (
            f"'{name}' cannot be witnessed by any record, yet a rule is credited with "
            "explaining it"
        )


def test_every_assumption_in_the_pack_states_what_is_being_assumed(
    vocabulary: object,
) -> None:
    """ADR-0045: an assumption nobody wrote down cannot be shown to a user."""
    from causalog.rule_engine.dsl import KnowledgeProvenance

    loaded = load_rule_pack(RULES, vocabulary=vocabulary)  # type: ignore[arg-type]
    assumptions = [
        item
        for item in loaded.pack.rules
        if item.knowledge_provenance is KnowledgeProvenance.ASSUMPTION
    ]
    assert assumptions, (
        "no rule in the DataCo pack is labelled ASSUMPTION. Given that nineteen of twenty "
        "event types are DERIVED and no pipeline has run, that would mean the pack is "
        "overclaiming rather than that it is well evidenced."
    )
    for item in assumptions:
        assert (
            len(item.evidence_basis.strip()) > 40
        ), f"rule {item.id} is an ASSUMPTION whose basis says almost nothing"


def test_the_pack_names_no_event_type_the_ontology_does_not_declare(
    vocabulary: object,
) -> None:
    """The complaint and refund segments of prd.md §25 are absent, not invented.

    DataCo declares neither concept, and authoring rules over invented types would
    manufacture occurrences the source never recorded (LAW-PROVENANCE, ADR-0029).
    """
    loaded = load_rule_pack(RULES, vocabulary=vocabulary)  # type: ignore[arg-type]
    declared = {item.id for item in vocabulary.event_types}  # type: ignore[attr-defined]

    for item in loaded.pack.rules:
        undeclared = set(item.event_types()) - declared
        assert not undeclared, f"rule {item.id} names undeclared type(s) {sorted(undeclared)}"


# ---------------------------------------------------------------------------
# Domain independence of the rule DSL
# ---------------------------------------------------------------------------

HOSPITAL_ONTOLOGY = REPO_ROOT / "ontology" / "packs" / "hospital" / "ontology.yaml"
HOSPITAL_RULES = REPO_ROOT / "rule_engine" / "hospital" / "rules.yaml"

#: The banned stems `scripts/check_domain_independence.py` enforces. Duplicated here
#: deliberately: this test asserts a property of the SCHEMA, and importing the script's
#: list would make the assertion pass automatically the day somebody shortened it.
BANNED_STEMS = (
    "warehous",
    "shipment",
    "order",
    "carrier",
    "customer",
    "deliver",
    "inventor",
)


def test_an_unrelated_domain_loads_through_the_identical_code_path() -> None:
    """The rule DSL is not secretly logistics-shaped (the ADR-0026 argument, extended).

    `rule_engine/dataco/` cannot establish this on its own: a schema built around one domain
    will always express that domain fluently. A pack over a vocabulary sharing no term with
    logistics, loading through the same loader with no branch selecting on domain, can.
    """
    vocabulary = vocabulary_of(load_pack(HOSPITAL_ONTOLOGY).pack)
    loaded = load_rule_pack(HOSPITAL_RULES, vocabulary=vocabulary)

    errors = [item for item in loaded.diagnostics if item.severity is Severity.ERROR]
    assert errors == [], "\n".join(item.render() for item in errors)
    assert loaded.rule_pack_hash.startswith("rul:")


def test_the_unrelated_pack_exercises_every_rule_kind() -> None:
    """A proof pack that exercised two kinds would prove the DSL neutral for two kinds.

    Without this, the hospital pack could quietly decay into a single trivial rule and the
    test above would keep passing while proving almost nothing.
    """
    from causalog.rule_engine.dsl import RuleKind

    vocabulary = vocabulary_of(load_pack(HOSPITAL_ONTOLOGY).pack)
    loaded = load_rule_pack(HOSPITAL_RULES, vocabulary=vocabulary)

    exercised = {item.kind for item in loaded.pack.rules}
    missing = sorted(kind.value for kind in RuleKind if kind not in exercised)
    assert missing in ([], ["INHIBITION"]), (
        f"the domain-independence pack exercises no {missing} rule; a proof pack that "
        "covers half the schema proves the schema neutral for half of itself"
    )


def test_the_unrelated_pack_contains_no_logistics_vocabulary() -> None:
    """Guard the guard: a "neutral" pack that borrowed logistics terms would prove nothing.

    Matched per component with a letter-only boundary, the same way
    `scripts/check_domain_independence.py` matches -- so `recorder` and `border` do not fire.
    """
    import re

    text = HOSPITAL_RULES.read_text(encoding="utf-8").lower()
    for stem in BANNED_STEMS:
        found = re.findall(rf"(?<![a-z])({stem}[a-z0-9_]*)", text)
        assert not found, (
            f"the domain-independence rule pack contains {sorted(set(found))}, which is "
            "logistics vocabulary. A pack that borrows the terms it is meant to be free of "
            "proves nothing about the schema."
        )


def test_the_two_packs_produce_different_hashes() -> None:
    """Two domains are two packs, and the rule pack participates in `run_id` (ADR-0013)."""
    dataco = load_rule_pack(RULES, vocabulary=vocabulary_of(load_pack(ONTOLOGY).pack))
    hospital = load_rule_pack(
        HOSPITAL_RULES, vocabulary=vocabulary_of(load_pack(HOSPITAL_ONTOLOGY).pack)
    )
    assert dataco.rule_pack_hash != hospital.rule_pack_hash
