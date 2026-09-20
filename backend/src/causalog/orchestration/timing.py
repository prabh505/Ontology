"""prd.md §55's budgets, as data, plus the measurement and the slow-query log.

The budgets were quoted in three places before this module -- `make bench`'s echo line,
three integration tests, and the PRD -- and quoted numbers drift. They are declared once
here and read from here, so a budget change is a one-line diff rather than a hunt.

**Two of the five budgets are deliberately NOT enforceable, and that is recorded rather
than smoothed over.** `DATASET_LOADING` and `GRAPH_GENERATION` carry `enforced=False`
because nobody has ruled what they count: prd.md §55 says "dataset loading < 30 seconds"
over a source of 180,519 rows that materializes roughly 3.8 million events, a factor of
twenty-one, and the measured import is about 105 s. That ambiguity is OQ-018 and OQ-019 and
it is a product owner's to resolve. Asserting a budget whose definition is an open question
would be picking the reading that passes, which is the "assertion not specification" error
this repository names in OQ-009. They are measured and reported; they are not gates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Final

from pydantic import BaseModel, ConfigDict

__all__ = [
    "BUDGETS",
    "Budget",
    "BudgetName",
    "SlowOperation",
    "TimingMeta",
    "budget_for",
    "log_slow_operation",
]

_LOGGER: Final[logging.Logger] = logging.getLogger("causalog.orchestration.timing")


class BudgetName(Enum):
    """The five prd.md §55 operations, as a closed vocabulary."""

    DATASET_LOADING = "DATASET_LOADING"
    GRAPH_GENERATION = "GRAPH_GENERATION"
    ROOT_CAUSE_QUERY = "ROOT_CAUSE_QUERY"
    COUNTERFACTUAL_QUERY = "COUNTERFACTUAL_QUERY"
    RECOMMENDATION_GENERATION = "RECOMMENDATION_GENERATION"


@dataclass(frozen=True)
class Budget:
    """One prd.md §55 target and whether it is a gate today.

    `enforced` is the honest field. A budget with `enforced=False` is measured, reported
    and compared -- it is simply not allowed to fail a build, because the number it would
    be compared against has not been agreed. The reason travels with it so a reader never
    has to go looking for why a budget is advisory.
    """

    name: BudgetName
    seconds: float
    enforced: bool
    reason_if_unenforced: str | None = None


BUDGETS: Final[dict[BudgetName, Budget]] = {
    BudgetName.DATASET_LOADING: Budget(
        name=BudgetName.DATASET_LOADING,
        seconds=30.0,
        enforced=False,
        reason_if_unenforced=(
            "OQ-018/OQ-019: prd.md §55 does not say whether 'dataset loading' counts the "
            "180,519 source rows or the ~3.8M events they materialize, a factor of 21. "
            "The measured import is ~105 s. Picking the reading that passes would be a "
            "ruling disguised as a measurement."
        ),
    ),
    BudgetName.GRAPH_GENERATION: Budget(
        name=BudgetName.GRAPH_GENERATION,
        seconds=60.0,
        enforced=False,
        reason_if_unenforced=(
            "Modules 7 and 8 are not built, so no full temporal property graph is "
            "generated and there is nothing whose duration this would bound. "
            "docs/architecture.md §7 risk 1 additionally puts the Neo4j rebuild on this "
            "budget's critical path, unmeasured."
        ),
    ),
    BudgetName.ROOT_CAUSE_QUERY: Budget(
        name=BudgetName.ROOT_CAUSE_QUERY, seconds=3.0, enforced=True
    ),
    BudgetName.COUNTERFACTUAL_QUERY: Budget(
        name=BudgetName.COUNTERFACTUAL_QUERY, seconds=5.0, enforced=True
    ),
    BudgetName.RECOMMENDATION_GENERATION: Budget(
        name=BudgetName.RECOMMENDATION_GENERATION, seconds=5.0, enforced=True
    ),
}


def budget_for(name: BudgetName) -> Budget:
    """Return one declared budget. Every member of the enum has one."""
    return BUDGETS[name]


class TimingMeta(BaseModel):
    """What one operation cost, and what it was allowed to cost.

    Carried on every API response. `CONVENTIONS.md` §11 excludes performance measurements
    from determinism comparisons, so this whole model is excluded -- which is why the
    budget and its name travel WITH the measurement rather than being looked up by a
    reader: a number the determinism diff ignores must still be interpretable on its own.

    `within_budget` is None when the operation has no declared budget. That is a third
    state and not a quiet `True`: "this was fast enough" and "nobody said how fast this
    should be" are different claims, and collapsing them would let an unbudgeted endpoint
    report compliance it was never measured for.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: str
    elapsed_seconds: float
    budget_name: BudgetName | None = None
    budget_seconds: float | None = None
    budget_enforced: bool | None = None
    within_budget: bool | None = None

    @classmethod
    def measured(
        cls, *, operation: str, elapsed_seconds: float, budget: Budget | None
    ) -> TimingMeta:
        """Build timing metadata, attaching a budget when the operation has one."""
        if budget is None:
            return cls(operation=operation, elapsed_seconds=elapsed_seconds)
        return cls(
            operation=operation,
            elapsed_seconds=elapsed_seconds,
            budget_name=budget.name,
            budget_seconds=budget.seconds,
            budget_enforced=budget.enforced,
            within_budget=elapsed_seconds <= budget.seconds,
        )


class SlowOperation(BaseModel):
    """One operation that exceeded its budget, as the slow-query log records it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: str
    elapsed_seconds: float
    budget_seconds: float
    overrun_seconds: float
    run_id: str | None
    correlation_id: str | None


def log_slow_operation(
    timing: TimingMeta, *, run_id: str | None, correlation_id: str | None
) -> SlowOperation | None:
    """Log and return a `SlowOperation` when `timing` breached its budget, else None.

    Logged at `WARNING` with a count-bearing structure, per `CONVENTIONS.md` §8: a
    tolerated degradation is always logged with its reason, never swallowed. An overrun is
    exactly that -- the answer is correct and arrived late -- so it is a warning and never
    an error, and it never changes a response body.
    """
    if timing.budget_seconds is None or timing.within_budget is not False:
        return None
    slow = SlowOperation(
        operation=timing.operation,
        elapsed_seconds=timing.elapsed_seconds,
        budget_seconds=timing.budget_seconds,
        overrun_seconds=timing.elapsed_seconds - timing.budget_seconds,
        run_id=run_id,
        correlation_id=correlation_id,
    )
    _LOGGER.warning("slow_operation", extra={"slow_operation": slow.model_dump(mode="json")})
    return slow
