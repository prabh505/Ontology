r"""LAW-DOMAIN's enforcement must itself be tested.

A lint that has never failed has not been tested, and a lint with false positives gets
disabled -- which returns LAW-DOMAIN to convention-only status (`CONVENTIONS.md` §6).

DEF-0001 is the reason this module is shaped the way it is. The first matcher used `\\b`
whole-word matching, which caught only the bare English word: `warehouse_id`, `orders`,
`WAREHOUSE_TABLE`, and `customerName` all passed clean. Worse, the self-test listed
`shipments` among the words that must never fire, certifying the hole as correct behaviour.
The identifier-form cases below are the regression suite for that defect.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.law

# The four probes that defeated the previous matcher, verbatim from the review.
REVIEW_PROBES = (
    "# probe A: warehouses plural",
    "# probe B: def resolve_shipments(orders): pass",
    '# probe C: WAREHOUSE_TABLE = "customers"',
    "# probe D: warehouse_id field",
)

# The forms domain vocabulary actually takes in code, as opposed to in prose.
IDENTIFIER_FORMS = (
    "warehouse_id",
    "order_id",
    "customer_name",
    "WAREHOUSE_TABLE",
    "DELIVERY_STATUS",
    "customerName",
    "OrderId",
    "orders",
    "shipments",
    "customers",
    "deliveries",
    "inventories",
    "carriers",
    "sort_order",
)


def test_matcher_fires_on_every_banned_stem(domain_lint: ModuleType) -> None:
    for stem in domain_lint.BANNED_STEMS:
        assert domain_lint.PATTERN.search(f"a bare {stem} in a sentence"), stem


@pytest.mark.parametrize("probe", REVIEW_PROBES)
def test_review_probes_now_fire(domain_lint: ModuleType, probe: str) -> None:
    r"""DEF-0001 regression. Each of these passed clean under the `\b` matcher."""
    assert domain_lint.PATTERN.search(probe) is not None


@pytest.mark.parametrize("form", IDENTIFIER_FORMS)
def test_identifier_forms_fire(domain_lint: ModuleType, form: str) -> None:
    """Vocabulary in code is `warehouse_id`, not `warehouse`. The lint must see both."""
    assert domain_lint.PATTERN.search(f"value = {form}") is not None


@pytest.mark.parametrize(
    "word",
    [
        "ordering",
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
        "sorted",
        "sequence",
        "record",
    ],
)
def test_matcher_does_not_fire_on_near_misses(domain_lint: ModuleType, word: str) -> None:
    r"""These are all legitimate in a temporal reasoning system.

    `ordering` is the exception that proves the rule: it DOES contain the banned stem, so
    the matcher fires on it and ADR-0019 accepts that cost -- reasoning packages write
    "sequence" instead. It is listed here so the asymmetry is visible rather than implied.
    """
    matched = domain_lint.PATTERN.search(f"canonical {word} key")
    if word == "ordering":
        assert matched is not None, "ADR-0019 bans the whole order stem, including `ordering`"
        return
    assert matched is None


def test_self_test_rejects_a_poisoned_must_not_fire_list(
    domain_lint: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The DEF-0001 root cause must be structurally impossible to recommit.

    The old list claimed `shipments` and `customers_table_in_a_name` were false positives.
    Both are domain vocabulary. The guard checks the claims independently of the matcher,
    so weakening the matcher cannot make a poisoned entry look correct.
    """
    monkeypatch.setattr(
        domain_lint, "MUST_NOT_FIRE", ("reorder", "shipments", "customers_table_in_a_name")
    )
    assert domain_lint.no_must_not_fire_entry_hides_a_stem() == 2


def test_shipped_self_test_passes(domain_lint: ModuleType) -> None:
    assert domain_lint.self_test() == 0


def test_planted_violation_is_detected(
    domain_lint: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plant domain vocabulary in a reasoning package and assert the lint reports it."""
    package = tmp_path / "core"
    package.mkdir()
    (package / "leak.py").write_text("WAREHOUSE_TABLE = 'x'\ndef resolve_shipments(orders): pass\n")

    monkeypatch.setattr(domain_lint, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(domain_lint, "PACKAGE_ROOT", tmp_path)
    monkeypatch.setattr(domain_lint, "ALLOWLIST_PATH", tmp_path / ".lawdomain-allowlist")

    assert domain_lint.scan() == 3  # WAREHOUSE_TABLE, shipments, orders


def test_allowlist_exempts_the_exact_match_only(
    domain_lint: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An entry must exempt one occurrence, never a family (ADR-0019)."""
    package = tmp_path / "core"
    package.mkdir()
    (package / "leak.py").write_text("warehouse_id = 1\nwarehouse_name = 2\n")
    allowlist = tmp_path / ".lawdomain-allowlist"
    allowlist.write_text("core/leak.py::warehouse_id  # reviewed: not domain here\n")

    monkeypatch.setattr(domain_lint, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(domain_lint, "PACKAGE_ROOT", tmp_path)
    monkeypatch.setattr(domain_lint, "ALLOWLIST_PATH", allowlist)

    assert domain_lint.scan() == 1  # warehouse_name is NOT covered by the warehouse_id entry


def test_allowlist_entry_without_justification_fails(
    domain_lint: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The allowlist is a pressure valve, not a bypass; an unjustified entry is refused."""
    allowlist = tmp_path / ".lawdomain-allowlist"
    allowlist.write_text("core/leak.py::warehouse\n")
    monkeypatch.setattr(domain_lint, "ALLOWLIST_PATH", allowlist)

    with pytest.raises(SystemExit):
        domain_lint.load_allowlist()


def test_repository_is_clean(domain_lint: ModuleType) -> None:
    assert domain_lint.scan() == 0
