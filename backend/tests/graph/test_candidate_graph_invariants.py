"""Graph-invariant tests for the candidate multigraph.

`CONVENTIONS.md` §14 requires this kind for modules 8-12: edge direction, absence of
temporal violations, sequencing. It asserts nothing about whether a specific edge is TRUE
-- there is no ground truth for causality in this dataset or any other here.
"""

from __future__ import annotations

from causalog.causal_engine.candidate_cause_generator import (
    CandidateGraph,
    generate_candidates,
)
from causalog.core.temporal import TemporalVerdict, strictly_before
from causalog.rule_engine import CandidateGenerationSpec
from fixtures.candidates import context_for, envelope, linear_process, window

STAGES = ("STAGE_ONE", "STAGE_TWO", "STAGE_THREE")


def _parameters() -> CandidateGenerationSpec:
    """Enable several generators so parallel edges actually arise."""
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
    )


def _graph() -> CandidateGraph:
    """Return a candidate graph over the standard three-stage fixture."""
    _, events, tl = linear_process(*STAGES)
    return generate_candidates(context_for(events, (tl,), _parameters()), envelope()).graph


def test_no_candidate_carries_a_violation_verdict() -> None:
    """LAW-TIME, asserted over the whole graph rather than over one construction."""
    for candidate in _graph().candidates:
        assert candidate.temporal_verdict is not TemporalVerdict.VIOLATION


def test_every_certain_candidate_really_does_have_its_cause_first() -> None:
    """Direction is a property of the intervals, re-derived here from `core.temporal`.

    Deliberately re-derived rather than read off the stored verdict: `docs/contracts.md`
    records (DEF-0002) that a stored verdict cannot be re-checked from the artifact alone,
    so this test does what the artifact cannot and goes back to the events.
    """
    _, events, tl = linear_process(*STAGES)
    by_id = {item.event_id: item for item in events}
    graph = generate_candidates(context_for(events, (tl,), _parameters()), envelope()).graph
    for candidate in graph.candidates:
        if candidate.temporal_verdict is not TemporalVerdict.CERTAIN:
            continue
        cause = by_id[candidate.source_event_id]
        effect = by_id[candidate.target_event_id]
        assert strictly_before(cause.occurred_at, effect.occurred_at)


def test_no_candidate_is_a_self_edge() -> None:
    """An event does not cause itself."""
    for candidate in _graph().candidates:
        assert candidate.source_event_id != candidate.target_event_id


def test_parallel_edges_are_retained_separately_with_distinct_evidence() -> None:
    """The multigraph claim. Merging two generators' reasoning would destroy it."""
    graph = _graph()
    by_pair: dict[tuple[str, str], list[str]] = {}
    for candidate in graph.candidates:
        by_pair.setdefault((candidate.source_event_id, candidate.target_event_id), []).append(
            candidate.generator_id
        )
    parallel = {pair: ids for pair, ids in by_pair.items() if len(ids) > 1}
    assert parallel, "the fixture must produce at least one pair reached by two generators"
    for pair, generator_ids in parallel.items():
        assert len(set(generator_ids)) == len(generator_ids), (
            f"pair {pair} holds two candidates from one generator; parallel edges are "
            "retained per generator, and two from one is a duplicate"
        )
    # Each parallel candidate carries its OWN evidence, not a shared or merged tuple.
    for pair in parallel:
        items = [
            candidate.evidence[0].kind
            for candidate in graph.candidates
            if (candidate.source_event_id, candidate.target_event_id) == pair
        ]
        assert len(set(items)) > 1, "parallel edges must carry different evidence kinds"


def test_the_graph_is_in_canonical_sequence() -> None:
    """`CONVENTIONS.md` §11: an unsequenced multigraph serializes two ways."""
    keys = [candidate.sort_key() for candidate in _graph().candidates]
    assert keys == sorted(keys)


def test_every_candidate_carries_inspectable_evidence() -> None:
    """LAW-EVIDENCE. An item nobody can re-execute is a defect, not a weak item."""
    for candidate in _graph().candidates:
        assert candidate.evidence
        for item in candidate.evidence:
            assert item.description.strip()
            assert item.verification.strip()
            assert item.supporting_ids


def test_no_candidate_claims_inferred_or_observed_provenance() -> None:
    """Module 9 proposes. It never promotes, and causation is never read from a record."""
    for candidate in _graph().candidates:
        assert candidate.provenance_class.value in ("ASSUMED", "STATISTICAL")
