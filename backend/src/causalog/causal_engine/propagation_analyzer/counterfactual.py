r"""Counterfactual-lite: what the GRAPH says disappears if one node is removed.

**The name says the limit and the limit is real.** This is graph surgery over frozen links,
not a causal effect estimate. No counterfactual was observed, no confounder was adjusted
for, and the answer is a statement about what this graph asserts rather than about what
would have happened. prd.md §33's simulator is module 13's and ships under the same caveat
(OQ-007); what is here is the smaller, purely structural question module 11 needs so as
to rank at all: **of everything downstream, how much of it does the graph still reach once
this node is gone.**

THE METHOD, AND WHY IT IS A RE-REACHABILITY RATHER THAN A SUBTRACTION.

The naive answer -- take the consequences downstream of the candidate and call that its
contribution -- is wrong on any graph with a diamond in it. A consequence downstream of the
candidate may also be downstream of something else that survives the removal, in which case
the graph does not say it disappears. So the set that disappears is computed by **re-running
reachability with the node and every link through it deleted, and diffing**:

    prevented(n) = reachable(seed) \\ reachable(seed, excluding=n)

which is O(V+E) per candidate and is correct on diamonds by construction. A node with
another surviving ancestor stays in the second set and therefore contributes nothing to the
difference, which is what the graph actually claims.

**Joint causes are removed as a group, never individually.** A `CONTRIBUTING` link belongs
to a `JointCauseGroup` that was promoted all-or-nothing, and the Causal Graph Builder's own
note on the type says why this matters here: over one member of a joint group the honest
answer to "what happens if this is removed" is that the effect may still occur, because the
others remain. Removing one member and reporting the effect as prevented would overstate
the candidate by the whole of the group's contribution.

**Nothing here is ever read as zero.** A candidate whose removal prevents nothing measurable
is reported as preventing nothing measurable, with the reason, and never as preventing zero
of something.

**No domain vocabulary appears below.**
"""

from __future__ import annotations

from causalog.causal_engine.propagation_analyzer.attribute import consequence_set, share_for
from causalog.causal_engine.propagation_analyzer.context import PropagationContext
from causalog.causal_engine.propagation_analyzer.graph import ConsequenceSet, MagnitudeShare
from causalog.causal_engine.propagation_analyzer.traverse import reachable_from
from causalog.core.attribution import difference_of

__all__ = ["PreventedConsequence", "prevented_by_removing", "share_of_whole"]


class PreventedConsequence:
    """What removing one node takes with it: the set, the total, and the reason if neither.

    A small immutable holder rather than a model. It is consumed by module 11 and folded
    into `RankedCause`, which is the artifact that leaves; publishing a second model here
    would put one fact into two types that could drift apart.
    """

    __slots__ = (
        "absent_because",
        "prevented_event_ids",
        "prevented_total",
        "removed_event_ids",
        "surviving_event_ids",
        "unit",
        "whole_total",
    )

    def __init__(
        self,
        *,
        removed_event_ids: tuple[str, ...],
        prevented_event_ids: tuple[str, ...],
        surviving_event_ids: tuple[str, ...],
        whole_total: float | None,
        prevented_total: float | None,
        unit: str | None,
        absent_because: str | None,
    ) -> None:
        """Record one counterfactual removal and what the graph says it takes with it."""
        self.removed_event_ids = removed_event_ids
        self.prevented_event_ids = prevented_event_ids
        self.surviving_event_ids = surviving_event_ids
        self.whole_total = whole_total
        self.prevented_total = prevented_total
        self.unit = unit
        self.absent_because = absent_because

    @property
    def prevented_count(self) -> int:
        """Return how many consequences the graph says stop occurring.

        A structural count, always available even when no magnitude is.
        """
        return len(self.prevented_event_ids)


def _shares(event_ids: tuple[str, ...], context: PropagationContext) -> tuple[MagnitudeShare, ...]:
    """Read one share per consequence, at full weight.

    Full weight rather than the route's apportioned share, deliberately. A share
    apportions a consequence among the several causes CLAIMED for it; a counterfactual asks
    what stops occurring altogether, and a consequence that stops occurring stops occurring
    entirely rather than by its share. The two questions want different numbers and this is
    the one that answers the second.
    """
    return tuple(share_for(event_id, 1.0, context) for event_id in event_ids)


