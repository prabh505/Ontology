"""Two acts on one chain are not worth the two figures added up.

The error this file exists to not make, stated plainly: **an operator shown two
recommendations worth eleven hours each will plan for twenty-two hours.** If both acts sit
on the same chain, the second one saves what the first one already saved, and the true
figure is closer to eleven than to twenty-two. Every part of the system upstream of here is
correct and the operator is still wrong, because nothing told them the two interact.

HOW THE JOINT FIGURE IS OBTAINED (ADR-0077)
---------------------------------------------
By simulating the whole set in ONE call to module 13. Not by simulating each act and
combining the answers -- any combination rule would be a model of how benefits interact, and
this engine has no standing to hold one. Module 13 already validates a set atomically
(ADR-0066) and propagates it together, so handing it the set asks the actual question.

`sum()` appears nowhere in this file and a law test asserts it: the naive total is computed
in `core.aggregation` under a named aggregator, so even the number that exists to be
contrasted with the truth is not arithmetic written here.

WHY THE NAIVE TOTAL IS PUBLISHED AT ALL
-----------------------------------------
Because the overlap is the finding. A portfolio that quietly reported the correct joint
figure would be right and would teach a reader nothing; one that reports both, and the
difference between them, shows that the interaction exists and how large it is. This is the
same reason module 12 reports the apportioned share beside the whole rather than instead of
it, and the same reason `ConfidenceVector` keeps its components.

WHAT COUNTS AS AN INTERACTION
-------------------------------
Set intersection, not a heuristic. Two acts interact when the consequences they reach
overlap, or when they belong to one joint cause group. A pair that fails both tests is
independent as far as this graph can tell.

AND WHY NO LOSS IS PUBLISHED FOR AN INDEPENDENT PAIR
------------------------------------------------------
Because the two figures would not be comparable. Module 13's benefit is a HEADLINE: the
single largest consequence affected, which is what its own sensitivity sweep perturbs and
what makes module 14's figure agree with module 13's by construction. Where two acts touch
DIFFERENT consequences, the naive total adds two headlines while the joint figure reports
one, and the difference between them measures that mismatch rather than any overlap.

Publishing it anyway would put a confident, specific, wrong number on the artifact -- the
exact failure this file exists to prevent, committed by the file that exists to prevent it.
So the loss is withheld with a reason, and the combined figure across several consequences
stays where the pack's declared operator computes it: `BenefitEstimate
.attributed_consequence`, from module 12.

**No domain vocabulary appears below.**
"""

from __future__ import annotations

from enum import Enum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from causalog.core.attribution import combine_magnitudes, difference_of
from causalog.core.errors import ContractViolationError
from causalog.core.run import OutputEnvelope
from causalog.recommendation_engine.candidate import Candidate
from causalog.recommendation_engine.context import RecommendationContext
from causalog.recommendation_engine.estimate import BenefitEstimate, estimate

__all__ = [
    "NAIVE_OPERATOR",
    "InteractionKind",
    "PortfolioBenefit",
    "interactions_within",
    "portfolio_benefit",
]


class InteractionKind(str, Enum):
    """Why two acts are not independent. Closed."""

    SHARED_CONSEQUENCE = "SHARED_CONSEQUENCE"
    """Their reachable consequence sets intersect: the second saves what the first saved."""

    SAME_JOINT_GROUP = "SAME_JOINT_GROUP"
    """Both contribute to one conjunctive cause. Neither alone prevents the effect."""


