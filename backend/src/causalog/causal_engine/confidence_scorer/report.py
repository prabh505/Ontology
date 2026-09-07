"""The Confidence Report: what was scored, what could not be, and what is not calibrated.

A first-class output, matching the `CandidateGraphReport` precedent. It exists because a
confidence distribution is the only place two specific failures are visible, and neither is
visible from any single edge:

* **A component that is constant across every edge contributes nothing.** It has a weight,
  it appears in every vector, and it moves no score. That is the same defect module 9's
  report calls a saturated generator, one layer on, and only the distribution shows it.
* **A component that is MISSING on every edge is a declared measurement nobody made.**
  `graph_connectivity` is exactly this today. An edge's own breakdown says so honestly; only
  the report says it about the whole run.

THE SEQUENCE IS DELIBERATE: WORST NEWS FIRST
------------------------------------------
The rendering opens with what is NOT calibrated, before any number. A reader who stops after
the first screen has read the caveat rather than the totals, which is the opposite of how
these documents usually fail.

WHAT THIS REPORT CANNOT DO, AND SAYS SO
----------------------------------------
It cannot tell you whether the scores are CALIBRATED. Calibration means that edges scored
0.8 are right about 80% of the time, and measuring it needs labelled causal ground truth.
This repository holds none: no fixture set, no labels, and DataCo carries no causal
annotation of any kind. Every diagnostic below is therefore a check of internal consistency
-- that the numbers behave as the strategy says they should -- and internal consistency is
not calibration. That distinction is the first thing the rendering prints.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from causalog.causal_engine.confidence_scorer.bands import (
    BAND_ABSENT_NOTICE,
    INSUFFICIENT_EVIDENCE_NOTICE,
)
from causalog.causal_engine.confidence_scorer.fuse import PayloadDivergence
from causalog.causal_engine.confidence_scorer.graph import ScoredEdge
from causalog.core.identifiers import format_float
from causalog.core.run import OutputEnvelope

__all__ = [
    "CONFIDENCE_REPORT_SCHEMA_VERSION",
    "NOT_CALIBRATED_NOTICE",
    "RENDERED_TOP_EDGES",
    "ComponentTally",
    "ConfidenceReport",
    "ScalarDistribution",
    "render_markdown",
]

#: This report's own shape. It does NOT participate in `run_id`: the report describes a run,
#: it is not an input to one (`CONTEXT.md` §7).
CONFIDENCE_REPORT_SCHEMA_VERSION = "1.1.0"

#: How many edges the rendering prints in full. The report VALUE carries the same ten; the
#: bound is on the document, and it is stated rather than implied.
RENDERED_TOP_EDGES = 10

#: Printed before any number, verbatim. Fixed text rather than generated, so it cannot be
#: softened per run -- the same argument module 9 makes for `ASSOCIATION_DISCLAIMER`.
NOT_CALIBRATED_NOTICE = (
    "**THESE SCORES ARE NOT CALIBRATED.** Calibration means that claims scored 0.8 turn out "
    "to be right about eighty per cent of the time, and measuring it requires labelled "
    "causal ground truth: a set of pairs where someone independently established what "
    "actually caused what. This repository holds none. The reference dataset carries no "
    "causal annotation, and no fixture set of known causes exists, so no reliability curve "
    "can be drawn and no error rate can be quoted.\n\n"
    "What the numbers below ARE is internally consistent: every component is computed from "
    "stated inputs by a named function, the aggregation is monotone and gated, and the "
    "whole vector is reproducible from the artifact. That is a real property and it is a "
    "much weaker one than calibration. Two scores ranking correctly relative to each "
    "other says nothing about either being right.\n\n"
    "The component weights are a stated editorial judgement, not a measurement. Nothing "
    "fitted them, because there was nothing to fit them against. They are written down in "
    "one place (`causalog.core.aggregation.V2_ADDEND_WEIGHTS`) precisely so that "
    "disagreement has somewhere to point."
)


class ComponentTally(BaseModel):
    """One component's behaviour across the whole run.

    `looks_inert` is the one derived flag, and it is derived from the SPREAD of the values,
    not from whether they seem right -- it fires on a component that never varies, which
    contributes a constant to every score and therefore distinguishes nothing.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    component_name: str
    #: Edges on which this component could not be measured. Counted, never hidden.
    missing_count: int
    #: What such an edge would need, taken from the first missing explanation seen.
    requirement: str | None = None
    edges: int
    minimum: float
    median: float
    maximum: float
    mean: float

    @classmethod
    def of(
        cls,
        component_name: str,
        values: tuple[float, ...],
        missing_count: int,
        requirement: str | None,
    ) -> ComponentTally:
        """Return one component's distribution over every edge in the run."""
        if not values:
            return cls(
                component_name=component_name,
                missing_count=missing_count,
                requirement=requirement,
                edges=0,
                minimum=0.0,
                median=0.0,
                maximum=0.0,
                mean=0.0,
            )
        sequenced = sorted(values)
        middle = len(sequenced) // 2
        median = (
            sequenced[middle]
            if len(sequenced) % 2 == 1
            else (sequenced[middle - 1] + sequenced[middle]) / 2.0
        )
        return cls(
            component_name=component_name,
            missing_count=missing_count,
            requirement=requirement,
            edges=len(sequenced),
            minimum=sequenced[0],
            median=median,
            maximum=sequenced[-1],
            mean=sum(sequenced) / len(sequenced),
        )

    @property
    def missing_share(self) -> float:
        """Return the share of edges on which this component could not be measured."""
        if self.edges == 0:
            return 0.0
        return self.missing_count / self.edges

    @property
    def looks_inert(self) -> bool:
        """Return whether this component distinguishes nothing across the run.

        True when every edge holds the same value. Such a component carries a weight, sits
        in every vector, and moves no score -- it is a constant wearing a measurement's
        name, and it is only visible beside the other seven.
        """
        return self.edges > 1 and self.minimum == self.maximum

    @property
    def inertness_note(self) -> str | None:
        """Return why this component is inert, or None if it is not."""
        if not self.looks_inert:
            return None
        if self.missing_count == self.edges:
            return (
                f"MISSING on all {self.edges} edge(s), so it holds {format_float(self.minimum)} "
                "everywhere. Its weight is being applied to an absence: every edge is scored "
                "lower for a measurement nobody made. That is the honest treatment, and it "
                "is also a standing argument for building what would supply it."
            )
        return (
            f"holds {format_float(self.minimum)} on every one of {self.edges} edge(s). A "
            "component that never varies distinguishes nothing; it shifts every score by the "
            "same amount and separates no two claims."
        )


