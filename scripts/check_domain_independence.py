#!/usr/bin/env python3
"""LAW-DOMAIN enforcement.

No file in a reasoning package may contain domain vocabulary. Domain vocabulary lives in
`ontology/` and `rule_engine/` as DATA (ADR-0002).

Specification: `CONVENTIONS.md` §6, ratified by ADR-0010.

  Scope       every file under core/, graph_engine/, causal_engine/,
              counterfactual_engine/, recommendation_engine/, rule_engine/ (code)
  Concepts    warehouse, shipment, order, carrier, customer, delivery, inventory
  Matching    case-insensitive STEM-PREFIX with a letter-only lookbehind. See the
              PATTERN comment below for why, and for what this deliberately does not
              exclude.

              This replaced `\b`-delimited whole-word matching, which was ineffective:
              `\b` requires a non-word character after the token and `_` IS a word
              character, so `warehouse_id`, `order_id`, `WAREHOUSE_TABLE`, `orders`,
              `shipments`, and `OrderId` all passed clean. Those are the forms domain
              vocabulary actually takes in code; the old matcher caught essentially only
              the bare English word in a comment. See DEF-0001 and ADR-0019.
  Exempt      tests/fixtures/**, ontology/**, rule_engine/**/*.yaml|*.json (data)
              `rule_engine` SOURCE CODE is explicitly not exempt
  Allowlist   .lawdomain-allowlist, one reviewed entry per line WITH a justification
  Failure     exit 1. This job fails the build. It does not warn.

Run `--self-test` to prove the matcher fires on every form domain vocabulary takes AND
stays clean on the non-domain words that contain a banned stem. The self-test additionally
refuses a MUST_NOT_FIRE entry that actually contains a banned stem -- the previous
self-test listed `shipments` as a word that must never fire, which certified the defect
rather than catching it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = REPO_ROOT / "backend" / "src" / "causalog"

# Truncated to the invariant root of each banned concept, so one entry covers every
# inflection: `warehous` covers warehouse/warehouses/warehousing, `deliver` covers
# delivery/deliveries/delivered, `inventor` covers inventory/inventories.
BANNED_STEMS = (
    "warehous",
    "shipment",
    "order",
    "carrier",
    "customer",
    "deliver",
    "inventor",
)

IN_SCOPE_PACKAGES = (
    "core",
    "graph_engine",
    "causal_engine",
    "counterfactual_engine",
    "recommendation_engine",
    "rule_engine",
)

SCANNED_SUFFIXES = (".py", ".md", ".sql", ".cypher")

EXEMPT_PATH_PARTS = ("tests/fixtures/",)

ALLOWLIST_PATH = REPO_ROOT / ".lawdomain-allowlist"

# Stem-prefix match, anchored by a LETTER-ONLY lookbehind and followed by a greedy letter
# tail.
#
#   (?<![A-Za-z])   a preceding LETTER means the stem sits inside a longer word --
#                   `reorder`, `recorder`, `border`, `bordering` -- which is not domain
#                   vocabulary. This is deliberately [A-Za-z] and NOT \w: a preceding
#                   underscore or digit means the stem is a separate identifier component
#                   (`sort_order`, `v2_customer`), and that IS the vocabulary we ban.
#   [A-Za-z0-9_]*   swallows the rest of the identifier. This is the part `\b` could not
#                   do, and its absence is what let `warehouse_id`, `orders`,
#                   `customerName`, and `OrderId` through for the whole of DEF-0001.
#                   The tail includes `_` so the REPORTED text is the whole identifier
#                   (`warehouse_id`, `ORDER_BY`) rather than just its first component.
#                   That matters for the allowlist, whose entries key on the reported
#                   text: an entry for `order_by` must not also exempt `order_id`.
#
# Words like `ordinal`, `coordinate`, and `sorted` never match because they do not contain
# a banned stem at all -- they need no special handling.
PATTERN = re.compile(
    r"(?<![A-Za-z])(" + "|".join(BANNED_STEMS) + r")[A-Za-z0-9_]*", re.IGNORECASE
)

# Every form domain vocabulary actually takes in code. The last four entries are the review
# probes that defeated the previous matcher; they are regression cases now, not anecdotes.
MUST_FIRE = (
    "a bare warehouse in prose",
    "shipment",
    "order",
    "carrier",
    "customer",
    "delivery",
    "inventory",
    "warehouses",
    "orders",
    "customers",
    "deliveries",
    "inventories",
    "carriers",
    "order_id",
    "customer_name",
    "DELIVERY_STATUS",
    "customerName",
    "OrderId",
    "v2_customer",
    "sort_order",
    "# probe A: warehouses plural",
    "# probe B: def resolve_shipments(orders): pass",
    '# probe C: WAREHOUSE_TABLE = "customers"',
    "# probe D: warehouse_id field",
)

# Non-domain words that contain, or look like they contain, a banned stem. Every entry here
# is a claim that the word is legitimate in a temporal reasoning system.
#
# `shipments` and `customers_table_in_a_name` were previously listed here. They are domain
# vocabulary. The `no_must_not_fire_entry_hides_a_stem` guard below now makes that class of
# mistake impossible to commit silently.
MUST_NOT_FIRE = (
    "reorder",
    "reordering",
    "reordered",
    "reorder_key",
    "recorder",
    "recorded",
    "border",
    "bordering",
    "ordinal",
    "coordinate",
    "coordinates",
    "sorted",
    "sorting",
    "sequence",
    "sequenced",
    "record",
    "records",
)


def load_allowlist() -> set[tuple[str, str]]:
    """Return the reviewed (relative_path, matched_text) pairs, refusing malformed entries.

    The second element is the EXACT matched text, lowercased -- `warehouse_id`, not the
    `warehous` stem. An entry must exempt one specific occurrence, never a whole family;
    keying on the stem would let one reviewed exception silently cover every inflection.
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
                f"{ALLOWLIST_PATH.name}:{number}: expected "
                "`<path>::<exact matched text> # why`."
            )
            raise SystemExit(1)
        path_part, matched_text = entry.split("::", 1)
        allowed.add((path_part.strip(), matched_text.strip().lower()))
    return allowed


