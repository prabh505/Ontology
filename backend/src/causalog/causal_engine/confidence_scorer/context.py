"""What a component scorer is handed, and what it is allowed to hand back.

`ScoringContext` is to module 10 what `GenerationContext` is to module 9, and it is shaped
the same way on purpose: everything a scorer reads arrives as a value, no scorer holds a
reference to another, and nothing here can reach a store (forbidden edge F4).

`ScoredComponent` is deliberately NOT a `ConfidenceComponent`
------------------------------------------------------------
A scorer returns a `ScoredComponent`: a value, an explanation, and the evidence behind it.
Only `score.py` turns those into a `ConfidenceVector`, through `core.aggregation.aggregate`,
which is the one path that can set the vector's provenance to the weakest input and name the
function that produced the scalar.

That is the same separation module 9 draws between `Proposal` and `CandidateEdge`, and it
buys the same thing: a scorer cannot emit a confidence, because it does not hold a type that
could be one. The gate a scorer cannot bypass here is LAW-EVIDENCE rather than LAW-TIME.

WHY EVERY SCORER RETURNS SOMETHING
-----------------------------------
`ComponentScorer.score` has no "not applicable" return. A scorer with no data returns a
`ScoredComponent` at value zero whose explanation says `missing`, and the difference between
that and a genuine zero is carried in the explanation rather than in the presence or absence
of the component. This is the module's central rule and it is enforced by shape: there is no
`None` for a caller to filter out, so a component cannot be skipped by accident.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from causalog.causal_engine.candidate_cause_generator import ConfoundingFlag
from causalog.causal_engine.confidence_scorer.base_rates import PairBaseRates
from causalog.causal_engine.confidence_scorer.explain import ComponentExplanation
from causalog.core.errors import ContractViolationError
from causalog.core.precedence import DerivedPrecedenceIndex
from causalog.core.provenance import ProvenanceClass
from causalog.core.types import (
    CandidateEdge,
    CausalEdgeKind,
    CausalEdgePayload,
    Event,
    EvidenceItem,
    Timeline,
)
from causalog.rule_engine import ConfidenceScoringSpec, EvaluationResult
from causalog.rule_engine.facts import GraphFacts

__all__ = [
    "ComponentScorer",
    "FusedClaim",
    "ScoredComponent",
    "ScoringContext",
]


class ScoredComponent(BaseModel):
    """One component's value, with the sentence and the arithmetic that produced it.

    Invariants:
      * `value` lies in `[0, 1]`. A scorer normalizes before returning, so that no
        aggregator has to know which components are counts (`docs/contracts.md` §5).
      * `explanation.component_name` matches `component_name`. Two names for one number is
        how an explanation ends up describing a different component than the one displayed.
      * `evidence_record_ids` is non-empty unless the component is missing. A component
        that scored on data nobody can cite is a component nobody can check (LAW-EVIDENCE,
        `CONVENTIONS.md` §8) -- and a missing component cites nothing because it measured
        nothing.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    component_name: str = Field(min_length=1)
    value: float = Field(ge=0.0, le=1.0)
    provenance_class: ProvenanceClass
    evidence_record_ids: tuple[str, ...]
    explanation: ComponentExplanation

    @model_validator(mode="after")
    def _check_invariants(self) -> ScoredComponent:
        """Refuse a mismatched explanation and an uncited non-missing component."""
        if self.explanation.component_name != self.component_name:
            raise ContractViolationError(
                f"ScoredComponent '{self.component_name}' carries an explanation for "
                f"'{self.explanation.component_name}'. An explanation describing another "
                "component is worse than none, because it will be read as this one's."
            )
        if not self.explanation.missing and not self.evidence_record_ids:
            raise ContractViolationError(
                f"ScoredComponent '{self.component_name}' scored {self.value} and cites no "
                "evidence. A value that cannot be traced back to a record is exactly the "
                "unexplained number LAW-EVIDENCE forbids; if the data was absent, the "
                "component is missing rather than uncited."
            )
        if self.explanation.missing and self.value != 0.0:
            raise ContractViolationError(
                f"ScoredComponent '{self.component_name}' is marked missing and scored "
                f"{self.value}. A component that could not be measured contributes "
                "nothing; a non-zero missing component would be a measurement smuggled in "
                "under a disclaimer."
            )
        return self


