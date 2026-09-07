"""The artifacts the Causal Graph Builder publishes: what was promoted, and what was not.

`CausalGraph` (module 10) holds every scored claim. This module holds the *stated view* --
the subset the engine is willing to assert -- and, beside it and of equal standing, the
record of everything it considered and rejected.

**The rejection ledger is not a diagnostic.** "What did you consider and reject?" is a
question a user is entitled to ask of a causal claim, and a graph that cannot answer it is
asserting a conclusion while withholding the alternatives. `DemotionRecord` is therefore a
first-class member of `PromotedGraph`, its arithmetic is checked against the promoted set at
construction, and both are rendered in the report.

Nothing here ranks. Edges are sequenced canonically by `(source, target, kind)`, exactly as
module 10 sequences them and for the same reason (`CONVENTIONS.md` §11): a ranked artifact
invites a reader to treat position as a finding, and ranking is module 11's.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalog.core.errors import ContractViolationError, LawViolationError
from causalog.core.provenance import ProvenanceClass
from causalog.core.types import CausalEdge, ConfidenceVector

__all__ = [
    "ATTRIBUTION_NOT_MEASUREMENT_NOTICE",
    "DemotionReason",
    "DemotionRecord",
    "EdgeLineage",
    "JointCauseGroup",
    "PromotedEdge",
    "PromotedGraph",
    "PropagationWeight",
    "TypingBasis",
    "TypingRecord",
    "WeightBasis",
]

#: Carried verbatim wherever a propagation weight is shown. Fixed text, in the shape of
#: module 10's `NOT_CALIBRATED_NOTICE`, so that no per-run rendering can soften it.
ATTRIBUTION_NOT_MEASUREMENT_NOTICE = (
    "PROPAGATION WEIGHT IS AN ATTRIBUTION ESTIMATE, NOT A MEASUREMENT. It apportions a "
    "magnitude the ontology declares how to compute across the causes this engine happens "
    "to hold for that effect. Nothing identifies a causal effect: no counterfactual was "
    "observed, no confounder was adjusted for, and a cause the engine never proposed "
    "receives no share -- so the shares sum to one over the modelled causes and not over "
    "the real ones. Two weights are comparable to each other. Neither is a quantity of "
    "anything in the world."
)


class EdgeLineage(BaseModel):
    """Everything that led to one claim, kept whether the claim was promoted or not.

    A promoted edge without its lineage is an assertion with the reasoning removed. A
    *demoted* one without its lineage is worse: a reader cannot tell whether the engine
    rejected a well-supported claim on a threshold or never had anything to reject.

    **`generator_ids` is recorded, never re-scored.** Module 10 already fused the parallel
    candidates over this pair, deduplicated their evidence by content-addressed
    `evidence_item_id`, and turned the multiplicity into the `evidence_diversity` and
    `evidence_count` components of the vector. Counting the generators again here as
    corroboration would be counting one fact twice (ADR-0055).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_edge_ids: tuple[str, ...] = Field(min_length=1)
    #: Distinct and sorted. Its length is the diversity of ORIGIN, not of evidence.
    generator_ids: tuple[str, ...] = Field(min_length=1)
    evidence_item_ids: tuple[str, ...] = Field(min_length=1)
    #: The WHOLE vector, not its scalar. A ledger entry saying "this scored 0.24" and
    #: nothing else is the unexplained number prd.md §49 forbids, and it is worst exactly
    #: here: a reader asking why a claim was rejected needs to see which leg was weak, and a
    #: demoted claim has no `CausalEdge` beside it to look the components up on. LAW-EVIDENCE
    #: exempts no artifact, including the record of a refusal.
    confidence: ConfidenceVector
    #: None when the pack declares no bands, or when the outcome was INSUFFICIENT_EVIDENCE.
    band_name: str | None = None
    scored_component_count: int = Field(ge=0)
    outcome: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_sequencing(self) -> EdgeLineage:
        """Refuse unsorted or repeated identifiers; lineage is compared across runs."""
        for label, values in (
            ("candidate_edge_ids", self.candidate_edge_ids),
            ("generator_ids", self.generator_ids),
            ("evidence_item_ids", self.evidence_item_ids),
        ):
            if list(values) != sorted(set(values)):
                raise ContractViolationError(
                    f"EdgeLineage.{label} is unsorted or repeats an entry; lineage is "
                    "diffed between runs and an unstable sequence makes two identical "
                    "runs look different (CONVENTIONS.md §11)."
                )
        return self


