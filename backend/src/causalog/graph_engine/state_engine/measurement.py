"""The first `MeasurementExpression` evaluator (`docs/architecture.md`, `ADR-0026`).

The ontology's `MeasurementExpression` is deliberately inert -- "nothing here is evaluated
by this module" -- so a downstream module has to walk the tree. This is that walk, scoped
to exactly what `StateQualityReport`'s duration statistics need: a `DURATION` or `DELAY`
measurement whose leaves are `ATTRIBUTE` nodes naming an instant-valued attribute on one
event type each. It walks `DurationExpressionView` (`causalog.core.ontology_view`), a plain
mirror of the DSL tree -- this package may never import `ontology_runtime` directly
(LAW-DOMAIN, ADR-0002, forbidden edge F3); `causalog.extraction.ontology_adapters` builds
the mirror.

Generic over the closed operator set -- no metric id and no domain vocabulary appears in
this interpreter's own logic, which is what keeps it out of
`scripts/check_metrics_are_declared.py`'s scope (that lint refuses inline arithmetic bound
to a metric NAME; a tree-walking interpreter that never mentions one is the sanctioned
alternative the lint exists to push code toward).
"""

from __future__ import annotations

from datetime import datetime

from causalog.core.errors import OntologyMappingError
from causalog.core.ontology_view import DurationExpressionOperator, DurationExpressionView
from causalog.core.types import Event

__all__ = ["evaluate_duration_seconds"]

#: Operators this evaluator supports for `DURATION`/`DELAY` measurements. `RATIO`/`PRODUCT`
#: on plain numeric attributes are out of scope here -- they are not a duration and State
#: Engine's report has no use for them; a future module needing them extends this
#: evaluator rather than duplicating it.
_SUPPORTED = frozenset(
    {
        DurationExpressionOperator.CONSTANT,
        DurationExpressionOperator.ATTRIBUTE,
        DurationExpressionOperator.DURATION_BETWEEN,
        DurationExpressionOperator.DIFFERENCE,
        DurationExpressionOperator.SUM,
        DurationExpressionOperator.MINIMUM,
        DurationExpressionOperator.MAXIMUM,
    }
)


def _attribute_value(event: Event, attribute: str) -> str | None:
    for name, value in event.changed_attributes:
        if name == attribute:
            return value
    return None


def _instant(event: Event, attribute: str) -> datetime | None:
    """Parse an `ATTRIBUTE` leaf as an ISO-8601 instant, per `DURATION_BETWEEN`'s contract."""
    raw = _attribute_value(event, attribute)
    if raw is None:
        return None
    return datetime.fromisoformat(raw)


def evaluate_duration_seconds(
    expression: DurationExpressionView, events_by_type: dict[str, Event]
) -> float | None:
    """Evaluate a `DURATION`/`DELAY` measurement's expression tree over one instance's events.

    `events_by_type` supplies at most one event per type for this evaluation -- one instance
    of one process, which is the unit `DISPATCH_LATENCY`-shaped measurements are defined
    over. Returns `None` when a referenced event type or attribute is absent for this
    instance (not every instance witnesses every step; a missing operand is a legitimate,
    silent "not evaluable here", exactly as `DurationExpressionView`'s own `NOT_RUNNABLE`
    coverage status already treats an unevaluable emission rule).

    Raises:
        OntologyMappingError: if the tree uses an operator this evaluator does not support.
    """
    if expression.op not in _SUPPORTED:
        raise OntologyMappingError(
            f"state_engine.measurement cannot evaluate operator {expression.op.value!r}; "
            "this evaluator supports "
            f"{sorted(op.value for op in _SUPPORTED)} for DURATION/DELAY measurements."
        )
    if expression.op is DurationExpressionOperator.CONSTANT:
        return expression.value
    if expression.op is DurationExpressionOperator.ATTRIBUTE:
        if expression.event_type is None or expression.attribute is None:
            return None
        event = events_by_type.get(expression.event_type)
        if event is None:
            return None
        raw = _attribute_value(event, expression.attribute)
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError:
            return None
    if expression.op is DurationExpressionOperator.DURATION_BETWEEN:
        start_leaf, end_leaf = expression.operands
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
    raw_operands = [
        evaluate_duration_seconds(operand, events_by_type) for operand in expression.operands
    ]
    if any(value is None for value in raw_operands):
        return None
    operands: list[float] = [value for value in raw_operands if value is not None]
    if expression.op is DurationExpressionOperator.DIFFERENCE:
        return operands[0] - operands[1]
    if expression.op is DurationExpressionOperator.SUM:
        return sum(operands)
    if expression.op is DurationExpressionOperator.MINIMUM:
        return min(operands)
    return max(operands)
