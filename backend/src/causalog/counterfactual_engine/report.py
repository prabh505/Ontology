"""The Counterfactual Report: what was simulated, and what nobody should take from it.

The habit every report in this engine keeps: **the first section is what the report does not
contain, and the last is what the run did not check.** A report listing only what it looked
at reads as a report that looked at everything, and this repository has twice mistaken a
check that could not run for one that passed (DEF-0001, OQ-014).

Two things this report does that the others do not, because the artifact is more dangerous
than theirs:

* **The extrapolation verdict is printed INSTEAD of the figure, not beside it.** A number a
  reader can quote without its warning is a number that will be quoted without its warning.
  Where the validity assessment says a hypothetical has left the data behind, the magnitude
  column holds the verdict and the figure is in the JSON alone, where a person has to go
  looking for it.
* **Every sentence about a consequence is in the past conditional.** prd.md §33's engine
  answers a question about a world that did not happen. A report that says "would reduce"
  in the present tense is describing a forecast, and prd.md §62 rules that this system
  produces none.

**No domain vocabulary appears below.** Nothing here reads a type name.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from causalog.causal_engine.causal_graph_builder.graph import (
    ATTRIBUTION_NOT_MEASUREMENT_NOTICE,
)
from causalog.causal_engine.propagation_analyzer import (
    DIAGNOSTIC_NOT_STATED_NOTICE,
    GraphStanding,
    TruncationRecord,
)
from causalog.core.perturbation import SIMULATION_IS_NOT_A_PREDICTION_NOTICE
from causalog.core.provenance import ProvenanceClass
from causalog.core.run import OutputEnvelope
from causalog.counterfactual_engine.context import SimulationContext
from causalog.counterfactual_engine.intervention import RejectedIntervention
from causalog.counterfactual_engine.propagate import CONDITION_TEST_NOTICE, Propagation
from causalog.counterfactual_engine.validate import Admission
from causalog.counterfactual_engine.validity import (
    NOT_CALIBRATED_NOTICE,
    ValidityAssessment,
    ValidityVerdict,
)
from causalog.counterfactual_engine.world import SimulatedWorld

__all__ = [
    "COUNTERFACTUAL_REPORT_SCHEMA_VERSION",
    "CounterfactualReport",
    "PolicyGap",
    "build_report",
    "render_markdown",
]

COUNTERFACTUAL_REPORT_SCHEMA_VERSION: Final[str] = "1.0.0"

#: The markdown prints at most this many deltas. The JSON carries every one; the markdown is
#: for a person, and a table nobody scrolls to the end of is one nobody reads.
RENDERED_DELTAS: Final[int] = 40


class PolicyGap(BaseModel):
    """One policy that could not run, and the declaration it would have needed.

    ADR-0049's absent-means-CANNOT-RUN rule, made visible. A gap is never a default that
    quietly took effect.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy: str = Field(min_length=1)
    requirement: str = Field(min_length=1)
    consequence: str = Field(min_length=1)

    def sort_key(self) -> str:
        """Return the canonical sequence key (`CONVENTIONS.md` §11)."""
        return self.policy


