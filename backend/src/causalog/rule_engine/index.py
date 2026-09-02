"""The indexes that make evaluation linear in inputs plus output, not quadratic in events.

The naive evaluator compares every event against every other event for every rule: `O(n^2)`
per rule, which on the DataCo expansion is upward of ten billion comparisons per rule and is
not a slow implementation but a different program -- one nobody can run.

What this module builds, once per evaluation:

  `by_type`         event type -> the events of that type, already in canonical sequence
  `by_participant`  entity id  -> the events that entity participates in
  `related`         (entity id, relationship type, direction) -> the entities across it
  `states_of`       entity id  -> that entity's states, in canonical sequence

Complexity, stated so a reader can check it against the code
------------------------------------------------------------
Construction is `O(E * p + S + R)` for `E` events with at most `p` participants each, `S`
states and `R` relationships -- one pass, each item appended to a constant number of buckets.

Evaluation of one two-event rule `r` is then

    O( |C_r| * (log |F_r| + k_r) )

where `C_r` is the antecedent bucket, `F_r` the consequent bucket, and `k_r` the number of
consequent events actually reachable from one antecedent through the rule's declared
linkage. The `log |F_r|` is a bisection into the consequent bucket by the window's lower
bound; `k_r` is bounded by the linkage, not by `|F_r|`. Summed over rules the whole
evaluation is

    O( E*p + S + R + SUM_r ( |C_r| * log|F_r| + m_r ) )

with `m_r` the pairs actually examined -- linear in the inputs plus the output, and never
`|E|^2`. `tests/unit/rule_engine/test_complexity_bound.py` asserts this against a counter
this module's consumer increments, rather than trusting the paragraph.

**The bound is a bound on comparisons, not a promise about output size.** A pack whose
linkage is `SHARED_PARTICIPANT` on an entity participating in every event has `k_r` equal to
`|F_r|`, and the evaluation is quadratic because the RULE is quadratic. That is a property
of the pack, is reported in the statistics as a large pair count, and is not something an
index can fix.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from causalog.core.types import Event, State
from causalog.rule_engine.dsl import RelationDirection
from causalog.rule_engine.facts import GraphFacts

__all__ = ["FactIndex", "build_index"]


@dataclass(frozen=True)
class FactIndex:
    """Precomputed lookups over one fact set. Built once, read many times.

    Every bucket is a tuple in canonical sequence, so two evaluations over the same facts
    walk them identically and the output is byte-identical (`CONVENTIONS.md` §11).
    """

    by_type: dict[str, tuple[Event, ...]]
    by_participant: dict[str, tuple[str, ...]]
    events_by_id: dict[str, Event]
    related: dict[tuple[str, str, RelationDirection], tuple[str, ...]]
    states_of: dict[str, tuple[State, ...]]
    #: Per event-type bucket, the `t_earliest` of each member in the bucket's own sequence.
    #: Held separately so `admissible_slice` bisects a plain list of instants rather than
    #: rebuilding a key list on every probe.
    earliest_of: dict[str, tuple[datetime, ...]] = field(default_factory=dict)
    #: Per event-type bucket, the widest interval it holds. This is what lets a cut on
    #: `t_earliest` reason soundly about `t_latest` -- see `admissible_slice`.
    max_span_of: dict[str, timedelta] = field(default_factory=dict)

    def of_type(self, event_type: str) -> tuple[Event, ...]:
        """Return the events of one type, in canonical sequence. Empty if none."""
        return self.by_type.get(event_type, ())

    def participants_of(self, event: Event) -> tuple[str, ...]:
        """Return every entity identifier the event names, sorted, without repeats."""
        return tuple(sorted(set(event.source_entity_ids) | set(event.target_entity_ids)))

    def admissible_slice(
        self,
        event_type: str,
        cause_earliest: datetime,
        cause_latest: datetime,
        window_maximum_seconds: int,
    ) -> tuple[tuple[Event, ...], int]:
        """Return the consequent candidates worth examining, and how many were violations.

        Returns `(candidates, refused)`. This is the bisection the complexity bound depends
        on, and it cuts BOTH ends of the bucket, which is what makes the cost a function of
        the rule's window rather than of the dataset's size.

        **The upper cut is the window.** `_within` admits a pair only if the minimum
        possible separation is inside `window_maximum_seconds`, and that minimum is
        `effect.t_earliest - cause.t_latest`. So every event with

            effect.t_earliest > cause.t_latest + window_maximum_seconds

        is outside the window, and the bucket is sequenced by `t_earliest`, so they are a
        contiguous suffix. Cutting them is exact.

        **The lower cut is LAW-TIME.** `docs/contracts.md` §3: the pair is a `VIOLATION` iff
        `cause.t_earliest >= effect.t_latest`. Every event in the bucket satisfies
        `t_latest <= t_earliest + max_span`, where `max_span` is the widest interval the
        bucket holds, so every event with

            effect.t_earliest < cause.t_earliest - max_span

        has `t_latest < cause.t_earliest` and is therefore a violation -- all of them, and
        nothing else. `refused` is that count: **exact, and obtained without examining a
        single one of them.**

        **What this deliberately does not do.** It never cuts on the window's *minimum*
        separation, though it could. Doing so would make `refused` an over-count -- some
        events below that line are outside the window rather than violations -- and a
        statistic that conflates "the rule did not want it" with "the law forbade it" is
        worse than a slightly wider slice. The window's lower bound is applied per pair.

        **An earlier version cut on `t_latest` alone and was quadratic in the event count**;
        the one before that cut on `t_earliest` alone and silently dropped admissible
        overlapping pairs. Both are pinned by tests in `tests/unit/rule_engine/`.

        A bucket holding an event with `UNKNOWN` precision has an unbounded `max_span`, so
        the lower cut degenerates to zero and that bucket is scanned from its start. That is
        correct and is the honest cost of an unplaced event: nothing can be excluded on the
        strength of bounds the source never recorded.
        """
        bucket = self.by_type.get(event_type, ())
        if not bucket:
            return (), 0
        keys = self.earliest_of[event_type]
        span = self.max_span_of[event_type]
        low = bisect_left(keys, cause_earliest - span)
        high = bisect_right(keys, cause_latest + timedelta(seconds=window_maximum_seconds))
        return bucket[low:high], low

    def neighbours(
        self, entity_id: str, relationship_type: str, direction: RelationDirection
    ) -> tuple[str, ...]:
        """Return the entities reachable from `entity_id` across one relationship type."""
        return self.related.get((entity_id, relationship_type, direction), ())

    def events_for_entity(self, entity_id: str) -> tuple[str, ...]:
        """Return every event identifier this entity participates in, sorted."""
        return self.by_participant.get(entity_id, ())


def build_index(facts: GraphFacts) -> FactIndex:
    """Return the indexes for one fact set. One pass over each collection.

    Every bucket is sorted at the end rather than kept sorted during insertion: the events
    already arrive canonically sequenced from `GraphFacts.events()`, so the sort is a
    verification of that contract at negligible cost, and it means an implementation of the
    protocol that violated the contract produces a correct result here instead of a subtly
    wrong one.
    """
    by_type: dict[str, list[Event]] = defaultdict(list)
    by_participant: dict[str, list[str]] = defaultdict(list)
    events_by_id: dict[str, Event] = {}
    related: dict[tuple[str, str, RelationDirection], list[str]] = defaultdict(list)
    states_of: dict[str, list[State]] = defaultdict(list)

    for event in facts.events():
        by_type[event.event_type].append(event)
        events_by_id[event.event_id] = event
        for entity_id in set(event.source_entity_ids) | set(event.target_entity_ids):
            by_participant[entity_id].append(event.event_id)

    for relationship in facts.relationships():
        source = relationship.source_entity_id
        target = relationship.target_entity_id
        kind = relationship.relationship_type
        related[(source, kind, RelationDirection.FROM_TO)].append(target)
        related[(target, kind, RelationDirection.TO_FROM)].append(source)

    for state in facts.states():
        states_of[state.entity_id].append(state)

    sequenced_by_type = {
        event_type: tuple(
            sorted(
                bucket,
                key=lambda item: (
                    item.occurred_at.t_earliest,
                    item.occurred_at.t_latest,
                    item.event_id,
                ),
            )
        )
        for event_type, bucket in sorted(by_type.items())
    }
    return FactIndex(
        by_type=sequenced_by_type,
        by_participant={
            entity_id: tuple(sorted(set(bucket)))
            for entity_id, bucket in sorted(by_participant.items())
        },
        events_by_id=events_by_id,
        related={key: tuple(sorted(set(bucket))) for key, bucket in sorted(related.items())},
        states_of={
            entity_id: tuple(sorted(bucket, key=lambda item: item.state_id))
            for entity_id, bucket in sorted(states_of.items())
        },
        earliest_of={
            event_type: tuple(item.occurred_at.t_earliest for item in bucket)
            for event_type, bucket in sequenced_by_type.items()
        },
        max_span_of={
            event_type: max(
                (item.occurred_at.t_latest - item.occurred_at.t_earliest for item in bucket),
                default=timedelta(0),
            )
            for event_type, bucket in sequenced_by_type.items()
        },
    )
