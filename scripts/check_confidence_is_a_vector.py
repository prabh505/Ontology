#!/usr/bin/env python3
"""LAW-EVIDENCE enforcement: confidence is never a bare float.

`ConfidenceVector` is the authoritative representation (ADR-0009). A judgement carried as a
bare `float` has no named components, no evidence trace, and no aggregation function, which
is exactly the unexplained number prd.md §49 forbids -- and it fails silently, because a
float is a perfectly valid float.

Specification: `docs/contracts.md` §5, ADR-0009, LAW-EVIDENCE.

  Scope       every `.py` file under backend/src/causalog/
  Matched     an annotation, parameter, or cast binding a confidence-named symbol to a
              numeric type: `confidence: float`, `edge_confidence: float`,
              `confidence_score: int`, `-> float` on a function named `*confidence*`.
  Not matched `EvidenceItem.strength` and anything else not NAMED for confidence. Naming is
              the whole signal available to a textual lint: a bare float called `strength`
              is documented as one item's own weight, not a confidence, and the contract
              says so explicitly. See MUST_NOT_FIRE.
  Allowlist   .lawevidence-allowlist, one reviewed entry per line WITH a justification
  Failure     exit 1. This job fails the build. It does not warn.

Run `--self-test` to prove the matcher fires on every shape a bare-float confidence takes
AND stays clean on the near-misses that are legitimate. Per `CONVENTIONS.md` §1, a check
that has never been observed to reject has not been tested, so the self-test runs before
the scan in `make laws`.

**What this does not catch.** A float carried under a name that says nothing
(`value: float`, `score: float`) passes clean, as does a confidence smuggled inside a dict
or a tuple. This lint raises the cost of the mistake; it does not make it impossible. The
structural guarantee remains the type of `CausalEdge.confidence` and `Event.confidence`,
both `ConfidenceVector`, which no lint is needed to enforce.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# Source only, matching `check_domain_independence.py`'s precedent. The test tree is
# excluded because a lint that scans its own regression corpus fires on every probe in it,
# and the natural fix -- deleting the probes -- is how a check stops being tested.
SCAN_ROOTS = (REPO_ROOT / "backend" / "src" / "causalog",)

ALLOWLIST_PATH = REPO_ROOT / ".lawevidence-allowlist"

NUMERIC_TYPES = ("float", "int", "Decimal", "complex")

# Two shapes, one pattern each.
#
#   ANNOTATION  a name containing `confidence` bound to a numeric type by `:` -- covers
#               model fields, dataclass fields, parameters, locals, and `x: float = 0.0`.
#               The name may carry prefixes and suffixes (`edge_confidence_score`), so the
#               match is substring-on-identifier, not whole-word.
#   RETURN      a def whose NAME contains `confidence` returning a numeric type. A function
#               called `edge_confidence` returning `float` hands a caller the same
#               unexplained number a field would.
#
# `Optional[float]`, `float | None`, and `list[float]` are all reached, because the numeric
# type is matched wherever it appears in the annotation tail rather than anchored to it.
# The prefix quantifier is `*`, not `+`: the commonest form of the defect is the bare field
# `confidence: float`, which a pattern requiring a leading identifier character misses
# entirely. The self-test caught exactly that during development, which is what a self-test
# is for (`CONVENTIONS.md` §1). The lookbehind, not a leading `\b`, is what keeps the
# optional prefix from matching mid-identifier.
_CONFIDENCE_NAME = r"(?<![A-Za-z0-9_])(?P<name>[A-Za-z0-9_]*confidence[A-Za-z0-9_]*)"

ANNOTATION_PATTERN = re.compile(
    _CONFIDENCE_NAME + r"\s*:\s*(?P<tail>[^=#\n]+)",
    re.IGNORECASE,
)
RETURN_PATTERN = re.compile(
    r"\bdef\s+" + _CONFIDENCE_NAME + r"\s*\([^)]*\)\s*->\s*(?P<tail>[^:#\n]+)",
    re.IGNORECASE,
)
NUMERIC_IN_TAIL = re.compile(
    r"(?<![A-Za-z0-9_])(" + "|".join(NUMERIC_TYPES) + r")(?![A-Za-z0-9_])"
)

# Every shape a bare-float confidence takes. These must all fire.
MUST_FIRE = (
    "    confidence: float",
    "    confidence: int",
    "    edge_confidence: float",
    "    confidence_score: float",
    "    causal_confidence_value: Decimal",
    "    confidence: float = 0.0",
    "    confidence: float | None = None",
    "    confidence: Optional[float]",
    "    component_confidences: list[float]",
    "def edge_confidence(edge: object) -> float:",
    "def compute_confidence(x: int, y: int) -> float:",
    "    CONFIDENCE: float = 0.5",
)

# Near-misses. Every entry is a claim that this line is legitimate under LAW-EVIDENCE.
#
# `strength` leads the list deliberately: it is the one bare float in the vicinity of a
# judgement that the contract explicitly sanctions, and a lint that fired on it would be
# disabled within a week -- which returns LAW-EVIDENCE to convention-only status.
MUST_NOT_FIRE = (
    "    strength: float",
    "    propagation_weight: float",
    "    magnitude_multiplier: float",
    "    value: float",
    "    scalar: float",
    "    confidence: ConfidenceVector",
    "    confidence: ConfidenceVector | None = None",
    "    edge_confidence: ConfidenceVector",
    "def build_confidence(components: object) -> ConfidenceVector:",
    "    confidence_schema_version: str",
    "    aggregation: str",
    '    """confidence is a decomposition, never a bare float."""',
)


def load_allowlist() -> set[tuple[str, str]]:
    """Return the reviewed (relative_path, symbol_name) pairs, refusing malformed entries.

    Keyed on the exact symbol, lowercased. An entry exempts one binding, never a family:
    an approved `legacy_confidence` must not also exempt `legacy_confidence_v2`.
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
                f"{ALLOWLIST_PATH.name}:{number}: expected `<path>::<symbol name> # why`."
            )
            raise SystemExit(1)
        path_part, symbol = entry.split("::", 1)
        allowed.add((path_part.strip(), symbol.strip().lower()))
    return allowed