class ScalarDistribution(BaseModel):
    """The shape of the confidence distribution over a whole run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    edges: int
    minimum: float
    median: float
    maximum: float
    mean: float
    #: `(upper bound inclusive, count at or below it and above the previous bound)`, in
    #: ascending sequence over tenths.
    histogram: tuple[tuple[float, int], ...]

    @classmethod
    def of(cls, scalars: tuple[float, ...]) -> ScalarDistribution:
        """Return the distribution over one run's scalars."""
        if not scalars:
            return cls(edges=0, minimum=0.0, median=0.0, maximum=0.0, mean=0.0, histogram=())
        sequenced = sorted(scalars)
        middle = len(sequenced) // 2
        median = (
            sequenced[middle]
            if len(sequenced) % 2 == 1
            else (sequenced[middle - 1] + sequenced[middle]) / 2.0
        )
        buckets: list[tuple[float, int]] = []
        previous = -1.0
        for step in range(1, 11):
            bound = step / 10.0
            buckets.append((bound, sum(1 for value in sequenced if previous < value <= bound)))
            previous = bound
        return cls(
            edges=len(sequenced),
            minimum=sequenced[0],
            median=median,
            maximum=sequenced[-1],
            mean=sum(sequenced) / len(sequenced),
            histogram=tuple(buckets),
        )


