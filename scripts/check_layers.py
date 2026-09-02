#!/usr/bin/env python3
"""Layer-boundary enforcement (ADR-0016).

Dependencies flow one direction only:

    UI -> API -> orchestration -> reasoning modules -> core contracts

This script builds the import graph with the standard library `ast` module and fails the
build on any forbidden edge. It uses no third-party import linter: the rule set is small,
project-specific, and must never be silently disabled by a dependency upgrade.

The rank table and the forbidden-edge table below are the machine-readable copy of
`docs/architecture.md` §1. If they diverge, the document is wrong and this file is right --
but the divergence is a defect, and `make lint` is where it shows up.

Run `--self-test` to prove every rule F1-F9 fires on a synthetic import and that the
permitted edges stay clean. A lint that has never been observed to fail has not been
tested; see DEF-0001 for what that costs.
"""

from __future__ import annotations

import ast
import contextlib
import io
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = REPO_ROOT / "backend" / "src" / "causalog"
PACKAGE = "causalog"

# Layer rank. A package may import its own rank and every LOWER rank. Never a higher one.
LAYER_RANKS: dict[str, int] = {
    "core": 0,
    "ontology_runtime": 1,
    "ingestion": 2,
    "extraction": 3,
    "graph_engine": 4,
    "rule_engine": 5,
    "causal_engine": 6,
    "counterfactual_engine": 7,
    "recommendation_engine": 7,
    "explanation_engine": 8,
    "orchestration": 9,
    "api": 10,
}

# `persistence` is not a layer. It implements core ports and is wired only by
# orchestration, so it is ranked beside orchestration and additionally gated by F4.
PERSISTENCE = "persistence"

# F3 -- only these may consume the ontology runtime. Mapping and extraction need its
# semantics; orchestration needs it to construct a Run. Nothing else may know the ontology
# exists. The presentation layer reads LABELS ONLY, through the core port, never from here.
ONTOLOGY_CONSUMERS = frozenset({"ingestion", "extraction", "orchestration"})

# F4 -- only orchestration may import a concrete persistence adapter.
PERSISTENCE_CONSUMERS = frozenset({"orchestration"})

# F5 -- the API talks to orchestration and core. No reach-through to a reasoning package.
API_PERMITTED_TARGETS = frozenset({"core", "orchestration", "api"})

# F7 -- the LAW-EVENT boundary, enforced at import level. Nothing at or above `extraction`
# may import a tabular library; a row may not exist above L2.
TABULAR_MODULES = frozenset({"pandas", "csv", "pyarrow", "polars", "numpy"})
TABULAR_MIN_RANK = 3

# F8 -- core's dependency ceiling (CONVENTIONS.md §12).
CORE_PERMITTED_THIRD_PARTY = frozenset({"pydantic"})

# F9 -- blocked by ADR-0003 for the whole distribution.
BLOCKED_MODULES = frozenset(
    {"pgmpy", "dowhy", "torch", "torch_geometric", "sklearn", "tensorflow"}
)

STDLIB_PREFIXES = frozenset(sys.stdlib_module_names)


def package_of(path: Path) -> str:
    """Return the top-level `causalog` sub-package a file belongs to."""
    return path.relative_to(PACKAGE_ROOT).parts[0]


def imported_modules(tree: ast.AST) -> list[tuple[str, int]]:
    """Return every imported dotted module name with its line number."""
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.module, node.lineno))
    return found


def report(path: Path, line: int, rule: str, message: str) -> None:
    """Print one violation in a clickable form."""
    relative = path.relative_to(REPO_ROOT).as_posix()
    print(f"{relative}:{line}: {rule} -- {message}")


