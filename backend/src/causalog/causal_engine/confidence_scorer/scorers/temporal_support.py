"""`temporal_support` -- how well the two events' precedence is established.

**This component is a GATE, not an addend.** It does not contribute to a weighted sum that
other evidence can outvote; it caps the result (`core.aggregation.gated_weighted_mean_v1`,
ADR-0052). An edge whose precedence rests on nothing is not slightly less confident than one
whose precedence is certain -- it is bounded, and no quantity of rule or statistical support
may lift it past that bound. A claim that A caused B without knowing that A came first is
not a weak causal claim; it is not a causal claim.

THREE TEMPORAL STANDINGS, SCORED DIFFERENTLY BECAUSE THEY ARE DIFFERENT FINDINGS
---------------------------------------------------------------------------------
* **temporally unverifiable** -- the data never placed one of the events. Scores exactly
  0.0, which caps the edge at the temporal ceiling's floor.
* **`UNDETERMINED`** -- the data placed both events and could not separate them. Scores the
  pack's declared `undetermined_temporal_support`. Deliberately above zero: the events WERE
  placed, which is more than nothing, and deliberately low. `CONTEXT.md` R-14 predicts this
  governs most of the graph on a day-granular source; that is the finding, and the response
  is to report it, never to raise the number.
* **`CERTAIN`** -- the precedence holds. Scored on TIGHTNESS: how narrowly the separation is
  known, degraded by the coarseness of the two timestamps.

`docs/contracts.md` §3 keeps the first two apart and never sums them. So does this.

TIGHTNESS, AND WHY COARSE TIMESTAMPS COST
------------------------------------------
    tightness = 1 / (1 + width / reference_seconds)

where `width` is `maximum - minimum` from `separation_bounds` -- the span of separations the
data admits, not a midpoint. Collapsing an interval to a point for computation is a defect
(`CONVENTIONS.md` §10), so the width IS the measurement here rather than something discarded
to get one. A pair known to the second has a narrow width and scores near 1.0; a pair whose
events are both bound at DAY precision has a width around a day and scores near 0.5 against
a one-day reference. Manufactured precision is expensive by construction.
"""

from __future__ import annotations

from causalog.causal_engine.candidate_cause_generator.generators.support import (
    separation_bounds,
)
from causalog.causal_engine.confidence_scorer.context import (
    FusedClaim,
    ScoredComponent,
    ScoringContext,
)
from causalog.causal_engine.confidence_scorer.explain import ComponentExplanation
from causalog.causal_engine.confidence_scorer.scorers.shared import citations, not_scorable
from causalog.core.precedence import DerivedPrecedence
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import TemporalVerdict
from causalog.core.types import Event

__all__ = ["TemporalSupportScorer"]


def _derived_requirement(check_id: str) -> str:
    """Return the requirement text for a pair whose precedence was measured as arithmetic.

    Branch-specific on purpose. `requirement()` names the parameters this component always
    needs, and both of them WERE supplied here -- reporting them as the gap would send a
    reader to check two declarations that are present and correct.
    """
    return (
        "confidence_scoring.derived_precedence_temporal_support. The supplied measurement "
        f"confirmed check {check_id!r}: this source computed the later instant from the "
        "earlier one, so their precedence holds by arithmetic and the tightness between "
        "them measures the source's own subtraction. What that is worth is a judgement "
        "about this domain, and this component will not invent it."
    )


