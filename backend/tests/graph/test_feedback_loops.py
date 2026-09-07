"""Two circuits of identical topology, differing only in time, classified differently.

This is the module's headline assertion. prd.md §31 asks the engine to find reinforcing
loops; the failure mode it invites is reporting every cycle it finds, and on a source whose
instants are recorded coarsely almost every cycle is an artifact of unresolvable ordering
rather than a mechanism in the domain.

So the fixtures below plant **the same graph twice**. Same event types, same edges, same
generators, same process instances. The only difference is the width of the occurrence
intervals: in one the events are separated cleanly and every link is `CERTAIN`; in the other
they overlap, so every link is `UNDETERMINED` and the circuit exists *because* nobody could
tell which came first. A detector that reported both as feedback loops would be reporting
its own input's granularity as a discovery about the world.

Why the projection is over event TYPES, asserted here as well as documented: at the instance
level a `CERTAIN` verdict is a strict order, a strict order admits no cycle, and therefore an
all-`CERTAIN` circuit over event instances cannot exist.
`test_no_instance_level_cycle_is_all_certain` pins that so the design cannot be quietly
reversed.
"""

from __future__ import annotations

from causalog.causal_engine.causal_graph_builder import (
    DetectionStatus,
    LoopClassification,
    build_causal_graph,
    detect_loops,
    select,
)
from causalog.core.temporal import TemporalVerdict
from causalog.core.types import TimelineView
from fixtures.candidates import RUN_ID, envelope
from fixtures.facts import entity, event, evidence_record, interval, timeline
from fixtures.graphs import build_context, candidate, graph_parameters, scored_graph

#: One reinforcing chain, twice: an instance of the process, then a later instance whose
#: first stage was caused by the previous instance's last. That crossing is what closes the
#: circuit at the type level, and it is exactly prd.md §31's shape -- "more delays" at the
#: end of the chain are a LATER RUN of the process, not the run that started it.
TYPES = ("STAGE_ONE", "STAGE_TWO", "STAGE_THREE")


def _planted(span_days: int) -> tuple:
    """Return (events, timelines, candidates) for one planted circuit.

    `span_days=0` gives point intervals two days apart: every pair is `CERTAIN`.
    `span_days=3` gives overlapping intervals: every pair is `UNDETERMINED`, because the
    source placed both events and cannot separate them. Nothing else differs.
    """
    citation = evidence_record(f"row-planted-{span_days}")
    instances = []
    for index, subject in enumerate(("A", "B")):
        participant = entity(subject, citation=citation)
        produced = tuple(
            event(
                event_type,
                interval(index * 6 + step * 2, span_days=span_days),
                citation=citation,
                participants=(participant,),
            )
            for step, event_type in enumerate(TYPES)
        )
        instances.append(produced)

    events = tuple(item for produced in instances for item in produced)
    # PROCESS_INSTANCE, deliberately: a feedback loop's whole distinction is whether it
    # closes across RUNS of a process, so the fixture has to model runs of one.
    timelines = tuple(
        timeline(
            *produced,
            view=TimelineView.PROCESS_INSTANCE,
            process_definition_id="FIXTURE_PROCESS",
        )
        for produced in instances
    )

    proposals = []
    for produced in instances:
        for step in range(len(TYPES) - 1):
            proposals.append(candidate(produced[step], produced[step + 1]))
    # The crossing link: the first instance's last stage causes the second instance's first.
    proposals.append(candidate(instances[0][-1], instances[1][0]))
    return events, timelines, tuple(proposals)


def _detect(span_days: int, *, kinds: tuple[str, ...] = ("DIRECT",)) -> tuple:
    """Run the whole module over one planted circuit and return its detection result."""
    events, timelines, candidates = _planted(span_days)
    graph = scored_graph(candidates, events, timelines)
    context = build_context(events, timelines, candidates, graph_parameters(kinds=kinds))
    promoted = select(graph, context)
    return graph, promoted, detect_loops(graph, promoted, context)


