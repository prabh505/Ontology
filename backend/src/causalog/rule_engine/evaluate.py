"""Deterministic evaluation of a rule pack over observed facts.

What this module does, in sequence:

1. Build the indexes (`index.py`), once.
2. Evaluate every enabled constraint, producing prohibitions.
3. Evaluate every enabled generating rule, producing firings with full traces.
4. Apply the precedence policy (`conflict.py`): constraints beat generators, and every
   suppression is reported rather than silently applied.

What this module deliberately does NOT do
------------------------------------------
**It does not create a causal edge.** `docs/architecture.md` §Module 9 gives the Candidate
Cause Generator (L6) the LAW-TIME gate and `CausalEdge` construction, and the §6.2 sequence
diagram has this layer handing it fired rule identifiers. This module stamps the temporal
verdict onto each firing and stops.

**It does not assign confidence.** `base_strength` travels with a firing as the rule's
authored weight; assembling named components into a `ConfidenceVector` is module 10's job
and needs evidence this layer does not hold.

**It does not read `Event.trigger`.** ADR-0020 forbids it: an `OBSERVED` mechanism recorded
on an event may not become an unscored causal claim by being matched on. The field is never
read here, and `tests/law/` asserts it.

**It does not suppress an `UNDETERMINED` verdict.** A pair whose intervals overlap is a
finding about the dataset, kept and flagged, never tuned away by loosening the test
(`CONTEXT.md` R-14). Only `VIOLATION` pairs are dropped, and their count is reported.

Determinism
-----------
Every collection is walked in a canonical sequence and the output is sorted before it is
returned, so two evaluations over the same facts produce byte-identical firings regardless
of the sequence the caller assembled its inputs in (`CONVENTIONS.md` §11).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from causalog.core.temporal import TemporalVerdict, TimeInterval, is_unverifiable, verdict
from causalog.core.types import Event
from causalog.rule_engine.conflict import ConflictFinding, ConflictReport
from causalog.rule_engine.dsl import (
    CausalBody,
    ConditionExpression,
    ConditionOperator,
    ConstraintBody,
    EntityRelation,
    JointBody,
    ModifierBody,
    RelationDirection,
    Rule,
    RulePackSpec,
    TemporalWindow,
)
from causalog.rule_engine.facts import GraphFacts
from causalog.rule_engine.index import FactIndex, build_index
from causalog.rule_engine.trace import ConditionTraceEntry, RuleFiring, WindowObservation

__all__ = ["EvaluationResult", "EvaluationStatistics", "evaluate"]


class EvaluationStatistics(BaseModel):
    """What the evaluation cost and what it refused, as data rather than as a log line.

    `pair_comparisons` is the counter the complexity bound is asserted against
    (`tests/unit/rule_engine/test_complexity_bound.py`). It is returned rather than kept
    internal so the claim in `index.py`'s docstring is inspectable in a real run and not
    only under test -- a bound nobody can measure in production is a bound nobody can
    notice breaking.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    events_examined: int
    rules_evaluated: int
    pair_comparisons: int
    firings_emitted: int
    #: Pairs the LAW-TIME test rejected. Never emitted, always counted -- a large value is a
    #: finding about the pack's windows, not a number to hide.
    temporal_violations_refused: int
    #: Firings retained with an `UNDETERMINED` verdict. Reported per `CONTEXT.md` R-14: if
    #: this dominates, that is a finding about the dataset's granularity.
    undetermined_firings: int
    #: Firings whose events carry no placed interval at all. Distinct from `UNDETERMINED`
    #: (`docs/contracts.md` §3): the data never placed one of them, rather than placed both
    #: and failed to separate them.
    unverifiable_firings: int
    conditions_evaluated: int