class CounterfactualReport(BaseModel):
    """One counterfactual query, rendered for a reader and for a machine.

    `standing` is required and has no default: an artifact cannot be built without stating
    which graph it came from (ADR-0059's rule, applied here).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    report_schema_version: str = COUNTERFACTUAL_REPORT_SCHEMA_VERSION
    envelope: OutputEnvelope
    standing: str
    base_graph_id: str
    simulated_world_id: str | None = None
    provenance_class: ProvenanceClass = ProvenanceClass.SIMULATED
    interventions_proposed: int = Field(default=0, ge=0)
    interventions_admitted: int = Field(default=0, ge=0)
    rejections: tuple[RejectedIntervention, ...] = ()
    world: SimulatedWorld | None = None
    validity: ValidityAssessment
    truncations: tuple[TruncationRecord, ...] = ()
    policy_gaps: tuple[PolicyGap, ...] = ()
    #: Why nothing was simulated, when nothing was. Never left implicit.
    not_runnable_because: str | None = None

    @property
    def notice(self) -> str:
        """Return the fixed statement of what a simulated figure is and is not."""
        return SIMULATION_IS_NOT_A_PREDICTION_NOTICE

    @property
    def disowned_notice(self) -> str | None:
        """Return the disowning notice when this walked a graph nobody stood behind.

        Imported from module 12 rather than restated: two copies of a caveat have already
        drifted once in this repository, and `propagation_analyzer/graph.py` sets the
        precedent of importing the constant instead.
        """
        if self.standing == GraphStanding.STATED.value:
            return None
        return DIAGNOSTIC_NOT_STATED_NOTICE


def _policy_gaps(context: SimulationContext) -> tuple[PolicyGap, ...]:
    """Return one gap per absent declaration in the pack's simulation block."""
    parameters = context.parameters
    gaps: list[PolicyGap] = []
    if parameters.maximum_simulation_depth is None:
        gaps.append(
            PolicyGap(
                policy="propagation depth",
                requirement="counterfactual_simulation.maximum_simulation_depth",
                consequence=(
                    "no change was propagated at all. The bound is not defaulted: a "
                    "simulator that chose its own reach would make prd.md §55's five-second "
                    "budget an engine decision rather than a declared one."
                ),
            )
        )
    if parameters.affected_subgraph_node_cap is None:
        gaps.append(
            PolicyGap(
                policy="affected subgraph cap",
                requirement="counterfactual_simulation.affected_subgraph_node_cap",
                consequence=(
                    "no change was propagated at all. An unbounded sweep over a dense graph "
                    "does not meet the stated budget."
                ),
            )
        )
    if parameters.support_envelope_tolerance is None:
        gaps.append(
            PolicyGap(
                policy="support envelope",
                requirement="counterfactual_simulation.support_envelope_tolerance",
                consequence=(
                    "every value outside the witnessed range is reported as EXTRAPOLATION "
                    "with no allowance around the edge. That is the conservative reading "
                    "and it is not a default standing in for a declaration."
                ),
            )
        )
    if not parameters.sensitivity_perturbations:
        gaps.append(
            PolicyGap(
                policy="sensitivity sweep",
                requirement="counterfactual_simulation.sensitivity_perturbations",
                consequence=(
                    "no assumption was perturbed, so the report cannot say whether the "
                    "answer survives a change in the inputs it rests on. Absent, not stable."
                ),
            )
        )
    if not context.mutability:
        gaps.append(
            PolicyGap(
                policy="attribute changeability",
                requirement="'mutable: true' on an attribute in the ontology pack",
                consequence=(
                    "no attribute change is admissible on any kind of occurrence. An absent "
                    "declaration refuses rather than permits (ADR-0067)."
                ),
            )
        )
    if context.derived_precedence is None:
        gaps.append(
            PolicyGap(
                policy="downstream re-timing",
                requirement="a DerivedPrecedenceIndex supplied by the caller",
                consequence=(
                    "no consequence's instant moved. The graph declares no transfer function "
                    "for time, so without module 1's measurement of which instants the "
                    "source COMPUTED from which, moving one would be manufactured precision "
                    "(R-20)."
                ),
            )
        )
    return tuple(sorted(gaps, key=lambda gap: gap.sort_key()))