class TypingBasis(str, Enum):
    """On what authority an edge carries the kind it carries (prd.md §26)."""

    RULE_DECLARED = "RULE_DECLARED"
    """A rule in the pack fired over this pair and its `RuleKind` names this category."""

    STRUCTURAL = "STRUCTURAL"
    """No rule named this pair. The kind follows from the payload a generator built, which
    is a structural claim about the graph rather than a declared piece of knowledge."""

    UNTYPED_DEFAULT = "UNTYPED_DEFAULT"
    """The kind is `DIRECT` because nothing qualified it, not because anyone established
    directness. Kept distinct from `STRUCTURAL` so a report can say how much of the graph
    is typed by default -- which is a coverage statement about the rule pack."""


class TypingRecord(BaseModel):
    """The §26 category an edge carries, and what put it there.

    **Disagreements are recorded, not resolved.** When a firing rule's kind and the payload's
    kind differ, both are reported and the payload's kind stands -- it is the one the
    identifier was computed from. Silently rewriting the kind would move the edge's content
    address, and silently keeping it while a rule says otherwise would hide a real
    contradiction between the pack and the graph. This is ADR-0051's treatment of confounder
    structures applied to typing: make it visible, resolve nothing, say so.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    edge_kind: str = Field(min_length=1)
    basis: TypingBasis
    #: Sorted rule identifiers that fired over this pair. Empty unless basis is RULE_DECLARED.
    supporting_rule_ids: tuple[str, ...] = ()
    #: One sentence per disagreement, sorted. Never empty when a rule's kind differs.
    disagreements: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _check_basis(self) -> TypingRecord:
        """A rule-declared typing names its rules; a structural one names none."""
        if self.basis is TypingBasis.RULE_DECLARED and not self.supporting_rule_ids:
            raise ContractViolationError(
                "TypingRecord claims RULE_DECLARED and names no rule; a basis nobody can "
                "look up is not a basis."
            )
        if self.basis is not TypingBasis.RULE_DECLARED and self.supporting_rule_ids:
            raise ContractViolationError(
                f"TypingRecord claims {self.basis.value} and names rules "
                f"{list(self.supporting_rule_ids)}; if a rule established the kind the "
                "basis is RULE_DECLARED, and if it did not it must not be cited."
            )
        if list(self.supporting_rule_ids) != sorted(set(self.supporting_rule_ids)):
            raise ContractViolationError("TypingRecord.supporting_rule_ids is unsorted.")
        if list(self.disagreements) != sorted(self.disagreements):
            raise ContractViolationError("TypingRecord.disagreements is unsorted.")
        return self


class WeightBasis(str, Enum):
    """What a propagation weight is a share OF. Never inferred from the number itself."""

    MEASURED_MAGNITUDE = "MEASURED_MAGNITUDE"
    """A declared measurement was evaluated for this effect and the weight is a share of
    that quantity, normalized over the effect's competing incoming contributing edges."""

    CONFIDENCE_SHARE = "CONFIDENCE_SHARE"
    """No magnitude was available, so the weight is a share of BELIEF -- this edge's
    confidence over the summed confidence of its competitors. Reported as a distinct basis
    because a share of belief and a share of a quantity are different things wearing one
    number, and a report that did not separate them would be the LAW-EVIDENCE defect."""

    MODIFIER_MULTIPLIER = "MODIFIER_MULTIPLIER"
    """An `AMPLIFYING` or `INHIBITING` edge. A modifier is not a contributor: it is excluded
    from the normalization basis and carries its declared multiplier's effect instead, so
    that giving it a share would not make it look like one of the causes."""


