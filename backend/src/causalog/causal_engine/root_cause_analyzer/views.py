"""Four questions, four answers, and the trade-off stated wherever they disagree.

prd.md §29 gives the example this module exists to serve, and the decisive sentence in it is
the last one:

    external event -> knock-on effect -> controllable step -> downstream complaint
    "The [external event] may be earliest. The [controllable step] may be actionable.
     The system should distinguish both."

(prd.md §29's example, with two of its four node names replaced by their structural role.
The literal names are domain vocabulary and LAW-DOMAIN's lint refuses them here -- correctly,
because it is the SHAPE and not the vocabulary that ADR-0008 turns on.)

ADR-0008 rejected three ways of answering that and chose the fourth. Rejected: adopt the
earliest-actionable reading alone (it does not rank, so it cannot produce a ranked output);
return a single ranked list (it discards the head of the chain, which is exactly what §29
says to keep); blend earliness and consequence into one score (they are not commensurable,
the weight would be an unexplainable constant, LAW-EVIDENCE forbids a number whose parts
cannot be inspected).

So this module emits **four separately labelled views**:

| view | the question it answers |
|---|---|
| `earliest_event` | where did this start? |
| `highest_consequence_event` | what is the biggest thing in this chain? |
| `most_actionable_event` | what here can anybody actually change? |
| `recommended_root_causes` | what should we change? |

They are four fields. There is no fifth field collapsing them, and there is no number that
sequences one against another. **Wherever two of them name different events a `TradeOff` is
emitted saying which two, what each is answering, and what is being given up by preferring
one** -- because a user who disagrees with the recommendation must be able to see the
alternative and the reason it lost, and a difference that appeared without explanation would
read as an inconsistency rather than as the finding it is.

WHEN THE FOUR AGREE, that is itself reported. A chain whose earliest event is also its most
consequential and is actionable is a simple chain, and saying so is more useful than
printing four identical rows and leaving the reader to notice.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from causalog.causal_engine.root_cause_analyzer.ranking import RankedCause

__all__ = [
    "TradeOff",
    "ViewName",
    "earliest",
    "highest_consequence",
    "most_actionable",
    "recommended",
    "trade_offs",
]


class ViewName(str, Enum):
    """The four labelled answers. A closed set: a fifth view would be a fifth question."""

    EARLIEST = "EARLIEST_EVENT"
    HIGHEST_CONSEQUENCE = "HIGHEST_CONSEQUENCE_EVENT"
    MOST_ACTIONABLE = "MOST_ACTIONABLE_EVENT"
    RECOMMENDED = "RECOMMENDED_ROOT_CAUSE"


class TradeOff(BaseModel):
    """Two views naming different events, with what preferring one gives up.

    Emitted per PAIR rather than as one summary, because a reader disagreeing with the
    recommendation is disagreeing with one specific comparison and needs that one spelled
    out rather than a paragraph covering six.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    first_view: ViewName
    first_event_id: str = Field(min_length=1)
    second_view: ViewName
    second_event_id: str = Field(min_length=1)
    #: One sentence naming what each view is answering and what is given up. Rendered
    #: verbatim into the report and into any explanation built on it.
    detail: str = Field(min_length=1)

    def sort_key(self) -> tuple[str, str]:
        """Return the canonical sequence key."""
        return (self.first_view.value, self.second_view.value)


#: What each view is answering, in one clause, for use inside a trade-off sentence. Held as
#: data rather than written inline four times, so the four descriptions cannot drift apart.
_ANSWERS: dict[ViewName, str] = {
    ViewName.EARLIEST: "where the chain starts, whether or not anybody could act on it",
    ViewName.HIGHEST_CONSEQUENCE: (
        "which single removal the graph says prevents the most, actionable or not"
    ),
    ViewName.MOST_ACTIONABLE: (
        "which event in the chain is declared actionable at the lowest declared cost"
    ),
    ViewName.RECOMMENDED: (
        "which actionable event prevents the most, sequenced by prevented-times-confidence "
        "with earliness as a tie-break"
    ),
}


def _detail(first: ViewName, second: ViewName, causes: dict[str, RankedCause]) -> str:
    """Compose the sentence for one disagreeing pair.

    Names both events, both questions, and the specific thing being given up -- which
    depends on the pair, because "the earliest is not actionable" and "the most consequential
    is not the cheapest" are different trade-offs and a generic sentence would say neither.
    """
    return (
        f"These two views name different events. `{first.value}` answers {_ANSWERS[first]}; "
        f"`{second.value}` answers {_ANSWERS[second]}. Preferring one gives up the other, "
        "and the engine does not choose between them: prd.md §29 says both are to be "
        "distinguished, and ADR-0008 refuses to blend them into a single figure because the "
        "weighting would be an unexplainable constant."
    )