def _derived_component(
    *,
    value: float,
    declared: float,
    derived: DerivedPrecedence,
    verdict: TemporalVerdict,
    records: tuple[str, ...],
    bounds_width: int,
) -> ScoredComponent:
    """Return the capped component for a precedence the source computed rather than recorded."""
    residuals = ", ".join(
        f"{seconds:+d}s in {count:,} rows" for seconds, count in derived.residual_seconds[:3]
    )
    caveats = [
        "This precedence is ARITHMETIC. The two instants could not have overlapped "
        "whatever the underlying events did, so the verdict over them is guaranteed by "
        "construction and is not an observation. That is why this value is capped rather "
        "than read from the separation.",
        "The cap is the value this rule pack declares. It is a statement about how much "
        "this domain trusts an instant its own source computed, not a measurement.",
        "The derivation itself IS measured. It is not assumed from the column's shape, "
        "and the agreement rate below is the share of evaluable rows it held in exactly.",
    ]
    if residuals:
        caveats.append(
            "A derivation that misses by one or two CONSTANT amounts is a corrupted "
            f"derivation rather than a noisy one. Observed residuals: {residuals}"
            + ("" if derived.residuals_exact else " (histogram capped upstream)")
        )
    return ScoredComponent(
        component_name="temporal_support",
        value=value,
        # ASSUMED, not INFERRED. INFERRED would say the bounds established this precedence;
        # they did not, and the number now standing here came from a declaration.
        provenance_class=ProvenanceClass.ASSUMED,
        evidence_record_ids=records,
        explanation=ComponentExplanation(
            component_name="temporal_support",
            plain_language=(
                "The cause is established as preceding the effect, but only because the "
                "source COMPUTED the second instant from the first. The gap between them "
                "is a subtraction the source had already performed, so it says nothing "
                "about how tightly the relationship is known. This scores the capped value "
                "the rule pack declares for that situation, and CAPS the whole edge."
            ),
            caveats=tuple(caveats),
            inputs=(
                ("temporal verdict", verdict.value),
                ("derivation check", derived.check_id),
                ComponentExplanation.number("measured agreement rate", derived.agreement_rate),
                ComponentExplanation.count("rows evaluated", derived.evaluated),
                ComponentExplanation.count("admissible width (s)", bounds_width),
                ComponentExplanation.number(
                    "declared derived_precedence_temporal_support", declared
                ),
            ),
        ),
    )


