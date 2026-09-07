"""Module 13's entry point: validate, propagate, assess, and refuse where required.

THE SEQUENCE IS THE ARGUMENT
-----------------------------
Validation runs over the whole set BEFORE anything propagates (ADR-0066), so a set holding
one inadmissible change never partially executes. Assessment runs after, over what actually
travelled, so an envelope describes the hypothetical that was simulated rather than the one
that was requested.

WHY A DIAGNOSTIC GRAPH IS REFUSED BY DEFAULT (ADR-0072, OQ-026)
----------------------------------------------------------------
`propagation_analyzer/view.py` states it twice -- once in its module docstring, once inside
`DIAGNOSTIC_NOT_STATED_NOTICE` as fixed text: "nothing here is an input to simulation or to
recommendation". OQ-026 requires modules 13 and 14 to refuse one.

On the committed slice the stated graph is EMPTY -- 0 of 9,492 claims promoted, because not
one of the 1,224 occurrences carries an `OBSERVED` timestamp so no temporal verdict is
`CERTAIN` (R-22). A simulator that only walks the stated graph therefore answers the PRD's
own worked example with silence. Silence is a TRUE answer about the inputs and it exercises
none of the machinery.

So: **refused by default; an explicit caller opt-in.** `accept_unpromoted` is a deliberate
act at a named call site, not a configuration value that drifts. Two details make that hold
rather than merely intend it:

* **This module never names `UNPROMOTED_DIAGNOSTIC`.** It compares `is not
  GraphStanding.STATED`. `diagnostic_view` remains the engine's only construction site of
  that member, and the caller -- a script, outside the engine -- decides which adapter to
  call.
* **The notice is imported, never restated.** `propagation_analyzer/graph.py` already sets
  that precedent for `ATTRIBUTION_NOT_MEASUREMENT_NOTICE`, with a note recording that two
  copies of a caveat have drifted once in this repository.

A NULL SET OF CHANGES REPRODUCES THE BASE WORLD EXACTLY
--------------------------------------------------------
`docs/architecture.md` §2 makes this an invariant, and it is enforced by refusing to build a
world at all: `SimulatedWorld.interventions` has `min_length=1`, so there is no such thing
as a hypothetical with nothing hypothetical about it. A caller handing in nothing gets the
statement that nothing was changed, and the base world is returned untouched because it was
never touched.

**No domain vocabulary appears below.**
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from causalog.causal_engine.propagation_analyzer import GraphStanding
from causalog.core.errors import ContractViolationError
from causalog.core.run import OutputEnvelope
from causalog.counterfactual_engine.context import SimulationContext, base_world_address
from causalog.counterfactual_engine.intervention import Intervention
from causalog.counterfactual_engine.propagate import Propagation, propagate
from causalog.counterfactual_engine.report import CounterfactualReport, build_report
from causalog.counterfactual_engine.validate import Admission, admit
from causalog.counterfactual_engine.validity import ValidityAssessment, assess
from causalog.counterfactual_engine.world import SimulatedWorld, WorldDiff

__all__ = ["SimulationResult", "simulate"]


class SimulationResult(BaseModel):
    """One counterfactual query: the world, what was refused, and how far to believe it.

    `world` is `None` whenever no change was admitted. That is deliberate and is not an
    error path: publishing an unchanged world would read as "the change was simulated and
    had no effect", which is a far stronger claim than "the change was never admissible".
    The ledger says which, and the report leads with it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    world: SimulatedWorld | None
    admission: Admission
    validity: ValidityAssessment
    report: CounterfactualReport


def _diff(propagation: Propagation) -> WorldDiff:
    """Return the base-against-simulated diff, with the reason when it is empty."""
    empty_because: str | None = None
    if not propagation.deltas:
        empty_because = (
            "the change reached "
            f"{propagation.reached_count} occurrence(s) and none of them differs. That is a "
            "statement about this graph's shape -- either nothing downstream was reachable, "
            "or everything reachable is held up by causes the change left standing. It is "
            "not a finding that the change does not matter."
        )
    return WorldDiff(
        deltas=propagation.deltas,
        unchanged_count=propagation.unchanged_count,
        reached_count=propagation.reached_count,
        empty_because=empty_because,
    )


def simulate(
    interventions: tuple[Intervention, ...],
    context: SimulationContext,
    envelope: OutputEnvelope,
    *,
    accept_unpromoted: bool = False,
) -> SimulationResult:
    """Simulate a hypothetical over the stated causal graph.

    Args:
        interventions: the proposed changes. An empty set produces no world and says so.
        context: the run's inputs, supplied by value.
        envelope: the run's output envelope, carried onto the report (`CONVENTIONS.md` §11:
            an output without its envelope cannot be verified and is a defect).
        accept_unpromoted: opt in to simulating over a graph the engine does not stand
            behind. **Refused by default** (OQ-026, ADR-0072). Everything produced under it
            is disowned by the artifacts that carry it.

    Returns:
        The world if one was built, the rejection ledger either way, the validity
        assessment, and the report.

    Raises:
        ContractViolationError: if the view's standing is not `STATED` and the caller did
            not opt in. Caught at the boundary so the caller's mistake is named here rather
            than surfacing three layers later as a validation error on a report.
    """
    standing = context.propagation.view.standing
    if standing is not GraphStanding.STATED and not accept_unpromoted:
        raise ContractViolationError(
            f"counterfactual_engine.simulate received a graph whose standing is "
            f"{standing.value}. Nothing in that graph was asserted by the engine, and "
            "propagation_analyzer/view.py states in fixed text that it is not an input to "
            "simulation (OQ-026). Simulating over claims nobody stood behind produces a "
            "figure that looks like every other figure this engine publishes. Pass "
            "accept_unpromoted=True to do it anyway; everything produced will be disowned "
            "by the artifacts that carry it."
        )

    admission = admit(interventions, context)
    propagation = propagate(admission.admitted, context)
    validity = assess(admission.admitted, propagation, context)
    base_graph_id = base_world_address(context.links, context.run_id, standing.value)

    world: SimulatedWorld | None = None
    if admission.admitted:
        world = SimulatedWorld(
            simulated_world_id=SimulatedWorld.address(base_graph_id, admission.admitted),
            run_id=context.run_id,
            standing=standing.value,
            base_graph_id=base_graph_id,
            interventions=tuple(sorted(admission.admitted, key=lambda item: item.sort_key())),
            events=propagation.events,
            diff=_diff(propagation),
        )

    return SimulationResult(
        world=world,
        admission=admission,
        validity=validity,
        report=build_report(
            world=world,
            admission=admission,
            validity=validity,
            propagation=propagation,
            context=context,
            envelope=envelope,
            standing=standing.value,
            base_graph_id=base_graph_id,
        ),
    )