def check_file(path: Path) -> int:
    """Return the number of forbidden edges leaving this file."""
    source_package = package_of(path)
    source_rank = LAYER_RANKS.get(source_package)
    violations = 0

    for module, line in imported_modules(
        ast.parse(path.read_text(), filename=str(path))
    ):
        root = module.split(".")[0]

        if root in BLOCKED_MODULES:
            report(path, line, "F9", f"`{module}` is blocked for V1 by ADR-0003.")
            violations += 1
            continue

        if root in STDLIB_PREFIXES:
            continue

        if root != PACKAGE:
            # Third-party import.
            if source_package == "core" and root not in CORE_PERMITTED_THIRD_PARTY:
                report(
                    path,
                    line,
                    "F8",
                    f"core/ may not depend on `{root}`; its ceiling is the standard "
                    "library plus the data-validation library (CONVENTIONS.md §12).",
                )
                violations += 1
            if (
                root in TABULAR_MODULES
                and source_rank is not None
                and source_rank >= TABULAR_MIN_RANK
            ):
                report(
                    path,
                    line,
                    "F7",
                    f"`{root}` is a tabular library imported at layer rank {source_rank}; "
                    "no row, frame, or column may exist above the LAW-EVENT boundary.",
                )
                violations += 1
            continue

        parts = module.split(".")
        if len(parts) < 2:
            continue
        target_package = parts[1]

        # F1 -- core purity.
        if source_package == "core" and target_package != "core":
            report(
                path,
                line,
                "F1",
                f"core/ may not import `{module}`; core has no project-local "
                "dependencies (CONVENTIONS.md §6).",
            )
            violations += 1
            continue

        # F4 -- persistence adapters are wired only by orchestration.
        # A package importing itself is never a forbidden edge: "a package may import its
        # own layer" (docs/architecture.md §1.1). This is the SECOND instance of that hole
        # -- ADR-0026 fixed the same one in F3, where it stayed invisible until
        # `ontology_runtime` held code. F4 had it too, and it stayed invisible for exactly
        # the same reason: `persistence` was four empty scaffold packages, so the rule had
        # nothing to fire on. A rule that cannot fire has not been observed to work
        # (DEF-0001), which is why both now carry a MUST_ACCEPT self-test case.
        if (
            target_package == PERSISTENCE
            and source_package != PERSISTENCE
            and source_package not in PERSISTENCE_CONSUMERS
        ):
            report(
                path,
                line,
                "F4",
                f"`{source_package}` may not import a persistence adapter; depend on a "
                "port in causalog.core.ports and let orchestration wire it (ADR-0014).",
            )
            violations += 1
            continue

        # F5 -- no cross-layer reach-through from the API.
        if source_package == "api" and target_package not in API_PERMITTED_TARGETS:
            report(
                path,
                line,
                "F5",
                f"api/ may not reach through to `{target_package}`; the API talks to "
                "orchestration (CONVENTIONS.md §6).",
            )
            violations += 1
            continue

        # F3 -- ontology consumption is restricted to mapping, extraction, and wiring.
        # A package importing itself is never a forbidden edge: "a package may import its
        # own layer" (docs/architecture.md §1.1). Without this clause the rule fired on
        # `ontology_runtime`'s own internal imports -- which it did not do while that
        # package was empty, so the hole was invisible until the ontology layer shipped.
        if (
            target_package == "ontology_runtime"
            and source_package != "ontology_runtime"
            and source_package not in ONTOLOGY_CONSUMERS
        ):
            report(
                path,
                line,
                "F3",
                f"`{source_package}` may not depend on the ontology; only "
                f"{sorted(ONTOLOGY_CONSUMERS)} may (LAW-DOMAIN, ADR-0002).",
            )
            violations += 1
            continue

        # F2/F6 -- upward imports.
        target_rank = LAYER_RANKS.get(target_package)
        if (
            source_rank is not None
            and target_rank is not None
            and target_rank > source_rank
        ):
            rule = (
                "F6"
                if (source_package, target_package) == ("graph_engine", "causal_engine")
                else "F2"
            )
            detail = (
                " Module 8 records only what was observed; module 9 is the first place an "
                "INFERRED assertion may be created."
                if rule == "F6"
                else ""
            )
            report(
                path,
                line,
                rule,
                f"upward import: `{source_package}` (L{source_rank}) may not import "
                f"`{target_package}` (L{target_rank}).{detail}",
            )
            violations += 1

    return violations


