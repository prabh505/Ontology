#!/usr/bin/env python3
"""ADR-0026 enforcement: a domain metric is declared in the ontology, never computed here.

A pack declares every metric as a `MeasurementExpression` -- an operator tree over attributes
the referenced event types guarantee to carry, built from a closed operator set, with no
expression string anywhere (`docs/ontology.md` §2, ADR-0026). That is the *declaration* half,
and the DSL makes it structural: there is no escape hatch to write a formula into a pack.

The *engine* half has no structure behind it. Nothing stops a reasoning module computing a
delay inline instead of walking the declared tree, and the failure is quiet: the number looks
right, the pack still validates, and the ontology silently stops being the place the metric
is defined. Swapping the pack then changes the declaration and not the arithmetic, which is
LAW-DOMAIN defeated by a value rather than by a word -- the residual `docs/architecture.md`
§1.5 states, and the one the vocabulary lint cannot see.

Specification: `CONVENTIONS.md` §6a, ADR-0026, LAW-DOMAIN.

  Scope       every `.py` file under graph_engine/, causal_engine/,
              counterfactual_engine/, recommendation_engine/, explanation_engine/
  Matched     Four rules.
              1. ARITHMETIC (`+ - * / // % **`) with an operand named for a domain metric.
              2. Any assignment binding a metric-named target to an arithmetic expression.
                 `delay = arrival - promised` is caught here even though neither operand is
                 metric-named; that form is the commonest shape of the defect.
              3. Arithmetic on a TAINTED value -- one bound, anywhere earlier in the same
                 scope, from a metric-named attribute or a metric-named string key.
                 `raw = event["shipping_delay"]` then `value = raw - baseline` names no
                 metric in the arithmetic at all, and rules 1 and 2 both miss it.
              4. A COMPARISON between a metric (named or tainted) and a NUMERIC LITERAL:
                 `if delay > 48`. That number is domain policy, and it belongs in the pack
                 beside the metric it bounds.
  Not matched `core/` -- `core/aggregation.py` does arithmetic over confidence components,
              which are engine concepts and not domain metrics (ADR-0009).
              `ontology_runtime/` -- it builds the tree and never evaluates it; evaluating
              there would put arithmetic over domain attributes inside the seam that exists
              to hold no logic (PROGRESS.md, the ontology layer's deliberate omissions).
              COMPARISON AGAINST A VARIABLE (`delay > threshold`) -- that is a guard
              reading a bound from somewhere else, not a policy constant written here, and
              a lint firing on every guard clause would be routed around. Only the
              metric-versus-literal form is matched (rule 4).
              `count` and `ratio` -- both are `MeasurementKind` members and both are
              ordinary program bookkeeping (`count += 1`). They are deliberately absent
              from METRIC_STEMS; a lint that fires on a loop counter gets disabled, and a
              disabled lint enforces nothing.
  Allowlist   .lawmetric-allowlist, one reviewed entry per line WITH a justification
  Failure     exit 1. This job fails the build. It does not warn.
              exit 2 while every in-scope package is scaffold only -- the check cannot
              run, and a check that cannot run is never reported as a check that
              passed (DEF-0001).

Matching is over the AST, not the text. A regex would fire on `# the cost of a rerun` and on
`"impact"` inside a string literal, and the natural response to a lint that cries wolf in
prose is to delete it.

Run `--self-test` to prove the matcher fires on every shape inline metric arithmetic takes
AND stays clean on the near-misses that are legitimate. Per `CONVENTIONS.md` §1, a check that
has never been observed to reject has not been tested, so the self-test runs before the scan
in `make laws`.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = REPO_ROOT / "backend" / "src" / "causalog"

# The reasoning packages. `core` and `ontology_runtime` are excluded on purpose; the
# docstring says why, because an unexplained exclusion is how a scope quietly rots.
IN_SCOPE_PACKAGES = (
    "graph_engine",
    "causal_engine",
    "counterfactual_engine",
    "recommendation_engine",
    "explanation_engine",
)

# Truncated to the invariant root, so one entry covers every inflection: `delay` covers
# delay/delays/delayed, `cost` covers cost/costs/costing.
#
# Tracks `MeasurementKind` in `causalog.ontology_runtime.dsl` -- DELAY, DURATION, COST,
# IMPACT, QUANTITY -- plus the metric words a pack author reaches for that the enum spells
# differently. COUNT and RATIO are members of that enum and are absent here; see the
# docstring.
METRIC_STEMS = (
    "delay",
    "duration",
    "cost",
    "impact",
    "penalty",
    "quantity",
    "amount",
    "price",
    "latency",
)

ARITHMETIC = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.FloorDiv: "//",
    ast.Mod: "%",
    ast.Pow: "**",
}

ALLOWLIST_PATH = REPO_ROOT / ".lawmetric-allowlist"

# A metric stem occupying a whole identifier component. The lookbehind is letter-only for
# the same reason as `check_domain_independence.py`: a preceding letter means the stem sits
# inside a longer word (`accosted`, `impactful` -- neither is a metric), while a preceding
# underscore or digit means it is a separate component (`total_cost`, `v2_delay`) and that
# IS the vocabulary this lint is about.
METRIC_NAME = re.compile(
    r"(?<![A-Za-z])(" + "|".join(METRIC_STEMS) + r")[A-Za-z0-9_]*", re.IGNORECASE
)


def _is_metric_name(name: str) -> bool:
    """Return whether an identifier names a domain metric."""
    return any(METRIC_NAME.fullmatch(part) for part in name.split("_") if part) or bool(
        METRIC_NAME.match(name)
    )


def _identifier(node: ast.expr) -> str | None:
    """Return the readable identifier a node binds to, if it has one."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _identifier(node.value)
    return None


