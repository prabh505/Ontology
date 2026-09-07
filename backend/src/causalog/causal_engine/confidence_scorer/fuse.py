"""Multigraph to claim: gathering module 9's parallel proposals into one thing to score.

Module 9 emits one `CandidateEdge` per generator per pair, keyed
`(source, target, edge_kind, generator_id)`. `CausalEdge.address` omits the generator and
keys `(source, target, edge_kind)`. That difference is deliberate on both sides and it makes
this step mandatory: module 10 emits ONE scored edge where module 9 emitted several
proposals, and something has to decide what "several proposals" means.

It means one claim with several justifications -- which is the reading that lets the
confidence vector say how many INDEPENDENT lines of reasoning support it. Any other reading
throws that away: scoring each candidate separately would emit several `CausalEdge` values
colliding on one address, and picking a single "best" candidate would be a ranking made
before any scoring had happened.

TWO CANDIDATES OF ONE KIND WITH DIFFERENT PAYLOAD PARAMETERS
------------------------------------------------------------
`CandidateEdge.address` includes the whole payload; `CausalEdge.address` includes only the
kind. So two `CONDITIONAL` candidates qualified by different conditions are two candidates
and would be one edge. They are fused, and the divergence is REPORTED as a
`PayloadDivergence` rather than averaged or silently resolved by iteration sequence --
averaging two conditions is not a thing that can be done, and picking one is a judgement
about which condition was meant.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from causalog.causal_engine.confidence_scorer.context import FusedClaim
from causalog.core.serialization import to_canonical_json
from causalog.core.types import CandidateEdge

__all__ = ["PayloadDivergence", "fuse_candidates"]


class PayloadDivergence(BaseModel):
    """Two candidates of one kind over one pair whose payload parameters disagree.

    Reported, never resolved. The fused claim takes the first payload in canonical
    sequence, which is deterministic but is not a judgement about which was right -- and
    saying so in the report is the difference between a known limitation and a silent one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_event_id: str
    target_event_id: str
    edge_kind: str
    #: The distinct canonical payload renderings observed, sorted. Two or more by
    #: construction; the first is the one the fused claim carries.
    payloads: tuple[str, ...]
    generator_ids: tuple[str, ...]


def fuse_candidates(
    candidates: tuple[CandidateEdge, ...],
) -> tuple[tuple[FusedClaim, ...], tuple[PayloadDivergence, ...]]:
    """Return one claim per `(source, target, edge_kind)`, and every payload divergence.

    Both results are in canonical sequence. Candidates inside a claim keep module 9's own
    sequence key, so the group a reader sees here is the group module 9's report counted.
    """
    grouped: dict[tuple[str, str, str], list[CandidateEdge]] = {}
    for candidate in candidates:
        key = (
            candidate.source_event_id,
            candidate.target_event_id,
            candidate.payload.edge_kind.value,
        )
        grouped.setdefault(key, []).append(candidate)

    claims: list[FusedClaim] = []
    divergences: list[PayloadDivergence] = []
    for (source_id, target_id, kind), group in sorted(grouped.items()):
        sequenced = tuple(sorted(group, key=lambda item: item.sort_key()))
        renderings = sorted({to_canonical_json(item.payload) for item in sequenced})
        if len(renderings) > 1:
            divergences.append(
                PayloadDivergence(
                    source_event_id=source_id,
                    target_event_id=target_id,
                    edge_kind=kind,
                    payloads=tuple(renderings),
                    generator_ids=tuple(sorted({item.generator_id for item in sequenced})),
                )
            )
        claims.append(
            FusedClaim(
                source_event_id=source_id,
                target_event_id=target_id,
                candidates=sequenced,
            )
        )
    return (
        tuple(sorted(claims, key=lambda claim: claim.sort_key())),
        tuple(divergences),
    )
