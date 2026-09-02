"""Column profiling: two streaming passes, exact where it can be, honest where it cannot.

**No tabular library.** Adding one needs an ADR (`CONVENTIONS.md` §12) and would buy nothing
a streaming profiler does not already give, while costing a large transitive dependency tree
and a second answer to what a value's type is. The standard library computes every statistic
here exactly, in bounded memory, over a file of any size.

Why two passes and not one
--------------------------
Quantiles and an outlier fence need the distribution's range before they can be binned, and
the range is not known until the data has been read. The alternatives are a reservoir sample
-- which is random, and therefore forbidden (`CONVENTIONS.md` §11) -- or a streaming sketch,
which is approximate without saying by how much. Two exact passes over a file cost seconds
and are byte-for-byte reproducible, so that is what this does.

  * **Pass 1** -- type lattice, null and blank rates, exact minimum and maximum, Welford
    mean and variance, and a bounded exact distinct-value counter.
  * **Pass 2** -- a fixed-width histogram over pass 1's bounds, giving quantiles, the
    interquartile fence, and outlier counts.

Where it stops being exact, it says so
--------------------------------------
The distinct-value counter is bounded. On overflow it does NOT truncate quietly: it sets
`distinct_exact = False` and reports the cap it hit. A profiler that reports "50 000 distinct
values" for a column with two million is the DEF-0001 failure -- a check that stopped being
the check it claims to be, with nothing in the output saying so.

The outlier rule and its parameters travel in the profile for the same reason. An outlier
count with no stated fence is a number nobody can argue with, which is not the same as a
number that is right.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from enum import Enum
from typing import Final

from pydantic import BaseModel, ConfigDict

__all__ = [
    "DEFAULT_DISTINCT_CAP",
    "DEFAULT_HISTOGRAM_BINS",
    "DEFAULT_TOP_VALUE_COUNT",
    "IQR_FENCE_MULTIPLIER",
    "ColumnProfile",
    "DatasetProfile",
    "InferredType",
    "NumericSummary",
    "Profiler",
    "TemporalSummary",
    "classify_value",
]

#: Distinct values held per column before the counter admits it stopped being exact.
DEFAULT_DISTINCT_CAP: Final[int] = 50_000

#: Most-frequent values carried in the profile, sequenced by `(-count, value)`.
DEFAULT_TOP_VALUE_COUNT: Final[int] = 20

#: Bins in the pass-2 histogram. Fixed, so quantiles are reproducible.
DEFAULT_HISTOGRAM_BINS: Final[int] = 1_024

#: Tukey's fence. Reported in the profile beside the counts it produced.
IQR_FENCE_MULTIPLIER: Final[float] = 1.5

#: The fewest digits any recognised date shape carries. Used by the shape gate below.
_MINIMUM_DATE_DIGITS: Final[int] = 4

_INTEGER_RE: Final[re.Pattern[str]] = re.compile(r"^[+-]?\d+$")
_DECIMAL_RE: Final[re.Pattern[str]] = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")

#: Values treated as booleans. Deliberately small and case-folded; anything else is
#: categorical text, and guessing wider would silently collapse two categories into one.
_BOOLEAN_VALUES: Final[frozenset[str]] = frozenset({"0", "1", "true", "false", "yes", "no"})

#: Date and datetime shapes recognised for PROFILING only.
#:
#: This list decides what the report SAYS about granularity. It never decides how a value is
#: parsed for use -- that comes from the mapping's declared `source_format`, because a
#: format the engine guessed is a format the engine can guess wrong, and a wrong guess
#: between `M/D/Y` and `D/M/Y` is silent for eleven days of every month.
_DATETIME_FORMATS: Final[tuple[tuple[str, bool], ...]] = (
    ("%Y-%m-%dT%H:%M:%S%z", True),
    ("%Y-%m-%d %H:%M:%S%z", True),
    ("%m/%d/%Y %H:%M", True),
    ("%m/%d/%Y %H:%M:%S", True),
    ("%Y-%m-%d %H:%M:%S", True),
    ("%Y-%m-%dT%H:%M:%S", True),
    ("%d/%m/%Y %H:%M", True),
    ("%m/%d/%Y", False),
    ("%Y-%m-%d", False),
    ("%d/%m/%Y", False),
)


class InferredType(str, Enum):
    """The observed type of a column, as a lattice joined upward across its values.

    `EMPTY` is the bottom (a column with no non-blank value at all) and `TEXT` the top.
    Two values of different types join to the least type that admits both, which for most
    disagreements is `TEXT` -- the honest answer for a column the source did not keep
    consistent.
    """

    EMPTY = "EMPTY"
    BOOLEAN = "BOOLEAN"
    INTEGER = "INTEGER"
    DECIMAL = "DECIMAL"
    DATE = "DATE"
    DATETIME = "DATETIME"
    TEXT = "TEXT"


#: The join table. Only the pairs that have a common type below `TEXT` are listed; every
#: other disagreement joins to `TEXT`.
_JOINS: Final[Mapping[frozenset[InferredType], InferredType]] = {
    frozenset({InferredType.BOOLEAN, InferredType.INTEGER}): InferredType.INTEGER,
    frozenset({InferredType.BOOLEAN, InferredType.DECIMAL}): InferredType.DECIMAL,
    frozenset({InferredType.INTEGER, InferredType.DECIMAL}): InferredType.DECIMAL,
    frozenset({InferredType.DATE, InferredType.DATETIME}): InferredType.DATETIME,
}


def _could_be_date(text: str) -> bool:
    """Return whether a value is worth attempting eight `strptime` parses on.

    A shape gate, not a parse. Every recognised date shape carries a `/` or `-` separator
    and at least four digits, so a value with neither cannot match one -- and skipping the
    parse loop for those is the difference between profiling this dataset in seconds and
    profiling it in minutes. Being wrong in the permissive direction costs a parse attempt;
    being wrong in the strict direction would misreport a column's type, so the gate is
    deliberately looser than the formats it guards.
    """
    if "/" not in text and "-" not in text:
        return False
    digits = 0
    for character in text:
        if character.isdigit():
            digits += 1
            if digits >= _MINIMUM_DATE_DIGITS:
                return True
    return False


def classify_value(text: str) -> InferredType:
    """Return the narrowest type one non-blank source value belongs to."""
    if text.lower() in _BOOLEAN_VALUES:
        return InferredType.BOOLEAN
    if _INTEGER_RE.match(text):
        return InferredType.INTEGER
    if _DECIMAL_RE.match(text):
        return InferredType.DECIMAL
    if not _could_be_date(text):
        return InferredType.TEXT
    for pattern, has_time in _DATETIME_FORMATS:
        try:
            datetime.strptime(text, pattern)  # noqa: DTZ007 -- classification, never a value
        except ValueError:
            continue
        return InferredType.DATETIME if has_time else InferredType.DATE
    return InferredType.TEXT


def _join(left: InferredType, right: InferredType) -> InferredType:
    """Return the least type admitting both, or `TEXT` when they have nothing in common."""
    if left is right:
        return left
    if left is InferredType.EMPTY:
        return right
    if right is InferredType.EMPTY:
        return left
    return _JOINS.get(frozenset({left, right}), InferredType.TEXT)


class NumericSummary(BaseModel):
    """Distribution of a column's numeric values, and the fence used to call an outlier."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    count: int
    minimum: float
    maximum: float
    mean: float
    standard_deviation: float
    p01: float
    p25: float
    p50: float
    p75: float
    p99: float
    fence_rule: str
    fence_low: float
    fence_high: float
    outliers_low: int
    outliers_high: int
    histogram_bins: int


