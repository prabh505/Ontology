"""The pipeline entry point the determinism gate executes (`python -m`).

`scripts/check_determinism.py` has exited 2 `NOT-YET-RUNNABLE` since P0 because this module
did not exist, and its CI job carries `continue-on-error` for that reason alone (OQ-014).
This is the entry point it looks for: run the pipeline once, write every artifact as
canonical JSON into `--output`, and exit.

**It refuses to produce nothing.** Two runs that both fail identically are byte-identical,
so an entry point that exited 0 on an unmaterialized dataset would hand the determinism
gate a pass it did not earn -- the "passed on having no work to do" failure this
repository's own budget tests are written to avoid, arriving in the gate that is supposed
to catch it. So a run that reaches no `run_id`, or that produces no events, exits non-zero
and says which stage refused. A gate that cannot run must never look like a gate that
passed.

Every artifact is written through `core.serialization.to_canonical_json`: sorted keys,
quantized floats, ISO-8601 UTC instants. That is what makes a byte-for-byte diff meaningful
rather than a report of formatting noise.

Exit codes
----------
    0  the pipeline ran and wrote its artifacts
    1  a stage refused, or the run produced nothing to compare
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from causalog.core.ports.jobs import StageStatus
from causalog.core.serialization import to_canonical_json
from causalog.orchestration.jobs import (
    JobOutcome,
    new_execution_id,
    new_job_record,
    run_job,
)
from causalog.orchestration.stages import PIPELINE_STAGES, PipelineRequest
from causalog.orchestration.wiring import SystemClock
from causalog.persistence.memory.fakes import InMemoryJobStore

__all__ = ["main"]

#: Written for every execution, so the gate compares the pipeline's SHAPE as well as its
#: artifacts. `elapsed_seconds` is excluded here rather than normalized away downstream:
#: a measurement is not an output (`CONVENTIONS.md` §11).
_STAGE_REPORT = "stages.json"


def _arguments() -> argparse.Namespace:
    """Parse the command line the determinism gate supplies."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", default="dataco", help="the domain to run")
    parser.add_argument("--seed", type=int, default=0, help="participates in run_id")
    parser.add_argument("--rows", type=int, default=150, help="0 removes the bound")
    parser.add_argument("--output", type=Path, required=True, help="artifact directory")
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[4],
        help="where ontology/, rule_engine/ and datasets/ live",
    )
    return parser.parse_args()


def _write(destination: Path, name: str, payload: str) -> None:
    """Write one artifact, creating the directory on first use."""
    destination.mkdir(parents=True, exist_ok=True)
    destination.joinpath(name).write_text(payload, encoding="utf-8")


def _write_artifacts(outcome: JobOutcome, destination: Path) -> int:
    """Write every artifact the run produced. Returns how many were written."""
    state = outcome.state
    written = 0

    stages = [
        {
            "stage_id": stage.stage_id,
            "status": outcome.statuses.get(stage.stage_id, StageStatus.PENDING).value,
            "requires": list(stage.requires),
            "runnable": stage.is_runnable,
        }
        for stage in PIPELINE_STAGES
    ]
    _write(
        destination,
        _STAGE_REPORT,
        json.dumps(
            {"stages": stages, "measurements": state.measurements},
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    written += 1

    if state.envelope is not None:
        _write(destination, "envelope.json", to_canonical_json(state.envelope) + "\n")
        written += 1
    for name, artifacts in (
        ("events.json", state.events),
        ("entities.json", state.entities),
        ("timelines.json", state.timelines),
        ("states.json", state.states),
        ("transitions.json", state.transitions),
    ):
        if artifacts:
            _write(
                destination,
                name,
                "[\n" + ",\n".join(to_canonical_json(item) for item in artifacts) + "\n]\n",
            )
            written += 1
    if state.construction is not None:
        _write(
            destination,
            "causal-graph.json",
            to_canonical_json(state.construction.graph) + "\n",
        )
        written += 1
    if state.scoring_report is not None:
        _write(destination, "confidence.json", to_canonical_json(state.scoring_report) + "\n")
        written += 1
    return written


def main() -> int:
    """Run the pipeline once and write its artifacts, or refuse loudly."""
    arguments = _arguments()
    clock = SystemClock()
    store = InMemoryJobStore()
    execution_id = new_execution_id()
    store.create_job(
        new_job_record(
            execution_id=execution_id,
            dataset_id=arguments.dataset,
            requested_by="determinism-gate",
            correlation_id=None,
            idempotency_key=None,
            clock=clock,
        )
    )
    outcome = run_job(
        store=store,
        clock=clock,
        request=PipelineRequest(
            dataset_id=arguments.dataset,
            repository_root=arguments.repository_root,
            rows=arguments.rows,
            seed=arguments.seed,
        ),
        execution_id=execution_id,
    )

    refused = [
        (transition.stage_id, transition.detail)
        for transition in store.transitions(execution_id)
        if transition.status is StageStatus.FAILED
    ]

    _write_artifacts(outcome, arguments.output)

    if outcome.state.envelope is None or not outcome.state.events:
        print(
            "PIPELINE: the run produced nothing to compare, so it exits non-zero rather "
            "than handing the determinism gate a pass it did not earn -- two runs that "
            "both fail identically are byte-identical.",
            file=sys.stderr,
        )
        for stage_id, detail in refused:
            print(f"  REFUSED {stage_id}: {detail}", file=sys.stderr)
        if not refused:
            print(
                "  No stage refused; the dataset is materialized but empty.",
                file=sys.stderr,
            )
        return 1

    print(
        f"PIPELINE: run {outcome.state.envelope.run_id} finished {outcome.status.value}; "
        f"{outcome.state.measurements.get('events', 0):,} event(s) written to "
        f"{arguments.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