class PortfolioBenefit(BaseModel):
    """A set's worth, the sum a reader would otherwise have assumed, and the gap.

    `naive_total` is not an alternative answer. It is the mistake, published so the
    correction is visible. `joint_low`/`joint_high` are the answer.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    member_event_ids: tuple[str, ...] = Field(min_length=1)
    #: What module 13 says the whole set is worth, simulated in one call.
    joint_low: float | None = None
    joint_high: float | None = None
    unit: str | None = None
    #: What adding the members' individual figures would have suggested. Never the answer.
    naive_total_low: float | None = None
    naive_total_high: float | None = None
    #: `naive_total_high - joint_high`, when the two are comparable AND the members
    #: interact. Positive means the naive sum OVERSTATES, which is the direction that
    #: misleads an operator into planning for savings that will not arrive.
    overlap_loss: float | None = None
    #: Why no loss figure is published. See `portfolio_benefit`: absent is a statement that
    #: the comparison was not valid here, never a claim that the loss is nil.
    loss_absent_because: str | None = None
    #: Which pairs interact and why, sorted. Empty means the graph shows no interaction --
    #: which is a claim about this graph, not a guarantee of independence in the world.
    interactions: tuple[tuple[str, str, InteractionKind], ...] = ()
    #: Names the `core.aggregation` function that produced the naive total, so a reader can
    #: recompute the number this artifact exists to warn them about.
    naive_aggregation: str | None = None
    absent_because: str | None = None


def interactions_within(
    members: tuple[Candidate, ...], context: RecommendationContext
) -> tuple[tuple[str, str, InteractionKind], ...]:
    """Return every interacting pair in a set, sorted, with the reason each interacts.

    Both tests are set operations over data already computed: `Candidate.reach` was filled
    once at discovery, and joint membership comes from the graph builder. Nothing is
    estimated and no threshold is applied, so there is no tuning knob here to get wrong.
    """
    del context  # membership arrives on the candidates; retained for signature stability
    found: list[tuple[str, str, InteractionKind]] = []
    for position, left in enumerate(members):
        for right in members[position + 1 :]:
            if (
                left.joint_cause_group_id is not None
                and left.joint_cause_group_id == right.joint_cause_group_id
            ):
                found.append((left.event_id, right.event_id, InteractionKind.SAME_JOINT_GROUP))
                continue
            if set(left.reach) & set(right.reach):
                found.append((left.event_id, right.event_id, InteractionKind.SHARED_CONSEQUENCE))
    return tuple(sorted(found, key=lambda item: (item[0], item[1], item[2].value)))


#: The operator the naive total is taken under. `SUM` deliberately: this number exists to
#: reproduce the mistake a reader would otherwise make in their head, and the mistake is
#: addition. It is named rather than written, and it is named here rather than read from the
#: pack, because the pack declares how CONSEQUENCES combine -- a real question about the
#: domain -- and this is a statement about human arithmetic that no pack should be asked to
#: authorise.
NAIVE_OPERATOR: Final[str] = "SUM"


def _naive(readings: tuple[float, ...]) -> float | None:
    """Total a set of individual figures under a NAMED operator, never with `sum`.

    `core.attribution` holds the arithmetic. Routing even this number -- the one that exists
    to be contradicted -- through a named function means a reader can see which rule
    produced it, and means no arithmetic over benefit figures is written in this package at
    all (`CONVENTIONS.md` §6a).
    """
    if not readings:
        return None
    return combine_magnitudes(readings, NAIVE_OPERATOR)


def portfolio_benefit(
    members: tuple[Candidate, ...],
    individual: dict[str, BenefitEstimate],
    context: RecommendationContext,
    envelope: OutputEnvelope,
    *,
    accept_unpromoted: bool = False,
) -> PortfolioBenefit:
    """Simulate a set as a set, and contrast it with the total nobody should have added.

    Raises:
        ContractViolationError: if the set is empty. A portfolio of nothing is not zero.
    """
    if not members:
        raise ContractViolationError(
            "recommendation_engine.portfolio_benefit was given an empty set. A portfolio "
            "with no members has no benefit to report and is not a benefit of zero."
        )
    member_ids = tuple(sorted(candidate.event_id for candidate in members))
    joint = estimate(member_ids, context, envelope, accept_unpromoted=accept_unpromoted)

    lows = tuple(
        individual[event_id].benefit.low
        for event_id in member_ids
        if event_id in individual and individual[event_id].benefit.low is not None
    )
    highs = tuple(
        individual[event_id].benefit.high
        for event_id in member_ids
        if event_id in individual and individual[event_id].benefit.high is not None
    )
    naive_low = _naive(tuple(value for value in lows if value is not None))
    naive_high = _naive(tuple(value for value in highs if value is not None))

    found = interactions_within(members, context)
    # The gap is a difference between two figures of ONE kind, taken under the function
    # module 12 already uses for exactly that (`difference_of`): the whole, less what
    # survives it. Writing `naive_high - joint.benefit.high` here would be arithmetic on a
    # benefit in this package, which §6a's sibling rule exists to keep out.
    loss: float | None = None
    loss_absent: str | None = None
    if not found:
        loss_absent = (
            "these acts do not interact on this graph, so their benefits are not being "
            "double-counted and there is no overlap to report. No figure is published "
            "because the two totals above are not comparable when the members touch "
            "different consequences: the naive total adds two headline figures while the "
            "joint figure reports one. The combined quantity across several consequences is "
            "attributed by module 12 under the pack's own declared operator, and appears on "
            "each member's estimate rather than here."
        )
    elif naive_high is None or joint.benefit.high is None:
        loss_absent = (
            "one of the two totals could not be measured, so their difference would be a "
            "figure standing on an absence."
        )
    else:
        loss = difference_of(naive_high, joint.benefit.high)

    return PortfolioBenefit(
        member_event_ids=member_ids,
        joint_low=joint.benefit.low,
        joint_high=joint.benefit.high,
        unit=joint.benefit.unit,
        naive_total_low=naive_low,
        naive_total_high=naive_high,
        overlap_loss=loss,
        loss_absent_because=loss_absent,
        interactions=found,
        naive_aggregation=NAIVE_OPERATOR,
        absent_because=joint.benefit.absent_because,
    )
