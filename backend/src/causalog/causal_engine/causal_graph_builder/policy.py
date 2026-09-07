"""The promotion decision, and the only place in this repository that assigns `INFERRED`.

ADR-0054 moved promotion here from module 10. One home for the decision, and it is the
module whose README says it owns it -- two places deciding what the engine will assert is
the defect ADR-0053 was written to prevent, and layering a second policy over module 10's
would have reproduced it one module later.

**LAW-TIME is re-verified here, belt and braces, by two independent mechanisms.**

1. **Explicitly, against the intervals.** `_temporal_standing` re-runs
   `core.temporal.verdict` over the two `Event` occurrence intervals fetched from the fact
   set. This is the check a stored edge *cannot* perform on itself: `CausalEdge` holds
   identifiers, not intervals, so its own validator can refuse a stored `VIOLATION` and can
   never recompute one (DEF-0002). Doing it here is the only way the law is checked against
   the data at the moment the assertion is made rather than against a field copied forward
   from module 9.
2. **Structurally, through `revise`.** Promotion is `core.immutability.revise`, which
   re-validates the whole model, so the frozen `CausalEdge` invariant
   `INFERRED ⇒ CERTAIN ∧ ¬temporally_unverifiable` runs again on the revision. A bug in (1)
   raises here rather than laundering an edge into the graph.

Neither check is redundant with the other: (1) can catch a stored verdict that disagrees
with the events, and (2) can catch a promotion path that never consulted (1).

`revise` also refuses an `OBSERVED` artifact outright (LAW-PROVENANCE), which is why
promotion is expressed as a revision rather than as a reconstruction: the guard is on the
path, not on the caller remembering to ask.

**Every threshold read here is a pack declaration.** There is no numeric literal in this
module's decisions, and a test asserts it.
"""

from __future__ import annotations

from causalog.causal_engine.causal_graph_builder.graph import (
    DemotionReason,
    PromotedEdge,
    PropagationWeight,
    TypingRecord,
)
from causalog.causal_engine.confidence_scorer import ScoredEdge, ScoringOutcome
from causalog.core.errors import LawViolationError
from causalog.core.immutability import revise
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import TemporalVerdict, is_unverifiable, verdict
from causalog.core.types import CausalEdge, Event
from causalog.rule_engine import ConfidenceScoringSpec, GraphConstructionSpec

__all__ = ["PromotionVerdict", "decide", "promote"]


class PromotionVerdict:
    """One claim's standing under the pack's policy: promote, or a reason not to.

    Not a model. It never leaves this module -- `PromotedEdge` and `DemotionRecord` are the
    artifacts -- and keeping it plain stops it acquiring fields that belong on those.
    """

    __slots__ = ("detail", "reason", "threshold_band")

    def __init__(
        self,
        *,
        reason: DemotionReason | None,
        detail: str,
        threshold_band: str | None = None,
    ) -> None:
        """Record a verdict: the reason it refuses, or None when it promotes."""
        self.reason = reason
        self.detail = detail
        self.threshold_band = threshold_band

    @property
    def promotes(self) -> bool:
        """Return whether this claim clears every condition the pack sets."""
        return self.reason is None


def _temporal_standing(
    edge: CausalEdge, events_by_id: dict[str, Event]
) -> tuple[TemporalVerdict | None, bool, str | None]:
    """Recompute LAW-TIME from the intervals, returning `(verdict, unverifiable, mismatch)`.

    `mismatch` is a sentence when the recomputed standing disagrees with what the edge
    carries, and `None` when it does not. A disagreement never repairs the edge and never
    promotes it: it is reported, and the claim is demoted.

    `verdict is None` means an event named by the edge is absent from the fact set, so the
    law could not be re-verified at all. That is treated exactly as a failure -- a check
    that could not run must never read as a check that passed (DEF-0001).
    """
    source = events_by_id.get(edge.source_event_id)
    target = events_by_id.get(edge.target_event_id)
    if source is None or target is None:
        return (
            None,
            True,
            (
                f"LAW-TIME could not be re-verified for {edge.causal_edge_id}: "
                f"{'source' if source is None else 'target'} event is not in this run's fact "
                "set. An unperformed check is not a passed one, so promotion is refused."
            ),
        )
    recomputed = verdict(source.occurred_at, target.occurred_at)
    unverifiable = is_unverifiable(source.occurred_at) or is_unverifiable(target.occurred_at)
    if recomputed is not edge.temporal_verdict or unverifiable != edge.temporally_unverifiable:
        return (
            recomputed,
            unverifiable,
            (
                f"the stored temporal standing of {edge.causal_edge_id} "
                f"({edge.temporal_verdict.value}, unverifiable={edge.temporally_unverifiable}) "
                f"disagrees with the intervals, which give {recomputed.value}, "
                f"unverifiable={unverifiable}. The edge is not repaired and is not promoted; a "
                "stored verdict that the data does not support is a defect in whatever wrote "
                "it (DEF-0002)."
            ),
        )
    return recomputed, unverifiable, None


