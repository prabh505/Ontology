"""Each generator, alone, on a fixture whose expected candidates were derived by hand.

Every test here runs ONE generator. That is the composability claim being exercised: a
generator that reached into another's state, or that depended on the orchestrator having
run first, would fail these outright.

`CONVENTIONS.md` §14: **no test here asserts that a candidate is causally correct.** There
is no ground truth for causality in any fixture, synthetic or otherwise. Every assertion is
structural -- which pairs were proposed, what evidence they carry, what the gate did with
them, whether two runs agree.
"""

from __future__ import annotations

import pytest

from causalog.causal_engine.candidate_cause_generator import GeneratorStatus
from causalog.causal_engine.candidate_cause_generator.generators import (
    ASSOCIATION_DISCLAIMER,
    HistoricalFrequencyGenerator,
    RuleBasedGenerator,
    SharedEntityGenerator,
    SharedIdentifierGenerator,
    StatisticalAssociationGenerator,
    StructuralPathGenerator,
    TemporalProximityGenerator,
)
from causalog.core.provenance import ProvenanceClass
from causalog.core.types import EvidenceKind, Relationship
from causalog.rule_engine import CandidateGenerationSpec
from fixtures.candidates import context_for, linear_process, window

ALL_STAGES = ("STAGE_ONE", "STAGE_TWO", "STAGE_THREE")


# ---------------------------------------------------------------------------------------
# (a) temporal proximity
# ---------------------------------------------------------------------------------------


def test_proximity_proposes_exactly_the_declared_pairs() -> None:
    """Only declared pairs are proposed. An undeclared pair is not a weak candidate."""
    _, events, tl = linear_process(*ALL_STAGES)
    parameters = CandidateGenerationSpec(proximity_windows=(window("STAGE_ONE", "STAGE_TWO"),))
    proposals = TemporalProximityGenerator().propose(context_for(events, (tl,), parameters))
    assert [(p.cause_event.event_type, p.effect_event.event_type) for p in proposals] == [
        ("STAGE_ONE", "STAGE_TWO")
    ]


def test_proximity_refuses_a_pair_outside_the_declared_width() -> None:
    """A pair separated by more than the declared width is not proposed."""
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO", step_days=30)
    parameters = CandidateGenerationSpec(
        proximity_windows=(window("STAGE_ONE", "STAGE_TWO", seconds=3600),)
    )
    assert TemporalProximityGenerator().propose(context_for(events, (tl,), parameters)) == ()


def test_proximity_carries_the_authored_strength_and_never_invents_one() -> None:
    """`EvidenceItem.strength` comes from the pack, verbatim."""
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO")
    parameters = CandidateGenerationSpec(
        proximity_windows=(window("STAGE_ONE", "STAGE_TWO", strength=0.37),)
    )
    (proposal,) = TemporalProximityGenerator().propose(context_for(events, (tl,), parameters))
    assert proposal.evidence[0].strength == 0.37
    assert proposal.evidence[0].kind is EvidenceKind.TEMPORAL_PROXIMITY


def test_proximity_without_a_declared_window_is_not_runnable_rather_than_empty() -> None:
    """The failure mode the whole report exists to keep visible."""
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO")
    context = context_for(events, (tl,), CandidateGenerationSpec())
    generator = TemporalProximityGenerator()
    assert generator.status(context) is GeneratorStatus.NOT_RUNNABLE
    assert "proximity_windows" in generator.requirement()


# ---------------------------------------------------------------------------------------
# (c1) shared entity  ·  (c2) shared identifier
# ---------------------------------------------------------------------------------------


def test_shared_entity_proposes_both_directions_and_leaves_direction_to_the_gate() -> None:
    """This generator has no basis for direction, so it proposes both and says nothing.

    Direction is supplied by `core.temporal.verdict` in the gate and by nothing else. A
    generator that picked a direction here would be asserting precedence from a field
    position, which is the failure LAW-TIME exists to prevent.
    """
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO")
    parameters = CandidateGenerationSpec(shared_entity_strength=0.55)
    proposals = SharedEntityGenerator().propose(context_for(events, (tl,), parameters))
    pairs = {(p.cause_event.event_type, p.effect_event.event_type) for p in proposals}
    assert pairs == {("STAGE_ONE", "STAGE_TWO"), ("STAGE_TWO", "STAGE_ONE")}


