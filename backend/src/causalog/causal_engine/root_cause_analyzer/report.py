"""`RootCauseRanking` -- four labelled answers, never collapsed -- and the report over it.

ADR-0008's ruling is held by this type rather than by the code that builds it. The four
views are four fields; there is no fifth field collapsing them and no method returning "the"
root cause. A consumer wanting one answer has to choose which question it is asking, which
is the whole point: prd.md §29's example says the earliest and the actionable may differ and
that the system should distinguish both.

The report's first section is what the ranking does not contain, as every report in this
engine begins. Here that section carries three things a reader must see before the numbers:
whether the graph was the stated one or a disowned diagnostic, whether the actionability the
ranking turns on could be validated (it cannot -- R-15), and whether the sequencing is a real
sequencing or a plateau in which the engine cannot separate its own candidates.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalog.causal_engine.propagation_analyzer.view import (
    DIAGNOSTIC_NOT_STATED_NOTICE,
    GraphStanding,
)
from causalog.causal_engine.root_cause_analyzer.ranking import RankedCause
from causalog.causal_engine.root_cause_analyzer.views import TradeOff
from causalog.core.errors import ContractViolationError, LawViolationError
from causalog.core.identifiers import format_float
from causalog.core.provenance import ProvenanceClass
from causalog.core.run import OutputEnvelope

__all__ = [
    "ACTIONABILITY_UNVALIDATED_NOTICE",
    "ROOT_CAUSE_REPORT_SCHEMA_VERSION",
    "RootCauseRanking",
    "RootCauseReport",
    "build_report",
    "render_markdown",
]

ROOT_CAUSE_REPORT_SCHEMA_VERSION = "1.0.0"

#: The most candidates rendered into the markdown. The JSON carries every one.
RENDERED_CAUSES = 20

#: Fixed text. `CONTEXT.md` R-15, stated where it bites rather than only where it was
#: recorded. A property on the ranking, so no revision can soften it.
ACTIONABILITY_UNVALIDATED_NOTICE = (
    "THIS RANKING TURNS ON A DECLARATION NOBODY CAN CHECK. Which events are actionable is "
    "ontology configuration carried with provenance ASSUMED (ADR-0008). Nothing in this "
    "engine can test whether an event really was one somebody could have acted on, so a "
    "single wrong declaration silently changes the recommendation and leaves no trace "
    "(R-15). Read the actionable set as the pack's claim about the domain, not as a finding "
    "about it."
)


class RootCauseRanking(BaseModel):
    """Four labelled answers to four different questions, and the trade-offs between them.

    THE FOUR FIELDS ARE NEVER MERGED. `earliest_cause` answers "where did this start?";
    `highest_consequence_cause` answers "what is the biggest?"; `most_actionable_cause`
    answers "what can anybody change?"; `actionable_root_causes` answers "what should we
    change?". A module, API response or interface that presents one of them as *the* root
    cause is a defect (ADR-0008).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1)
    standing: GraphStanding
    outcome_event_id: str = Field(min_length=1)
    #: Structural. The head of the chain, whether or not anybody could act on it.
    earliest_cause: RankedCause | None = None
    #: The single removal the graph says prevents the most, actionable or not.
    highest_consequence_cause: RankedCause | None = None
    #: The actionable event that is cheapest to act on. May prevent very little.
    most_actionable_cause: RankedCause | None = None
    #: The ranked recommendation: actionable candidates sequenced by ADR-0008's criterion.
    actionable_root_causes: tuple[RankedCause, ...] = ()
    #: Every candidate considered, sequenced canonically. Carried whole so that a reader who
    #: disagrees with all four views can see what was in front of them.
    considered: tuple[RankedCause, ...] = ()
    #: One record per pair of views naming different events.
    trade_offs: tuple[TradeOff, ...] = ()
    candidate_search_truncated: bool = False
    sequencing_function: str | None = None
    provenance_class: ProvenanceClass

    @property
    def actionability_notice(self) -> str:
        """Return the fixed R-15 caveat. A property, so no revision can soften it."""
        return ACTIONABILITY_UNVALIDATED_NOTICE

    @property
    def standing_notice(self) -> str | None:
        """Return the disowning notice for a diagnostic ranking, or None for a stated one."""
        if self.standing is GraphStanding.UNPROMOTED_DIAGNOSTIC:
            return DIAGNOSTIC_NOT_STATED_NOTICE
        return None

    @property
    def views_agree(self) -> bool:
        """Return whether every populated view names one event.

        Reported rather than left to a reader comparing four rows: a chain whose earliest
        event is also its most consequential and is actionable is a SIMPLE chain, and saying
        so is more useful than printing four identical rows.
        """
        named = {
            view.event_id
            for view in (
                self.earliest_cause,
                self.highest_consequence_cause,
                self.most_actionable_cause,
                self.actionable_root_causes[0] if self.actionable_root_causes else None,
            )
            if view is not None
        }
        return len(named) <= 1

    @model_validator(mode="after")
    def _check_invariants(self) -> RootCauseRanking:
        """Refuse a ranking that has collapsed its own views or laundered its standing."""
        if (
            self.standing is GraphStanding.UNPROMOTED_DIAGNOSTIC
            and self.provenance_class is ProvenanceClass.INFERRED
        ):
            raise LawViolationError(
                "RootCauseRanking carries INFERRED under an UNPROMOTED_DIAGNOSTIC standing. "
                "Nothing walked under that standing was asserted, so no ranking over it may "
                "claim to be an inference (LAW-PROVENANCE)."
            )
        considered = {cause.event_id for cause in self.considered}
        for name, view in (
            ("earliest_cause", self.earliest_cause),
            ("highest_consequence_cause", self.highest_consequence_cause),
            ("most_actionable_cause", self.most_actionable_cause),
        ):
            if view is not None and view.event_id not in considered:
                raise ContractViolationError(
                    f"RootCauseRanking.{name} names {view.event_id}, which is not among the "
                    "candidates considered. A headline answer absent from the list beneath "
                    "it cannot be checked by the reader it is shown to."
                )
        for cause in self.actionable_root_causes:
            if not cause.actionability.is_actionable:
                raise LawViolationError(
                    f"RootCauseRanking recommends {cause.event_id}, which is not actionable. "
                    "prd.md §29's definition turns on actionability, and an unactionable "
                    "recommendation is not a recommendation."
                )
        keys = [cause.sort_key() for cause in self.actionable_root_causes]
        if keys != sorted(keys):
            raise ContractViolationError(
                "RootCauseRanking.actionable_root_causes is unsequenced; it is the ranked "
                "output and a sequence that is not the ranking misrepresents it."
            )
        return self