class EvaluationResult(BaseModel):
    """Everything one evaluation produced: what fired, what was suppressed, what it cost."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    firings: tuple[RuleFiring, ...]
    conflicts: ConflictReport
    statistics: EvaluationStatistics

    def firings_of(self, rule_id: str) -> tuple[RuleFiring, ...]:
        """Return every firing one rule produced, in canonical sequence."""
        return tuple(firing for firing in self.firings if firing.rule_id == rule_id)

    def fired_rule_ids(self) -> tuple[str, ...]:
        """Return every rule that fired at least once, sorted and without repeats."""
        return tuple(sorted({firing.rule_id for firing in self.firings}))


@dataclass
class _Counters:
    """Mutable tallies, folded into the frozen statistics at the end."""

    pair_comparisons: int = 0
    temporal_violations_refused: int = 0
    conditions_evaluated: int = 0


@dataclass(frozen=True)
class _Prohibition:
    """One constraint that fired: which entity, which type it may not participate in."""

    constraint_rule_id: str
    entity_id: str
    forbidden_event_type: str
    bindings: tuple[tuple[str, str], ...]


@dataclass
class _Match:
    """One candidate binding of a rule, before its conditions are evaluated."""

    bound_events: dict[str, Event]
    bindings: dict[str, str]
    window: WindowObservation | None = None
    temporal_verdict: TemporalVerdict = TemporalVerdict.CERTAIN
    unverifiable: bool = False
    entity_bindings: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------


def _attribute_value(event: Event, attribute: str) -> str | None:
    """Return an attribute's value from an event, or None if the event does not carry it.

    Reads `changed_attributes` first and `metadata` second, because a changed value is the
    one the occurrence asserts and a metadata value is context carried alongside it. Both
    are sorted pair tuples on a frozen type, so this is a scan over a small fixed list and
    not worth an index.

    `None` means **absent**, and is deliberately distinguishable from an empty string. An
    evaluator that collapsed the two would make `IS_ABSENT` untestable.
    """
    for name, value in event.changed_attributes:
        if name == attribute:
            return value
    for name, value in event.metadata:
        if name == attribute:
            return value
    return None


def _resolve(expression: ConditionExpression, match: _Match) -> str | None:
    """Return the value an ATTRIBUTE or CONSTANT leaf denotes under this match."""
    if expression.op is ConditionOperator.CONSTANT:
        return expression.value
    address = expression.address
    if address is None:
        return None
    event = match.bound_events.get(address.binding)
    if event is None:
        return None
    return _attribute_value(event, address.attribute)


def _compare(operator: ConditionOperator, left: str | None, right: str | None) -> bool:
    """Apply one comparison operator to two resolved values.

    An absent operand makes every comparison **false**, including `NOT_EQUALS`. That is the
    conservative reading and the deliberate one: "these two differ" is a claim, and a claim
    about a value nobody recorded is not supported by the absence. Use `IS_ABSENT` to test
    for absence; that is what it is for.

    `GREATER_THAN` and `LESS_THAN` compare numerically and return false when either side is
    not a number. Attribute values arrive as text, and inferring which strings are numbers
    from their content is how two evaluations come to disagree about `"10" > "9"`.
    """
    if left is None or right is None:
        return False
    if operator is ConditionOperator.EQUALS:
        return left == right
    if operator is ConditionOperator.NOT_EQUALS:
        return left != right
    try:
        left_number = float(left)
        right_number = float(right)
    except ValueError:
        return False
    if operator is ConditionOperator.GREATER_THAN:
        return left_number > right_number
    return left_number < right_number


def _evaluate_condition(
    expression: ConditionExpression,
    match: _Match,
    path: str,
    trace: list[ConditionTraceEntry],
    counters: _Counters,
) -> bool:
    """Evaluate one condition subtree, appending a trace entry for every node visited.

    **Every visited node is traced, including one whose value did not change the outcome.**
    Short-circuiting the evaluation would be faster and would produce a trace that cannot be
    checked: a reader seeing three of five operands cannot tell whether the other two were
    false or were never looked at. The cost is bounded by the tree's size, which a pack
    author controls.
    """
    counters.conditions_evaluated += 1

    if expression.op is ConditionOperator.ALWAYS:
        return True

    if expression.op is ConditionOperator.ATTRIBUTE:
        observed = _resolve(expression, match)
        trace.append(
            ConditionTraceEntry(
                path=path,
                operator=expression.op,
                address="" if expression.address is None else expression.address.rendered(),
                observed=observed,
                result=observed is not None,
            )
        )
        return observed is not None

    if expression.op is ConditionOperator.CONSTANT:
        trace.append(
            ConditionTraceEntry(
                path=path,
                operator=expression.op,
                observed=expression.value,
                result=True,
            )
        )
        return True

    if expression.op in (
        ConditionOperator.EQUALS,
        ConditionOperator.NOT_EQUALS,
        ConditionOperator.GREATER_THAN,
        ConditionOperator.LESS_THAN,
    ):
        left = _resolve(expression.operands[0], match)
        right = _resolve(expression.operands[1], match)
        result = _compare(expression.op, left, right)
        trace.append(
            ConditionTraceEntry(
                path=path,
                operator=expression.op,
                address=_render_operands(expression),
                observed=f"{left!r} vs {right!r}",
                result=result,
            )
        )
        return result

    if expression.op is ConditionOperator.IN:
        observed = _resolve(expression.operands[0], match)
        result = observed is not None and observed in expression.values
        trace.append(
            ConditionTraceEntry(
                path=path,
                operator=expression.op,
                address=_render_operands(expression),
                observed=observed,
                result=result,
            )
        )
        return result

    if expression.op in (ConditionOperator.IS_PRESENT, ConditionOperator.IS_ABSENT):
        observed = _resolve(expression.operands[0], match)
        present = observed is not None
        result = present if expression.op is ConditionOperator.IS_PRESENT else not present
        trace.append(
            ConditionTraceEntry(
                path=path,
                operator=expression.op,
                address=_render_operands(expression),
                observed=observed,
                result=result,
            )
        )
        return result

    if expression.op is ConditionOperator.NOT:
        inner = _evaluate_condition(
            expression.operands[0], match, f"{path}.operands[0]", trace, counters
        )
        result = not inner
        trace.append(ConditionTraceEntry(path=path, operator=expression.op, result=result))
        return result

    outcomes = [
        _evaluate_condition(operand, match, f"{path}.operands[{position}]", trace, counters)
        for position, operand in enumerate(expression.operands)
    ]
    result = all(outcomes) if expression.op is ConditionOperator.AND else any(outcomes)
    trace.append(ConditionTraceEntry(path=path, operator=expression.op, result=result))
    return result


def _render_operands(expression: ConditionExpression) -> str:
    """Return the addresses a comparison node read, for its trace entry."""
    return " ".join(
        operand.address.rendered() for operand in expression.operands if operand.address is not None
    )


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def _participants(event: Event) -> tuple[str, ...]:
    """Return every entity the event names, sorted and without repeats."""
    return tuple(sorted(set(event.source_entity_ids) | set(event.target_entity_ids)))


def _linked(
    cause: Event, effect: Event, relation: EntityRelation, index: FactIndex
) -> tuple[str, str] | None:
    """Return the two entities that satisfy the linkage, or None if none do.

    Deterministic: candidates are walked in sorted sequence and the first satisfying pair is
    returned, so two evaluations over the same facts pick the same pair.

    **What this checks, and what it does not.** Roles are ontology declarations and an
    `Event` does not carry them: it carries `source_entity_ids` and `target_entity_ids`
    (`docs/contracts.md` §5). So the linkage is tested over the participants the two events
    actually name, not over the specific roles the rule labelled them with. A rule whose two
    roles were transposed is therefore admitted here if the entities are related at all; the
    loader's `RUL-E-UNDECLARED-ROLE` check is what catches a role that could never resolve.
    Stated rather than papered over -- it is a real gap between what a rule says and what
    this layer can verify, and closing it needs role-tagged participants on `Event`, which
    is a frozen type and a separate ADR.
    """
    cause_entities = _participants(cause)
    effect_entities = set(_participants(effect))

    if relation.direction is RelationDirection.SHARED_PARTICIPANT:
        for entity_id in cause_entities:
            if entity_id in effect_entities:
                return (entity_id, entity_id)
        return None

    kind = relation.relationship_type
    if kind is None:
        return None
    for entity_id in cause_entities:
        for neighbour in index.neighbours(entity_id, kind, relation.direction):
            if neighbour in effect_entities:
                return (entity_id, neighbour)
    return None


def _separation(cause: TimeInterval, effect: TimeInterval) -> tuple[int, int]:
    """Return the minimum and maximum seconds that could separate two intervals.

    Bounds, not a point. Collapsing an interval for computation is a defect
    (`CONVENTIONS.md` §10), and a midpoint here would let a rule with a tight window match a
    pair whose true separation the data never pinned down.
    """
    minimum = (effect.t_earliest - cause.t_latest).total_seconds()
    maximum = (effect.t_latest - cause.t_earliest).total_seconds()
    return (int(minimum), int(maximum))


def _within(window: TemporalWindow, minimum: int, maximum: int) -> bool:
    """Return whether an observed separation range overlaps the authored window.

    Overlap, not containment. The observed range is an uncertainty band; requiring it to sit
    wholly inside the window would reject every day-granularity pair on a dataset whose
    timestamps are day-granularity, which is this dataset (ADR-0007). The boundary flags are
    honoured on the ends they apply to.
    """
    if window.maximum_inclusive:
        if minimum > window.maximum_seconds:
            return False
    elif minimum >= window.maximum_seconds:
        return False
    if window.minimum_inclusive:
        if maximum < window.minimum_seconds:
            return False
    elif maximum <= window.minimum_seconds:
        return False
    return True


# ---------------------------------------------------------------------------
# Rule evaluation
# ---------------------------------------------------------------------------


def _pair_matches(body: CausalBody, index: FactIndex, counters: _Counters) -> list[_Match]:
    """Return every admissible (antecedent, consequent) binding of a two-event rule.

    This is where the complexity bound lives. The antecedent bucket is walked once; for each
    member the consequent bucket is **bisected** by the window's lower bound before any pair
    is examined, so the pairs actually compared are bounded by the window and the linkage
    rather than by the size of the consequent bucket.
    """
    matches: list[_Match] = []
    causes = index.of_type(body.cause.event_type)
    for cause in causes:
        candidates, refused = index.admissible_slice(
            body.effect.event_type,
            cause.occurred_at.t_earliest,
            cause.occurred_at.t_latest,
            body.window.maximum_seconds,
        )
        # Exact, not sampled: the cut removes all and only the LAW-TIME violations, so the
        # count is right without examining a single one of them.
        counters.temporal_violations_refused += refused
        for effect in candidates:
            if effect.event_id == cause.event_id:
                continue
            counters.pair_comparisons += 1

            # LAW-TIME first, so a reversed pair is counted as refused by the law rather
            # than dismissed as merely outside the window. The two exclusions overlap and
            # the statistic must not depend on which test happened to run first.
            outcome = verdict(cause.occurred_at, effect.occurred_at)
            if outcome is TemporalVerdict.VIOLATION:
                counters.temporal_violations_refused += 1
                continue

            minimum, maximum = _separation(cause.occurred_at, effect.occurred_at)
            if not _within(body.window, minimum, maximum):
                continue

            linkage = _linked(cause, effect, body.relation, index)
            if linkage is None:
                continue

            matches.append(
                _Match(
                    bound_events={
                        body.cause.binding: cause,
                        body.effect.binding: effect,
                    },
                    bindings={
                        body.cause.binding: cause.event_id,
                        body.effect.binding: effect.event_id,
                    },
                    window=WindowObservation(
                        minimum_separation_seconds=minimum,
                        maximum_separation_seconds=maximum,
                        window_minimum_seconds=body.window.minimum_seconds,
                        window_maximum_seconds=body.window.maximum_seconds,
                    ),
                    temporal_verdict=outcome,
                    unverifiable=(
                        is_unverifiable(cause.occurred_at) or is_unverifiable(effect.occurred_at)
                    ),
                    entity_bindings={
                        body.relation.cause_role: linkage[0],
                        body.relation.effect_role: linkage[1],
                    },
                )
            )
    return matches


def _joint_matches(body: JointBody, index: FactIndex, counters: _Counters) -> list[_Match]:
    """Return every binding where EVERY contributor is linked to one consequent.

    Conjunctive: a consequent with three of four contributors present produces nothing. That
    is what `ContributingCause` means -- "several causes JOINTLY produce an outcome"
    (prd.md §26) -- and emitting a partial group would turn a joint claim into a set of weak
    direct ones nobody authored.

    Driven from the consequent rather than from the contributors, because the consequent is
    the thing being explained and it is the only member all contributors must link to. The
    contributor buckets are bisected the same way the pair case bisects.
    """
    matches: list[_Match] = []
    for effect in index.of_type(body.effect.event_type):
        bound: dict[str, Event] = {}
        entity_bindings: dict[str, str] = {}
        separations: list[tuple[int, int]] = []
        outcome = TemporalVerdict.CERTAIN
        unverifiable = False

        for contributor in body.contributors:
            chosen: Event | None = None
            for candidate in index.of_type(contributor.event_type):
                if candidate.event_id == effect.event_id:
                    continue
                counters.pair_comparisons += 1
                minimum, maximum = _separation(candidate.occurred_at, effect.occurred_at)
                if not _within(body.window, minimum, maximum):
                    continue
                linkage = _linked(candidate, effect, body.relation, index)
                if linkage is None:
                    continue
                candidate_verdict = verdict(candidate.occurred_at, effect.occurred_at)
                if candidate_verdict is TemporalVerdict.VIOLATION:
                    counters.temporal_violations_refused += 1
                    continue
                chosen = candidate
                separations.append((minimum, maximum))
                entity_bindings[body.relation.cause_role] = linkage[0]
                entity_bindings[body.relation.effect_role] = linkage[1]
                if candidate_verdict is TemporalVerdict.UNDETERMINED:
                    outcome = TemporalVerdict.UNDETERMINED
                unverifiable = unverifiable or is_unverifiable(candidate.occurred_at)
                break
            if chosen is None:
                bound = {}
                break
            bound[contributor.binding] = chosen

        if not bound:
            continue

        bound[body.effect.binding] = effect
        unverifiable = unverifiable or is_unverifiable(effect.occurred_at)
        matches.append(
            _Match(
                bound_events=bound,
                bindings={label: event.event_id for label, event in bound.items()},
                window=WindowObservation(
                    minimum_separation_seconds=min(pair[0] for pair in separations),
                    maximum_separation_seconds=max(pair[1] for pair in separations),
                    window_minimum_seconds=body.window.minimum_seconds,
                    window_maximum_seconds=body.window.maximum_seconds,
                ),
                temporal_verdict=outcome,
                unverifiable=unverifiable,
                entity_bindings=entity_bindings,
            )
        )
    return matches


def _modifier_matches(rule: Rule, index: FactIndex, counters: _Counters) -> list[_Match]:
    """Return every occurrence of a modifier's own pattern.

    A modifier does not pair two events; it observes one and rescales another rule's claim
    over the entities that one names. Pairing it against its target's matches here would
    duplicate the target rule's work and would put the two rules' windows in conflict with
    no stated resolution.
    """
    body = rule.body
    if not isinstance(body, ModifierBody):
        return []
    modifier = body.modifier
    matches: list[_Match] = []
    for event in index.of_type(modifier.event_type):
        counters.pair_comparisons += 1
        matches.append(
            _Match(
                bound_events={modifier.binding: event},
                bindings={modifier.binding: event.event_id},
                temporal_verdict=TemporalVerdict.CERTAIN,
                unverifiable=is_unverifiable(event.occurred_at),
                entity_bindings=_first_participant_binding(body.relation.cause_role, event),
            )
        )
    return matches


def _first_participant_binding(role: str, event: Event) -> dict[str, str]:
    """Bind `role` to the event's first participant, or to nothing when it names none.

    A modifier observes one event and rescales another rule's claim over the entities that
    event names. The first participant in canonical sequence is the deterministic choice;
    an event naming no participant binds nothing rather than binding an empty identifier.
    """
    participants = _participants(event)
    return {role: participants[0]} if participants else {}


def _fire(rule: Rule, pack: RulePackSpec, match: _Match, counters: _Counters) -> RuleFiring | None:
    """Evaluate a match's conditions and, if they hold, build the traced firing.

    Returns `None` when the conditions do not hold. A rule that did not fire produces no
    firing and no trace -- the trace exists to justify a claim, and there is no claim.
    """
    condition = rule.conditions()
    trivial = condition.is_trivial()
    trace: list[ConditionTraceEntry] = []
    if not _evaluate_condition(condition, match, "root", trace, counters):
        return None

    body = rule.body
    return RuleFiring(
        rule_id=rule.id,
        rule_kind=rule.kind,
        rule_pack_version=pack.rule_pack_version,
        knowledge_provenance=rule.knowledge_provenance,
        bindings=tuple(sorted(match.bindings.items())),
        matched_event_ids=tuple(sorted(match.bindings.values())),
        evaluated_conditions=tuple(trace),
        condition_was_trivial=trivial,
        window_observed=match.window,
        temporal_verdict=match.temporal_verdict,
        temporally_unverifiable=match.unverifiable,
        base_strength=rule.base_strength,
        modifies_rule_id=body.modifies if isinstance(body, ModifierBody) else None,
        magnitude_multiplier=(
            body.magnitude_multiplier if isinstance(body, ModifierBody) else None
        ),
    )


def _prohibitions(
    pack: RulePackSpec, index: FactIndex, counters: _Counters
) -> tuple[tuple[_Prohibition, ...], tuple[RuleFiring, ...]]:
    """Evaluate every enabled constraint, returning its prohibitions and its own firings.

    A constraint fires over the STATES the facts carry, not over event pairs: it says an
    entity in a named state cannot participate in a named event type. Its own firings are
    returned alongside the prohibitions, because a constraint that fired is a rule that
    fired and it owes the same trace every other rule owes.
    """
    prohibitions: list[_Prohibition] = []
    firings: list[RuleFiring] = []

    for rule in pack.enabled_rules():
        body = rule.body
        if not isinstance(body, ConstraintBody):
            continue
        for entity_id, states in sorted(index.states_of.items()):
            for state in states:
                if state.state_name != body.subject_state:
                    continue
                counters.pair_comparisons += 1
                event = index.events_by_id.get(state.derived_from_event_id)
                if event is None:
                    continue
                match = _Match(
                    bound_events={"SUBJECT": event},
                    bindings={"SUBJECT": event.event_id},
                    temporal_verdict=TemporalVerdict.CERTAIN,
                    unverifiable=is_unverifiable(event.occurred_at),
                    entity_bindings={body.subject_role: entity_id},
                )
                firing = _fire(rule, pack, match, counters)
                if firing is None:
                    continue
                firings.append(firing)
                if body.forbidden_event_type is not None:
                    prohibitions.append(
                        _Prohibition(
                            constraint_rule_id=rule.id,
                            entity_id=entity_id,
                            forbidden_event_type=body.forbidden_event_type,
                            bindings=firing.bindings,
                        )
                    )
                break
    return tuple(prohibitions), tuple(firings)


def _consequent_event_type(rule: Rule) -> str | None:
    """Return the event type a generating rule proposes as its consequent, if any."""
    body = rule.body
    if isinstance(body, CausalBody):
        return body.effect.event_type
    if isinstance(body, JointBody):
        return body.effect.event_type
    return None


def evaluate(pack: RulePackSpec, facts: GraphFacts) -> EvaluationResult:
    """Evaluate one rule pack over one set of facts. Deterministic, indexed, fully traced.

    The precedence policy is applied last and its every application is reported (ADR-0047):
    a firing suppressed by a constraint appears in `EvaluationResult.conflicts`, never
    merely absent from `EvaluationResult.firings`.
    """
    index = build_index(facts)
    counters = _Counters()
    prohibitions, constraint_firings = _prohibitions(pack, index, counters)

    generated: list[RuleFiring] = []
    rules_evaluated = 0

    for rule in pack.enabled_rules():
        body = rule.body
        if isinstance(body, ConstraintBody):
            rules_evaluated += 1
            continue
        rules_evaluated += 1

        if isinstance(body, CausalBody):
            matches = _pair_matches(body, index, counters)
        elif isinstance(body, JointBody):
            matches = _joint_matches(body, index, counters)
        else:
            matches = _modifier_matches(rule, index, counters)

        for match in matches:
            firing = _fire(rule, pack, match, counters)
            if firing is not None:
                generated.append(firing)

    surviving, conflicts = _apply_precedence(pack, generated, prohibitions, index)
    firings = tuple(
        sorted(
            [*constraint_firings, *surviving],
            key=lambda item: (item.rule_id, item.matched_event_ids, item.bindings),
        )
    )

    undetermined = sum(
        1 for firing in firings if firing.temporal_verdict is TemporalVerdict.UNDETERMINED
    )
    unverifiable = sum(1 for firing in firings if firing.temporally_unverifiable)

    return EvaluationResult(
        firings=firings,
        conflicts=conflicts,
        statistics=EvaluationStatistics(
            events_examined=len(facts.events()),
            rules_evaluated=rules_evaluated,
            pair_comparisons=counters.pair_comparisons,
            firings_emitted=len(firings),
            temporal_violations_refused=counters.temporal_violations_refused,
            undetermined_firings=undetermined,
            unverifiable_firings=unverifiable,
            conditions_evaluated=counters.conditions_evaluated,
        ),
    )


def _apply_precedence(
    pack: RulePackSpec,
    generated: list[RuleFiring],
    prohibitions: tuple[_Prohibition, ...],
    index: FactIndex,
) -> tuple[list[RuleFiring], ConflictReport]:
    """Apply `constraints beat generators`, reporting every suppression (ADR-0047).

    A generated firing is suppressed when a constraint prohibits the firing's consequent
    event type for an entity that consequent event names. The check is over the entities the
    consequent event actually names, which is the linkage the constraint's subject role
    resolves through.
    """
    by_id = {rule.id: rule for rule in pack.rules}
    blocked: dict[tuple[str, str], _Prohibition] = {
        (item.entity_id, item.forbidden_event_type): item for item in prohibitions
    }
    if not blocked:
        return list(generated), ConflictReport()

    surviving: list[RuleFiring] = []
    findings: list[ConflictFinding] = []

    for firing in generated:
        rule = by_id[firing.rule_id]
        consequent_type = _consequent_event_type(rule)
        if consequent_type is None:
            surviving.append(firing)
            continue

        prohibition: _Prohibition | None = None
        for event_id in firing.matched_event_ids:
            event = index.events_by_id.get(event_id)
            if event is None or event.event_type != consequent_type:
                continue
            for entity_id in _participants(event):
                found = blocked.get((entity_id, consequent_type))
                if found is not None:
                    prohibition = found
                    break
            if prohibition is not None:
                break

        if prohibition is None:
            surviving.append(firing)
            continue

        findings.append(
            ConflictFinding(
                suppressed_rule_id=firing.rule_id,
                constraint_rule_id=prohibition.constraint_rule_id,
                shared_bindings=firing.bindings,
                suppressed_firing=firing,
            )
        )

    findings.sort(
        key=lambda item: (
            item.constraint_rule_id,
            item.suppressed_rule_id,
            item.shared_bindings,
        )
    )
    return surviving, ConflictReport(findings=tuple(findings))
