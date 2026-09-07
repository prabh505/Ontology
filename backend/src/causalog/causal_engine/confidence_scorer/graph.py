"""`CausalGraph` and `ScoredEdge` -- module 10's output, and the explanation beside it.

`docs/architecture.md` §Module 10 names `CausalGraph` as the output and nothing in the
repository had defined it, because nothing had produced one. This is it.

TWO VALUES, NOT ONE
-------------------
`CausalEdge` is a frozen core type and carries the scored claim: its confidence vector, its
evidence, its provenance, its temporal standing. `ScoredEdge` wraps it with everything the
scoring produced that the frozen type has nowhere to hold -- the per-component explanations,
the outcome, the band, and which gate bound the scalar.

The wrapper exists because the alternatives are worse. Adding fields to `CausalEdge` means
changing a frozen contract for prose that will be reworded (ADR-0025 makes that an ADR, not
an edit). Discarding the explanations means shipping the number without the reasons, which is
the whole thing prd.md §49 forbids. So the audit trail lives in the core type and the
readable account lives beside it, keyed by the same identifier.

**THE SCALAR IS NOT THE GRAPH'S PRECEDENCE.** `edges` is sequenced canonically by identifier,
not by score. Ranking is module 11's, and a graph that arrived pre-sorted by confidence
would have made module 11's job look already done.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalog.causal_engine.confidence_scorer.bands import ScoringOutcome
from causalog.causal_engine.confidence_scorer.explain import ComponentExplanation
from causalog.core.errors import ContractViolationError, LawViolationError
from causalog.core.provenance import ProvenanceClass
from causalog.core.types import CausalEdge

__all__ = ["CausalGraph", "ScoredEdge"]


class ScoredEdge(BaseModel):
    """One scored claim: the edge, why each component holds its value, and the outcome.

    Invariants:
      * `explanations` covers every component in the edge's vector, and nothing else. An
        explained component that is not in the vector, or a component with no explanation,
        both mean a reader is shown a breakdown that does not match the number above it.
      * An `INSUFFICIENT_EVIDENCE` edge carries no band. The two are different findings and
        showing one as the other is the specific confusion this module refuses.
      * An edge carrying `INFERRED` was promoted, and promotion requires the outcome to be
        `SCORED`. A vector mostly made of absence may not become an inference.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    edge: CausalEdge
    #: One per component, sorted by `component_name` to match the vector's own sequence.
    explanations: tuple[ComponentExplanation, ...] = Field(min_length=1)
    outcome: ScoringOutcome
    #: The declared band's name, or None when the outcome is INSUFFICIENT_EVIDENCE or the
    #: pack declares no bands. `bands.BAND_ABSENT_NOTICE` says which.
    band_name: str | None = None
    band_plain_language: str | None = None
    #: How many of the eight components carried real, non-missing support.
    scored_component_count: int
    #: Which gate, if either, held the scalar below the plain weighted mean. `None` means
    #: neither bound and the score is the mean of the addends.
    binding_gate: str | None = None
    #: The unclamped weighted mean of the six addends, kept so a reader can see the size of
    #: what the gate removed. Never displayed as the confidence.
    ungated_mean: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_invariants(self) -> ScoredEdge:
        """Refuse a breakdown that does not match the vector it explains."""
        explained = [item.component_name for item in self.explanations]
        scored = [item.component_name for item in self.edge.confidence.components]
        if explained != sorted(explained):
            raise ContractViolationError(
                "ScoredEdge.explanations is unsequenced; it is rendered beside the vector "
                "and the two must line up by name (CONVENTIONS.md §11)."
            )
        if explained != scored:
            raise LawViolationError(
                f"ScoredEdge for {self.edge.causal_edge_id} explains {explained} but its "
                f"vector holds {scored}. A breakdown that does not match the number above "
                "it is worse than no breakdown, because it will be read as the reason for "
                "that number (LAW-EVIDENCE)."
            )
        if self.outcome is ScoringOutcome.INSUFFICIENT_EVIDENCE and self.band_name is not None:
            raise ContractViolationError(
                f"ScoredEdge for {self.edge.causal_edge_id} is INSUFFICIENT_EVIDENCE and "
                f"carries band '{self.band_name}'. 'We did not measure enough to say' is "
                "not a band, and showing it as one presents an absence of measurement as a "
                "measurement."
            )
        if (
            self.edge.provenance_class is ProvenanceClass.INFERRED
            and self.outcome is not ScoringOutcome.SCORED
        ):
            raise LawViolationError(
                f"ScoredEdge for {self.edge.causal_edge_id} carries INFERRED with outcome "
                f"{self.outcome.value}. An inference standing on a vector that is mostly "
                "absence is an inference standing on nothing (LAW-PROVENANCE)."
            )
        return self

    def sort_key(self) -> tuple[str, str, str]:
        """Return the canonical sequence key (`CONVENTIONS.md` §11)."""
        return (
            self.edge.source_event_id,
            self.edge.target_event_id,
            self.edge.payload.edge_kind.value,
        )


