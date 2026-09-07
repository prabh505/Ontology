"""`statistical_support` -- the measured association, its size, its sample, and its caveats.

prd.md §37 requires that observed facts, business assumptions, statistical associations,
inferred causes and counterfactual simulations are never conflated. This component is the
third of those five and it says so in three separate places: its provenance class is
`STATISTICAL` and never promoted (LAW-PROVENANCE, ADR-0003), its explanation carries
`ASSOCIATION_DISCLAIMER` verbatim, and the report renders it under its own heading.

WHAT IS ACTUALLY REPORTED, AND WHAT IS NOT
-------------------------------------------
* **The measure used:** lift over an instance-level 2x2 contingency table. Named, not
  implied, because "statistical support 0.4" is meaningless without knowing what was
  measured.
* **The effect size:** the lift itself, plus all four contingency cells, so a reader
  recomputes rather than trusts.
* **The sample size:** the instance count, entering the score through the same small-sample
  shrinkage `historical_support` uses. Small samples are penalized, never rounded up.
* **NO p-value, and no significance claim.** No null is tested, no sampling distribution is
  assumed, and the set of instances is fixed and complete rather than sampled. Calling this
  significant would require assumptions nobody here has made. Module 9's generator says the
  same thing in the same words and this component repeats them rather than softening them.

HOW THIS DIFFERS FROM `historical_support`, GIVEN BOTH READ LIFT
------------------------------------------------------------------
They read the same table and they answer different questions, which is why they are two
components and not one. `historical_support` asks whether the pattern RECURS enough to be
worth attention and is dominated by its sample term; this asks how far the association
departs from independence and is dominated by the effect size. On a pair seen twice with
enormous lift the two disagree sharply, and a reader needs to see that disagreement rather
than an average of it. Module 9 draws the same line between its two generators.
"""

from __future__ import annotations

from causalog.causal_engine.candidate_cause_generator import ASSOCIATION_DISCLAIMER
from causalog.causal_engine.confidence_scorer.context import (
    FusedClaim,
    ScoredComponent,
    ScoringContext,
)
from causalog.causal_engine.confidence_scorer.explain import ComponentExplanation
from causalog.causal_engine.confidence_scorer.scorers.shared import (
    EFFECT_WEIGHTED,
    blend,
    citations,
    not_scorable,
    shrinkage,
    squashed_lift,
)
from causalog.core.provenance import ProvenanceClass
from causalog.core.types import Event

__all__ = ["MEASURE_USED", "StatisticalSupportScorer"]

#: The measure this component computes, named in every explanation. A component that says
#: "statistical support: 0.4" without naming what was measured is the unexplained number
#: prd.md section 49 forbids, wearing a component name.
MEASURE_USED = "lift over an instance-level 2x2 contingency table; no hypothesis test is performed"


class StatisticalSupportScorer:
    """Score the measured association, with its size, its sample, and its caveats."""

    component_name = "statistical_support"

    def requirement(self) -> str:
        """Return what must be declared and present for this component to be scorable."""
        return (
            "confidence_scoring.lift_reference and "
            "confidence_scoring.small_sample_prior_count, plus a contingency table with a "
            "non-zero baseline rate for this event-type pair. Without a baseline there is "
            "no independence to measure a departure from."
        )

    def score(
        self,
        claim: FusedClaim,
        context: ScoringContext,
        events_by_id: dict[str, Event],
    ) -> ScoredComponent:
        """Return the association's size on a declared scale, discounted for sample size."""
        reference = context.parameters.lift_reference
        prior_count = context.parameters.small_sample_prior_count
        source = events_by_id.get(claim.source_event_id)
        target = events_by_id.get(claim.target_event_id)
        if reference is None or prior_count is None or source is None or target is None:
            return not_scorable(self.component_name, self.requirement())

        table = context.base_rates.table_for(source.event_type, target.event_type)
        if table is None or table.lift is None:
            return not_scorable(self.component_name, self.requirement())

        lift = table.lift
        effect_size = squashed_lift(lift, reference)
        # Driven by `both`, the cell the ratio's numerator actually rests on -- NOT by the
        # instance total.
        #
        # CORRECTED, and the first version is worth recording because it was wrong in this
        # module's own characteristic way. It discounted on `table.instances`, arguing that a
        # contingency table's precision rests on the whole table. On the reference slice that
        # is 733 against a declared prior of 20, so the term was 0.973 for EVERY pair: a
        # small-sample penalty that never penalized anything, sitting underneath a caveat
        # that correctly announced a small sample. A number and its caveat disagreeing is
        # exactly the defect this module exists to prevent, and it was shipped for one run.
        sample_discount = shrinkage(table.both, prior_count)
        value = blend(sample_discount, effect_size, EFFECT_WEIGHTED)

        caveat_lines = [ASSOCIATION_DISCLAIMER]
        if table.both < prior_count:
            caveat_lines.append(
                f"SMALL SAMPLE. The sequenced pair appears in {table.both} instance(s), "
                f"below this pack's declared prior of {prior_count}. The ratio above is "
                "unstable at that size; it is discounted rather than rounded up, and it "
                "should not be read as a stable property of the domain."
            )
        if context.confounding_flags:
            caveat_lines.append(
                "Confounding structures are present in this candidate graph and are "
                "REPORTED, not resolved. Nothing in V1 distinguishes a direct association "
                "from one explained by a third event, and the absence of a flag is not "
                "evidence of no confounding (CONTEXT.md R-05)."
            )

        return ScoredComponent(
            component_name=self.component_name,
            value=value,
            # STATISTICAL, always. Never promoted to INFERRED however large the number
            # (ADR-0003, LAW-PROVENANCE). This is the mechanism by which a reader can
            # always tell which of their claims rests on a frequency ratio.
            provenance_class=ProvenanceClass.STATISTICAL,
            evidence_record_ids=citations(source, target),
            explanation=ComponentExplanation(
                component_name=self.component_name,
                plain_language=(
                    f"Measure: {MEASURE_USED}. {source.event_type} and "
                    f"{target.event_type} co-occur, in that sequence, at "
                    f"{lift:.3f} times the rate independence would predict, measured over "
                    f"{table.instances} process instances of which {table.both} exhibit the "
                    "pair. The score is that effect size on a declared scale, discounted "
                    "for the size of the sample it was measured on."
                ),
                caveats=tuple(caveat_lines),
                inputs=(
                    ("measure", MEASURE_USED),
                    ComponentExplanation.count("sample size (process instances)", table.instances),
                    ComponentExplanation.count("both", table.both),
                    ComponentExplanation.count("cause only", table.cause_only),
                    ComponentExplanation.count("effect only", table.effect_only),
                    ComponentExplanation.count("neither", table.neither),
                    ComponentExplanation.number("effect size (lift)", lift),
                    ComponentExplanation.number("declared lift_reference", reference),
                    ComponentExplanation.number("effect size on the declared scale", effect_size),
                    ComponentExplanation.count("declared small_sample_prior_count", prior_count),
                    ComponentExplanation.number("sample-size discount", sample_discount),
                    ("blend", "effect-weighted: discount^(1/3) * lift^(2/3)"),
                    ("p-value", "not computed; no null hypothesis is tested"),
                ),
            ),
        )