# (package, source line, rule) -- one synthetic import per forbidden edge. Every rule in
# the F1-F9 table must appear here; `self_test` fails if one does not.
MUST_REJECT: tuple[tuple[str, str, str], ...] = (
    ("core", "from causalog.causal_engine import scorer\n", "F1"),
    ("ingestion", "import causalog.api\n", "F2"),
    ("causal_engine", "from causalog.ontology_runtime import loader\n", "F3"),
    ("causal_engine", "from causalog.persistence.neo4j import driver\n", "F4"),
    ("api", "from causalog.graph_engine import builder\n", "F5"),
    ("graph_engine", "import causalog.causal_engine\n", "F6"),
    ("causal_engine", "import pandas\n", "F7"),
    ("core", "import redis\n", "F8"),
    ("causal_engine", "import torch\n", "F9"),
)

# Edges that MUST stay clean. Without these a matcher that rejects everything would pass.
MUST_ACCEPT: tuple[tuple[str, str], ...] = (
    ("causal_engine", "from causalog.core.types import Event\n"),
    ("orchestration", "from causalog.persistence.postgres import repo\n"),
    ("extraction", "from causalog.ontology_runtime import loader\n"),
    # A package always may import itself. These two cases exist because F3 and then F4
    # each once rejected it -- the same hole, found twice, both times only after the
    # package in question stopped being empty scaffold and started holding code.
    ("ontology_runtime", "from causalog.ontology_runtime import dsl\n"),
    ("persistence", "from causalog.persistence.postgres import connection\n"),
    ("api", "from causalog.orchestration import facade\n"),
    ("core", "import hashlib\n"),
    ("core", "from pydantic import BaseModel\n"),
)


def self_test() -> int:
    """Prove each forbidden edge is rejected and each permitted edge is not."""
    failures = 0

    declared = {rule for _, _, rule in MUST_REJECT}
    expected = {f"F{n}" for n in range(1, 10)}
    for missing in sorted(expected - declared):
        print(f"SELF-TEST FAILED: no synthetic case covers rule {missing}.")
        failures += 1

    global REPO_ROOT, PACKAGE_ROOT  # noqa: PLW0603 -- the probe needs a throwaway tree
    real_repo, real_package = REPO_ROOT, PACKAGE_ROOT
    try:
        with tempfile.TemporaryDirectory() as raw:
            sandbox = Path(raw)
            REPO_ROOT = PACKAGE_ROOT = sandbox

            def probe(package: str, source: str) -> int:
                target = sandbox / package
                target.mkdir(parents=True, exist_ok=True)
                planted = target / "probe.py"
                planted.write_text(source)
                # The probes are expected to report; swallow that output so the
                # self-test's own result is the only thing on stdout.
                with contextlib.redirect_stdout(io.StringIO()):
                    return check_file(planted)

            for package, source, rule in MUST_REJECT:
                if probe(package, source) < 1:
                    print(
                        f"SELF-TEST FAILED: {rule} -- `{package}` importing "
                        f"`{source.strip()}` was accepted and must not be."
                    )
                    failures += 1
            for package, source in MUST_ACCEPT:
                if probe(package, source) != 0:
                    print(
                        f"SELF-TEST FAILED: `{package}` importing `{source.strip()}` is "
                        "permitted and was rejected."
                    )
                    failures += 1
    finally:
        REPO_ROOT, PACKAGE_ROOT = real_repo, real_package

    if failures == 0:
        print(
            f"self-test passed: {len(MUST_REJECT)} forbidden edges rejected "
            f"(F1-F9 all covered), {len(MUST_ACCEPT)} permitted edges accepted."
        )
    return failures


def main() -> int:
    """Walk every module in the distribution and report forbidden edges."""
    if "--self-test" in sys.argv:
        return 1 if self_test() else 0
    if not PACKAGE_ROOT.exists():
        print(f"layer check: package root {PACKAGE_ROOT} does not exist.")
        return 1
    files = sorted(PACKAGE_ROOT.rglob("*.py"))
    violations = sum(check_file(path) for path in files)
    if violations:
        print(
            f"\nLAYER BOUNDARIES: {violations} forbidden edge(s) across {len(files)} file(s). BUILD FAILED."
        )
        return 1
    print(f"LAYER BOUNDARIES: clean across {len(files)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
