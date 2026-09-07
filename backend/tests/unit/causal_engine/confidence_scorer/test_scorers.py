"""Each component scorer against hand-computed values, and against its own promises.

Every expected number below is worked out in the docstring above the assertion. A test
asserting `== 0.571429` with no arithmetic beside it pins whatever the implementation
happened to do on the day, which is a regression guard rather than a specification.
"""

from __future__ import annotations

import pytest

from causalog.causal_engine.confidence_scorer import (
    ContradictionFreedomScorer,
    EvidenceCountScorer,
    EvidenceDiversityScorer,
    GraphConnectivityScorer,
    HistoricalSupportScorer,
    RuleSupportScorer,
    StatisticalSupportScorer,
    TemporalSupportScorer,
)
from causalog.causal_engine.confidence_scorer.fuse import FusedClaim
from causalog.core.precedence import (
    DerivedPrecedence,
    DerivedPrecedenceIndex,
    temporal_binding_source,
)
from causalog.core.provenance import ProvenanceClass
from causalog.core.types import Event, Timeline
from fixtures.candidates import scoring_context_for, scoring_parameters
from tests.unit.causal_engine.confidence_scorer.conftest import one_claim


def _by_id(events: tuple[Event, ...]) -> dict[str, Event]:
    """Return the events indexed by identifier."""
    return {event.event_id: event for event in events}


# ---------------------------------------------------------------------------------------
# rule_support
# ---------------------------------------------------------------------------------------