class TemporalSummary(BaseModel):
    """What a column's date-like values look like, and how finely they are pinned down."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    parsed_count: int
    unparsed_count: int
    """Non-blank values in this column that no recognised date shape matched. Derived, not
    accumulated: a column is temporal because SOME of its values are, and the ones that are
    not are exactly the mixed-type defect a reader needs to see."""
    earliest: str | None
    latest: str | None
    values_with_time_component: int
    values_without_time_component: int
    values_with_nonzero_seconds: int
    values_stating_utc_offset: int

    @property
    def is_date_granular(self) -> bool:
        """Return whether no parsed value pins an instant finer than a calendar day.

        A column where every time component is `00:00` is date-granular whatever its
        formatting suggests -- and a column whose times are all present but whose seconds
        are always zero is minute-granular, not exact. Both distinctions bound what LAW-TIME
        can conclude, so both are measured rather than assumed from the format string.
        """
        return self.parsed_count > 0 and self.values_with_time_component == 0


class ColumnProfile(BaseModel):
    """Everything measured about one column."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    position: int
    row_count: int
    blank_count: int
    inferred_type: InferredType
    type_counts: tuple[tuple[str, int], ...]
    distinct_count: int
    distinct_exact: bool
    distinct_cap: int
    top_values: tuple[tuple[str, int], ...]
    minimum_text: str | None
    maximum_text: str | None
    numeric: NumericSummary | None = None
    temporal: TemporalSummary | None = None

    @property
    def blank_rate(self) -> float:
        """Return the fraction of rows where this column carried no value."""
        if self.row_count == 0:
            return 0.0
        return self.blank_count / self.row_count