def test_the_two_plantings_have_identical_topology() -> None:
    """If the graphs differed structurally the comparison below would prove nothing."""
    clean_graph, _, _ = _detect(0)
    murky_graph, _, _ = _detect(3)
    assert len(clean_graph.edges) == len(murky_graph.edges)
    assert [edge.edge.payload.edge_kind for edge in clean_graph.edges] == [
        edge.edge.payload.edge_kind for edge in murky_graph.edges
    ]


def test_a_planted_reinforcing_loop_is_classified_genuine() -> None:
    """Cleanly ordered, promoted on every link, and spanning two process instances."""
    _, promoted, result = _detect(0)
    assert result.status is DetectionStatus.RAN
    assert promoted.edges, "the clean planting must promote, or the test proves nothing"
    genuine = [loop for loop in result.loops if loop.classification is LoopClassification.GENUINE]
    assert len(genuine) == 1
    loop = genuine[0]
    assert set(loop.participants) == set(TYPES)
    assert len(loop.process_instance_ids) >= 2
    assert loop.classification_reason is None


def test_a_planted_spurious_cycle_is_classified_a_temporal_artifact() -> None:
    """Same topology; overlapping intervals. Never presented as a discovered loop."""
    _, promoted, result = _detect(3)
    assert result.status is DetectionStatus.RAN
    assert not promoted.edges, "an UNDETERMINED link may never be promoted (LAW-TIME)"
    assert result.loops, "the circuit is still FOUND -- it is found and then labelled"
    assert all(loop.classification is LoopClassification.TEMPORAL_ARTIFACT for loop in result.loops)
    reason = result.loops[0].classification_reason or ""
    assert "DATA ARTIFACT, NOT A DISCOVERED FEEDBACK LOOP" in reason
    assert "granularity" in reason


def test_the_two_plantings_are_classified_differently() -> None:
    """The assertion the whole file exists for, stated as one line."""
    _, _, clean = _detect(0)
    _, _, murky = _detect(3)
    clean_kinds = {loop.classification for loop in clean.loops}
    murky_kinds = {loop.classification for loop in murky.loops}
    assert clean_kinds == {LoopClassification.GENUINE}
    assert murky_kinds == {LoopClassification.TEMPORAL_ARTIFACT}
    assert clean_kinds != murky_kinds


def test_an_artifact_never_names_a_weakest_link() -> None:
    """Naming the cheapest place to break a data artifact invites acting on one."""
    _, _, murky = _detect(3)
    for loop in murky.loops:
        assert loop.weakest_link_index is None
        assert loop.loop_gain is None


def test_a_genuine_loop_names_its_weakest_link_and_its_gain() -> None:
    """Characterization (prd.md §31): participants, gain, evidence, and where to break it."""
    _, _, clean = _detect(0)
    loop = clean.loops[0]
    assert loop.loop_gain is not None
    assert loop.weakest_link_index is not None
    weakest = loop.members[loop.weakest_link_index]
    assert weakest.weight == min(member.weight for member in loop.members)
    assert all(member.supporting_pairs for member in loop.members), "evidence per link"
    assert "CANNOT EXCEED 1.0" in loop.gain_notice


def test_loop_gain_is_the_product_of_member_weights() -> None:
    """Stated arithmetic, so a reader can recompute it and disagree."""
    _, _, clean = _detect(0)
    loop = clean.loops[0]
    expected = 1.0
    for member in loop.members:
        expected = expected * member.weight
        if member.magnitude_multiplier is not None:
            expected = expected * member.magnitude_multiplier
    assert loop.loop_gain == expected


def test_an_unpromoted_but_sound_circuit_is_not_genuine() -> None:
    """A loop of hypotheses is not a loop the system asserts."""
    events, timelines, candidates = _planted(0)
    graph = scored_graph(candidates, events, timelines)
    # A pack declaring no threshold for DIRECT promotes nothing while the temporal standing
    # of every link stays exactly as clean as in the genuine case.
    context = build_context(events, timelines, candidates, graph_parameters(kinds=("CONDITIONAL",)))
    promoted = select(graph, context)
    assert not promoted.edges
    result = detect_loops(graph, promoted, context)
    assert {loop.classification for loop in result.loops} == {LoopClassification.UNPROMOTED}
    assert "does not stand behind" in (result.loops[0].classification_reason or "")