def _metric_operands(node: ast.BinOp) -> list[str]:
    """Return the metric-named identifiers appearing directly in one arithmetic node."""
    found: list[str] = []
    for side in (node.left, node.right):
        name = _identifier(side)
        if name is not None and _is_metric_name(name):
            found.append(name)
    return found


def _contains_arithmetic(node: ast.expr) -> bool:
    """Return whether an expression performs arithmetic anywhere inside itself."""
    return any(
        isinstance(inner, ast.BinOp) and type(inner.op) in ARITHMETIC
        for inner in ast.walk(node)
    )


def _is_numeric_literal(node: ast.expr) -> bool:
    """Return whether a node is a bare number, `True`/`False` excluded.

    `bool` is a subclass of `int`, and `delay == True` is a nonsense comparison rather than
    a hard-coded policy constant. Excluding it keeps the finding meaning one thing.
    """
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int | float)
        and not isinstance(node.value, bool)
    )


NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _scopes(tree: ast.Module) -> list[ast.AST]:
    """Return the module and every function or class in it, each analysed separately.

    Taint is tracked per scope. Sharing one set across the file would mean a `value` bound
    from a metric in one function silently taints an unrelated `value` in the next, and a
    lint that invents violations is disabled as fast as one that misses them.
    """
    found: list[ast.AST] = [tree]
    found.extend(node for node in ast.walk(tree) if isinstance(node, NESTED_SCOPES))
    return found


def _own_nodes(scope: ast.AST) -> list[ast.AST]:
    """Return the nodes belonging to one scope, in source order, excluding nested scopes."""
    found: list[ast.AST] = []
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        found.append(node)
        if isinstance(node, NESTED_SCOPES):
            continue
        stack.extend(ast.iter_child_nodes(node))
    found.sort(
        key=lambda node: (getattr(node, "lineno", 0), getattr(node, "col_offset", 0))
    )
    return found


def _attribute_key(node: ast.AST) -> str | None:
    """Return a metric-named string key used to read an attribute out of a record.

    `event.attributes["shipping_delay"]` names a metric in a *string*, where no identifier
    does. That subscript is the boundary at which a declared quantity enters engine code,
    so it is where taint starts.
    """
    if not isinstance(node, ast.Subscript):
        return None
    key = node.slice
    if (
        isinstance(key, ast.Constant)
        and isinstance(key.value, str)
        and _is_metric_name(key.value)
    ):
        return key.value
    return None


def _metric_origin(node: ast.expr, tainted: dict[str, str]) -> str | None:
    """Return what makes an expression carry a domain metric, or `None` if nothing does.

    Three ways in, in the order they are cheapest to be sure about: a metric-named
    identifier, a metric-named string key, and a name already known to hold a metric.
    """
    for inner in ast.walk(node):
        key = _attribute_key(inner)
        if key is not None:
            return key
        if isinstance(inner, ast.Name) and inner.id in tainted:
            return tainted[inner.id]
        if isinstance(inner, ast.Name | ast.Attribute):
            name = _identifier(inner)
            if name is not None and _is_metric_name(name):
                return name
    return None


def _targets(node: ast.expr) -> list[str]:
    """Return the plain names one assignment target binds."""
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Tuple | ast.List):
        return [name for element in node.elts for name in _targets(element)]
    return []