class DerivedPrecedenceAudit(BaseModel):
    """Whether this run knew which of its instants the source computed, and what it found.

    Stated ONCE, at run level, rather than repeated per edge. Whether a derivation audit was
    supplied is a property of the run; per-edge it would be the same sentence thousands of
    times, and a reader who saw it there could reasonably read its absence on some other edge
    as a clean result.

    `supplied=False` is the case this exists for. Nothing was measured, so nothing was
    capped, and the zero in `pairs_capped` means "not looked for" rather than "looked for
    and not found". The rendering never prints that zero without the sentence beside it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: False when no measurement reached this run. Then every other field here is vacuous.
    supplied: bool
    #: Declared checks the measurement CONFIRMED. Zero with `supplied` true is a real
    #: finding: the audit ran and this source computes none of the instants it was asked about.
    checks_confirmed: int = Field(default=0, ge=0)
    #: Claims whose `temporal_support` was capped because their precedence is arithmetic.
    pairs_capped: int = Field(default=0, ge=0)


class ConfidenceReport(BaseModel):
    """Everything one scoring produced, as data rather than as a log."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    report_schema_version: str = CONFIDENCE_REPORT_SCHEMA_VERSION
    envelope: OutputEnvelope
    #: The aggregation strategy every vector in this run names.
    aggregation: str
    candidates_read: int
    claims_scored: int
    scored_count: int
    insufficient_count: int
    #: Structurally zero since ADR-0054, which moved promotion to the Causal Graph Builder.
    #: The field keeps its name -- renaming it would break comparison with every report
    #: already committed -- and the rendered section says where the decision went.
    promoted_count: int
    components: tuple[ComponentTally, ...] = Field(min_length=1)
    distribution: ScalarDistribution
    #: `(name, minimum_scalar, plain_language)` as the pack declared them, highest first.
    bands_declared: tuple[tuple[str, float, str], ...]
    band_counts: tuple[tuple[str, int], ...]
    #: `(gate name or "none", count)` -- how often each gate held the scalar down.
    gate_binding_counts: tuple[tuple[str, int], ...]
    payload_divergences: tuple[PayloadDivergence, ...]
    #: `(components measured, edge count)`, ascending. The distribution the outcome floor
    #: is set against: a floor below this histogram's minimum can never fire, which makes
    #: `INSUFFICIENT_EVIDENCE` unreachable and is a pack defect rather than a clean run.
    measured_component_histogram: tuple[tuple[int, int], ...] = ()
    #: The ten highest-scoring edges, carried in full so the report can be inspected
    #: without the graph beside it.
    highest_scoring: tuple[ScoredEdge, ...]
    #: What the pack declared as its outcome floor, or None. Carried so the report can say
    #: whether the floor is capable of firing at all.
    minimum_scored_components: int | None = None
    #: How many edges sit at exactly the maximum scalar. When a gate caps a large set of
    #: edges they all land on one value, and "the top ten" is then a canonical slice of a
    #: tie rather than the ten best-supported claims.
    edges_at_maximum: int = 0
    #: Whether this run was told which of its instants the source computed. Defaulted to
    #: `supplied=False` so a report built without the audit says so rather than omitting it.
    derived_precedence: DerivedPrecedenceAudit = DerivedPrecedenceAudit(supplied=False)

    @property
    def top_is_a_plateau(self) -> bool:
        """Return whether the highest-scoring list is a slice of a tie.

        True when more edges share the maximum scalar than the rendering prints. A gate
        that caps many edges puts every one of them on the same number, and presenting a
        canonical slice of that tie as "the ten highest-scoring edges" would invite a
        reader to believe a ranking the data does not contain.
        """
        return self.edges_at_maximum > len(self.highest_scoring)

    @property
    def outcome_floor_is_unreachable(self) -> bool:
        """Return whether the declared floor can never mark an edge insufficient.

        True when every edge already measures at least the floor. Such a floor is not a
        lenient threshold -- it is a threshold that does not exist, and an
        `INSUFFICIENT_EVIDENCE` count of zero under it says nothing about the data.
        """
        if self.minimum_scored_components is None or not self.measured_component_histogram:
            return False
        return min(count for count, _ in self.measured_component_histogram) >= (
            self.minimum_scored_components
        )

    @property
    def missing_components(self) -> tuple[ComponentTally, ...]:
        """Return every component missing on at least one edge, worst first."""
        return tuple(
            sorted(
                (tally for tally in self.components if tally.missing_count),
                key=lambda tally: (-tally.missing_count, tally.component_name),
            )
        )

    @property
    def inert_components(self) -> tuple[ComponentTally, ...]:
        """Return every component that distinguishes nothing across the run."""
        return tuple(tally for tally in self.components if tally.looks_inert)

    def insufficient_share(self) -> float:
        """Return the share of edges too little was measured on."""
        if self.claims_scored == 0:
            return 0.0
        return self.insufficient_count / self.claims_scored

    def gate_share(self, gate_name: str) -> float:
        """Return the share of edges on which one named gate was the binding constraint."""
        if self.claims_scored == 0:
            return 0.0
        for name, count in self.gate_binding_counts:
            if name == gate_name:
                return count / self.claims_scored
        return 0.0


