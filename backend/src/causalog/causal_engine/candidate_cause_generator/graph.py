"""`CandidateGraph` -- the multigraph, and the explosion control that bounds it.

THE MULTIGRAPH
--------------
Parallel edges between one pair of events are RETAINED SEPARATELY, one per generator, each
with its own evidence. Two generators reaching the same pair by different reasoning is the
most informative thing this module can report -- it is exactly what module 10 needs to
assemble a decomposed confidence vector from -- and merging them would destroy it, leaving
one edge whose evidence tuple no longer says which line of reasoning contributed what.

The key is `(source_event_id, target_event_id, edge_kind, generator_id)`.
`docs/architecture.md` §Module 9 names the first three; `generator_id` extends it because
the first three cannot separate parallel proposals.

EXPLOSION CONTROL, AND WHY THE POLICY IS WHAT IT IS
---------------------------------------------------
Without a bound, a single effect in a dense timeline can attract a candidate from every
generator for every prior event. `per_effect_candidate_cap` bounds it, and the selection
policy is **round-robin across generators in canonical `generator_id` sequence**, then
within a generator by `(source_event_id, edge_kind)`.

That policy is chosen for what it REFUSES to do. Every intuitive alternative --
closest-in-time first, highest evidence strength first, most generators agreeing first --
ranks candidates by plausibility, and ranking is module 10's and module 11's job. A cap that
selects by plausibility is a module that prunes on "seems unlikely" while claiming not to,
and the resulting graph would silently encode a judgement nobody declared. Round-robin is
fair allocation, not assessment: it starves no generator, it is fully determined by the
canonical sequence, and it makes no claim about which survivors are better.

NOTHING IS EVER SILENTLY DROPPED
--------------------------------
Every truncation emits a `TruncationRecord` naming the effect, the cap, what survived and
what was dropped **per generator**. `CandidateGraph` asserts its own arithmetic on
construction: admitted == retained + truncated. A graph whose numbers disagree with itself
raises rather than being published, which is the treatment module 1 already gives
`rows_read == rows_clean + rows_quarantined` (`CONTEXT.md` R-04).
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalog.causal_engine.candidate_cause_generator.gate import RejectionReason
from causalog.core.errors import ContractViolationError
from causalog.core.temporal import TemporalVerdict
from causalog.core.types import CandidateEdge

__all__ = [
    "SAMPLED_REJECTIONS",
    "CandidateGraph",
    "RejectedProposal",
    "TruncationRecord",
    "apply_per_effect_cap",
]


class TruncationRecord(BaseModel):
    """What one effect event lost to the cap, and to which generators it belonged.

    Per generator rather than a single total, because the question a reader asks after
    seeing a truncation is "did this cost me my rule-based candidates, or only my
    proximity ones?" -- and a single number cannot answer it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    effect_event_id: str
    cap: int
    proposed_count: int
    retained_count: int
    #: (generator_id, dropped_count), sorted by generator_id. Only generators that actually
    #: lost a candidate appear, so a reader is not made to scan a row of zeroes.
    dropped_by_generator: tuple[tuple[str, int], ...]

    @property
    def dropped_count(self) -> int:
        """Return every dropped candidate for this effect, summed."""
        return sum(count for _, count in self.dropped_by_generator)

    @model_validator(mode="after")
    def _check_arithmetic(self) -> TruncationRecord:
        """Refuse a record whose own numbers disagree."""
        if self.retained_count + self.dropped_count != self.proposed_count:
            raise ContractViolationError(
                f"TruncationRecord for {self.effect_event_id} does not reconcile: "
                f"retained {self.retained_count} + dropped {self.dropped_count} != "
                f"proposed {self.proposed_count}. A truncation report whose arithmetic "
                "disagrees with itself is worse than no report, because it will be read."
            )
        return self


