#!/usr/bin/env python3
"""Determinism gate: run the pipeline twice and diff the outputs byte for byte.

`CONVENTIONS.md` §11 -- identical inputs + identical seed + identical ontology hash imply
byte-identical outputs. Byte-identical covers every persisted artifact, every API response
body, every generated identifier, every serialized graph, and every explanation sentence.

It does NOT cover `execution_id`, `correlation_id`, wall-clock log timestamps, or
performance measurements. Those are the only permitted sources of run-to-run variation and
they are excluded HERE, explicitly, rather than accidentally.

`--self-test` proves the comparison works before it is trusted to report a result: that
two identical trees agree, that a real difference is caught, and that each volatile field
is blanked. It gained one on 2026-09-20, when ADR-0083 landed the pipeline entry point and
gave this script behaviour to prove; until then it had none, and said so.

Exit codes:
    0  two runs agree (or the self-test passed)
    1  two runs disagree -- determinism is broken
    2  NOT-RUNNABLE -- the entry point exists but refused; there is nothing to compare
"""

from __future__ import annotations

import os
import re
import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
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


def run_once(destination: Path, seed: str) -> int:
    """Execute the pipeline into a fresh output directory; return its exit code.

    `check=True` used to raise here, which surfaced a pipeline that legitimately refused --
    an unmaterialized dataset, say -- as a `CalledProcessError` traceback. That reads like
    a defect in the gate rather than the loud, actionable report this script exists to
    produce, so the code is returned and `main` decides what it means.
    """
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    environment = dict(os.environ)
    environment["PYTHONHASHSEED"] = "0"
    environment["PYTHONPATH"] = str(BACKEND_SRC)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "causalog.orchestration.pipeline",
            "--seed",
            seed,
            "--output",
            str(destination),
        ],
        check=False,
        env=environment,
        cwd=REPO_ROOT,
    )
    return completed.returncode


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


@contextlib.contextmanager
def _quiet() -> Iterator[None]:
    """Silence `compare`'s own reporting while the self-test deliberately provokes it.

    The self-test makes the comparison fire on purpose. Without this, a PASSING self-test
    prints "artifact.json differs between runs" and reads like a failure -- which is how a
    green check trains people to ignore its output.
    """
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def self_test() -> int:
    """Prove the comparison rejects a difference before trusting it to accept a match.

    A gate that has only ever been seen to pass has not been shown to be a gate
    (DEF-0001). Three properties, each of which this script would be useless without:

      * two identical trees compare equal;
      * a one-byte difference in a file is CAUGHT;
      * every volatile pattern is genuinely blanked, so the exclusions are doing work
        rather than being decorative.
    """
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        left = root / "left"
        right = root / "right"
        for tree in (left, right):
            tree.mkdir()
            (tree / "artifact.json").write_text('{"a":1,"b":[2,3]}\n')

        with _quiet():
            identical = compare(left, right)
        if identical != 0:
            print("SELF-TEST FAILED: two identical trees were reported as differing.")
            return 1

        (right / "artifact.json").write_text('{"a":2,"b":[2,3]}\n')
        with _quiet():
            changed = compare(left, right)
        if changed == 0:
            print("SELF-TEST FAILED: a changed artifact was NOT caught.")
            return 1

        (right / "artifact.json").write_text('{"a":1,"b":[2,3]}\n')
        (right / "extra.json").write_text("{}\n")
        with _quiet():
            differing = compare(left, right)
        if differing == 0:
            print("SELF-TEST FAILED: differing file SETS were not caught.")
            return 1
        (right / "extra.json").unlink()

    volatile_cases = (
        ('{"execution_id": "exec:aaa"}', '{"execution_id": "exec:bbb"}'),
        ('{"correlation_id": "corr:aaa"}', '{"correlation_id": "corr:bbb"}'),
        ('{"elapsed_seconds": 1.25}', '{"elapsed_seconds": 9.75}'),
        ('{"at": "2026-01-01T00:00:00Z"}', '{"at": "2026-09-20T13:45:01Z"}'),
    )
    for left_text, right_text in volatile_cases:
        if normalize(left_text) != normalize(right_text):
            print(
                f"SELF-TEST FAILED: {left_text} and {right_text} differ after "
                "normalization, so that volatile field is not actually excluded."
            )
            return 1

    if normalize('{"run_id": "run:aaa"}') == normalize('{"run_id": "run:bbb"}'):
        print(
            "SELF-TEST FAILED: normalization blanked `run_id`, which is the one value "
            "determinism is asserted AGAINST (ADR-0013). Excluding it would make every "
            "comparison vacuous."
        )
        return 1

    print(
        "self-test passed: identical trees agree, a changed artifact and a changed file "
        f"set are both caught, {len(volatile_cases)} volatile field(s) are blanked, and "
        "run_id is not."
    )
    return 0


def main() -> int:
    """Run twice with the same seed and compare, or prove the comparison first."""
    if "--self-test" in sys.argv:
        return self_test()

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
    if run_once(WORK_ROOT / "run_a", seed) != 0:
        print(
            "\nDETERMINISM: NOT-RUNNABLE. The pipeline entry point exists and was executed,\n"
            "  but it refused rather than producing artifacts -- see its message above.\n"
            "  The gate deliberately does NOT treat that as a pass: two runs that both fail\n"
            "  identically are byte-identical, and accepting that would be the exact\n"
            "  'passed on having no work to do' failure this gate exists to catch.\n"
            "  Materialize the dataset (import it, so a clean layer exists) and re-run."
        )
        return 2
    if run_once(WORK_ROOT / "run_b", seed) != 0:
        print("\nDETERMINISM: the second run refused where the first succeeded.")
        return 1
    mismatches = compare(WORK_ROOT / "run_a", WORK_ROOT / "run_b")
    if mismatches:
        print(f"\nDETERMINISM: {mismatches} mismatch(es). BUILD FAILED.")
        return 1
    print("DETERMINISM: two runs are byte-identical after excluding volatile fields.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
