"""The orchestrator: fuse, score all eight, aggregate, band, promote, report.

Sequence, and why it is this sequence:

1. **Fuse.** Module 9's multigraph becomes one claim per `(source, target, edge_kind)`,
   because that is `CausalEdge.address`'s key. Diversity is only computable after this.
2. **Score all eight components, for every claim, always.** No component is skipped. One
   that cannot be measured is emitted at zero and marked missing, so absence costs
   confidence and is visible in the artifact rather than inferred from a gap.
3. **Aggregate through `core.aggregation.aggregate`.** That is the only path that names the
   function in the vector and sets provenance to the weakest input rather than to the
   arithmetic (ADR-0005, ADR-0009).
4. **Decide the outcome** before the band: too few measured components is
   `INSUFFICIENT_EVIDENCE`, which is not a low score and never gets a band.
5. **Band**, from the pack's declaration, never from a literal here.
6. **Promote**, or refuse to. Three conditions, all of them necessary.
7. **Report** every count, with the distinctions the report refuses to collapse.

Steps 4 and 5 are in that sequence deliberately: banding first would put a label on an edge
that has no business carrying one, and removing it afterwards leaves the label in whatever
consumed the intermediate.

WHY PROMOTION IS HERE AND NOT IN A GENERATOR
---------------------------------------------
`ProvenanceClass.INFERRED` is a judgement, and module 9 is forbidden from making it -- its
gate stamps `ASSUMED` or `STATISTICAL` and stops (`gate.py`). This module is the first place
in the pipeline permitted to say a causal claim is inferred, and `docs/architecture.md`
§Module 10 names it as the only module permitted to write `CAUSES`. The three conditions
below are that permission being exercised narrowly.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from causalog.causal_engine.candidate_cause_generator import ConfoundingFlag
from causalog.causal_engine.confidence_scorer.bands import ScoringOutcome, band_for
from causalog.causal_engine.confidence_scorer.context import (
    ComponentScorer,
    FusedClaim,
    ScoredComponent,
    ScoringContext,
)
from causalog.causal_engine.confidence_scorer.fuse import PayloadDivergence, fuse_candidates
from causalog.causal_engine.confidence_scorer.graph import CausalGraph, ScoredEdge
from causalog.causal_engine.confidence_scorer.report import (
    ComponentTally,
    ConfidenceReport,
    DerivedPrecedenceAudit,
    ScalarDistribution,
)
from causalog.causal_engine.confidence_scorer.scorers import (
    ContradictionFreedomScorer,
    EvidenceCountScorer,
    EvidenceDiversityScorer,
    GraphConnectivityScorer,
    HistoricalSupportScorer,
    RuleSupportScorer,
    StatisticalSupportScorer,
    TemporalSupportScorer,
)
from causalog.core.aggregation import (
    CONTRADICTION_CEILING_ANCHORS,
    TEMPORAL_CEILING_ANCHORS,
    V2_ADDEND_WEIGHTS,
    aggregate,
    ceiling_at,
)
from causalog.core.errors import ContractViolationError
from causalog.core.provenance import ProvenanceClass
from causalog.core.run import OutputEnvelope
from causalog.core.types import CandidateEdge, ConfidenceComponent, Event

__all__ = [
    "CONFIDENCE_AGGREGATOR",
    "SCORER_COUNT",
    "ScoringResult",
    "score_candidates",
]

#: The strategy module 10 uses. Recorded in every vector's `aggregation` field either way,
#: so a later change of default cannot silently reinterpret an artifact already written.
CONFIDENCE_AGGREGATOR = "gated_weighted_mean_v1"

#: How many components every edge carries. Eight, always, on every edge, with no exception:
#: a vector with seven means a scorer was skipped, which is the defect this module is built
#: to make impossible.
SCORER_COUNT = 8


class ScoringResult(BaseModel):
    """The module's whole output: the graph, the divergences, and the report over both."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    graph: CausalGraph
    payload_divergences: tuple[PayloadDivergence, ...]
    report: ConfidenceReport


def score_candidates(
    candidates: tuple[CandidateEdge, ...],
    context: ScoringContext,
    envelope: OutputEnvelope,
    confounding_flags: tuple[ConfoundingFlag, ...] = (),
) -> ScoringResult:
    """Score every candidate module 9 produced and build the causal graph over them.

    `confounding_flags` is accepted here as well as on the context so that a caller wiring
    module 9's `GenerationResult` straight through does not have to rebuild the context;
    when both are supplied the context's value wins, because that is the one the scorers
    read.

    Raises:
        ContractViolationError: if a scorer returned a component set that is not the
            declared eight. Raised rather than reported: a vector missing a component would
            be accepted by `ConfidenceVector` and would silently change every score.
    """
    claims, divergences = fuse_candidates(candidates)
    events_by_id = context.events_by_id()
    if not context.confounding_flags and confounding_flags:
        context = context.model_copy(update={"confounding_flags": confounding_flags})

    scorers = _assemble_scorers(claims, context)
    edges: list[ScoredEdge] = []
    for claim in claims:
        edges.append(_score_one(claim, context, events_by_id, scorers))

    graph = CausalGraph(
        run_id=context.run_id,
        edges=tuple(sorted(edges, key=lambda item: item.sort_key())),
        claims_scored=len(claims),
    )
    report = _build_report(graph, context, envelope, candidates, divergences)
    return ScoringResult(graph=graph, payload_divergences=divergences, report=report)