class PropagationWeight(BaseModel):
    """How much of an effect's magnitude this cause is credited with -- and on what basis.

    Every field exists so that the number can be argued with. `notice` is fixed text and
    is not stored: storing it would let a revision soften it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    weight: float = Field(ge=0.0, le=1.0)
    basis: WeightBasis
    measurement_id: str | None = None
    measurement_unit: str | None = None
    #: The effect's magnitude as the declared measurement computed it, before apportioning.
    #: `None` under `CONFIDENCE_SHARE`, and `None` under `MEASURED_MAGNITUDE` only when the
    #: measurement was declared and evaluated to nothing for this instance.
    effect_magnitude: float | None = None
    #: The declared normalization, carried per edge so a stored artifact says which rule
    #: produced its number rather than requiring the pack to be fetched to find out.
    normalization: str | None = None
    #: How many incoming edges shared the basis with this one. One means no competition,
    #: which is a materially different claim from a share of one among many.
    competing_edge_count: int = Field(ge=0)

    @property
    def notice(self) -> str:
        """Return the fixed attribution notice. Not a field, so it cannot be revised."""
        return ATTRIBUTION_NOT_MEASUREMENT_NOTICE

    @model_validator(mode="after")
    def _check_basis(self) -> PropagationWeight:
        """A measured weight names its measurement; a belief share must not pretend to."""
        if self.basis is WeightBasis.MEASURED_MAGNITUDE and self.measurement_id is None:
            raise ContractViolationError(
                "PropagationWeight claims MEASURED_MAGNITUDE and names no measurement; the "
                "basis is the claim that a declared quantity was apportioned, and an "
                "unnamed quantity cannot be recomputed by anyone who doubts the share."
            )
        if self.basis is not WeightBasis.MEASURED_MAGNITUDE and self.measurement_id is not None:
            raise ContractViolationError(
                f"PropagationWeight claims {self.basis.value} and names measurement "
                f"{self.measurement_id!r}; citing a measurement that was not apportioned "
                "would present a share of belief as a share of that quantity."
            )
        return self


class PromotedEdge(BaseModel):
    """One edge the engine stands behind: `INFERRED`, typed, weighted, and traceable.

    Invariants:
      * The wrapped edge carries `INFERRED`. That is what promotion MEANS, and an edge in
        this collection carrying anything else would make the collection's name false.
      * `threshold_band` names the band the pack required for this kind. Stored rather than
        recomputed so that a change to the pack does not retroactively re-explain an
        artifact already written.
      * A `CONTRIBUTING` edge names its joint group, and no other kind does. Membership is
        what makes all-or-nothing promotion checkable (ADR-0054).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    edge: CausalEdge
    lineage: EdgeLineage
    typing: TypingRecord
    weight: PropagationWeight
    threshold_band: str = Field(min_length=1)
    joint_cause_group_id: str | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> PromotedEdge:
        """Enforce that a promoted edge is actually promoted, and is typed consistently."""
        if self.edge.provenance_class is not ProvenanceClass.INFERRED:
            raise LawViolationError(
                f"PromotedEdge wraps {self.edge.causal_edge_id} carrying "
                f"{self.edge.provenance_class.value}, not INFERRED. Promotion is the "
                "assignment of INFERRED; an edge in the promoted set that never received "
                "it would be presented as the engine's stated view while carrying a class "
                "that says otherwise (LAW-PROVENANCE)."
            )
        if self.typing.edge_kind != self.edge.payload.edge_kind.value:
            raise ContractViolationError(
                f"PromotedEdge types {self.edge.causal_edge_id} as "
                f"{self.typing.edge_kind!r} while its payload says "
                f"{self.edge.payload.edge_kind.value!r}. The payload's kind is in the "
                "content address; a typing record that disagrees with it describes a "
                "different edge."
            )
        is_contributing = self.edge.payload.edge_kind.value == "CONTRIBUTING"
        if is_contributing and self.joint_cause_group_id is None:
            raise ContractViolationError(
                f"PromotedEdge {self.edge.causal_edge_id} is CONTRIBUTING and names no "
                "joint cause group; a contributor whose group is unknown cannot be "
                "promoted all-or-nothing with its co-causes, and intervention analysis "
                "would read it as independently sufficient (prd.md §26)."
            )
        if not is_contributing and self.joint_cause_group_id is not None:
            raise ContractViolationError(
                f"PromotedEdge {self.edge.causal_edge_id} is "
                f"{self.edge.payload.edge_kind.value} and names a joint cause group; only "
                "a contributor belongs to one."
            )
        return self

    def sort_key(self) -> tuple[str, str, str]:
        """Return the canonical sequence key -- never a score (`CONVENTIONS.md` §11)."""
        return (
            self.edge.source_event_id,
            self.edge.target_event_id,
            self.edge.payload.edge_kind.value,
        )