def test_shared_entity_proposes_nothing_when_no_entity_is_shared() -> None:
    """Two processes with disjoint participants produce no shared-entity pair."""
    _, first_events, first_tl = linear_process("STAGE_ONE", subject="A")
    _, second_events, second_tl = linear_process("STAGE_TWO", subject="B")
    parameters = CandidateGenerationSpec(shared_entity_strength=0.55)
    context = context_for(first_events + second_events, (first_tl, second_tl), parameters)
    assert SharedEntityGenerator().propose(context) == ()


def test_shared_identifier_reads_only_the_declared_keys() -> None:
    """The positive case, and the reason the keys are declared rather than inferred.

    `facts.event` stamps `metadata=(("origin", "fixture"),)` on every event, standing in for
    the traceability pairs the real Event Generator stamps (`observation_mode`, `emission`,
    `occurred_at_policy`). Declaring `origin` as an identifier key makes the generator match
    on it; that is the positive path. The next test is the one that matters more.
    """
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO")
    parameters = CandidateGenerationSpec(
        shared_identifier_strength=0.35, identifier_metadata_keys=("origin",)
    )
    proposals = SharedIdentifierGenerator().propose(context_for(events, (tl,), parameters))
    assert proposals
    for proposal in proposals:
        item = proposal.evidence[0]
        assert item.kind is EvidenceKind.SHARED_IDENTIFIER
        assert "origin" in item.verification
        # The exclusion holds: no participant id reaches the evidence as a shared identifier.
        participants = set(proposal.cause_event.source_entity_ids)
        assert not participants & (
            set(item.supporting_ids)
            - {proposal.cause_event.event_id, proposal.effect_event.event_id}
        )


def test_shared_identifier_with_no_declared_keys_is_not_runnable() -> None:
    """The regression that matters: reading all of metadata was a measured defect.

    A first draft read every metadata pair. On a 150-row slice of the reference dataset it
    proposed 87,446 candidates -- one for every pair of events sharing an `observation_mode`,
    exactly matching the shared-entity generator's count and saying nothing whatever about
    the domain. `Event.metadata` carries the Event Generator's traceability pairs, and
    nothing in its shape distinguishes those from a domain identifier.

    So the keys are declared, and a pack declaring none switches the generator off and is
    told which declaration it is missing. The DataCo pack declares none deliberately: every
    identifier that dataset records becomes a participant entity.
    """
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO")
    parameters = CandidateGenerationSpec(shared_identifier_strength=0.35)
    context = context_for(events, (tl,), parameters)
    generator = SharedIdentifierGenerator()
    assert generator.status(context) is GeneratorStatus.NOT_RUNNABLE
    assert "identifier_metadata_keys" in generator.requirement()
    assert generator.propose(context) == ()


def test_shared_identifier_ignores_an_undeclared_key() -> None:
    """A key the pack did not name is not an identifier, whatever it looks like."""
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO")
    parameters = CandidateGenerationSpec(
        shared_identifier_strength=0.35, identifier_metadata_keys=("some_other_key",)
    )
    assert SharedIdentifierGenerator().propose(context_for(events, (tl,), parameters)) == ()


# ---------------------------------------------------------------------------------------
# (d) structural path
# ---------------------------------------------------------------------------------------


def test_structural_path_reports_zero_over_zero_relationships_rather_than_being_absent() -> None:
    """Module 7 does not exist, so this is today's real behaviour, pinned as such.

    It RUNS -- status is `RAN`, not `NOT_RUNNABLE` -- because its parameters are declared.
    It finds nothing because `GraphFacts.relationships()` is empty. Those are different
    facts and the report keeps them apart.
    """
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO")
    parameters = CandidateGenerationSpec(structural_max_hops=2, structural_path_strength=0.25)
    context = context_for(events, (tl,), parameters)
    generator = StructuralPathGenerator()
    assert generator.status(context) is GeneratorStatus.RAN
    assert generator.propose(context) == ()


