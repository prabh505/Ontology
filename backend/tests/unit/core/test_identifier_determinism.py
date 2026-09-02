"""Identifier determinism (`CONVENTIONS.md` §9, ADR-0013).

Content addressing is what makes a rerun comparable to its predecessor. Two failures would
destroy that quietly rather than loudly: the same input producing two identifiers (a rerun
mints duplicates and the determinism gate reports a diff nobody can explain), and two
different inputs producing one identifier (two artifacts silently merge, and an explanation
cites evidence belonging to something else).

The separator-escaping properties exist because the second failure is the plausible one: a
payload encoder that joins fields with `|` without escaping leaves makes `("a|b", "c")` and
`("a", "b|c")` indistinguishable, and nothing downstream would ever notice.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from causalog.core.errors import ContractViolationError
from causalog.core.identifiers import (
    DIGEST_LENGTH,
    PAYLOAD_SEPARATOR,
    IdentifierPrefix,
    canonical_instant,
    canonical_pairs,
    canonical_payload,
    canonical_sequence,
    canonical_text,
    digest,
    format_float,
)
from tests.unit.core.strategies import quantized_unit_floats, tokens, utc_instants

pytestmark = pytest.mark.property


# ---------------------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------------------


@given(st.sampled_from(list(IdentifierPrefix)), st.text(max_size=64))
def test_the_same_payload_always_yields_the_same_identifier(
    prefix: IdentifierPrefix, payload: str
) -> None:
    """Determinism within a process."""
    assert digest(prefix, payload) == digest(prefix, payload)


@given(st.sampled_from(list(IdentifierPrefix)), st.text(max_size=64))
def test_the_identifier_has_the_declared_shape(prefix: IdentifierPrefix, payload: str) -> None:
    """`<prefix>:<16 hex chars>` -- the shape logs, URLs, and Cypher all assume."""
    identifier = digest(prefix, payload)
    stated_prefix, _, tail = identifier.partition(":")
    assert stated_prefix == prefix.value
    assert len(tail) == DIGEST_LENGTH
    assert all(character in "0123456789abcdef" for character in tail)


@given(st.text(max_size=32), st.text(max_size=32))
def test_different_payloads_yield_different_identifiers(left: str, right: str) -> None:
    """Different payloads must not share an identifier.

    Not a collision-freedom proof -- 64 bits cannot offer one -- but it does catch a
    digest that ignores part of its input, which is the realistic defect.
    """
    if left != right:
        assert digest(IdentifierPrefix.EVENT, left) != digest(IdentifierPrefix.EVENT, right)


@given(st.text(max_size=32))
def test_the_prefix_participates_in_the_identifier(payload: str) -> None:
    """An entity and an event over one payload must not share a tail."""
    assert digest(IdentifierPrefix.EVENT, payload) != digest(IdentifierPrefix.ENTITY, payload)


def test_the_identifier_survives_a_fresh_interpreter() -> None:
    """The property no in-process test can assert.

    A digest seeded from process state -- `hash()`, `PYTHONHASHSEED`, an address -- passes
    every in-process check and produces a different answer on the next run. Only a separate
    interpreter can tell the two apart, so this test pays for a subprocess.
    """
    source_root = Path(__file__).resolve().parents[3] / "src"
    program = (
        "from causalog.core.identifiers import IdentifierPrefix, digest;"
        "print(digest(IdentifierPrefix.EVENT, 'stable-payload'))"
    )
    results = [
        subprocess.run(  # noqa: S603 -- fixed argv, no user input
            [sys.executable, "-c", program],
            capture_output=True,
            text=True,
            check=True,
            env={"PYTHONPATH": str(source_root), "PYTHONHASHSEED": seed},
        ).stdout.strip()
        for seed in ("0", "1")
    ]
    assert results[0] == results[1]
    assert results[0] == digest(IdentifierPrefix.EVENT, "stable-payload")


# ---------------------------------------------------------------------------------------
# canonicalization: the injectivity that keeps identifiers from colliding
# ---------------------------------------------------------------------------------------


@given(st.lists(tokens(), min_size=1, max_size=4))
def test_encoded_leaves_never_reintroduce_the_field_separator(
    values: list[str],
) -> None:
    """A leaf containing `|` must not be able to fake a field boundary."""
    assert PAYLOAD_SEPARATOR not in canonical_sequence(values)
    for value in values:
        assert PAYLOAD_SEPARATOR not in canonical_text(value)


@given(tokens(), tokens())
def test_leaf_escaping_is_injective(left: str, right: str) -> None:
    """Two different leaves must never escape to one string, or they would collide."""
    if left != right:
        assert canonical_text(left) != canonical_text(right)


@given(tokens(), tokens())
def test_field_boundaries_are_unambiguous(left: str, right: str) -> None:
    """One leaf containing a separator must not encode as two leaves.

    The concrete collision this design exists to prevent: one leaf containing the
    separator must not encode identically to two leaves split across it.
    """
    joined = canonical_payload(canonical_text(f"{left}{PAYLOAD_SEPARATOR}{right}"))
    split = canonical_payload(canonical_text(left), canonical_text(right))
    assert joined != split


@given(
    st.lists(
        st.tuples(tokens(), tokens()),
        min_size=1,
        max_size=4,
        unique_by=lambda pair: pair[0],
    )
)
def test_pair_encoding_is_independent_of_input_sequence(
    pairs: list[tuple[str, str]],
) -> None:
    """Pair sequence must not change the address.

    Attributes arrive in whatever sequence a caller assembled them; the address must
    not depend on it, or a rerun that iterates differently mints a duplicate.
    """
    assert canonical_pairs(pairs) == canonical_pairs(list(reversed(pairs)))


def test_an_unescaped_separator_in_a_field_is_refused() -> None:
    """Hand-built fields bypass the escaping, so the join refuses them."""
    with pytest.raises(ContractViolationError):
        canonical_payload("already|joined")


# ---------------------------------------------------------------------------------------
# float and instant formatting
# ---------------------------------------------------------------------------------------


@given(quantized_unit_floats())
def test_float_formatting_is_stable_and_round_trips(value: float) -> None:
    """One formatter, one text form, and no drift for values already quantized."""
    formatted = format_float(value)
    assert formatted == format_float(value)
    assert float(formatted) == value


def test_negative_zero_formats_as_zero() -> None:
    """`-0.0` and `0.0` are the same number and must not produce two identifiers."""
    assert format_float(-0.0) == format_float(0.0)


@given(st.sampled_from([float("nan"), float("inf"), float("-inf")]))
def test_non_finite_floats_have_no_canonical_form(value: float) -> None:
    """None of them is an admissible confidence, weight, or magnitude."""
    with pytest.raises(ContractViolationError):
        format_float(value)


@given(utc_instants())
def test_instants_encode_with_an_explicit_offset(moment: object) -> None:
    """`CONVENTIONS.md` §10: never a bare local-looking timestamp on the wire."""
    encoded = canonical_instant(moment)  # type: ignore[arg-type]
    assert encoded.endswith("+00:00")


def test_a_naive_instant_is_refused() -> None:
    """Assuming UTC is how a local time enters the system and is never noticed again."""
    from datetime import datetime

    with pytest.raises(ContractViolationError):
        canonical_instant(datetime(2026, 1, 1))  # noqa: DTZ001 -- the defect under test
