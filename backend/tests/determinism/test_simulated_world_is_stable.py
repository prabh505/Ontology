"""Two runs of one hypothetical produce byte-identical bytes, and identical prose.

The input is handed over in two different SEQUENCES rather than merely re-run. A module that
happened to sort its output while reading its input in insertion sequence would pass a naive
rerun test and produce two different artifacts the first time a caller assembled its changes
differently -- which is the failure `test_root_cause_is_stable.py` states and this one
inherits.
"""

from __future__ import annotations

import pytest

from causalog.core.serialization import to_canonical_json
from causalog.counterfactual_engine import (
    Intervention,
    RemoveEvent,
    ShiftTiming,
    SimulationResult,
    render_markdown,
    simulate,
)
from fixtures.candidates import envelope
from fixtures.simulation import (
    derived_precedence_between,
    joint_cause_shape,
    simulation_context,
)

pytestmark = pytest.mark.determinism


def _run(reverse: bool) -> SimulationResult:
    """Build one fixed hypothetical, optionally handing the changes over in reverse."""
    events, graph, members = joint_cause_shape(magnitude=90.0, members=4)
    antecedent = events[0]
    consequence = events[-1]
    context = simulation_context(
        events,
        graph,
        derived_precedence=derived_precedence_between(antecedent, consequence),
    )
    changes = (
        Intervention.of(RemoveEvent(target_event_id=members[0]), rationale="first"),
        Intervention.of(
            ShiftTiming(target_event_id=members[1], shift_seconds=-1800.0),
            rationale="second",
        ),
    )
    return simulate(tuple(reversed(changes)) if reverse else changes, context, envelope())


def test_two_runs_of_one_hypothetical_are_byte_identical() -> None:
    """The artifact itself, through the one canonical serializer."""
    first = _run(reverse=False)
    second = _run(reverse=True)
    assert to_canonical_json(first.world) == to_canonical_json(second.world)
    assert to_canonical_json(first.report) == to_canonical_json(second.report)


def test_the_world_identifier_does_not_depend_on_the_input_sequence() -> None:
    """Content addressing: one base graph and one set of changes address one world."""
    first = _run(reverse=False).world
    second = _run(reverse=True).world
    assert first is not None and second is not None
    assert first.simulated_world_id == second.simulated_world_id


def test_the_rendered_markdown_is_byte_identical() -> None:
    """Prose is an artifact too.

    A report that resequenced its own tables between runs would make every committed report
    a spurious diff, and would hide a real one inside the noise.
    """
    assert render_markdown(_run(reverse=False).report) == render_markdown(_run(reverse=True).report)


def test_the_run_actually_produced_something() -> None:
    """Two empty artifacts are trivially identical, so emptiness is refused here."""
    result = _run(reverse=False)
    assert result.world is not None
    assert result.world.diff.deltas, "the hypothetical changed nothing; nothing was compared"
    assert result.report.interventions_admitted == 2
