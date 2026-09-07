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
    """`rule_pack_version` was `unset` in CONTEXT.md §7 until this pack existed.

    Moved 1.0.0 -> 1.1.0 when the pack gained its `candidate_generation` block for module 9,
    1.1.0 -> 1.2.0 when it gained `confidence_scoring` for module 10 (ADR-0053), and
    1.2.0 -> 1.3.0 when it gained `graph_construction` for the Causal Graph Builder
    (ADR-0055), 1.3.0 -> 1.4.0 when it gained `derived_precedence_temporal_support`
    (ADR-0057), and 1.4.0 -> 1.5.0 when it gained `propagation_analysis`,
    `root_cause_analysis` and `pattern_mining` for modules 12 and 11 and the pattern miner
    (ADR-0063), 1.5.0 -> 1.6.0 when it gained `counterfactual_simulation` for module 13
    (ADR-0071), and 1.6.0 -> 1.7.0 when it gained `recommendation` for module 14 (ADR-0079).
    No bump is incidental: `rule_pack_version` participates in `run_id`
    (ADR-0013), so declaring a proximity window, declaring how to score one, declaring which
    claims the engine will stand behind, or declaring how far consequence travels each mints
    a new Run and re-dates every artifact derived under it. Pinned here so that a version
    edit is a deliberate act with a failing test attached, rather than a silent re-dating of
    every committed report.

    This test has now fired SEVEN times, which is it working. R-19 predicted exactly this,
    and each firing has been followed by regenerating every report under the new `run_id`
    rather than by editing the pin alone.

    The sixth firing was the first where `run_id` moved for TWO reasons at once: ADR-0071
    moved `rule_pack_version` and ADR-0067 moved `ontology_hash` in the same commit, and both
    are `RunKey` inputs. A pin that tracked only one of them would have gone green while the
    Run underneath it changed.

    The seventh firing has the same shape and is therefore no longer a surprise: ADR-0079
    moved `rule_pack_version` to 1.7.0 and ADR-0073 moved `ontology_hash` by adding the
    `risk_classes` vocabulary and a `risk_class` per actionable event type. Two `RunKey`
    inputs, one commit, one new Run. That this now reads as ordinary is the point of pinning
    it: the second occurrence of a hazard should be routine, not a rediscovery.
    """
    loaded = load_rule_pack(RULES, vocabulary=vocabulary)  # type: ignore[arg-type]
    assert loaded.rule_pack_version == "1.7.0"
    assert loaded.rule_pack_hash.startswith("rul:")


def test_the_pack_declares_every_parameter_module_nine_needs(vocabulary: object) -> None:
    """A generator with no declared parameter does not run, and must say so rather than zero.

    Pinned here so that removing a declaration is a test failure naming the generator it
    switches off, rather than a silently emptier candidate graph. The DataCo pack declares
    all of them; the hospital pack deliberately declares none, and that asymmetry is the
    point -- it exercises both halves of the 1.1.0 contract.
    """
    loaded = load_rule_pack(RULES, vocabulary=vocabulary)  # type: ignore[arg-type]
    parameters = loaded.pack.candidate_generation

    assert parameters.proximity_windows, "temporal_proximity would not run"
    assert parameters.structural_max_hops is not None, "structural_path would not run"
    assert parameters.structural_path_strength is not None
    assert parameters.minimum_support_count is not None, "historical_frequency would not run"
    assert parameters.historical_frequency_strength is not None
    assert parameters.minimum_lift is not None, "statistical_association would not run"
    assert parameters.statistical_association_strength is not None
    assert parameters.shared_entity_strength is not None, "shared_entity would not run"
    assert parameters.shared_identifier_strength is not None
    assert parameters.per_effect_candidate_cap is not None

    # Every window states why it is that wide. A threshold nobody justified is a threshold
    # nobody can argue with, which is the same requirement `Rule.rationale` carries.
    for entry in parameters.proximity_windows:
        assert entry.rationale.strip()
        assert 0.0 <= entry.evidence_strength <= 1.0


def test_the_pack_declares_every_parameter_module_ten_needs(vocabulary: object) -> None:
    """A scorer with no declared parameter is NOT SCORABLE, and that is contagious.

    Module 10 refuses to invent a threshold, so an absent declaration does not degrade one
    component gracefully -- it marks the component missing, which lowers `measured` and can
    drop the whole edge below `minimum_scored_components` into `INSUFFICIENT_EVIDENCE`.
    Removing a declaration here is therefore not a small edit, and it should fail a test that
    names the scorer it switches off rather than showing up as a quieter graph.

    `derived_precedence_temporal_support` is the newest of these and the reason the pack is
    at 1.4.0: without it, an edge whose precedence module 1 measured as arithmetic scores no
    temporal support at all rather than the capped value the pack intends (ADR-0057).
    """
    loaded = load_rule_pack(RULES, vocabulary=vocabulary)  # type: ignore[arg-type]
    scoring = loaded.pack.confidence_scoring

    assert scoring.lift_reference is not None, "statistical_support would not run"
    assert scoring.small_sample_prior_count is not None, "historical_support would not run"
    assert scoring.evidence_count_saturation_k is not None, "evidence_count would not run"
    assert scoring.temporal_reference_seconds is not None, "temporal_support would not run"
    assert scoring.undetermined_temporal_support is not None
    assert (
        scoring.derived_precedence_temporal_support is not None
    ), "an edge resting on a confirmed derivation would score no temporal support at all"
    assert scoring.minimum_scored_components is not None

    # A derived precedence is worth strictly LESS than a tie the data could not break: the
    # tie placed both events, the derivation placed one and restated it. A pack that inverts
    # this is saying an instant its own source computed is better evidence than one it
    # recorded twice, which is not a position any pack should hold by accident.
    assert scoring.derived_precedence_temporal_support <= scoring.undetermined_temporal_support


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
