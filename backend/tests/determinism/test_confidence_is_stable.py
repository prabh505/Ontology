"""Two scorings of one input are byte-identical (`CONVENTIONS.md` §11).

Following `test_candidate_graph_is_stable.py`, one layer on. Determinism here is not an
abstract nicety: a confidence vector that differs between two runs over one dataset cannot
be audited, because the number a reader is disagreeing with is not the number that will be
recomputed.

The dangerous non-determinism in this module is dictionary iteration -- the fusion groups
candidates in a dict, the base rates index tables in one, and the report tallies components
in one. `PYTHONHASHSEED` is pinned in the Makefile for exactly that reason, and this test is
what would notice if a sort were dropped anyway.
"""

from __future__ import annotations

from causalog.causal_engine.candidate_cause_generator import (
    GenerationContext,
    generate_candidates,
)
from causalog.causal_engine.confidence_scorer import (
    ScoringResult,
    render_markdown,
    score_candidates,
)
from causalog.core.serialization import to_canonical_json
from causalog.rule_engine import CandidateGenerationSpec
from causalog.rule_engine.facts import FactSet
from fixtures.candidates import (
    RUN_ID,
    envelope,
    linear_process,
    scoring_context_for,
    scoring_parameters,
    window,
)


def _run(reverse: bool) -> ScoringResult:
    """Score one fixed input, optionally handing the candidates over in reverse sequence."""
    events, timelines = [], []
    for subject in ("A", "B", "C"):
        _, produced, built = linear_process(
            "STAGE_ONE", "STAGE_TWO", "STAGE_THREE", subject=subject
        )
        events.extend(produced)
        timelines.append(built)
    events, timelines = tuple(events), tuple(timelines)

    generated = generate_candidates(
        GenerationContext(
            facts=FactSet.of(events=events),
            timelines=timelines,
            parameters=CandidateGenerationSpec(
                proximity_windows=(
                    window("STAGE_ONE", "STAGE_TWO"),
                    window("STAGE_TWO", "STAGE_THREE"),
                ),
                minimum_support_count=1,
                historical_frequency_strength=0.4,
                minimum_lift=1.0,
                statistical_association_strength=0.2,
                shared_entity_strength=0.55,
                per_effect_candidate_cap=20,
            ),
            rule_evaluation=None,
            run_id=RUN_ID,
        ),
        envelope(),
    )
    candidates = generated.graph.candidates
    if reverse:
        candidates = tuple(reversed(candidates))
    context = scoring_context_for(
        events,
        timelines,
        scoring_parameters(),
        confounding_flags=generated.confounding_flags,
        proposed_pairs=frozenset(
            (candidate.source_event_id, candidate.target_event_id)
            for candidate in generated.graph.candidates
        ),
    )
    return score_candidates(candidates, context, envelope())


def test_two_scorings_of_one_input_are_byte_identical() -> None:
    """The graph and the report both serialize identically across runs."""
    first, second = _run(reverse=False), _run(reverse=False)
    assert to_canonical_json(first.graph) == to_canonical_json(second.graph)
    assert to_canonical_json(first.report) == to_canonical_json(second.report)


def test_the_input_sequence_does_not_change_the_output() -> None:
    """Candidates arrive in whatever sequence the caller had; the answer must not depend on it.

    Sequencing is applied at the boundary rather than assumed of the caller, which is the
    same choice `FactSet.of` and module 9's `CandidateGraph` both make.
    """
    forward, backward = _run(reverse=False), _run(reverse=True)
    assert to_canonical_json(forward.graph) == to_canonical_json(backward.graph)


def test_the_rendered_report_is_stable_too() -> None:
    """A committed report that differs between two runs cannot be reviewed as a diff."""
    assert render_markdown(_run(reverse=False).report) == render_markdown(_run(reverse=True).report)