def _assemble_scorers(
    claims: tuple[FusedClaim, ...], context: ScoringContext
) -> tuple[ComponentScorer, ...]:
    """Return the eight scorers, with diversity told what this run could actually reach.

    The reachable spread is measured from the run rather than read from the enums, so a run
    in which several generators were `NOT_RUNNABLE` is not permanently capped below a
    diversity nothing in it could have produced.
    """
    reachable_kinds = len({item.kind for claim in claims for item in claim.evidence()})
    reachable_generators = len(
        {candidate.generator_id for claim in claims for candidate in claim.candidates}
    )
    return (
        ContradictionFreedomScorer(),
        EvidenceCountScorer(),
        EvidenceDiversityScorer(reachable_kinds, reachable_generators),
        GraphConnectivityScorer(),
        HistoricalSupportScorer(),
        RuleSupportScorer(),
        StatisticalSupportScorer(),
        TemporalSupportScorer(),
    )


def _score_one(
    claim: FusedClaim,
    context: ScoringContext,
    events_by_id: dict[str, Event],
    scorers: tuple[ComponentScorer, ...],
) -> ScoredEdge:
    """Score one fused claim into one `ScoredEdge`."""
    scored: list[ScoredComponent] = [
        scorer.score(claim, context, events_by_id) for scorer in scorers
    ]
    if len({item.component_name for item in scored}) != SCORER_COUNT:
        raise ContractViolationError(
            f"The confidence scorer produced {len(scored)} component(s) under "
            f"{len({item.component_name for item in scored})} distinct name(s) for "
            f"{claim.source_event_id} -> {claim.target_event_id}; every edge carries "
            f"exactly {SCORER_COUNT}. A vector short a component is accepted by "
            "ConfidenceVector and silently changes every score (LAW-EVIDENCE)."
        )
    scored.sort(key=lambda item: item.component_name)

    vector = aggregate(
        [
            ConfidenceComponent(
                component_name=item.component_name,
                value=item.value,
                provenance_class=item.provenance_class,
                evidence_record_ids=item.evidence_record_ids,
            )
            for item in scored
        ],
        CONFIDENCE_AGGREGATOR,
    )
    values = {item.component_name: item.value for item in scored}
    ungated_mean = sum(weight * values[name] for name, weight in V2_ADDEND_WEIGHTS.items()) / sum(
        V2_ADDEND_WEIGHTS.values()
    )
    binding_gate = _binding_gate(values, ungated_mean)

    measured = sum(1 for item in scored if not item.explanation.missing)
    floor = context.parameters.minimum_scored_components
    outcome = (
        ScoringOutcome.INSUFFICIENT_EVIDENCE
        if floor is not None and measured < floor
        else ScoringOutcome.SCORED
    )
    band = band_for(vector.scalar, outcome, context.parameters)

    source = events_by_id[claim.source_event_id]
    target = events_by_id[claim.target_event_id]
    provenance = _promotion_class(claim, outcome, band, context)

    from causalog.core.types import CausalEdge  # local: keeps the module's import list flat

    edge = CausalEdge.between(
        source_event=source,
        target_event=target,
        payload=claim.payload,
        confidence=vector,
        evidence=claim.evidence(),
        # The scalar, deliberately. prd.md §25 lists propagation weight as an edge field
        # and §49 lists confidence as components; deriving the weight from the vector keeps
        # one number in one home rather than two free to disagree (docs/contracts.md §5).
        propagation_weight=vector.scalar,
        provenance_class=provenance,
        run_id=context.run_id,
    )
    return ScoredEdge(
        edge=edge,
        explanations=tuple(item.explanation for item in scored),
        outcome=outcome,
        band_name=band.name if band is not None else None,
        band_plain_language=band.plain_language if band is not None else None,
        scored_component_count=measured,
        binding_gate=binding_gate,
        ungated_mean=min(1.0, max(0.0, ungated_mean)),
    )


def _binding_gate(values: dict[str, float], ungated_mean: float) -> str | None:
    """Return which gate held the scalar below the addend mean, or None if neither did.

    Reported per edge and tallied in the report, because "the temporal gate bound on 98% of
    edges" is a finding about the DATASET that no single edge's score can express.
    """
    temporal = ceiling_at(values["temporal_support"], TEMPORAL_CEILING_ANCHORS)
    contradiction = ceiling_at(values["contradiction_freedom"], CONTRADICTION_CEILING_ANCHORS)
    lowest = min(ungated_mean, temporal, contradiction)
    if lowest >= ungated_mean:
        return None
    return "temporal_support" if temporal <= contradiction else "contradiction_freedom"


