"""Property tests over generated graphs: no promotion ever reaches an observed fact.

`tests/law/test_observed_facts_are_immutable.py` proves the `core` guarantees hold for one
artifact at a time. This file proves the *module* keeps them over arbitrary inputs, which is
where a promotion path could plausibly break them: promotion is the one operation in this
repository that rewrites a field on an artifact, and it does so on the artifact class that
sits closest to observed data.

Three properties, each stated as a sentence a reader can check the assertion against.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from causalog.causal_engine.causal_graph_builder import (
    build_causal_graph,
)
from causalog.causal_engine.causal_graph_builder import (
    graph as graph_types,
)
from causalog.core.provenance import ProvenanceClass
from causalog.core.serialization import to_canonical_json
from causalog.core.temporal import TemporalVerdict
from fixtures.candidates import envelope, linear_process
from fixtures.graphs import (
    build_context,
    candidate,
    graph_parameters,
    permissive_scoring,
    scored_graph,
)

SETTINGS = settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)


@st.composite
def _pipelines(draw: st.DrawFn) -> tuple:
    """Draw a small chain of processes, a threshold, and the proposals over them."""
    subjects = draw(st.integers(min_value=1, max_value=3))
    stages = draw(st.integers(min_value=2, max_value=4))
    floor = draw(st.sampled_from([0.0, 0.2, 0.5, 0.99]))
    step = draw(st.sampled_from([0, 1, 2]))
    types = tuple(f"STAGE_{index}" for index in range(stages))

    events: list = []
    timelines: list = []
    for index in range(subjects):
        _, produced, line = linear_process(
            *types, subject=chr(ord("A") + index), start_day=index * 20, step_days=step or 1
        )
        events.extend(produced)
        timelines.append(line)
    facts, lines = tuple(events), tuple(timelines)

    proposals = []
    for index in range(0, len(facts), stages):
        for offset in range(stages - 1):
            proposals.append(candidate(facts[index + offset], facts[index + offset + 1]))
    return facts, lines, tuple(proposals), floor


@SETTINGS
@given(pipeline=_pipelines())
def test_no_observed_artifact_is_altered_by_a_build(pipeline: tuple) -> None:
    """Whatever the graph, the events that went in come out byte-identical.

    LAW-PROVENANCE's headline sentence, asserted over the inputs rather than over the
    outputs: an inference that overwrote an observation would show up here as a changed
    canonical rendering, however the promotion decision came out.
    """
    facts, lines, proposals, floor = pipeline
    before = tuple(to_canonical_json(item) for item in facts)
    bands = permissive_scoring(floor)
    graph = scored_graph(proposals, facts, lines, bands)
    context = build_context(facts, lines, proposals, bands=bands)
    build_causal_graph(graph, context, envelope())
    assert tuple(to_canonical_json(item) for item in facts) == before
    assert all(item.provenance_class is ProvenanceClass.OBSERVED for item in facts)


@SETTINGS
@given(pipeline=_pipelines())
def test_promotion_and_rejection_together_account_for_every_claim(pipeline: tuple) -> None:
    """Nothing is dropped, whatever the thresholds. A dropped claim is an invisible one."""
    facts, lines, proposals, floor = pipeline
    bands = permissive_scoring(floor)
    graph = scored_graph(proposals, facts, lines, bands)
    context = build_context(facts, lines, proposals, bands=bands)
    result = build_causal_graph(graph, context, envelope())
    assert (
        len(result.graph.edges) + len(result.graph.demotions)
        == result.graph.claims_considered
        == len(graph.edges)
    )
    assert all(record.detail for record in result.graph.demotions)
    assert all(record.lineage.candidate_edge_ids for record in result.graph.demotions)


@SETTINGS
@given(pipeline=_pipelines())
def test_every_promoted_edge_is_law_time_clean_and_run_scoped(pipeline: tuple) -> None:
    """The invariant the frozen type enforces, checked at the module's own boundary too."""
    facts, lines, proposals, floor = pipeline
    bands = permissive_scoring(floor)
    graph = scored_graph(proposals, facts, lines, bands)
    context = build_context(facts, lines, proposals, bands=bands, parameters=graph_parameters())
    result = build_causal_graph(graph, context, envelope())
    for edge in result.graph.edges:
        assert edge.edge.provenance_class is ProvenanceClass.INFERRED
        assert edge.edge.temporal_verdict is TemporalVerdict.CERTAIN
        assert not edge.edge.temporally_unverifiable
        assert edge.edge.run_id == context.run_id
        assert 0.0 <= edge.weight.weight <= 1.0


@SETTINGS
@given(pipeline=_pipelines())
def test_the_stated_view_and_the_ledger_never_hold_the_same_claim(pipeline: tuple) -> None:
    """A claim is asserted or accounted for, never both. Enforced on the type."""
    facts, lines, proposals, floor = pipeline
    bands = permissive_scoring(floor)
    graph = scored_graph(proposals, facts, lines, bands)
    context = build_context(facts, lines, proposals, bands=bands)
    result = build_causal_graph(graph, context, envelope())
    promoted = {edge.sort_key() for edge in result.graph.edges}
    demoted = {record.sort_key() for record in result.graph.demotions}
    assert not promoted & demoted
    assert isinstance(result.graph, graph_types.PromotedGraph)
