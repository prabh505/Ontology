"""`rule_support` -- how strongly the active rule pack backs this claim.

An explicit, authored rule is the strongest evidence this engine admits, which is why it
carries the largest addend weight (`core.aggregation.V2_ADDEND_WEIGHTS`). It is also the
only component whose strength was written down by a person: `Rule.base_strength` is authored
in the pack beside its `rationale`, so this component is reading a declaration rather than
computing an opinion.

COMBINATION IS NOISY-OR, NOT A MEAN, AND NOT A SUM
---------------------------------------------------
Two independent rules at 0.5 give `1 - (1 - 0.5)(1 - 0.5) == 0.75`. That is deliberate and
it is the standard combination for independent evidence for one proposition: a second
authored rule reaching the same conclusion by different reasoning genuinely does raise
support, and a mean would say the second rule was worth nothing.

The same arithmetic is **refused** one level up: `core.aggregation` does not register a
noisy-OR aggregator, because across COMPONENTS it would manufacture confidence -- an
aggregate above every input. The two levels are different questions. Within one component,
independent corroboration accumulates. Across components, the rollup summarizes and may
never exceed its strongest input. ADR-0052 records the distinction.

WHY CONFLICTS ARE NOT NETTED OFF HERE
--------------------------------------
A rule that a `CONSTRAINT` suppressed, and a pair the rule engine reported a conflict over,
both lower this edge's confidence -- through `contradiction_freedom`, not by being
subtracted from this number. One number, one home: a `rule_support` that quietly contained a
penalty would be a component whose name no longer describes it, and a reader could not tell
a weakly-supported claim from a contradicted one.
"""

from __future__ import annotations

from causalog.causal_engine.confidence_scorer.context import (
    FusedClaim,
    ScoredComponent,
    ScoringContext,
)
from causalog.causal_engine.confidence_scorer.explain import ComponentExplanation
from causalog.causal_engine.confidence_scorer.scorers.shared import citations, not_scorable
from causalog.core.provenance import ProvenanceClass
from causalog.core.types import Event, EvidenceKind

__all__ = ["RuleSupportScorer"]


class RuleSupportScorer:
    """Score the pack's explicit backing for one claim."""

    component_name = "rule_support"

    def requirement(self) -> str:
        """Return what must be present for this component to be scorable."""
        return (
            "at least one EvidenceKind.RULE item on the fused claim. A claim no rule "
            "proposed has no rule support to measure -- which is not the same as a claim "
            "the pack argues against, and is scored as missing rather than as zero."
        )

    def score(
        self,
        claim: FusedClaim,
        context: ScoringContext,
        events_by_id: dict[str, Event],
    ) -> ScoredComponent:
        """Return the noisy-OR of every distinct firing rule's authored strength."""
        rule_items = tuple(item for item in claim.evidence() if item.kind is EvidenceKind.RULE)
        if not rule_items:
            return not_scorable(self.component_name, self.requirement())

        # One strength per distinct evidence item: module 9 merges proposals making the
        # identical claim and carries every justification across, so two rules over one
        # pair arrive here as two items and one rule as one.
        strengths = tuple(sorted(item.strength for item in rule_items))
        combined = 1.0
        for strength in strengths:
            combined *= 1.0 - strength
        value = 1.0 - combined

        source = events_by_id.get(claim.source_event_id)
        target = events_by_id.get(claim.target_event_id)
        present = tuple(event for event in (source, target) if event is not None)
        return ScoredComponent(
            component_name=self.component_name,
            value=value,
            # The pack is an assumption about the world, never an observation of it
            # (ADR-0045, LAW-PROVENANCE). A rule firing does not make its conclusion
            # observed, however strongly it was authored.
            provenance_class=ProvenanceClass.ASSUMED,
            evidence_record_ids=citations(*present),
            explanation=ComponentExplanation(
                component_name=self.component_name,
                plain_language=(
                    f"{len(rule_items)} authored rule justification(s) in the active pack "
                    "support this pair. Their declared strengths are combined so that "
                    "independent rules corroborate rather than average: two rules reaching "
                    "the same conclusion by different reasoning say more than either alone."
                ),
                caveats=(
                    "A rule is a stated belief about the domain, not an observation of it. "
                    "Strong rule support means the pack's authors expected this; it does "
                    "not mean it happened.",
                    "Rules that a constraint suppressed, and conflicts the rule engine "
                    "reported, are NOT subtracted here. They lower this edge through the "
                    "contradiction_freedom component, so that weak support and contradicted "
                    "support stay distinguishable.",
                ),
                inputs=(
                    ComponentExplanation.count("rule justifications", len(rule_items)),
                    *(
                        ComponentExplanation.number(
                            f"authored strength [{item.evidence_item_id}]", item.strength
                        )
                        for item in rule_items
                    ),
                    ComponentExplanation.number("combined (noisy-OR)", value),
                ),
            ),
        )
