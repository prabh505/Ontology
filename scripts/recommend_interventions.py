#!/usr/bin/env python3
"""Run module 14 over a clean layer, under BOTH standings, and write both sets of reports.

Wiring, in the sense `simulate_counterfactuals.py` is wiring, and its direct sibling: it
imports `build_causal_graph.py`'s `run_pipeline` rather than re-implementing the stages, so
every report in `docs/reports/` describes one slice and cannot disagree about it.

THE QUESTION THIS ASKS
----------------------
prd.md §51's Workspace 6, and §32 and §50 behind it: which acts should an operator be shown
first, with what expected benefit, at what cost, at what operational risk, and how sure is
the engine. Not "what happened" and not "what if" -- what to DO.

WHY IT RUNS TWICE
-----------------
`STATED` walks the promoted graph. On the committed bounded run that graph is EMPTY -- 0 of
9,492 claims promoted, because not one of the slice's occurrences carries an `OBSERVED`
timestamp so no temporal verdict is `CERTAIN` (R-22). A strict run therefore recommends
nothing, which is a TRUE answer about the inputs and tells a reader nothing about whether
the machinery works.

So the same run happens a second time over module 10's scored graph, before promotion, under
the `UNPROMOTED_DIAGNOSTIC` standing. **Module 14 refuses that input by default** (OQ-026);
this script passes `accept_unpromoted=True` explicitly, which is the deliberate act at a
named call site ADR-0072 requires. Everything that run produces is disowned -- by the report
that carries it, by the fixed notices above every table, and by being written to separate
files that nothing merges.

The disowning matters more here than it did for module 13. A counterfactual is a question and
a recommendation is an instruction, so a diagnostic recommendation is an instruction derived
from claims nobody stood behind. It is published because the machinery must be shown to work
and because the withheld ledger is itself a finding; it is not operational advice, and
`PROGRESS.md` carries a per-recommendation critique saying which parts of it are artifacts of
this dataset's limitations.

WHICH OUTCOMES ARE PROTECTED
-----------------------------
"Which outcome matters" is a domain question and module 14 refuses to answer it -- the
engine has no standing to decide what an organisation wants less of. So this script names
them, in DataCo's own vocabulary, which `scripts/` may do and the engine may not. The
default is the type prd.md §29's worked example is about.

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
from causalog.causal_engine.propagation_analyzer import (  # noqa: E402
    GraphStanding,
    GraphView,
    PropagationContext,
    diagnostic_view,
    stated_view,
)
from causalog.core.errors import CausaLogError  # noqa: E402
from causalog.core.serialization import to_canonical_json  # noqa: E402
from causalog.counterfactual_engine import (  # noqa: E402
    SimulationContext,
    stated_links,
    unpromoted_links,
)
from causalog.extraction.ontology_adapters import (  # noqa: E402
    actionability_of,
    cost_classes_of,
    lifecycles_of,
    magnitude_measurements_of,
    mutable_attributes_of,
    process_definitions_of,
    risk_classes_of,
    severity_classes_of,
)
from causalog.recommendation_engine import (  # noqa: E402
    RecommendationContext,
    build_report,
    optimize,
    render_markdown,
)
from causalog.rule_engine.facts import FactSet  # noqa: E402

DATASET_ID = "dataco"

#: The outcomes worth protecting, in DataCo's own vocabulary. `scripts/` is outside the
#: LAW-DOMAIN scan precisely so that wiring may name what the engine may not; the engine
#: sees these only as opaque strings.
#:
#: `SHIPMENT_DELAYED` is prd.md §29's own subject and the pack's primary delay metric hangs
#: off the same chain. `ORDER_CANCELED` is the terminal failure -- the process ending without
#: its intended outcome -- and is included so the run is not asked to protect lateness alone.
DEFAULT_OUTCOMES = ("SHIPMENT_DELAYED", "ORDER_CANCELED")


def _arguments() -> argparse.Namespace:
    """Parse the command line. Mirrors its sibling scripts', because it feeds on one."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--dataset", default=DATASET_ID, help="pack identifier")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument(
        "--outcomes",
        nargs="*",
        default=list(DEFAULT_OUTCOMES),
        help="event TYPES whose occurrences are the outcomes worth protecting",
    )
    parser.add_argument(
        "--clean-layer", type=Path, default=REPO_ROOT / "datasets" / "clean"
    )
    parser.add_argument("--reports", type=Path, default=REPO_ROOT / "docs" / "reports")
    parser.add_argument("--data-quality-report", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def _outcome_ids(pipeline: Pipeline, wanted: tuple[str, ...]) -> tuple[str, ...]:
    """Return the occurrence identifiers of every named outcome type, sorted.

    Sorted and de-duplicated so two runs over one slice name the same outcomes in the same
    sequence (`CONVENTIONS.md` §11). An empty result is returned as empty rather than
    substituted for: a run asked to protect an outcome this slice never witnessed should
    report that it found none, not quietly protect something else.
    """
    return tuple(
        sorted(
            {
                event.event_id
                for event in pipeline.events  # type: ignore[attr-defined]
                if event.event_type in wanted
            }
        )
    )


def _recommendation_context(
    pipeline: Pipeline, view: GraphView, outcomes: tuple[str, ...]
) -> RecommendationContext:
    """Assemble module 14's context over one standing's view.

    The ontology arrives already flattened by `extraction.ontology_adapters` -- forbidden
    edge F3 means the engine may not read a pack, and this script is where that boundary is
    crossed for module 14, exactly as its sibling crosses it for module 13.
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
    # The links MUST come from the graph the view's standing describes. Indexing the promoted
    # graph while walking a scored view would report a run over an empty graph as one that
    # reached nothing -- a true-looking statement about the wrong world.
    if view.standing is GraphStanding.STATED:
        links = stated_links(pipeline.construction.graph)  # type: ignore[attr-defined]
        groups = pipeline.construction.graph.joint_groups  # type: ignore[attr-defined]
    else:
        links = unpromoted_links(pipeline.scored)  # type: ignore[arg-type]
        groups = ()
    simulation = SimulationContext(
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
    return RecommendationContext(
        propagation=propagation,
        simulation=simulation,
        actionability=actionability_of(pack),
        cost_vocabulary=cost_classes_of(pack),
        risk_vocabulary=risk_classes_of(pack),
        severity_vocabulary=severity_classes_of(pack),
        joint_groups=groups,
        loops=(),
        outcome_event_ids=outcomes,
        parameters=pipeline.rules.pack.recommendation,  # type: ignore[attr-defined]
        run_id=pipeline.envelope.run_id,
    )


def main() -> int:
    """Run the optimizer under both standings and write both sets of reports."""
    arguments = _arguments()
    try:
        pipeline = run_pipeline(arguments)
    except CausaLogError as error:
        print(f"    refused: {error}", file=sys.stderr)
        return 1
    if pipeline is None:
        return 1

    wanted = tuple(arguments.outcomes)
    outcomes = _outcome_ids(pipeline, wanted)
    destination = arguments.reports / arguments.dataset / pipeline.dataset_version
    destination.mkdir(parents=True, exist_ok=True)
    notice = (
        BOUNDED_NOTICE.format(rows=arguments.rows, total=pipeline.row_count)
        if arguments.rows
        else ""
    )

    print(
        f"    outcomes protected  {', '.join(wanted)} -> {len(outcomes)} occurrence(s)"
    )

    stated = stated_view(pipeline.construction.graph)  # type: ignore[attr-defined]
    diagnostic = diagnostic_view(pipeline.scored)

    for view, stem in (
        (stated, "recommendations"),
        (diagnostic, "recommendations-diagnostic"),
    ):
        context = _recommendation_context(pipeline, view, outcomes)
        # The opt-in is explicit and confined to this line. Module 14 refuses a non-STATED
        # view by default (OQ-026); passing the flag here is the deliberate act at a named
        # call site ADR-0072 requires, and everything the diagnostic run produces is disowned
        # by the report that carries it.
        accept = view.standing is not GraphStanding.STATED
        result = optimize(context, pipeline.envelope, accept_unpromoted=accept)
        report = build_report(result, context, pipeline.envelope)

        rendered = render_markdown(report)
        header = [
            "> **The question (prd.md §51, Workspace 6).** Which acts should an operator be "
            f"shown first, to protect {', '.join(wanted)}?",
            "",
        ]
        if notice:
            header = [notice, "", *header]
        lines = rendered.splitlines()
        rendered = "\n".join([lines[0], "", *header, *lines[1:]])
        (destination / f"{stem}.md").write_text(rendered, encoding="utf-8")
        (destination / f"{stem}.json").write_text(
            to_canonical_json(report), encoding="utf-8"
        )
        print(
            f"        {view.standing.value:<22} links {view.link_count():>6,}  "
            f"proposed {report.proposed_count:>5,}  refused {report.refused_count:>5,}  "
            f"published {report.recommended_count:>3}  withheld {report.withheld_count:>4}"
        )
        print(f"        report           {destination / f'{stem}.md'}")
    return 0


raise SystemExit(main())
