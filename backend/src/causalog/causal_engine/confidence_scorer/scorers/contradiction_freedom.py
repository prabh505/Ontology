"""`contradiction_freedom` -- what argues AGAINST this claim, expressed so it stays monotone.

The brief this module was built to is "contradiction penalty". The component is named for
freedom rather than for penalty, and the inversion is deliberate and is stated everywhere it
is rendered.

WHY THE INVERSION
-----------------
Every other component rises with support. A penalty that rose with counter-evidence would be
the one component where a larger number meant a worse claim, and the aggregation strategy
would have to know which of its inputs to subtract -- which is exactly the "an aggregator
that has to know what its components mean" problem `docs/contracts.md` §5 avoids by
normalizing counts before they become components. Worse, it would break monotonicity: the
strategy is required to be non-decreasing in every component, and a subtracted term is not.

So: **1.0 means nothing on record argues against this claim; 0.0 means a great deal does.**
More contradiction lowers the number, the number lowers the score, and the strategy stays
uniformly monotone. ADR-0052 records the argument.

**This component is a GATE, not an addend**, for the same reason `temporal_support` is. A
claim a `CONSTRAINT` rule prohibits is not a slightly weaker claim to be outvoted by enough
correlation; it is capped. Its ceiling is steeper than the temporal one, because active
counter-evidence is a positive finding against the claim while unverifiable time is only an
absence.

FOUR SOURCES OF CONTRADICTION, WEIGHTED BY HOW DIRECTLY THEY BEAR
-------------------------------------------------------------------
1. **A `CONSTRAINT` prohibition on this exact pair.** The pack states this cannot happen.
   The strongest signal available and the only one that can drive the component to zero.
2. **A rule-engine conflict** touching a rule that supports this pair: the pack argues with
   itself here, and module 9 already reports the suppression rather than applying it silently
   (ADR-0044).
3. **The reverse pair also proposed.** Some generator argued B caused A while this claim
   says A caused B. Both cannot be right, and neither is refuted by the other.
4. **Confounding flags naming this edge.** A mediation or common-cause triangle is not
   counter-evidence -- it is a structure that would explain the association without this
   edge being real -- so it is the weakest of the four and can never by itself drive the
   component low. Nothing at V1 resolves these (`CONTEXT.md` R-05, prd.md §59).
"""

from __future__ import annotations

from causalog.causal_engine.confidence_scorer.context import (
    FusedClaim,
    ScoredComponent,
    ScoringContext,
)
from causalog.causal_engine.confidence_scorer.explain import ComponentExplanation
from causalog.causal_engine.confidence_scorer.scorers.shared import citations
from causalog.core.provenance import ProvenanceClass
from causalog.core.types import Event, EvidenceKind

__all__ = ["CONTRADICTION_WEIGHTS", "ContradictionFreedomScorer"]

#: How much each source of counter-evidence weighs, before saturation. Sequenced by how
#: directly each bears on THIS claim: a prohibition names the pair, a conflict names a rule
#: that supports it, a reverse proposal contests its direction, and a confounding flag names
#: a structure that would explain it away. Engine-level rather than pack-level: these are
#: weights over the engine's OWN findings, not over anything the domain declares, and a pack
#: that could retune them could tune its own contradictions away.
CONTRADICTION_WEIGHTS: dict[str, float] = {
    "constraint_prohibition": 1.00,
    "rule_conflict": 0.50,
    "reverse_pair_proposed": 0.30,
    "confounding_flag": 0.10,
}

#: The total contradiction weight at which freedom has fallen to one half. Saturating like
#: every other count in this module, so that the tenth confounding flag costs less than the
#: second and no accumulation of weak signals can imitate a prohibition.
CONTRADICTION_HALF_AT = 1.0