class CausalGraph(BaseModel):
    """Every scored edge from one run, sequenced canonically -- never by score.

    Not a graph object with traversal methods, for the reason `CandidateGraph` is not one:
    traversal belongs to modules 11 and 12, and giving this a `neighbours()` would invite
    ranking here, which is module 11's job and not this one's.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1)
    edges: tuple[ScoredEdge, ...]
    #: Fused claims module 9 proposed, before scoring. `claims == len(edges)` always;
    #: carried so the report can assert it rather than assume it.
    claims_scored: int

    @model_validator(mode="after")
    def _check_arithmetic(self) -> CausalGraph:
        """Refuse a graph that lost an edge between two of its own numbers, or is unsequenced.

        Checked rather than trusted, for the reason module 1 checks
        `rows_read == rows_clean + rows_quarantined` and module 9 checks its own totals: a
        report is read as authoritative, and one whose numbers disagree is worse than none.
        """
        keys = [edge.sort_key() for edge in self.edges]
        if keys != sorted(keys):
            raise ContractViolationError(
                "CausalGraph.edges is unsequenced; a graph serialized in two sequences "
                "produces two hashes for one run (CONVENTIONS.md §11)."
            )
        if len(set(keys)) != len(keys):
            raise ContractViolationError(
                "CausalGraph holds two edges under one (source, target, edge_kind) key. "
                "That is CausalEdge.address's recipe, so the two would collide on one "
                "identifier -- module 9's parallel candidates are fused into one scored "
                "edge precisely to prevent it."
            )
        if len(self.edges) != self.claims_scored:
            raise ContractViolationError(
                f"CausalGraph does not reconcile: {len(self.edges)} edge(s) from "
                f"{self.claims_scored} fused claim(s). Every claim is scored -- an edge "
                "dropped between the two would be a silent judgement."
            )
        for edge in self.edges:
            if edge.edge.run_id != self.run_id:
                raise ContractViolationError(
                    f"CausalGraph is scoped to run {self.run_id} and holds an edge scoped "
                    f"to {edge.edge.run_id}; mixing runs would let one run's inference "
                    "read as another's (ADR-0013)."
                )
        return self

    def scored_edges(self) -> tuple[ScoredEdge, ...]:
        """Return only the edges whose vector carried enough real support to mean anything."""
        return tuple(edge for edge in self.edges if edge.outcome is ScoringOutcome.SCORED)

    def insufficient_edges(self) -> tuple[ScoredEdge, ...]:
        """Return the edges too little was measured on -- NOT the low-scoring ones."""
        return tuple(
            edge for edge in self.edges if edge.outcome is ScoringOutcome.INSUFFICIENT_EVIDENCE
        )

    def promoted_edges(self) -> tuple[ScoredEdge, ...]:
        """Return the edges that reached `INFERRED`."""
        return tuple(
            edge for edge in self.edges if edge.edge.provenance_class is ProvenanceClass.INFERRED
        )

    def highest_scoring(self, count: int) -> tuple[ScoredEdge, ...]:
        """Return the `count` highest-scoring SCORED edges, best first.

        A reporting convenience and explicitly not the graph's sequence: `edges` stays
        canonical. Ties break on the canonical key so two runs produce one list.
        """
        return tuple(
            sorted(
                self.scored_edges(),
                key=lambda edge: (-edge.edge.confidence.scalar, edge.sort_key()),
            )
        )[:count]
