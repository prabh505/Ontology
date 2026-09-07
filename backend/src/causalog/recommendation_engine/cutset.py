"""Which acts, taken together, break the most chains -- and whether that set is provably few.

The task prd.md §32 does not name. §32 exposes intervention opportunities per chain, one at
a time. But a chain with joint causes has no single opportunity: removing one contributor of
a conjunctive cause does not prevent the effect (ADR-0069), so the honest recommendation is
a SET, and it has to say that it is a set or an operator will do one of the three things and
find that nothing improved.

WHAT A CHAIN IS HERE
---------------------
A pair: a source node, and one of the outcomes the caller named as worth protecting, where
the second is currently reachable from the first. A set BREAKS that pair when deleting the
set's nodes leaves the outcome unreachable from the source. Reachability is
`propagation_analyzer.reachable_from(..., excluding=...)`, which is the same primitive
module 12 uses for counterfactual-lite reasoning -- so "broken" means here exactly what it
means there, rather than nearly.

Chains are counted as PAIRS, not as routes. Two routes between one source and one outcome
are one chain, because they are one thing an operator cares about. Counting routes would
make a diamond look like twice the opportunity, which is ADR-0061's error in a new place.

TWO SEARCHES, AND THE ARTIFACT SAYS WHICH RAN (ADR-0076)
----------------------------------------------------------
Minimal set cover is NP-hard and prd.md §55 allows five seconds. So:

* At or below the pack's `cut_set_exact_ceiling` candidates, every subset up to
  `portfolio_size_cap` is enumerated and the result is genuinely minimal -- no smaller set
  achieves that coverage, and this module knows it because it looked.
* Above the ceiling, a greedy set cover runs and the result is labelled
  `NOT_PROVEN_MINIMAL`, naming the ceiling that bound it and the count that exceeded it.

The label is on the artifact rather than in a log, because "minimal" is a claim and the
difference between a proved claim and a plausible one is exactly what a reader needs. A
greedy cover is often minimal; this module simply cannot say so.

JOINT GROUPS ARE INDIVISIBLE
------------------------------
A set holding one member of a joint cause group is expanded to hold the whole group before
it is scored, and `is_set_because` states it. An operator reading the recommendation must
see "these three together, or none" rather than a list they might reasonably do one of.

**And a group larger than the declared size cap is REFUSED, not silently admitted.** The
expansion can push a set past `portfolio_size_cap`, and letting it through would mean a
declared bound that quietly does not hold -- the worst kind, because the artifact still
looks bounded. Letting it through and shrinking it back would be worse still: a partial
joint cause buys nothing, so a truncated group is a recommendation that cannot work. So the
set is dropped and the refusal is reported by name, which leaves a pack author with the two
real choices -- raise the cap, or accept that this act is beyond what one operator can be
asked to do at once.

**No domain vocabulary appears below.**
"""

from __future__ import annotations

from enum import Enum
from itertools import combinations

from pydantic import BaseModel, ConfigDict, Field

from causalog.causal_engine.propagation_analyzer import reachable_from
from causalog.recommendation_engine.candidate import Candidate
from causalog.recommendation_engine.context import RecommendationContext

__all__ = ["CutSet", "SearchRegime", "chains_of", "find_cut_sets"]


class SearchRegime(str, Enum):
    """Which search produced a set, and therefore what its minimality claim is worth."""

    EXACT = "EXACT"
    """Every subset up to the size cap was enumerated. The set is provably minimal."""

    GREEDY_NOT_PROVEN_MINIMAL = "GREEDY_NOT_PROVEN_MINIMAL"
    """A greedy cover. Often minimal; this module did not look and does not claim it."""

    NOT_RUNNABLE = "NOT_RUNNABLE"
    """The pack declares no bound, so no search ran. Distinct from a search finding none."""


