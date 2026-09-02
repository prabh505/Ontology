"""Evaluate an emission condition tree against one mapped record.

The tree is data (`schema_mapper.dsl.ConditionExpression`); this walks it. Nothing here is
compiled, `eval`'d, or cached as code -- a data file that becomes executable is the thing
ADR-0026 refused for measurements and ADR-0039 refuses again for emissions.

Absence is FALSE, and it is counted
-----------------------------------
A comparison whose operand the record does not supply is false. It is not an error: an
optional attribute is legitimately absent, and raising would make every optional column a
pipeline stop. But it is also not nothing -- a rule that never fires because the attribute
it reads is always missing looks exactly like a rule whose condition is never met, and only
one of those is a finding about the dataset. So every unevaluable comparison is COUNTED, per
rule, and the count reaches the event quality report.

An author who means "absent" writes `IS_ABSENT`, which is true for an absent value and is
not counted as unevaluable. That is the whole difference between asking a question the data
cannot answer and asking whether the data answered.

Numeric comparison is arithmetic, never lexicographic
-----------------------------------------------------
`GREATER_THAN` and `LESS_THAN` parse both operands as numbers and fail loudly on a present
operand that is not one. `'9' > '10'` is true as text and false as arithmetic, and a
delay comparison that silently used the first would be wrong on exactly the rows that
matter.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from causalog.core.errors import DataQualityError
from causalog.ingestion.schema_mapper.apply import RecordView
from causalog.ingestion.schema_mapper.dsl import ConditionExpression, ConditionOperator

__all__ = ["ConditionCounters", "evaluate"]


@dataclass
class ConditionCounters:
    """Per-rule counts of comparisons the record could not answer.

    Keyed by `(event_type, address)` so a report can say WHICH attribute was missing, not
    merely that something was. A rule that fired zero times with a large count here is a
    coverage problem; a rule that fired zero times with a zero count here is a condition
    the dataset genuinely never met, and the two want different responses.
    """

    unevaluable: dict[tuple[str, str], int] = field(default_factory=dict)

    def missed(self, event_type: str, address: str) -> None:
        """Count one comparison that read an absent value."""
        key = (event_type, address)
        self.unevaluable[key] = self.unevaluable.get(key, 0) + 1

    def sequenced(self) -> tuple[tuple[str, str, int], ...]:
        """Return `(event_type, address, count)` triples, canonically sequenced."""
        return tuple(
            (event_type, address, count)
            for (event_type, address), count in sorted(self.unevaluable.items())
        )


def evaluate(
    condition: ConditionExpression,
    record: RecordView,
    *,
    event_type: str,
    counters: ConditionCounters | None = None,
) -> bool:
    """Return whether one record witnesses the occurrence this condition describes.

    Args:
        condition: the tree, already validated by the DSL.
        record: the mapped record to read.
        event_type: the rule's event type, used only to label counts.
        counters: where unevaluable comparisons are counted. Optional so a unit test can
            evaluate a tree without assembling a report.

    Raises:
        DataQualityError: if a numeric comparison reads a present value that is not a
            number. That is a mapping defect -- a column declared as a quantity carrying
            something else -- and it is loud rather than silently false.
    """
    operator = condition.op
    if operator is ConditionOperator.ALWAYS:
        return True
    if operator is ConditionOperator.AND:
        return all(
            evaluate(operand, record, event_type=event_type, counters=counters)
            for operand in condition.operands
        )
    if operator is ConditionOperator.OR:
        # Not short-circuiting through `any`, deliberately: an OR whose first branch is
        # true would leave the later branches' unevaluable comparisons uncounted, and the
        # count would then depend on the sequence the author wrote the branches in.
        outcomes = [
            evaluate(operand, record, event_type=event_type, counters=counters)
            for operand in condition.operands
        ]
        return any(outcomes)
    if operator is ConditionOperator.NOT:
        return not evaluate(condition.operands[0], record, event_type=event_type, counters=counters)
    if operator is ConditionOperator.IS_PRESENT:
        return _read(condition.operands[0], record) is not None
    if operator is ConditionOperator.IS_ABSENT:
        return _read(condition.operands[0], record) is None
    if operator is ConditionOperator.IN:
        address = condition.operands[0].address
        value = _read(condition.operands[0], record)
        if value is None:
            _count(counters, event_type, address)
            return False
        return value in condition.values
    left, right = condition.operands
    left_value = _read(left, record)
    right_value = _read(right, record)
    if left_value is None or right_value is None:
        _count(counters, event_type, _absent_address(left, right, left_value, right_value))
        return False
    if operator is ConditionOperator.EQUALS:
        return left_value == right_value
    if operator is ConditionOperator.NOT_EQUALS:
        return left_value != right_value
    left_number = _as_number(left, left_value, event_type)
    right_number = _as_number(right, right_value, event_type)
    if operator is ConditionOperator.GREATER_THAN:
        return left_number > right_number
    return left_number < right_number


def _read(leaf: ConditionExpression, record: RecordView) -> str | None:
    """Return a leaf's value: the record's value for an ATTRIBUTE, the literal otherwise."""
    if leaf.op is ConditionOperator.CONSTANT:
        return leaf.value
    return record.value(leaf.address)


def _absent_address(
    left: ConditionExpression,
    right: ConditionExpression,
    left_value: str | None,
    right_value: str | None,
) -> str:
    """Return the address of the operand that was missing, for the count."""
    if left_value is None and left.op is ConditionOperator.ATTRIBUTE:
        return left.address
    if right_value is None and right.op is ConditionOperator.ATTRIBUTE:
        return right.address
    return "<constant>"


def _count(counters: ConditionCounters | None, event_type: str, address: str) -> None:
    """Count one unevaluable comparison, when a counter is collecting them."""
    if counters is not None:
        counters.missed(event_type, address)


def _as_number(leaf: ConditionExpression, value: str, event_type: str) -> float:
    """Parse one operand of a numeric comparison, or refuse it.

    Raises:
        DataQualityError: naming the rule, the operand, and the value.
    """
    try:
        return float(value)
    except ValueError as failure:
        where = leaf.address if leaf.op is ConditionOperator.ATTRIBUTE else "a literal"
        raise DataQualityError(
            f"emission rule for {event_type!r} compares {where} numerically and read "
            f"{value!r}, which is not a number. A numeric comparison is arithmetic, never "
            "lexicographic; falling back to text here would make the rule quietly wrong on "
            "exactly the values that differ in width."
        ) from failure
