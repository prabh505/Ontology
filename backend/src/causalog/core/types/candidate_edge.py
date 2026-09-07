"""`CandidateEdge` -- a PROPOSED cause/effect pair, before anyone has judged it.

prd.md §27: "The engine should initially construct a candidate graph rather than assuming
certainty. Candidate causes are ranked later." This type is that sentence expressed as a
type. It is what module 9 emits and what module 10 consumes.

Why this is not `CausalEdge`
----------------------------
`CausalEdge` requires a `ConfidenceVector`, and module 9 is forbidden from assigning one
(`docs/architecture.md` §Module 9). Reusing it would force the generator to invent a
placeholder judgement, and a placeholder is indistinguishable downstream from a real one --
which is the precise conflation the generation/judgment split exists to prevent.

So the separation is structural rather than procedural: **there is no field here that could
hold a judgement.** A generator cannot score, because the artifact it produces has nowhere
to put a score. `CausalEdge` is unchanged, still frozen, and is constructed by module 10
from these (`docs/contracts.md`).

The five-payload union IS reused, deliberately. One taxonomy for the five prd.md §26
categories, not a second, weaker one made of strings -- the same argument ADR-0022 makes
about `CausalEdgePayload` applies unchanged one layer earlier.

LAW-TIME is enforced here, at construction. See `CandidateEdge.between`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from causalog.core.errors import ContractViolationError, LawViolationError
from causalog.core.identifiers import (
    IdentifierPrefix,
    canonical_payload,
    canonical_text,
    digest,
)
from causalog.core.provenance import ProvenanceClass
from causalog.core.serialization import to_canonical_json
from causalog.core.temporal import TemporalVerdict, is_unverifiable, verdict
from causalog.core.types.causal_edge import CausalEdgeKind, CausalEdgePayload
from causalog.core.types.event import Event
from causalog.core.types.evidence import EvidenceItem

__all__ = ["CandidateEdge"]


class CandidateEdge(BaseModel):
    """One generator's proposal that one event may have produced another.

    A hypothesis with its reasoning attached. Never a conclusion: nothing here ranks it,
    scores it, or claims it is true, and the type carries no field that could.

    Construct with `CandidateEdge.between`, which is the only path that can evaluate
    LAW-TIME. Direct construction and `model_validate` remain available for
    deserialization and are guarded by the same invariants.

    **What that does and does not buy.** The invariants below re-run on every path, so a
    stored `VIOLATION` verdict is refused on the way back in. They cannot verify the
    verdict itself: this artifact stores identifiers, not the two intervals, so nothing
    inside it can recompute `verdict(...)`. This is the identical boundary `CausalEdge`
    documents under DEF-0002, restated rather than quietly inherited -- closing it means
    putting the intervals into the artifact, which is an ADR, not an edit.

    `generator_id` is part of the identity, not a label beside it. The candidate graph is a
    **multigraph**: two generators proposing the same pair are two proposals with two
    independent evidence trails, and collapsing them into one edge would destroy the fact
    that two unrelated lines of reasoning arrived at the same place -- which is exactly the
    thing module 10 needs to see.

    Invariants:
      * `temporal_verdict` is never `VIOLATION` (LAW-TIME). A pair whose cause cannot
        precede its effect is not stored with a warning flag; it does not exist.
      * `provenance_class` is never `OBSERVED`. Causation is never read from a source
        record (LAW-PROVENANCE, ADR-0020).
      * `provenance_class == INFERRED` requires `temporal_verdict == CERTAIN` and
        `temporally_unverifiable is False` (ADR-0007, `CONVENTIONS.md` §10).
      * `evidence` is non-empty (LAW-EVIDENCE).
      * `source_event_id != target_event_id`. An event does not cause itself.
      * `generator_id` is non-empty. A proposal whose origin nobody recorded cannot be
        counted in the per-generator report, and a generator that produces everything or
        nothing is only visible in that report.
      * `run_id` is present. Every inferred artifact is run-scoped (ADR-0013).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_edge_id: str
    generator_id: str
    source_event_id: str
    target_event_id: str
    payload: CausalEdgePayload
    evidence: tuple[EvidenceItem, ...]
    provenance_class: ProvenanceClass
    temporal_verdict: TemporalVerdict
    temporally_unverifiable: bool
    run_id: str

    @property
    def edge_kind(self) -> CausalEdgeKind:
        """Return the edge kind, read from the payload so the two cannot disagree."""
        return self.payload.edge_kind

    @property
    def admits_promotion(self) -> bool:
        """Return whether LAW-TIME permits this candidate to ever become `INFERRED`.

        A convenience for module 10 and for the run report. It reads the two temporal
        fields and nothing else -- it is not a judgement about the candidate's merit, and
        a `True` here says only that time does not block promotion.
        """
        return self.temporal_verdict is TemporalVerdict.CERTAIN and not self.temporally_unverifiable

    def sort_key(self) -> tuple[str, str, str, str]:
        """Return the canonical sequence key (`CONVENTIONS.md` §11).

        `(source_event_id, target_event_id, edge_kind, generator_id)` --
        `docs/architecture.md` §Module 9 names the first three, and `generator_id` extends
        it because the multigraph admits parallel edges the first three cannot separate.
        """
        return (
            self.source_event_id,
            self.target_event_id,
            self.payload.edge_kind.value,
            self.generator_id,
        )

    @classmethod
    def address(
        cls,
        source_event_id: str,
        target_event_id: str,
        payload: CausalEdgePayload,
        generator_id: str,
    ) -> str:
        """Return the content-addressed identifier for a candidate (`CONVENTIONS.md` §9).

        Payload recipe:
        `source_event_id | target_event_id | edge_type | generator_id | payload`.

        **The generator is in the recipe because it is in the identity.**
        `CausalEdge.address` deliberately omits it, and the two recipes are therefore
        different by design: a candidate is one generator's proposal, whereas a causal edge
        is the single scored claim module 10 assembles from every proposal over that pair.
        Two artifacts with two lifetimes get two addresses.

        **The whole payload participates, not just its kind**, and that is not decorative.
        `CausalEdge.address` uses the kind alone, which is right for it: module 10 emits one
        scored edge per (pair, kind). It is wrong here, because one generator legitimately
        reaches one pair twice with two different claims -- two rules both proposing
        `DIRECT`, or two `CONDITIONAL` claims qualified by different conditions, or two
        `CONTRIBUTING` claims in different joint groups. Under a kind-only recipe those
        collide on one address, and a multigraph that silently merges two distinct claims
        has lost exactly the thing it exists to keep. Two proposals with an IDENTICAL
        payload are genuinely one hypothesis with two justifications, and they are merged
        into one candidate carrying both evidence items -- which is what an equal address
        should mean.
        """
        return digest(
            IdentifierPrefix.CANDIDATE_EDGE,
            canonical_payload(
                canonical_text(source_event_id),
                canonical_text(target_event_id),
                canonical_text(payload.edge_kind.value),
                canonical_text(generator_id),
                canonical_text(to_canonical_json(payload)),
            ),
        )

    @classmethod
    def between(
        cls,
        *,
        source_event: Event,
        target_event: Event,
        generator_id: str,
        payload: CausalEdgePayload,
        evidence: tuple[EvidenceItem, ...],
        provenance_class: ProvenanceClass,
        run_id: str,
    ) -> CandidateEdge:
        """Build a candidate between two events, enforcing LAW-TIME.

        This is the only constructor that sees both intervals, and therefore the only one
        that can evaluate LAW-TIME. It takes the `Event` objects rather than their
        identifiers for exactly that reason: a candidate built from identifiers alone could
        not check the law, and a check that cannot run is indistinguishable from one that
        passes.

        The verdict and the unverifiability flag are computed here and stamped on; they are
        never supplied by the caller. A caller who could pass `temporal_verdict=CERTAIN`
        could launder a rejected pair into the graph.

        **There is no escape hatch and no `skip_law_time` argument.** A `VIOLATION` raises.
        The only accommodation for absent time is `temporally_unverifiable`, which is a
        distinct recorded state, not a silent pass: such a candidate is retained, is
        counted in the run report, and is barred from `INFERRED` by the invariant below.

        `temporally_unverifiable` is deliberately separate from the verdict.
        `UNDETERMINED` means the data placed both events and could not separate them;
        `temporally_unverifiable` means the data never placed one of them. Both block
        promotion, but they are different findings about the dataset, and collapsing them
        would hide which one the run actually hit.

        Raises:
            LawViolationError: if the cause cannot precede the effect. Never repaired,
                never skipped, never downgraded to a flag.
        """
        temporal_verdict = verdict(source_event.occurred_at, target_event.occurred_at)
        if temporal_verdict is TemporalVerdict.VIOLATION:
            raise LawViolationError(
                "LAW-TIME: refusing to construct a candidate edge from "
                f"{source_event.event_id} to {target_event.event_id}; the cause interval "
                "does not precede the effect interval "
                f"({source_event.occurred_at.t_earliest.isoformat()} >= "
                f"{target_event.occurred_at.t_latest.isoformat()}). A temporally invalid "
                "pair is rejected at construction and never created (CONVENTIONS.md §10)."
            )
        return cls(
            candidate_edge_id=cls.address(
                source_event.event_id,
                target_event.event_id,
                payload,
                generator_id,
            ),
            generator_id=generator_id,
            source_event_id=source_event.event_id,
            target_event_id=target_event.event_id,
            payload=payload,
            evidence=evidence,
            provenance_class=provenance_class,
            temporal_verdict=temporal_verdict,
            temporally_unverifiable=(
                is_unverifiable(source_event.occurred_at)
                or is_unverifiable(target_event.occurred_at)
            ),
            run_id=run_id,
        )

    @model_validator(mode="after")
    def _check_invariants(self) -> CandidateEdge:
        """Enforce the documented invariants on every construction path.

        This runs for `model_validate` too, which is the point: the guarantee has to hold
        for deserialized data, or a rejected pair could be reintroduced by writing it to
        disk and reading it back.
        """
        if self.temporal_verdict is TemporalVerdict.VIOLATION:
            raise LawViolationError(
                "LAW-TIME: a CandidateEdge may never carry the VIOLATION verdict. Such a "
                "pair is rejected at construction and never created (CONVENTIONS.md §10)."
            )
        if self.source_event_id == self.target_event_id:
            raise ContractViolationError(
                f"CandidateEdge source and target are both {self.source_event_id}; an "
                "event does not cause itself."
            )
        if self.provenance_class is ProvenanceClass.OBSERVED:
            raise LawViolationError(
                "CandidateEdge may not carry OBSERVED provenance; causation is proposed, "
                "never read from a source record (LAW-PROVENANCE, ADR-0020)."
            )
        if self.provenance_class is ProvenanceClass.INFERRED and (
            self.temporal_verdict is not TemporalVerdict.CERTAIN or self.temporally_unverifiable
        ):
            raise LawViolationError(
                "CandidateEdge with INFERRED provenance requires a CERTAIN temporal "
                "verdict and verifiable timestamps; a proposal resting on ambiguous or "
                "absent time may be retained but may never be promoted (ADR-0007, "
                "CONVENTIONS.md §10)."
            )
        if not self.evidence:
            raise LawViolationError(
                "CandidateEdge.evidence is empty; a proposal with no inspectable evidence "
                "is a defect (LAW-EVIDENCE)."
            )
        if not self.generator_id.strip():
            raise ContractViolationError(
                "CandidateEdge.generator_id is empty; a proposal whose origin nobody "
                "recorded cannot be counted per generator, and a generator producing "
                "everything or nothing is visible only in that count."
            )
        if not self.run_id.strip():
            raise ContractViolationError(
                "CandidateEdge.run_id is empty; every inferred artifact is run-scoped, "
                "which is what stops it overwriting an observed fact (ADR-0013)."
            )
        return self
