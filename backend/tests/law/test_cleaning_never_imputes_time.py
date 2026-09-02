"""LAW-TIME / R-01: no cleaning path can manufacture an instant the source did not record.

`CONVENTIONS.md` §10 forbids imputing a timestamp outright. `TimeInterval` enforces part of
that at construction. This file enforces the rest, at the layer where a source string first
becomes an instant -- because that is where imputation would enter, and it would enter
looking like a formatting decision rather than like a guess.

The registry is ENUMERATED here rather than sampled. A test that checks the transforms it
happens to know about is a test that stops covering the one somebody adds next week.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from causalog.core.errors import DataQualityError
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import (
    UNKNOWN_EARLIEST,
    UNKNOWN_LATEST,
    Precision,
    TemporalVerdict,
    verdict,
)
from causalog.ingestion.data_adapter.cleaning import (
    PRECISION_SPANS,
    TRANSFORM_RATIONALE,
    build_interval,
)
from causalog.ingestion.schema_mapper.dsl import (
    TEMPORAL_TRANSFORMS,
    TemporalBindingSpec,
    Transform,
)

pytestmark = pytest.mark.law

COARSE_PRECISIONS = (Precision.SECOND, Precision.MINUTE, Precision.HOUR, Precision.DAY)


def _binding(precision: Precision) -> TemporalBindingSpec:
    return TemporalBindingSpec(column="c", source_format="%Y-%m-%d %H:%M:%S", precision=precision)


@pytest.mark.parametrize("precision", COARSE_PRECISIONS)
def test_no_declared_precision_produces_an_exact_instant(precision: Any) -> None:
    """An EXACT interval asserts a point the source never pinned down."""
    interval = build_interval("2020-06-15 13:45:30", _binding(precision))
    assert interval.precision is not Precision.EXACT
    assert interval.t_latest > interval.t_earliest


@pytest.mark.parametrize("precision", COARSE_PRECISIONS)
def test_every_transform_widens_and_none_narrows(precision: Any) -> None:
    """The parsed instant must lie inside the interval the transform produced."""
    interval = build_interval("2020-06-15 13:45:30", _binding(precision))
    parsed = datetime(2020, 6, 15, 13, 45, 30, tzinfo=UTC)
    assert interval.t_earliest <= parsed <= interval.t_latest


def test_the_mapping_dsl_refuses_to_declare_exact_precision() -> None:
    """Imputation must not be reachable through a configuration field."""
    with pytest.raises(ValueError, match="EXACT"):
        TemporalBindingSpec(column="c", source_format="%Y-%m-%d", precision=Precision.EXACT)


def test_a_missing_instant_becomes_unbounded_unknown_and_assumed() -> None:
    interval = build_interval(None, _binding(Precision.DAY))
    assert interval.precision is Precision.UNKNOWN
    assert interval.provenance is ProvenanceClass.ASSUMED
    assert (interval.t_earliest, interval.t_latest) == (UNKNOWN_EARLIEST, UNKNOWN_LATEST)


def test_an_unknown_instant_supports_no_temporal_claim_in_either_direction() -> None:
    unknown = build_interval("", _binding(Precision.DAY))
    known = build_interval("2020-06-15 13:45:30", _binding(Precision.DAY))
    assert verdict(unknown, known) is TemporalVerdict.UNDETERMINED
    assert verdict(known, unknown) is TemporalVerdict.UNDETERMINED


def test_an_unreadable_instant_is_refused_rather_than_reparsed_by_a_second_format() -> None:
    """Choosing between 'a different format' and 'corrupt' is a guess, so neither is made."""
    with pytest.raises(DataQualityError, match="source_format"):
        build_interval("15/06/2020 13:45:30", _binding(Precision.DAY))


def test_the_precision_span_table_only_ever_widens() -> None:
    """Enumerated over the whole table: a negative or zero span would narrow or pin."""
    for precision, span in PRECISION_SPANS.items():
        assert span.total_seconds() > 0, f"{precision.value} does not widen"
    assert Precision.EXACT not in PRECISION_SPANS
    assert Precision.UNKNOWN not in PRECISION_SPANS


def test_every_temporal_transform_is_registered_and_documented() -> None:
    """A transform with no stated rationale is a change nobody has to justify."""
    for transform in TEMPORAL_TRANSFORMS:
        assert transform in TRANSFORM_RATIONALE
        assert TRANSFORM_RATIONALE[transform].strip()


def test_no_transform_name_suggests_narrowing_an_instant() -> None:
    """A structural guard on the registry itself, not on today's members."""
    forbidden = ("ROUND", "SNAP", "IMPUTE", "FILL", "INFER", "ESTIMATE", "GUESS", "DEFAULT")
    for transform in Transform:
        assert not any(word in transform.value for word in forbidden), (
            f"{transform.value} names an operation that would manufacture a value; "
            "CONVENTIONS.md §10 forbids imputation and the registry is where it would enter."
        )
