"""Explosion control, the totals reconciliation, and the report's three refusals.

The cap is the one place this module could quietly become a ranking module, so the tests
here assert what the policy REFUSES to do as much as what it does.
"""

from __future__ import annotations

import pytest

from causalog.causal_engine.candidate_cause_generator import (
    SATURATION_SHARE,
    CandidateGraph,
    GeneratorStatus,
    RejectedProposal,
    RejectionReason,
    apply_per_effect_cap,
    generate_candidates,
    render_markdown,
)
from causalog.core.errors import ContractViolationError
from causalog.rule_engine import CandidateGenerationSpec
from fixtures.candidates import context_for, envelope, linear_process, window

STAGES = ("STAGE_ONE", "STAGE_TWO", "STAGE_THREE", "STAGE_FOUR")


def _dense_parameters(cap: int | None) -> CandidateGenerationSpec:
    """Declare enough generators that one effect attracts candidates from several."""
    return CandidateGenerationSpec(
        proximity_windows=tuple(
            window(cause, effect) for cause in STAGES for effect in STAGES if cause != effect
        ),
        shared_entity_strength=0.55,
        shared_identifier_strength=0.35,
        minimum_support_count=1,
        historical_frequency_strength=0.4,
        minimum_lift=1.0,
        statistical_association_strength=0.2,
        per_effect_candidate_cap=cap,
    )


def test_no_effect_exceeds_the_declared_cap() -> None:
    """The bound is a bound."""
    _, events, tl = linear_process(*STAGES)
    result = generate_candidates(context_for(events, (tl,), _dense_parameters(3)), envelope())
    for _, count in result.graph.candidates_per_effect():
        assert count <= 3


def test_round_robin_starves_no_generator() -> None:
    """The whole reason the policy is round-robin rather than any ranking.

    Under a cap smaller than the number of generators that reached one effect, a policy
    that sorted by anything -- time, strength, agreement -- would keep several candidates
    from one generator and none from another. Round-robin keeps one from each first.
    """
    _, events, tl = linear_process(*STAGES)
    uncapped = generate_candidates(context_for(events, (tl,), _dense_parameters(None)), envelope())
    per_effect = dict(uncapped.graph.candidates_per_effect())
    busiest = max(per_effect, key=lambda key: (per_effect[key], key))
    contributors = {
        candidate.generator_id
        for candidate in uncapped.graph.candidates
        if candidate.target_event_id == busiest
    }
    assert len(contributors) > 1, "the fixture must have several generators on one effect"

    capped = generate_candidates(
        context_for(events, (tl,), _dense_parameters(len(contributors))), envelope()
    )
    survivors = {
        candidate.generator_id
        for candidate in capped.graph.candidates
        if candidate.target_event_id == busiest
    }
    assert survivors == contributors, "every generator kept exactly one candidate"


def test_every_truncation_is_recorded_per_generator_and_reconciles() -> None:
    """Nothing is ever silently dropped, and the arithmetic is checked, not asserted."""
    _, events, tl = linear_process(*STAGES)
    result = generate_candidates(context_for(events, (tl,), _dense_parameters(2)), envelope())
    assert result.graph.truncations, "the fixture must actually truncate"
    for record in result.graph.truncations:
        assert record.retained_count + record.dropped_count == record.proposed_count
        assert record.dropped_by_generator, "a truncation names who lost what"
    dropped = sum(record.dropped_count for record in result.graph.truncations)
    assert len(result.graph.candidates) + dropped == result.graph.admitted_count


def test_a_truncated_candidate_is_counted_under_its_own_rejection_reason() -> None:
    """Truncated is not rejected. Merging them would make the cap look like bad data."""
    _, events, tl = linear_process(*STAGES)
    result = generate_candidates(context_for(events, (tl,), _dense_parameters(2)), envelope())
    truncated = sum(record.dropped_count for record in result.graph.truncations)
    assert result.report.total_rejections.truncated_by_cap == truncated
    assert truncated > 0


