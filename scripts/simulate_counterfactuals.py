#!/usr/bin/env python3
"""Run module 13 over a clean layer, under BOTH standings, on the PRD's own worked example.

Wiring, in the sense `analyze_root_causes.py` is wiring, and its direct sibling: it imports
`build_causal_graph.py`'s `run_pipeline` rather than re-implementing the nine stages, so
every report in this directory describes one slice and cannot disagree about it.

THE QUESTION THIS ASKS
----------------------
prd.md §11 Category D, verbatim:

    "If inventory reconciliation occurred within thirty minutes, would delivery still be
     delayed?"

Note the form. It is a YES/NO question about whether a delay persists, not a request for a
number, and the PRD gives no answer, no method, no assumption list and no statement of what
would make an answer trustworthy. Expressing it as a typed intervention is this script's
job: the reconciliation step is moved so that it occurs within thirty minutes of the start
of its own process instance, and the engine is asked what the graph then says about the
consequences downstream of it.

`scripts/` is outside the LAW-DOMAIN scan precisely so that wiring may name what the engine
may not. The event type below is a DataCo type name; the engine never sees it as anything
but an opaque string.

WHY IT RUNS TWICE
-----------------
`STATED` walks the promoted graph. On the committed bounded run that graph is EMPTY -- 0 of
9,492 claims promoted, because not one of the slice's occurrences carries an `OBSERVED`
timestamp so no temporal verdict is `CERTAIN` (R-22). A strict run therefore answers the
question with "there is no world to simulate", which is a TRUE answer about the inputs and
tells a reader nothing about whether the machinery works.

So the same query runs a second time over module 10's scored graph, before promotion, under
the `UNPROMOTED_DIAGNOSTIC` standing. **Module 13 refuses that input by default** (OQ-026);
this script passes `accept_unpromoted=True` explicitly, which is the deliberate act at a
named call site ADR-0072 requires. Everything that run produces is disowned -- by the report
that carries it, by the fixed notice above every table, and by being written to separate
files that nothing merges.

Exit codes
----------
    0  both runs completed and the reports were written
    1  the pack, the mapping, the rule pack or the clean layer was refused or is missing
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_causal_graph import BOUNDED_NOTICE, DEFAULT_ROWS, Pipeline, run_pipeline  # noqa: E402
from causalog.causal_engine.propagation_analyzer import (  # noqa: E402
    GraphStanding,
    GraphView,
    PropagationContext,
    diagnostic_view,
    stated_view,
)
from causalog.core.errors import CausaLogError  # noqa: E402
from causalog.core.serialization import to_canonical_json  # noqa: E402
from causalog.core.types import Event, TimelineEntryKind, TimelineView  # noqa: E402
from causalog.counterfactual_engine import (  # noqa: E402
    Intervention,
    ShiftTiming,
    SimulationContext,
    render_markdown,
    simulate,
    stated_links,
    unpromoted_links,
)
from causalog.extraction.ontology_adapters import (  # noqa: E402
    lifecycles_of,
    magnitude_measurements_of,
    mutable_attributes_of,
    process_definitions_of,
)
from causalog.rule_engine.facts import FactSet  # noqa: E402

DATASET_ID = "dataco"

#: The step prd.md §11's question moves. A DataCo type name, admissible here and nowhere in
#: the engine. The pack's closest declared analogue of "inventory reconciliation" is the
#: reservation of stock against an placed request, which is the step an operator would
#: actually bring forward.
DEFAULT_STEP = "INVENTORY_RESERVED"

#: The step asked about when the named one cannot be moved. On the DataCo slice
#: `INVENTORY_RESERVED` is emitted 48 times and PLACED IN TIME ZERO TIMES -- it is one of the
#: thirteen derived types this source never timestamps (R-21) -- so prd.md §11's question
#: has no referent on this data. `SHIPMENT_DISPATCHED` is placed, is declared actionable, and
#: is prd.md §51 Workspace 5's own second example ("What if dispatch occurred earlier?").
#: Asking it instead is a SUBSTITUTION, is stated as one in the report, and is not the
#: question prd.md §11 asked.
FALLBACK_STEP = "SHIPMENT_DISPATCHED"

#: prd.md §11's "within thirty minutes", as the engine measures time.
DEFAULT_WINDOW_MINUTES = 30


def _arguments() -> argparse.Namespace:
    """Parse the command line. Mirrors its two sibling scripts', because it feeds on one."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", default=DATASET_ID, help="pack identifier")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--step", default=DEFAULT_STEP, help="the event type to move")
    parser.add_argument(
        "--fallback-step",
        default=FALLBACK_STEP,
        help=(
            "the type to ask about when the named step cannot be moved at all. The "
            "substitution is stated in the report, never made silently."
        ),
    )
    parser.add_argument("--window-minutes", type=int, default=DEFAULT_WINDOW_MINUTES)
    parser.add_argument(
        "--clean-layer", type=Path, default=REPO_ROOT / "datasets" / "clean"
    )
    parser.add_argument("--reports", type=Path, default=REPO_ROOT / "docs" / "reports")
    parser.add_argument("--data-quality-report", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def _instances(pipeline: Pipeline) -> tuple[tuple[str, tuple[Event, ...]], ...]:
    """Return each process instance's occurrences, earliest first, sequenced by identifier."""
    events_by_id = {event.event_id: event for event in pipeline.events}
    held: list[tuple[str, tuple[Event, ...]]] = []
    for timeline in pipeline.timelines:
        if timeline.view is not TimelineView.PROCESS_INSTANCE:
            continue
        members = tuple(
            events_by_id[entry.event_id]
            for entry in timeline.entries
            if entry.kind is TimelineEntryKind.EVENT
            and entry.event_id is not None
            and entry.event_id in events_by_id
        )
        if members:
            held.append((timeline.timeline_id, members))
    held.sort(key=lambda item: item[0])
    return tuple(held)


def _placement_census(
    pipeline: Pipeline,
) -> tuple[tuple[str, int, int, float, float], ...]:
    """Return, per event type, how many occurrences the source PLACED and how late they sit.

    Printed whenever the named step cannot be moved, because "nothing to move" is a claim a
    reader is entitled to check. `(type, placed, unplaced, median_minutes, max_minutes)`,
    sequenced by type.

    R-21 is the reason this exists: thirteen of the eighteen emitted DataCo event types are
    100% `UNKNOWN` precision, so most of the ontology's vocabulary names occurrences the
    source never placed in time. A question about WHEN one of those happened has no
    referent, and saying so beats returning an empty answer.
    """
    placed: dict[str, list[float]] = {}
    unplaced: dict[str, int] = {}
    for _, members in _instances(pipeline):
        located = [
            member
            for member in members
            if member.occurred_at.precision.value != "UNKNOWN"
        ]
        for member in members:
            if member.occurred_at.precision.value == "UNKNOWN":
                unplaced[member.event_type] = unplaced.get(member.event_type, 0) + 1
        if not located:
            continue
        start = min(located, key=lambda item: item.occurred_at.t_earliest)
        for member in located:
            elapsed = (
                member.occurred_at.t_earliest - start.occurred_at.t_earliest
            ).total_seconds() / 60.0
            placed.setdefault(member.event_type, []).append(elapsed)
    names = sorted(set(placed) | set(unplaced))
    census: list[tuple[str, int, int, float, float]] = []
    for name in names:
        held = sorted(placed.get(name, []))
        median = held[len(held) // 2] if held else 0.0
        census.append(
            (name, len(held), unplaced.get(name, 0), median, max(held, default=0.0))
        )
    return tuple(census)


def _the_question(
    pipeline: Pipeline, step_type: str, window: timedelta
) -> tuple[Intervention | None, str]:
    """Return prd.md §11's question as a typed change, and the prose describing it.

    The step is moved so that it occurs within `window` of the START of its own process
    instance. That is prd.md's phrasing read literally -- "occurred within thirty minutes"
    is a statement about how soon the step happened, not about how far it moved.

    Returns `(None, reason)` when the slice holds no instance where the step is late, which
    is a finding about the data and is reported as one rather than worked around.
    """
    latest: tuple[float, Event] | None = None
    seen = 0
    for _, members in _instances(pipeline):
        placed = [
            member
            for member in members
            if member.occurred_at.precision.value != "UNKNOWN"
        ]
        if not placed:
            continue
        start = min(placed, key=lambda item: item.occurred_at.t_earliest)
        steps = [member for member in placed if member.event_type == step_type]
        for step in steps:
            seen += 1
            elapsed = (
                step.occurred_at.t_earliest - start.occurred_at.t_earliest
            ).total_seconds()
            if elapsed <= window.total_seconds():
                continue
            if latest is None or elapsed > latest[0]:
                latest = (elapsed, step)
    if latest is None:
        return (
            None,
            f"no process instance in this slice places a {step_type} more than "
            f"{int(window.total_seconds() // 60)} minute(s) after its own start. "
            f"{seen} placed occurrence(s) of that type were examined. There is therefore "
            "nothing for this question to move, which is a finding about the slice and not "
            "a failure of the query.",
        )
    elapsed, step = latest
    shift = -(elapsed - window.total_seconds())
    return (
        Intervention.of(
            ShiftTiming(target_event_id=step.event_id, shift_seconds=round(shift, 6)),
            rationale=(
                f"prd.md §11 Category D, expressed as a typed change: bring {step_type} "
                f"forward by {abs(shift) / 60:.1f} minute(s) so that it occurs within "
                f"{int(window.total_seconds() // 60)} minute(s) of the start of its process "
                f"instance, rather than the {elapsed / 60:.1f} minute(s) the source records."
            ),
        ),
        f"`{step.event_id}` ({step_type}) occurred {elapsed / 60:.1f} minute(s) after the "
        f"start of its process instance; the question asks what the graph says had it "
        f"occurred within {int(window.total_seconds() // 60)}.",
    )


def _census_block(
    census: tuple[tuple[str, int, int, float, float], ...], step: str
) -> list[str]:
    """Return the placement census as markdown, so "nothing to move" is checkable.

    A reader told a question cannot be posed is entitled to see why. The census is the
    evidence: per declared type, how many occurrences this source PLACED IN TIME and how many
    it emitted with no instant at all.
    """
    lines = [
        "### Why: which occurrences this source places in time",
        "",
        f"`{step}` is the step the question names. A type with **0 placed** is one this "
        "source emits without ever saying when it happened, so a question about its timing "
        "has no referent \u2014 thirteen of DataCo's declared types are in that position "
        "(R-21).",
        "",
        "| type | placed | never placed | median min. after instance start | max |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, held, missing, median, worst in census:
        marker = " **\u2190**" if name == step else ""
        lines.append(
            f"| `{name}`{marker} | {held} | {missing} | {median:.1f} | {worst:.1f} |"
        )
    lines.append("")
    return lines


def _simulation_context(pipeline: Pipeline, view: GraphView) -> SimulationContext:
    """Assemble module 13's context over one standing's view.

    The ontology arrives already flattened by `extraction.ontology_adapters` -- forbidden
    edge F3 means the engine may not read a pack, and this script is where that boundary is
    crossed for module 13.
    """
    pack = pipeline.pack.pack  # type: ignore[attr-defined]
    propagation = PropagationContext(
        facts=FactSet.of(events=pipeline.events),
        timelines=pipeline.timelines,
        view=view,
        parameters=pipeline.rules.pack.propagation_analysis,  # type: ignore[attr-defined]
        magnitude_measurements=magnitude_measurements_of(pack),
        magnitude_attributions=tuple(
            sorted(
                (item.effect_event_type, item.measurement_id)
                for item in pipeline.rules.pack.graph_construction.magnitude_attributions  # type: ignore[attr-defined]
            )
        ),
        run_id=pipeline.envelope.run_id,
    )
    # The links MUST come from the graph the view's standing describes. Indexing the
    # promoted graph while walking a scored view would report a hypothetical over an empty
    # graph as one that reached nothing -- a true-looking statement about the wrong world.
    if view.standing is GraphStanding.STATED:
        links = stated_links(pipeline.construction.graph)  # type: ignore[attr-defined]
        groups = pipeline.construction.graph.joint_groups  # type: ignore[attr-defined]
    else:
        links = unpromoted_links(pipeline.scored)  # type: ignore[arg-type]
        groups = ()
    return SimulationContext(
        propagation=propagation,
        links=links,
        joint_groups=groups,
        lifecycles=lifecycles_of(pack),
        processes=process_definitions_of(pack),
        mutability=mutable_attributes_of(pack),
        derived_precedence=pipeline.derived_precedence,  # type: ignore[arg-type]
        entities=(),
        parameters=pipeline.rules.pack.counterfactual_simulation,  # type: ignore[attr-defined]
        run_id=pipeline.envelope.run_id,
    )


def main() -> int:
    """Run the query under both standings and write both sets of reports."""
    arguments = _arguments()
    try:
        pipeline = run_pipeline(arguments)
    except CausaLogError as failure:
        print(f"pipeline REFUSED\n{failure}", file=sys.stderr)
        return 1
    if pipeline is None:
        return 1

    window = timedelta(minutes=arguments.window_minutes)
    change, description = _the_question(pipeline, arguments.step, window)
    print(f"[10/11] the question      {description}")
    census = _placement_census(pipeline)
    substitution: str | None = None
    if change is None:
        print(
            "        placement census  (type: placed / unplaced, median and max minutes)"
        )
        for name, held, missing, median, worst in census:
            print(
                f"          {name:<32} {held:>5} / {missing:<5}  "
                f"median {median:>9.1f}  max {worst:>10.1f}"
            )
        if arguments.fallback_step and arguments.fallback_step != arguments.step:
            fallback, fallback_description = _the_question(
                pipeline, arguments.fallback_step, window
            )
            if fallback is not None:
                substitution = (
                    "**THE QUESTION AS ASKED COULD NOT BE POSED, AND A DIFFERENT ONE WAS "
                    f"ANSWERED.** {description} What follows asks about "
                    f"`{arguments.fallback_step}` instead, which this source does place in "
                    "time. That is a SUBSTITUTION and not the question prd.md \u00a711 "
                    "asked: it moves a different step, so nothing below is an answer about "
                    f"`{arguments.step}`. {fallback_description}"
                )
                change = fallback
                print(f"        substituted       {arguments.fallback_step}")

    destination = arguments.reports / arguments.dataset / pipeline.dataset_version
    destination.mkdir(parents=True, exist_ok=True)
    notice = (
        BOUNDED_NOTICE.format(rows=arguments.rows, total=pipeline.row_count)
        if arguments.rows
        else ""
    )

    stated = stated_view(pipeline.construction.graph)  # type: ignore[attr-defined]
    diagnostic = diagnostic_view(pipeline.scored)

    for view, stem in (
        (stated, "counterfactual"),
        (diagnostic, "counterfactual-diagnostic"),
    ):
        context = _simulation_context(pipeline, view)
        # The opt-in is explicit and is confined to this line. Module 13 refuses a
        # non-STATED view by default (OQ-026); passing the flag here is the deliberate act
        # at a named call site that ADR-0072 requires, and everything the diagnostic run
        # produces is disowned by the report that carries it.
        accept = view.standing is not GraphStanding.STATED
        result = simulate(
            () if change is None else (change,),
            context,
            pipeline.envelope,
            accept_unpromoted=accept,
        )
        rendered = render_markdown(result.report)
        header = [
            f"> **The question (prd.md §11 Category D).** {description}",
            "",
        ]
        if substitution is not None:
            header = [f"> {substitution}", "", *_census_block(census, arguments.step)]
        elif change is None:
            header = [
                f"> **No change could be posed.** {description}",
                "",
                *_census_block(census, arguments.step),
            ]
        if notice:
            header = [notice, "", *header]
        lines = rendered.splitlines()
        rendered = "\n".join([lines[0], "", *header, *lines[1:]])
        (destination / f"{stem}.md").write_text(rendered, encoding="utf-8")
        (destination / f"{stem}.json").write_text(
            to_canonical_json(result.report), encoding="utf-8"
        )
        world = result.world
        print(
            f"        {view.standing.value:<22} links {view.link_count():>6,}  "
            f"admitted {result.report.interventions_admitted}  "
            f"reached {0 if world is None else world.diff.reached_count:>5,}  "
            f"changed {0 if world is None else len(world.diff.deltas):>5,}  "
            f"verdict {result.validity.verdict.value}"
        )
        print(f"        report           {destination / f'{stem}.md'}")
    return 0


raise SystemExit(main())
