"""What a generator is handed, and what it is allowed to hand back.

Two types and one protocol, kept in their own module because the shape of a generator's
input and output is the whole of the composability claim: six independent generators are
independently testable only if none of them can reach anything the others reach through.

`Proposal` is deliberately NOT a `CandidateEdge`
------------------------------------------------
A generator returns proposals. Only `gate.py` turns a proposal into a `CandidateEdge`, and
it does so through `CandidateEdge.between`, which is the one constructor that can evaluate
LAW-TIME. A generator therefore *cannot* emit an ungated candidate -- not because it is
asked not to, but because it does not hold a type that could be one.

That is the same argument `rule_engine.trace` makes about `RuleFiring`: a firing is a
proposal with its reasoning attached, and the decision to promote it is taken a layer up.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalog.core.errors import ContractViolationError
from causalog.core.types import CausalEdgePayload, Event, EvidenceItem, Timeline
from causalog.rule_engine import CandidateGenerationSpec, EvaluationResult
from causalog.rule_engine.facts import GraphFacts

__all__ = [
    "CandidateGenerator",
    "GenerationContext",
    "GeneratorStatus",
    "Proposal",
]


class GeneratorStatus(str, Enum):
    """Whether a generator ran, and if not, why not.

    `NOT_RUNNABLE` exists for the reason `ontology_runtime` introduced its third severity:
    **a check that could not run reads identically to a check that passed.** A generator
    whose declared parameter is absent produced no candidates, and reporting that as `0`
    would be indistinguishable from a generator that ran over the whole dataset and found
    nothing -- which is a completely different finding about the pack and about the data.
    """

    RAN = "RAN"
    """The generator had everything it needed and produced whatever it produced."""

    NOT_RUNNABLE = "NOT_RUNNABLE"
    """A parameter the generator requires is not declared. It did not run. This is not zero."""


class Proposal(BaseModel):
    """One generator's pre-gate suggestion that one event may have produced another.

    Carries the two `Event` objects rather than their identifiers, because the gate needs
    both intervals and an identifier does not carry one. That is the same reasoning
    `CausalEdge.between` and `CandidateEdge.between` both apply, propagated one step
    earlier so a generator cannot construct a pair the gate is then unable to check.

    Invariants:
      * `evidence` is non-empty and every item is sorted-stable (LAW-EVIDENCE).
      * `cause_event` and `effect_event` are distinct. A generator proposing a self-pair is
        a generator with a bug, and it is refused here rather than counted downstream.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    generator_id: str = Field(min_length=1)
    cause_event: Event
    effect_event: Event
    payload: CausalEdgePayload
    evidence: tuple[EvidenceItem, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_invariants(self) -> Proposal:
        """Refuse a self-pair and an unevidenced proposal at construction."""
        if self.cause_event.event_id == self.effect_event.event_id:
            raise ContractViolationError(
                f"Generator {self.generator_id} proposed {self.cause_event.event_id} as "
                "its own cause. An event does not cause itself, and a generator that "
                "emits one has a pairing defect rather than an unusual finding."
            )
        return self

    def sort_key(self) -> tuple[str, str, str, str]:
        """Return the canonical sequence key (`CONVENTIONS.md` §11)."""
        return (
            self.cause_event.event_id,
            self.effect_event.event_id,
            self.payload.edge_kind.value,
            self.generator_id,
        )


class GenerationContext(BaseModel):
    """Everything the generators read, as values rather than as a store.

    Forbidden edge F4 means no reasoning package may import `causalog.persistence`, so
    facts arrive through the `GraphFacts` protocol satisfied by a plain value -- exactly
    the seam `rule_engine.facts` established, and reused rather than reinvented.

    **`TemporalPropertyGraph` is deliberately absent.** Module 8 does not exist
    (`CONTEXT.md` §3), so the graph this module is documented as reading cannot be handed
    to it. `GraphFacts` is what module 8 will satisfy when it lands, without this module
    changing. Waiting for module 8 instead would leave prd.md §27 unbuilt and would leave
    the rule engine, which has been finished since 2026-09-01, with no consumer.

    `rule_evaluation` is `None` when the caller did not run the rule engine. The rule-based
    generator then reports `NOT_RUNNABLE` rather than zero, for the reason `GeneratorStatus`
    gives.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    facts: GraphFacts
    timelines: tuple[Timeline, ...]
    parameters: CandidateGenerationSpec
    rule_evaluation: EvaluationResult | None
    run_id: str = Field(min_length=1)

    def events_by_id(self) -> dict[str, Event]:
        """Return every event indexed by identifier.

        Built on demand rather than cached on the model, which is frozen. Callers that
        need it repeatedly bind it once; the cost is linear and the alternative is a
        mutable field on an immutable value.
        """
        return {event.event_id: event for event in self.facts.events()}


@runtime_checkable
class CandidateGenerator(Protocol):
    """One independent source of causal hypotheses (prd.md §27).

    Six sources are named in prd.md §27 and seven implement them here: shared entity and
    shared identifier are separated because `EvidenceKind` already distinguishes them, and
    fusing two evidence kinds under one generator identifier would make the per-generator
    report unable to say which of the two produced a given proposal.

    Each is independently testable by construction: it reads a `GenerationContext` and
    returns proposals, and holds no reference to any other generator.
    """

    generator_id: str

    def status(self, context: GenerationContext) -> GeneratorStatus:
        """Return whether this generator can run against the declared parameters."""
        ...

    def requirement(self) -> str:
        """Return what this generator needs declared, for the `NOT_RUNNABLE` report line."""
        ...

    def propose(self, context: GenerationContext) -> tuple[Proposal, ...]:
        """Return every proposal this generator makes, in canonical sequence.

        Never called when `status` is `NOT_RUNNABLE`. A generator is free to return an
        empty tuple when it ran and found nothing -- that is a real and different finding.
        """
        ...