class DatasetProfile(BaseModel):
    """Every column's profile, plus the row count they were measured over."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    row_count: int
    columns: tuple[ColumnProfile, ...]

    def column(self, name: str) -> ColumnProfile | None:
        """Return one column's profile by name, or `None` if the column was not profiled."""
        for profile in self.columns:
            if profile.name == name:
                return profile
        return None


class _ColumnAccumulator:
    """Pass-1 state for one column. Bounded memory, exact statistics."""

    __slots__ = (
        "blank_count",
        "distinct_cap",
        "distinct_exact",
        "earliest",
        "latest",
        "maximum",
        "maximum_text",
        "mean",
        "minimum",
        "minimum_text",
        "name",
        "numeric_count",
        "parsed_count",
        "position",
        "row_count",
        "sum_squares",
        "type_counts",
        "type_memo",
        "value_counts",
        "with_offset",
        "with_seconds",
        "with_time",
        "without_time",
    )

    def __init__(self, name: str, position: int, distinct_cap: int) -> None:
        """Start an empty accumulator for one column."""
        self.name = name
        self.position = position
        self.distinct_cap = distinct_cap
        self.row_count = 0
        self.blank_count = 0
        self.type_counts: dict[InferredType, int] = {}
        self.value_counts: dict[str, int] = {}
        # Classification is a pure function of the text, and most columns repeat a small
        # vocabulary across every row. Memoising it inside the distinct-value cap turns
        # nine million classifications into one per distinct value, and the cap already
        # bounds the memory.
        self.type_memo: dict[str, InferredType] = {}
        self.distinct_exact = True
        self.minimum_text: str | None = None
        self.maximum_text: str | None = None
        self.numeric_count = 0
        self.minimum = math.inf
        self.maximum = -math.inf
        self.mean = 0.0
        self.sum_squares = 0.0
        self.parsed_count = 0
        self.earliest: datetime | None = None
        self.latest: datetime | None = None
        self.with_time = 0
        self.without_time = 0
        self.with_seconds = 0
        self.with_offset = 0

    def observe(self, raw: str) -> None:
        """Fold one source value into the accumulator."""
        self.row_count += 1
        text = raw.strip()
        if not text:
            self.blank_count += 1
            return
        kind = self.type_memo.get(text)
        if kind is None:
            kind = classify_value(text)
            if len(self.type_memo) < self.distinct_cap:
                self.type_memo[text] = kind
        self.type_counts[kind] = self.type_counts.get(kind, 0) + 1
        if len(self.value_counts) < self.distinct_cap or text in self.value_counts:
            self.value_counts[text] = self.value_counts.get(text, 0) + 1
        else:
            self.distinct_exact = False
        if self.minimum_text is None or text < self.minimum_text:
            self.minimum_text = text
        if self.maximum_text is None or text > self.maximum_text:
            self.maximum_text = text
        if kind in (InferredType.INTEGER, InferredType.DECIMAL, InferredType.BOOLEAN):
            self._observe_number(text)
        elif kind in (InferredType.DATE, InferredType.DATETIME):
            self._observe_instant(text)

    def _observe_number(self, text: str) -> None:
        """Fold a numeric value into the exact range and the Welford accumulators."""
        try:
            value = float(text)
        except ValueError:
            return
        if not math.isfinite(value):
            return
        self.numeric_count += 1
        self.minimum = min(self.minimum, value)
        self.maximum = max(self.maximum, value)
        delta = value - self.mean
        self.mean += delta / self.numeric_count
        self.sum_squares += delta * (value - self.mean)

    def _observe_instant(self, text: str) -> None:
        """Fold a date-like value into the temporal counters."""
        for pattern, has_time in _DATETIME_FORMATS:
            try:
                moment = datetime.strptime(text, pattern)  # noqa: DTZ007 -- profiling only
            except ValueError:
                continue
            self.parsed_count += 1
            if moment.tzinfo is not None:
                self.with_offset += 1
            # Compared on one scale. A column mixing offset-aware and naive values would
            # otherwise raise, and the range is a REPORTED figure, never a value the engine
            # uses -- values are parsed for use from the mapping's declared source_format.
            comparable = moment.astimezone(UTC).replace(tzinfo=None) if moment.tzinfo else moment
            if self.earliest is None or comparable < self.earliest:
                self.earliest = comparable
            if self.latest is None or comparable > self.latest:
                self.latest = comparable
            if has_time and (moment.hour or moment.minute or moment.second):
                self.with_time += 1
            else:
                self.without_time += 1
            if moment.second:
                self.with_seconds += 1
            return

    @property
    def inferred_type(self) -> InferredType:
        """Return the join of every type observed in this column."""
        joined = InferredType.EMPTY
        for kind in self.type_counts:
            joined = _join(joined, kind)
        return joined

    def numeric_bounds(self) -> tuple[float, float] | None:
        """Return the exact numeric range, when the column had numeric values."""
        if self.numeric_count == 0 or not math.isfinite(self.minimum):
            return None
        return (self.minimum, self.maximum)