def files_in_scope() -> list[Path]:
    """Return every file the lint reads, in a stable sequence."""
    found: list[Path] = []
    for package in IN_SCOPE_PACKAGES:
        base = PACKAGE_ROOT / package
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
                continue
            relative = path.relative_to(REPO_ROOT).as_posix()
            if any(part in relative for part in EXEMPT_PATH_PARTS):
                continue
            found.append(path)
    return found


def scan() -> int:
    """Report every violation and return the count."""
    allowed = load_allowlist()
    violations = 0
    for path in files_in_scope():
        relative = path.relative_to(REPO_ROOT).as_posix()
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            for match in PATTERN.finditer(line):
                # The whole match, not the stem: an allowlist entry exempts `warehouse_id`
                # specifically and must not also exempt `warehouse_name`.
                matched_text = match.group(0).lower()
                if (relative, matched_text) in allowed:
                    continue
                print(
                    f"{relative}:{number}: LAW-DOMAIN violation -- domain vocabulary "
                    f"'{match.group(0)}' in a reasoning package.\n"
                    f"    {line.strip()}\n"
                    "    Domain vocabulary belongs in ontology/ or rule_engine/ as data "
                    "(ADR-0002). If this word is genuinely non-domain here, add a "
                    "justified entry to .lawdomain-allowlist."
                )
                violations += 1
    return violations


def no_must_not_fire_entry_hides_a_stem() -> int:
    """Refuse a MUST_NOT_FIRE entry that genuinely contains a banned stem.

    This guard exists because of DEF-0001. The previous self-test listed `shipments` and
    `customers_table_in_a_name` as words that must never fire -- both are domain
    vocabulary, so the test asserted the matcher's hole was correct behaviour. A list of
    claimed false positives is only trustworthy if something independent checks the claims,
    and that something is this function: it uses a strict stem search that no matcher
    change can weaken.
    """
    strict = re.compile(
        r"(?<![A-Za-z])(" + "|".join(BANNED_STEMS) + r")", re.IGNORECASE
    )
    failures = 0
    for word in MUST_NOT_FIRE:
        hit = strict.search(word)
        if hit:
            print(
                f"SELF-TEST FAILED: MUST_NOT_FIRE lists {word!r}, which contains the "
                f"banned stem {hit.group(1)!r}. That is domain vocabulary and it must "
                "fire. Remove it from the list; do not weaken the matcher to suit it."
            )
            failures += 1
    return failures


def self_test() -> int:
    """Prove the matcher fires on every form vocabulary takes, and only on those."""
    failures = no_must_not_fire_entry_hides_a_stem()

    for sample in MUST_FIRE:
        if not PATTERN.search(sample):
            print(
                f"SELF-TEST FAILED: {sample!r} is domain vocabulary and did not fire."
            )
            failures += 1

    for word in MUST_NOT_FIRE:
        match = PATTERN.search(f"canonical {word} key")
        if match:
            print(
                f"SELF-TEST FAILED: {word!r} is legitimate in a temporal reasoning "
                f"system but fired on {match.group(0)!r}."
            )
            failures += 1

    if failures == 0:
        print(
            f"self-test passed: {len(MUST_FIRE)} vocabulary forms fire, "
            f"{len(MUST_NOT_FIRE)} non-domain words stay clean, "
            "and no claimed false positive hides a banned stem."
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
            f"\nLAW-DOMAIN: {violations} violation(s) across {scanned} file(s). BUILD FAILED."
        )
        return 1
    print(
        f"LAW-DOMAIN: clean across {scanned} file(s) in {len(IN_SCOPE_PACKAGES)} package(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