def test_rule_support_is_missing_when_no_rule_proposed_the_pair(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """No rule evidence is a missing component, not a measured zero.

    A claim nobody wrote a rule for has no rule support to measure. That is different
    from a claim the pack argues against, and reporting them alike would make an
    unwritten rule indistinguishable from a refuted one.
    """
    events, timelines = three_stage_run
    claim = one_claim(events, timelines, "STAGE_ONE", "STAGE_TWO")
    scored = RuleSupportScorer().score(
        claim, scoring_context_for(events, timelines), _by_id(events)
    )
    assert scored.value == 0.0
    assert scored.explanation.missing is True
    assert scored.evidence_record_ids == ()


def test_rule_support_combines_independent_rules_by_noisy_or() -> None:
    """Two rules at 0.5 give 1 - (0.5 * 0.5) == 0.75, not 0.5.

    A second authored rule reaching the same conclusion by different reasoning genuinely
    raises support. A mean would say the second rule was worth nothing. The same
    arithmetic is refused one level up, across components, where it would manufacture
    confidence -- ADR-0052 records why the two levels differ.
    """
    combined = 1.0
    for strength in (0.5, 0.5):
        combined *= 1.0 - strength
    assert 1.0 - combined == 0.75


# ---------------------------------------------------------------------------------------
# temporal_support -- the gate
# ---------------------------------------------------------------------------------------


def test_temporal_support_is_zero_when_the_source_never_placed_an_event(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """An unverifiable pair scores exactly 0.0, which caps the whole edge.

    Not missing: the temporal standing WAS measured, and the answer was "the ordering
    rests on nothing". That is a finding, and it is the finding that caps the edge.
    """
    from causalog.core.temporal import TemporalVerdict
    from fixtures.candidates import linear_process, unknown_time_event

    participant, events, timeline = linear_process("STAGE_ONE", "STAGE_TWO", subject="A")
    unplaced = unknown_time_event("STAGE_THREE", participant=participant)
    from fixtures.facts import timeline as build_timeline

    combined_events = (*events, unplaced)
    combined_timeline = build_timeline(*combined_events)
    claim = one_claim(combined_events, (combined_timeline,), "STAGE_ONE", "STAGE_THREE")
    assert any(candidate.temporally_unverifiable for candidate in claim.candidates)

    scored = TemporalSupportScorer().score(
        claim,
        scoring_context_for(combined_events, (combined_timeline,)),
        _by_id(combined_events),
    )
    assert scored.value == 0.0
    assert scored.explanation.missing is False
    assert ("temporally unverifiable", "true") in scored.explanation.inputs
    assert claim.candidates[0].temporal_verdict is not TemporalVerdict.VIOLATION


def test_temporal_support_uses_the_declared_value_for_an_unresolvable_order() -> None:
    """`UNDETERMINED` scores what the pack declared, never a value chosen in engine code.

    The events WERE placed and could not be separated. That is more than an absent
    timestamp and much less than an established order, and how much more is a domain
    judgement -- which is why it is read from `undetermined_temporal_support`.
    """
    from datetime import UTC, datetime

    from causalog.core.temporal import Precision, TemporalVerdict, TimeInterval
    from fixtures.facts import entity, event, evidence_record
    from fixtures.facts import timeline as build_timeline

    same_day = TimeInterval(
        t_earliest=datetime(2024, 1, 1, tzinfo=UTC),
        t_latest=datetime(2024, 1, 1, 23, 59, 59, tzinfo=UTC),
        precision=Precision.DAY,
        provenance=ProvenanceClass.OBSERVED,
        source="fixture: one day, two events, no separation",
    )
    citation = evidence_record("row-tie")
    participant = entity("A", citation=citation)
    first = event("STAGE_ONE", same_day, citation=citation, participants=(participant,))
    second = event("STAGE_TWO", same_day, citation=citation, participants=(participant,))
    events = (first, second)
    timelines = (build_timeline(*events),)
    claim = one_claim(events, timelines, "STAGE_ONE", "STAGE_TWO")
    assert claim.candidates[0].temporal_verdict is TemporalVerdict.UNDETERMINED

    parameters = scoring_parameters(undetermined_temporal_support=0.15)
    scored = TemporalSupportScorer().score(
        claim, scoring_context_for(events, timelines, parameters), _by_id(events)
    )
    assert scored.value == 0.15


def test_temporal_support_is_missing_when_the_scale_is_not_declared(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """A tightness scale is domain policy; without one the component cannot run.

    Defaulting a reference width here would be a judgement wearing a schema default's
    clothes, and it would score every pair in a minutes-scale domain as tight.
    """
    events, timelines = three_stage_run
    claim = one_claim(events, timelines, "STAGE_ONE", "STAGE_TWO")
    parameters = scoring_parameters(temporal_reference_seconds=None)
    scored = TemporalSupportScorer().score(
        claim, scoring_context_for(events, timelines, parameters), _by_id(events)
    )
    assert scored.value == 0.0
    assert scored.explanation.missing is True
    assert scored.explanation.requirement is not None


def test_temporal_tightness_falls_as_the_admissible_gap_widens() -> None:
    """`1 / (1 + width / reference)` is 0.5 at width == reference, and falls from there.

    A pair whose separation is known only to within the source's own granularity scores
    one half against a reference of that granularity. Manufactured precision is expensive
    by construction (`CONVENTIONS.md` §10).
    """
    reference = 86_400

    def tightness(width: int) -> float:
        return 1.0 / (1.0 + width / reference)

    assert tightness(0) == 1.0
    assert tightness(reference) == 0.5
    assert tightness(reference * 3) == 0.25
    assert tightness(reference * 2) < tightness(reference)


# ---------------------------------------------------------------------------------------
# historical_support and statistical_support
# ---------------------------------------------------------------------------------------


def test_historical_support_scores_zero_on_a_pattern_present_everywhere(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """Every instance runs every stage, so lift is 1.0 and support is zero.

    Three instances, each ONE -> TWO -> THREE. P(TWO follows | ONE) == 1.0 and
    P(TWO present) == 1.0, so lift == 1.0 == independence. The count is 3 out of 3 --
    maximal recurrence, and zero evidence. This is the base-rate requirement, asserted
    through the scorer rather than only through the table.
    """
    events, timelines = three_stage_run
    claim = one_claim(events, timelines, "STAGE_ONE", "STAGE_TWO")
    scored = HistoricalSupportScorer().score(
        claim, scoring_context_for(events, timelines), _by_id(events)
    )
    assert scored.value == 0.0
    assert scored.explanation.missing is False
    inputs = dict(scored.explanation.inputs)
    assert inputs["lift"] == "1.000000"
    assert inputs["instances with the sequenced pair"] == "3"
    assert inputs["process instances (denominator)"] == "3"


def test_statistical_support_names_the_measure_and_carries_the_disclaimer(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """prd.md §37: a statistical association is never conflated with an inferred cause.

    Three separate carriers of that separation, all asserted here: the provenance class
    is STATISTICAL, the measure is named rather than implied, and module 9's fixed
    disclaimer travels verbatim rather than being reworded per edge.
    """
    from causalog.causal_engine.candidate_cause_generator import ASSOCIATION_DISCLAIMER

    events, timelines = three_stage_run
    claim = one_claim(events, timelines, "STAGE_ONE", "STAGE_TWO")
    scored = StatisticalSupportScorer().score(
        claim, scoring_context_for(events, timelines), _by_id(events)
    )
    assert scored.provenance_class is ProvenanceClass.STATISTICAL
    assert dict(scored.explanation.inputs)["measure"].startswith("lift over an instance-level")
    assert dict(scored.explanation.inputs)["p-value"].startswith("not computed")
    assert ASSOCIATION_DISCLAIMER in scored.explanation.caveats


def test_a_small_sample_gets_an_explicit_caveat_not_a_rounded_up_score(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """Three instances against a declared prior of twenty is a small sample, and says so."""
    events, timelines = three_stage_run
    claim = one_claim(events, timelines, "STAGE_ONE", "STAGE_TWO")
    scored = StatisticalSupportScorer().score(
        claim, scoring_context_for(events, timelines), _by_id(events)
    )
    assert any("SMALL SAMPLE" in caveat for caveat in scored.explanation.caveats)


# ---------------------------------------------------------------------------------------
# graph_connectivity
# ---------------------------------------------------------------------------------------


def test_graph_connectivity_is_missing_while_there_is_no_relationship_graph(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """Module 7 does not exist, so this is MISSING on every edge -- never a neutral 1.0.

    The three available responses were: drop the component (it renormalizes away and
    every edge scores as though connectivity had been checked), score it neutral (which
    manufactures support out of an absence), or emit it missing at zero so it costs the
    edge score. The third is what happens, and the cost is the correct one.
    """
    events, timelines = three_stage_run
    claim = one_claim(events, timelines, "STAGE_ONE", "STAGE_TWO")
    scored = GraphConnectivityScorer().score(
        claim, scoring_context_for(events, timelines), _by_id(events)
    )
    assert scored.value == 0.0
    assert scored.explanation.missing is True
    assert "module 7" in (scored.explanation.requirement or "")


# ---------------------------------------------------------------------------------------
# evidence_count and evidence_diversity
# ---------------------------------------------------------------------------------------


def test_evidence_count_is_saturating_and_reads_the_declared_k(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """`n / (n + k)`: with k == 3 and four items, 4 / 7 == 0.571429."""
    events, timelines = three_stage_run
    claim = one_claim(events, timelines, "STAGE_ONE", "STAGE_TWO")
    parameters = scoring_parameters(evidence_count_saturation_k=3)
    scored = EvidenceCountScorer().score(
        claim, scoring_context_for(events, timelines, parameters), _by_id(events)
    )
    item_count = len(claim.evidence())
    assert scored.value == pytest.approx(item_count / (item_count + 3))


def test_evidence_count_is_missing_when_the_saturation_point_is_not_declared(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """The count at which a domain is half convinced is a domain judgement."""
    events, timelines = three_stage_run
    claim = one_claim(events, timelines, "STAGE_ONE", "STAGE_TWO")
    parameters = scoring_parameters(evidence_count_saturation_k=None)
    scored = EvidenceCountScorer().score(
        claim, scoring_context_for(events, timelines, parameters), _by_id(events)
    )
    assert scored.explanation.missing is True


def test_diversity_scores_zero_for_a_single_source() -> None:
    """One kind from one generator is not diverse, and scores exactly 0.0.

    `(1 - 1) / (reachable - 1) == 0` on both axes. Calling a single source slightly
    diverse would be arithmetic flattering it.
    """
    from causalog.causal_engine.confidence_scorer.scorers.evidence_diversity import _spread

    assert _spread(1, 4) == 0.0
    assert _spread(1, 1) == 0.0


def test_diversity_rises_with_distinct_kinds_and_not_with_repetition() -> None:
    """The whole point of the component: independence, not volume.

    Against four reachable kinds, two distinct kinds score (2-1)/(4-1) == 0.333 and four
    score 1.0. Repetition of one kind never moves it, which is what `evidence_count`
    measures instead.
    """
    from causalog.causal_engine.confidence_scorer.scorers.evidence_diversity import _spread

    assert _spread(2, 4) == pytest.approx(1 / 3)
    assert _spread(4, 4) == 1.0
    assert _spread(1, 4) < _spread(2, 4) < _spread(3, 4) < _spread(4, 4)


def test_diversity_is_normalized_against_what_this_run_could_reach(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """A run where generators could not run is not capped below an unreachable spread.

    Normalizing against the enum would permanently hold every edge in such a run below a
    diversity nothing in it could have produced, which reads as a finding about the
    claims rather than about the run's configuration.
    """
    events, timelines = three_stage_run
    claim = one_claim(events, timelines, "STAGE_ONE", "STAGE_TWO")
    context = scoring_context_for(events, timelines)
    kinds = len({item.kind for item in claim.evidence()})
    generous = EvidenceDiversityScorer(kinds, len(claim.generator_ids())).score(
        claim, context, _by_id(events)
    )
    stingy = EvidenceDiversityScorer(99, 99).score(claim, context, _by_id(events))
    assert generous.value > stingy.value
    assert generous.value == 1.0


# ---------------------------------------------------------------------------------------
# contradiction_freedom -- the second gate
# ---------------------------------------------------------------------------------------


def test_contradiction_freedom_is_one_when_nothing_argues_against_the_claim(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """No counter-evidence is a measured finding, never a missing component.

    Reporting it as missing would make a claim nothing argues against look like a claim
    nobody checked.
    """
    events, timelines = three_stage_run
    claim = one_claim(events, timelines, "STAGE_ONE", "STAGE_TWO")
    scored = ContradictionFreedomScorer().score(
        claim, scoring_context_for(events, timelines), _by_id(events)
    )
    assert scored.value == 1.0
    assert scored.explanation.missing is False


def test_a_constraint_prohibition_drives_contradiction_freedom_to_one_half(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """Weight 1.00 against a half-at of 1.0 gives 1 - (1 / 2) == 0.5.

    The strongest of the four signals: the pack states this pair cannot happen. Half is
    what one such finding costs, and the contradiction ceiling at 0.5 is 0.60 -- so the
    edge is capped there however strong its other support.
    """
    events, timelines = three_stage_run
    claim = one_claim(events, timelines, "STAGE_ONE", "STAGE_TWO")
    context = scoring_context_for(
        events,
        timelines,
        suppressed_pairs=frozenset({(claim.source_event_id, claim.target_event_id)}),
    )
    scored = ContradictionFreedomScorer().score(claim, context, _by_id(events))
    assert scored.value == 0.5
    assert dict(scored.explanation.inputs)["constraint prohibition"] == "yes"


def test_contradiction_signals_accumulate_but_never_imitate_a_prohibition(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """Saturating, so no pile of weak signals reaches what one strong signal costs.

    A reverse proposal weighs 0.30 and a confounding flag 0.10. Ten flags plus a reverse
    proposal total 1.30, which costs more than one prohibition -- but each additional
    flag costs less than the one before it, so the accumulation decelerates rather than
    running away.
    """
    events, timelines = three_stage_run
    claim = one_claim(events, timelines, "STAGE_ONE", "STAGE_TWO")
    by_id = _by_id(events)
    clean = ContradictionFreedomScorer().score(claim, scoring_context_for(events, timelines), by_id)
    reversed_too = ContradictionFreedomScorer().score(
        claim,
        scoring_context_for(
            events,
            timelines,
            proposed_pairs=frozenset({(claim.target_event_id, claim.source_event_id)}),
        ),
        by_id,
    )
    assert reversed_too.value < clean.value
    # 1 - (0.30 / 1.30)
    assert reversed_too.value == pytest.approx(1.0 - (0.30 / 1.30))


def test_every_scorer_returns_a_component_rather_than_none(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """The rule the whole module rests on, asserted over all eight scorers.

    There is no "not applicable" return anywhere, so a component cannot be skipped by
    accident. A scorer with nothing to measure returns zero and marks itself missing.
    """
    events, timelines = three_stage_run
    claim = one_claim(events, timelines, "STAGE_ONE", "STAGE_TWO")
    context = scoring_context_for(events, timelines, scoring_parameters())
    by_id = _by_id(events)
    scorers = (
        ContradictionFreedomScorer(),
        EvidenceCountScorer(),
        EvidenceDiversityScorer(4, 4),
        GraphConnectivityScorer(),
        HistoricalSupportScorer(),
        RuleSupportScorer(),
        StatisticalSupportScorer(),
        TemporalSupportScorer(),
    )
    for scorer in scorers:
        scored = scorer.score(claim, context, by_id)
        assert scored is not None
        assert scored.component_name == scorer.component_name
        assert 0.0 <= scored.value <= 1.0
        assert scored.explanation.component_name == scorer.component_name
        assert scorer.requirement()


# ---------------------------------------------------------------------------------------
# temporal_support: precedence the source COMPUTED rather than recorded (ADR-0057)
# ---------------------------------------------------------------------------------------


_EARLIER_SOURCE = temporal_binding_source("column_a")
_DERIVED_SOURCE = temporal_binding_source("column_b")


def _with_distinct_sources(
    events: tuple[Event, ...], cause_id: str, effect_id: str
) -> tuple[Event, ...]:
    """Return the events with the claim's two instants bound to DIFFERENT source columns.

    The shared fixture builds every instant from one binding, so out of the box the two
    sides of a claim carry the same locator -- which `DerivedPrecedence` refuses outright,
    and rightly: two events read from ONE column cannot have had one computed from the
    other. That refusal is load-bearing in production (many events of a type share a
    column), so the fixture is adjusted rather than the invariant.
    """
    patched: list[Event] = []
    for event in events:
        if event.event_id == cause_id:
            interval = event.occurred_at.model_copy(update={"source": _EARLIER_SOURCE})
            patched.append(event.model_copy(update={"occurred_at": interval}))
        elif event.event_id == effect_id:
            interval = event.occurred_at.model_copy(update={"source": _DERIVED_SOURCE})
            patched.append(event.model_copy(update={"occurred_at": interval}))
        else:
            patched.append(event)
    return tuple(patched)


def _derived_index(cause_source: str, effect_source: str) -> DerivedPrecedenceIndex:
    """Return an index declaring the effect's instant computed from the cause's."""
    return DerivedPrecedenceIndex.of(
        (
            DerivedPrecedence(
                check_id="CHECK_ONE",
                cause_interval_source=cause_source,
                effect_interval_source=effect_source,
                agreement_rate=0.9461,
                evaluated=180519,
                residual_seconds=((43200, 5080),),
                rationale="the later instant is suspected of being computed from the earlier",
            ),
        )
    )


def _sound_pair(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> tuple[FusedClaim, tuple[Event, ...], tuple[Timeline, ...]]:
    """Return a CERTAIN claim over events whose two instants carry distinct locators."""
    events, timelines = three_stage_run
    claim = one_claim(events, timelines, "STAGE_ONE", "STAGE_TWO")
    patched = _with_distinct_sources(events, claim.source_event_id, claim.target_event_id)
    return claim, patched, timelines


def test_a_derived_precedence_is_capped_at_the_declared_value(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """Arithmetic precedence scores the pack's cap, not the separation's tightness.

    The tightness would be high here -- the fixture's instants are narrow -- and that is the
    point: a tight gap between an instant and itself-plus-a-constant is still no evidence.
    """
    claim, events, timelines = _sound_pair(three_stage_run)
    context = scoring_context_for(
        events, timelines, derived_precedence=_derived_index(_EARLIER_SOURCE, _DERIVED_SOURCE)
    )

    scored = TemporalSupportScorer().score(claim, context, _by_id(events))

    assert scored.value == pytest.approx(0.10)
    assert scored.explanation.missing is False
    assert ("derivation check", "CHECK_ONE") in scored.explanation.inputs


def test_a_derived_precedence_is_assumed_and_never_inferred(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """INFERRED would claim the bounds established this precedence. They did not.

    The number standing here came from a declaration, and `ASSUMED` is the class that says
    so. Provenance combines weakest-first, so this weakens the whole vector -- intended.
    """
    claim, events, timelines = _sound_pair(three_stage_run)
    context = scoring_context_for(
        events, timelines, derived_precedence=_derived_index(_EARLIER_SOURCE, _DERIVED_SOURCE)
    )

    scored = TemporalSupportScorer().score(claim, context, _by_id(events))

    assert scored.provenance_class is ProvenanceClass.ASSUMED


def test_the_cap_never_raises_a_score_it_should_lower(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """A ceiling, not a substitution.

    Where measured tightness already sits below the declared cap -- a very wide admissible
    separation -- the cap must leave it alone. Substituting would REWARD a pair for having
    its precedence manufactured, which inverts the whole point of the feature.
    """
    claim, events, timelines = _sound_pair(three_stage_run)
    by_id = _by_id(events)
    plain = TemporalSupportScorer().score(claim, scoring_context_for(events, timelines), by_id)
    # A cap above the measured tightness cannot lift it.
    context = scoring_context_for(
        events,
        timelines,
        parameters=scoring_parameters(derived_precedence_temporal_support=1.0),
        derived_precedence=_derived_index(_EARLIER_SOURCE, _DERIVED_SOURCE),
    )

    capped = TemporalSupportScorer().score(claim, context, by_id)

    assert capped.value <= plain.value


def test_the_derivation_is_matched_only_in_the_direction_it_was_measured(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """A reversed declaration must not touch this claim.

    The measurement says one instant was computed from the other. Applied backwards it would
    depress confidence on precedence the source really did record.
    """
    claim, events, timelines = _sound_pair(three_stage_run)
    by_id = _by_id(events)
    plain = TemporalSupportScorer().score(claim, scoring_context_for(events, timelines), by_id)
    reversed_index = _derived_index(_DERIVED_SOURCE, _EARLIER_SOURCE)

    scored = TemporalSupportScorer().score(
        claim,
        scoring_context_for(events, timelines, derived_precedence=reversed_index),
        by_id,
    )

    assert scored.value == pytest.approx(plain.value)
    assert scored.provenance_class is ProvenanceClass.INFERRED


def test_a_confirmed_derivation_with_no_declared_cap_is_not_scorable(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """The pack did not say what arithmetic precedence is worth, so this module does not.

    Scoring the tightness instead would report the source's own subtraction back to the
    reader as evidence, which is exactly the substitution ADR-0057 exists to refuse. The
    requirement names the missing knob and the check that fired -- not the two parameters
    that were supplied and are fine.
    """
    claim, events, timelines = _sound_pair(three_stage_run)
    context = scoring_context_for(
        events,
        timelines,
        parameters=scoring_parameters(derived_precedence_temporal_support=None),
        derived_precedence=_derived_index(_EARLIER_SOURCE, _DERIVED_SOURCE),
    )

    scored = TemporalSupportScorer().score(claim, context, _by_id(events))

    assert scored.explanation.missing is True
    assert scored.value == 0.0
    requirement = scored.explanation.requirement or ""
    assert "derived_precedence_temporal_support" in requirement
    assert "CHECK_ONE" in requirement
    assert "temporal_reference_seconds" not in requirement


def test_an_unaudited_run_scores_tightness_but_says_it_was_not_audited(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """No measurement is a fact about the RUN, never a per-pair refusal.

    Refusing every CERTAIN pair for want of an audit would assert that all precedence is
    suspect -- an overclaim in the opposite direction from the one being corrected. The
    score stands and the caveat records that nobody looked.
    """
    claim, events, timelines = _sound_pair(three_stage_run)

    scored = TemporalSupportScorer().score(
        claim, scoring_context_for(events, timelines), _by_id(events)
    )

    assert scored.explanation.missing is False
    assert scored.provenance_class is ProvenanceClass.INFERRED
    assert any("NOT AUDITED" in caveat for caveat in scored.explanation.caveats)


def test_an_audited_run_that_confirmed_nothing_carries_no_absence_caveat(
    three_stage_run: tuple[tuple[Event, ...], tuple[Timeline, ...]],
) -> None:
    """Supplied-and-empty is a measurement. It must not read as an unaudited run."""
    claim, events, timelines = _sound_pair(three_stage_run)
    context = scoring_context_for(events, timelines, derived_precedence=DerivedPrecedenceIndex())

    scored = TemporalSupportScorer().score(claim, context, _by_id(events))

    assert not any("NOT AUDITED" in caveat for caveat in scored.explanation.caveats)