def test_structural_path_connects_two_events_through_a_declared_relationship() -> None:
    """The positive case, proving the BFS works before module 7 supplies real input."""
    from fixtures.facts import entity, event, evidence_record, interval, timeline

    citation = evidence_record("row-structural")
    left = entity("LEFT", citation=citation)
    right = entity("RIGHT", citation=citation)
    first = event("STAGE_ONE", interval(0), citation=citation, participants=(left,))
    second = event("STAGE_TWO", interval(2), citation=citation, participants=(right,))
    link = Relationship(
        relationship_id="rel-1",
        relationship_type="ASSOCIATED_WITH",
        source_entity_id=left.entity_id,
        target_entity_id=right.entity_id,
        valid_over=interval(0, span_days=10),
        provenance_class=ProvenanceClass.OBSERVED,
        evidence_record_ids=(citation.evidence_record_id,),
    )
    parameters = CandidateGenerationSpec(structural_max_hops=2, structural_path_strength=0.25)
    context = context_for(
        (first, second),
        (timeline(first, second, subject_entity_ids=(left.entity_id, right.entity_id)),),
        parameters,
        relationships=(link,),
    )
    proposals = StructuralPathGenerator().propose(context)
    assert {(p.cause_event.event_type, p.effect_event.event_type) for p in proposals} == {
        ("STAGE_ONE", "STAGE_TWO"),
        ("STAGE_TWO", "STAGE_ONE"),
    }
    assert "rel-1" in proposals[0].evidence[0].supporting_ids


# ---------------------------------------------------------------------------------------
# (e) historical frequency  ·  (f) statistical association
# ---------------------------------------------------------------------------------------


def test_historical_frequency_needs_the_declared_support_floor_to_be_met() -> None:
    """One instance does not clear a floor of two; two instances do."""
    _, first_events, first_tl = linear_process("STAGE_ONE", "STAGE_TWO", subject="A")
    _, second_events, second_tl = linear_process("STAGE_ONE", "STAGE_TWO", subject="B")
    generator = HistoricalFrequencyGenerator()

    strict = CandidateGenerationSpec(minimum_support_count=2, historical_frequency_strength=0.4)
    one_instance = context_for(first_events, (first_tl,), strict)
    assert generator.propose(one_instance) == ()

    two_instances = context_for(first_events + second_events, (first_tl, second_tl), strict)
    assert len(generator.propose(two_instances)) == 2


def test_historical_frequency_evidence_states_the_rate_and_the_instance_count() -> None:
    """A count nobody can re-derive is not evidence (LAW-EVIDENCE)."""
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO")
    parameters = CandidateGenerationSpec(minimum_support_count=1, historical_frequency_strength=0.4)
    (proposal,) = HistoricalFrequencyGenerator().propose(context_for(events, (tl,), parameters))
    item = proposal.evidence[0]
    assert item.kind is EvidenceKind.HISTORICAL_FREQUENCY
    assert item.provenance_class is ProvenanceClass.STATISTICAL
    assert "minimum_support_count == 1" in item.verification
    # The description must state the limit of what a count establishes. A recurrence claim
    # that does not say it is not a causal claim is exactly the overclaiming R-06 tracks.
    assert "does not establish" in item.description
    assert "not a correlation" in item.description


def test_statistical_association_carries_the_disclaimer_verbatim_on_every_item() -> None:
    """The scope statement is fixed text so it cannot be softened per candidate."""
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO")
    parameters = CandidateGenerationSpec(minimum_lift=1.0, statistical_association_strength=0.2)
    proposals = StatisticalAssociationGenerator().propose(context_for(events, (tl,), parameters))
    assert proposals
    for proposal in proposals:
        item = proposal.evidence[0]
        assert ASSOCIATION_DISCLAIMER in item.description
        assert item.provenance_class is ProvenanceClass.STATISTICAL
        assert "lift =" in item.verification


