#!/usr/bin/env python3
"""Run modules 11 and 12 and the pattern miner over a clean layer, under BOTH standings.

Wiring, in the sense `build_causal_graph.py` is wiring, and its direct sibling: it imports
that script's `run_pipeline` rather than re-implementing the nine stages, so the two reports
describe one slice and cannot disagree about it.

WHY IT RUNS TWICE
-----------------
`STATED` walks the promoted graph -- the engine's claims. On the committed bounded run that
graph is EMPTY: 0 of 9,492 claims promoted, 79.3% of them stopped by the temporal verdict
rather than by any threshold (R-22). A strict analysis therefore answers every question with
silence. Silence is a TRUE answer and it is reported as the headline finding; it also shows a
reader nothing about whether the machinery works.

So the same analyzers run a second time over module 10's scored graph, before promotion,
under the `UNPROMOTED_DIAGNOSTIC` standing. **Everything that run produces is disowned** --
by the type that carries it, by a validator that refuses `INFERRED` on it, and by a fixed
notice printed above every table. It is published so the reason the stated view is empty is
visible as a property of the inputs rather than as an absence of output.

The two are written to separate files. Nothing merges them.

Exit codes
----------
    0  both runs completed and the reports were written
    1  the pack, the mapping, the rule pack or the clean layer was refused or is missing
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_causal_graph import BOUNDED_NOTICE, DEFAULT_ROWS, Pipeline, run_pipeline  # noqa: E402
from causalog.causal_engine.pattern_miner import mine_patterns  # noqa: E402
from causalog.causal_engine.pattern_miner import render_markdown as render_patterns  # noqa: E402
from causalog.causal_engine.propagation_analyzer import (  # noqa: E402
    GraphStanding,
    GraphView,
    PropagationContext,
    analyze_propagation,
    diagnostic_view,
    stated_view,
)
from causalog.causal_engine.propagation_analyzer import (  # noqa: E402
    render_markdown as render_propagation,
)
from causalog.causal_engine.root_cause_analyzer import (  # noqa: E402
    RootCauseContext,
    RootCauseResult,
    analyze_root_causes,
)
from causalog.core.errors import CausaLogError  # noqa: E402
from causalog.core.measurement import evaluate_measurement  # noqa: E402
from causalog.core.serialization import to_canonical_json  # noqa: E402
from causalog.core.types import Event, TimelineEntryKind, TimelineView  # noqa: E402
from causalog.extraction.ontology_adapters import (  # noqa: E402
    actionability_of,
    cost_classes_of,
    magnitude_measurements_of,
    severity_classes_of,
)
from causalog.rule_engine.facts import FactSet  # noqa: E402

DATASET_ID = "dataco"

#: How many worked cases the report carries. prd.md gives no number; five is what a reader
#: will actually read, and every case is written out in full rather than tabulated.
DEFAULT_CASES = 5


def _arguments() -> argparse.Namespace:
    """Parse the command line. Mirrors `build_causal_graph.py`'s, because it feeds it."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", default=DATASET_ID, help="pack identifier")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--cases", type=int, default=DEFAULT_CASES)
    parser.add_argument(
        "--clean-layer", type=Path, default=REPO_ROOT / "datasets" / "clean"
    )
    parser.add_argument("--reports", type=Path, default=REPO_ROOT / "docs" / "reports")
    parser.add_argument("--data-quality-report", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def _worst_outcomes(
    pipeline: Pipeline, count: int
) -> tuple[tuple[str, float, str], ...]:
    """Return the `count` process instances with the largest declared delay, worst first.

    Selection is domain-flavoured -- it reads the pack's primary delay measurement by name --
    and it lives HERE rather than in a module for that reason. `scripts/` is outside the
    LAW-DOMAIN scan precisely so that wiring may name what the engine may not, and choosing
    which cases to write up is wiring.

    Returns `(outcome_event_id, delay_reading, timeline_id)` triples. The outcome is the LAST
    event of the instance, because that is the thing a reader wants explained.
    """
    pack = pipeline.pack.pack  # type: ignore[attr-defined]
    measurements = {item.id: item for item in magnitude_measurements_of(pack)}
    primary = next(
        (
            item
            for item in pipeline.rules.pack.graph_construction.magnitude_attributions  # type: ignore[attr-defined]
        ),
        None,
    )
    if primary is None or primary.measurement_id not in measurements:
        return ()
    measurement = measurements[primary.measurement_id]
    events_by_id = {event.event_id: event for event in pipeline.events}
    scored: list[tuple[str, float, str]] = []
    for timeline in pipeline.timelines:
        if timeline.view is not TimelineView.PROCESS_INSTANCE:
            continue
        members = [
            events_by_id[entry.event_id]
            for entry in timeline.entries
            if entry.kind is TimelineEntryKind.EVENT
            and entry.event_id is not None
            and entry.event_id in events_by_id
        ]
        if not members:
            continue
        by_type: dict[str, Event] = {}
        for member in members:
            by_type.setdefault(member.event_type, member)
        reading = evaluate_measurement(
            measurement.expression, by_type, caller="scripts.analyze_root_causes"
        )
        if reading is None or reading <= 0.0:
            continue
        scored.append((members[-1].event_id, reading, timeline.timeline_id))
    # Worst first, ties broken on identifier so two runs choose one set of cases.
    scored.sort(key=lambda item: (-item[1], item[0]))
    return tuple(scored[:count])


def _context(pipeline: Pipeline, view: GraphView) -> PropagationContext:
    """Assemble module 12's context over one standing's view."""
    pack = pipeline.pack.pack  # type: ignore[attr-defined]
    return PropagationContext(
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


def _ranking_context(
    pipeline: Pipeline, propagation: PropagationContext
) -> RootCauseContext:
    """Assemble module 11's context, with the actionability views flattened by the adapter."""
    pack = pipeline.pack.pack  # type: ignore[attr-defined]
    return RootCauseContext(
        propagation=propagation,
        actionability=actionability_of(pack),
        cost_classes=cost_classes_of(pack),
        severity_classes=severity_classes_of(pack),
        parameters=pipeline.rules.pack.root_cause_analysis,  # type: ignore[attr-defined]
        run_id=pipeline.envelope.run_id,
    )


def _case_section(index: int, delay: float, result: RootCauseResult) -> str:
    """Render one worked case: the four views, the tree, and the evidence behind each."""
    ranking = result.ranking
    tree = result.propagation.tree
    lines = [
        f"## Case {index}",
        "",
        f"- outcome: `{ranking.outcome_event_id}`",
        f"- declared delay on this instance: **{delay:.6f}**",
        f"- standing: `{ranking.standing.value}`",
        f"- candidates considered: {len(ranking.considered)}",
        "",
    ]
    if not ranking.considered:
        lines.extend(
            [
                "**No candidate cause.** Nothing in this view leads to the outcome, so "
                "there is no chain to rank and no propagation to measure. That is a "
                "statement about the graph and not about the outcome.",
                "",
            ]
        )
        return "\n".join(lines)
    lines.extend(
        [
            "### The four views",
            "",
            "| view | event | type | actionable |",
            "|---|---|---|---|",
        ]
    )
    for label, view in (
        ("EARLIEST_EVENT", ranking.earliest_cause),
        ("HIGHEST_CONSEQUENCE_EVENT", ranking.highest_consequence_cause),
        ("MOST_ACTIONABLE_EVENT", ranking.most_actionable_cause),
        (
            "RECOMMENDED_ROOT_CAUSE",
            ranking.actionable_root_causes[0]
            if ranking.actionable_root_causes
            else None,
        ),
    ):
        if view is None:
            lines.append(f"| `{label}` | *none* | -- | -- |")
        else:
            lines.append(
                f"| `{label}` | `{view.event_id[:20]}` | `{view.event_type}` | "
                f"{'yes' if view.actionability.is_actionable else 'no'} |"
            )
    lines.append("")
    if ranking.views_agree:
        lines.extend(["The four views agree: this is a simple chain.", ""])
    for record in ranking.trade_offs:
        lines.extend(
            [
                f"**Trade-off — `{record.first_view.value}` vs `{record.second_view.value}`.** "
                f"`{record.first_event_id[:20]}` against `{record.second_event_id[:20]}`.",
                "",
            ]
        )
    lines.extend(
        [
            "### Propagation from the recommended cause",
            "",
            f"- depth **{tree.depth}**, breadth **{tree.breadth}** (never averaged)",
            f"- consequences reached: {len(tree.nodes)}",
            f"- affected entities: {result.report.candidates_considered}",
            "- combined magnitude: "
            + (
                f"**{tree.consequences.combined:.6f}** {tree.consequences.unit} under "
                f"`{tree.consequences.combination}`, resting on "
                f"{tree.consequences.measured_member_count} of {len(tree.nodes)} consequence(s)"
                if tree.consequences.combined is not None
                else "none — "
                + (tree.consequences.combination_absent_because or "reason unrecorded")
            ),
            "",
            "### Ranked causes",
            "",
            "| cause | type | actionable | earliness | prevents | chain | links | recurs |",
            "|---|---|---|---:|---|---:|---:|---:|",
        ]
    )
    for cause in ranking.considered[:8]:
        prevents = (
            f"{cause.prevented_magnitude:.6f} {cause.prevented_unit or ''}".strip()
            if cause.prevented_magnitude is not None
            else "not measurable"
        )
        lines.append(
            f"| `{cause.event_id[:20]}` | `{cause.event_type}` | "
            f"{'yes' if cause.actionability.is_actionable else 'no'} | "
            f"{cause.earliness_rank} | {prevents} | {cause.chain.composed:.6f} | "
            f"{cause.chain.path_length} | {cause.recurrence.occurrences} |"
        )
    lines.append("")
    flagged = [
        cause for cause in ranking.considered if cause.partial_data_flag is not None
    ]
    if flagged:
        lines.extend(
            [
                f"**{len(flagged)} of {len(ranking.considered)} chain(s) carry a partial-data "
                "flag.** " + (flagged[0].partial_data_flag or ""),
                "",
            ]
        )
    return "\n".join(lines)


def _run_standing(
    pipeline: Pipeline,
    view: GraphView,
    cases: tuple[tuple[str, float, str], ...],
    label: str,
) -> tuple[str, list[str]]:
    """Run modules 12 and 11 and the miner under one standing; return markdown and paths."""
    propagation = _context(pipeline, view)
    ranking_context = _ranking_context(pipeline, propagation)
    sections = [
        f"# Root Cause Analysis — {label}",
        "",
        f"- standing: `{view.standing.value}`",
        f"- `run_id`: `{pipeline.envelope.run_id}`",
        f"- links available in this view: {view.link_count():,}",
        "",
    ]
    if view.standing is GraphStanding.UNPROMOTED_DIAGNOSTIC:
        from causalog.causal_engine.propagation_analyzer import (
            DIAGNOSTIC_NOT_STATED_NOTICE,
        )

        sections.extend([f"> **{DIAGNOSTIC_NOT_STATED_NOTICE}**", ""])
    if not cases:
        sections.extend(
            [
                "No case could be selected: the pack's primary delay measurement evaluated "
                "to nothing positive on every process instance in this slice.",
                "",
            ]
        )
    for index, (outcome, delay, _) in enumerate(cases, start=1):
        result = analyze_root_causes(outcome, ranking_context, pipeline.envelope)
        sections.append(_case_section(index, delay, result))
    return "\n".join(sections), []


def main() -> int:
    """Run the analysis under both standings and write both sets of reports."""
    arguments = _arguments()
    try:
        pipeline = run_pipeline(arguments)
    except CausaLogError as failure:
        print(f"pipeline REFUSED\n{failure}", file=sys.stderr)
        return 1
    if pipeline is None:
        return 1

    cases = _worst_outcomes(pipeline, arguments.cases)
    print(f"[10/12] cases            {len(cases)} selected by declared delay")

    destination = arguments.reports / arguments.dataset / pipeline.dataset_version
    destination.mkdir(parents=True, exist_ok=True)
    notice = (
        BOUNDED_NOTICE.format(rows=arguments.rows, total=pipeline.row_count)
        if arguments.rows
        else ""
    )

    stated = stated_view(pipeline.construction.graph)  # type: ignore[attr-defined]
    diagnostic = diagnostic_view(pipeline.scored)

    for view, label, stem in (
        (stated, "the engine's stated view", "root-cause-cases"),
        (diagnostic, "the unpromoted diagnostic view", "root-cause-cases-diagnostic"),
    ):
        rendered, _ = _run_standing(pipeline, view, cases, label)
        if notice:
            rendered = rendered.replace(
                rendered.splitlines()[0], rendered.splitlines()[0] + "\n\n" + notice, 1
            )
        (destination / f"{stem}.md").write_text(rendered, encoding="utf-8")
        print(f"        report           {destination / f'{stem}.md'}")

        propagation = _context(pipeline, view)
        suffix = "" if view.standing is GraphStanding.STATED else "-diagnostic"
        if cases:
            tree = analyze_propagation(cases[0][0], propagation, pipeline.envelope)
            (destination / f"propagation{suffix}.md").write_text(
                render_propagation(tree.report), encoding="utf-8"
            )
            (destination / f"propagation{suffix}.json").write_text(
                to_canonical_json(tree.report), encoding="utf-8"
            )
        patterns = mine_patterns(
            propagation,
            pipeline.rules.pack.pattern_mining,  # type: ignore[attr-defined]
            pipeline.envelope,
        )
        (destination / f"patterns{suffix}.md").write_text(
            render_patterns(patterns), encoding="utf-8"
        )
        (destination / f"patterns{suffix}.json").write_text(
            to_canonical_json(patterns), encoding="utf-8"
        )
        print(
            f"        patterns         {len(patterns.motifs)} motif(s), "
            f"{len(patterns.bottlenecks)} bottleneck(s) [{view.standing.value}]"
        )
    return 0


raise SystemExit(main())
