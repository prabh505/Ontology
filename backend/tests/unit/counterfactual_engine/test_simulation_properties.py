"""Properties that must hold over generated hypotheticals, not over one example.

Two claims are asserted here that no single case can establish: that a thousand simulations
leave the observed store byte-identical, and that a simulated belief is never stronger than
the chain it was composed from.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from causalog.core.serialization import to_canonical_json
from causalog.counterfactual_engine import (
    Intervention,
    RemoveEvent,
    ShiftTiming,
    simulate,
)
from fixtures.candidates import envelope
from fixtures.simulation import (
    derived_precedence_between,
    joint_cause_shape,
    linear_shape,
    simulation_context,
)

pytestmark = pytest.mark.property

SETTINGS = settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)


def test_a_thousand_simulations_leave_the_observed_store_byte_identical() -> None:
    """**The immutability property.** 1000 hypotheticals, one unchanged history.

    Not a Hypothesis test: the requirement is a specific count over a specific shape, and
    expressing it as a generated property would let the example budget decide how many
    simulations actually ran. The changes vary deterministically across the sweep, so the
    thousand runs are a thousand different worlds and not one repeated.

    Asserted over the INPUTS, through the one canonical serializer. An assertion about the
    outputs would pass even if the simulator had scribbled on what it was given, which is
    the single thing this test exists to rule out.
    """
    events, graph, members = joint_cause_shape(magnitude=90.0, members=4)
    context = simulation_context(events, graph)

    before_events = tuple(to_canonical_json(event) for event in events)
    before_graph = to_canonical_json(graph)

    for index in range(1000):
        which = members[index % len(members)]
        if index % 3 == 0:
            change = Intervention.of(RemoveEvent(target_event_id=which), rationale=f"sweep {index}")
        else:
            change = Intervention.of(
                ShiftTiming(target_event_id=which, shift_seconds=-float(60 * (1 + index % 29))),
                rationale=f"sweep {index}",
            )
        simulate((change,), context, envelope())

    assert tuple(to_canonical_json(event) for event in events) == before_events, (
        "an occurrence changed across a thousand hypotheticals; history is not writable "
        "from here (LAW-PROVENANCE, prd.md §33, prd.md §54)"
    )
    assert to_canonical_json(graph) == before_graph, "the base graph changed"


@SETTINGS
@given(
    magnitude=st.floats(min_value=1.0, max_value=1000.0).map(lambda value: round(value, 6)),
    members=st.integers(min_value=2, max_value=6),
    removed=st.integers(min_value=0, max_value=5),
)
def test_a_surviving_consequence_is_never_larger_than_it_was(
    magnitude: float, members: int, removed: int
) -> None:
    """Removing causes can only shrink a consequence, whatever the shape.

    A monotonicity claim over the shares, and a hypothesis rather than a comment: if some
    apportionment ever produced a larger consequence from a removal, the arithmetic would
    be reporting a change as making things worse in a direction the model does not admit.
    """
    events, graph, member_ids = joint_cause_shape(magnitude=magnitude, members=members)
    context = simulation_context(events, graph)
    count = min(removed, members - 1)
    if count == 0:
        return
    result = simulate(
        tuple(
            Intervention.of(RemoveEvent(target_event_id=one), rationale="property")
            for one in member_ids[:count]
        ),
        context,
        envelope(),
    )
    assert result.world is not None
    for delta in result.world.diff.deltas:
        if delta.simulated_magnitude is None or delta.base_magnitude is None:
            continue
        assert (
            delta.simulated_magnitude <= delta.base_magnitude + 1e-6
        ), "removing causes made a consequence larger, which no apportionment admits"
        assert delta.simulated_magnitude >= -1e-6, "a magnitude went negative"


@SETTINGS
@given(members=st.integers(min_value=2, max_value=6))
def test_a_simulated_belief_is_never_stronger_than_its_weakest_link(members: int) -> None:
    """`weakest_link_v1` is a minimum, so the composed belief cannot exceed any link's.

    ADR-0060's rule, one layer down. A simulated outcome can only be weaker than the chain
    that produced it; a composition that ever returned more would be manufacturing
    confidence out of a traversal.
    """
    events, graph, member_ids = joint_cause_shape(members=members)
    context = simulation_context(events, graph)
    result = simulate(
        (Intervention.of(RemoveEvent(target_event_id=member_ids[0]), rationale="property"),),
        context,
        envelope(),
    )
    belief = result.validity.composed_belief
    if belief is None:
        return
    scalars = [edge.edge.confidence.scalar for edge in graph.edges]
    assert belief <= min(scalars) + 1e-9
    assert result.validity.independent_product is not None
    assert result.validity.independent_product <= belief + 1e-9, (
        "the product is reported in its own column and is never blended into the minimum; "
        "over links below 1.0 it is also never larger"
    )


@SETTINGS
@given(seconds=st.integers(min_value=60, max_value=10_000).map(float))
def test_a_move_never_changes_an_interval_width(seconds: float) -> None:
    """Both bounds move together, so the source's own uncertainty is preserved.

    Widening or narrowing the interval would change what the source is claimed to have
    recorded, which a hypothetical about timing has no standing to do.
    """
    events, graph = linear_shape()
    antecedent, consequence = events
    context = simulation_context(
        events, graph, derived_precedence=derived_precedence_between(antecedent, consequence)
    )
    result = simulate(
        (
            Intervention.of(
                ShiftTiming(target_event_id=antecedent.event_id, shift_seconds=-seconds),
                rationale="property",
            ),
        ),
        context,
        envelope(),
    )
    assert result.world is not None
    base_widths = {
        event.event_id: (event.occurred_at.t_latest - event.occurred_at.t_earliest)
        for event in events
    }
    for occurrence in result.world.events:
        width = occurrence.occurred_at.t_latest - occurrence.occurred_at.t_earliest
        assert width == base_widths[occurrence.event_id]


@SETTINGS
@given(seconds=st.integers(min_value=60, max_value=10_000).map(float))
def test_one_change_addresses_one_world(seconds: float) -> None:
    """Two runs handed the same change produce the same world identifier.

    Content addressing, asserted over generated inputs rather than one. A world whose
    identity depended on anything but its base graph and its changes could not be
    reproduced by a rerun.
    """
    events, graph = linear_shape()
    antecedent, _ = events
    context = simulation_context(events, graph)
    change = Intervention.of(
        ShiftTiming(target_event_id=antecedent.event_id, shift_seconds=-seconds),
        rationale="property",
    )
    first = simulate((change,), context, envelope())
    second = simulate((change,), context, envelope())
    assert first.world is not None and second.world is not None
    assert first.world.simulated_world_id == second.world.simulated_world_id
    assert to_canonical_json(first.world) == to_canonical_json(second.world)
