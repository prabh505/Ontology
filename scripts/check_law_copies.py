#!/usr/bin/env python3
"""The Five Inviolable Laws must be byte-identical in both governance files.

`CONTEXT.md` §2 and `CONVENTIONS.md` §1 each hold a copy. A divergence between them is a
defect, not a style difference -- and `HANDOFF.md` §2 check 1 previously asked a human to
`diff` them by eye. This script does it instead.

Run `--self-test` to prove the check detects a planted divergence and a missing law. Before
DEF-0001 this script had only a positive test -- it asserted the repository currently
passes, and was never once observed to fail. That is not evidence that it works.
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTEXT = REPO_ROOT / "CONTEXT.md"
CONVENTIONS = REPO_ROOT / "CONVENTIONS.md"

LAW_LINE = re.compile(r"^\d\.\s+\*\*LAW-[A-Z]+\*\*")


def law_block(path: Path) -> list[str]:
    """Return the numbered law lines from a governance file, in file sequence."""
    return [
        line.rstrip() for line in path.read_text().splitlines() if LAW_LINE.match(line)
    ]


FIVE_LAWS_SAMPLE = "\n".join(
    f"{n}. **LAW-{name}** — placeholder text for the self-test only."
    for n, name in enumerate(
        ("EVENT", "TIME", "PROVENANCE", "DOMAIN", "EVIDENCE"), start=1
    )
)


def compare(left: list[str], right: list[str]) -> int:
    """Return the number of defects between two law blocks, reporting each."""
    if len(left) != 5:
        print(f"a law block holds {len(left)} law lines; expected 5.")
        return 1
    if left == right:
        return 0
    print(
        "FIVE LAWS: the two copies have diverged. This is a defect, not a style difference."
    )
    for index, (a, b) in enumerate(zip(left, right, strict=False), start=1):
        if a != b:
            print(f"  law {index}:\n    CONTEXT.md     {a}\n    CONVENTIONS.md {b}")
    print("Do not pick a favourite -- ask which is correct (HANDOFF.md §2).")
    return 1


def self_test() -> int:
    """Prove the check fails on a divergence and on a missing law, and passes on a match."""
    failures = 0
    with tempfile.TemporaryDirectory() as raw:
        sandbox = Path(raw)

        def block(text: str) -> list[str]:
            path = sandbox / "probe.md"
            path.write_text(text)
            return law_block(path)

        identical = block(FIVE_LAWS_SAMPLE)
        diverged = block(
            FIVE_LAWS_SAMPLE.replace("placeholder text", "DIFFERENT text", 1)
        )
        truncated = block("\n".join(FIVE_LAWS_SAMPLE.splitlines()[:4]))

        cases = (
            ("identical copies", identical, identical, 0),
            ("one diverged law", identical, diverged, 1),
            ("a missing law", truncated, truncated, 1),
            ("a missing law on the other side", identical, truncated, 1),
        )
        for label, left, right, expected in cases:
            # The comparison is expected to report on the failing cases; swallow that so
            # the self-test's own result is the only thing on stdout.
            with contextlib.redirect_stdout(io.StringIO()):
                actual = compare(left, right)
            if (actual != 0) != (expected != 0):
                verb = "was accepted" if expected else "was rejected"
                print(f"SELF-TEST FAILED: {label} {verb} and must not have been.")
                failures += 1

    if failures == 0:
        print("self-test passed: 3 defect shapes rejected, identical copies accepted.")
    return failures


def main() -> int:
    """Compare the two copies line by line."""
    if "--self-test" in sys.argv:
        return 1 if self_test() else 0

    left, right = law_block(CONTEXT), law_block(CONVENTIONS)
    if len(left) != 5:
        print(f"CONTEXT.md §2 holds {len(left)} law lines; expected 5.")
        return 1
    if left == right:
        print("FIVE LAWS: byte-identical across CONTEXT.md §2 and CONVENTIONS.md §1.")
        return 0
    print(
        "FIVE LAWS: the two copies have diverged. This is a defect, not a style difference."
    )
    for index, (a, b) in enumerate(zip(left, right, strict=False), start=1):
        if a != b:
            print(f"  law {index}:\n    CONTEXT.md     {a}\n    CONVENTIONS.md {b}")
    print("Do not pick a favourite -- ask which is correct (HANDOFF.md §2).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
