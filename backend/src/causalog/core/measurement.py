"""The one walk of a declared measurement tree in this repository (ADR-0056).

The ontology's `MeasurementExpression` is deliberately inert -- "nothing here is evaluated
by this module" (ADR-0026) -- so a consumer has to walk it. Before this module there was one
such walk, in `graph_engine/state_engine/measurement.py`, scoped to `DURATION`/`DELAY`; its
own docstring said that a future module needing more operators "extends this evaluator
rather than duplicating it". This is that extension, lifted to `L0` so that the two
consumers share one implementation instead of drifting apart.

**Why `core/` and not `causal_engine/`.** `scripts/check_metrics_are_declared.py` refuses
inline arithmetic bound to a metric name inside the reasoning packages, and it is right to:
a formula written there does not move when the domain is swapped, which is LAW-DOMAIN
defeated by a value rather than by a word. A tree-walking interpreter that never mentions a
metric is the sanctioned alternative that lint exists to push code toward, and `core/` is
where it belongs -- the same exemption `core/aggregation.py` already holds, and for the same
reason.

**Generic by structural protocol, not by concrete type.** `DurationExpressionView` and
`MeasurementExpressionView` are field-identical apart from their operator enum. Typing this
walk against a protocol lets it evaluate either without a conversion step and without either
view learning about the other. The cost, stated rather than discovered: nothing here can
check at type level that the two enums stay in step. That is checked by a test
(`tests/unit/core/test_measurement.py`), as ADR-0056 records.

**No domain vocabulary appears below.** Every event type and attribute name arrives as a
string from the tree; nothing here branches on the value of one.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from causalog.core.errors import OntologyMappingError
from causalog.core.types.event import Event

__all__ = ["MeasurementNode", "evaluate_measurement"]


@runtime_checkable
class MeasurementNode(Protocol):
    """One node of a declared operator tree, in whichever view mirrors it.

    `op` is any object with a `.value` string -- both mirrors use a `str` enum, and reading
    `.value` rather than comparing enum members is what lets one walk serve both.
    """

    @property
    def op(self) -> object:  # pragma: no cover -- protocol declaration
        """The operator, as any object carrying a `.value` string."""
        ...

    @property
    def event_type(self) -> str | None:  # pragma: no cover -- protocol declaration
        """The event type an `ATTRIBUTE` leaf names, or None."""
        ...

    @property
    def attribute(self) -> str | None:  # pragma: no cover -- protocol declaration
        """The attribute an `ATTRIBUTE` leaf names, or None."""
        ...

    @property
    def value(self) -> float | None:  # pragma: no cover -- protocol declaration
        """The number a `CONSTANT` leaf carries, or None."""
        ...

    @property
    def operands(self) -> tuple[MeasurementNode, ...]:  # pragma: no cover -- protocol
        """This node's children; empty for a leaf."""
        ...


#: Every operator the closed set declares. A `supported` argument narrower than this is how
#: a caller states which subset IT can evaluate; the walk itself handles all nine.
ALL_OPERATORS = frozenset(
    {
        "CONSTANT",
        "ATTRIBUTE",
        "SUM",
        "DIFFERENCE",
        "PRODUCT",
        "RATIO",
        "DURATION_BETWEEN",
        "MINIMUM",
        "MAXIMUM",
    }
)


def _attribute_text(event: Event, attribute: str) -> str | None:
    """Return one changed attribute's raw text, or None if the event does not carry it."""
    for name, text in event.changed_attributes:
        if name == attribute:
            return text
    return None


def _instant(event: Event, attribute: str) -> datetime | None:
    """Parse an `ATTRIBUTE` leaf as an ISO-8601 instant, per `DURATION_BETWEEN`'s contract."""
    raw = _attribute_text(event, attribute)
    if raw is None:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _leaf(node: MeasurementNode, events_by_type: dict[str, Event]) -> float | None:
    """Evaluate an `ATTRIBUTE` leaf to a number, or None if anything it names is absent."""
    if node.event_type is None or node.attribute is None:
        return None
    event = events_by_type.get(node.event_type)
    if event is None:
        return None
    raw = _attribute_text(event, node.attribute)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _between(node: MeasurementNode, events_by_type: dict[str, Event]) -> float | None:
    """Evaluate `DURATION_BETWEEN` over two instant-valued leaves, in seconds."""
    start_leaf, end_leaf = node.operands
    if start_leaf.event_type is None or start_leaf.attribute is None:
        return None
    if end_leaf.event_type is None or end_leaf.attribute is None:
        return None
    start_event = events_by_type.get(start_leaf.event_type)
    end_event = events_by_type.get(end_leaf.event_type)
    if start_event is None or end_event is None:
        return None
    start = _instant(start_event, start_leaf.attribute)
    end = _instant(end_event, end_leaf.attribute)
    if start is None or end is None:
        return None
    return (end - start).total_seconds()


def evaluate_measurement(
    expression: MeasurementNode,
    events_by_type: dict[str, Event],
    *,
    supported: frozenset[str] = ALL_OPERATORS,
    caller: str = "core.measurement",
) -> float | None:
    """Evaluate a declared measurement tree over one instance's events.

    `events_by_type` supplies at most one event per type -- one instance of one process,
    which is the unit a measurement is defined over.

    Returns `None` when a referenced event type or attribute is absent for this instance, or
    when a `RATIO` would divide by zero. A missing operand is a legitimate, silent "not
    evaluable here": not every instance witnesses every step, and reporting an absence as a
    zero would put a manufactured number into an attribution.

    `supported` lets a caller declare the subset it can accept, so a narrower consumer keeps
    its own refusal rather than silently gaining operators it has no meaning for. `caller`
    names that consumer in the error message.

    Raises:
        OntologyMappingError: if the tree uses an operator outside `supported`.
    """
    op = str(getattr(expression.op, "value", expression.op))
    if op not in supported:
        raise OntologyMappingError(
            f"{caller} cannot evaluate operator {op!r}; it supports "
            f"{sorted(supported)}. A tree using an operator its consumer has no meaning "
            "for is refused rather than skipped, because a skipped operand would silently "
            "change the value the rest of the tree produces."
        )
    if op == "CONSTANT":
        return expression.value
    if op == "ATTRIBUTE":
        return _leaf(expression, events_by_type)
    if op == "DURATION_BETWEEN":
        return _between(expression, events_by_type)

    evaluated = [
        evaluate_measurement(operand, events_by_type, supported=supported, caller=caller)
        for operand in expression.operands
    ]
    if any(item is None for item in evaluated):
        return None
    operands: list[float] = [item for item in evaluated if item is not None]
    if op == "SUM":
        return float(sum(operands))
    if op == "DIFFERENCE":
        return operands[0] - operands[1]
    if op == "PRODUCT":
        product = 1.0
        for operand in operands:
            product = product * operand
        return product
    if op == "RATIO":
        # None rather than an exception or an infinity. A denominator of zero means this
        # instance cannot express the ratio, which is the same finding as a missing operand
        # and is reported the same way.
        if operands[1] == 0.0:
            return None
        return operands[0] / operands[1]
    if op == "MINIMUM":
        return min(operands)
    return max(operands)