def apply_per_effect_cap(
    candidates: tuple[CandidateEdge, ...], cap: int | None
) -> tuple[tuple[CandidateEdge, ...], tuple[TruncationRecord, ...], tuple[CandidateEdge, ...]]:
    """Return the retained candidates, a record per truncated effect, and what was dropped.

    `cap is None` means the pack declared no bound, and every candidate is retained. That
    is a legitimate declaration for a small dataset, and it produces no truncation records
    because nothing was truncated -- distinct from a cap so high it never binds, which
    would also produce none.

    The third member returns the dropped EDGES rather than a projection of them. A cap
    rejection is the commonest rejection this module makes, and the caller is the one that
    knows what it needs to keep -- handing back counts, as this function used to, forced
    the lossy decision here where the information no longer exists.
    """
    if cap is None:
        return tuple(sorted(candidates, key=lambda item: item.sort_key())), (), ()

    by_effect: dict[str, list[CandidateEdge]] = {}
    for candidate in candidates:
        by_effect.setdefault(candidate.target_event_id, []).append(candidate)

    retained: list[CandidateEdge] = []
    records: list[TruncationRecord] = []
    dropped_edges: list[CandidateEdge] = []
    for effect_id in sorted(by_effect):
        group = sorted(by_effect[effect_id], key=lambda item: item.sort_key())
        if len(group) <= cap:
            retained.extend(group)
            continue

        # Round-robin: one per generator in canonical sequence, repeatedly, until the cap
        # is reached. Within a generator, candidates are already in canonical sequence.
        queues: dict[str, list[CandidateEdge]] = {}
        for candidate in group:
            queues.setdefault(candidate.generator_id, []).append(candidate)
        generator_ids = sorted(queues)
        kept: list[CandidateEdge] = []
        cursor = 0
        while len(kept) < cap:
            progressed = False
            for generator_id in generator_ids:
                if len(kept) >= cap:
                    break
                queue = queues[generator_id]
                if cursor < len(queue):
                    kept.append(queue[cursor])
                    progressed = True
            if not progressed:
                break
            cursor += 1

        kept_ids = {candidate.candidate_edge_id for candidate in kept}
        dropped: dict[str, int] = {}
        for candidate in group:
            if candidate.candidate_edge_id not in kept_ids:
                dropped[candidate.generator_id] = dropped.get(candidate.generator_id, 0) + 1
                dropped_edges.append(candidate)
        retained.extend(sorted(kept, key=lambda item: item.sort_key()))
        records.append(
            TruncationRecord(
                effect_event_id=effect_id,
                cap=cap,
                proposed_count=len(group),
                retained_count=len(kept),
                dropped_by_generator=tuple(sorted(dropped.items())),
            )
        )
    return (
        tuple(sorted(retained, key=lambda item: item.sort_key())),
        tuple(records),
        tuple(sorted(dropped_edges, key=lambda item: item.sort_key())),
    )


#: How many individual rejections a `CandidateGraph` carries before the tail is elided.
#:
#: MEASURED, NOT GUESSED. The 150-row reference slice retains 17,864 candidates and rejects
#: 143,145 -- eight times the graph, of which 133,835 are cap truncations. Retaining those in
#: full would make the rejections the largest object in the module several times over, on
#: a slice of 150 rows out of 180,519. The complete COUNTS are kept regardless
#: (`rejection_total`, `rejections_per_effect`); it is the individual records that are
#: bounded, exactly as `SAMPLED_CONFOUNDING_FLAGS` bounds a larger population next door.
SAMPLED_REJECTIONS: Final[int] = 500


