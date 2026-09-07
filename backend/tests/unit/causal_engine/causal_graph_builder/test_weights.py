"""Propagation weights: normalization, the modifier exclusion, and the honest fallback."""

from __future__ import annotations

import pytest

from causalog.causal_engine.causal_graph_builder import (
    ATTRIBUTION_NOT_MEASUREMENT_NOTICE,
    PropagationWeight,
    WeightBasis,
    weights_for_effect,
)
from causalog.core.errors import ContractViolationError
from causalog.core.ontology_view import (
    MagnitudeMeasurementView,
    MeasurementExpressionOperator,
    MeasurementExpressionView,
    MeasurementKindView,
)
from causalog.core.types.causal_edge import AmplifyingCause
from causalog.rule_engine import MagnitudeAttributionSpec
from fixtures.candidates import linear_process
from fixtures.graphs import build_context, candidate, graph_parameters, scored_graph


def _converging_on_one_effect() -> tuple:
    """Return two causes of one shared effect, with their facts."""
    _, first, line_a = linear_process("STAGE_ONE", "STAGE_EFFECT", subject="A")
    _, second, line_b = linear_process("STAGE_TWO", "STAGE_EFFECT", subject="B")
    effect = first[1]
    events = (*first, *second)
    candidates = (candidate(first[0], effect), candidate(second[0], effect))
    graph = scored_graph(candidates, events, (line_a, line_b))
    return events, (line_a, line_b), candidates, graph, effect


def test_weights_over_competing_incoming_edges_sum_to_one() -> None:
    """The declared normalization, checked rather than asserted in prose."""
    events, timelines, candidates, graph, effect = _converging_on_one_effect()
    context = build_context(events, timelines, candidates)
    incoming = tuple(edge for edge in graph.edges if edge.edge.target_event_id == effect.event_id)
    weights = weights_for_effect(incoming, context, context.events_by_id())
    assert len(weights) == 2
    assert sum(item.weight for item in weights.values()) == pytest.approx(1.0)


def test_a_single_cause_takes_the_whole_share() -> None:
    """One incoming edge is a materially different claim from one share among many."""
    _, events, line = linear_process("STAGE_ONE", "STAGE_TWO", subject="A")
    candidates = (candidate(events[0], events[1]),)
    graph = scored_graph(candidates, events, (line,))
    context = build_context(events, (line,), candidates)
    weights = weights_for_effect(graph.edges, context, context.events_by_id())
    only = next(iter(weights.values()))
    assert only.weight == pytest.approx(1.0)
    assert only.competing_edge_count == 1


def test_with_no_declared_magnitude_the_basis_is_a_share_of_belief() -> None:
    """A share of belief and a share of a quantity are never printed under one heading."""
    events, timelines, candidates, graph, effect = _converging_on_one_effect()
    context = build_context(events, timelines, candidates)
    weights = weights_for_effect(
        tuple(e for e in graph.edges if e.edge.target_event_id == effect.event_id),
        context,
        context.events_by_id(),
    )
    for item in weights.values():
        assert item.basis is WeightBasis.CONFIDENCE_SHARE
        assert item.measurement_id is None
        assert item.effect_magnitude is None


def test_a_declared_magnitude_is_evaluated_and_carried() -> None:
    """The quantity comes from the ontology's declared tree, never from a formula here."""
    _, events, line = linear_process("STAGE_ONE", "STAGE_EFFECT", subject="A")
    candidates = (candidate(events[0], events[1]),)
    graph = scored_graph(candidates, events, (line,))
    measurement = MagnitudeMeasurementView(
        id="FIXTURE_MAGNITUDE",
        kind=MeasurementKindView.IMPACT,
        unit="UNITS",
        expression=MeasurementExpressionView(op=MeasurementExpressionOperator.CONSTANT, value=42.0),
    )
    context = build_context(
        events,
        (line,),
        candidates,
        graph_parameters(
            attributions=(
                MagnitudeAttributionSpec(
                    effect_event_type="STAGE_EFFECT",
                    measurement_id="FIXTURE_MAGNITUDE",
                    rationale="fixture attribution",
                ),
            )
        ),
        measurements=(measurement,),
    )
    weights = weights_for_effect(graph.edges, context, context.events_by_id())
    item = next(iter(weights.values()))
    assert item.basis is WeightBasis.MEASURED_MAGNITUDE
    assert item.measurement_id == "FIXTURE_MAGNITUDE"
    assert item.measurement_unit == "UNITS"
    assert item.effect_magnitude == 42.0
    assert item.normalization == "SHARE_OF_INCOMING"


