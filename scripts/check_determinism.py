#!/usr/bin/env python3
"""Determinism gate: run the pipeline twice and diff the outputs byte for byte.

`CONVENTIONS.md` §11 -- identical inputs + identical seed + identical ontology hash imply
byte-identical outputs. Byte-identical covers every persisted artifact, every API response
body, every generated identifier, every serialized graph, and every explanation sentence.

It does NOT cover `execution_id`, `correlation_id`, wall-clock log timestamps, or
performance measurements. Those are the only permitted sources of run-to-run variation and
they are excluded HERE, explicitly, rather than accidentally.

Exit codes:
    0  two runs agree
    1  two runs disagree -- determinism is broken
    2  NOT-YET-RUNNABLE -- no pipeline entry point exists yet
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_SRC = REPO_ROOT / "backend" / "src"
ENTRY_POINT = BACKEND_SRC / "causalog" / "orchestration" / "pipeline.py"
WORK_ROOT = REPO_ROOT / ".determinism"

# Values that are permitted to differ between two runs of the same Run. Each pattern is
# replaced with a stable placeholder before the diff.
VOLATILE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r'"execution_id"\s*:\s*"[^"]*"', '"execution_id":"<volatile>"'),
    (r'"correlation_id"\s*:\s*"[^"]*"', '"correlation_id":"<volatile>"'),
    (r'"elapsed_seconds"\s*:\s*[0-9.]+', '"elapsed_seconds":<volatile>'),
    (
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
        "<instant>",
    ),
)


def normalize(text: str) -> str:
    """Blank out the permitted sources of variation."""
    for pattern, replacement in VOLATILE_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text


def run_once(destination: Path, seed: str) -> None:
    """Execute the pipeline into a fresh output directory."""
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    environment = dict(os.environ)
    environment["PYTHONHASHSEED"] = "0"
    environment["PYTHONPATH"] = str(BACKEND_SRC)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "causalog.orchestration.pipeline",
            "--seed",
            seed,
            "--output",
            str(destination),
        ],
        check=True,
        env=environment,
        cwd=REPO_ROOT,
    )


def compare(left: Path, right: Path) -> int:
    """Diff two output trees after normalization; return the mismatch count."""
    left_files = sorted(p.relative_to(left) for p in left.rglob("*") if p.is_file())
    right_files = sorted(p.relative_to(right) for p in right.rglob("*") if p.is_file())
    mismatches = 0
    if left_files != right_files:
        print("DETERMINISM: the two runs produced different file sets.")
        for missing in sorted(set(left_files) ^ set(right_files)):
            print(f"  only in one run: {missing}")
        mismatches += 1
    for relative in left_files:
        if relative not in right_files:
            continue
        a = normalize((left / relative).read_text(errors="replace"))
        b = normalize((right / relative).read_text(errors="replace"))
        if a != b:
            print(f"DETERMINISM: {relative} differs between runs after normalization.")
            mismatches += 1
    return mismatches


def main() -> int:
    """Run twice with the same seed and compare."""
    if not ENTRY_POINT.exists():
        print(
            "DETERMINISM: NOT-YET-RUNNABLE.\n"
            f"  No pipeline entry point at {ENTRY_POINT.relative_to(REPO_ROOT).as_posix()}.\n"
            "  The determinism gate is a Definition-of-Done item for every module\n"
            "  (CONVENTIONS.md §3, §11). Until the orchestration pipeline exists it cannot\n"
            "  run, and this script reports that fact loudly rather than exiting 0 and\n"
            "  letting a missing gate look like a passing one.\n"
            "  Tracked in PROGRESS.md as a known gap. Becomes blocking at the P1 exit."
        )
        return 2

    seed = "0"
    run_once(WORK_ROOT / "run_a", seed)
    run_once(WORK_ROOT / "run_b", seed)
    mismatches = compare(WORK_ROOT / "run_a", WORK_ROOT / "run_b")
    if mismatches:
        print(f"\nDETERMINISM: {mismatches} mismatch(es). BUILD FAILED.")
        return 1
    print("DETERMINISM: two runs are byte-identical after excluding volatile fields.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