class RejectedProposal(BaseModel):
    """One claim the gate or the cap refused, and which effect it was refused for.

    Deliberately four scalar fields. The evidence and payload behind a refused proposal are
    not carried: at the volumes above that would be the whole candidate graph again in a
    field named for what is not in it, and the question this record exists to answer --
    "what was rejected for this effect, and why?" -- needs neither.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    cause_event_id: str = Field(min_length=1)
    effect_event_id: str = Field(min_length=1)
    generator_id: str = Field(min_length=1)
    reason: RejectionReason

    def sort_key(self) -> tuple[str, str, str, str]:
        """Return the canonical sequence key, effect first.

        Effect first because that is the axis this record is read along: every rejection for
        one effect sits together, so a reader answering "why was nothing kept here?" reads a
        run rather than a scatter.
        """
        return (
            self.effect_event_id,
            self.cause_event_id,
            self.generator_id,
            self.reason.value,
        )


class CandidateGraph(BaseModel):
    """Every retained candidate, sequenced canonically, with what the capping cost.

    Not a graph object with traversal methods -- a value. Traversal belongs to modules 11
    and 12, which have a scored graph to traverse; giving this one a `neighbours()` would
    invite inference over unscored hypotheses, which is the boundary F6 exists to hold.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1)
    candidates: tuple[CandidateEdge, ...]
    truncations: tuple[TruncationRecord, ...]
    #: Candidates the gate admitted, before the cap. `admitted == len(candidates) + dropped`.
    admitted_count: int
    #: A BOUNDED sample of the individual rejections, sequenced canonically. Read
    #: `rejection_total` beside it: this tuple is not the population, and `SAMPLED_REJECTIONS`
    #: says why.
    rejections: tuple[RejectedProposal, ...] = ()
    #: Every rejection that named an effect, counted in full whatever the sample holds.
    rejection_total: int = 0
    #: `(effect_event_id, rejection count)` over the COMPLETE set, sorted. Stored rather
    #: than derived from `rejections`: a per-effect count computed off a bounded sample
    #: would be a partial number in the shape of a total, which is worse than no number.
    rejections_per_effect: tuple[tuple[str, int], ...] = ()

    @model_validator(mode="after")
    def _check_arithmetic(self) -> CandidateGraph:
        """Refuse a graph whose totals disagree, and one that is unsequenced.

        Both are checked rather than trusted, for the reason module 1 checks
        `rows_read == rows_clean + rows_quarantined`: a report is read as authoritative,
        and one that quietly loses candidates between two of its own numbers is worse than
        no report at all.
        """
        keys = [candidate.sort_key() for candidate in self.candidates]
        if keys != sorted(keys):
            raise ContractViolationError(
                "CandidateGraph.candidates is unsequenced; a multigraph serialized in two "
                "sequences produces two hashes for one run (CONVENTIONS.md §11)."
            )
        if len(set(keys)) != len(keys):
            raise ContractViolationError(
                "CandidateGraph holds two candidates under one "
                "(source, target, edge_kind, generator) key. Parallel edges are retained "
                "per GENERATOR; two from one generator over one pair and kind is a "
                "duplicate, not a parallel edge."
            )
        dropped = sum(record.dropped_count for record in self.truncations)
        if len(self.candidates) + dropped != self.admitted_count:
            raise ContractViolationError(
                f"CandidateGraph does not reconcile: retained {len(self.candidates)} + "
                f"truncated {dropped} != admitted {self.admitted_count}."
            )
        rejection_keys = [item.sort_key() for item in self.rejections]
        if rejection_keys != sorted(rejection_keys):
            raise ContractViolationError(
                "CandidateGraph.rejections is unsequenced (CONVENTIONS.md §11)."
            )
        # No uniqueness check, deliberately. One generator may propose the same pair twice
        # with DIFFERENT payloads -- `_merge_identical_proposals` merges only identical ones
        # -- and both may be refused for one reason. A uniqueness validator here would raise
        # on legitimate data.
        for rejection in self.rejections:
            if rejection.reason is RejectionReason.GENERATOR_NOT_RUNNABLE:
                raise ContractViolationError(
                    "CandidateGraph.rejections holds a GENERATOR_NOT_RUNNABLE record. That "
                    "reason is recorded when a generator never ran, so there was no "
                    "proposal and no effect to name; a record claiming otherwise invents "
                    "an instance. It stays a per-generator count."
                )
        if len(self.rejections) > SAMPLED_REJECTIONS:
            raise ContractViolationError(
                f"CandidateGraph carries {len(self.rejections)} rejection records against a "
                f"declared bound of {SAMPLED_REJECTIONS}."
            )
        if self.rejection_total < len(self.rejections):
            raise ContractViolationError(
                f"CandidateGraph reports {self.rejection_total} rejections and carries "
                f"{len(self.rejections)}; the total may exceed the sample, never trail it."
            )
        per_effect = [effect for effect, _count in self.rejections_per_effect]
        if per_effect != sorted(per_effect):
            raise ContractViolationError(
                "CandidateGraph.rejections_per_effect is unsequenced (CONVENTIONS.md §11)."
            )
        if sum(count for _effect, count in self.rejections_per_effect) != self.rejection_total:
            raise ContractViolationError(
                "CandidateGraph.rejections_per_effect does not sum to rejection_total; the "
                "per-effect breakdown must be complete, not a tally of the sample."
            )
        # Indexed, not scanned. A nested walk of two collections that both scale with the
        # candidate graph is quadratic, and this validator runs on every construction: at
        # the 20,000-row default it would be the slowest thing in the module by far.
        counted = dict(self.rejections_per_effect)
        for record in self.truncations:
            if counted.get(record.effect_event_id, 0) < record.dropped_count:
                raise ContractViolationError(
                    f"CandidateGraph says {record.dropped_count} candidate(s) were dropped "
                    f"for effect {record.effect_event_id} and records "
                    f"{counted.get(record.effect_event_id, 0)} rejection(s) against it. "
                    "The two ledgers count one event and must agree."
                )
        for candidate in self.candidates:
            if candidate.run_id != self.run_id:
                raise ContractViolationError(
                    f"CandidateGraph is scoped to run {self.run_id} and holds a candidate "
                    f"scoped to {candidate.run_id}; mixing runs would let one run's "
                    "inference read as another's (ADR-0013)."
                )
        return self

    def unverifiable_candidates(self) -> tuple[CandidateEdge, ...]:
        """Return candidates resting on an interval the source never placed."""
        return tuple(item for item in self.candidates if item.temporally_unverifiable)

    def undetermined_candidates(self) -> tuple[CandidateEdge, ...]:
        """Return candidates the data placed but could not separate.

        Deliberately excludes the unverifiable ones. They are a different finding
        (`docs/contracts.md` §3) and summing the two would hide which one a run hit.
        """
        return tuple(
            item
            for item in self.candidates
            if item.temporal_verdict is TemporalVerdict.UNDETERMINED
            and not item.temporally_unverifiable
        )

    def rejections_for_effect(self, effect_event_id: str) -> tuple[RejectedProposal, ...]:
        """Return the sampled rejections recorded against one effect event.

        **From the SAMPLE.** Where `rejection_total` exceeds `SAMPLED_REJECTIONS` this
        returns some of an effect's rejections rather than all of them, and an empty result
        does not prove an effect was never rejected for. The complete count per effect is in
        `rejections_per_effect`; consult it before concluding anything from what is missing
        here.
        """
        return tuple(item for item in self.rejections if item.effect_event_id == effect_event_id)

    def candidates_per_effect(self) -> tuple[tuple[str, int], ...]:
        """Return (effect_event_id, candidate count), sorted by effect identifier."""
        counted: dict[str, int] = {}
        for candidate in self.candidates:
            counted[candidate.target_event_id] = counted.get(candidate.target_event_id, 0) + 1
        return tuple(sorted(counted.items()))