class _Histogram:
    """Pass-2 fixed-width bins over a range pass 1 already measured exactly."""

    __slots__ = ("bins", "counts", "high", "low", "total", "width")

    def __init__(self, low: float, high: float, bins: int) -> None:
        """Bin the closed interval `[low, high]` into `bins` equal parts."""
        self.low = low
        self.high = high
        self.bins = bins
        self.width = (high - low) / bins if high > low else 0.0
        self.counts = [0] * bins
        self.total = 0

    def observe(self, value: float) -> None:
        """Place one value in its bin."""
        if self.width == 0.0:
            index = 0
        else:
            index = int((value - self.low) / self.width)
            index = min(max(index, 0), self.bins - 1)
        self.counts[index] += 1
        self.total += 1

    def quantile(self, fraction: float) -> float:
        """Return the value at `fraction` of the distribution, at bin resolution.

        Bin resolution is stated rather than hidden: with the default bin count a quantile
        is accurate to one part in 1024 of the column's range, and it is identical on every
        platform and every rerun, which a sampled quantile would not be.
        """
        if self.total == 0:
            return self.low
        if self.width == 0.0:
            return self.low
        target = fraction * self.total
        seen = 0
        for index, count in enumerate(self.counts):
            seen += count
            if seen >= target:
                return self.low + (index + 0.5) * self.width
        return self.high