class DemotionReason(str, Enum):
    """Why a scored claim did not become part of the stated view.

    A closed set, because the report tallies by reason and an open one would let a new
    rejection path arrive as an untallied "other". Every member is a different question the
    reader might be asking, and they are never summed into a single "rejected" count.
    """

    BELOW_KIND_THRESHOLD = "BELOW_KIND_THRESHOLD"
    """Scored, banded, and below the band this kind requires. The commonest honest reason."""

    NO_THRESHOLD_DECLARED = "NO_THRESHOLD_DECLARED"
    """The pack declares no threshold for this edge kind, so nothing of that kind may be
    promoted. A statement about the PACK, never about the claim, and separated from
    `BELOW_KIND_THRESHOLD` for exactly that reason."""

    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    """Module 10 could not measure enough components to call the edge scored. Not a low
    score, and never reported as one."""

    TEMPORAL_NOT_CERTAIN = "TEMPORAL_NOT_CERTAIN"
    """The data placed both events and could not separate them (`UNDETERMINED`). LAW-TIME
    blocks promotion and no threshold can override it."""

    TEMPORALLY_UNVERIFIABLE = "TEMPORALLY_UNVERIFIABLE"
    """The data never placed one of the two events. A different finding about the dataset
    from `TEMPORAL_NOT_CERTAIN`, and collapsing them would hide which one the run hit."""

    LOST_COMPETITION = "LOST_COMPETITION"
    """Above its threshold, but the pack's competing-effect policy retained others instead.
    The only reason here that is a judgement about relative standing rather than about the
    claim itself."""

    JOINT_GROUP_INCOMPLETE = "JOINT_GROUP_INCOMPLETE"
    """A co-contributor in this claim's joint cause group could not be promoted, so no
    member is. Promoting a subset would tell intervention analysis that removing any one
    member prevents the outcome, which is the opposite of what a joint cause asserts."""

    POLICY_NOT_RUNNABLE = "POLICY_NOT_RUNNABLE"
    """A declaration the promotion decision needs is absent from the pack, so no decision
    was made. Never reported as a rejection of the claim (ADR-0049's rule)."""


class DemotionRecord(BaseModel):
    """One claim the engine considered and did not assert, with the reason and the lineage.

    `detail` is required and is the sentence a reader gets. A reason code alone tells them
    which bucket the claim fell into and not what would have to change.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_event_id: str = Field(min_length=1)
    target_event_id: str = Field(min_length=1)
    edge_kind: str = Field(min_length=1)
    reason: DemotionReason
    detail: str = Field(min_length=1)
    lineage: EdgeLineage

    def sort_key(self) -> tuple[str, str, str]:
        """Return the canonical sequence key, matching `PromotedEdge.sort_key`."""
        return (self.source_event_id, self.target_event_id, self.edge_kind)


class JointCauseGroup(BaseModel):
    """A set of contributors that jointly produce one effect, promoted all or not at all.

    prd.md §26's contributing cause is conjunctive: several causes *jointly* produce the
    outcome, and none is sufficient alone. Modelling that as N independent edges loses the
    conjunction, and the loss is not cosmetic -- module 13's counterfactual surgery and
    module 14's intervention ranking both ask "what happens if this cause is removed", and
    over an independent edge the answer is "the effect does not occur". Over one member of a
    joint group the honest answer is "the effect may still occur, because the others remain".

    So the group is the unit of promotion. `promoted` is false for the whole group the
    moment any member fails, and every member is demoted with `JOINT_GROUP_INCOMPLETE`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    joint_cause_group_id: str = Field(min_length=1)
    target_event_id: str = Field(min_length=1)
    #: Sorted. Two members minimum: a "joint" cause with one contributor is a direct cause.
    member_source_event_ids: tuple[str, ...] = Field(min_length=2)
    promoted: bool
    detail: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_members(self) -> JointCauseGroup:
        """Refuse an unsorted or repeating membership."""
        members = list(self.member_source_event_ids)
        if members != sorted(set(members)):
            raise ContractViolationError(
                "JointCauseGroup.member_source_event_ids is unsorted or repeats a member; "
                "the group's membership is what all-or-nothing promotion is checked "
                "against, and a repeated member would make the count disagree with itself."
            )
        return self

    def sort_key(self) -> tuple[str, str]:
        """Return the canonical sequence key."""
        return (self.target_event_id, self.joint_cause_group_id)