def test_an_attribution_naming_an_undeclared_measurement_falls_back_and_is_visible() -> None:
    """The loader cannot check measurement ids, so the failure surfaces here, per effect."""
    _, events, line = linear_process("STAGE_ONE", "STAGE_EFFECT", subject="A")
    candidates = (candidate(events[0], events[1]),)
    graph = scored_graph(candidates, events, (line,))
    context = build_context(
        events,
        (line,),
        candidates,
        graph_parameters(
            attributions=(
                MagnitudeAttributionSpec(
                    effect_event_type="STAGE_EFFECT",
                    measurement_id="NOT_DECLARED",
                    rationale="fixture attribution naming nothing",
                ),
            )
        ),
    )
    weights = weights_for_effect(graph.edges, context, context.events_by_id())
    assert next(iter(weights.values())).basis is WeightBasis.CONFIDENCE_SHARE


def test_a_modifier_is_excluded_from_the_normalization_basis() -> None:
    """A modifier is not a contributor; giving it a share would take one from the causes."""
    _, first, line_a = linear_process("STAGE_ONE", "STAGE_EFFECT", subject="A")
    _, second, line_b = linear_process("STAGE_TWO", "STAGE_EFFECT", subject="B")
    effect = first[1]
    events = (*first, *second)
    candidates = (
        candidate(first[0], effect),
        candidate(second[0], effect, payload=AmplifyingCause(magnitude_multiplier=2.0)),
    )
    graph = scored_graph(candidates, events, (line_a, line_b))
    context = build_context(events, (line_a, line_b), candidates)
    incoming = tuple(e for e in graph.edges if e.edge.target_event_id == effect.event_id)
    weights = weights_for_effect(incoming, context, context.events_by_id())
    contributing = [w for w in weights.values() if w.basis is not WeightBasis.MODIFIER_MULTIPLIER]
    modifiers = [w for w in weights.values() if w.basis is WeightBasis.MODIFIER_MULTIPLIER]
    assert len(contributing) == 1
    assert len(modifiers) == 1
    assert sum(item.weight for item in contributing) == pytest.approx(1.0)
    assert modifiers[0].competing_edge_count == 0


def test_the_attribution_notice_is_a_property_and_cannot_be_revised_away() -> None:
    """Fixed text in the shape of module 10's calibration notice."""
    weight = PropagationWeight(
        weight=0.5, basis=WeightBasis.CONFIDENCE_SHARE, competing_edge_count=2
    )
    assert weight.notice == ATTRIBUTION_NOT_MEASUREMENT_NOTICE
    assert "NOT A MEASUREMENT" in weight.notice
    assert "notice" not in PropagationWeight.model_fields


def test_a_measured_basis_must_name_its_measurement() -> None:
    """An unnamed quantity cannot be recomputed by anyone who doubts the share."""
    with pytest.raises(ContractViolationError, match="names no measurement"):
        PropagationWeight(weight=0.5, basis=WeightBasis.MEASURED_MAGNITUDE, competing_edge_count=1)


def test_a_belief_share_may_not_cite_a_measurement() -> None:
    """Citing one would present a share of belief as a share of that quantity."""
    with pytest.raises(ContractViolationError, match="would present a share of belief"):
        PropagationWeight(
            weight=0.5,
            basis=WeightBasis.CONFIDENCE_SHARE,
            measurement_id="FIXTURE",
            competing_edge_count=1,
        )