class FusedClaim(BaseModel):
    """Every generator's proposal about one `(cause, effect, edge_kind)`, gathered.

    Module 9 emits a MULTIGRAPH: parallel candidates over one pair, one per generator, each
    with its own evidence. `CausalEdge.address` takes `(source, target, edge_kind)` and
    deliberately omits the generator, so module 10 emits ONE scored edge where module 9
    emitted several proposals -- and this is the value that gathering produces.

    The fusion is not bookkeeping. It is where evidence *diversity* becomes computable: how
    many independent lines of reasoning arrived at the same place is a property of the group
    and of no single member, and `CandidateEdge` has nowhere to record it. Module 9's
    `graph.py` says in as many words that keeping the parallel edges apart is "exactly what
    module 10 needs to assemble a decomposed confidence vector from". This is that.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_event_id: str
    target_event_id: str
    #: Every parallel candidate over this pair and kind, in canonical sequence.
    candidates: tuple[CandidateEdge, ...] = Field(min_length=1)

    @property
    def payload(self) -> CausalEdgePayload:
        """Return the payload, read from the first candidate in canonical sequence.

        Every candidate in a fused claim shares a kind by construction. The payload of the
        first in canonical sequence is taken as the claim's, which matters only for the two
        parametrized kinds; two candidates of one kind with differing parameters are a
        finding this module reports rather than averages (see `fuse.py`).
        """
        return self.candidates[0].payload

    @property
    def edge_kind(self) -> CausalEdgeKind:
        """Return the kind, read from the payload so the two cannot disagree."""
        return self.candidates[0].payload.edge_kind

    def generator_ids(self) -> tuple[str, ...]:
        """Return the distinct generators that reached this pair, sorted."""
        return tuple(sorted({candidate.generator_id for candidate in self.candidates}))

    def evidence(self) -> tuple[EvidenceItem, ...]:
        """Return the union of every candidate's evidence, deduplicated and sequenced.

        Deduplicated by `evidence_item_id`, which is content-addressed, so two generators
        that minted a byte-identical justification contribute it once. Union rather than
        selection: LAW-EVIDENCE wants every justification attached to the claim, and
        picking a winner is the silent judgement this module exists to avoid making.
        """
        by_id = {
            item.evidence_item_id: item
            for candidate in self.candidates
            for item in candidate.evidence
        }
        return tuple(by_id[identifier] for identifier in sorted(by_id))

    def admits_promotion(self) -> bool:
        """Return whether LAW-TIME permits this claim to become `INFERRED`.

        Requires EVERY candidate in the group to admit promotion, not merely one. The
        fused edge is a single claim about one pair, and promoting it on the strength of
        the most permissive of several proposals would launder the others' temporal
        standing -- the exact thing `CandidateEdge`'s own invariant refuses.
        """
        return all(candidate.admits_promotion for candidate in self.candidates)

    def sort_key(self) -> tuple[str, str, str]:
        """Return the canonical sequence key (`CONVENTIONS.md` §11)."""
        return (self.source_event_id, self.target_event_id, self.edge_kind.value)


class ScoringContext(BaseModel):
    """Everything the component scorers read, as values rather than as a store.

    `facts` stands in for `TemporalPropertyGraph` for the same reason it does in module 9:
    module 8 does not exist (`CONTEXT.md` §3), and `GraphFacts` is what it will satisfy when
    it lands without this module changing. The visible consequence is that
    `graph_connectivity` has no relationships to read today and is reported MISSING on every
    edge -- which is a finding this module publishes rather than a gap it papers over.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    facts: GraphFacts
    timelines: tuple[Timeline, ...]
    base_rates: PairBaseRates
    parameters: ConfidenceScoringSpec
    #: `None` when the caller did not run the rule engine. `rule_support` is then MISSING
    #: rather than zero, for the reason module 9's `GeneratorStatus.NOT_RUNNABLE` exists.
    rule_evaluation: EvaluationResult | None
    #: The structures module 9 made visible. They feed `contradiction_freedom`; nothing
    #: here resolves them, and nothing at V1 can (`CONTEXT.md` R-05).
    confounding_flags: tuple[ConfoundingFlag, ...] = ()
    #: `(cause_event_id, effect_event_id)` pairs a `CONSTRAINT` rule prohibited. Module 9
    #: refuses these at its gate; a pair that survived and is still prohibited is a direct
    #: contradiction and is scored as one.
    suppressed_pairs: frozenset[tuple[str, str]] = frozenset()
    #: Every `(cause, effect)` a candidate exists for, in EITHER direction. The reverse of
    #: a claim being independently proposed is counter-evidence against it.
    proposed_pairs: frozenset[tuple[str, str]] = frozenset()
    #: Which of this source's instants were COMPUTED from another rather than recorded,
    #: as module 1 measured them.
    #:
    #: `None` when no such measurement was supplied to this run -- the state that matters,
    #: and the reason this is nullable rather than defaulting to an empty index. An empty
    #: index says the measurement RAN and confirmed nothing; `None` says nobody looked.
    #: Collapsing the two would let an unaudited run present as an audited clean one, which
    #: is the substitution `rule_evaluation` above is nullable to prevent.
    derived_precedence: DerivedPrecedenceIndex | None = None
    run_id: str = Field(min_length=1)

    #: `candidate_edge_id -> flag count`, built once on first use. Not a field: it is
    #: derived from `confounding_flags` and a stored second copy could disagree. Without
    #: it, every edge scans every flag -- 17,864 edges against 68,580 flags on the
    #: reference slice, which is over a billion comparisons for one component.
    _flags_by_candidate: dict[str, int] | None = PrivateAttr(default=None)

    def confounding_flag_count(self, candidate_edge_ids: tuple[str, ...]) -> int:
        """Return how many flagged structures bear on these candidates.

        Matched on `flagged_candidate_ids` rather than on the flag's own event pair, which
        is the semantically correct link: module 9 records on each flag exactly which
        candidates' interpretation the structure bears on, and a flag naming the same two
        events in a different role does not bear on this claim.
        """
        if self._flags_by_candidate is None:
            counted: dict[str, int] = {}
            for flag in self.confounding_flags:
                for candidate_id in flag.flagged_candidate_ids:
                    counted[candidate_id] = counted.get(candidate_id, 0) + 1
            self._flags_by_candidate = counted
        return sum(self._flags_by_candidate.get(item, 0) for item in candidate_edge_ids)

    def events_by_id(self) -> dict[str, Event]:
        """Return every event indexed by identifier.

        Built on demand rather than cached on the model, which is frozen. Callers needing
        it repeatedly bind it once -- `score.py` does.
        """
        return {event.event_id: event for event in self.facts.events()}


@runtime_checkable
class ComponentScorer(Protocol):
    """One named, independently computed contribution to a confidence figure.

    Eight implement this: the six prd.md §49 names, plus `evidence_diversity` and
    `contradiction_freedom` (confidence_schema_version 2.0.0, ADR-0052). Each reads a
    `ScoringContext` and a `FusedClaim` and holds no reference to any other scorer, which
    is what makes each independently testable against hand-computed values.
    """

    component_name: str

    def requirement(self) -> str:
        """Return what must be declared or present for this component to be scorable."""
        ...

    def score(
        self,
        claim: FusedClaim,
        context: ScoringContext,
        events_by_id: dict[str, Event],
    ) -> ScoredComponent:
        """Return this component for one claim; never returns None.

        A component with nothing to measure returns value zero with
        `explanation.missing` set. There is no "skip" return, because a skippable
        component is one that gets silently skipped.
        """
        ...
