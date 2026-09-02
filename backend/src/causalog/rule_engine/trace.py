"""`RuleFiring` -- what a rule produced, and the whole of why (ADR-0047).

A firing carries every input a reader needs to re-derive it by hand: which rule, which
bindings, which events, which conditions were evaluated, what each one read, and what each
one returned. **A firing with no trace is a defect**, and this module makes that
enforceable rather than aspirational: `RuleFiring` refuses to construct without its trace,
so an untraceable firing does not exist to be persisted, scored, or displayed.

The alternative -- a lint, a review convention, or a nullable `trace` field -- leaves the
defect representable, and a defect that is representable eventually gets represented.

What a firing is NOT
--------------------
It is not a causal edge, and this module may not create one. `docs/architecture.md` §Module
9 gives the Candidate Cause Generator (L6) ownership of the LAW-TIME gate and of
`CausalEdge` construction; the §6.2 sequence diagram has this layer returning fired rule
identifiers to it. A firing is a proposal with its reasoning attached, and the decision to
promote it is taken a layer up, with evidence this layer does not hold.

It carries no `ConfidenceVector` either. `base_strength` is the rule's own authored weight,
a bare float exactly as `EvidenceItem.strength` is (`docs/contracts.md` §5) and named so it
is not mistaken for a judgement. Assembling components into a vector is module 10's job.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalog.core.errors import ContractViolationError
from causalog.core.temporal import TemporalVerdict
from causalog.rule_engine.dsl import ConditionOperator, KnowledgeProvenance, RuleKind

__all__ = ["ConditionTraceEntry", "RuleFiring", "WindowObservation"]


class ConditionTraceEntry(BaseModel):
    """One evaluated node of a condition tree: what was read, and what it returned.

    `path` is the node's position in the tree (`root.operands[0]`), so a reader can line the
    trace up against the authored condition without guessing. `address` and `observed` are
    populated only for a node that read a value; a junction reads nothing and says so by
    leaving them empty rather than by carrying a placeholder.

    `observed` is `None` when the addressed attribute was **absent**, which is a different
    finding from an attribute present and empty. Collapsing the two would make `IS_ABSENT`
    untestable from the trace alone.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1)
    operator: ConditionOperator
    address: str = ""
    observed: str | None = None
    result: bool


class WindowObservation(BaseModel):
    """The separation actually seen between two matched events, against the authored bound.

    Kept as bounds rather than a point, because the two events carry intervals and
    collapsing an interval for computation is a defect (`CONVENTIONS.md` §10). A reader
    checking a firing needs the numbers the comparison used, not a midpoint.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    minimum_separation_seconds: int
    maximum_separation_seconds: int
    window_minimum_seconds: int
    window_maximum_seconds: int


class RuleFiring(BaseModel):
    """One rule matching one binding of events, with the whole of its reasoning attached.

    Invariants, all enforced at construction:

      * `matched_event_ids` is non-empty and sorted.
      * `bindings` is sorted by label, has no repeat, and every label the rule declared
        appears exactly once -- a firing that bound only half its rule cannot be re-derived.
      * `evaluated_conditions` is non-empty **unless** the rule's condition tree was
        `ALWAYS`. `condition_was_trivial` records which case this is, so an empty trace is
        always a stated fact rather than an omission.
      * `temporal_verdict` is never `VIOLATION`. A pair the LAW-TIME test rejects is never
        emitted (`CONVENTIONS.md` §10), so a firing carrying that verdict could only come
        from a caller that bypassed the test.
      * `base_strength` is in `[0, 1]`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str
    rule_kind: RuleKind
    rule_pack_version: str
    knowledge_provenance: KnowledgeProvenance
    #: (binding label, entity or event identifier the label resolved to), sorted by label.
    bindings: tuple[tuple[str, str], ...]
    matched_event_ids: tuple[str, ...]
    evaluated_conditions: tuple[ConditionTraceEntry, ...]
    condition_was_trivial: bool
    window_observed: WindowObservation | None = None
    temporal_verdict: TemporalVerdict
    temporally_unverifiable: bool
    base_strength: float = Field(ge=0.0, le=1.0)
    #: For a modifier firing, the rule whose claim it rescales, and by how much.
    modifies_rule_id: str | None = None
    magnitude_multiplier: float | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> RuleFiring:
        """Enforce that a firing carries its reasoning, or does not exist."""
        if not self.matched_event_ids:
            raise ContractViolationError(
                f"RuleFiring for {self.rule_id} matched no event; a firing over nothing "
                "cites nothing and cannot be re-derived by a reader."
            )
        if list(self.matched_event_ids) != sorted(self.matched_event_ids):
            raise ContractViolationError(
                f"RuleFiring for {self.rule_id} has unsequenced matched_event_ids "
                "(CONVENTIONS.md §11)."
            )
        labels = [label for label, _ in self.bindings]
        if labels != sorted(labels):
            raise ContractViolationError(
                f"RuleFiring for {self.rule_id} has unsequenced bindings " "(CONVENTIONS.md §11)."
            )
        if len(set(labels)) != len(labels):
            raise ContractViolationError(
                f"RuleFiring for {self.rule_id} binds one label twice; a trace that reads "
                "two ways is not a trace."
            )
        if not self.bindings:
            raise ContractViolationError(
                f"RuleFiring for {self.rule_id} carries no bindings; the reader cannot tell "
                "which participants the rule matched (ADR-0047)."
            )
        if not self.condition_was_trivial and not self.evaluated_conditions:
            raise ContractViolationError(
                f"RuleFiring for {self.rule_id} carries a non-trivial condition and an "
                "empty trace. A rule that cannot explain itself may not fire (ADR-0047); "
                "this firing does not exist."
            )
        if self.condition_was_trivial and self.evaluated_conditions:
            raise ContractViolationError(
                f"RuleFiring for {self.rule_id} claims a trivial condition and carries "
                "trace entries; the two disagree and a reader cannot tell which is stale."
            )
        if self.temporal_verdict is TemporalVerdict.VIOLATION:
            raise ContractViolationError(
                f"RuleFiring for {self.rule_id} carries a VIOLATION verdict. A pair the "
                "LAW-TIME test rejects is never emitted, so this firing was constructed by "
                "a path that bypassed the test (CONVENTIONS.md §10)."
            )
        return self

    def explains(self) -> str:
        """Return the one-line human form: rule, bindings, verdict.

        Deliberately terse and deliberately not the explanation a user sees -- rendering
        that is module 15's job, through `PresentationLabels`, and it needs display strings
        this layer may not read. This exists so a firing is legible in a test failure.
        """
        bound = " ".join(f"{label}={value}" for label, value in self.bindings)
        return f"{self.rule_id} [{self.rule_kind.value}] {bound} -> {self.temporal_verdict.value}"
