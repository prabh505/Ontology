"""Two generations over one input produce byte-identical output.

`CONVENTIONS.md` §3 makes determinism a Definition-of-Done item for every module, and §11
names the specific threats: unsorted iteration, float drift, random identifiers. This file
tests all three at once by comparing canonical JSON, not by comparing object graphs -- a
`==` on two pydantic models would pass while their serialized forms differed in float
formatting or collection sequence, which is exactly the defect that surfaces later as an
unreproducible graph.

Invariance to INPUT SEQUENCE is tested alongside stability, because the two failures look
identical from a single run and have different causes: a stable-but-sequence-sensitive
module is deterministic on one machine and not across two callers.
"""

from __future__ import annotations

from causalog.causal_engine.candidate_cause_generator import (
    generate_candidates,
    render_markdown,
)
from causalog.core.serialization import to_canonical_json
from causalog.rule_engine import CandidateGenerationSpec
from fixtures.candidates import context_for, envelope, linear_process, window

STAGES = ("STAGE_ONE", "STAGE_TWO", "STAGE_THREE", "STAGE_FOUR")


def _parameters() -> CandidateGenerationSpec:
    """Enable every generator that can run without a rule evaluation."""
    return CandidateGenerationSpec(
        proximity_windows=tuple(
            window(cause, effect) for cause in STAGES for effect in STAGES if cause != effect
        ),
        shared_entity_strength=0.55,
        shared_identifier_strength=0.35,
        structural_max_hops=2,
        structural_path_strength=0.25,
        minimum_support_count=1,
        historical_frequency_strength=0.4,
        minimum_lift=1.0,
        statistical_association_strength=0.2,
        per_effect_candidate_cap=5,
    )


def test_two_generations_produce_byte_identical_graphs() -> None:
    """Same inputs, same seed, same hashes: one answer."""
    _, events, tl = linear_process(*STAGES)
    first = generate_candidates(context_for(events, (tl,), _parameters()), envelope())
    second = generate_candidates(context_for(events, (tl,), _parameters()), envelope())
    assert to_canonical_json(first.graph) == to_canonical_json(second.graph)


def test_two_generations_produce_byte_identical_reports() -> None:
    """The report is an output too, and a report that drifts is a report nobody can diff."""
    _, events, tl = linear_process(*STAGES)
    first = generate_candidates(context_for(events, (tl,), _parameters()), envelope())
    second = generate_candidates(context_for(events, (tl,), _parameters()), envelope())
    assert to_canonical_json(first.report) == to_canonical_json(second.report)
    assert render_markdown(first.report) == render_markdown(second.report)


def test_the_graph_is_invariant_to_the_sequence_the_caller_assembled_events_in() -> None:
    """`FactSet.of` sequences at the boundary, so a caller's sequence cannot reach here."""
    _, events, tl = linear_process(*STAGES)
    forwards = generate_candidates(context_for(events, (tl,), _parameters()), envelope())
    backwards = generate_candidates(
        context_for(tuple(reversed(events)), (tl,), _parameters()), envelope()
    )
    assert to_canonical_json(forwards.graph) == to_canonical_json(backwards.graph)


def test_the_graph_is_invariant_to_the_sequence_of_the_timelines() -> None:
    """Two process instances handed over in either sequence produce one graph."""
    _, first_events, first_tl = linear_process(*STAGES, subject="A")
    _, second_events, second_tl = linear_process(*STAGES, subject="B")
    events = first_events + second_events
    forwards = generate_candidates(
        context_for(events, (first_tl, second_tl), _parameters()), envelope()
    )
    backwards = generate_candidates(
        context_for(events, (second_tl, first_tl), _parameters()), envelope()
    )
    assert to_canonical_json(forwards.graph) == to_canonical_json(backwards.graph)


def test_the_graph_is_invariant_to_the_sequence_the_generators_are_offered_in() -> None:
    """`generate_candidates` sorts them, so an injected sequence cannot change the answer.

    This is the one that would silently break the cap: round-robin walks the generators in
    canonical sequence, so a caller passing them in a different sequence must still lose
    the same candidates.
    """
    from causalog.causal_engine.candidate_cause_generator.generators import ALL_GENERATORS

    _, events, tl = linear_process(*STAGES)
    forwards = generate_candidates(
        context_for(events, (tl,), _parameters()), envelope(), ALL_GENERATORS
    )
    backwards = generate_candidates(
        context_for(events, (tl,), _parameters()),
        envelope(),
        tuple(reversed(ALL_GENERATORS)),
    )
    assert to_canonical_json(forwards.graph) == to_canonical_json(backwards.graph)


def test_candidate_identifiers_are_content_addressed_not_positional() -> None:
    """A positional or random identifier would make every rerun a different graph."""
    _, events, tl = linear_process(*STAGES)
    first = generate_candidates(context_for(events, (tl,), _parameters()), envelope())
    second = generate_candidates(
        context_for(tuple(reversed(events)), (tl,), _parameters()), envelope()
    )
    assert [item.candidate_edge_id for item in first.graph.candidates] == [
        item.candidate_edge_id for item in second.graph.candidates
    ]


def test_evidence_identifiers_are_content_addressed_too() -> None:
    """LAW-EVIDENCE items are minted here in bulk; an unaddressed one breaks reruns."""
    _, events, tl = linear_process(*STAGES)
    first = generate_candidates(context_for(events, (tl,), _parameters()), envelope())
    second = generate_candidates(context_for(events, (tl,), _parameters()), envelope())
    assert [
        item.evidence_item_id for candidate in first.graph.candidates for item in candidate.evidence
    ] == [
        item.evidence_item_id
        for candidate in second.graph.candidates
        for item in candidate.evidence
    ]