def test_an_absent_cap_retains_everything_and_records_no_truncation() -> None:
    """A pack declaring no bound is making a legitimate declaration for a small dataset."""
    _, events, tl = linear_process(*STAGES)
    result = generate_candidates(context_for(events, (tl,), _dense_parameters(None)), envelope())
    assert result.graph.truncations == ()
    assert len(result.graph.candidates) == result.graph.admitted_count


def test_a_graph_whose_totals_disagree_raises_rather_than_being_published() -> None:
    """Module 1's `rows_read == rows_clean + rows_quarantined` treatment, applied here."""
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO")
    result = generate_candidates(context_for(events, (tl,), _dense_parameters(None)), envelope())
    with pytest.raises(ContractViolationError, match="does not reconcile"):
        CandidateGraph(
            run_id=result.graph.run_id,
            candidates=result.graph.candidates,
            truncations=(),
            admitted_count=len(result.graph.candidates) + 99,
        )


def test_a_graph_mixing_two_runs_is_refused() -> None:
    """One run's inference must never read as another's (ADR-0013)."""
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO")
    result = generate_candidates(context_for(events, (tl,), _dense_parameters(None)), envelope())
    with pytest.raises(ContractViolationError, match="scoped to run"):
        CandidateGraph(
            run_id="run:someotherrun000",
            candidates=result.graph.candidates,
            truncations=(),
            admitted_count=len(result.graph.candidates),
        )


def test_capping_is_deterministic_over_a_reshuffled_input() -> None:
    """Two callers assembling candidates differently must lose the same ones."""
    _, events, tl = linear_process(*STAGES)
    result = generate_candidates(context_for(events, (tl,), _dense_parameters(None)), envelope())
    forwards, first_records, first_dropped = apply_per_effect_cap(result.graph.candidates, 2)
    backwards, second_records, second_dropped = apply_per_effect_cap(
        tuple(reversed(result.graph.candidates)), 2
    )
    assert forwards == backwards
    assert first_records == second_records
    # The dropped set is part of the answer now, so it is part of what must be stable.
    assert first_dropped == second_dropped
    assert set(forwards).isdisjoint(first_dropped)
    assert len(forwards) + len(first_dropped) == len(result.graph.candidates)


# ---------------------------------------------------------------------------------------
# The report's three refusals
# ---------------------------------------------------------------------------------------


def test_a_generator_that_could_not_run_is_never_reported_as_zero() -> None:
    """Refusal 1. The OQ-014 / DEF-0001 failure shape, kept out of this report."""
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO")
    parameters = CandidateGenerationSpec(proximity_windows=(window("STAGE_ONE", "STAGE_TWO"),))
    result = generate_candidates(context_for(events, (tl,), parameters), envelope())
    not_runnable = {tally.generator_id for tally in result.report.not_runnable_generators}
    assert "rule_based" in not_runnable
    assert "shared_entity" in not_runnable
    for tally in result.report.not_runnable_generators:
        assert tally.status is GeneratorStatus.NOT_RUNNABLE
        assert tally.requirement, "a NOT_RUNNABLE generator names what it needs"
        assert tally.looks_degenerate is False, "it did not run, so it is not broken"


def test_undetermined_and_unverifiable_are_counted_separately_and_never_summed() -> None:
    """Refusal 2 (`docs/contracts.md` §3)."""
    from fixtures.candidates import unknown_time_event
    from fixtures.facts import timeline

    participant, events, _ = linear_process("STAGE_ONE", "STAGE_TWO")
    unplaced = unknown_time_event("STAGE_THREE", participant=participant)
    everything = (*events, unplaced)
    parameters = CandidateGenerationSpec(
        proximity_windows=(
            window("STAGE_ONE", "STAGE_TWO"),
            window("STAGE_ONE", "STAGE_THREE"),
        ),
        shared_entity_strength=0.55,
    )
    result = generate_candidates(
        context_for(everything, (timeline(*everything),), parameters), envelope()
    )
    assert result.report.unverifiable_count > 0, "the fixture must produce one"
    # Disjoint by construction: `undetermined_candidates` excludes the unverifiable ones.
    unverifiable = {c.candidate_edge_id for c in result.graph.unverifiable_candidates()}
    undetermined = {c.candidate_edge_id for c in result.graph.undetermined_candidates()}
    assert not (unverifiable & undetermined)
    # And nothing resting on absent time may ever be promoted.
    for candidate in result.graph.unverifiable_candidates():
        assert candidate.admits_promotion is False