def test_statistical_association_evidence_carries_all_four_contingency_cells() -> None:
    """A reader recomputes the number; they do not take it on trust."""
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO")
    parameters = CandidateGenerationSpec(minimum_lift=1.0, statistical_association_strength=0.2)
    (proposal, *_) = StatisticalAssociationGenerator().propose(
        context_for(events, (tl,), parameters)
    )
    verification = proposal.evidence[0].verification
    for cell in ("both=", "cause_only=", "effect_only=", "neither="):
        assert cell in verification


def test_statistical_association_refuses_a_pair_below_the_declared_lift_floor() -> None:
    """A floor of 1.0 admits everything that co-occurs; a high floor admits nothing here."""
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO")
    parameters = CandidateGenerationSpec(minimum_lift=99.0, statistical_association_strength=0.2)
    assert StatisticalAssociationGenerator().propose(context_for(events, (tl,), parameters)) == ()


# ---------------------------------------------------------------------------------------
# (b) rule based
# ---------------------------------------------------------------------------------------


def test_rule_based_without_an_evaluation_is_not_runnable_rather_than_empty() -> None:
    """An unevaluated pack is not a pack that proposed nothing."""
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO")
    context = context_for(events, (tl,), CandidateGenerationSpec())
    generator = RuleBasedGenerator()
    assert generator.status(context) is GeneratorStatus.NOT_RUNNABLE
    assert "EvaluationResult" in generator.requirement()


# ---------------------------------------------------------------------------------------
# shared properties of every generator
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "generator",
    [
        HistoricalFrequencyGenerator(),
        SharedEntityGenerator(),
        SharedIdentifierGenerator(),
        StatisticalAssociationGenerator(),
        StructuralPathGenerator(),
        TemporalProximityGenerator(),
    ],
    ids=lambda generator: generator.generator_id,
)
def test_every_generator_returns_a_canonical_sequence(generator: object) -> None:
    """An unsequenced return breaks determinism silently (`CONVENTIONS.md` §11)."""
    _, events, tl = linear_process(*ALL_STAGES)
    parameters = CandidateGenerationSpec(
        proximity_windows=(
            window("STAGE_ONE", "STAGE_TWO"),
            window("STAGE_TWO", "STAGE_THREE"),
        ),
        shared_entity_strength=0.55,
        shared_identifier_strength=0.35,
        structural_max_hops=2,
        structural_path_strength=0.25,
        minimum_support_count=1,
        historical_frequency_strength=0.4,
        minimum_lift=1.0,
        statistical_association_strength=0.2,
    )
    proposals = generator.propose(context_for(events, (tl,), parameters))  # type: ignore[attr-defined]
    keys = [proposal.sort_key() for proposal in proposals]
    assert keys == sorted(keys)


@pytest.mark.parametrize(
    "generator",
    [
        HistoricalFrequencyGenerator(),
        SharedEntityGenerator(),
        SharedIdentifierGenerator(),
        StatisticalAssociationGenerator(),
        StructuralPathGenerator(),
        TemporalProximityGenerator(),
    ],
    ids=lambda generator: generator.generator_id,
)
def test_no_generator_ever_proposes_a_self_pair(generator: object) -> None:
    """An event does not cause itself, and `Proposal` refuses one at construction."""
    _, events, tl = linear_process(*ALL_STAGES)
    parameters = CandidateGenerationSpec(
        proximity_windows=(window("STAGE_ONE", "STAGE_TWO"),),
        shared_entity_strength=0.55,
        shared_identifier_strength=0.35,
        structural_max_hops=2,
        structural_path_strength=0.25,
        minimum_support_count=1,
        historical_frequency_strength=0.4,
        minimum_lift=1.0,
        statistical_association_strength=0.2,
    )
    for proposal in generator.propose(context_for(events, (tl,), parameters)):  # type: ignore[attr-defined]
        assert proposal.cause_event.event_id != proposal.effect_event.event_id
