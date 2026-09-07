"""The bounded forward walk: breadth-first, shortest-route, and never unbounded.

Breadth-first rather than depth-first, and the choice is load-bearing rather than
stylistic. `PropagationNode.depth` is the length of the SHORTEST route from the seed, which
is the same never-count-twice rule the consequence set applies to magnitude applied to
distance; breadth-first settles each node at its shortest depth the first time it is
reached, so no node is ever revised downward and the walk needs no second pass.

THREE THINGS STOP THE WALK, and all three are reported rather than silently absorbed.

* **The declared depth.** A pack's `maximum_depth`, itself bounded by
  `MAX_PROPAGATION_DEPTH`. Reaching it is `DEPTH_BOUND` truncation naming the frontier that
  was not walked. It is never printed as a completed sweep -- prd.md §30's whole subject is
  how far consequence travels, and a bounded answer to that question that does not say it
  was bounded is a wrong answer.
* **The declared node cap.** A separate bound because a shallow, very wide fan-out and a
  deep, narrow chain are different shapes and one number cannot bound both.
* **A circuit.** prd.md §31 makes a reinforcing loop a REQUIREMENT rather than a defect. A
  link back onto the current route terminates that route, records a `CIRCUIT`, and the walk
  continues elsewhere. It is not an error and it does not stop the traversal.

**A pack that declares no depth gets no traversal**, and the tree says what it would have
needed. That is ADR-0049's absent-means-NOT-RUNNABLE rule: a default depth written here
would be this engine's opinion about how far consequence travels in someone else's domain.

**No domain vocabulary appears below.** Nothing here reads a type name or a link kind.
"""

from __future__ import annotations

from itertools import pairwise

from causalog.causal_engine.propagation_analyzer.context import PropagationContext
from causalog.causal_engine.propagation_analyzer.graph import (
    MAX_PROPAGATION_DEPTH,
    TruncationReason,
    TruncationRecord,
)
from causalog.causal_engine.propagation_analyzer.view import GraphLink

__all__ = [
    "DEPTH_NOT_DECLARED",
    "Reached",
    "effective_depth_bound",
    "links_along_route",
    "reachable_from",
    "walk",
]

#: The sentence a tree carries when the pack declares no depth. Fixed text so that two runs
#: over two packs that both omit it produce one message.
DEPTH_NOT_DECLARED = (
    "the pack declares no propagation_analysis.maximum_depth, so no traversal ran. How far "
    "consequence travels before it stops being consequence is a domain judgement -- "
    "prd.md §30's own example is six deep and another domain's is not -- and a bound "
    "written into the engine would be this engine's opinion about someone else's domain "
    "(ADR-0049). This is not a propagation of zero."
)


class Reached:
    """One node the walk settled, with how it got there. Never leaves this module.

    A small mutable holder built during the walk and read out afterwards; the artifacts that
    leave are `PropagationNode` values assembled from these in `analyze`.
    """

    __slots__ = ("depth", "event_id", "link_scalars", "reached_ids", "route_count", "weight")

    def __init__(
        self, event_id: str, depth: int, link_scalars: tuple[float, ...], weight: float
    ) -> None:
        """Record a node at its shortest depth, with the links along that shortest route."""
        self.event_id = event_id
        self.depth = depth
        self.link_scalars = link_scalars
        self.weight = weight
        self.route_count = 1
        self.reached_ids: set[str] = set()


def effective_depth_bound(context: PropagationContext) -> int | None:
    """Return the depth the walk will honour, or None when the pack declares none.

    A declared depth above `MAX_PROPAGATION_DEPTH` is clamped rather than refused. The
    ceiling is not a policy competing with the pack's: it is the point past which a walk
    over a graph that should be acyclic is evidence that it is not, and continuing would be
    looping rather than measuring. The clamp is visible in the truncation record, which
    names the depth actually reached.
    """
    declared = context.parameters.maximum_depth
    if declared is None:
        return None
    return min(declared, MAX_PROPAGATION_DEPTH)


