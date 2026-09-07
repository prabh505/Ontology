"""The three properties `CONVENTIONS.md` §14 makes mandatory for module 13.

A null intervention reproduces the base world; a simulation never writes back to history;
`SIMULATED` provenance survives serialization. This file may NOT assert that any simulated
figure is accurate -- §14 says so explicitly, and there is no ground truth here that could.
"""

from __future__ import annotations

import pytest

from causalog.core.errors import ContractViolationError
from causalog.core.provenance import ProvenanceClass
from causalog.core.serialization import from_canonical_json, to_canonical_json
from causalog.counterfactual_engine import (
    Intervention,
    RemoveEvent,
    SimulatedWorld,
    simulate,
)
from fixtures.candidates import envelope
from fixtures.simulation import joint_cause_shape, linear_shape, simulation_context


def test_a_null_intervention_reproduces_the_base_world_exactly() -> None:
    """No change proposed, so no world is published and nothing is described as simulated.

    `docs/architecture.md` §2 states this as an invariant. It is held by refusing to build
    a world at all rather than by building an identical one: `SimulatedWorld.interventions`
    has `min_length=1`, so there is no such thing as a hypothetical with nothing
    hypothetical about it. An empty world published here would read as "the change was
    simulated and had no effect".
    """
    events, graph = linear_shape()
    result = simulate((), simulation_context(events, graph), envelope())

    assert result.world is None
    assert result.report.not_runnable_because is not None
    assert "no change was proposed" in result.report.not_runnable_because


def test_the_base_world_is_byte_identical_after_a_simulation() -> None:
    """Every occurrence that went in comes out unchanged, through the one serializer.

    LAW-PROVENANCE's headline sentence, asserted over the INPUTS rather than the outputs:
    an assertion about what the simulator produced would pass even if it had scribbled on
    what it was given.
    """
    events, graph, members = joint_cause_shape()
    before = tuple(to_canonical_json(event) for event in events)
    before_graph = to_canonical_json(graph)

    simulate(
        (Intervention.of(RemoveEvent(target_event_id=members[0]), rationale="check"),),
        simulation_context(events, graph),
        envelope(),
    )

    assert tuple(to_canonical_json(event) for event in events) == before
    assert to_canonical_json(graph) == before_graph


def test_simulated_provenance_survives_a_round_trip_through_the_wire() -> None:
    """`SIMULATED` on the world and on every instant, out through JSON and back.

    prd.md §37 requires that observed facts and counterfactual simulations never be
    conflated "in the implementation or the user interface", and the wire is where a
    provenance field most easily goes missing.
    """
    events, graph, members = joint_cause_shape()
    result = simulate(
        (Intervention.of(RemoveEvent(target_event_id=members[0]), rationale="check"),),
        simulation_context(events, graph),
        envelope(),
    )
    assert result.world is not None

    restored = from_canonical_json(SimulatedWorld, to_canonical_json(result.world))
    assert restored.provenance_class is ProvenanceClass.SIMULATED
    assert restored == result.world
    for occurrence in restored.events:
        assert occurrence.provenance_class is ProvenanceClass.SIMULATED
        assert occurrence.occurred_at.provenance_class is ProvenanceClass.SIMULATED


def test_a_world_cannot_be_built_claiming_any_other_provenance() -> None:
    """Editing the class on the way in is refused by the type, not by a caller's care."""
    events, graph, members = joint_cause_shape()
    result = simulate(
        (Intervention.of(RemoveEvent(target_event_id=members[0]), rationale="check"),),
        simulation_context(events, graph),
        envelope(),
    )
    assert result.world is not None

    payload = result.world.model_dump()
    payload["provenance_class"] = ProvenanceClass.INFERRED
    with pytest.raises(ContractViolationError, match="LAW-PROVENANCE"):
        SimulatedWorld.model_validate(payload)


def test_a_simulated_world_holds_no_historical_type() -> None:
    """Structurally, not by inspection: nothing in a world is an `Event` or a `TimeInterval`.

    ADR-0068's guarantee. A consumer holding a value from here cannot mistake it for
    history, because it does not have history's shape -- which is what makes prd.md §37's
    non-conflation hold without anyone having to check a field.
    """
    from causalog.core.temporal import TimeInterval
    from causalog.core.types import Event

    events, graph, members = joint_cause_shape()
    result = simulate(
        (Intervention.of(RemoveEvent(target_event_id=members[0]), rationale="check"),),
        simulation_context(events, graph),
        envelope(),
    )
    assert result.world is not None
    for occurrence in result.world.events:
        assert not isinstance(occurrence, Event)
        assert not isinstance(occurrence.occurred_at, TimeInterval)


