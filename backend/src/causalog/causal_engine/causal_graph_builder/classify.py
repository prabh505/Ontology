"""Edge typing against prd.md §26, and the grouping of joint causes (ADR-0054).

**This module verifies a type; it does not invent one.** The §26 category already rides in
`CausalEdge.payload` -- module 9 built the payload from the firing rule or from the
structural claim its generator was making, and the kind participates in the edge's content
address. Re-deciding it here would move that address and would mean two modules disagreeing
about what one artifact is.

What this module adds is the *basis*: on whose authority the edge carries that kind. Three
answers, and the distinction between them is a coverage statement about the rule pack rather
than a property of the claim:

* `RULE_DECLARED` -- a rule fired over this pair and its `RuleKind` names this category.
* `STRUCTURAL` -- no rule named the pair; a generator's structural claim produced the kind.
* `UNTYPED_DEFAULT` -- the kind is `DIRECT` and nothing qualified it. Not evidence of
  directness; evidence that nothing said otherwise.

**Disagreements are recorded and not resolved** (the ADR-0051 idiom). A firing whose kind
differs from the payload's is reported on the edge, in both directions, and the payload's
kind stands because it is the one in the address.

**Joint causes are grouped, not counted.** A `CONTRIBUTING` payload names its
`joint_cause_group_id` and its co-causes; this module assembles the group so that promotion
can be all-or-nothing. prd.md §26's contributing cause is conjunctive -- several causes
*jointly* produce the outcome -- and promoting two of three members would tell module 13's
counterfactual surgery that removing either one prevents the effect, which is the opposite
of what the group asserts.

No domain vocabulary appears here: every type, kind and identifier arrives as a string.
"""

from __future__ import annotations

from causalog.causal_engine.causal_graph_builder.graph import (
    JointCauseGroup,
    TypingBasis,
    TypingRecord,
)
from causalog.causal_engine.confidence_scorer import ScoredEdge
from causalog.core.types.causal_edge import CausalEdgeKind, ContributingCause
from causalog.rule_engine import EvaluationResult, RuleKind

__all__ = ["RULE_KIND_TO_EDGE_KIND", "group_joint_causes", "type_edge"]

#: The one mapping between the rule vocabulary and the edge vocabulary. Both are closed sets
#: modelling prd.md §26, and `RuleKind`'s own docstring says the first five mirror the
#: payload union deliberately -- "one vocabulary for the five categories, not a second,
#: weaker one made of strings". This table is where that mirroring is checked rather than
#: assumed, and a member added to either enum without the other fails the test that walks it.
#:
#: `CONSTRAINT` is absent and its absence is the point: a constraint produces a PROHIBITION,
#: not a claim. It prunes a candidate upstream in module 9 and has no edge counterpart, so
#: mapping it to one would make impossibility rankable.
RULE_KIND_TO_EDGE_KIND: dict[RuleKind, CausalEdgeKind] = {
    RuleKind.CAUSAL: CausalEdgeKind.DIRECT,
    RuleKind.CONDITIONAL: CausalEdgeKind.CONDITIONAL,
    RuleKind.JOINT: CausalEdgeKind.CONTRIBUTING,
    RuleKind.AMPLIFICATION: CausalEdgeKind.AMPLIFYING,
    RuleKind.INHIBITION: CausalEdgeKind.INHIBITING,
}


def _firings_over(
    source_event_id: str, target_event_id: str, evaluation: EvaluationResult
) -> tuple[tuple[str, RuleKind], ...]:
    """Return every firing that matched both events, as (rule_id, rule_kind), sorted.

    Membership of `matched_event_ids` rather than a binding lookup: a firing's bindings name
    roles the rule chose, and a joint rule binds three contributors under three labels, so
    asking "did this rule match both of these events" is the question that has one answer
    for every rule kind. It is a weaker claim than "this rule asserted this directed pair",
    and the weaker claim is the one that is true -- which is why the basis it produces is
    reported as a rule DECLARATION about the pair and not as a proof of direction.
    """
    found = {
        (firing.rule_id, firing.rule_kind)
        for firing in evaluation.firings
        if source_event_id in firing.matched_event_ids
        and target_event_id in firing.matched_event_ids
    }
    return tuple(sorted(found, key=lambda entry: entry[0]))