class CutSet(BaseModel):
    """A set of acts, what it breaks, and how strong the claim about its size is."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Sorted, unique, at least one. A one-member set is a singleton recommendation and is
    #: represented here rather than in a second type, so one code path scores both.
    member_event_ids: tuple[str, ...] = Field(min_length=1)
    #: How many (source, outcome) pairs stop being connected. Pairs, never routes.
    chains_broken: int = Field(ge=0)
    chains_considered: int = Field(ge=0)
    regime: SearchRegime
    #: Present exactly when the set holds more than one member: why it must be taken whole.
    is_set_because: str | None = None
    #: Present exactly when the regime is not EXACT: what stopped this being provable.
    not_minimal_because: str | None = None

    def sort_key(self) -> tuple[int, int, str]:
        """Canonical sequence: most broken first, then smallest, then by identifier."""
        return (-self.chains_broken, len(self.member_event_ids), ",".join(self.member_event_ids))


def chains_of(
    candidates: tuple[Candidate, ...], context: RecommendationContext
) -> tuple[tuple[str, str], ...]:
    """Return the (source, outcome) pairs currently connected, sorted.

    An outcome the caller named that nothing reaches contributes no pair, and its absence is
    a real finding rather than an omission: it means this graph offers no act that could
    have protected it.
    """
    pairs: list[tuple[str, str]] = []
    for candidate in candidates:
        for outcome_event_id in sorted(context.outcome_event_ids):
            if outcome_event_id in candidate.reach:
                pairs.append((candidate.event_id, outcome_event_id))
    return tuple(sorted(set(pairs)))


def _expand_joint(
    members: frozenset[str], context: RecommendationContext
) -> tuple[frozenset[str], tuple[str, ...]]:
    """Grow a set to hold every joint group any of its members belongs to.

    Returns the grown set and the identifiers of the groups that grew it, so the caller can
    say WHY the set is a set rather than only that it is one.
    """
    grown = set(members)
    groups: list[str] = []
    changed = True
    while changed:
        changed = False
        for group in sorted(context.joint_groups, key=lambda item: item.joint_cause_group_id):
            group_members = set(group.member_source_event_ids)
            if grown & group_members and not group_members <= grown:
                grown |= group_members
                groups.append(group.joint_cause_group_id)
                changed = True
    return (frozenset(grown), tuple(sorted(set(groups))))


def _broken_by(
    members: frozenset[str],
    chains: tuple[tuple[str, str], ...],
    context: RecommendationContext,
) -> int:
    """Count the pairs this set disconnects. Pairs, never routes.

    Chains are GROUPED BY SOURCE before anything is traversed, so one reachability walk
    answers every outcome that source is asked about. The naive shape -- a walk per pair --
    is the same answer and does not meet prd.md §55: a greedy step over two hundred
    candidates against four hundred pairs is eighty thousand traversals, and the first run of
    `scripts/recommend_interventions.py` against the real slice did not finish.

    The grouping changes cost, never semantics: `reachable_from` depends on the source and
    the excluded set, and not on which outcome the caller is about to look for.
    """
    grouped: dict[str, set[str]] = {}
    broken = 0
    for source_event_id, outcome_event_id in chains:
        if source_event_id in members:
            # Removing the source removes the chain trivially and truthfully: nothing
            # travels from a node that did not occur.
            broken += 1
            continue
        grouped.setdefault(source_event_id, set()).add(outcome_event_id)
    for source_event_id, outcomes in grouped.items():
        still = reachable_from(source_event_id, context.propagation, excluding=members)
        broken += len(outcomes - still)
    return broken


def _describe_set(groups: tuple[str, ...], size: int) -> str | None:
    """Say why a multi-member set must be taken whole, or return None for a singleton."""
    if size < 2:
        return None
    if groups:
        return (
            f"these acts must be taken together because they belong to joint cause "
            f"group(s) {', '.join(groups)}. A joint cause is conjunctive: doing some of "
            "these and not the others leaves the effect standing, so a partial execution "
            "buys nothing rather than buying a proportion (ADR-0069)."
        )
    return (
        "these acts must be taken together because no one of them alone disconnects the "
        "chains this set disconnects. They are not independently valuable in proportion; "
        "the coverage figure beside them is the coverage of the whole set."
    )


def find_cut_sets(
    candidates: tuple[Candidate, ...], context: RecommendationContext
) -> tuple[tuple[CutSet, ...], str | None, tuple[str, ...]]:
    """Return the cut sets worth considering, the policy gap, and what was refused by size.

    Returns:
        `(cut_sets, gap, oversized)`. `gap` is `None` when a search ran; otherwise it names
        the declaration that would have let one run, and `cut_sets` is empty. An empty
        result with no gap means a search ran and found nothing to break -- a different
        statement, reported as one. `oversized` names every joint group whose indivisible
        membership exceeds the declared `portfolio_size_cap`; those sets are refused rather
        than admitted over the bound or truncated under it.
    """
    size_cap = context.parameters.portfolio_size_cap
    exact_ceiling = context.parameters.cut_set_exact_ceiling
    if size_cap is None or exact_ceiling is None:
        return (
            (),
            (
                "the pack declares no recommendation.portfolio_size_cap and/or no "
                "recommendation.cut_set_exact_ceiling, so no cut-set search could run. "
                "Nothing is defaulted: a size cap chosen here would decide how large an act "
                "an operator is asked to take, and a ceiling chosen here would decide "
                "whether the word 'minimal' on the artifact is a proof or a guess "
                "(ADR-0049, ADR-0076)."
            ),
            (),
        )
    chains = chains_of(candidates, context)
    if not chains or not candidates:
        return ((), None, ())

    exact = len(candidates) <= exact_ceiling
    regime = SearchRegime.EXACT if exact else SearchRegime.GREEDY_NOT_PROVEN_MINIMAL
    not_minimal = (
        None
        if exact
        else (
            f"{len(candidates)} candidates exceed the pack's declared "
            f"cut_set_exact_ceiling of {exact_ceiling}, so subsets were not enumerated and "
            "a greedy cover ran instead. The set below may well be minimal; this module did "
            "not look and does not claim it (ADR-0076)."
        )
    )

    found: dict[frozenset[str], CutSet] = {}
    oversized: set[str] = set()
    identifiers = tuple(candidate.event_id for candidate in candidates)

    def record(raw: frozenset[str]) -> None:
        members, groups = _expand_joint(raw, context)
        if members in found:
            return
        if len(members) > size_cap:
            # Only reachable through joint expansion: the searches never choose a set larger
            # than the cap on their own. See this module's docstring -- refused by name
            # rather than admitted over the bound or truncated under it.
            oversized.add(
                f"a joint cause group ({', '.join(sorted(groups)) or 'unnamed'}) is "
                f"indivisible at {len(members)} members, above the declared "
                f"recommendation.portfolio_size_cap of {size_cap}. It is refused rather "
                "than recommended over the bound: a partial joint cause buys nothing, so "
                "truncating it to fit would produce an act that cannot work (ADR-0069). "
                "Raise the cap, or accept that this is beyond one operator's single act."
            )
            return
        found[members] = CutSet(
            member_event_ids=tuple(sorted(members)),
            chains_broken=_broken_by(members, chains, context),
            chains_considered=len(chains),
            regime=regime,
            is_set_because=_describe_set(groups, len(members)),
            not_minimal_because=not_minimal,
        )

    # EVERY SINGLETON IS RECORDED FIRST, under both regimes. A cut-set search answers "which
    # acts together break the most chains"; it does not answer "what is each act worth", and
    # a ranked list needs both. The greedy branch below emits only its own cumulative
    # prefixes -- at most `size_cap` of them -- so without this loop a run over two hundred
    # candidates would score three of them and publish a top-three list while calling it a
    # top ten. The first real run of `scripts/recommend_interventions.py` did exactly that.
    for identifier in identifiers:
        record(frozenset({identifier}))

    if exact:
        for size in range(2, min(size_cap, len(identifiers)) + 1):
            for subset in combinations(identifiers, size):
                record(frozenset(subset))
    else:
        # Greedy: repeatedly take the candidate that breaks the most still-unbroken chains,
        # emitting the accumulated set at every size. Emitting each prefix rather than only
        # the final set means a reader sees what the second and third acts bought.
        taken: set[str] = set()
        for _ in range(min(size_cap, len(identifiers))):
            covered = _broken_by(frozenset(taken), chains, context) if taken else 0
            # Score every remaining candidate, then take the best by (most gained, then
            # lowest identifier). Expressed as a sorted list rather than as a running best,
            # so the tie-break is a visible sequencing rule rather than a buried comparison
            # -- and so two runs over one input cannot disagree (CONVENTIONS.md §11).
            gains = sorted(
                (
                    -(_broken_by(frozenset(taken | {event_id}), chains, context) - covered),
                    event_id,
                )
                for event_id in identifiers
                if event_id not in taken
            )
            if not gains:
                break
            negated_gain, best_id = gains[0]
            if taken and -negated_gain <= 0:
                # Nothing left buys another chain. Stopping rather than padding the set to
                # its cap: an act that breaks nothing does not belong in a recommendation an
                # operator is asked to execute as a unit.
                break
            taken.add(best_id)
            record(frozenset(taken))

    return (
        tuple(sorted(found.values(), key=lambda item: item.sort_key())),
        None,
        tuple(sorted(oversized)),
    )