def _analyse(scope: ast.AST) -> list[tuple[int, str, str]]:
    """Return every finding in one scope, walking its statements in source order.

    Source order is what makes the taint set usable without a full dataflow analysis: by
    the time `delay = arrival - promised` is read, the line that bound `arrival` from the
    record has already been seen. It is an approximation -- a loop that assigns after it
    reads is not modelled -- and it is deliberately the cheap end of the trade, because the
    alternative is a type checker and this file is standard-library only (ADR-0016).
    """
    found: list[tuple[int, str, str]] = []
    tainted: dict[str, str] = {}

    for node in _own_nodes(scope):
        if isinstance(node, ast.BinOp) and type(node.op) in ARITHMETIC:
            symbol = ARITHMETIC[type(node.op)]
            for name in _metric_operands(node):
                found.append((node.lineno, name, f"arithmetic '{symbol}' on"))
            for side in (node.left, node.right):
                if isinstance(side, ast.Name) and side.id in tainted:
                    found.append(
                        (
                            node.lineno,
                            side.id,
                            f"arithmetic '{symbol}' on a value read from "
                            f"'{tainted[side.id]}' and carried in",
                        )
                    )

        elif isinstance(node, ast.Compare):
            origin = _metric_origin(node.left, tainted)
            literals = [side for side in node.comparators if _is_numeric_literal(side)]
            if origin is None:
                for side in node.comparators:
                    origin = origin or _metric_origin(side, tainted)
                literals = [side for side in [node.left] if _is_numeric_literal(side)]
            if origin is not None and literals:
                found.append(
                    (
                        node.lineno,
                        origin,
                        f"the hard-coded threshold {literals[0].value!r} compared against",
                    )
                )

        elif isinstance(node, ast.Assign | ast.AnnAssign):
            targets = (
                list(node.targets) if isinstance(node, ast.Assign) else [node.target]
            )
            if node.value is None:
                continue
            if _contains_arithmetic(node.value):
                for target in targets:
                    name = _identifier(target)
                    if name is not None and _is_metric_name(name):
                        found.append(
                            (node.lineno, name, "an arithmetic expression assigned to")
                        )
            origin = _metric_origin(node.value, tainted)
            if origin is not None:
                for name in [n for target in targets for n in _targets(target)]:
                    tainted[name] = origin

        elif isinstance(node, ast.AugAssign) and type(node.op) in ARITHMETIC:
            name = _identifier(node.target)
            symbol = ARITHMETIC[type(node.op)]
            if name is not None and _is_metric_name(name):
                found.append((node.lineno, name, f"in-place arithmetic '{symbol}=' on"))
            elif name is not None and name in tainted:
                found.append(
                    (
                        node.lineno,
                        name,
                        f"in-place arithmetic '{symbol}=' on a value read from "
                        f"'{tainted[name]}' and carried in",
                    )
                )

    return found


def violations_in(source: str) -> list[tuple[int, str, str]]:
    """Return `(line, identifier, what happened)` for every metric computed in `source`."""
    tree = ast.parse(source)
    found = [finding for scope in _scopes(tree) for finding in _analyse(scope)]
    return sorted(set(found))


