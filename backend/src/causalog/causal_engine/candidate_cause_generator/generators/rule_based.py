"""Generator (b): an explicit rule in the active pack fired.

The strongest of the seven, and the only one whose weight it does not have to be told:
a firing carries the rule's own authored `base_strength`, and a firing carries its whole
condition trace, so the evidence this generator produces is re-verifiable by reading the
pack rather than by re-running the engine.

This generator does not evaluate anything. `rule_engine.evaluate` already did, in L5, and
already stamped the LAW-TIME verdict onto every firing. What happens here is a translation:
a `RuleFiring` becomes one or more `Proposal`s, with the firing's `RuleKind` selecting the
payload type. The two vocabularies were built to line up (ADR-0044: "one vocabulary for the
five categories, not a second, weaker one made of strings"), so the translation is total and
has no default branch.

**`CONSTRAINT` firings never arrive here.** A constraint prunes rather than proposes, and
`rule_engine.evaluate` has already applied the precedence policy and reported every
suppression. This module reads that report and counts the suppressions; it does not re-apply
them, which would double-count.
"""

from __future__ import annotations

from causalog.causal_engine.candidate_cause_generator.context import (
    GenerationContext,
    GeneratorStatus,
    Proposal,
)
from causalog.causal_engine.candidate_cause_generator.generators.support import evidence_item
from causalog.core.errors import ContractViolationError
from causalog.core.provenance import ProvenanceClass
from causalog.core.types import (
    AmplifyingCause,
    ConditionalCause,
    ContributingCause,
    DirectCause,
    Event,
    EvidenceKind,
)
from causalog.core.types.causal_edge import InhibitingCause
from causalog.rule_engine import RuleFiring, RuleKind

__all__ = ["RuleBasedGenerator"]

#: The payload types a firing can translate into. Named so the signature below fits, and
#: so the set is stated in one place rather than repeated at every use.
_Payload = DirectCause | ConditionalCause | ContributingCause | AmplifyingCause | InhibitingCause

#: The binding labels the DataCo and hospital packs use for a two-event body. A firing
#: names its own bindings, so these are read from the firing rather than assumed -- but the
#: cause/effect ROLES have to be recovered somehow, and a rule body states them positionally.
#: `_cause_and_effect` documents how.
_EFFECT_HINTS = ("EFFECT",)


def _bound(firing: RuleFiring, label: str) -> str | None:
    """Return the identifier one binding label resolved to, or None if unbound."""
    for bound_label, value in firing.bindings:
        if bound_label == label:
            return value
    return None