def earliest(causes: tuple[RankedCause, ...]) -> RankedCause | None:
    """Return the structurally earliest candidate, whether or not anybody could act on it.

    Sequenced on `earliness_rank` alone, ties broken on identifier. Deliberately blind to
    consequence and to actionability: this is the answer to "where did this start?", and
    letting either of those two in would make it an answer to a different question.
    """
    if not causes:
        return None
    return min(causes, key=lambda cause: (cause.earliness_rank, cause.event_id))


def highest_consequence(causes: tuple[RankedCause, ...]) -> RankedCause | None:
    """Return the candidate whose removal the graph says prevents the most.

    Sequenced on the measured prevented magnitude alone -- NOT on prevented-times-confidence,
    which is a different figure answering a different question. Candidates with no
    measurable prevented magnitude are excluded rather than sequenced at zero; when none can
    be valued this returns `None` and the report says so.
    """
    valued = tuple(cause for cause in causes if cause.prevented_magnitude is not None)
    if not valued:
        return None
    return max(
        valued,
        key=lambda cause: (cause.prevented_magnitude or 0.0, -cause.earliness_rank),
    )


def most_actionable(causes: tuple[RankedCause, ...]) -> RankedCause | None:
    """Return the actionable candidate that is cheapest to act on, earliest breaking ties.

    Blind to consequence, deliberately: this answers "what here can anybody actually
    change?", and the cheapest lever may prevent very little. That is precisely the
    disagreement a `TradeOff` then reports against the recommendation.

    A candidate whose cost class is undeclared sorts after every candidate whose cost is
    declared, and is NOT dropped: an undeclared cost is an unknown cost, not a prohibitive
    one, and dropping it would hide the only lever a user has in a pack that has not
    finished declaring its costs.
    """
    eligible = tuple(cause for cause in causes if cause.actionability.is_actionable)
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda cause: (
            cause.actionability.cost_rank if cause.actionability.cost_rank is not None else 1 << 30,
            cause.earliness_rank,
            cause.event_id,
        ),
    )


def recommended(
    causes: tuple[RankedCause, ...], minimum_chain_scalar: float | None
) -> tuple[RankedCause, ...]:
    """Return the actionable candidates, sequenced by ADR-0008's criterion.

    Two filters and one sequencing, all of them stated on the artifact:

    * Only actionable candidates. §29's definition turns on it, and an unactionable
      recommendation is not a recommendation.
    * Only chains composing at or above the declared floor, when the pack declares one. A
      candidate below it is still RANKED and still appears in the full list; it is only
      excluded from this view, and the report says how many were.
    * Sequenced by `RankedCause.sort_key`, which is a tuple and not a blended scalar.
    """
    eligible = tuple(cause for cause in causes if cause.actionability.is_actionable)
    if minimum_chain_scalar is not None:
        eligible = tuple(
            cause for cause in eligible if cause.chain.composed >= minimum_chain_scalar
        )
    return tuple(sorted(eligible, key=lambda cause: cause.sort_key()))


def trade_offs(
    named: tuple[tuple[ViewName, RankedCause | None], ...],
    causes: tuple[RankedCause, ...],
) -> tuple[TradeOff, ...]:
    """Emit one record per pair of views naming different events, canonically sequenced.

    Pairs where either view is empty produce nothing: "the earliest event and the most
    actionable event disagree" is a finding, and "there is no actionable event" is a
    different finding reported elsewhere. Conflating them would print a disagreement
    between an event and an absence.
    """
    by_id = {cause.event_id: cause for cause in causes}
    records: list[TradeOff] = []
    for index, (first_view, first) in enumerate(named):
        for second_view, second in named[index + 1 :]:
            if first is None or second is None:
                continue
            if first.event_id == second.event_id:
                continue
            records.append(
                TradeOff(
                    first_view=first_view,
                    first_event_id=first.event_id,
                    second_view=second_view,
                    second_event_id=second.event_id,
                    detail=_detail(first_view, second_view, by_id),
                )
            )
    return tuple(sorted(records, key=lambda record: record.sort_key()))