def test_a_saturated_generator_is_flagged_as_degenerate() -> None:
    """Refusal 3's positive case: a generator proposing over almost everything is broken."""
    _, events, tl = linear_process(*STAGES)
    parameters = CandidateGenerationSpec(shared_entity_strength=0.55)
    result = generate_candidates(context_for(events, (tl,), parameters), envelope())
    (tally,) = [t for t in result.report.generators if t.generator_id == "shared_entity"]
    assert tally.proposed_count >= SATURATION_SHARE * tally.available_pair_count
    assert tally.looks_degenerate is True
    assert "not discriminating" in (tally.degeneracy_note or "")


def test_a_generator_that_ran_and_proposed_nothing_is_flagged_as_degenerate() -> None:
    """The other half of refusal 3, and the easier one to miss."""
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO")
    parameters = CandidateGenerationSpec(
        proximity_windows=(window("STAGE_ONE", "STAGE_TWO"),),
        structural_max_hops=2,
        structural_path_strength=0.25,
    )
    result = generate_candidates(context_for(events, (tl,), parameters), envelope())
    (tally,) = [t for t in result.report.generators if t.generator_id == "structural_path"]
    assert tally.status is GeneratorStatus.RAN
    assert tally.proposed_count == 0
    assert tally.looks_degenerate is True


def test_the_rendered_report_leads_with_the_findings_not_the_totals() -> None:
    """A reader who stops after one screen must have seen what is wrong."""
    _, events, tl = linear_process(*STAGES)
    result = generate_candidates(context_for(events, (tl,), _dense_parameters(2)), envelope())
    rendered = render_markdown(result.report)
    not_runnable_at = rendered.index("## Generators that could not run")
    degenerate_at = rendered.index("## Generators whose output looks degenerate")
    totals_at = rendered.index("## Candidates by generator")
    assert not_runnable_at < degenerate_at < totals_at
    assert "assigns no confidence" in rendered
    assert "never a plausibility ranking" in rendered


# ---------------------------------------------------------------------------------------
# Merging identical claims (found by the graph's own arithmetic check, on real data)
# ---------------------------------------------------------------------------------------


def test_two_rules_proposing_one_claim_become_one_candidate_with_both_justifications() -> None:
    """One generator reaching one pair twice with the same payload is ONE hypothesis.

    The DataCo pack authors this on purpose -- `R-DCO-DISPATCH-MISS-DELAYS` and
    `R-DCO-TRANSIT-DELAYS` both propose into one delay, and the pack's own rationale calls
    that "exactly the candidate graph prd.md §27 asks for". Two rules are two justifications
    for one claim, and LAW-EVIDENCE wants both attached rather than one silently winning.

    Found by `CandidateGraph`'s own totals check on the reference dataset: before the merge
    the two collided on one address and `retained + dropped != proposed`.
    """
    from causalog.causal_engine.candidate_cause_generator import Proposal
    from causalog.causal_engine.candidate_cause_generator.generate import (
        _merge_identical_proposals,
    )
    from causalog.causal_engine.candidate_cause_generator.generators.support import (
        evidence_item,
    )
    from causalog.core.provenance import ProvenanceClass
    from causalog.core.types import DirectCause, EvidenceKind

    _, events, _ = linear_process("STAGE_ONE", "STAGE_TWO")
    cause, effect = events

    def _from(rule_id: str) -> Proposal:
        return Proposal(
            generator_id="rule_based",
            cause_event=cause,
            effect_event=effect,
            payload=DirectCause(),
            evidence=(
                evidence_item(
                    kind=EvidenceKind.RULE,
                    description=f"rule {rule_id} fired",
                    verification=f"rule_engine.evaluate; rule {rule_id}",
                    supporting_ids=(cause.event_id, effect.event_id),
                    strength=0.5,
                    provenance_class=ProvenanceClass.ASSUMED,
                ),
            ),
        )

    (merged,) = _merge_identical_proposals((_from("R-ONE"), _from("R-TWO")))
    assert len(merged.evidence) == 2, "both justifications survive"
    descriptions = {item.description for item in merged.evidence}
    assert descriptions == {"rule R-ONE fired", "rule R-TWO fired"}
    ids = [item.evidence_item_id for item in merged.evidence]
    assert ids == sorted(ids), "merged evidence is sequenced (CONVENTIONS.md §11)"