class Profiler:
    """Accumulate a two-pass profile over a stream of column/value pairs.

    Usage is deliberately explicit about which pass is running: `observe_first(row)` for
    every row, then `begin_second_pass()`, then `observe_second(row)` for every row again,
    then `result()`. Calling `result()` without the second pass yields a profile with no
    quantiles rather than invented ones.
    """

    def __init__(
        self,
        columns: Sequence[str],
        *,
        distinct_cap: int = DEFAULT_DISTINCT_CAP,
        histogram_bins: int = DEFAULT_HISTOGRAM_BINS,
        top_value_count: int = DEFAULT_TOP_VALUE_COUNT,
    ) -> None:
        """Prepare an accumulator per column, in header sequence."""
        self._columns = tuple(columns)
        self._histogram_bins = histogram_bins
        self._top_value_count = top_value_count
        self._accumulators = {
            name: _ColumnAccumulator(name, position, distinct_cap)
            for position, name in enumerate(self._columns)
        }
        self._histograms: dict[str, _Histogram] = {}
        self._row_count = 0
        self._second_pass_started = False

    @property
    def row_count(self) -> int:
        """Return the number of rows folded in during the first pass."""
        return self._row_count

    def observe_first(self, fields: Iterable[tuple[str, str]]) -> None:
        """Fold one row into pass 1."""
        self._row_count += 1
        for name, value in fields:
            accumulator = self._accumulators.get(name)
            if accumulator is not None:
                accumulator.observe(value)

    def begin_second_pass(self) -> None:
        """Build a histogram for every column pass 1 found a numeric range for."""
        self._second_pass_started = True
        for name, accumulator in self._accumulators.items():
            bounds = accumulator.numeric_bounds()
            if bounds is not None:
                self._histograms[name] = _Histogram(bounds[0], bounds[1], self._histogram_bins)

    def observe_second(self, fields: Iterable[tuple[str, str]]) -> None:
        """Fold one row into pass 2."""
        for name, value in fields:
            histogram = self._histograms.get(name)
            if histogram is None:
                continue
            text = value.strip()
            if not text:
                continue
            try:
                number = float(text)
            except ValueError:
                continue
            if math.isfinite(number):
                histogram.observe(number)

    def _numeric_summary(self, accumulator: _ColumnAccumulator) -> NumericSummary | None:
        """Assemble one column's numeric summary from both passes."""
        bounds = accumulator.numeric_bounds()
        if bounds is None:
            return None
        histogram = self._histograms.get(accumulator.name)
        variance = (
            accumulator.sum_squares / (accumulator.numeric_count - 1)
            if accumulator.numeric_count > 1
            else 0.0
        )
        if histogram is None:
            p01 = p25 = p50 = p75 = p99 = bounds[0]
            outliers_low = outliers_high = 0
            fence_low, fence_high = bounds
            bins = 0
        else:
            p01 = histogram.quantile(0.01)
            p25 = histogram.quantile(0.25)
            p50 = histogram.quantile(0.50)
            p75 = histogram.quantile(0.75)
            p99 = histogram.quantile(0.99)
            spread = p75 - p25
            fence_low = p25 - IQR_FENCE_MULTIPLIER * spread
            fence_high = p75 + IQR_FENCE_MULTIPLIER * spread
            outliers_low, outliers_high = self._count_outliers(histogram, fence_low, fence_high)
            bins = histogram.bins
        return NumericSummary(
            count=accumulator.numeric_count,
            minimum=bounds[0],
            maximum=bounds[1],
            mean=accumulator.mean,
            standard_deviation=math.sqrt(variance),
            p01=p01,
            p25=p25,
            p50=p50,
            p75=p75,
            p99=p99,
            fence_rule=f"tukey_iqr_{IQR_FENCE_MULTIPLIER}",
            fence_low=fence_low,
            fence_high=fence_high,
            outliers_low=outliers_low,
            outliers_high=outliers_high,
            histogram_bins=bins,
        )

    @staticmethod
    def _count_outliers(histogram: _Histogram, low: float, high: float) -> tuple[int, int]:
        """Count values outside the fence, at bin resolution."""
        below = 0
        above = 0
        for index, count in enumerate(histogram.counts):
            centre = histogram.low + (index + 0.5) * histogram.width
            if centre < low:
                below += count
            elif centre > high:
                above += count
        return below, above

    @staticmethod
    def _temporal_summary(accumulator: _ColumnAccumulator) -> TemporalSummary | None:
        """Assemble one column's temporal summary, when it held date-like values."""
        if accumulator.parsed_count == 0:
            return None
        return TemporalSummary(
            parsed_count=accumulator.parsed_count,
            unparsed_count=(
                accumulator.row_count - accumulator.blank_count - accumulator.parsed_count
            ),
            earliest=accumulator.earliest.isoformat() if accumulator.earliest else None,
            latest=accumulator.latest.isoformat() if accumulator.latest else None,
            values_with_time_component=accumulator.with_time,
            values_without_time_component=accumulator.without_time,
            values_with_nonzero_seconds=accumulator.with_seconds,
            values_stating_utc_offset=accumulator.with_offset,
        )

    def result(self) -> DatasetProfile:
        """Return the finished profile, with every collection canonically sequenced."""
        profiles = []
        for name in self._columns:
            accumulator = self._accumulators[name]
            top = sorted(accumulator.value_counts.items(), key=lambda item: (-item[1], item[0]))
            profiles.append(
                ColumnProfile(
                    name=name,
                    position=accumulator.position,
                    row_count=accumulator.row_count,
                    blank_count=accumulator.blank_count,
                    inferred_type=accumulator.inferred_type,
                    type_counts=tuple(
                        (kind.value, count)
                        for kind, count in sorted(
                            accumulator.type_counts.items(), key=lambda item: item[0].value
                        )
                    ),
                    distinct_count=len(accumulator.value_counts),
                    distinct_exact=accumulator.distinct_exact,
                    distinct_cap=accumulator.distinct_cap,
                    top_values=tuple(top[: self._top_value_count]),
                    minimum_text=accumulator.minimum_text,
                    maximum_text=accumulator.maximum_text,
                    numeric=self._numeric_summary(accumulator),
                    temporal=self._temporal_summary(accumulator),
                )
            )
        return DatasetProfile(row_count=self._row_count, columns=tuple(profiles))