class TemporalSupportScorer:
    """Score how well this claim's precedence is established. Acts as a ceiling."""

    component_name = "temporal_support"

    def requirement(self) -> str:
        """Return what must be declared for this component to be scorable."""
        return (
            "confidence_scoring.temporal_reference_seconds and "
            "confidence_scoring.undetermined_temporal_support, plus both events present in "
            "the fact set. A tightness scale borrowed from another domain would score every "
            "pair in this one as tight. Additionally "
            "confidence_scoring.derived_precedence_temporal_support, but only for a pair "
            "whose precedence a supplied measurement found to be arithmetic."
        )

    def score(
        self,
        claim: FusedClaim,
        context: ScoringContext,
        events_by_id: dict[str, Event],
    ) -> ScoredComponent:
        """Return 0.0, the declared undetermined value, or measured tightness."""
        reference = context.parameters.temporal_reference_seconds
        undetermined_value = context.parameters.undetermined_temporal_support
        source = events_by_id.get(claim.source_event_id)
        target = events_by_id.get(claim.target_event_id)
        if reference is None or undetermined_value is None or source is None or target is None:
            return not_scorable(self.component_name, self.requirement())

        # Every candidate in the group shares a pair, so they share a verdict; the first in
        # canonical sequence carries it. Taken from the candidate rather than recomputed:
        # module 9 owns the LAW-TIME gate and this module reads its verdict (F6).
        first = claim.candidates[0]
        unverifiable = any(candidate.temporally_unverifiable for candidate in claim.candidates)
        verdict = first.temporal_verdict
        records = citations(source, target)

        if unverifiable:
            return ScoredComponent(
                component_name=self.component_name,
                value=0.0,
                provenance_class=ProvenanceClass.ASSUMED,
                evidence_record_ids=records,
                explanation=ComponentExplanation(
                    component_name=self.component_name,
                    plain_language=(
                        "The source never placed one of these two events in time, so their "
                        "precedence cannot be checked at all. This scores zero and CAPS the "
                        "whole edge: no amount of other evidence can raise a causal claim "
                        "whose direction rests on nothing."
                    ),
                    caveats=(
                        "This is an absent timestamp, not an ambiguous one. The two are "
                        "different findings about the dataset and are never summed "
                        "(docs/contracts.md section 3).",
                        "This edge can never be promoted to INFERRED, by the type's own "
                        "invariant (ADR-0007).",
                    ),
                    inputs=(
                        ("temporal verdict", verdict.value),
                        ("temporally unverifiable", "true"),
                    ),
                ),
            )

        if verdict is TemporalVerdict.UNDETERMINED:
            return ScoredComponent(
                component_name=self.component_name,
                value=undetermined_value,
                provenance_class=ProvenanceClass.ASSUMED,
                evidence_record_ids=records,
                explanation=ComponentExplanation(
                    component_name=self.component_name,
                    plain_language=(
                        "Both events were placed in time, but not precisely enough to say "
                        "which came first. This scores the low value this rule pack "
                        "declares for an unresolvable precedence, and CAPS the whole edge."
                    ),
                    caveats=(
                        "The events were placed; precedence was not resolved. That is "
                        "more than an absent timestamp and much less than an established "
                        "precedence.",
                        "A dominant UNDETERMINED share is a finding about the source's "
                        "granularity (CONTEXT.md R-14). It is never resolved by loosening "
                        "the test or by raising this number.",
                        "This edge can never be promoted to INFERRED (ADR-0007).",
                    ),
                    inputs=(
                        ("temporal verdict", verdict.value),
                        ComponentExplanation.number(
                            "declared undetermined_temporal_support", undetermined_value
                        ),
                    ),
                ),
            )

        bounds = separation_bounds(source.occurred_at, target.occurred_at)
        width = bounds.maximum_seconds - bounds.minimum_seconds
        value = 1.0 / (1.0 + width / reference)

        # The precedence is sound. The remaining question is whether it was OBSERVED, and
        # only a measurement can answer it -- the bounds cannot, because bounds computed
        # from each other are still bounds and still fail to overlap.
        index = context.derived_precedence
        derived = (
            None
            if index is None
            else index.precedence_for(source.occurred_at.source, target.occurred_at.source)
        )
        if derived is not None:
            capped = context.parameters.derived_precedence_temporal_support
            if capped is None:
                # The pack did not say what an arithmetic precedence is worth, so this
                # module does not decide. NOT SCORABLE rather than the tightness above:
                # scoring it would report the source's own arithmetic back as evidence.
                return not_scorable(self.component_name, _derived_requirement(derived.check_id))
            return _derived_component(
                value=min(value, capped),
                declared=capped,
                derived=derived,
                verdict=verdict,
                records=records,
                bounds_width=width,
            )
        return ScoredComponent(
            component_name=self.component_name,
            value=value,
            # INFERRED: the precedence is a temporal derivation over observed instants, which
            # is precisely what INFERRED means. Whether the EDGE may carry it is decided by
            # promotion, not here (LAW-PROVENANCE).
            provenance_class=ProvenanceClass.INFERRED,
            evidence_record_ids=records,
            explanation=ComponentExplanation(
                component_name=self.component_name,
                plain_language=(
                    "The cause is established as preceding the effect. The score reflects "
                    "how NARROWLY the gap between them is known: the two timestamps admit a "
                    f"separation anywhere between {bounds.minimum_seconds} and "
                    f"{bounds.maximum_seconds} seconds, and a wide admissible range means a "
                    "loosely established relationship even though the precedence itself is sound."
                ),
                caveats=(
                    "Correct precedence is a necessary condition for causation and nowhere "
                    "near a sufficient one. Everything that happens after something else "
                    "is correctly sequenced.",
                    "The separation is carried as bounds and never collapsed to a "
                    "midpoint. A coarse source timestamp widens the bounds and lowers this "
                    "score, which is the intended cost of imprecision (CONVENTIONS.md "
                    "section 10).",
                )
                + (
                    ()
                    if context.derived_precedence is not None
                    else (
                        "NOT AUDITED: no derivation measurement was supplied to this run, "
                        "so whether the source COMPUTED one of these instants from the "
                        "other is unknown. Were it computed, this precedence would hold by "
                        "arithmetic and this score would be capped. The run-level gap is "
                        "reported once in the confidence report.",
                    )
                ),
                inputs=(
                    ("temporal verdict", verdict.value),
                    ComponentExplanation.count("separation minimum (s)", bounds.minimum_seconds),
                    ComponentExplanation.count("separation maximum (s)", bounds.maximum_seconds),
                    ComponentExplanation.count("admissible width (s)", width),
                    ComponentExplanation.count("declared reference (s)", reference),
                    ("cause precision", source.occurred_at.precision.value),
                    ("effect precision", target.occurred_at.precision.value),
                ),
            ),
        )
