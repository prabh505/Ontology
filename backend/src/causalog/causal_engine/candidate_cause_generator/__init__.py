"""`causalog.causal_engine.candidate_cause_generator` -- module 9, the candidate graph (L6).

prd.md §27, in full: "Every event may have multiple candidate causes. The engine should
initially construct a candidate graph rather than assuming certainty. Candidate causes are
ranked later." This package is that paragraph.

WHAT THIS PACKAGE PRODUCES
--------------------------
`CandidateEdge` values, in a `CandidateGraph` multigraph, with a `CandidateGraphReport`
saying what each of the seven generators proposed and what the gate refused. Every
candidate carries at least one `EvidenceItem` naming the exact rule, window, contingency
table or path that produced it (LAW-EVIDENCE).

It owns **the LAW-TIME gate**, and that is the reason this module and not another is where
the inference boundary sits (`docs/architecture.md` forbidden edge F6). Everything below L6
records what was observed; this is the first place a proposal about causation may be made.

WHAT THIS PACKAGE DOES NOT DO, STRUCTURALLY RATHER THAN BY CONVENTION
---------------------------------------------------------------------
* **It does not assign confidence.** `CandidateEdge` has no confidence field. The
  separation is enforced by the type, not by a rule someone has to remember -- a generator
  cannot score because the artifact it produces has nowhere to put a score. Module 10 builds
  `CausalEdge` from these, and `CausalEdge` is where a `ConfidenceVector` first appears.
* **It does not rank.** The cap policy is round-robin across generators, deliberately
  chosen because every intuitive alternative -- closest in time, strongest evidence, most
  agreement -- is a plausibility ranking wearing a bound's clothing.
* **It does not prune on "seems unlikely".** The only things refused are a LAW-TIME
  violation, a self-pair, a declared constraint prohibition, and the declared cap. All four
  are counted and reported.
* **It does not discard an `UNDETERMINED` candidate.** They are retained, flagged, blocked
  from `INFERRED` by the type's own invariant, and reported as a ratio. `CONTEXT.md` R-14
  predicts they may dominate; that is a finding about the dataset, never something to tune
  away by loosening the test.
* **It does not read `Event.trigger`.** ADR-0020: an observed mechanism recorded on an
  event may not become an unscored causal claim by being matched on.
* **It does not resolve confounding, and nothing at V1 can.** `confounding.py` makes two
  structures visible and says in every flag that visibility is not resolution.

WHAT IT READS, AND WHY NOT `TemporalPropertyGraph`
---------------------------------------------------
`GraphFacts` -- the by-value protocol `rule_engine.facts` established -- plus `Timeline`
values and the rule pack's `candidate_generation` block. Module 8 does not exist
(`CONTEXT.md` §3), so the temporal property graph this module is documented as reading
cannot be handed to it; `GraphFacts` is what module 8 will satisfy when it lands, without
this module changing. The structural-path generator consequently runs over zero
relationships today and reports zero rather than being quietly absent.
"""

from causalog.causal_engine.candidate_cause_generator.confounding import (
    CONFOUNDING_UNRESOLVED_NOTICE,
    ConfoundingFlag,
    ConfoundingStructure,
    detect_confounding,
)
from causalog.causal_engine.candidate_cause_generator.context import (
    CandidateGenerator,
    GenerationContext,
    GeneratorStatus,
    Proposal,
)
from causalog.causal_engine.candidate_cause_generator.gate import (
    GateOutcome,
    RejectionReason,
    RejectionTally,
    gate,
    gate_all,
)
from causalog.causal_engine.candidate_cause_generator.generate import (
    GenerationResult,
    generate_candidates,
)
from causalog.causal_engine.candidate_cause_generator.generators import (
    ALL_GENERATORS,
    ASSOCIATION_DISCLAIMER,
)
from causalog.causal_engine.candidate_cause_generator.graph import (
    CandidateGraph,
    RejectedProposal,
    TruncationRecord,
    apply_per_effect_cap,
)
from causalog.causal_engine.candidate_cause_generator.report import (
    CANDIDATE_GRAPH_SCHEMA_VERSION,
    RENDERED_TRUNCATION_ROWS,
    SAMPLED_CONFOUNDING_FLAGS,
    SATURATION_SHARE,
    CandidateGraphReport,
    GeneratorTally,
    PerEffectDistribution,
    render_markdown,
)

__all__ = [
    "ALL_GENERATORS",
    "ASSOCIATION_DISCLAIMER",
    "CANDIDATE_GRAPH_SCHEMA_VERSION",
    "CONFOUNDING_UNRESOLVED_NOTICE",
    "RENDERED_TRUNCATION_ROWS",
    "SAMPLED_CONFOUNDING_FLAGS",
    "SATURATION_SHARE",
    "CandidateGenerator",
    "CandidateGraph",
    "CandidateGraphReport",
    "ConfoundingFlag",
    "ConfoundingStructure",
    "GateOutcome",
    "GenerationContext",
    "GenerationResult",
    "GeneratorStatus",
    "GeneratorTally",
    "PerEffectDistribution",
    "Proposal",
    "RejectedProposal",
    "RejectionReason",
    "RejectionTally",
    "TruncationRecord",
    "apply_per_effect_cap",
    "detect_confounding",
    "gate",
    "gate_all",
    "generate_candidates",
    "render_markdown",
]