def build_report(
    *,
    world: SimulatedWorld | None,
    admission: Admission,
    validity: ValidityAssessment,
    propagation: Propagation,
    context: SimulationContext,
    envelope: OutputEnvelope,
    standing: str,
    base_graph_id: str,
) -> CounterfactualReport:
    """Return the report for one counterfactual query."""
    gaps = _policy_gaps(context)
    not_runnable: str | None = None
    if world is None:
        if not admission.admitted and admission.rejected:
            not_runnable = (
                f"all {len(admission.rejected)} proposed change(s) were refused before "
                "anything was simulated. The ledger below names what each was checked "
                "against. No world is published: an unchanged world would read as 'the "
                "change was simulated and had no effect', which is a much stronger claim "
                "than 'the change was never admissible'."
            )
        elif not admission.admitted:
            not_runnable = (
                "no change was proposed, so there is no hypothetical. A null set of changes "
                "reproduces the base world exactly, and the base world is returned untouched "
                "because it was never touched."
            )
    return CounterfactualReport(
        envelope=envelope,
        standing=standing,
        base_graph_id=base_graph_id,
        simulated_world_id=None if world is None else world.simulated_world_id,
        interventions_proposed=len(admission.admitted) + len(admission.rejected),
        interventions_admitted=len(admission.admitted),
        rejections=admission.rejected,
        world=world,
        validity=validity,
        truncations=propagation.truncations,
        policy_gaps=gaps,
        not_runnable_because=not_runnable,
    )


def _magnitude_cell(simulated: float | None, verdict: ValidityVerdict, unit: str | None) -> str:
    """Return the magnitude cell, or the verdict standing in place of it.

    The verdict replaces the figure rather than sitting beside it. A reader who can copy the
    number out of the row will copy the number out of the row.
    """
    if verdict in (ValidityVerdict.EXTRAPOLATION, ValidityVerdict.NOT_ASSESSABLE):
        return f"**{verdict.value}**"
    if simulated is None:
        return "not measurable"
    return f"{simulated}{'' if unit is None else ' ' + unit}"