def test_two_claims_from_one_generator_with_different_payloads_are_not_merged() -> None:
    """Two CONDITIONAL claims under different conditions are two claims, not one."""
    from causalog.causal_engine.candidate_cause_generator import Proposal
    from causalog.causal_engine.candidate_cause_generator.generate import (
        _merge_identical_proposals,
    )
    from causalog.causal_engine.candidate_cause_generator.generators.support import (
        evidence_item,
    )
    from causalog.core.provenance import ProvenanceClass
    from causalog.core.types import ConditionalCause, EvidenceKind

    _, events, _ = linear_process("STAGE_ONE", "STAGE_TWO")
    cause, effect = events

    def _under(condition: str) -> Proposal:
        return Proposal(
            generator_id="rule_based",
            cause_event=cause,
            effect_event=effect,
            payload=ConditionalCause(condition_expression=condition, condition_holds=True),
            evidence=(
                evidence_item(
                    kind=EvidenceKind.RULE,
                    description=f"fired under {condition}",
                    verification=f"rule_engine.evaluate; condition {condition}",
                    supporting_ids=(cause.event_id, effect.event_id),
                    strength=0.5,
                    provenance_class=ProvenanceClass.ASSUMED,
                ),
            ),
        )

    kept = _merge_identical_proposals((_under("A == 1"), _under("B == 2")))
    assert len(kept) == 2, "different conditions are different claims"


def test_the_per_generator_totals_reconcile_after_merging() -> None:
    """`proposed == merged + admitted + rejected`, per generator, on every run."""
    _, events, tl = linear_process(*STAGES)
    result = generate_candidates(context_for(events, (tl,), _dense_parameters(2)), envelope())
    for tally in result.report.generators:
        if tally.status is GeneratorStatus.NOT_RUNNABLE:
            continue
        rejected = tally.rejections.total - tally.rejections.truncated_by_cap
        assert (
            tally.proposed_count == tally.merged_count + tally.admitted_count + rejected
        ), f"{tally.generator_id} does not reconcile"


# ---------------------------------------------------------------------------------------
# Rejections keep the effect they were refused for (ADR-0058)
# ---------------------------------------------------------------------------------------


def test_a_refusal_names_the_effect_it_was_refused_for() -> None:
    """The question this feature exists to answer, asked of a real run.

    Before this, a rejection kept its reason and its generator and lost both event ids, so
    "what was rejected for THIS effect?" could only be answered per generator.
    """
    _, events, tl = linear_process(*STAGES)
    result = generate_candidates(context_for(events, (tl,), _dense_parameters(2)), envelope())
    graph = result.graph

    assert graph.rejection_total > 0
    assert graph.rejections_per_effect
    for effect_id, count in graph.rejections_per_effect:
        assert count > 0
        for rejection in graph.rejections_for_effect(effect_id):
            assert rejection.effect_event_id == effect_id
            assert rejection.cause_event_id