def walk(
    seed_event_id: str, context: PropagationContext
) -> tuple[dict[str, Reached], tuple[TruncationRecord, ...]]:
    """Walk forward from one seed, returning the settled nodes and where it stopped.

    The seed itself is NOT in the result. prd.md §30 measures downstream consequence, and
    including the seed would put the thing being explained into its own consequence set --
    where it would contribute a magnitude and inflate every total by it.

    Determinism: the frontier is drained in insertion sequence and every node's onward links
    arrive canonically sequenced from the view, so the visit sequence is a function of the
    graph and not of dictionary iteration.
    """
    bound = effective_depth_bound(context)
    if bound is None:
        return {}, ()
    node_cap = context.parameters.traversal_node_cap
    settled: dict[str, Reached] = {}
    # Onward adjacency is tracked separately from `settled` because the SEED has onward
    # links and is deliberately not a settled node: it is the thing being explained, not one
    # of its own consequences. Folding the two together would either lose the seed's
    # children or put the seed into its own consequence set, where it would contribute a
    # magnitude and inflate every total by it.
    reached_by: dict[str, set[str]] = {}
    truncations: list[TruncationRecord] = []
    # Each frontier entry carries the route that reached it, so a circuit is detected
    # against THIS route rather than against the settled set -- a node reachable by two
    # disjoint routes is not a circuit, and treating it as one would drop a real branch.
    frontier: list[tuple[str, int, tuple[float, ...], tuple[str, ...], float]] = [
        (seed_event_id, 0, (), (seed_event_id,), 1.0)
    ]
    capped = False
    while frontier:
        event_id, depth, scalars, route, weight = frontier.pop(0)
        onward = context.view.links_from(event_id)
        if depth >= bound:
            if onward:
                beyond = tuple(sorted({link.target_event_id for link in onward}))
                truncations.append(
                    TruncationRecord(
                        reason=TruncationReason.DEPTH_BOUND,
                        at_event_id=event_id,
                        depth=depth,
                        unwalked_event_ids=beyond,
                        detail=(
                            f"the declared maximum_depth of {bound} was reached here. "
                            f"{len(beyond)} further consequence(s) exist beyond this point "
                            "and were NOT measured; every figure in this report is "
                            "therefore a lower bound."
                        ),
                    )
                )
            continue
        for link in onward:
            target = link.target_event_id
            if target in route:
                truncations.append(
                    TruncationRecord(
                        reason=TruncationReason.CIRCUIT,
                        at_event_id=target,
                        depth=depth + 1,
                        detail=(
                            f"the link from {event_id} leads back onto the route that "
                            "reached it. This route terminates here and the circuit is "
                            "recorded; the traversal continues elsewhere. A reinforcing "
                            "loop is a requirement of prd.md §31, not a defect."
                        ),
                    )
                )
                continue
            if target in settled:
                # A second route to a node already settled at its shortest depth. The node
                # is NOT revisited and its magnitude is NOT counted again; only the route
                # count rises, and that number multiplies nothing.
                settled[target].route_count = settled[target].route_count + 1
                reached_by.setdefault(event_id, set()).add(target)
                continue
            if node_cap is not None and len(settled) >= node_cap:
                capped = True
                continue
            reached = Reached(
                event_id=target,
                depth=depth + 1,
                link_scalars=(*scalars, link.link_scalar),
                weight=link.weight,
            )
            settled[target] = reached
            reached_by.setdefault(event_id, set()).add(target)
            frontier.append(
                (target, depth + 1, reached.link_scalars, (*route, target), link.weight)
            )
    for event_id, children in reached_by.items():
        if event_id in settled:
            settled[event_id].reached_ids = children
    if capped and node_cap is not None:
        truncations.append(
            TruncationRecord(
                reason=TruncationReason.NODE_CAP,
                at_event_id=seed_event_id,
                depth=0,
                detail=(
                    f"the declared traversal_node_cap of {node_cap} was reached. Which "
                    "consequences were left out follows the canonical visit sequence and is "
                    "reproducible, but it is still an arbitrary subset of a larger truth: "
                    "every figure in this report is a lower bound."
                ),
            )
        )
    return settled, tuple(sorted(truncations, key=lambda record: record.sort_key()))


def reachable_from(
    seed_event_id: str,
    context: PropagationContext,
    *,
    excluding: frozenset[str] = frozenset(),
) -> frozenset[str]:
    """Return the consequences reachable from a seed, with the excluded nodes deleted.

    The primitive behind counterfactual-lite reasoning. `excluding` removes those nodes
    **and every link through them**, so what the caller gets back is what the graph still
    says happens once they are gone -- not the same set minus those members. A consequence
    with another surviving cause stays in the set, which is precisely the diamond case a
    subtraction would get wrong.

    A SET rather than a single identifier because a joint cause group is removed as a unit:
    removing its members one at a time and intersecting the results is a different and wrong
    computation, since a consequence held up by two members of one group survives each
    single removal and survives neither removal of the group.

    Bounded by the same declared depth the full walk honours, so the two are comparable. The
    node cap is deliberately NOT applied here: this set is a membership test rather than a
    report, its members carry no magnitude reading, and a cap would make the counterfactual
    answer depend on where an unrelated bound happened to fall.
    """
    bound = effective_depth_bound(context)
    if bound is None or seed_event_id in excluding:
        return frozenset()
    seen: set[str] = set()
    frontier: list[tuple[str, int]] = [(seed_event_id, 0)]
    while frontier:
        event_id, depth = frontier.pop(0)
        if depth >= bound:
            continue
        for link in context.view.links_from(event_id):
            target = link.target_event_id
            if target in excluding or target in seen:
                continue
            seen.add(target)
            frontier.append((target, depth + 1))
    return frozenset(seen)


def links_along_route(route: tuple[str, ...], context: PropagationContext) -> tuple[GraphLink, ...]:
    """Return the strongest link joining each consecutive pair on one route.

    A multigraph admits several links over one pair -- one per claim kind -- and a route
    names nodes rather than links. The strongest is taken, and the choice is stated rather
    than left implicit: taking the weakest would let a claim the engine barely makes decide
    the confidence of a route it also makes strongly, and averaging would blend two
    assertions about different relations into one number about neither.
    """
    chosen: list[GraphLink] = []
    for source, target in pairwise(route):
        candidates = [
            link for link in context.view.links_from(source) if link.target_event_id == target
        ]
        if not candidates:
            continue
        chosen.append(max(candidates, key=lambda link: (link.link_scalar, link.edge_kind)))
    return tuple(chosen)