def render_markdown(report: CounterfactualReport) -> str:
    """Return the report rendered for a person, section by section.

    The JSON carries everything; this is capped and sequenced for reading. Both are
    rendered from one object, so they cannot drift.
    """
    lines: list[str] = ["# Counterfactual Report", ""]
    lines.append(f"- standing: `{report.standing}`")
    disowned = report.disowned_notice
    if disowned is not None:
        lines.extend(["", f"> {disowned}", ""])
    lines.append(f"> {report.notice}")
    lines.append("")
    lines.append(f"- `report_schema_version`: `{report.report_schema_version}`")
    lines.append(f"- `run_id`: `{report.envelope.run_id}`")
    lines.append(f"- base world: `{report.base_graph_id}`")
    lines.append(f"- simulated world: `{report.simulated_world_id or 'none published'}`")
    lines.append(
        f"- changes proposed: {report.interventions_proposed}; "
        f"admitted: {report.interventions_admitted}"
    )
    lines.append("")

    lines.append("## What this report does not contain")
    lines.append("")
    lines.append(f"> {NOT_CALIBRATED_NOTICE}")
    lines.append("")
    lines.append(
        "It contains no prediction. Every statement below is about a world that did NOT "
        "happen, phrased in the past conditional, and none of it forecasts anything."
    )
    lines.append("")
    lines.append(
        "It contains no causal effect estimate. The links this change travelled were "
        "derived from rules, temporal structure and frequency rather than identified as "
        "causal effects (prd.md §16, OQ-007)."
    )
    lines.append("")
    if report.policy_gaps:
        lines.append("Policies that could not run:")
        lines.append("")
        lines.append("| policy | would have needed | consequence |")
        lines.append("|---|---|---|")
        for gap in report.policy_gaps:
            lines.append(f"| {gap.policy} | `{gap.requirement}` | {gap.consequence} |")
        lines.append("")
    else:
        lines.append("Every declared policy ran.")
        lines.append("")

    if report.not_runnable_because is not None:
        lines.append("## Nothing was simulated")
        lines.append("")
        lines.append(report.not_runnable_because)
        lines.append("")

    lines.append("## What was refused, and against what")
    lines.append("")
    if not report.rejections:
        lines.append("No proposed change was refused.")
        lines.append("")
    else:
        lines.append("| kind | reason | checked against | detail |")
        lines.append("|---|---|---|---|")
        for rejection in report.rejections:
            lines.append(
                f"| `{rejection.kind.value}` | `{rejection.reason.value}` | "
                f"{rejection.checked_against} | {rejection.detail} |"
            )
        lines.append("")

    lines.append("## Validity")
    lines.append("")
    lines.append(f"**Verdict: `{report.validity.verdict.value}`**")
    lines.append("")
    if report.validity.verdict is ValidityVerdict.EXTRAPOLATION:
        lines.append(
            "> This hypothetical is NOT reported as a figure. It asks the graph about a "
            "region beyond the range this run witnessed, so a magnitude here would be an "
            "extrapolation wearing a measurement's shape."
        )
        lines.append("")
    elif report.validity.verdict is ValidityVerdict.NOT_ASSESSABLE:
        # A DIFFERENT statement from the one above, and the difference is the point.
        # `EXTRAPOLATION` says the change leaves the data behind; this says the data never
        # spoke to the question. Printing the first message for the second case would
        # report an absence of measurement as a measurement of distance.
        lines.append(
            "> Support could NOT BE JUDGED for this hypothetical, which is a different "
            "finding from its leaving the data behind. Nothing comparable was witnessed, so "
            "there is no range to place the change against — an absence of measurement, not "
            "a measurement of nothing. A figure is withheld for that reason and not because "
            "the change was found unsupported."
        )
        lines.append("")
    if report.validity.envelopes:
        lines.append("| quantity | witnessed | over | asked for | beyond | verdict |")
        lines.append("|---|---|---|---|---|---|")
        for held in report.validity.envelopes:
            witnessed = (
                f"{held.witnessed_low} to {held.witnessed_high}"
                if held.witnessed_low is not None
                else "nothing comparable"
            )
            lines.append(
                f"| {held.quantity} | {witnessed} | {held.witnessed_count} | "
                f"{held.requested_value} | {held.distance_beyond} | "
                f"`{held.verdict.value}` |"
            )
        lines.append("")
    else:
        lines.append(
            "No quantity was moved that a support envelope could be measured for. This is "
            "an absence of measurement, not a finding that the change is supported."
        )
        lines.append("")

    lines.append("### Belief along the chain")
    lines.append("")
    if report.validity.composed_belief is None:
        lines.append(report.validity.belief_absent_because or "No belief was composed.")
    else:
        lines.append(
            f"- composed under `{report.validity.composition}`: "
            f"{report.validity.composed_belief}"
        )
        lines.append(
            f"- independent product, reported separately and never blended: "
            f"{report.validity.independent_product}"
        )
        lines.append(f"- links composed over: {report.validity.path_length}")
        lines.append("")
        lines.append(
            "A simulated outcome can only be weaker than the chain that produced it. The "
            "two compositions sit in separate columns because blending them would produce "
            "a number nobody could write down the meaning of (ADR-0060)."
        )
    lines.append("")

    lines.append("### Sensitivity")
    lines.append("")
    if not report.validity.sensitivity:
        lines.append(
            "No perturbation was declared, so no assumption was tested. **Absent, not " "stable.**"
        )
    else:
        lines.append("| assumption | multiplier | outcome | stable? |")
        lines.append("|---|---|---|---|")
        for finding in report.validity.sensitivity:
            # An outcome of `None` means there was no figure to perturb. Rendering that row
            # as "stable: yes" would report a sweep that never ran as a sweep that found the
            # answer robust, which is the absence-read-as-a-finding error this report's
            # closing section exists to prevent.
            if finding.outcome is None:
                stability = "**not runnable** — nothing was perturbed"
            elif finding.unstable:
                stability = "NO -- the answer inverts"
            else:
                stability = "yes"
            lines.append(
                f"| {finding.assumption} | {finding.multiplier} | "
                f"{'none' if finding.outcome is None else finding.outcome} | {stability} |"
            )
    lines.append("")

    lines.append("### Assumptions this answer rests on")
    lines.append("")
    for assumption in report.validity.assumptions:
        lines.append(f"**{assumption.name}** -- {assumption.statement}")
        lines.append("")
        lines.append(f"- why it is needed: {assumption.why_needed}")
        lines.append(f"- falsified by: {assumption.falsified_by}")
        lines.append("")

    lines.append("## The diff: the world that happened against the one that did not")
    lines.append("")
    if report.world is None:
        lines.append("No world was published. See above for why.")
        lines.append("")
    elif not report.world.diff.deltas:
        lines.append(report.world.diff.empty_because or "The diff is empty.")
        lines.append("")
    else:
        diff = report.world.diff
        lines.append(
            f"- occurrences reached: {diff.reached_count}; changed: {len(diff.deltas)}; "
            f"reached and unchanged: {diff.unchanged_count}"
        )
        lines.append(
            f"- the graph says {len(diff.eliminated_event_ids)} would not have happened, "
            f"and {len(diff.reduced_event_ids)} would still have happened and been smaller"
        )
        lines.append("")
        lines.append(
            "**Those two counts are never added.** A consequence that would have been "
            "smaller is not a consequence that would have been prevented, and merging them "
            "is the single most common counterfactual error."
        )
        lines.append("")
        lines.append("| occurrence | kinds | was | would have been | note |")
        lines.append("|---|---|---|---|---|")
        for delta in diff.deltas[:RENDERED_DELTAS]:
            kinds = ", ".join(f"`{kind.value}`" for kind in delta.kinds)
            was = (
                f"{delta.base_magnitude}{'' if delta.unit is None else ' ' + delta.unit}"
                if delta.base_magnitude is not None
                else "not measurable"
            )
            would = _magnitude_cell(delta.simulated_magnitude, report.validity.verdict, delta.unit)
            lines.append(
                f"| `{delta.event_id}` ({delta.event_type}) | {kinds} | {was} | {would} | "
                f"{delta.detail} |"
            )
        if len(diff.deltas) > RENDERED_DELTAS:
            lines.append("")
            lines.append(
                f"{len(diff.deltas) - RENDERED_DELTAS} further delta(s) are in the JSON and "
                "are not printed here."
            )
        lines.append("")
        lines.append(f"> {ATTRIBUTION_NOT_MEASUREMENT_NOTICE}")
        lines.append("")

    lines.append("## Where the sweep stopped")
    lines.append("")
    if not report.truncations:
        lines.append("The sweep ran to completion within the declared bounds.")
    else:
        for truncation in report.truncations:
            lines.append(
                f"- `{truncation.reason.value}` at `{truncation.at_event_id}` "
                f"(depth {truncation.depth}): {truncation.detail}"
            )
    lines.append("")

    lines.append("## What this run did not check")
    lines.append("")
    lines.append(
        "- **Whether the answer is right.** No labelled causal ground truth exists for this "
        "dataset, so no counterfactual here can be scored against what actually would have "
        "happened. prd.md §57 names 'counterfactual plausibility' as a metric and defines "
        "it nowhere; nothing in this repository can compute it (OQ-030)."
    )
    lines.append(
        "- **Whether a condition that should have stopped holding did.** " + CONDITION_TEST_NOTICE
    )
    lines.append(
        "- **Whether the ontology's changeability declarations are true.** A `mutable: true` "
        "on an attribute no operator could really have set is a declaration that loads "
        "cleanly and is wrong, and nothing here can detect it (R-16)."
    )
    lines.append(
        "- **Anything at dataset scale.** Every figure above is a property of the slice this "
        "run walked, not of the dataset (OQ-023)."
    )
    lines.append("")
    return "\n".join(lines)
