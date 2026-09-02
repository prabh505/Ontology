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
    AGGREGATORS,
    DEFAULT_AGGREGATOR,
    DEFAULT_COMPONENT_WEIGHTS,
    aggregate,
    minimum_v1,
)
from causalog.core.errors import ContractViolationError
from causalog.core.provenance import PROVENANCE_STRENGTH, ProvenanceClass
from causalog.core.types import ConfidenceComponent
from tests.unit.core.strategies import (
    WEIGHTED_COMPONENT_NAMES,
    component_sets,
    quantized_unit_floats,
)

pytestmark = pytest.mark.property


@given(component_sets(), st.sampled_from(sorted(AGGREGATORS)))
def test_every_aggregator_stays_within_the_unit_range(
    components: list[ConfidenceComponent], aggregator_name: str
) -> None:
    """A rollup outside [0, 1] is a latent crash.

    A rollup outside [0, 1] would be rejected by ConfidenceVector, so an aggregator
    that could produce one is a latent crash rather than a wrong number.
    """
    assert 0.0 <= AGGREGATORS[aggregator_name](components) <= 1.0


@given(component_sets(), st.sampled_from(sorted(AGGREGATORS)))
def test_the_rollup_never_exceeds_the_strongest_component(
    components: list[ConfidenceComponent], aggregator_name: str
) -> None:
    """An aggregate stronger than every input would be confidence created by arithmetic."""
    assert AGGREGATORS[aggregator_name](components) <= max(
        component.value for component in components
    )


@given(component_sets(), st.sampled_from(sorted(AGGREGATORS)))
def test_the_rollup_never_falls_below_the_weakest_component(
    components: list[ConfidenceComponent], aggregator_name: str
) -> None:
    """Bounded on both sides: the rollup summarizes its inputs rather than replacing them."""
    assert AGGREGATORS[aggregator_name](components) >= min(
        component.value for component in components
    )


@given(component_sets(), st.sampled_from(sorted(AGGREGATORS)))
def test_the_aggregate_provenance_is_the_weakest_component(
    components: list[ConfidenceComponent], aggregator_name: str
) -> None:
    """The scalar and the provenance are answered separately.

    The rule that keeps the scalar and the provenance from being confused: a high
    number over ASSUMED inputs is still ASSUMED (ADR-0005).
    """
    vector = aggregate(components, aggregator_name)
    assert PROVENANCE_STRENGTH[vector.provenance_class] == min(
        PROVENANCE_STRENGTH[component.provenance_class] for component in components
    )


@given(component_sets(), st.sampled_from(sorted(AGGREGATORS)))
def test_the_vector_names_the_function_that_produced_its_scalar(
    components: list[ConfidenceComponent], aggregator_name: str
) -> None:
    """An unnamed rollup cannot be rechecked, which is the number prd.md §49 forbids."""
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
