"""The orchestrator: run every generator, gate everything, cap, flag, report.

Sequence, and why it is this sequence:

1. **Ask each generator whether it can run.** A generator missing a declared parameter is
   recorded `NOT_RUNNABLE` and is never invoked, so it cannot report zero by accident.
2. **Collect proposals.** Generators are independent and see only the shared context; none
   holds a reference to another, which is what makes each one testable alone.
3. **Gate everything through `gate_all`.** One chokepoint, LAW-TIME applied there and
   nowhere else. Constraint prohibitions are applied here too, as counted rejections.
4. **Cap per effect.** Round-robin, deterministic, and every drop recorded.
5. **Flag confounding structures** over what survived.
6. **Report** every count, with the three distinctions the report refuses to collapse.

Steps 4 and 5 are in that sequence deliberately: flagging before capping would surface
structures involving candidates that are not in the graph the user receives, and a flag
pointing at an absent edge is worse than no flag.
"""

from __future__ import annotations

import heapq
from collections.abc import Iterator

from pydantic import BaseModel, ConfigDict

from causalog.causal_engine.candidate_cause_generator.confounding import (
    ConfoundingFlag,
    ConfoundingStructure,
    detect_confounding,
)
from causalog.causal_engine.candidate_cause_generator.context import (
    CandidateGenerator,
    GenerationContext,
    GeneratorStatus,
    Proposal,
)
from causalog.causal_engine.candidate_cause_generator.gate import (
    RejectionReason,
    RejectionTally,
    gate_all,
)
from causalog.causal_engine.candidate_cause_generator.generators import ALL_GENERATORS
from causalog.causal_engine.candidate_cause_generator.generators.support import (
    events_of_timeline,
)
from causalog.causal_engine.candidate_cause_generator.graph import (
    SAMPLED_REJECTIONS,
    CandidateGraph,
    RejectedProposal,
    apply_per_effect_cap,
)
from causalog.causal_engine.candidate_cause_generator.report import (
    SAMPLED_CONFOUNDING_FLAGS,
    CandidateGraphReport,
    GeneratorTally,
    PerEffectDistribution,
)
from causalog.core.run import OutputEnvelope
from causalog.core.serialization import to_canonical_json
from causalog.core.types import CandidateEdge

__all__ = ["GenerationResult", "generate_candidates"]