def decide(
    scored: ScoredEdge,
    parameters: GraphConstructionSpec,
    bands: ConfidenceScoringSpec,
    events_by_id: dict[str, Event],
) -> PromotionVerdict:
    """Return whether the pack's policy admits this claim into the stated view.

    The conditions, in the sequence they are checked, and each one reported distinctly
    because they answer different questions a reader might be asking:

    1. **A policy exists.** No declared threshold for this kind means no decision was made,
       reported as `NO_THRESHOLD_DECLARED` -- a statement about the pack, not the claim.
    2. **The outcome is `SCORED`.** `INSUFFICIENT_EVIDENCE` is the absence of a
       measurement, never a low score, and is never promoted however the arithmetic came out.
    3. **LAW-TIME, recomputed.** `UNDETERMINED` and unverifiable are separated, because they
       are different findings about the dataset.
    4. **The band.** The scalar reaches the floor of the band the pack requires for this
       kind. Compared against the declared floor rather than by band name so that an edge
       above a higher band's floor is not rejected for carrying that higher band's label.
    """
    kind = scored.edge.payload.edge_kind.value
    threshold = parameters.threshold_for(kind)
    if threshold is None:
        return PromotionVerdict(
            reason=DemotionReason.NO_THRESHOLD_DECLARED,
            detail=(
                f"the pack declares no graph_construction promotion threshold for edge kind "
                f"{kind}, so no claim of that kind may be promoted. This is a statement "
                "about the pack rather than about this claim: nothing was measured and "
                "found wanting. Declaring a threshold for this kind would make the claim "
                "decidable."
            ),
        )
    if scored.outcome is not ScoringOutcome.SCORED:
        return PromotionVerdict(
            reason=DemotionReason.INSUFFICIENT_EVIDENCE,
            detail=(
                f"module 10 measured {scored.scored_component_count} component(s) and the "
                "pack requires more before it calls an edge scored. This is the absence of "
                "a measurement, not a weak claim, and it is never shown as one."
            ),
        )

    recomputed, unverifiable, mismatch = _temporal_standing(scored.edge, events_by_id)
    if mismatch is not None:
        return PromotionVerdict(reason=DemotionReason.TEMPORAL_NOT_CERTAIN, detail=mismatch)
    if unverifiable:
        return PromotionVerdict(
            reason=DemotionReason.TEMPORALLY_UNVERIFIABLE,
            detail=(
                "the source never placed one of the two events in time, so no precedence "
                "between them can be established. LAW-TIME bars promotion and no threshold "
                "can override it. Distinct from an unresolvable tie: nothing was measured "
                "here, rather than measured and found equal."
            ),
        )
    if recomputed is not TemporalVerdict.CERTAIN:
        return PromotionVerdict(
            reason=DemotionReason.TEMPORAL_NOT_CERTAIN,
            detail=(
                f"the intervals give {recomputed.value if recomputed else 'no'} precedence: "
                "the data placed both events and could not separate them. LAW-TIME bars "
                "promotion. On a source whose instants are recorded at day granularity this "
                "is the expected outcome for most pairs and is a finding about the SOURCE, "
                "not about the claim (CONTEXT.md R-14)."
            ),
        )

    required = next(
        (band for band in bands.confidence_bands if band.name == threshold.minimum_band), None
    )
    if required is None:
        return PromotionVerdict(
            reason=DemotionReason.POLICY_NOT_RUNNABLE,
            detail=(
                f"the pack requires band {threshold.minimum_band!r} for edge kind {kind} and "
                "declares no band by that name, so the threshold could not be evaluated. "
                "The rule-pack loader reports this as an error; it is repeated here so a "
                "graph built from an unchecked pack still says why it is empty."
            ),
        )
    if scored.edge.confidence.scalar < required.minimum_scalar:
        return PromotionVerdict(
            reason=DemotionReason.BELOW_KIND_THRESHOLD,
            detail=(
                f"scored {scored.edge.confidence.scalar:.6f} against the "
                f"{required.name} floor of {required.minimum_scalar:.6f} that this pack "
                f"requires for a {kind} edge. The component breakdown on the edge says "
                "which leg was weak."
            ),
        )
    return PromotionVerdict(reason=None, detail="", threshold_band=required.name)


def promote(
    scored: ScoredEdge,
    weight: PropagationWeight,
    typing: TypingRecord,
    threshold_band: str,
    lineage: object,
    events_by_id: dict[str, Event],
) -> PromotedEdge:
    """Promote one claim to `INFERRED`, re-verifying LAW-TIME on the way.

    The second of the two belt-and-braces checks lives in the `revise` call: re-validating
    the whole model re-runs `CausalEdge`'s own `INFERRED ⇒ CERTAIN ∧ ¬unverifiable`
    invariant, so a caller that reached here without consulting `decide` still cannot
    launder an ambiguous edge into the graph. The explicit re-check below runs first anyway,
    so the failure names the events rather than only the invariant.

    `propagation_weight` is replaced in the same revision. Module 10 set it to the
    confidence scalar because it had nothing better and said so in a comment; it is an
    attribution share now, computed from the ontology's declared measurement. One field, one
    meaning, one revision.

    Raises:
        LawViolationError: if the intervals do not support promotion. Never repaired,
            never skipped.
    """
    _, unverifiable, mismatch = _temporal_standing(scored.edge, events_by_id)
    if mismatch is not None or unverifiable:
        raise LawViolationError(
            "LAW-TIME: refusing to promote "
            f"{scored.edge.causal_edge_id} to INFERRED. "
            + (mismatch or "one of the two events was never placed in time.")
        )
    promoted = revise(
        scored.edge,
        provenance_class=ProvenanceClass.INFERRED,
        propagation_weight=weight.weight,
    )
    payload = scored.edge.payload
    return PromotedEdge(
        edge=promoted,
        lineage=lineage,  # type: ignore[arg-type]
        typing=typing,
        weight=weight,
        threshold_band=threshold_band,
        joint_cause_group_id=getattr(payload, "joint_cause_group_id", None),
    )
