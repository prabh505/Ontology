"""Module 13 -- the Counterfactual Simulator. Graph surgery over frozen links, at L7.

prd.md §33 asks the engine to answer hypothetical questions and states one hard constraint:
"The engine simulates downstream changes without modifying historical records." This package
does that, and it says -- in the artifact rather than in a footnote -- exactly what the
answer is worth.

WHAT THIS MODULE STRUCTURALLY CANNOT DO
----------------------------------------
* **It cannot write to history.** Nothing here holds an `Event` it could modify: a
  hypothetical world contains `SimulatedEvent` and `SimulatedInstant`, which are separate
  shapes (ADR-0068). `core.immutability.revise` is never called on a base-world artifact,
  asserted over the AST, and `revise` itself refuses an `OBSERVED` artifact -- two
  independent mechanisms, neither depending on a call site remembering.
* **It cannot state a causal claim.** It constructs no `CausalEdge` and assigns no
  `INFERRED`. `causal_graph_builder/policy.py` is the one place in this engine that promotes
  a claim, and a simulator minting links would be a second opinion about what the graph
  contains.
* **It cannot produce a value that is not `SIMULATED`.** `ProvenanceClass.SIMULATED` is the
  weakest member of `WEAKEST_FIRST`, so `core.provenance.combine` makes containment
  arithmetic: anything touched by a simulated input is simulated, and a hypothetical cannot
  launder itself back into an inference.
* **It cannot simulate a world the ontology does not admit.** Every change is validated
  against the declared lifecycles, processes and changeable attributes first, and LAW-TIME
  is re-checked over the moved bounds. An impossible premise is refused rather than
  simulated and flagged, because every check after the premise would pass on it.
* **It cannot walk a graph the engine does not stand behind, unless a caller says so at the
  call site.** OQ-026, ADR-0072.

WHY A SIMULATED WORLD IS NOT A PREDICTION
------------------------------------------
It is backward-facing. It re-evaluates a world that already happened under a change that did
not, over links derived from rules, temporal structure and frequency rather than identified
as causal effects (prd.md §16, OQ-007). No counterfactual was observed and no confounder was
adjusted for. prd.md §62 rules that this system is not a model that predicts anything, and
`GLOSSARY.md` §2.6 says a session finding itself building one has left the product.

THE ERROR THIS MODULE EXISTS TO NOT MAKE
-----------------------------------------
**Removing one of three contributing causes does not prevent the outcome.** Elimination is a
re-reachability question -- does anything still transmit into this consequence -- and
reduction is what is left over when some causes stop and others do not. The two are computed
separately, reported in separate fields, counted separately, and never summed. Merging them
is the single most common counterfactual error and it produces a confident wrong answer with
every downstream check passing.

EVERY BOUND IS DECLARED
------------------------
Depth, node cap, support tolerance, sensitivity sweep and path composition all come from the
pack's `counterfactual_simulation` block (ADR-0071). An absent declaration means the policy
**cannot run**, is reported as a `PolicyGap` naming what it would have needed, and is never
defaulted (ADR-0049). The only numbers in this package are named ceilings, which bound a
declaration rather than substitute for one.
"""

from __future__ import annotations

from causalog.counterfactual_engine.context import (
    SimulationContext,
    SimulationLink,
    base_world_address,
    stated_links,
    unpromoted_links,
)
from causalog.counterfactual_engine.intervention import (
    ChangeAttribute,
    ChangeEntityState,
    InsertEvent,
    Intervention,
    InterventionKind,
    InterventionPayload,
    RejectedIntervention,
    RejectionReason,
    RemoveEvent,
    ShiftTiming,
)
from causalog.counterfactual_engine.propagate import (
    CONDITION_TEST_NOTICE,
    MAX_SIMULATION_DEPTH,
    ConditionStanding,
    Propagation,
    propagate,
)
from causalog.counterfactual_engine.report import (
    COUNTERFACTUAL_REPORT_SCHEMA_VERSION,
    CounterfactualReport,
    PolicyGap,
    build_report,
    render_markdown,
)
from causalog.counterfactual_engine.simulate import SimulationResult, simulate
from causalog.counterfactual_engine.validate import Admission, admit
from causalog.counterfactual_engine.validity import (
    NOT_CALIBRATED_NOTICE,
    Assumption,
    SensitivityFinding,
    SupportEnvelope,
    ValidityAssessment,
    ValidityVerdict,
    assess,
    standing_assumptions,
)
from causalog.counterfactual_engine.world import (
    DeltaKind,
    EventDelta,
    SimulatedEvent,
    SimulatedWorld,
    WorldDiff,
)

__all__ = [
    "CONDITION_TEST_NOTICE",
    "COUNTERFACTUAL_REPORT_SCHEMA_VERSION",
    "MAX_SIMULATION_DEPTH",
    "NOT_CALIBRATED_NOTICE",
    "Admission",
    "Assumption",
    "ChangeAttribute",
    "ChangeEntityState",
    "ConditionStanding",
    "CounterfactualReport",
    "DeltaKind",
    "EventDelta",
    "InsertEvent",
    "Intervention",
    "InterventionKind",
    "InterventionPayload",
    "PolicyGap",
    "Propagation",
    "RejectedIntervention",
    "RejectionReason",
    "RemoveEvent",
    "SensitivityFinding",
    "ShiftTiming",
    "SimulatedEvent",
    "SimulatedWorld",
    "SimulationContext",
    "SimulationLink",
    "SimulationResult",
    "SupportEnvelope",
    "ValidityAssessment",
    "ValidityVerdict",
    "WorldDiff",
    "admit",
    "assess",
    "base_world_address",
    "build_report",
    "propagate",
    "render_markdown",
    "simulate",
    "standing_assumptions",
    "stated_links",
    "unpromoted_links",
]