class ContradictionFreedomScorer:
    """Score the ABSENCE of counter-evidence. Acts as a ceiling."""

    component_name = "contradiction_freedom"

    def requirement(self) -> str:
        """Return what must be present for this component to be scorable.

        Always scorable. The absence of counter-evidence is a real finding over the inputs
        this module holds, and reporting it as missing would let a claim nothing argues
        against look like a claim nobody checked.
        """
        return (
            "nothing; the four contradiction sources are all readable from the run's own "
            "outputs. A claim with no counter-evidence scores 1.0, which is a measured "
            "finding rather than an absence of measurement."
        )

    def score(
        self,
        claim: FusedClaim,
        context: ScoringContext,
        events_by_id: dict[str, Event],
    ) -> ScoredComponent:
        """Return 1 - saturate(total contradiction weight)."""
        pair = (claim.source_event_id, claim.target_event_id)
        reverse = (claim.target_event_id, claim.source_event_id)

        prohibited = pair in context.suppressed_pairs
        reverse_proposed = reverse in context.proposed_pairs
        flag_count = context.confounding_flag_count(
            tuple(candidate.candidate_edge_id for candidate in claim.candidates)
        )
        conflicts = _conflicting_rule_ids(claim, context)

        weight = 0.0
        findings: list[tuple[str, str]] = []
        if prohibited:
            weight += CONTRADICTION_WEIGHTS["constraint_prohibition"]
            findings.append(
                ("constraint prohibition", "this pair is prohibited by a CONSTRAINT rule")
            )
        if conflicts:
            weight += CONTRADICTION_WEIGHTS["rule_conflict"] * len(conflicts)
            findings.append(("rule conflicts", ", ".join(conflicts)))
        if reverse_proposed:
            weight += CONTRADICTION_WEIGHTS["reverse_pair_proposed"]
            findings.append(("reverse pair", "the opposite direction was independently proposed"))
        if flag_count:
            weight += CONTRADICTION_WEIGHTS["confounding_flag"] * flag_count
            findings.append(("confounding flags", str(flag_count)))

        value = 1.0 - (weight / (weight + CONTRADICTION_HALF_AT)) if weight > 0.0 else 1.0

        source = events_by_id.get(claim.source_event_id)
        target = events_by_id.get(claim.target_event_id)
        present = tuple(event for event in (source, target) if event is not None)
        if not findings:
            sentence = (
                "Nothing on record argues against this claim: no constraint prohibits the "
                "pair, no rule conflict touches it, nothing proposed the reverse direction, "
                "and it sits in no flagged confounding structure. This is a measured "
                "finding of no counter-evidence, not an absence of checking."
            )
        else:
            sentence = (
                "This claim has counter-evidence against it, so its score is capped. "
                "Higher is better here: 1.0 means nothing argues against the claim, and "
                "this edge scores "
                f"{value:.3f}. What was found: "
                + "; ".join(f"{label} ({detail})" for label, detail in findings)
                + "."
            )

        return ScoredComponent(
            component_name=self.component_name,
            value=value,
            provenance_class=ProvenanceClass.ASSUMED,
            evidence_record_ids=citations(*present),
            explanation=ComponentExplanation(
                component_name=self.component_name,
                plain_language=sentence,
                caveats=(
                    "READ THE DIRECTION. This component is inverted relative to its name in "
                    "the brief: it scores FREEDOM from contradiction, so a HIGH value means "
                    "LITTLE counter-evidence. It is named this way so that every component "
                    "rises with support and the aggregation stays monotone (ADR-0052).",
                    "A confounding flag is not counter-evidence. It marks a structure that "
                    "could explain the association without this edge being real. Nothing at "
                    "V1 resolves it, and the ABSENCE of a flag is not evidence of no "
                    "confounding -- an unobserved common cause leaves no shape in a graph "
                    "built from observed events (CONTEXT.md R-05).",
                    "Absence of contradiction is not support. A claim nothing argues "
                    "against still needs evidence FOR it, which the other seven components "
                    "supply.",
                ),
                inputs=(
                    ("constraint prohibition", "yes" if prohibited else "no"),
                    ComponentExplanation.count("rule conflicts touching this pair", len(conflicts)),
                    ("reverse pair also proposed", "yes" if reverse_proposed else "no"),
                    ComponentExplanation.count("confounding flags on this edge", flag_count),
                    ComponentExplanation.number("total contradiction weight", weight),
                    ComponentExplanation.number("half-at", CONTRADICTION_HALF_AT),
                ),
            ),
        )


def _conflicting_rule_ids(claim: FusedClaim, context: ScoringContext) -> tuple[str, ...]:
    """Return the suppressed rules that also supply rule evidence for this claim.

    A conflict elsewhere in the pack is not a fact about this edge. Only a conflict
    touching a rule that actually supports THIS pair is counted, which is why the rule
    identifiers are matched against the claim's own evidence rather than against the run.
    """
    if context.rule_evaluation is None:
        return ()
    suppressed = set(context.rule_evaluation.conflicts.suppressed_rule_ids())
    if not suppressed:
        return ()
    supporting: set[str] = set()
    for item in claim.evidence():
        if item.kind is not EvidenceKind.RULE:
            continue
        for rule_id in suppressed:
            if rule_id in item.verification or rule_id in item.description:
                supporting.add(rule_id)
    return tuple(sorted(supporting))