def type_edge(scored: ScoredEdge, evaluation: EvaluationResult | None) -> TypingRecord:
    """Return the typing record for one scored claim.

    `evaluation is None` means no rule metadata was supplied at all. Every edge is then
    typed structurally, and the graph quality report says so -- rather than the run reading
    as though every edge had been checked against the pack and found unmentioned, which is
    the DEF-0001 shape.
    """
    kind = scored.edge.payload.edge_kind
    if evaluation is None:
        return TypingRecord(
            edge_kind=kind.value,
            basis=(
                TypingBasis.UNTYPED_DEFAULT
                if kind is CausalEdgeKind.DIRECT
                else TypingBasis.STRUCTURAL
            ),
        )

    firings = _firings_over(scored.edge.source_event_id, scored.edge.target_event_id, evaluation)
    if not firings:
        return TypingRecord(
            edge_kind=kind.value,
            basis=(
                TypingBasis.UNTYPED_DEFAULT
                if kind is CausalEdgeKind.DIRECT
                else TypingBasis.STRUCTURAL
            ),
        )

    agreeing = tuple(
        rule_id for rule_id, rule_kind in firings if RULE_KIND_TO_EDGE_KIND.get(rule_kind) is kind
    )
    disagreements = tuple(
        sorted(
            f"rule {rule_id} fired over this pair as {rule_kind.value}, which is the "
            f"{RULE_KIND_TO_EDGE_KIND[rule_kind].value} category, while the edge carries "
            f"{kind.value}. The edge's kind stands because it is in its content address; "
            "the disagreement is recorded and resolved by nobody."
            for rule_id, rule_kind in firings
            if rule_kind in RULE_KIND_TO_EDGE_KIND and RULE_KIND_TO_EDGE_KIND[rule_kind] is not kind
        )
    )
    if not agreeing:
        return TypingRecord(
            edge_kind=kind.value,
            basis=TypingBasis.STRUCTURAL,
            disagreements=disagreements,
        )
    return TypingRecord(
        edge_kind=kind.value,
        basis=TypingBasis.RULE_DECLARED,
        supporting_rule_ids=tuple(sorted(set(agreeing))),
        disagreements=disagreements,
    )


def group_joint_causes(edges: tuple[ScoredEdge, ...]) -> tuple[JointCauseGroup, ...]:
    """Assemble every joint cause group present among the scored claims.

    Keyed on `(target_event_id, joint_cause_group_id)`: one group identifier may legitimately
    be reused across process instances, and two instances' groups are two groups. Membership
    is taken from the payloads' own `co_cause_event_ids` UNION the sources actually present,
    so a group whose co-cause was never scored is visible as a group whose declared
    membership exceeds what the graph holds -- which is the case all-or-nothing promotion has
    to refuse.

    `promoted` is `False` on every group returned here. It is decided in `select.py`, which
    is the module that knows which members cleared their threshold; setting it here would
    put the decision in two places.
    """
    declared: dict[tuple[str, str], set[str]] = {}
    present: dict[tuple[str, str], set[str]] = {}
    for scored in edges:
        payload = scored.edge.payload
        if not isinstance(payload, ContributingCause):
            continue
        key = (scored.edge.target_event_id, payload.joint_cause_group_id)
        declared.setdefault(key, set()).update(payload.co_cause_event_ids)
        declared[key].add(scored.edge.source_event_id)
        present.setdefault(key, set()).add(scored.edge.source_event_id)

    groups: list[JointCauseGroup] = []
    for (target, group_id), members in sorted(declared.items()):
        held = present.get((target, group_id), set())
        missing = sorted(members - held)
        detail = (
            f"{len(held)} of {len(members)} declared contributor(s) are present as scored "
            "claims over this effect."
        )
        if missing:
            detail += (
                f" Absent: {missing}. A group whose declared membership exceeds what the "
                "graph holds cannot be promoted: asserting the contributors that ARE "
                "present would state that they jointly suffice, which is precisely what a "
                "group with a missing member does not say."
            )
        groups.append(
            JointCauseGroup(
                joint_cause_group_id=group_id,
                target_event_id=target,
                member_source_event_ids=tuple(sorted(members)),
                promoted=False,
                detail=detail,
            )
        )
    return tuple(groups)