def render_markdown(report: ConfidenceReport) -> str:
    """Return the report as Markdown, for `docs/reports/<dataset>/<version>/confidence.md`.

    Sequenced worst news first: what is not calibrated, then what could not be measured,
    then the outcome split, and only then the distribution and the top edges. A reader who
    stops after the first screen has seen the caveats rather than the totals.
    """
    lines: list[str] = [
        "# Confidence Report",
        "",
        f"- `report_schema_version`: `{report.report_schema_version}`",
        "- `confidence_schema_version`: `2.0.0` (eight components)",
        f"- `run_id`: `{report.envelope.run_id}`",
        f"- aggregation strategy: `{report.aggregation}`",
        f"- candidate edges read: {report.candidates_read}",
        f"- claims scored (one per source, target, kind): {report.claims_scored}",
        "",
        "## What is not calibrated",
        "",
        NOT_CALIBRATED_NOTICE,
        "",
        "## Components that could not be measured",
        "",
    ]

    missing = report.missing_components
    if not missing:
        lines.append("None. Every component was measurable on every edge.")
    else:
        lines.append(
            "These were emitted at zero and marked missing rather than being omitted. An "
            "omitted component would renormalize away and every edge would score as though "
            "the measurement had been made and found irrelevant. Missing costs score, and "
            "the cost is stated here."
        )
        lines.append("")
        lines.append("| component | missing on | share | needs |")
        lines.append("|---|---:|---:|---|")
        for tally in missing:
            lines.append(
                f"| `{tally.component_name}` | {tally.missing_count} / {tally.edges} | "
                f"{format_float(tally.missing_share)} | {tally.requirement or ''} |"
            )
    lines.append("")

    lines.append("## Was this run told which instants the source computed?")
    lines.append("")
    audit = report.derived_precedence
    if not audit.supplied:
        lines.append(
            "**NOT AUDITED.** No derivation measurement reached this run, so nothing here "
            "distinguishes a precedence the source RECORDED from one it CALCULATED. Where "
            "a source computes its later instant from its earlier one, the two intervals "
            "cannot overlap however the underlying events fell, and the temporal verdict "
            "over them is arithmetic rather than evidence -- scored, on this run, exactly "
            "as an observed precedence would be."
        )
        lines.append("")
        lines.append(
            "The zero counts this section would otherwise print mean NOTHING WAS LOOKED "
            "FOR. They are omitted rather than shown, because a zero here is "
            "indistinguishable from a clean result and would be read as one."
        )
    else:
        lines.append(
            f"Audited. **{audit.checks_confirmed} declared derivation check(s) were "
            f"confirmed**, and {audit.pairs_capped:,} claim(s) had `temporal_support` "
            "capped as a result."
        )
        lines.append("")
        if audit.checks_confirmed == 0:
            lines.append(
                "Zero confirmed is a measurement, not a silence: the audit ran and found "
                "that this source computes none of the instants it was asked about."
            )
        elif audit.pairs_capped == 0:
            lines.append(
                "A confirmed derivation that capped nothing means no scored claim ran "
                "between the two columns it names. The finding stands against the SOURCE "
                "and would bind the moment such a claim appeared."
            )
        else:
            lines.append(
                "A capped claim is not a rejected one. Its precedence holds; what it lacks "
                "is any evidence that the precedence was OBSERVED. The cap is the value "
                "the rule pack declares, and each affected edge names the check that fired."
            )
    lines.append("")

    lines.append("## Components that distinguish nothing")
    lines.append("")
    inert = report.inert_components
    if not inert:
        lines.append("None. Every component varies across the run.")
    else:
        lines.append(
            "A component holding one value on every edge carries a weight and separates no "
            "two claims. This is the same defect module 9's report calls a saturated "
            "generator, one layer on."
        )
        lines.append("")
        for tally in inert:
            lines.append(f"- **`{tally.component_name}`** {tally.inertness_note}")
    lines.append("")

    lines.extend(
        [
            "## Outcome: scored, versus not enough measured",
            "",
            "Two counts, never summed. `INSUFFICIENT_EVIDENCE` is **not** a low score: it "
            "is the absence of a measurement, and showing it as a weak claim would present "
            "a gap as a finding (`docs/contracts.md` §3's distinction, carried into scoring).",
            "",
            f"- **`SCORED`**: {report.scored_count}",
            f"- **`INSUFFICIENT_EVIDENCE`**: {report.insufficient_count} "
            f"({format_float(report.insufficient_share())} of claims)",
            f"- **promoted to `INFERRED` by this module**: {report.promoted_count}",
            "",
            "**Promotion is no longer this module's decision (ADR-0054).** It moved to "
            "`causal_engine.causal_graph_builder`, which owns an explicit per-edge-kind "
            "selection policy declared in the rule pack's `graph_construction` namespace. "
            "The count above is structurally zero from that commit forward and is NOT a "
            "finding about the data; the Graph Quality Report is where promotion is "
            "counted, with the reason every rejected claim was rejected. "
            "`confidence_scoring.promotion_band` is deprecated and the loader warns "
            "about it.",
            "",
            "### How many components were actually measured",
            "",
            "The distribution the outcome floor is set against. A floor at or below this "
            "histogram's minimum can never fire, and an `INSUFFICIENT_EVIDENCE` count of "
            "zero under such a floor says nothing about the data -- it says the threshold "
            "does not exist.",
            "",
            "| components measured (of 8) | edges |",
            "|---:|---:|",
        ]
    )
    for measured, count in report.measured_component_histogram:
        lines.append(f"| {measured} | {count} |")
    lines.append("")
    if report.minimum_scored_components is None:
        lines.append(
            "This rule pack declares no `minimum_scored_components`, so no edge is ever "
            "called `INSUFFICIENT_EVIDENCE`. That is a legitimate declaration and it is "
            "not the same as every edge having been measured well."
        )
    else:
        lines.append(
            f"Declared floor: **{report.minimum_scored_components}**."
            + (
                "  **THIS FLOOR CANNOT FIRE.** Every edge in this run already measures at "
                "least that many components, so the zero above is a property of the "
                "threshold and not of the data."
                if report.outcome_floor_is_unreachable
                else ""
            )
        )
    lines.append("")
    if report.insufficient_count:
        lines.append(INSUFFICIENT_EVIDENCE_NOTICE)
        lines.append("")
    lines.extend(
        [
            "## Which gate bound the score",
            "",
            "`temporal_support` and `contradiction_freedom` are ceilings, not addends: they "
            "cap the score rather than being outvoted by it (ADR-0052). This table says how "
            "often each was the binding constraint. A dominant temporal share is a finding "
            "about the source's granularity, not about the claims (`CONTEXT.md` R-14).",
            "",
            "| binding gate | edges | share |",
            "|---|---:|---:|",
        ]
    )
    for name, count in report.gate_binding_counts:
        share = count / report.claims_scored if report.claims_scored else 0.0
        label = "none (the weighted mean stood)" if name == "none" else f"`{name}`"
        lines.append(f"| {label} | {count} | {format_float(share)} |")
    lines.append("")

    distribution = report.distribution
    lines.extend(
        [
            "## Confidence distribution",
            "",
            f"- edges: {distribution.edges}",
            f"- minimum: {format_float(distribution.minimum)} · median: "
            f"{format_float(distribution.median)} · mean: {format_float(distribution.mean)} "
            f"· maximum: {format_float(distribution.maximum)}",
            "",
            "| scalar (up to) | edges |",
            "|---:|---:|",
        ]
    )
    for bound, count in distribution.histogram:
        lines.append(f"| {format_float(bound)} | {count} |")
    lines.append("")

    lines.append("## Bands")
    lines.append("")
    if not report.bands_declared:
        lines.append(BAND_ABSENT_NOTICE)
    else:
        lines.append(
            "Thresholds and wording are declared in the rule pack, not in engine or UI code "
            "(ADR-0053). A boundary in a component is a policy no reviewer can find and two "
            "screens can silently disagree about."
        )
        lines.append("")
        counts = dict(report.band_counts)
        for name, floor, plain_language in report.bands_declared:
            lines.append(f"### `{name}` — scalar at or above {format_float(floor)}")
            lines.append("")
            lines.append(f"{counts.get(name, 0)} edge(s).")
            lines.append("")
            lines.append(f"> {plain_language.strip()}")
            lines.append("")
    lines.append("")

    lines.append("## Per-component distribution")
    lines.append("")
    lines.append("| component | missing | min | median | mean | max |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for tally in report.components:
        lines.append(
            f"| `{tally.component_name}` | {tally.missing_count} | "
            f"{format_float(tally.minimum)} | {format_float(tally.median)} | "
            f"{format_float(tally.mean)} | {format_float(tally.maximum)} |"
        )
    lines.append("")

    lines.append(f"## The {RENDERED_TOP_EDGES} highest-scoring edges, in full")
    lines.append("")
    if not report.highest_scoring:
        lines.append("No edge was scored.")
    else:
        lines.append(
            "Every component of every edge below, with the arithmetic that produced it. "
            "This is what prd.md §49 asks for: never a single unexplained number."
        )
        lines.append("")
        if report.top_is_a_plateau:
            lines.append(
                f"> **THIS IS NOT A RANKING OF THE TOP {RENDERED_TOP_EDGES}.** "
                f"{report.edges_at_maximum} edges share the maximum scalar of "
                f"{format_float(report.distribution.maximum)}, which is more than this "
                "section prints. They are tied because a **gate** put them there: a "
                "ceiling maps every edge above it onto one value, so the claims below are "
                "a canonical slice of a tie, not the best-supported claims in the graph. "
                "Read them as examples of what sits at the ceiling. Anything that looks "
                "like a ranking between them is the sort key, not the evidence."
            )
            lines.append("")
        for position, scored in enumerate(report.highest_scoring, start=1):
            lines.extend(_render_edge(position, scored))
    lines.append("")

    lines.append("## Payload divergence")
    lines.append("")
    if not report.payload_divergences:
        lines.append(
            "None. No two candidates of one kind over one pair disagreed about their "
            "payload parameters."
        )
    else:
        lines.append(
            f"{len(report.payload_divergences)} fused claim(s) gathered candidates of one "
            "kind whose payload parameters differ. The fused edge carries the first in "
            "canonical sequence. **This is reported rather than resolved**: two conditions "
            "cannot be averaged, and picking one is a judgement about which was meant."
        )
        lines.append("")
        lines.append("| cause | effect | kind | payloads | generators |")
        lines.append("|---|---|---|---:|---|")
        for divergence in report.payload_divergences:
            lines.append(
                f"| `{divergence.source_event_id}` | `{divergence.target_event_id}` | "
                f"{divergence.edge_kind} | {len(divergence.payloads)} | "
                f"{', '.join(divergence.generator_ids)} |"
            )
    lines.append("")
    return "\n".join(lines)


def _render_edge(position: int, scored: ScoredEdge) -> list[str]:
    """Return the full breakdown of one edge, components and all."""
    edge = scored.edge
    lines = [
        f"### {position}. `{edge.source_event_id}` → `{edge.target_event_id}`",
        "",
        f"- `causal_edge_id`: `{edge.causal_edge_id}`",
        f"- edge kind: `{edge.payload.edge_kind.value}`",
        f"- **confidence: {format_float(edge.confidence.scalar)}** via "
        f"`{edge.confidence.aggregation}`",
        f"- band: {scored.band_name or 'none'}",
        f"- outcome: `{scored.outcome.value}` "
        f"({scored.scored_component_count} of 8 components measured)",
        f"- provenance: `{edge.provenance_class.value}` · temporal verdict: "
        f"`{edge.temporal_verdict.value}` · temporally unverifiable: "
        f"{str(edge.temporally_unverifiable).lower()}",
        f"- weighted mean of the addends before gating: "
        f"{format_float(scored.ungated_mean)}; binding gate: "
        f"{scored.binding_gate or 'none'}",
        "",
    ]
    if scored.outcome.value == "INSUFFICIENT_EVIDENCE":
        lines.append(f"> {INSUFFICIENT_EVIDENCE_NOTICE}")
        lines.append("")
    if scored.band_plain_language:
        lines.append(f"> {scored.band_plain_language.strip()}")
        lines.append("")
    values = {component.component_name: component.value for component in edge.confidence.components}
    for explanation in scored.explanations:
        marker = " *(MISSING)*" if explanation.missing else ""
        lines.append(
            f"**`{explanation.component_name}` = "
            f"{format_float(values[explanation.component_name])}**{marker}"
        )
        lines.append("")
        lines.append(explanation.plain_language.strip())
        lines.append("")
        if explanation.requirement:
            lines.append(f"- *needs*: {explanation.requirement}")
        for label, value in explanation.inputs:
            lines.append(f"- {label}: `{value}`")
        for caveat in explanation.caveats:
            lines.append(f"- ⚠ {caveat}")
        lines.append("")
    return lines