def _grouped(event_ids: tuple[str, ...], context: PropagationContext) -> tuple[ConsequenceSet, ...]:
    """Group consequences by the measurement declared for them and build one set per group.

    Grouping is required rather than optional: a set mixing two measurements has no single
    unit, and `consequence_set` refuses one. Groups are sequenced by measurement identifier
    so two runs produce one list.
    """
    by_measurement: dict[str, list[MagnitudeShare]] = {}
    unmeasured: list[MagnitudeShare] = []
    for share in _shares(event_ids, context):
        if share.measurement_id is None:
            unmeasured.append(share)
        else:
            by_measurement.setdefault(share.measurement_id, []).append(share)
    sets = [consequence_set(tuple(group), context) for _, group in sorted(by_measurement.items())]
    if unmeasured:
        sets.append(consequence_set(tuple(unmeasured), context))
    return tuple(sets)


def prevented_by_removing(
    seed_event_id: str,
    removed_event_ids: tuple[str, ...],
    context: PropagationContext,
) -> PreventedConsequence:
    """Return what the graph says stops occurring if the named nodes are removed.

    `removed_event_ids` is a TUPLE rather than one identifier because a joint cause group is
    removed as a unit -- see this module's docstring. A single ordinary cause is passed as a
    one-element tuple, which keeps one code path rather than two.

    The prevented total is a difference between two combinations over the SAME measurement
    and the same declared operator, so the subtraction is between two figures of one kind.
    When several measurements are in play the largest prevented group is reported and the
    unit names which -- two quantities in different units are never added to make a headline.
    """
    whole = reachable_from(seed_event_id, context)
    removed = frozenset(removed_event_ids)
    # The whole group is deleted at once. Deleting its members one at a time and
    # intersecting would keep every consequence that any single member still holds up,
    # which is the opposite of what removing the group does.
    surviving_reach = reachable_from(seed_event_id, context, excluding=removed)
    prevented = tuple(sorted((whole - surviving_reach) - removed))
    surviving = tuple(sorted(surviving_reach - removed))
    if not prevented:
        return PreventedConsequence(
            removed_event_ids=tuple(sorted(removed)),
            prevented_event_ids=(),
            surviving_event_ids=surviving,
            whole_total=None,
            prevented_total=None,
            unit=None,
            absent_because=(
                "the graph says nothing stops occurring if this is removed: every "
                "consequence downstream of it is also reachable by a route that survives "
                "the removal. That is a statement about this graph's shape and not a "
                "finding that the node does not matter."
            ),
        )
    whole_sets = _grouped(tuple(sorted(whole - removed)), context)
    prevented_sets = _grouped(prevented, context)
    combinable = tuple(
        item for item in prevented_sets if item.combined is not None and item.measurement_id
    )
    if not combinable:
        reason = (
            prevented_sets[0].combination_absent_because
            if prevented_sets and prevented_sets[0].combination_absent_because
            else "no consequence in the prevented set carried an evaluable magnitude."
        )
        return PreventedConsequence(
            removed_event_ids=tuple(sorted(removed)),
            prevented_event_ids=prevented,
            surviving_event_ids=surviving,
            whole_total=None,
            prevented_total=None,
            unit=None,
            absent_because=(
                f"{len(prevented)} consequence(s) stop occurring and none of them could be "
                f"valued: {reason} The COUNT is a measurement and is reported; the total is "
                "not, and is not reported as zero."
            ),
        )
    # Largest by prevented total, ties broken on measurement id so two runs agree. Never a
    # sum across units: adding a currency figure to an elapsed-time figure would produce a
    # headline whose name nobody could write down.
    headline = max(
        combinable,
        key=lambda item: ((item.combined or 0.0), item.measurement_id or ""),
    )
    matching_whole = next(
        (
            item
            for item in whole_sets
            if item.measurement_id == headline.measurement_id and item.combined is not None
        ),
        None,
    )
    return PreventedConsequence(
        removed_event_ids=tuple(sorted(removed)),
        prevented_event_ids=prevented,
        surviving_event_ids=surviving,
        whole_total=matching_whole.combined if matching_whole is not None else None,
        prevented_total=headline.combined,
        unit=headline.unit,
        absent_because=(
            None
            if matching_whole is not None
            else (
                "the prevented total is reported and the whole-graph total it is a part of "
                "is not, because no consequence outside the prevented set carried the same "
                "measurement. The share of the whole cannot be stated, only the part."
            )
        ),
    )


def share_of_whole(prevented: PreventedConsequence) -> float | None:
    """Return the prevented total as a proportion of the whole, or None if either is absent.

    prd.md §32's "propagation reduced 82%" figure. Returns `None` rather than zero whenever
    either operand is missing or the whole is nothing: a proportion of an unmeasured whole
    is not a proportion, and printing it as zero would say the removal prevents none of
    something when the truth is that nobody could tell.
    """
    if prevented.prevented_total is None or prevented.whole_total is None:
        return None
    if prevented.whole_total == 0.0:
        return None
    difference = difference_of(prevented.whole_total, prevented.prevented_total)
    if difference is None:
        return None
    return prevented.prevented_total / prevented.whole_total