class RootCauseReport(BaseModel):
    """The account beside the ranking: coverage, disagreements, and what could not be said."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    report_schema_version: str = ROOT_CAUSE_REPORT_SCHEMA_VERSION
    envelope: OutputEnvelope
    standing: GraphStanding
    outcome_event_id: str = Field(min_length=1)
    candidates_considered: int = Field(ge=0)
    actionable_candidates: int = Field(ge=0)
    recommended_count: int = Field(ge=0)
    #: How many candidates were excluded from the recommendation by the declared chain
    #: floor. Reported so an empty recommendation produced by a threshold is never mistaken
    #: for one produced by the evidence.
    excluded_by_chain_floor: int = Field(default=0, ge=0)
    minimum_chain_scalar: float | None = None
    #: How many candidates could not be valued at all. They are ranked last and their
    #: absence of a magnitude is stated on each, never counted as zero.
    unvalued_candidates: int = Field(default=0, ge=0)
    #: Distinct sequencing values among the recommended. **A plateau is not a ranking**: at
    #: one distinct value the engine cannot separate its own candidates, and any sequence
    #: imposed on them is arbitrary.
    distinct_sequencing_values: int = Field(default=0, ge=0)
    #: `(event_type, count)` over the candidates, sorted.
    candidates_by_type: tuple[tuple[str, int], ...] = ()
    #: Every stamp-versus-pack actionability disagreement, sorted. Reported, never resolved.
    actionability_disagreements: tuple[tuple[str, str], ...] = ()
    #: How many chains pass through an instant the source never observed.
    partial_data_chains: int = Field(default=0, ge=0)
    views_agree: bool = False
    trade_off_count: int = Field(default=0, ge=0)
    candidate_search_truncated: bool = False
    policy_gaps: tuple[tuple[str, str, str], ...] = ()
    not_runnable_because: str | None = None


def _policy_gaps(context: object) -> tuple[tuple[str, str, str], ...]:
    """Collect the `root_cause_analysis` declarations the pack does not make.

    Returned as `(policy, requirement, consequence)` triples rather than as a model,
    because module 12 already publishes a `PolicyGap` and a second identical type in a
    sibling package would be one concept with two definitions.
    """
    parameters = context.parameters  # type: ignore[attr-defined]
    gaps: list[tuple[str, str, str]] = []
    if parameters.ranking_function is None:
        gaps.append(
            (
                "root_cause_analysis.ranking_function",
                "the name of a function registered in causalog.core.ranking",
                "no candidate carries a sequencing value, so the recommendation is "
                "sequenced by earliness alone. The structural views -- earliest, and the "
                "actionable set -- are unaffected, because neither needs a sequencing.",
            )
        )
    if parameters.minimum_chain_scalar is None:
        gaps.append(
            (
                "root_cause_analysis.minimum_chain_scalar",
                "a floor in [0.0, 1.0] a chain must compose to before it is recommended",
                "every actionable candidate is recommended whatever its chain composes to. "
                "The composed value is on each row, so nothing is hidden -- but the pack has "
                "not said how much belief it requires before acting.",
            )
        )
    if parameters.recurrence_minimum_support is None:
        gaps.append(
            (
                "root_cause_analysis.recurrence_minimum_support",
                "how many repetitions make a pattern in this domain",
                "recurrence is COUNTED and never CLASSIFIED. The count is a measurement and "
                "is always reported; calling something structural is a judgement and needs "
                "a declared threshold (ADR-0049).",
            )
        )
    return tuple(sorted(gaps))


def build_report(
    ranking: RootCauseRanking, context: object, envelope: OutputEnvelope
) -> RootCauseReport:
    """Assemble the report over one finished ranking. Pure: it measures and decides nothing."""
    floor = context.parameters.minimum_chain_scalar  # type: ignore[attr-defined]
    actionable = tuple(cause for cause in ranking.considered if cause.actionability.is_actionable)
    excluded = (
        sum(1 for cause in actionable if cause.chain.composed < floor) if floor is not None else 0
    )
    per_type: dict[str, int] = {}
    for cause in ranking.considered:
        per_type[cause.event_type] = per_type.get(cause.event_type, 0) + 1
    disagreements = tuple(
        sorted(
            (cause.event_id, cause.actionability.disagreement)
            for cause in ranking.considered
            if cause.actionability.disagreement is not None
        )
    )
    values = {
        format_float(cause.sequencing_value)
        for cause in ranking.actionable_root_causes
        if cause.sequencing_value is not None
    }
    return RootCauseReport(
        envelope=envelope,
        standing=ranking.standing,
        outcome_event_id=ranking.outcome_event_id,
        candidates_considered=len(ranking.considered),
        actionable_candidates=len(actionable),
        recommended_count=len(ranking.actionable_root_causes),
        excluded_by_chain_floor=excluded,
        minimum_chain_scalar=floor,
        unvalued_candidates=sum(
            1 for cause in ranking.considered if cause.prevented_magnitude is None
        ),
        distinct_sequencing_values=len(values),
        candidates_by_type=tuple(sorted(per_type.items())),
        actionability_disagreements=disagreements,
        partial_data_chains=sum(
            1 for cause in ranking.considered if cause.partial_data_flag is not None
        ),
        views_agree=ranking.views_agree,
        trade_off_count=len(ranking.trade_offs),
        candidate_search_truncated=ranking.candidate_search_truncated,
        policy_gaps=_policy_gaps(context),
        not_runnable_because=(
            "no candidate cause was found: nothing in this view leads to the outcome. That "
            "is a statement about the graph, not about the outcome -- a cause the engine "
            "never asserted is a cause this ranking cannot see."
            if not ranking.considered
            else None
        ),
    )


def _row(cause: RankedCause) -> str:
    """Render one candidate as a table row. Every signal in its own column, none blended."""
    prevented = (
        f"{format_float(cause.prevented_magnitude)} {cause.prevented_unit or ''}".strip()
        if cause.prevented_magnitude is not None
        else "not measurable"
    )
    share = f"{format_float(cause.prevented_share)}" if cause.prevented_share is not None else "--"
    value = format_float(cause.sequencing_value) if cause.sequencing_value is not None else "--"
    structural = (
        "--"
        if cause.recurrence.structural is None
        else ("structural" if cause.recurrence.structural else "incidental")
    )
    return (
        f"| `{cause.event_id[:16]}` | `{cause.event_type}` | "
        f"{'yes' if cause.actionability.is_actionable else 'no'} | "
        f"{cause.actionability.cost_class or '--'} | {cause.earliness_rank} | {prevented} | "
        f"{share} | {format_float(cause.chain.composed)} | {cause.chain.path_length} | "
        f"{cause.recurrence.occurrences} | {structural} | {value} |"
    )


_HEADER = (
    "| cause | type | actionable | cost | earliness | prevents | share | chain | links | "
    "recurs | pattern | prevented x chain |"
)
_RULE = "|---|---|---|---|---:|---|---:|---:|---:|---:|---|---:|"


def render_markdown(ranking: RootCauseRanking, report: RootCauseReport) -> str:
    """Render the ranking as markdown. Returns a string; writing it belongs in `scripts/`."""
    lines: list[str] = [
        "# Root Cause Ranking",
        "",
        f"- outcome: `{ranking.outcome_event_id}`",
        f"- standing: `{ranking.standing.value}`",
        f"- `run_id`: `{report.envelope.run_id}`",
        f"- `report_schema_version`: `{report.report_schema_version}`",
        "",
    ]
    if ranking.standing_notice is not None:
        lines.extend([f"> **{ranking.standing_notice}**", ""])
    lines.extend(["## What this ranking does not contain", ""])
    if report.not_runnable_because is not None:
        lines.extend([f"**NO CANDIDATE CAUSE.** {report.not_runnable_because}", ""])
    lines.extend([f"> **{ranking.actionability_notice}**", ""])
    if report.candidate_search_truncated:
        lines.extend(
            [
                "**THE CANDIDATE SEARCH WAS TRUNCATED** at the declared cap. Causes exist "
                "that were not considered, so every view below is a choice among a subset.",
                "",
            ]
        )
    if report.excluded_by_chain_floor:
        lines.extend(
            [
                f"{report.excluded_by_chain_floor} actionable candidate(s) were excluded "
                f"from the recommendation by the declared chain floor of "
                f"{format_float(report.minimum_chain_scalar or 0.0)}. They are still "
                "listed under 'Every candidate considered' with their numbers, so an empty "
                "recommendation produced by a threshold is never mistaken for one produced "
                "by the evidence.",
                "",
            ]
        )
    if report.unvalued_candidates:
        lines.extend(
            [
                f"{report.unvalued_candidates} of {report.candidates_considered} "
                "candidate(s) could not be valued. They are sequenced last and carry no "
                "magnitude, rather than being counted as preventing zero.",
                "",
            ]
        )
    if report.partial_data_chains:
        lines.extend(
            [
                f"{report.partial_data_chains} of {report.candidates_considered} chain(s) "
                "pass through an instant the source never observed. The flag is on each row "
                "and travels into every explanation built on it.",
                "",
            ]
        )
    if report.policy_gaps:
        lines.extend(
            [
                "### Policies that could not run",
                "",
                "An absent declaration is reported, never defaulted (ADR-0049).",
                "",
                "| policy | needs | consequence |",
                "|---|---|---|",
            ]
        )
        lines.extend(
            f"| `{policy}` | {requirement} | {consequence} |"
            for policy, requirement, consequence in report.policy_gaps
        )
        lines.append("")
    lines.extend(
        [
            "## The four views",
            "",
            'prd.md §29: *"The storm may be earliest. Late dispatch may be actionable. The '
            'system should distinguish both."* ADR-0008 requires these to be four separate '
            "answers to four separate questions. They are never blended into one figure, "
            "and where they disagree the trade-off is stated below rather than resolved.",
            "",
            "| view | answers | event | type |",
            "|---|---|---|---|",
        ]
    )
    for label, question, view in (
        ("`EARLIEST_EVENT`", "where did this start?", ranking.earliest_cause),
        (
            "`HIGHEST_CONSEQUENCE_EVENT`",
            "what single removal prevents the most?",
            ranking.highest_consequence_cause,
        ),
        (
            "`MOST_ACTIONABLE_EVENT`",
            "what can anybody actually change?",
            ranking.most_actionable_cause,
        ),
        (
            "`RECOMMENDED_ROOT_CAUSE`",
            "what should we change?",
            ranking.actionable_root_causes[0] if ranking.actionable_root_causes else None,
        ),
    ):
        if view is None:
            lines.append(f"| {label} | {question} | *none* | -- |")
        else:
            lines.append(f"| {label} | {question} | `{view.event_id[:16]}` | `{view.event_type}` |")
    lines.append("")
    if ranking.views_agree:
        lines.extend(
            [
                "**These views agree.** The earliest event in this chain is also the most "
                "consequential one and is actionable, so there is no trade-off to make. "
                "That is a simple chain and is worth saying explicitly.",
                "",
            ]
        )
    if ranking.trade_offs:
        lines.extend(["### Where the views disagree, and what each costs", ""])
        for record in ranking.trade_offs:
            lines.extend(
                [
                    f"**`{record.first_view.value}` (`{record.first_event_id[:16]}`) vs "
                    f"`{record.second_view.value}` (`{record.second_event_id[:16]}`)**",
                    "",
                    record.detail,
                    "",
                ]
            )
    lines.extend(["## Recommended root causes", ""])
    if not ranking.actionable_root_causes:
        lines.extend(
            [
                "**None.** "
                + (
                    "No candidate in this chain is declared actionable, so there is nothing "
                    "to recommend changing. The earliest and highest-consequence views above "
                    "still hold: something started this and something is biggest, and "
                    "neither is a thing anybody can change."
                    if report.actionable_candidates == 0
                    else "Every actionable candidate fell below the declared chain floor."
                ),
                "",
            ]
        )
    else:
        if report.distinct_sequencing_values <= 1 and report.recommended_count > 1:
            lines.extend(
                [
                    "**THIS IS A PLATEAU, NOT A RANKING.** Every recommended candidate "
                    "carries one sequencing value, so the engine cannot separate them. The "
                    "sequence below is canonical and arbitrary, and preferring the first row "
                    "over the second is a choice the engine has not made for you.",
                    "",
                ]
            )
        lines.extend([_HEADER, _RULE])
        lines.extend(_row(cause) for cause in ranking.actionable_root_causes[:RENDERED_CAUSES])
        lines.append("")
    lines.extend(
        [
            "## Every candidate considered",
            "",
            f"{report.candidates_considered} candidate(s), "
            f"{report.actionable_candidates} of them actionable. Carried whole so a reader "
            "who disagrees with all four views can see what was in front of them.",
            "",
            _HEADER,
            _RULE,
        ]
    )
    lines.extend(_row(cause) for cause in ranking.considered[:RENDERED_CAUSES])
    if len(ranking.considered) > RENDERED_CAUSES:
        lines.append(
            f"| ... | {len(ranking.considered) - RENDERED_CAUSES} further row(s) in the "
            "JSON artifact | | | | | | | | | | |"
        )
    lines.append("")
    if report.actionability_disagreements:
        lines.extend(
            [
                "## Actionability disagreements",
                "",
                "Reported, never resolved. The stamp on the event is what the ranking used.",
                "",
                "| candidate | disagreement |",
                "|---|---|",
            ]
        )
        lines.extend(
            f"| `{event_id[:16]}` | {detail} |"
            for event_id, detail in report.actionability_disagreements
        )
        lines.append("")
    return "\n".join(lines)