# ---------------------------------------------------------------------------------------
# Module 14 against module 13 (ADR-0074).
#
# The correctness requirement is not that module 14 produces a plausible figure; it is that
# it produces module 13's figure. A recommender with its own estimator would agree with the
# simulator on the day both were written and on no day afterwards, and the disagreement
# would surface as an operator acting on a benefit no counterfactual in the system supports.
#
# These tests live HERE rather than under `unit/recommendation_engine/` deliberately: this
# file is where module 13's own consistency properties are asserted, and a cross-module
# agreement asserted inside one of the two modules' own directories reads as that module's
# property rather than as a contract between them.
# ---------------------------------------------------------------------------------------


def test_module_14_reports_the_figure_module_13_produced() -> None:
    """One hypothetical, posed through both modules, yields one number.

    Module 14 is asked for its estimate; module 13 is then asked the same question directly,
    through the intervention module 14 itself builds. The two figures must be equal
    exactly -- not close, since both are quantized at the same resolution
    (`CONVENTIONS.md` §11) and any drift would be a second computation rather than a
    rounding difference.
    """
    from causalog.recommendation_engine import estimate as recommend_estimate
    from causalog.recommendation_engine import intervention_for
    from fixtures.recommendation import recommendation_context, serial_chain_shape

    events, graph, identifiers = serial_chain_shape(magnitude=40.0)
    context = recommendation_context(events, graph)
    target = identifiers[0]

    through_14 = recommend_estimate((target,), context, envelope())
    through_13 = simulate(
        intervention_for((target,), "consistency check"), context.simulation, envelope()
    )

    assert through_13.world is not None
    assert through_14.benefit.absent_because is None
    assert through_14.verdict is through_13.validity.verdict
    assert through_14.composed_belief == through_13.validity.composed_belief
    assert through_14.assumptions == through_13.validity.assumptions

    # The headline figure module 14 publishes is a delta module 13 built, not a recomputation.
    magnitudes = {
        delta.event_id: (delta.base_magnitude, delta.magnitude_difference)
        for delta in through_13.world.diff.deltas
    }
    assert through_14.benefit.headline_event_id in magnitudes
    base, difference = magnitudes[through_14.benefit.headline_event_id]
    assert through_14.benefit.point_of_departure in {base, difference}


def test_a_benefit_range_is_bounded_by_module_13s_own_sweep() -> None:
    """The width of the range is the pack's declared perturbations, not a decoration.

    Asserted against module 13's `SensitivityFinding` outcomes rather than against a
    constant: a range whose bounds nobody can attribute to a declared assumption is a
    decoration, and this is what stops one appearing.
    """
    from causalog.recommendation_engine import estimate as recommend_estimate
    from causalog.recommendation_engine import intervention_for
    from fixtures.recommendation import recommendation_context
    from fixtures.simulation import joint_cause_shape as joint_shape

    events, graph, members = joint_shape(actionable=True, magnitude=90.0)
    context = recommendation_context(events, graph)
    target = members[0]

    through_14 = recommend_estimate((target,), context, envelope())
    through_13 = simulate(
        intervention_for((target,), "sweep check"), context.simulation, envelope()
    )

    outcomes = [
        finding.outcome
        for finding in through_13.validity.sensitivity
        if finding.outcome is not None
    ]
    assert outcomes, "the fixture pack declares perturbations, or this asserts nothing"
    assert through_14.benefit.low == min([*outcomes, through_14.benefit.point_of_departure])
    assert through_14.benefit.high == max([*outcomes, through_14.benefit.point_of_departure])
    assert through_14.benefit.perturbations == tuple(
        sorted(finding.multiplier for finding in through_13.validity.sensitivity)
    )


def test_the_recommender_imports_the_simulator_and_defines_no_second_estimator() -> None:
    """ADR-0074 structurally, over the AST.

    A numeric equality test proves the two agree TODAY. This proves there is only one path
    that could produce the figure at all, which is what keeps them agreeing.
    """
    import ast
    from importlib import import_module
    from pathlib import Path

    import causalog.recommendation_engine as package

    # `import_module` rather than attribute access: the package re-exports the FUNCTION
    # `estimate`, which shadows the module of the same name on the package object.
    estimate_module = import_module("causalog.recommendation_engine.estimate")
    source = Path(estimate_module.__file__ or "").read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "simulate" in imported, "estimate.py must obtain its figures from module 13"

    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "simulate" in called, "estimate.py must CALL module 13, not merely import it"

    # No other file in the package may call the simulator: one estimation path, one place.
    for path in sorted(Path(package.__file__ or "").parent.glob("*.py")):
        if path.name in {"estimate.py", "__init__.py"}:
            continue
        others = {
            node.func.id
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "simulate" not in others, (
            f"{path.name} calls simulate() directly; every benefit figure goes through "
            "estimate.py so that one definition of the headline exists (ADR-0074)"
        )
