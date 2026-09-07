"""Confounder flagging on synthetic fork and chain structures.

Every fixture here is a hand-drawn graph shape. Nothing asserts that a flagged structure IS
confounded -- no test can, there is no ground truth -- only that the structure the data
exhibits is made visible, and that flagging changes nothing else about the graph.
"""

from __future__ import annotations

from causalog.causal_engine.candidate_cause_generator import (
    CONFOUNDING_UNRESOLVED_NOTICE,
    ConfoundingStructure,
    detect_confounding,
    generate_candidates,
)
from causalog.rule_engine import CandidateGenerationSpec
from fixtures.candidates import context_for, envelope, linear_process, window


def _triangle_parameters() -> CandidateGenerationSpec:
    """Declare all three edges of the X -> Y -> Z triangle, and X -> Z directly."""
    return CandidateGenerationSpec(
        proximity_windows=(
            window("STAGE_ONE", "STAGE_TWO"),
            window("STAGE_TWO", "STAGE_THREE"),
            window("STAGE_ONE", "STAGE_THREE"),
        )
    )


def test_a_fork_is_flagged_as_a_possible_common_cause() -> None:
    """X -> Y, X -> Z and Y -> Z: the Y -> Z claim may be explained by the shared parent X."""
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO", "STAGE_THREE")
    first, second, third = events
    result = generate_candidates(context_for(events, (tl,), _triangle_parameters()), envelope())
    common_cause = [
        flag
        for flag in result.confounding_flags
        if flag.structure is ConfoundingStructure.POSSIBLE_COMMON_CAUSE
    ]
    assert len(common_cause) == 1
    (flag,) = common_cause
    assert flag.third_event_id == first.event_id, "the shared parent is X"
    assert (flag.source_event_id, flag.target_event_id) == (
        second.event_id,
        third.event_id,
    ), "the flag bears on the Y -> Z pair"


def test_a_chain_is_flagged_as_possible_mediation() -> None:
    """X -> Y -> Z with X -> Z present: the direct claim may be carried through Y."""
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO", "STAGE_THREE")
    first, second, third = events
    result = generate_candidates(context_for(events, (tl,), _triangle_parameters()), envelope())
    mediation = [
        flag
        for flag in result.confounding_flags
        if flag.structure is ConfoundingStructure.POSSIBLE_MEDIATION
    ]
    assert len(mediation) == 1
    (flag,) = mediation
    assert flag.third_event_id == second.event_id, "the mediator is Y"
    assert (flag.source_event_id, flag.target_event_id) == (
        first.event_id,
        third.event_id,
    ), "the flag bears on the X -> Z pair"


def test_one_triangle_produces_both_readings_because_the_data_cannot_separate_them() -> None:
    """Emitting one and not the other would be resolving what nothing here can resolve."""
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO", "STAGE_THREE")
    result = generate_candidates(context_for(events, (tl,), _triangle_parameters()), envelope())
    assert {flag.structure for flag in result.confounding_flags} == {
        ConfoundingStructure.POSSIBLE_MEDIATION,
        ConfoundingStructure.POSSIBLE_COMMON_CAUSE,
    }


def test_a_bare_chain_with_no_shortcut_is_flagged_neither_way() -> None:
    """X -> Y -> Z alone exhibits neither structure. Only the closed triangle does."""
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO", "STAGE_THREE")
    parameters = CandidateGenerationSpec(
        proximity_windows=(
            window("STAGE_ONE", "STAGE_TWO"),
            window("STAGE_TWO", "STAGE_THREE"),
        )
    )
    result = generate_candidates(context_for(events, (tl,), parameters), envelope())
    assert result.confounding_flags == ()


def test_an_unrelated_pair_is_flagged_neither_way() -> None:
    """Two events with one declared window between them form no triangle."""
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO")
    parameters = CandidateGenerationSpec(proximity_windows=(window("STAGE_ONE", "STAGE_TWO"),))
    result = generate_candidates(context_for(events, (tl,), parameters), envelope())
    assert result.confounding_flags == ()


def test_flagging_removes_nothing_and_mutates_nothing() -> None:
    """A module forbidden from ranking is equally forbidden from de-ranking."""
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO", "STAGE_THREE")
    context = context_for(events, (tl,), _triangle_parameters())
    result = generate_candidates(context, envelope())
    assert result.confounding_flags, "the fixture must actually flag something"
    flagged = {
        candidate_id
        for flag in result.confounding_flags
        for candidate_id in flag.flagged_candidate_ids
    }
    present = {candidate.candidate_edge_id for candidate in result.graph.candidates}
    assert flagged <= present, "every flagged candidate is still in the graph"
    # And the graph is exactly what it would have been without any flagging at all.
    assert len(result.graph.candidates) == result.graph.admitted_count


def test_every_flag_carries_the_unresolved_notice_verbatim() -> None:
    """Visibility is not resolution, and every flag has to say so (prd.md §59, R-05)."""
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO", "STAGE_THREE")
    result = generate_candidates(context_for(events, (tl,), _triangle_parameters()), envelope())
    for flag in result.confounding_flags:
        assert flag.notice == CONFOUNDING_UNRESOLVED_NOTICE
        assert "does not resolve" in flag.notice
        assert "absence of a flag is not evidence of no confounding" in flag.notice


def test_a_multigraph_flag_names_every_parallel_candidate_over_the_pair() -> None:
    """Two generators reaching one pair means the structure bears on both proposals."""
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO", "STAGE_THREE")
    parameters = _triangle_parameters().model_copy(update={"shared_entity_strength": 0.55})
    result = generate_candidates(context_for(events, (tl,), parameters), envelope())
    assert result.confounding_flags
    for flag in result.confounding_flags:
        over_pair = {
            candidate.candidate_edge_id
            for candidate in result.graph.candidates
            if (candidate.source_event_id, candidate.target_event_id)
            == (flag.source_event_id, flag.target_event_id)
        }
        assert set(flag.flagged_candidate_ids) == over_pair
        assert len(over_pair) > 1, "the fixture must produce parallel edges"


def test_detection_is_deterministic_over_a_reshuffled_input() -> None:
    """Sorted traversal, so the sequence a caller assembled candidates in cannot matter."""
    _, events, tl = linear_process("STAGE_ONE", "STAGE_TWO", "STAGE_THREE")
    result = generate_candidates(context_for(events, (tl,), _triangle_parameters()), envelope())
    forwards = detect_confounding(result.graph.candidates)
    backwards = detect_confounding(tuple(reversed(result.graph.candidates)))
    assert forwards == backwards
