"""What module 14 publishes, and the sentence it publishes before anything else.

Every report in this engine leads with what is NOT established rather than closing with it.
Module 10's Confidence Report opens with what is not calibrated; module 13's opens with the
same notice; this one opens with both of theirs plus one of its own, because a recommendation
is the first artifact in this system that is an INSTRUCTION rather than a description.

`ASSUMED_COST_NOTICE` is a fixed property, not a field a run can soften, for the reason
ADR-0070 gave for `NOT_CALIBRATED_NOTICE`: a caveat a run can set is a caveat a run can
unset, and the run that most needs it is the one most likely to.

**No domain vocabulary appears below.**
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from causalog.causal_engine.propagation_analyzer import (
    DIAGNOSTIC_NOT_STATED_NOTICE,
    GraphStanding,
)
from causalog.core.run import OutputEnvelope
from causalog.counterfactual_engine import NOT_CALIBRATED_NOTICE
from causalog.recommendation_engine.context import RecommendationContext
from causalog.recommendation_engine.optimize import RecommendationResult

__all__ = [
    "ASSUMED_COST_NOTICE",
    "RECOMMENDATION_REPORT_SCHEMA_VERSION",
    "RecommendationReport",
    "build_report",
    "render_markdown",
]

RECOMMENDATION_REPORT_SCHEMA_VERSION: Final[str] = "1.0.0"

ASSUMED_COST_NOTICE: Final[str] = (
    "EVERY COST AND EVERY OPERATIONAL RISK BELOW IS AN ASSUMPTION, NOT A MEASUREMENT. They "
    "are read from the ontology pack, where their provenance is pinned to ASSUMED because "
    "no observation in any dataset establishes what an act costs an organisation or what "
    "taking it risks. Nothing in this system can validate either declaration, and a "
    "mis-declared one silently changes the sequence below with no symptom (R-15, R-25). "
    "Benefit figures are SIMULATED: they describe a world that did not happen, re-evaluated "
    "over links derived from rules, temporal structure and frequency rather than identified "
    "as causal effects. This report ranks acts; it does not establish that any of them "
    "would work."
)


class RecommendationReport(BaseModel):
    """The artifact a run publishes, carrying its envelope and its standing.

    `CONVENTIONS.md` §11: an output without its envelope cannot be verified and is a defect.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    recommendation_report_schema_version: str = RECOMMENDATION_REPORT_SCHEMA_VERSION
    envelope: OutputEnvelope
    standing: str = Field(min_length=1)
    result: RecommendationResult
    #: Counts a reader would otherwise have to compute, so two readers agree on them.
    proposed_count: int = Field(ge=0)
    refused_count: int = Field(ge=0)
    recommended_count: int = Field(ge=0)
    withheld_count: int = Field(ge=0)

    @property
    def notice(self) -> str:
        """The caveats this report opens with. A property, so no run can soften them."""
        parts = [ASSUMED_COST_NOTICE, NOT_CALIBRATED_NOTICE]
        if self.standing != GraphStanding.STATED.value:
            parts.append(DIAGNOSTIC_NOT_STATED_NOTICE)
        return "\n\n".join(parts)


def build_report(
    result: RecommendationResult, context: RecommendationContext, envelope: OutputEnvelope
) -> RecommendationReport:
    """Assemble the report. Adds no finding; counts what the result already holds."""
    return RecommendationReport(
        envelope=envelope,
        standing=context.standing.value,
        result=result,
        proposed_count=result.discovery.proposed_count,
        refused_count=len(result.discovery.refused),
        recommended_count=len(result.recommendations),
        withheld_count=len(result.withheld),
    )


def _benefit_cell(report: RecommendationReport, position: int) -> str:
    """Render a benefit as a range, or as the reason there is none. Never as a point."""
    benefit = report.result.recommendations[position].expected_benefit
    if benefit.absent_because is not None:
        return "**no figure** — " + benefit.absent_because.split(".")[0]
    return f"{benefit.low} … {benefit.high} {benefit.unit}"


def render_markdown(report: RecommendationReport) -> str:
    """Render the report, notice first.

    The notice is first because a warning below a table does not survive a screenshot, and
    an act somebody screenshots is an act somebody takes.
    """
    lines: list[str] = [
        "# Recommendation Report",
        "",
        f"`recommendation_report_schema_version` {report.recommendation_report_schema_version} · "
        f"`run_id` {report.envelope.run_id} · standing **{report.standing}**",
        "",
        "> " + report.notice.replace("\n\n", "\n>\n> "),
        "",
        "## 1. What this run did",
        "",
        f"- Nodes proposed by the four generators: **{report.proposed_count}**",
        f"- Refused at the actionability gate: **{report.refused_count}**",
        f"- Published as recommendations: **{report.recommended_count}**",
        f"- Withheld with a reason: **{report.withheld_count}**",
        "",
    ]
    if report.result.policy_gaps:
        lines += ["## 2. Declarations that were absent", ""]
        lines += [f"- {gap}" for gap in report.result.policy_gaps]
        lines += [""]

    lines += ["## 3. Ranked recommendations", ""]
    if not report.result.recommendations:
        lines += [
            "**None.** This is a finding, not an empty section. Every candidate either "
            "failed the actionability gate or was withheld; sections 1 and 4 say which.",
            "",
        ]
    else:
        lines += [
            "| # | Node(s) | Set? | Benefit (range) | Cost | Risk | Confidence | "
            "Desirability | Frontier | Chains |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for position, entry in enumerate(report.result.recommendations):
            lines.append(
                f"| {position + 1} "
                f"| {', '.join(entry.node_event_types)} "
                f"| {'YES' if entry.is_set else 'no'} "
                f"| {_benefit_cell(report, position)} "
                f"| {entry.implementation_cost.class_id or 'NOT_DECLARED'} "
                f"| {entry.operational_risk.class_id or 'NOT_DECLARED'} "
                f"| {entry.confidence.scalar} "
                f"| {entry.desirability} "
                f"| {'on' if entry.on_pareto_frontier else 'dominated'} "
                f"| {entry.chains_broken}/{entry.chains_considered} |"
            )
        lines.append("")

    lines += ["## 4. Withheld, and why", ""]
    if not report.result.withheld:
        lines += ["Nothing was withheld.", ""]
    else:
        lines += ["| Node(s) | Reason | Checked against | Belief |", "|---|---|---|---|"]
        for held in report.result.withheld:
            lines.append(
                f"| {', '.join(held.node_event_types)} | {held.reason.value} "
                f"| {held.checked_against} | {held.belief_scalar} |"
            )
        lines.append("")

    lines += [
        "## 5. What this report is a property of",
        "",
        "Every figure above is a property of the run named in the envelope: this dataset "
        "slice, this ontology pack, this rule pack, this seed. A benefit range is bounded by "
        "the perturbations the pack declares, not by a confidence interval. A cost and a "
        "risk are declarations. Nothing here is calibrated and no procedure in this "
        "repository could calibrate it, because the dataset carries no causal ground truth.",
        "",
    ]
    return "\n".join(lines)
