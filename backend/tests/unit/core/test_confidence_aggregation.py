"""Confidence aggregation is explainable, bounded, and never over-claims (ADR-0009).

LAW-EVIDENCE says a bare float is a defect. These tests assert the two things that make the
rollup safe to display beside the decomposition it summarizes: it stays inside the range
everyone assumes, and it never reports stronger provenance than its weakest input.

No test here asserts that a particular score is *correct*. There is no causal ground truth
in this dataset (`CONVENTIONS.md` §14), so the properties are structural.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from causalog.core.aggregation import (
    AGGREGATOR_COMPONENT_NAMES,
    AGGREGATORS,
    CONTRADICTION_CEILING_ANCHORS,
    DEFAULT_AGGREGATOR,
    DEFAULT_COMPONENT_WEIGHTS,
    TEMPORAL_CEILING_ANCHORS,
    V2_COMPONENT_NAMES,
    aggregate,
    ceiling_at,
    gated_weighted_mean_v1,
    minimum_v1,
)
from causalog.core.errors import ContractViolationError
from causalog.core.provenance import PROVENANCE_STRENGTH, ProvenanceClass
from causalog.core.types import ConfidenceComponent
from tests.unit.core.strategies import (
    GATED_COMPONENT_NAMES,
    WEIGHTED_COMPONENT_NAMES,
    aggregator_and_components,
    component_sets,
    gated_component_sets,
    quantized_unit_floats,
)

pytestmark = pytest.mark.property


@given(aggregator_and_components())
def test_every_aggregator_stays_within_the_unit_range(
    drawn: tuple[str, list[ConfidenceComponent]],
) -> None:
    """A rollup outside [0, 1] is a latent crash.

    A rollup outside [0, 1] would be rejected by ConfidenceVector, so an aggregator
    that could produce one is a latent crash rather than a wrong number.
    """
    aggregator_name, components = drawn
    assert 0.0 <= AGGREGATORS[aggregator_name](components) <= 1.0


@given(aggregator_and_components())
def test_the_rollup_never_exceeds_the_strongest_component(
    drawn: tuple[str, list[ConfidenceComponent]],
) -> None:
    """An aggregate stronger than every input would be confidence created by arithmetic.

    This is the property that kept noisy-OR out of the registry: two independent
    components at 0.5 roll up to 0.75 under it, which is support the inputs do not
    contain (ADR-0052).
    """
    aggregator_name, components = drawn
    assert AGGREGATORS[aggregator_name](components) <= max(
        component.value for component in components
    )


@given(aggregator_and_components())
def test_the_rollup_never_falls_below_the_weakest_component(
    drawn: tuple[str, list[ConfidenceComponent]],
) -> None:
    """Bounded on both sides: the rollup summarizes its inputs rather than replacing them.

    This is what forces every gate ceiling to sit at or above its own input: a gate that
    capped below the component driving it would push the rollup under its weakest input.
    """
    aggregator_name, components = drawn
    assert AGGREGATORS[aggregator_name](components) >= min(
        component.value for component in components
    )


@given(aggregator_and_components())
def test_the_aggregate_provenance_is_the_weakest_component(
    drawn: tuple[str, list[ConfidenceComponent]],
) -> None:
    """The scalar and the provenance are answered separately.

    The rule that keeps the scalar and the provenance from being confused: a high
    number over ASSUMED inputs is still ASSUMED (ADR-0005).
    """
    aggregator_name, components = drawn
    vector = aggregate(components, aggregator_name)
    assert PROVENANCE_STRENGTH[vector.provenance_class] == min(
        PROVENANCE_STRENGTH[component.provenance_class] for component in components
    )


@given(aggregator_and_components())
def test_the_vector_names_the_function_that_produced_its_scalar(
    drawn: tuple[str, list[ConfidenceComponent]],
) -> None:
    """An unnamed rollup cannot be rechecked, which is the number prd.md §49 forbids."""
    aggregator_name, components = drawn
    vector = aggregate(components, aggregator_name)
    assert vector.aggregation == aggregator_name
    assert AGGREGATORS[vector.aggregation](vector.components) == vector.scalar


@given(component_sets())
def test_aggregation_is_independent_of_the_input_sequence(
    components: list[ConfidenceComponent],
) -> None:
    """Input sequence must not change the answer.

    Components arrive in whatever sequence the scorer produced them; determinism
    requires the answer not to depend on it (`CONVENTIONS.md` §11).
    """
    forward = aggregate(components)
    backward = aggregate(list(reversed(components)))
    assert forward == backward


@given(component_sets())
def test_the_vector_sequences_its_components_by_name(
    components: list[ConfidenceComponent],
) -> None:
    """An unsequenced vector serializes two ways and breaks byte-identity."""
    names = [component.component_name for component in aggregate(components).components]
    assert names == sorted(names)


@given(component_sets())
def test_the_conservative_aggregator_reports_the_weakest_support(
    components: list[ConfidenceComponent],
) -> None:
    """`minimum_v1` is the documented under-claiming option; this pins its meaning."""
    assert minimum_v1(components) == min(component.value for component in components)


@given(st.sampled_from(WEIGHTED_COMPONENT_NAMES), quantized_unit_floats())
def test_a_single_component_rolls_up_to_its_own_value(component_name: str, value: float) -> None:
    """With one component the weights renormalize to 1, so the rollup is the value itself.

    This is the property that makes "an absent component abstains" true rather than
    aspirational: were absent components treated as zero, one strong component would
    still score near the floor.
    """
    component = ConfidenceComponent(
        component_name=component_name,
        value=value,
        provenance_class=ProvenanceClass.OBSERVED,
        evidence_record_ids=("evd:1",),
    )
    assert aggregate([component]).scalar == value


def test_an_unknown_aggregator_is_never_silently_replaced() -> None:
    """Falling back to the default would produce a vector misdescribing its own scalar."""
    component = ConfidenceComponent(
        component_name="rule_support",
        value=0.5,
        provenance_class=ProvenanceClass.OBSERVED,
        evidence_record_ids=("evd:1",),
    )
    with pytest.raises(ContractViolationError):
        aggregate([component], "no_such_aggregator_v1")


def test_an_empty_component_set_is_refused() -> None:
    """An empty vector is a defect, not zero confidence (LAW-EVIDENCE)."""
    with pytest.raises(ContractViolationError):
        aggregate([])


def test_an_unweighted_component_name_is_refused_rather_than_guessed() -> None:
    """An unrecognised component name is refused, never weighted by guess.

    Component names are part of `confidence_schema_version`; guessing a weight would
    let a schema change pass silently and shift every score.
    """
    component = ConfidenceComponent(
        component_name="a_name_no_version_declares",
        value=0.5,
        provenance_class=ProvenanceClass.OBSERVED,
        evidence_record_ids=("evd:1",),
    )
    with pytest.raises(ContractViolationError):
        aggregate([component], "weighted_mean_v1")


def test_the_declared_weights_cover_the_documented_component_names() -> None:
    """Every documented component name has a declared weight.

    prd.md §49 names the components; a missing weight is an aggregator that cannot
    score a vector the pipeline is entitled to build.
    """
    assert set(DEFAULT_COMPONENT_WEIGHTS) == set(WEIGHTED_COMPONENT_NAMES)
    assert DEFAULT_AGGREGATOR in AGGREGATORS


# ---------------------------------------------------------------------------------------
# confidence_schema_version 2.0.0 -- the gated strategy (ADR-0052)
# ---------------------------------------------------------------------------------------


def _gated(**values: float) -> list[ConfidenceComponent]:
    """Return a full eight-name component set, defaulting every unnamed one to zero."""
    return [
        ConfidenceComponent(
            component_name=name,
            value=values.get(name, 0.0),
            provenance_class=ProvenanceClass.ASSUMED,
            evidence_record_ids=("evd:1",),
        )
        for name in GATED_COMPONENT_NAMES
    ]


def test_weighted_mean_v1_is_unchanged_by_the_second_schema_version() -> None:
    """A vector naming `weighted_mean_v1` must recompute to the same scalar forever.

    The whole value of recording the function name is that a stored scalar can be
    rechecked. Revising what a shipped name computes would silently reinterpret every
    artifact already written under it, so 2.0.0 arrives as a new function beside the old
    one and this test pins that the old one did not move.
    """
    components = [
        ConfidenceComponent(
            component_name=name,
            value=value,
            provenance_class=ProvenanceClass.OBSERVED,
            evidence_record_ids=("evd:1",),
        )
        for name, value in (
            ("rule_support", 0.8),
            ("temporal_support", 0.4),
            ("historical_support", 0.6),
        )
    ]
    # (0.25*0.8 + 0.20*0.4 + 0.15*0.6) / (0.25 + 0.20 + 0.15) == 0.37 / 0.60
    assert aggregate(components, "weighted_mean_v1").scalar == 0.616667
    assert set(DEFAULT_COMPONENT_WEIGHTS) == set(WEIGHTED_COMPONENT_NAMES)


def test_the_temporal_gate_caps_an_otherwise_perfect_edge() -> None:
    """Unestablished ordering is a ceiling, not a subtraction.

    Every addend at 1.0 and no contradiction, but temporal support at zero: the six
    addends mean 1.0 and the temporal ceiling is 0.25, so the scalar is 0.25. No
    quantity of rule, historical or statistical support may lift an edge whose ordering
    rests on nothing (prd.md §23).
    """
    components = _gated(
        rule_support=1.0,
        historical_support=1.0,
        statistical_support=1.0,
        evidence_diversity=1.0,
        evidence_count=1.0,
        graph_connectivity=1.0,
        contradiction_freedom=1.0,
        temporal_support=0.0,
    )
    assert gated_weighted_mean_v1(components) == 0.25


def test_the_contradiction_gate_caps_an_otherwise_perfect_edge() -> None:
    """Counter-evidence is a ceiling too, and a harder one than absent time.

    A positive finding against the claim caps at 0.10; merely unverifiable time caps at
    0.25. The two are different findings and they cap differently.
    """
    components = _gated(
        rule_support=1.0,
        historical_support=1.0,
        statistical_support=1.0,
        evidence_diversity=1.0,
        evidence_count=1.0,
        graph_connectivity=1.0,
        temporal_support=1.0,
        contradiction_freedom=0.0,
    )
    assert gated_weighted_mean_v1(components) == 0.10


def test_the_binding_gate_is_the_lower_of_the_two() -> None:
    """Two ceilings compose by `min`, never by averaging or by precedence."""
    components = _gated(
        rule_support=1.0,
        historical_support=1.0,
        statistical_support=1.0,
        evidence_diversity=1.0,
        evidence_count=1.0,
        graph_connectivity=1.0,
        temporal_support=0.30,  # ceiling 0.55
        contradiction_freedom=0.50,  # ceiling 0.60
    )
    assert gated_weighted_mean_v1(components) == 0.55


def test_ungated_the_strategy_is_the_declared_weighted_mean() -> None:
    """With both gates open the scalar is the plain weighted mean of the six addends.

    0.28*1.0 + 0.17*0.5 + 0.17*0.0 + 0.16*0.5 + 0.12*0.0 + 0.10*0.0 == 0.445, over a
    weight total of 1.0. The temporal ceiling at 1.0 is 1.0 and does not bind.
    """
    components = _gated(
        rule_support=1.0,
        historical_support=0.5,
        evidence_diversity=0.5,
        temporal_support=1.0,
        contradiction_freedom=1.0,
    )
    assert gated_weighted_mean_v1(components) == 0.445


@given(gated_component_sets(), st.sampled_from(GATED_COMPONENT_NAMES), quantized_unit_floats())
def test_raising_any_single_component_never_lowers_the_scalar(
    components: list[ConfidenceComponent], component_name: str, raised_to: float
) -> None:
    """Monotonicity in every component, gates included.

    More support must never produce less confidence. The proof: a weighted mean is
    non-decreasing in each addend, each ceiling is non-decreasing in its gate because the
    anchors ascend in both coordinates, and the minimum of non-decreasing functions is
    non-decreasing (ADR-0052). This is the property that makes the whole vector safe to
    hand a user who wants to know what would raise the number.
    """
    before = gated_weighted_mean_v1(components)
    raised = [
        component.model_copy(update={"value": max(component.value, raised_to)})
        if component.component_name == component_name
        else component
        for component in components
    ]
    assert gated_weighted_mean_v1(raised) >= before


@given(gated_component_sets())
def test_the_scalar_never_exceeds_either_ceiling(
    components: list[ConfidenceComponent],
) -> None:
    """The gate is a hard cap, not a strong hint."""
    values = {component.component_name: component.value for component in components}
    assert gated_weighted_mean_v1(components) <= ceiling_at(
        values["temporal_support"], TEMPORAL_CEILING_ANCHORS
    )
    assert gated_weighted_mean_v1(components) <= ceiling_at(
        values["contradiction_freedom"], CONTRADICTION_CEILING_ANCHORS
    )


@given(quantized_unit_floats(), quantized_unit_floats())
def test_every_ceiling_sits_at_or_above_its_own_input(lower: float, upper: float) -> None:
    """Non-decreasing, and never below the gate value driving it.

    The first keeps the strategy monotone. The second keeps the rollup from falling below
    its weakest component, which every registered aggregator is required to respect.
    """
    low, high = min(lower, upper), max(lower, upper)
    for anchors in (TEMPORAL_CEILING_ANCHORS, CONTRADICTION_CEILING_ANCHORS):
        assert ceiling_at(low, anchors) <= ceiling_at(high, anchors)
        assert ceiling_at(low, anchors) >= low


def test_a_missing_component_is_refused_rather_than_allowed_to_abstain() -> None:
    """The gated strategy does not let an absent component abstain.

    `weighted_mean_v1` renormalizes over what it is given, which is right for it. Here it
    would be wrong: the scorer never omits a component -- a component whose data is
    absent is emitted at zero and reported as missing -- so an absent name means the
    vector was assembled somewhere else, and the two meanings score differently.
    """
    incomplete = [
        component
        for component in _gated(rule_support=1.0)
        if component.component_name != "graph_connectivity"
    ]
    with pytest.raises(ContractViolationError):
        gated_weighted_mean_v1(incomplete)


def test_every_registered_aggregator_declares_what_it_accepts() -> None:
    """A registry whose entries disagree about their inputs must say so in data.

    Without this declaration a caller learns an aggregator's requirements by being
    refused, and a test learns them by passing for the wrong reason.
    """
    assert set(AGGREGATOR_COMPONENT_NAMES) == set(AGGREGATORS)
    assert AGGREGATOR_COMPONENT_NAMES["minimum_v1"] is None
    assert AGGREGATOR_COMPONENT_NAMES["gated_weighted_mean_v1"] == V2_COMPONENT_NAMES
