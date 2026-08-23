#!/usr/bin/env python3
"""Governance-record consistency enforcement.

The governance model works only if the record is internally consistent. Two defects of the
same class have already occurred, both found by hand rather than by a check:

  * OQ-004 was described as resolved in `CONTEXT.md` §3 prose while its §8 row still read
    as open (found during the ADR-0007/0008/0020 work).
  * OQ-008 was fully answered by ADR-0003 at the scaffold and its row was never struck
    (found by the sweep that followed).

Twice is a pattern, not bad luck, so it gets a check rather than more care. Per ADR-0019,
this ships `--self-test` proving it rejects each defect shape.

Checks:
  1. No open question is both struck through and listed as open.
  2. Every struck question names at least one ADR, and every ADR it names exists.
  3. Every ADR marked superseded names a successor, and that successor exists.
  4. Every ADR that claims to supersede another is reflected in that other's status.
  5. No open question is answered by an already-accepted ADR -- the OQ-004/OQ-008 class.
  6. No open question is called resolved in prose while its row still reads as open.
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTEXT = REPO_ROOT / "CONTEXT.md"
DECISIONS = REPO_ROOT / "DECISIONS.md"

STRUCK = re.compile(r"~~(OQ-\d+)~~")
OPEN_ROW = re.compile(r"^\| (OQ-\d+) \|", re.M)
ADR_HEADING = re.compile(r"^## (ADR-\d+) — ", re.M)
ADR_BODY = re.compile(r"^## (ADR-\d+) — .*?\n(.*?)(?=^## ADR-|\Z)", re.M | re.S)
STATUS = re.compile(r"\*\*Status:\*\* (.+)")
SUPERSEDES = re.compile(r"\*\*Supersedes:\*\* (ADR-\d+)")


def adr_statuses(decisions: str) -> dict[str, str]:
    """Return {adr_id: status} for every ADR in the log."""
    statuses: dict[str, str] = {}
    for match in ADR_BODY.finditer(decisions):
        status = STATUS.search(match.group(2))
        statuses[match.group(1)] = status.group(1).strip() if status else ""
    return statuses


def check(context: str, decisions: str) -> int:
    """Report every inconsistency and return the count."""
    failures = 0
    struck = set(STRUCK.findall(context))
    open_rows = set(OPEN_ROW.findall(context))
    declared = set(ADR_HEADING.findall(decisions))
    statuses = adr_statuses(decisions)

    for question in sorted(struck & open_rows):
        print(f"{question} is both struck through and listed as open in CONTEXT.md §8.")
        failures += 1

    for question in sorted(struck):
        row = next(
            (line for line in context.splitlines() if f"~~{question}~~" in line), ""
        )
        named = set(re.findall(r"ADR-\d+", row))
        if not named:
            print(
                f"{question} is struck through but names no ADR. A question is closed by a decision, not by assertion."
            )
            failures += 1
        for adr in sorted(named - declared):
            print(f"{question} names {adr}, which does not exist in DECISIONS.md.")
            failures += 1

    for adr, status in sorted(statuses.items()):
        if "superseded" not in status:
            continue
        successors = re.findall(r"ADR-\d+", status)
        if not successors:
            print(f"{adr} is marked superseded but names no successor.")
            failures += 1
        for successor in successors:
            if successor not in declared:
                print(f"{adr} is superseded by {successor}, which does not exist.")
                failures += 1

    for match in ADR_BODY.finditer(decisions):
        adr, body = match.group(1), match.group(2)
        target = SUPERSEDES.search(body)
        if target and adr not in statuses.get(target.group(1), ""):
            print(
                f"{adr} supersedes {target.group(1)}, but {target.group(1)}'s status does "
                "not say so. Status is the only field that may be edited on a past ADR "
                "(DECISIONS.md) -- edit it."
            )
            failures += 1

    for line in context.splitlines():
        row = OPEN_ROW.match(line)
        if not row:
            continue
        question = row.group(1)
        unblocked_by = line.rsplit("|", 2)[-2]
        for adr in re.findall(r"ADR-\d+", unblocked_by):
            if statuses.get(adr) == "accepted":
                print(
                    f"{question} is listed as open, but {adr} is already accepted and is "
                    "named as what unblocks it. Strike the row, or say why the ADR does "
                    "not settle it. (This is the OQ-004 / OQ-008 defect class.)"
                )
                failures += 1

    for question in sorted(open_rows):
        if re.search(rf"{question}[^|\n]{{0,40}}(resolved|closed)", context, re.I):
            print(
                f"{question} is open in §8 but is described as resolved elsewhere in CONTEXT.md."
            )
            failures += 1

    return failures


def self_test() -> int:
    """Prove each defect shape is rejected and a consistent record is accepted."""
    good_context = "| ~~OQ-001~~ **RESOLVED by ADR-0006** | q | d | c | ADR-0006 |\n| OQ-005 | q | d | c | ADR-0009 |\n"
    good_decisions = (
        "## ADR-0006 — a\n\n- **Status:** accepted\n- **Supersedes:** —\n\n"
        "## ADR-0010 — b\n\n- **Status:** superseded by ADR-0019\n- **Supersedes:** —\n\n"
        "## ADR-0019 — c\n\n- **Status:** accepted\n- **Supersedes:** ADR-0010\n"
    )

    cases: tuple[tuple[str, str, str, bool], ...] = (
        ("a consistent record", good_context, good_decisions, False),
        (
            "a question both struck and open",
            good_context + "| OQ-001 | q | d | c | ADR-0006 |\n",
            good_decisions,
            True,
        ),
        (
            "a struck question naming no ADR",
            "| ~~OQ-002~~ resolved | q | d | c | none |\n",
            good_decisions,
            True,
        ),
        (
            "a struck question naming a nonexistent ADR",
            "| ~~OQ-002~~ **RESOLVED by ADR-0099** | q | d | c | ADR-0099 |\n",
            good_decisions,
            True,
        ),
        (
            "a superseded ADR with no successor",
            good_context,
            "## ADR-0010 — b\n\n- **Status:** superseded\n- **Supersedes:** —\n",
            True,
        ),
        (
            "a supersession the target does not acknowledge",
            good_context,
            "## ADR-0010 — b\n\n- **Status:** accepted\n- **Supersedes:** —\n\n"
            "## ADR-0019 — c\n\n- **Status:** accepted\n- **Supersedes:** ADR-0010\n",
            True,
        ),
        (
            "an open question already answered by an accepted ADR",
            "| OQ-008 | q | d | c | ADR-0006 |\n",
            good_decisions,
            True,
        ),
        (
            "an open question called resolved in prose",
            "OQ-005 was resolved last week.\n| OQ-005 | q | d | c | ADR-0009 |\n",
            good_decisions,
            True,
        ),
    )

    failures = 0
    for label, context, decisions, must_reject in cases:
        with contextlib.redirect_stdout(io.StringIO()):
            rejected = check(context, decisions) > 0
        if rejected != must_reject:
            verb = "was accepted" if must_reject else "was rejected"
            print(f"SELF-TEST FAILED: {label} {verb} and must not have been.")
            failures += 1

    if failures == 0:
        rejecting = sum(1 for _, _, _, must_reject in cases if must_reject)
        print(
            f"self-test passed: {rejecting} inconsistency shapes rejected, "
            f"{len(cases) - rejecting} consistent record accepted."
        )
    return failures


def main() -> int:
    """Check the governance record, or self-test when asked."""
    if "--self-test" in sys.argv:
        return 1 if self_test() else 0

    failures = check(CONTEXT.read_text(), DECISIONS.read_text())
    if failures:
        print(f"\nGOVERNANCE CONSISTENCY: {failures} inconsistency(ies). BUILD FAILED.")
        return 1
    struck = len(set(STRUCK.findall(CONTEXT.read_text())))
    still_open = len(set(OPEN_ROW.findall(CONTEXT.read_text())))
    print(
        f"GOVERNANCE CONSISTENCY: clean; {struck} question(s) closed by an existing ADR, "
        f"{still_open} still open, supersessions acknowledged both ways."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
