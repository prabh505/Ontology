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

**The walk itself now lives in `causalog.core.measurement` (ADR-0056)**, because a second
consumer arrived that needs `PRODUCT` and `RATIO` and this module's own docstring said such
a consumer should extend this evaluator rather than duplicate it. What remains here is the
`DURATION`/`DELAY` restriction, unchanged: the same operators are refused and the refusal
says the same thing.
"""

from __future__ import annotations

from causalog.core.measurement import evaluate_measurement
from causalog.core.ontology_view import DurationExpressionOperator, DurationExpressionView
from causalog.core.types import Event

__all__ = ["evaluate_duration_seconds"]

#: Operators this evaluator supports for `DURATION`/`DELAY` measurements. `RATIO`/`PRODUCT`
#: on plain numeric attributes are out of scope here -- they are not a duration and State
#: Engine's report has no use for them.
#:
#: Kept as a restriction rather than dropped when the walk moved to `core.measurement`
#: (ADR-0056). `core` handles all nine operators; this module still refuses the two it has
#: no meaning for, and refuses them with the same message it always did. Widening a
#: consumer's operator set as a side effect of sharing an implementation would be a
#: behaviour change wearing a refactor's clothes.
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

#: The same set as operator NAMES, which is what `core.measurement` matches on.
_SUPPORTED_NAMES = frozenset(operator.value for operator in _SUPPORTED)


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

    A thin restriction of `causalog.core.measurement.evaluate_measurement` since ADR-0056.
    The behaviour is unchanged, including which operators are refused and what the refusal
    says.

    Raises:
        OntologyMappingError: if the tree uses an operator this evaluator does not support.
    """
    return evaluate_measurement(
        expression,
        events_by_type,
        supported=_SUPPORTED_NAMES,
        caller="state_engine.measurement",
    )
