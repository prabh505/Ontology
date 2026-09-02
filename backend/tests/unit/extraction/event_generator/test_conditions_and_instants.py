"""Module 4's stated failure modes: every operator, every instant policy, every refusal.

Domain-neutral wherever it can be. The condition operators and the interval policies are
engine mechanics and are tested against synthetic records built here; only the tests that
need a real pack reach for the fixture, and those live behind the DataCo harness like every
other DataCo-derived test (`CONVENTIONS.md` §14).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from causalog.core.errors import ContractViolationError, DataQualityError
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import UNKNOWN_EARLIEST, UNKNOWN_LATEST, Precision, TimeInterval
from causalog.extraction.event_generator import (
    ConditionCounters,
    MissingEventPolicy,
    coarser,
    evaluate,
    occurred_at,
    occurrence_key,
)
from causalog.ingestion.schema_mapper import MappedRecord
from causalog.ingestion.schema_mapper.dsl import (
    AttributeRef,
    ConditionExpression,
    ConditionOperator,
    OccurredAtPolicy,
    OccurredAtSpec,
)
from extraction_harness import Harness, build_batches, envelope_for, harness_for
from fixtures.dataco.expansion import GROUND_TRUTH_DATASET_VERSION, rows


def attribute(concept: str, name: str) -> ConditionExpression:
    return ConditionExpression(op=ConditionOperator.ATTRIBUTE, concept=concept, attribute=name)


def constant(value: str) -> ConditionExpression:
    return ConditionExpression(op=ConditionOperator.CONSTANT, value=value)


def record(**values: str) -> MappedRecord:
    return MappedRecord(
        evidence_record_id="evd:0000000000000000",
        row_number=1,
        values=tuple(sorted((f"THING.{name}", value) for name, value in values.items())),
    )


def check(
    condition: ConditionExpression,
    subject: MappedRecord,
    counters: ConditionCounters | None = None,
) -> bool:
    return evaluate(condition, subject, event_type="THING_HAPPENED", counters=counters)


# --- the operator set ---------------------------------------------------------------------


def test_always_holds_for_every_record() -> None:
    assert check(ConditionExpression(op=ConditionOperator.ALWAYS), record())


def test_equals_and_not_equals_compare_as_text() -> None:
    subject = record(state="OPEN")
    equals = ConditionExpression(
        op=ConditionOperator.EQUALS, operands=(attribute("THING", "state"), constant("OPEN"))
    )
    assert check(equals, subject)
    unequal = ConditionExpression(
        op=ConditionOperator.NOT_EQUALS, operands=(attribute("THING", "state"), constant("OPEN"))
    )
    assert not check(unequal, subject)


def test_in_tests_membership_of_the_declared_set() -> None:
    condition = ConditionExpression(
        op=ConditionOperator.IN,
        values=("CLOSED", "OPEN"),
        operands=(attribute("THING", "state"),),
    )
    assert check(condition, record(state="OPEN"))
    assert not check(condition, record(state="PENDING"))


def test_presence_operators_distinguish_absent_from_empty() -> None:
    present = ConditionExpression(
        op=ConditionOperator.IS_PRESENT, operands=(attribute("THING", "state"),)
    )
    absent = ConditionExpression(
        op=ConditionOperator.IS_ABSENT, operands=(attribute("THING", "state"),)
    )
    assert check(present, record(state="OPEN"))
    assert not check(present, record())
    assert check(absent, record())
    assert not check(absent, record(state="OPEN"))


def test_numeric_comparison_is_arithmetic_and_never_lexicographic() -> None:
    """`'9' > '10'` is true as text and false as arithmetic. The rule means arithmetic."""
    condition = ConditionExpression(
        op=ConditionOperator.GREATER_THAN,
        operands=(attribute("THING", "realised"), attribute("THING", "planned")),
    )
    assert not check(condition, record(realised="9", planned="10"))
    assert check(condition, record(realised="11", planned="10"))
    less = ConditionExpression(
        op=ConditionOperator.LESS_THAN,
        operands=(attribute("THING", "realised"), attribute("THING", "planned")),
    )
    assert check(less, record(realised="9", planned="10"))


def test_a_non_numeric_operand_in_a_numeric_comparison_is_loud() -> None:
    condition = ConditionExpression(
        op=ConditionOperator.GREATER_THAN,
        operands=(attribute("THING", "realised"), constant("10")),
    )
    with pytest.raises(DataQualityError, match="is not a number"):
        check(condition, record(realised="soon"))


def test_junctions_combine_and_negation_inverts() -> None:
    subject = record(state="OPEN", realised="5")
    both = ConditionExpression(
        op=ConditionOperator.AND,
        operands=(
            ConditionExpression(
                op=ConditionOperator.EQUALS,
                operands=(attribute("THING", "state"), constant("OPEN")),
            ),
            ConditionExpression(
                op=ConditionOperator.IS_PRESENT, operands=(attribute("THING", "realised"),)
            ),
        ),
    )
    assert check(both, subject)
    assert not check(ConditionExpression(op=ConditionOperator.NOT, operands=(both,)), subject)


def test_an_absent_operand_makes_a_comparison_false_and_counts_it() -> None:
    """Absence is false, and it is counted.

    A rule that cannot fire must stay distinguishable from one whose condition was never met.
    """
    counters = ConditionCounters()
    condition = ConditionExpression(
        op=ConditionOperator.EQUALS,
        operands=(attribute("THING", "state"), constant("OPEN")),
    )
    assert not check(condition, record(), counters=counters)
    assert counters.sequenced() == (("THING_HAPPENED", "THING.state", 1),)


def test_is_absent_is_not_counted_as_unevaluable() -> None:
    """Asking whether a value is missing is a question the data CAN answer."""
    counters = ConditionCounters()
    condition = ConditionExpression(
        op=ConditionOperator.IS_ABSENT, operands=(attribute("THING", "state"),)
    )
    assert check(condition, record(), counters=counters)
    assert counters.sequenced() == ()


def test_or_evaluates_every_branch_so_counts_do_not_depend_on_branch_sequence() -> None:
    counters = ConditionCounters()
    condition = ConditionExpression(
        op=ConditionOperator.OR,
        operands=(
            ConditionExpression(
                op=ConditionOperator.IS_PRESENT, operands=(attribute("THING", "state"),)
            ),
            ConditionExpression(
                op=ConditionOperator.EQUALS,
                operands=(attribute("THING", "other"), constant("X")),
            ),
        ),
    )
    assert check(condition, record(state="OPEN"), counters=counters)
    assert counters.sequenced() == (("THING_HAPPENED", "THING.other", 1),)


# --- the DSL's own refusals ---------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        {"op": ConditionOperator.AND, "operands": ()},
        {"op": ConditionOperator.NOT, "operands": ()},
        {"op": ConditionOperator.IN, "operands": (), "values": ("A",)},
        {"op": ConditionOperator.IN, "operands": (), "values": ()},
        {"op": ConditionOperator.ATTRIBUTE, "concept": "THING"},
        {"op": ConditionOperator.CONSTANT, "concept": "THING", "value": "X"},
        {"op": ConditionOperator.ALWAYS, "value": "X"},
    ],
)
def test_a_malformed_condition_is_refused_at_load(bad: dict[str, object]) -> None:
    with pytest.raises(Exception, match="condition"):
        ConditionExpression(**bad)


def test_two_identity_bindings_for_one_entity_type_are_refused() -> None:
    """An emission rule declares no participants because ONE key per type determines them.

    Two keys would make which participant an event names a function of document sequence,
    which is the same defect `_cleaning_plan` refuses for two transform chains on one column.
    """
    from causalog.ingestion.schema_mapper.dsl import IdentityBindingSpec, SchemaMappingSpec

    with pytest.raises(Exception, match="more than one identity binding"):
        SchemaMappingSpec(
            mapping_schema_version="1.1.0",
            mapping_id="planted",
            mapping_version="1.0.0",
            ontology_pack="planted",
            description="a planted violation",
            identity_bindings=(
                IdentityBindingSpec(entity_type="THING", key_columns=("a",)),
                IdentityBindingSpec(entity_type="THING", key_columns=("b",)),
            ),
        )


def test_two_emission_rules_for_one_event_type_are_refused() -> None:
    """A disjunction is written with OR inside one rule, not as two entries."""
    from causalog.ingestion.schema_mapper.dsl import (
        EventEmissionSpec,
        OccurredAtPolicy,
        OccurredAtSpec,
        SchemaMappingSpec,
    )

    rule = EventEmissionSpec(
        event_type="THING_HAPPENED",
        when=ConditionExpression(op=ConditionOperator.ALWAYS),
        occurred_at=OccurredAtSpec(policy=OccurredAtPolicy.UNKNOWN, derivation="none"),
        rationale="a planted violation",
    )
    with pytest.raises(Exception, match="more than one emission rule"):
        SchemaMappingSpec(
            mapping_schema_version="1.1.0",
            mapping_id="planted",
            mapping_version="1.0.0",
            ontology_pack="planted",
            description="a planted violation",
            event_emissions=(rule, rule),
        )


def test_an_in_condition_with_unsequenced_values_is_refused() -> None:
    with pytest.raises(Exception, match="sequenced"):
        ConditionExpression(
            op=ConditionOperator.IN,
            values=("OPEN", "CLOSED"),
            operands=(attribute("THING", "state"),),
        )


# --- the interval policies ----------------------------------------------------------------


def interval(
    day: int,
    precision: Precision,
    provenance: ProvenanceClass = ProvenanceClass.OBSERVED,
) -> TimeInterval:
    start = datetime(2018, 1, day, tzinfo=UTC)
    span = {Precision.DAY: 86399, Precision.MINUTE: 59}[precision]
    return TimeInterval(
        t_earliest=start,
        t_latest=start.replace(microsecond=0) + __import__("datetime").timedelta(seconds=span),
        precision=precision,
        provenance=provenance,
        source="test",
    )


def timed(**intervals: TimeInterval) -> MappedRecord:
    return MappedRecord(
        evidence_record_id="evd:0000000000000000",
        row_number=1,
        values=(("THING.days", "3"),),
        intervals=tuple(sorted((f"THING.{name}", value) for name, value in intervals.items())),
    )


def test_unknown_policy_returns_the_unbounded_interval_and_names_its_reason() -> None:
    spec = OccurredAtSpec(policy=OccurredAtPolicy.UNKNOWN, derivation="no column places it")
    result = occurred_at(spec, timed(), "THING_HAPPENED")
    assert result.precision is Precision.UNKNOWN
    assert result.provenance is ProvenanceClass.ASSUMED
    assert (result.t_earliest, result.t_latest) == (UNKNOWN_EARLIEST, UNKNOWN_LATEST)
    assert "no column places it" in result.source


def test_from_temporal_binding_returns_the_mapping_interval_unchanged() -> None:
    supplied = interval(4, Precision.MINUTE)
    spec = OccurredAtSpec(
        policy=OccurredAtPolicy.FROM_TEMPORAL_BINDING,
        anchor=AttributeRef(concept="THING", attribute="started"),
        derivation="the column",
    )
    assert occurred_at(spec, timed(started=supplied), "THING_HAPPENED") == supplied


def test_bounded_between_widens_to_both_bounds_and_takes_the_coarser_precision() -> None:
    spec = OccurredAtSpec(
        policy=OccurredAtPolicy.BOUNDED_BETWEEN,
        earliest=AttributeRef(concept="THING", attribute="started"),
        latest=AttributeRef(concept="THING", attribute="finished"),
        derivation="between the two",
    )
    result = occurred_at(
        spec,
        timed(started=interval(1, Precision.MINUTE), finished=interval(5, Precision.DAY)),
        "THING_HAPPENED",
    )
    assert result.t_earliest == datetime(2018, 1, 1, tzinfo=UTC)
    assert result.t_latest.date() == datetime(2018, 1, 5, tzinfo=UTC).date()
    assert result.precision is Precision.DAY, "the coarser bound governs"
    assert result.provenance is ProvenanceClass.INFERRED


def test_bounded_between_falls_back_to_unknown_when_a_bound_is_unknown() -> None:
    """Narrowing an occurrence to "before an instant we do not have" is imputation."""
    unknown = TimeInterval(
        t_earliest=UNKNOWN_EARLIEST,
        t_latest=UNKNOWN_LATEST,
        precision=Precision.UNKNOWN,
        provenance=ProvenanceClass.ASSUMED,
        source="absent",
    )
    spec = OccurredAtSpec(
        policy=OccurredAtPolicy.BOUNDED_BETWEEN,
        earliest=AttributeRef(concept="THING", attribute="started"),
        latest=AttributeRef(concept="THING", attribute="finished"),
        derivation="between the two",
    )
    result = occurred_at(
        spec, timed(started=interval(1, Precision.MINUTE), finished=unknown), "THING_HAPPENED"
    )
    assert result.precision is Precision.UNKNOWN


def test_bounded_between_refuses_a_backwards_window() -> None:
    spec = OccurredAtSpec(
        policy=OccurredAtPolicy.BOUNDED_BETWEEN,
        earliest=AttributeRef(concept="THING", attribute="started"),
        latest=AttributeRef(concept="THING", attribute="finished"),
        derivation="between the two",
    )
    result = occurred_at(
        spec,
        timed(started=interval(9, Precision.DAY), finished=interval(2, Precision.DAY)),
        "THING_HAPPENED",
    )
    assert result.precision is Precision.UNKNOWN


def test_offset_from_advances_by_whole_days_and_keeps_the_anchor_precision() -> None:
    """Adding whole days to a day-granular instant yields a day, never an hour."""
    spec = OccurredAtSpec(
        policy=OccurredAtPolicy.OFFSET_FROM,
        anchor=AttributeRef(concept="THING", attribute="started"),
        plus_days=AttributeRef(concept="THING", attribute="days"),
        derivation="started plus days",
    )
    result = occurred_at(spec, timed(started=interval(4, Precision.DAY)), "THING_HAPPENED")
    assert result.t_earliest == datetime(2018, 1, 7, tzinfo=UTC)
    assert result.precision is Precision.DAY
    assert result.provenance is ProvenanceClass.INFERRED


def test_no_policy_can_produce_exact_precision() -> None:
    """No policy manufactures a point instant.

    `CONVENTIONS.md` §10: a parsed source instant is never exact, and neither is one derived
    from two. The type refuses INFERRED + EXACT, and no policy here even tries.
    """
    for policy, kwargs in (
        (OccurredAtPolicy.UNKNOWN, {}),
        (
            OccurredAtPolicy.FROM_TEMPORAL_BINDING,
            {"anchor": AttributeRef(concept="THING", attribute="started")},
        ),
        (
            OccurredAtPolicy.OFFSET_FROM,
            {
                "anchor": AttributeRef(concept="THING", attribute="started"),
                "plus_days": AttributeRef(concept="THING", attribute="days"),
            },
        ),
    ):
        spec = OccurredAtSpec(policy=policy, derivation="d", **kwargs)
        result = occurred_at(spec, timed(started=interval(4, Precision.DAY)), "THING_HAPPENED")
        assert result.precision is not Precision.EXACT


def test_coarser_returns_the_less_precise_of_two() -> None:
    assert coarser(Precision.MINUTE, Precision.DAY) is Precision.DAY
    assert coarser(Precision.UNKNOWN, Precision.DAY) is Precision.UNKNOWN


def test_a_policy_missing_its_declared_reference_is_refused_at_load() -> None:
    with pytest.raises(ContractViolationError, match="requires"):
        OccurredAtSpec(policy=OccurredAtPolicy.OFFSET_FROM, derivation="d")
    with pytest.raises(ContractViolationError, match="does not read"):
        OccurredAtSpec(
            policy=OccurredAtPolicy.UNKNOWN,
            anchor=AttributeRef(concept="THING", attribute="started"),
            derivation="d",
        )


# --- occurrence identity -------------------------------------------------------------------


def test_the_occurrence_key_ignores_citations_and_nothing_else() -> None:
    """Two records witnessing the same occurrence must group; a different claim must not."""
    when = interval(4, Precision.DAY)
    base = occurrence_key("THING_HAPPENED", ("ent:a", "ent:b"), when, (("q", "1"),))
    assert base == occurrence_key("THING_HAPPENED", ("ent:b", "ent:a"), when, (("q", "1"),))
    assert base != occurrence_key("THING_HAPPENED", ("ent:a",), when, (("q", "1"),))
    assert base != occurrence_key("OTHER", ("ent:a", "ent:b"), when, (("q", "1"),))
    assert base != occurrence_key(
        "THING_HAPPENED", ("ent:a", "ent:b"), interval(5, Precision.DAY), (("q", "1"),)
    )
    assert base != occurrence_key("THING_HAPPENED", ("ent:a", "ent:b"), when, (("q", "2"),))


def test_the_occurrence_key_is_not_an_artifact_identifier() -> None:
    """A grouping address that looked like an `evt:` identifier would be read as one."""
    when = interval(4, Precision.DAY)
    assert ":" not in occurrence_key("THING_HAPPENED", ("ent:a",), when, ())


# --- the missing-event policy ---------------------------------------------------------------


@pytest.fixture(scope="module")
def harness():
    return harness_for()


def test_record_gap_emits_no_event_for_a_step_no_field_supports(harness: Harness) -> None:
    batches = build_batches(rows(), harness, GROUND_TRUTH_DATASET_VERSION)
    envelope = envelope_for(harness, GROUND_TRUTH_DATASET_VERSION)
    extraction = harness.extract(batches, envelope)
    result = harness.generate(batches, extraction, envelope, policy=MissingEventPolicy.RECORD_GAP)
    assert result.report.gap_markers_emitted == 0
    assert not result.of_type("ORDER_RELEASED")
    coverage = result.report.process_coverage[0]
    assert "ORDER_RELEASED" in coverage.unwitnessable_steps


def test_emit_gap_marker_emits_an_unplaced_event_with_zero_support(harness: Harness) -> None:
    batches = build_batches(rows(), harness, GROUND_TRUTH_DATASET_VERSION)
    envelope = envelope_for(harness, GROUND_TRUTH_DATASET_VERSION)
    extraction = harness.extract(batches, envelope)
    result = harness.generate(
        batches, extraction, envelope, policy=MissingEventPolicy.EMIT_GAP_MARKER
    )
    assert result.report.gap_markers_emitted > 0
    marker = result.of_type("ORDER_RELEASED")[0]
    assert marker.occurred_at.precision is Precision.UNKNOWN
    assert marker.confidence.scalar == 0.0
    assert dict(marker.metadata)["emission"] == "GAP_MARKER"
    assert marker.evidence_record_ids, "a marker with no citation would break LAW-EVIDENCE"


def test_a_step_the_anchor_cannot_see_is_reported_unmeasured_not_missing(
    harness: Harness,
) -> None:
    """The worst wrong answer available here, and the test that stops it.

    A step whose event type names no participant of the process's anchor type produces
    events this measurement cannot connect to any instance. Counting those instances as
    lacking the step would state "100% missing" -- a confident, quantified claim -- about a
    step that fired on nearly every one of them. It was doing exactly that before this test
    existed, on a step with 19,222 events behind it.
    """
    batches = build_batches(rows(), harness, GROUND_TRUTH_DATASET_VERSION)
    envelope = envelope_for(harness, GROUND_TRUTH_DATASET_VERSION)
    extraction = harness.extract(batches, envelope)
    result = harness.generate(batches, extraction, envelope)
    coverage = result.report.process_coverage[0]

    unattributable = coverage.unattributable_steps
    assert unattributable, "this pack has such a step, so the case must be exercised"
    for step in coverage.steps:
        if step.attributable:
            continue
        assert result.of_type(step.event_type), (
            f"{step.event_type} was reported unmeasured but produced nothing, so this test "
            "is not exercising the case it names"
        )
        assert step.anchors_expecting == 0
        assert step.anchors_missing == 0
        assert step.miss_rate == 0.0
        assert (
            not step.systematically_missing
        ), "an unmeasured step must never be reported as systematically missing"


def test_the_rendered_report_says_a_step_was_not_measured(harness: Harness) -> None:
    from causalog.extraction.event_generator import render_markdown

    batches = build_batches(rows(), harness, GROUND_TRUTH_DATASET_VERSION)
    envelope = envelope_for(harness, GROUND_TRUTH_DATASET_VERSION)
    extraction = harness.extract(batches, envelope)
    result = harness.generate(batches, extraction, envelope)
    rendered = render_markdown(result.report)
    assert "NOT MEASURED against this anchor" in rendered
    assert (
        "n/a | n/a | n/a" in rendered
    ), "an unmeasured step must render as n/a, never as a rate it did not count"


def test_the_policy_is_stamped_into_the_report(harness: Harness) -> None:
    """It changes what the causal engine can conclude, so a reader must not have to ask."""
    batches = build_batches(rows(), harness, GROUND_TRUTH_DATASET_VERSION)
    envelope = envelope_for(harness, GROUND_TRUTH_DATASET_VERSION)
    extraction = harness.extract(batches, envelope)
    for policy in MissingEventPolicy:
        result = harness.generate(batches, extraction, envelope, policy=policy)
        assert result.report.missing_event_policy == policy.value
