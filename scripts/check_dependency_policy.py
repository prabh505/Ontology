#!/usr/bin/env python3
"""Dependency policy enforcement (`CONVENTIONS.md` §12, ADR-0003, ADR-0015).

Three claims, each checked mechanically:

  1. Every pin is exact. No ranges, no `latest`.
  2. Every declared dependency is named in ADR-0015. A dependency nobody wrote an ADR for
     is a defect, not a convenience.
  3. No blocked library is declared or imported anywhere. `pgmpy`, `dowhy`, `torch`, and
     `torch-geometric` are deferred (prd.md §45 stages them at V2+); importing one would
     introduce nondeterminism the Definition of Done cannot absorb.

Run `--self-test` to prove each of the three rejects the violation it exists to catch and
accepts a clean input. Before DEF-0001 this script had no test of any kind: it was the one
law check with no evidence it worked at all.

Each rule is a function taking its inputs rather than reading module globals, so the
self-test and pytest can drive it directly -- the shape `check_layers.check_file` already
uses.
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "backend" / "pyproject.toml"
ADR_LOG = REPO_ROOT / "DECISIONS.md"  # the canonical ADR log; ADR-0015 lives there

BLOCKED = (
    "pgmpy",
    "dowhy",
    "torch",
    "torch-geometric",
    "torch_geometric",
    "tensorflow",
    "scikit-learn",
)

EXACT_PIN = re.compile(r"^([A-Za-z0-9_.\-]+)(\[[a-z,]+\])?==[0-9][0-9A-Za-z.\-]*$")

SEARCH_ROOTS = ("backend/src", "backend/tests", "scripts")


def declared_dependencies(pyproject: Path) -> list[str]:
    """Return every runtime, dev, and build dependency string from a pyproject file."""
    data = tomllib.loads(pyproject.read_text())
    project = data["project"]
    declared = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        declared.extend(extra)
    declared.extend(data.get("build-system", {}).get("requires", []))
    return declared


def requirement_name(requirement: str) -> str:
    """Return the package name from a requirement string."""
    match = EXACT_PIN.match(requirement)
    return match.group(1) if match else requirement


def check_pins(declared: list[str]) -> int:
    """Rule 1 -- every pin is exact. Returns the violation count."""
    failures = 0
    for requirement in declared:
        if not EXACT_PIN.match(requirement):
            print(
                f"pyproject.toml: `{requirement}` is not an exact pin (CONVENTIONS.md §12)."
            )
            failures += 1
    return failures


def check_adr_coverage(declared: list[str], adr_text: str) -> int:
    """Rule 2 -- every declared dependency is named in ADR-0015."""
    if "adr-0015" not in adr_text.lower():
        print(
            "DECISIONS.md holds no ADR-0015; every dependency needs an ADR (CONVENTIONS.md §12)."
        )
        return 1
    failures = 0
    for requirement in declared:
        name = requirement_name(requirement)
        if name.lower() not in adr_text.lower():
            print(
                f"`{name}` is declared in pyproject.toml but is not named in "
                "ADR-0015. Write the ADR before the import (CONVENTIONS.md §12)."
            )
            failures += 1
    return failures


def check_blocked_declarations(declared: list[str]) -> int:
    """Rule 3a -- no blocked library is declared."""
    failures = 0
    for requirement in declared:
        if any(requirement.lower().startswith(blocked) for blocked in BLOCKED):
            print(f"`{requirement}` is blocked for V1 by ADR-0003.")
            failures += 1
    return failures


def check_blocked_imports(roots: tuple[str, ...], base_dir: Path) -> int:
    """Rule 3b -- no blocked library is imported anywhere under the given roots."""
    patterns = [
        (
            blocked,
            re.compile(
                rf"^\s*(?:import|from)\s+{re.escape(blocked.replace('-', '_'))}\b"
            ),
        )
        for blocked in BLOCKED
    ]
    failures = 0
    for root in roots:
        search_root = base_dir / root
        if not search_root.exists():
            continue
        for path in sorted(search_root.rglob("*.py")):
            for number, line in enumerate(path.read_text().splitlines(), start=1):
                for blocked, pattern in patterns:
                    if pattern.match(line):
                        print(
                            f"{path.relative_to(base_dir).as_posix()}:{number}: "
                            f"import of blocked library `{blocked}` (ADR-0003)."
                        )
                        failures += 1
    return failures


def self_test() -> int:
    """Prove each rule rejects its violation and accepts a clean input."""
    failures = 0
    clean = ["fastapi==0.115.6", "pydantic==2.10.4"]
    clean_adr = "ADR-0015 names fastapi and pydantic."

    cases: tuple[tuple[str, object, bool], ...] = (
        ("a range pin", lambda: check_pins(["fastapi>=0.115.6"]), True),
        ("a `latest` pin", lambda: check_pins(["fastapi"]), True),
        ("exact pins", lambda: check_pins(clean), False),
        (
            "a package absent from ADR-0015",
            lambda: check_adr_coverage(["requests==2.32.3"], clean_adr),
            True,
        ),
        (
            "a missing ADR-0015 entirely",
            lambda: check_adr_coverage(clean, "no adrs here"),
            True,
        ),
        ("ADR-backed packages", lambda: check_adr_coverage(clean, clean_adr), False),
        (
            "a blocked declaration",
            lambda: check_blocked_declarations(["torch==2.5.1"]),
            True,
        ),
        ("permitted declarations", lambda: check_blocked_declarations(clean), False),
    )

    for label, rule, must_reject in cases:
        # The rules are expected to report on the failing cases; swallow that so the
        # self-test's own result is the only thing on stdout.
        with contextlib.redirect_stdout(io.StringIO()):
            rejected = rule() > 0  # type: ignore[operator]
        if rejected != must_reject:
            verb = "was accepted" if must_reject else "was rejected"
            print(f"SELF-TEST FAILED: {label} {verb} and must not have been.")
            failures += 1

    if failures == 0:
        rejecting = sum(1 for _, _, must_reject in cases if must_reject)
        print(
            f"self-test passed: {rejecting} policy violations rejected, "
            f"{len(cases) - rejecting} clean inputs accepted."
        )
    return failures


def main() -> int:
    """Run the three checks."""
    if "--self-test" in sys.argv:
        return 1 if self_test() else 0

    declared = declared_dependencies(PYPROJECT)
    adr_text = ADR_LOG.read_text() if ADR_LOG.exists() else ""

    failures = (
        check_pins(declared)
        + check_adr_coverage(declared, adr_text)
        + check_blocked_declarations(declared)
        + check_blocked_imports(SEARCH_ROOTS, REPO_ROOT)
    )

    if failures:
        print(f"\nDEPENDENCY POLICY: {failures} violation(s). BUILD FAILED.")
        return 1
    print(
        f"DEPENDENCY POLICY: clean; {len(declared)} pinned dependencies, all ADR-backed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