def violations_in(line: str) -> list[str]:
    """Return the confidence-named symbols this line binds to a numeric type."""
    found: list[str] = []
    for pattern in (ANNOTATION_PATTERN, RETURN_PATTERN):
        for match in pattern.finditer(line):
            if NUMERIC_IN_TAIL.search(match.group("tail")):
                found.append(match.group("name"))
    return found


def files_in_scope() -> list[Path]:
    """Return every file the lint reads, in a stable sequence."""
    found: list[Path] = []
    for base in SCAN_ROOTS:
        if not base.exists():
            continue
        found.extend(sorted(path for path in base.rglob("*.py") if path.is_file()))
    return found


def scan() -> int:
    """Report every violation and return the count."""
    allowed = load_allowlist()
    violations = 0
    for path in files_in_scope():
        relative = path.relative_to(REPO_ROOT).as_posix()
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            for symbol in violations_in(line):
                if (relative, symbol.lower()) in allowed:
                    continue
                print(
                    f"{relative}:{number}: LAW-EVIDENCE violation -- '{symbol}' is bound "
                    "to a numeric type.\n"
                    f"    {line.strip()}\n"
                    "    Confidence is a ConfidenceVector: named components, each tracing "
                    "to evidence, plus a named aggregation (ADR-0009). A bare float is the "
                    "unexplained number prd.md §49 forbids. If this genuinely is not a "
                    "confidence, rename it, or add a justified entry to "
                    ".lawevidence-allowlist."
                )
                violations += 1
    return violations


def no_must_not_fire_entry_is_actually_a_violation() -> int:
    """Refuse a MUST_NOT_FIRE entry that really does bind a confidence to a number.

    The DEF-0001 guard, transplanted. A list of claimed false positives is only trustworthy
    if something independent checks the claims. This check is deliberately cruder and
    stricter than the matcher -- a confidence-named symbol on the same line as a numeric
    type word -- so no weakening of the matcher can make a poisoned entry look correct.
    """
    # `*` on the prefix, for the same reason as the matcher: a bare `confidence: float`
    # entry is the poisoning most likely to be attempted, and a guard that misses it is
    # precisely the DEF-0001 shape -- a self-test certifying the hole as correct behaviour.
    strict_name = re.compile(
        r"(?<![A-Za-z0-9_])[A-Za-z0-9_]*confidence[A-Za-z0-9_]*\s*:", re.IGNORECASE
    )
    failures = 0
    for sample in MUST_NOT_FIRE:
        if sample.lstrip().startswith(('"', "#")):
            continue
        if strict_name.search(sample) and NUMERIC_IN_TAIL.search(sample):
            print(
                f"SELF-TEST FAILED: MUST_NOT_FIRE lists {sample!r}, which binds a "
                "confidence-named symbol to a numeric type. That is a LAW-EVIDENCE "
                "violation and it must fire. Remove it from the list; do not weaken the "
                "matcher to suit it."
            )
            failures += 1
    return failures


def self_test() -> int:
    """Prove the matcher fires on every bare-float shape, and only on those."""
    failures = no_must_not_fire_entry_is_actually_a_violation()

    for sample in MUST_FIRE:
        if not violations_in(sample):
            print(
                f"SELF-TEST FAILED: {sample!r} is a bare-float confidence and did not fire."
            )
            failures += 1

    for sample in MUST_NOT_FIRE:
        found = violations_in(sample)
        if found:
            print(
                f"SELF-TEST FAILED: {sample!r} is legitimate under LAW-EVIDENCE but fired "
                f"on {found!r}."
            )
            failures += 1

    if failures == 0:
        print(
            f"self-test passed: {len(MUST_FIRE)} bare-float shapes fire, "
            f"{len(MUST_NOT_FIRE)} legitimate lines stay clean, "
            "and no claimed false positive hides a violation."
        )
    return failures


def main() -> int:
    """Run the scan, or the self-test when asked."""
    if "--self-test" in sys.argv:
        return 1 if self_test() else 0
    scanned = len(files_in_scope())
    violations = scan()
    if violations:
        print(
            f"\nLAW-EVIDENCE: {violations} violation(s) across {scanned} file(s). BUILD FAILED."
        )
        return 1
    print(
        f"LAW-EVIDENCE: clean across {scanned} file(s); confidence is a vector everywhere."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