class GenerationResult(BaseModel):
    """The module's whole output: the graph, the flags, and the report over both."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    graph: CandidateGraph
    confounding_flags: tuple[ConfoundingFlag, ...]
    report: CandidateGraphReport

    def candidates(self) -> tuple[CandidateEdge, ...]:
        """Return every retained candidate, in canonical sequence."""
        return self.graph.candidates


def _available_pair_count(context: GenerationContext) -> int:
    """Return the sequenced within-timeline event pairs any generator could reach.

    The denominator `GeneratorTally.looks_degenerate` reads. Counted over timelines rather
    than over the whole event set because every generator here is timeline-scoped -- using
    the global cross product would make every generator look sparse and the saturation
    check would never fire.
    """
    events_by_id = context.events_by_id()
    total = 0
    for timeline in context.timelines:
        held = len(events_of_timeline(timeline, events_by_id))
        total += held * (held - 1)
    return total


def _merge_identical_proposals(proposals: tuple[Proposal, ...]) -> tuple[Proposal, ...]:
    """Fold proposals that make the IDENTICAL claim into one carrying every justification.

    One generator legitimately reaches one pair more than once. Two rules can both propose
    that A produced B directly; the shared-entity generator cannot, but the rule-based one
    does it constantly, because the pack contains several rules over the same sequenced type
    pair -- `R-DCO-DISPATCH-MISS-DELAYS` and `R-DCO-TRANSIT-DELAYS` are authored that way on
    purpose, and the pack says so.

    Those are not two hypotheses. They are one hypothesis with two justifications, and
    LAW-EVIDENCE wants both attached to it rather than one of them silently winning. So they
    are merged on `(cause, effect, generator, payload)` -- the identity `CandidateEdge.address`
    computes -- with their evidence concatenated and sequenced.

    Proposals from one generator whose payloads DIFFER are not merged: two `CONDITIONAL`
    claims qualified by different conditions are two different claims, and they keep two
    addresses because the payload participates in the recipe.

    Evidence is deduplicated by `evidence_item_id`, which is itself content-addressed, so two
    rules producing a byte-identical justification contribute it once.
    """
    merged: dict[tuple[str, str, str, str], Proposal] = {}
    for proposal in proposals:
        key = (
            proposal.cause_event.event_id,
            proposal.effect_event.event_id,
            proposal.generator_id,
            to_canonical_json(proposal.payload),
        )
        existing = merged.get(key)
        if existing is None:
            merged[key] = proposal
            continue
        by_id = {item.evidence_item_id: item for item in (*existing.evidence, *proposal.evidence)}
        merged[key] = existing.model_copy(
            update={"evidence": tuple(by_id[identifier] for identifier in sorted(by_id))}
        )
    return tuple(sorted(merged.values(), key=lambda item: item.sort_key()))


def generate_candidates(
    context: GenerationContext,
    envelope: OutputEnvelope,
    generators: tuple[CandidateGenerator, ...] = ALL_GENERATORS,
    suppressed_pairs: frozenset[tuple[str, str]] = frozenset(),
) -> GenerationResult:
    """Build the candidate graph and the report over it.

    `generators` is injected with the full canonical set as its default, so a test can run
    one generator in isolation without this function knowing which one. `suppressed_pairs`
    carries the `CONSTRAINT` prohibitions the rule engine reported; they arrive as data and
    are refused at the gate, where the refusal is counted under its own reason.

    Raises:
        ContractViolationError: if the graph's own arithmetic does not reconcile. Raised
            rather than reported: a report that has quietly lost candidates between two of
            its own numbers will still be read as authoritative.
    """
    available = _available_pair_count(context)
    proposals: list[Proposal] = []
    tallies: list[GeneratorTally] = []
    statuses: dict[str, GeneratorStatus] = {}

    for generator in sorted(generators, key=lambda item: item.generator_id):
        status = generator.status(context)
        statuses[generator.generator_id] = status
        if status is GeneratorStatus.NOT_RUNNABLE:
            tallies.append(
                GeneratorTally(
                    generator_id=generator.generator_id,
                    status=status,
                    requirement=generator.requirement(),
                    available_pair_count=available,
                    rejections=RejectionTally().with_one(RejectionReason.GENERATOR_NOT_RUNNABLE),
                )
            )
            continue
        produced = generator.propose(context)
        proposals.extend(produced)
        tallies.append(
            GeneratorTally(
                generator_id=generator.generator_id,
                status=status,
                proposed_count=len(produced),
                available_pair_count=available,
            )
        )

    # Merge before gating, not after: two proposals making one claim must reach the gate
    # as one, or the second would be counted as a separate admission and the graph's own
    # totals would disagree with the number of candidates it holds.
    sequenced = _merge_identical_proposals(tuple(proposals))
    surviving_per_generator: dict[str, int] = {}
    for proposal in sequenced:
        surviving_per_generator[proposal.generator_id] = (
            surviving_per_generator.get(proposal.generator_id, 0) + 1
        )
    outcomes = gate_all(sequenced, context.run_id, suppressed_pairs)

    admitted: list[CandidateEdge] = []
    rejections: dict[str, RejectionTally] = {
        tally.generator_id: tally.rejections for tally in tallies
    }
    admitted_per_generator: dict[str, int] = {}
    for outcome in outcomes:
        if outcome.candidate is not None:
            admitted.append(outcome.candidate)
            admitted_per_generator[outcome.generator_id] = (
                admitted_per_generator.get(outcome.generator_id, 0) + 1
            )
        elif outcome.reason is not None:
            rejections[outcome.generator_id] = rejections[outcome.generator_id].with_one(
                outcome.reason
            )

    retained, truncations, dropped = apply_per_effect_cap(
        tuple(admitted), context.parameters.per_effect_candidate_cap
    )
    for record in truncations:
        for generator_id, count in record.dropped_by_generator:
            for _ in range(count):
                rejections[generator_id] = rejections[generator_id].with_one(
                    RejectionReason.TRUNCATED_BY_CAP
                )

    # Rejection identities, as plain tuples in `RejectedProposal.sort_key` shape.
    #
    # A generator, iterated twice, rather than a materialized list -- and NOT a list of
    # models. The counts below need every rejection; the records need only the canonical
    # first `SAMPLED_REJECTIONS` of them. Building a model per rejection to satisfy the
    # second would build millions of them at the 20,000-row default and discard all but 500,
    # which is the cost the bound exists to avoid rather than a cost it removes.
    def _refusal_keys() -> Iterator[tuple[str, str, str, str]]:
        for outcome in outcomes:
            if outcome.candidate is None and outcome.reason is not None:
                yield (
                    outcome.effect_event_id,
                    outcome.cause_event_id,
                    outcome.generator_id,
                    outcome.reason.value,
                )
        for candidate in dropped:
            yield (
                candidate.target_event_id,
                candidate.source_event_id,
                candidate.generator_id,
                RejectionReason.TRUNCATED_BY_CAP.value,
            )

    # Counted over the COMPLETE set. A per-effect count taken from the bounded sample would
    # be a partial number wearing a total's clothes.
    per_effect: dict[str, int] = {}
    rejection_total = 0
    for effect_id, _cause, _generator, _reason in _refusal_keys():
        per_effect[effect_id] = per_effect.get(effect_id, 0) + 1
        rejection_total += 1
    # `nsmallest` keeps a bounded heap internally, so this is one more pass in O(n log 500)
    # time and O(500) space -- never the whole population in memory at once.
    sample = heapq.nsmallest(SAMPLED_REJECTIONS, _refusal_keys())
    graph = CandidateGraph(
        run_id=context.run_id,
        candidates=retained,
        truncations=truncations,
        admitted_count=len(admitted),
        rejections=tuple(
            RejectedProposal(
                effect_event_id=effect_id,
                cause_event_id=cause_id,
                generator_id=generator_id,
                reason=RejectionReason(reason),
            )
            for effect_id, cause_id, generator_id, reason in sample
        ),
        rejection_total=rejection_total,
        rejections_per_effect=tuple(sorted(per_effect.items())),
    )
    flags = detect_confounding(graph.candidates)

    retained_per_generator: dict[str, int] = {}
    for candidate in graph.candidates:
        retained_per_generator[candidate.generator_id] = (
            retained_per_generator.get(candidate.generator_id, 0) + 1
        )

    final_tallies = tuple(
        tally.model_copy(
            update={
                "merged_count": tally.proposed_count
                - surviving_per_generator.get(tally.generator_id, 0),
                "admitted_count": admitted_per_generator.get(tally.generator_id, 0),
                "retained_count": retained_per_generator.get(tally.generator_id, 0),
                "rejections": rejections[tally.generator_id],
            }
        )
        for tally in tallies
    )

    report = CandidateGraphReport(
        envelope=envelope,
        events_examined=len(context.facts.events()),
        timelines_examined=len(context.timelines),
        generators=final_tallies,
        retained_count=len(graph.candidates),
        undetermined_count=len(graph.undetermined_candidates()),
        unverifiable_count=len(graph.unverifiable_candidates()),
        promotable_count=sum(1 for item in graph.candidates if item.admits_promotion),
        distribution=PerEffectDistribution.of(graph.candidates_per_effect()),
        truncations=truncations,
        rejections_per_effect=graph.rejections_per_effect,
        rejection_total=graph.rejection_total,
        confounding_flags=flags[:SAMPLED_CONFOUNDING_FLAGS],
        confounding_flag_total=len(flags),
        confounding_flags_by_structure=tuple(
            sorted(
                (structure.value, sum(1 for flag in flags if flag.structure is structure))
                for structure in ConfoundingStructure
            )
        ),
    )
    return GenerationResult(graph=graph, confounding_flags=flags, report=report)