def load_allowlist() -> set[tuple[str, str]]:
    """Return the reviewed (relative_path, identifier) pairs, refusing malformed entries.

    Keyed on the exact identifier, lowercased. An entry exempts one binding, never a family:
    an approved `transit_delay` must not also exempt `transit_delay_seconds`.
    """
    allowed: set[tuple[str, str]] = set()
    if not ALLOWLIST_PATH.exists():
        return allowed
    for number, raw in enumerate(ALLOWLIST_PATH.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "#" not in line:
            print(
                f"{ALLOWLIST_PATH.name}:{number}: entry has no justification comment. "
                "Every allowlist entry needs a one-line justification; the allowlist is a "
                "pressure valve, not a bypass."
            )
            raise SystemExit(1)
        entry, justification = line.split("#", 1)
        if not justification.strip():
            print(f"{ALLOWLIST_PATH.name}:{number}: empty justification.")
            raise SystemExit(1)
        if "::" not in entry:
            print(
                f"{ALLOWLIST_PATH.name}:{number}: expected `<path>::<identifier> # why`."
            )
            raise SystemExit(1)
        path_part, symbol = entry.split("::", 1)
        allowed.add((path_part.strip(), symbol.strip().lower()))
    return allowed


def files_in_scope() -> list[Path]:
    """Return every file the lint reads, in a stable sequence."""
    found: list[Path] = []
    for package in IN_SCOPE_PACKAGES:
        base = PACKAGE_ROOT / package
        if not base.exists():
            continue
        found.extend(sorted(path for path in base.rglob("*.py") if path.is_file()))
    return found


def carries_implementation(path: Path) -> bool:
    """Return whether a file holds anything this lint could possibly find.

    The reasoning packages are scaffolded: each is a package directory holding an
    `__init__.py` with a docstring and no code. Counting those as scanned files is what
    would turn "13 files, clean" into a green tick over an engine that does not exist --
    DEF-0001 in a new costume. A file counts only once it defines something.
    """
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        # Unparseable source is somebody else's failure (ruff, mypy, the test run). Treat it
        # as present so this check reports on it rather than quietly narrowing its own scope.
        return True
    return any(
        isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        for node in ast.walk(tree)
    )


def scan() -> int:
    """Report every violation and return the count."""
    allowed = load_allowlist()
    violations = 0
    for path in files_in_scope():
        relative = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text()
        lines = text.splitlines()
        for number, symbol, what in violations_in(text):
            if (relative, symbol.lower()) in allowed:
                continue
            remedy = (
                "    A threshold on a domain metric is domain policy. It belongs in the "
                "pack beside the metric it bounds, not in a reasoning module, where "
                "swapping the ontology leaves it behind. If this number genuinely is not "
                "domain policy, name what it is, or add a justified entry to "
                ".lawmetric-allowlist."
                if what.startswith("the hard-coded threshold")
                else "    Metrics are declared in the pack as a MeasurementExpression tree "
                "and walked here, never recomputed. A formula in engine code does not move "
                "when the ontology is swapped, which is how a domain leaks in as a value "
                "rather than as a word. If this genuinely is not a domain metric, rename "
                "it, or add a justified entry to .lawmetric-allowlist."
            )
            print(
                f"{relative}:{number}: ADR-0026 violation -- {what} '{symbol}', "
                "a domain metric.\n"
                f"    {lines[number - 1].strip()}\n" + remedy
            )
            violations += 1
    return violations


# Every shape inline metric arithmetic takes. These must all fire.
MUST_FIRE = (
    "actual_delay = arrival - promised",
    "total_cost = unit_cost * units",
    "impact = downstream_effect * 2",
    "penalty += late_hours",
    "duration_hours = (finish - start) / 3600",
    "self.total_cost = self.base + self.surcharge",
    "quantity_short = requested - fulfilled",
    "score = observed_delay + 1",
    "weighted = 0.5 * propagation_impact",
    "delay: float = a - b",
    "record.latency = end - begin",
    "amount_due = subtotal * rate",
    # Taint: the metric is named in a string key or an attribute, never in the arithmetic.
    # Every one of these passed clean under the name-only matcher (ADR-0031).
    "raw = event.attributes['shipping_delay']\nvalue = raw * 2",
    "held = record.transit_cost\nresult = held - baseline",
    "a = row['delay_hours']\nb = a\nc = b + 1",
    "acc = row['penalty_amount']\nacc += 1",
    # Hard-coded thresholds: domain policy written into engine code.
    "if delay > 48: pass",
    "if 48 < total_cost: pass",
    "if elapsed_duration >= 1.5: pass",
    "raw = row['cost_of_delay']\nif raw > 100: pass",
)

# Near-misses. Every entry is a claim that this line computes no domain metric.
MUST_NOT_FIRE = (
    "count += 1",
    "index = position + 1",
    "depth = depth + 1",
    "total = base_value * multiplier",
    "weighted = weight * strength",
    "ratio = numerator / denominator",
    "cost_class = pack.severity_classes[0]",
    "if cost_class is None: pass",
    "label = f'{cost_class} band'",
    "delay_kind = measurement.kind",
    "impact_of = {item.id: item for item in definitions}",
    "return walk(measurement.expression)",
    # A metric compared against a VARIABLE is a guard reading a bound from somewhere else,
    # not a policy constant written here. Matching it would fire on every guard clause.
    "if delay > threshold: pass",
    "if duration is None: pass",
    "if cost_class == 'CHEAP': pass",
    "if index > 3: pass",
    "if len(items) > 3: pass",
    # Taint has to start at a metric. A string key that names no metric starts nothing.
    "raw = row['identifier']\nvalue = raw * 2",
)
#
# Entries stay SINGLE-LINE wherever a metric stem appears. The DEF-0001 guard below is
# deliberately line-blind, so a multi-line entry could hide a stem on one line and the
# arithmetic on the next and escape it; the one multi-line entry here carries no stem at
# all, so the guard's stem check skips it before that matters. The negative case that
# genuinely needs several lines -- taint must not cross a function boundary -- is asserted
# in tests/law/test_enforcement_scripts_prove_themselves.py instead, where it can be stated
# exactly rather than smuggled past a guard.


def no_must_not_fire_entry_is_actually_a_violation() -> int:
    """Refuse a MUST_NOT_FIRE entry that really does compute a metric.

    The DEF-0001 guard. A list of claimed false positives is only trustworthy if something
    independent checks the claims, and this check is deliberately cruder and stricter than
    the matcher -- a metric-stem identifier anywhere on a line that also carries an
    arithmetic operator -- so no weakening of the AST walk can make a poisoned entry look
    correct. `ratio = numerator / denominator` passes because `ratio` is not a stem here;
    that exclusion is argued in the module docstring rather than hidden in this list.
    """
    strict_stem = re.compile(
        r"(?<![A-Za-z])(" + "|".join(METRIC_STEMS) + r")", re.IGNORECASE
    )
    strict_operator = re.compile(r"[+\-*/%]")
    strict_threshold = re.compile(r"(<|>|<=|>=|==|!=)\s*-?\d")
    failures = 0
    for sample in MUST_NOT_FIRE:
        hit = strict_stem.search(sample)
        if hit is None:
            continue
        if strict_operator.search(sample):
            print(
                f"SELF-TEST FAILED: MUST_NOT_FIRE lists {sample!r}, which puts the metric "
                f"stem {hit.group(1)!r} on a line doing arithmetic. That is an ADR-0026 "
                "violation and it must fire. Remove it from the list; do not weaken the "
                "matcher to suit it."
            )
            failures += 1
        if strict_threshold.search(sample):
            print(
                f"SELF-TEST FAILED: MUST_NOT_FIRE lists {sample!r}, which compares the "
                f"metric stem {hit.group(1)!r} against a numeric literal. That is a policy "
                "constant hard-coded in engine code and it must fire. Remove it from the "
                "list; do not weaken the matcher to suit it."
            )
            failures += 1
    return failures


def self_test() -> int:
    """Prove the matcher fires on every shape metric arithmetic takes, and only on those."""
    failures = no_must_not_fire_entry_is_actually_a_violation()

    for sample in MUST_FIRE:
        if not violations_in(sample):
            print(
                f"SELF-TEST FAILED: {sample!r} computes a domain metric and did not fire."
            )
            failures += 1

    for sample in MUST_NOT_FIRE:
        found = violations_in(sample)
        if found:
            print(
                f"SELF-TEST FAILED: {sample!r} computes no domain metric but fired on "
                f"{found[0][1]!r}."
            )
            failures += 1

    if failures == 0:
        print(
            f"self-test passed: {len(MUST_FIRE)} metric-arithmetic shapes fire, "
            f"{len(MUST_NOT_FIRE)} legitimate lines stay clean, "
            "and no claimed false positive hides a computed metric."
        )
    return failures


def main() -> int:
    """Run the scan, or the self-test when asked."""
    if "--self-test" in sys.argv:
        return 1 if self_test() else 0
    scanned = files_in_scope()
    if not any(carries_implementation(path) for path in scanned):
        print(
            "ADR-0026 metric declaration: NOT-YET-RUNNABLE.\n"
            "  Every reasoning package "
            f"({', '.join(IN_SCOPE_PACKAGES)}) is scaffold only --\n"
            f"  {len(scanned)} file(s), none of which defines anything. The modules that\n"
            "  would hold engine code -- 5 through 16 -- are not built. (1 through 4 are,\n"
            "  and they are at L2 and L3, outside this scan.) There is nothing here to\n"
            "  scan. The matcher is proved by\n"
            "  --self-test; the SCAN is not evidence of anything yet, and this script says so\n"
            "  rather than exiting 0 and letting an unrun check look like a passing one\n"
            "  (DEF-0001). Tracked in PROGRESS.md as a known gap. Blocking at the P2 exit."
        )
        return 2
    violations = scan()
    if violations:
        print(
            f"\nADR-0026: {violations} metric(s) computed in engine code across "
            f"{len(scanned)} file(s). BUILD FAILED."
        )
        return 1
    print(
        f"ADR-0026: clean across {len(scanned)} file(s) in "
        f"{len(IN_SCOPE_PACKAGES)} package(s); every metric is declared, not computed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