def _promotion_class(
    claim: FusedClaim,
    outcome: ScoringOutcome,
    band: object | None,
    context: ScoringContext,
) -> ProvenanceClass:
    """Return the weakest provenance class this claim's evidence supports.

    **This module no longer promotes (ADR-0054).** It once read the pack's
    `confidence_scoring.promotion_band` and returned `INFERRED` when three conditions held.
    Promotion moved to `causal_engine.causal_graph_builder`, which owns an explicit
    per-edge-kind selection policy; leaving a second promotion path here would have meant
    two modules deciding what the engine asserts, which is the defect ADR-0053 was written
    to prevent, one module later.

    What remains is the fallback that was always here: `STATISTICAL` if any evidence item is
    statistical, else `ASSUMED`. Exactly what module 9's gate assigns, and never `OBSERVED`
    -- causation is never read from a record (LAW-PROVENANCE, ADR-0020).

    **The three conditions did not disappear**; they moved with the decision.
    `causal_graph_builder.policy.decide` checks all three and reports each one distinctly,
    and it additionally re-verifies LAW-TIME against the `Event` intervals rather than
    against `claim.admits_promotion()`, which reads fields copied forward from module 9.

    The parameters `outcome`, `band` and `context` are retained in the signature so that the
    move is visible as a behaviour change at this exact site rather than as a refactor that
    removed a function. `confidence_scoring.promotion_band` is deprecated and the rule-pack
    loader warns about it.
    """
    del outcome, band, context  # read by causal_graph_builder.policy.decide since ADR-0054
    return (
        ProvenanceClass.STATISTICAL
        if any(item.provenance_class is ProvenanceClass.STATISTICAL for item in claim.evidence())
        else ProvenanceClass.ASSUMED
    )


def _build_report(
    graph: CausalGraph,
    context: ScoringContext,
    envelope: OutputEnvelope,
    candidates: tuple[CandidateEdge, ...],
    divergences: tuple[PayloadDivergence, ...],
) -> ConfidenceReport:
    """Assemble the calibration report over a scored graph."""
    tallies: list[ComponentTally] = []
    names = sorted({item.component_name for edge in graph.edges for item in edge.explanations})
    for name in names:
        values: list[float] = []
        missing = 0
        requirement: str | None = None
        for edge in graph.edges:
            for explanation in edge.explanations:
                if explanation.component_name != name:
                    continue
                if explanation.missing:
                    missing += 1
                    requirement = requirement or explanation.requirement
                for component in edge.edge.confidence.components:
                    if component.component_name == name:
                        values.append(component.value)
        tallies.append(ComponentTally.of(name, tuple(values), missing, requirement))

    gates: dict[str, int] = {}
    for edge in graph.edges:
        key = edge.binding_gate or "none"
        gates[key] = gates.get(key, 0) + 1

    bands: dict[str, int] = {}
    for edge in graph.scored_edges():
        key = edge.band_name or "unbanded"
        bands[key] = bands.get(key, 0) + 1

    scalars = [edge.edge.confidence.scalar for edge in graph.edges]
    peak = max(scalars) if scalars else 0.0

    measured: dict[int, int] = {}
    for edge in graph.edges:
        measured[edge.scored_component_count] = measured.get(edge.scored_component_count, 0) + 1

    # Counted off the explanations rather than recomputed from the index, so the number
    # reports what the scorer ACTUALLY did. Recomputing here would let the two drift and the
    # report would then describe a scoring that did not happen.
    capped = sum(
        1
        for edge in graph.edges
        for explanation in edge.explanations
        if explanation.component_name == "temporal_support"
        and any(label == "derivation check" for label, _value in explanation.inputs)
    )
    index = context.derived_precedence

    return ConfidenceReport(
        envelope=envelope,
        aggregation=CONFIDENCE_AGGREGATOR,
        candidates_read=len(candidates),
        claims_scored=len(graph.edges),
        scored_count=len(graph.scored_edges()),
        insufficient_count=len(graph.insufficient_edges()),
        promoted_count=len(graph.promoted_edges()),
        components=tuple(tallies),
        distribution=ScalarDistribution.of(
            tuple(edge.edge.confidence.scalar for edge in graph.edges)
        ),
        bands_declared=tuple(
            (band.name, band.minimum_scalar, band.plain_language)
            for band in context.parameters.bands_high_to_low()
        ),
        band_counts=tuple(sorted(bands.items())),
        gate_binding_counts=tuple(sorted(gates.items())),
        payload_divergences=divergences,
        measured_component_histogram=tuple(sorted(measured.items())),
        highest_scoring=graph.highest_scoring(10),
        minimum_scored_components=context.parameters.minimum_scored_components,
        edges_at_maximum=sum(1 for value in scalars if value == peak),
        derived_precedence=DerivedPrecedenceAudit(
            supplied=index is not None,
            checks_confirmed=0 if index is None else len(index.entries),
            pairs_capped=capped,
        ),
    )