def test_the_per_effect_counts_are_complete_even_where_the_sample_is_not() -> None:
    """The counts are the answer; the records are a way in.

    A per-effect count derived from the bounded sample would be a partial number in the
    shape of a total. This asserts the two are computed from different populations.
    """
    _, events, tl = linear_process(*STAGES)
    result = generate_candidates(context_for(events, (tl,), _dense_parameters(2)), envelope())
    graph = result.graph

    assert sum(count for _effect, count in graph.rejections_per_effect) == graph.rejection_total
    assert len(graph.rejections) <= graph.rejection_total
    assert graph.rejection_total == result.report.rejection_total


def test_cap_truncations_reconcile_against_their_own_records() -> None:
    """The commonest rejection must agree with the ledger that already counted it.

    `TruncationRecord` counted the drops per generator and the new records name them per
    instance. Two accounts of one event that can disagree is exactly the defect the graph's
    other arithmetic checks exist to catch.
    """
    _, events, tl = linear_process(*STAGES)
    result = generate_candidates(context_for(events, (tl,), _dense_parameters(2)), envelope())
    graph = result.graph
    assert graph.truncations

    for record in graph.truncations:
        counted = dict(graph.rejections_per_effect).get(record.effect_event_id, 0)
        assert counted >= record.dropped_count


def test_a_rejection_that_names_no_proposal_is_refused() -> None:
    """`GENERATOR_NOT_RUNNABLE` has no proposal behind it, so it can name no effect.

    Coverage here is instance-level for four of the five reasons, not five. Making the
    fifth structurally impossible is what keeps that honest -- a documented limitation
    nothing enforces is a limitation waiting to be violated.
    """
    with pytest.raises(ContractViolationError, match="GENERATOR_NOT_RUNNABLE"):
        CandidateGraph(
            run_id="run:test",
            candidates=(),
            truncations=(),
            admitted_count=0,
            rejections=(
                RejectedProposal(
                    cause_event_id="evt:a",
                    effect_event_id="evt:b",
                    generator_id="rule_based",
                    reason=RejectionReason.GENERATOR_NOT_RUNNABLE,
                ),
            ),
            rejection_total=1,
            rejections_per_effect=(("evt:b", 1),),
        )


def test_two_refusals_of_one_pair_by_one_generator_are_both_retained() -> None:
    """`(cause, effect, generator, reason)` is NOT unique, and must not be treated as such.

    Only IDENTICAL payloads are merged upstream, so one generator can legitimately propose
    a pair twice under different payloads and have both refused alike. A uniqueness
    validator here would raise on real data.
    """
    duplicate = RejectedProposal(
        cause_event_id="evt:a",
        effect_event_id="evt:b",
        generator_id="rule_based",
        reason=RejectionReason.TEMPORAL_VIOLATION,
    )

    graph = CandidateGraph(
        run_id="run:test",
        candidates=(),
        truncations=(),
        admitted_count=0,
        rejections=(duplicate, duplicate),
        rejection_total=2,
        rejections_per_effect=(("evt:b", 2),),
    )

    assert len(graph.rejections_for_effect("evt:b")) == 2


def test_a_per_effect_breakdown_that_is_only_a_tally_of_the_sample_is_refused() -> None:
    """The breakdown must cover the population, not the printed part of it."""
    with pytest.raises(ContractViolationError, match="complete"):
        CandidateGraph(
            run_id="run:test",
            candidates=(),
            truncations=(),
            admitted_count=0,
            rejections=(),
            rejection_total=7,
            rejections_per_effect=(("evt:b", 2),),
        )


def test_the_rendered_report_states_the_true_total_when_it_elides() -> None:
    _, events, tl = linear_process(*STAGES)
    result = generate_candidates(context_for(events, (tl,), _dense_parameters(2)), envelope())
    rendered = render_markdown(result.report)

    assert "## Rejections per effect event" in rendered
    assert f"{result.report.rejection_total:,} claim(s) were refused" in rendered
    # Placed after the totals table, so the section-ordering guarantee above is untouched.
    assert rendered.index("## Candidates by generator") < rendered.index(
        "## Rejections per effect event"
    )