class RuleBasedGenerator:
    """Translate rule firings into proposals, one payload type per rule kind."""

    generator_id = "rule_based"

    def status(self, context: GenerationContext) -> GeneratorStatus:
        """Runnable only when the caller actually evaluated the rule pack.

        A caller that skipped evaluation gets `NOT_RUNNABLE`, never zero. Reporting an
        unevaluated pack as "the rules proposed nothing" would be the single most
        misleading line this module could print.
        """
        if context.rule_evaluation is None:
            return GeneratorStatus.NOT_RUNNABLE
        return GeneratorStatus.RAN

    def requirement(self) -> str:
        """Return what a caller must supply for this generator to run."""
        return (
            "a rule_engine.EvaluationResult -- the caller must run "
            "rule_engine.evaluate(pack, facts) and pass the result in the "
            "GenerationContext. An unevaluated pack is not a pack that proposed nothing."
        )

    def propose(self, context: GenerationContext) -> tuple[Proposal, ...]:
        """Return one proposal per firing per antecedent, in canonical sequence."""
        evaluation = context.rule_evaluation
        if evaluation is None:
            return ()
        events_by_id = context.events_by_id()
        proposals: list[Proposal] = []
        for firing in evaluation.firings:
            proposals.extend(self._from_firing(firing, events_by_id))
        return tuple(sorted(proposals, key=lambda item: item.sort_key()))

    def _from_firing(
        self, firing: RuleFiring, events_by_id: dict[str, Event]
    ) -> tuple[Proposal, ...]:
        """Return every proposal one firing produces.

        A `JOINT` firing produces one proposal PER CONTRIBUTOR, each carrying the same
        `joint_cause_group_id` and naming the others as co-causes. That is what
        `ContributingCause` requires and what makes the group reassemblable from the edges
        alone -- and it is why a joint rule over three contributors yields three candidates
        and not one.
        """
        effect_id = self._effect_id(firing)
        if effect_id is None:
            return ()
        effect = events_by_id.get(effect_id)
        if effect is None:
            return ()
        cause_ids = tuple(
            sorted(
                identifier
                for identifier in firing.matched_event_ids
                if identifier != effect_id and identifier in events_by_id
            )
        )
        if not cause_ids:
            return ()

        built: list[Proposal] = []
        for cause_id in cause_ids:
            cause = events_by_id[cause_id]
            payload = self._payload(firing, cause_id, cause_ids)
            if payload is None:
                continue
            built.append(
                Proposal(
                    generator_id=self.generator_id,
                    cause_event=cause,
                    effect_event=effect,
                    payload=payload,
                    evidence=(
                        evidence_item(
                            kind=EvidenceKind.RULE,
                            description=(
                                f"Rule {firing.rule_id} ({firing.rule_kind.value}) fired, "
                                f"binding {firing.explains()}. The rule's knowledge "
                                f"provenance is {firing.knowledge_provenance.value}: a rule "
                                "is a declared policy about the world, not an observation "
                                "of it."
                            ),
                            verification=(
                                f"rule_engine.evaluate over rule_pack_version "
                                f"{firing.rule_pack_version}; rule {firing.rule_id}; "
                                f"conditions evaluated: "
                                f"{len(firing.evaluated_conditions)} "
                                f"(trivial={firing.condition_was_trivial}); "
                                f"temporal_verdict={firing.temporal_verdict.value}"
                            ),
                            supporting_ids=(*firing.matched_event_ids,),
                            strength=firing.base_strength,
                            provenance_class=ProvenanceClass.ASSUMED,
                        ),
                    ),
                )
            )
        return tuple(built)

    def _effect_id(self, firing: RuleFiring) -> str | None:
        """Return the event identifier the firing's consequent binding resolved to.

        A modifier firing binds only its modifier and names the rule it rescales; it
        proposes no edge of its own and correctly yields nothing here. That is not a gap:
        `AmplifyingCause`/`InhibitingCause` describe an edge's magnitude, and module 10
        applies a modifier to the edge it names.
        """
        if firing.rule_kind in (RuleKind.AMPLIFICATION, RuleKind.INHIBITION):
            return None
        for label in _EFFECT_HINTS:
            bound = _bound(firing, label)
            if bound is not None:
                return bound
        return None

    def _payload(
        self, firing: RuleFiring, cause_id: str, cause_ids: tuple[str, ...]
    ) -> _Payload | None:
        """Return the payload the firing's kind requires, or None if it proposes no edge.

        Total over `RuleKind` with no default branch: an unhandled kind raises rather than
        silently becoming a `DirectCause`, because a mislabelled edge is worse than a
        missing one.
        """
        if firing.rule_kind is RuleKind.CAUSAL:
            return DirectCause()
        if firing.rule_kind is RuleKind.CONDITIONAL:
            return ConditionalCause(
                condition_expression=self._condition_text(firing),
                condition_holds=all(entry.result for entry in firing.evaluated_conditions),
            )
        if firing.rule_kind is RuleKind.JOINT:
            co_causes = tuple(sorted(other for other in cause_ids if other != cause_id))
            if not co_causes:
                return DirectCause()
            return ContributingCause(
                joint_cause_group_id=firing.rule_id,
                co_cause_event_ids=co_causes,
            )
        if firing.rule_kind in (RuleKind.AMPLIFICATION, RuleKind.INHIBITION, RuleKind.CONSTRAINT):
            return None
        raise ContractViolationError(
            f"RuleBasedGenerator met rule kind {firing.rule_kind.value}, which it has no "
            "payload for. An unhandled kind must not become a DirectCause by default: a "
            "mislabelled edge misdescribes the direction of the claim to every consumer."
        )

    def _condition_text(self, firing: RuleFiring) -> str:
        """Return the exact condition trace, as the expression a reader can re-check.

        `ConditionalCause.condition_expression` must be "the exact expression that was
        evaluated ... a paraphrase is not re-checkable". The trace is that expression in
        the only form this layer holds it: each evaluated node, its address, what it read,
        and what it returned.
        """
        if firing.condition_was_trivial:
            return f"{firing.rule_id}: ALWAYS"
        parts = [
            f"{entry.path} {entry.operator.value}"
            + (f" {entry.address}" if entry.address else "")
            + f" observed={entry.observed!r} -> {entry.result}"
            for entry in firing.evaluated_conditions
        ]
        return f"{firing.rule_id}: " + "; ".join(parts)
