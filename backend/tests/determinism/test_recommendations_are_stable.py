"""Two runs of one recommendation query produce byte-identical bytes, and identical prose.

The candidate set is handed over in two different SEQUENCES rather than merely re-run. A
module that happened to sort its output while reading its input in insertion sequence would
pass a naive rerun test and produce two different artifacts the first time a caller assembled
its facts differently -- the failure `test_root_cause_is_stable.py` states and this one
inherits.

Module 14 has more places to get this wrong than its siblings, because it holds several
dictionaries keyed by occurrence identifier and a subset enumeration whose sequence is the
sequence its input arrived in. Each of those is a place where an unsorted read would produce
a ranking that changes between runs while every figure in it stays correct -- the hardest
kind of non-determinism to notice, because nothing looks wrong.
"""

from __future__ import annotations

import pytest

from causalog.core.serialization import to_canonical_json
from causalog.recommendation_engine import (
    RecommendationResult,
    build_report,
    optimize,
    render_markdown,
)
from fixtures.candidates import envelope
from fixtures.propagation import MEASURED
from fixtures.recommendation import bottleneck_shape, recommendation_context

pytestmark = pytest.mark.determinism


def _run(reverse: bool) -> tuple[RecommendationResult, str, str]:
    """Run the optimizer once, optionally handing the outcomes over in reverse sequence."""
    events, graph, _ = bottleneck_shape()
    # The measured consequences of the shape. Named explicitly rather than derived from a
    # magnitude field `Event` does not carry: which outcome matters is the caller's to say,
    # and this fixture is the caller.
    outcomes = tuple(sorted(event.event_id for event in events if event.event_type == MEASURED))
    context = recommendation_context(
        events, graph, outcomes=tuple(reversed(outcomes)) if reverse else outcomes
    )
    result = optimize(context, envelope())
    report = build_report(result, context, envelope())
    return result, to_canonical_json(report), render_markdown(report)


def test_two_runs_produce_byte_identical_reports() -> None:
    """`CONVENTIONS.md` §11: same inputs, same seed, same ontology hash, same bytes."""
    _, first_json, first_prose = _run(reverse=False)
    _, second_json, second_prose = _run(reverse=True)

    assert first_json == second_json
    assert first_prose == second_prose


def test_the_run_is_not_empty() -> None:
    """A determinism test over an empty artifact passes and proves nothing (DEF-0001)."""
    result, rendered, _ = _run(reverse=False)

    assert result.discovery.candidates
    assert result.recommendations or result.withheld
    assert len(rendered) > 500


def test_every_published_sequence_is_canonical() -> None:
    """Sorted memberships and sorted ledgers, so a digest over the artifact is stable."""
    result, _, _ = _run(reverse=False)

    for entry in result.recommendations:
        assert list(entry.node_event_ids) == sorted(set(entry.node_event_ids))
        assert list(entry.affected_event_ids) == sorted(set(entry.affected_event_ids))
        assert list(entry.evidence_item_ids) == sorted(set(entry.evidence_item_ids))
        assert list(entry.risks) == sorted(entry.risks)

    keys = [entry.sort_key() for entry in result.recommendations]
    assert keys == sorted(keys)

    ledger = [entry.sort_key() for entry in result.withheld]
    assert ledger == sorted(ledger)

    refused = [entry.sort_key() for entry in result.discovery.refused]
    assert refused == sorted(refused)


def test_the_declared_weights_travel_on_every_recommendation() -> None:
    """A ranking must never be readable under a weighting that did not produce it.

    Determinism's other half: the artifact is stable AND it says what made it that way, so a
    reader who recomputes the sequencing gets the same answer rather than a different one
    under whatever the pack happens to declare today.
    """
    result, _, _ = _run(reverse=False)

    for entry in result.recommendations:
        assert entry.objective_weights
        assert list(entry.objective_weights) == sorted(entry.objective_weights)
        assert entry.scalarization is not None