class PromotedGraph(BaseModel):
    """The stated causal view of one run, and everything it declined to state.

    Checks its own arithmetic at construction rather than trusting the builder, which is
    the idiom `CandidateGraph` (module 9) and `CausalGraph` (module 10) both establish: a
    graph whose totals disagree with themselves is not published with a warning, it is
    refused.

    Invariants:
      * `edges` and `demotions` are each canonically sequenced and internally unique.
      * `len(edges) + len(demotions) == claims_considered`. Every claim module 10 scored is
        either asserted or accounted for. A claim that is neither has been dropped, and a
        dropped claim is the one failure mode this artifact exists to make impossible.
      * No `(source, target, kind)` appears in both collections.
      * Every edge is scoped to this run (ADR-0013).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1)
    edges: tuple[PromotedEdge, ...]
    demotions: tuple[DemotionRecord, ...]
    joint_groups: tuple[JointCauseGroup, ...]
    claims_considered: int = Field(ge=0)

    @model_validator(mode="after")
    def _check_arithmetic(self) -> PromotedGraph:
        """Refuse a graph whose totals disagree with its contents."""
        promoted_keys = [edge.sort_key() for edge in self.edges]
        if promoted_keys != sorted(promoted_keys):
            raise ContractViolationError(
                "PromotedGraph.edges is unsequenced; it is sequenced canonically and never "
                "by score, so two runs over one input render identically (CONVENTIONS.md "
                "§11). Ranking is module 11's."
            )
        if len(set(promoted_keys)) != len(promoted_keys):
            raise ContractViolationError(
                "PromotedGraph.edges repeats a (source, target, kind); module 10 emits one "
                "scored claim per such key, so a repeat means a claim was promoted twice "
                "and every degree count is wrong."
            )
        demoted_keys = [record.sort_key() for record in self.demotions]
        if demoted_keys != sorted(demoted_keys):
            raise ContractViolationError("PromotedGraph.demotions is unsequenced.")
        if len(set(demoted_keys)) != len(demoted_keys):
            raise ContractViolationError(
                "PromotedGraph.demotions repeats a (source, target, kind); one claim "
                "rejected twice would be counted twice in the rejection ledger."
            )
        overlap = sorted(set(promoted_keys) & set(demoted_keys))
        if overlap:
            raise ContractViolationError(
                f"PromotedGraph both asserts and rejects {overlap}; a claim is in the "
                "stated view or in the ledger, never in both."
            )
        total = len(self.edges) + len(self.demotions)
        if total != self.claims_considered:
            raise ContractViolationError(
                f"PromotedGraph asserts {len(self.edges)} and rejects "
                f"{len(self.demotions)}, totalling {total}, against "
                f"{self.claims_considered} claims considered. A claim that is neither "
                "asserted nor accounted for has been dropped silently, which is the "
                "failure this artifact exists to make impossible."
            )
        for edge in self.edges:
            if edge.edge.run_id != self.run_id:
                raise ContractViolationError(
                    f"PromotedGraph is scoped to {self.run_id} and holds an edge scoped to "
                    f"{edge.edge.run_id}; run scoping is what structurally prevents an "
                    "inference overwriting an observed fact (ADR-0013)."
                )
        group_keys = [group.sort_key() for group in self.joint_groups]
        if group_keys != sorted(group_keys) or len(set(group_keys)) != len(group_keys):
            raise ContractViolationError(
                "PromotedGraph.joint_groups is unsequenced or repeats a group."
            )
        return self

    def edges_by_target(self) -> dict[str, tuple[PromotedEdge, ...]]:
        """Return the promoted incoming edges of every effect, in canonical sequence."""
        grouped: dict[str, list[PromotedEdge]] = {}
        for edge in self.edges:
            grouped.setdefault(edge.edge.target_event_id, []).append(edge)
        return {target: tuple(members) for target, members in sorted(grouped.items())}

    def demotions_for_effect(self, effect_event_id: str) -> tuple[DemotionRecord, ...]:
        """Return every claim this run considered for one effect and did not assert.

        The counterpart to `edges_by_target` on the other side of the ledger, and the answer
        to "why is there nothing here?" for a specific outcome. `DemotionRecord` already
        carries both event ids and every demotion is retained, so this is complete -- no
        sampling, no elision.

        Note that the report aggregates demotions by event TYPE. That is a summary for a
        reader; it is not the data, and a question about one event instance is answered
        here rather than there.
        """
        return tuple(
            record for record in self.demotions if record.target_event_id == effect_event_id
        )

    def demotions_per_effect(self) -> tuple[tuple[str, int], ...]:
        """Return (effect_event_id, demotion count), sorted by effect identifier."""
        tally: dict[str, int] = {}
        for record in self.demotions:
            tally[record.target_event_id] = tally.get(record.target_event_id, 0) + 1
        return tuple(sorted(tally.items()))

    def demotions_by_reason(self) -> tuple[tuple[str, int], ...]:
        """Return the rejection ledger's tally, one row per reason that actually occurred.

        Reasons that did not occur are omitted here and are listed in the report instead,
        which is where the distinction between "none fell here" and "this path is
        unreachable" belongs.
        """
        tally: dict[str, int] = {}
        for record in self.demotions:
            tally[record.reason.value] = tally.get(record.reason.value, 0) + 1
        return tuple(sorted(tally.items()))