def test_a_circuit_inside_one_process_instance_is_not_a_feedback_loop() -> None:
    """prd.md §31's reinforcement runs across instances; within one it is a modelling error."""
    citation = evidence_record("row-single-instance")
    participant = entity("A", citation=citation)
    produced = tuple(
        event(
            event_type,
            interval(step * 2, span_days=3),
            citation=citation,
            participants=(participant,),
        )
        for step, event_type in enumerate((*TYPES, "STAGE_ONE_AGAIN"))
    )
    events = produced
    line = timeline(
        *events,
        view=TimelineView.PROCESS_INSTANCE,
        process_definition_id="FIXTURE_PROCESS",
    )
    candidates = (
        candidate(produced[0], produced[1]),
        candidate(produced[1], produced[2]),
        candidate(produced[2], produced[3]),
    )
    graph = scored_graph(candidates, events, (line,))
    context = build_context(events, (line,), candidates)
    result = detect_loops(graph, select(graph, context), context)
    assert LoopClassification.GENUINE not in {loop.classification for loop in result.loops}


def test_no_instance_level_cycle_is_all_certain() -> None:
    """The reason detection projects onto types at all, pinned so it cannot be reversed.

    A `CERTAIN` verdict means the cause interval strictly precedes the effect interval.
    Strict precedence is a strict order and a strict order admits no cycle, so any circuit
    over event INSTANCES contains at least one link that is not `CERTAIN`. A detector that
    ran at the instance level could therefore only ever find artifacts.
    """
    for span in (0, 3):
        graph, _, _ = _detect(span)
        instance_edges = {
            (edge.edge.source_event_id, edge.edge.target_event_id)
            for edge in graph.edges
            if edge.edge.temporal_verdict is TemporalVerdict.CERTAIN
            and not edge.edge.temporally_unverifiable
        }
        reachable = dict.fromkeys({node for pair in instance_edges for node in pair}, False)
        # A cycle exists iff a depth-first walk revisits a node on its own stack.
        adjacency: dict[str, list[str]] = {}
        for source, target in instance_edges:
            adjacency.setdefault(source, []).append(target)

        def has_cycle(
            node: str, stack: frozenset[str], edges: dict[str, list[str]] = adjacency
        ) -> bool:
            if node in stack:
                return True
            return any(has_cycle(child, stack | {node}, edges) for child in edges.get(node, []))

        assert not any(has_cycle(node, frozenset()) for node in reachable)


def test_detection_reports_not_runnable_rather_than_zero_loops() -> None:
    """A check that could not run must never read as a check that found nothing."""
    events, timelines, candidates = _planted(0)
    graph = scored_graph(candidates, events, timelines)
    context = build_context(events, timelines, candidates, graph_parameters(circuits=None))
    result = detect_loops(graph, select(graph, context), context)
    assert result.status is DetectionStatus.NOT_RUNNABLE
    assert not result.loops
    assert "circuit_enumeration_cap" in (result.requirement or "")


def test_the_report_keeps_artifacts_out_of_the_findings_section() -> None:
    """Rendering an artifact beside a genuine loop would let a reader act on one."""
    from causalog.causal_engine.causal_graph_builder import render_markdown

    events, timelines, candidates = _planted(3)
    graph = scored_graph(candidates, events, timelines)
    context = build_context(events, timelines, candidates)
    rendered = render_markdown(build_causal_graph(graph, context, envelope()).report)
    findings = rendered.split("### Genuine reinforcing loops")[1].split(
        "### Circuits that are NOT feedback loops"
    )[0]
    assert "**None.**" in findings
    assert "TEMPORAL_ARTIFACT" not in findings


def test_run_scoping_is_preserved_through_detection() -> None:
    """Every artifact stays scoped to its run (ADR-0013)."""
    events, timelines, candidates = _planted(0)
    graph = scored_graph(candidates, events, timelines)
    context = build_context(events, timelines, candidates)
    promoted = select(graph, context)
    assert promoted.run_id == RUN_ID
    assert all(edge.edge.run_id == RUN_ID for edge in promoted.edges)
