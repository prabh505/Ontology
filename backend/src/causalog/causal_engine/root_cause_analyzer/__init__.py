"""Rank causes by consequence prevented and structural earliness (module 11).

FOUR QUESTIONS, FOUR ANSWERS, NEVER ONE NUMBER

prd.md §29 defines a root cause as the earliest ACTIONABLE event whose modification would
prevent the largest downstream consequence, and then gives the example that decides how this
module is built:

    external event -> knock-on effect -> controllable step -> downstream complaint
    "The [external event] may be earliest. The [controllable step] may be actionable.
     The system should distinguish both."

(prd.md §29's example, with two of its four node names replaced by their structural role.
The literal names are domain vocabulary and LAW-DOMAIN's lint refuses them here -- correctly,
because it is the SHAPE and not the vocabulary that ADR-0008 turns on.)

ADR-0008 ruled on it. Earliness and prevented consequence are not commensurable; any
weighting between them would be an unexplainable constant; LAW-EVIDENCE forbids a number
whose parts cannot be inspected. So this module emits **four separately labelled fields** --
`earliest_cause`, `highest_consequence_cause`, `most_actionable_cause` and
`actionable_root_causes` -- and there is no fifth field collapsing them and no method
returning "the" root cause. **Wherever two of them name different events a `TradeOff` is
emitted** saying which two, what each is answering, and what preferring one gives up, so a
user who disagrees with the recommendation can see the alternative and why it lost.

There is deliberately **no root-cause score anywhere in this package**. Not an omission: the
number would have to weight a quantity against a position in a chain, so any figure produced
would be a judgement disguised as arithmetic. `sequencing_value` is ADR-0008's literal
prevented-times-confidence criterion, names the function that produced it, and is one of
five signals carried side by side -- not a score for the cause.

FIVE SIGNALS, CARRIED SEPARATELY

Each `RankedCause` holds what the graph says stops occurring if it is removed
(counterfactual-lite, correct on diamonds by re-reachability rather than by subtraction);
whether it is actionable, refined but never overridden by the declared cost and severity
ranks; its structural earliness, which is a TIE-BREAK and never a term; belief about the
chain joining it to the outcome, composed under a named function with its length beside it;
and how often the shape recurs across the run. Every one of them carries its evidence chain
and its whole `ConfidenceVector`, never a scalar.

ACTIONABILITY IS DECLARED AND CANNOT BE VALIDATED

`Event.is_actionable` is stamped at generation time (ADR-0008) precisely so that this module,
at L6, never reads the ontology -- forbidden edge F3. The declared cost and severity arrive
as flattened `core.ontology_view` values and refine a set the boolean has already selected;
they never promote an unactionable event into it. Where the stamp and the current pack
disagree the disagreement is REPORTED and the stamp is used, because silently preferring
either would move the headline answer with nothing recording that it had. And R-15 stands
unmitigated: a mis-declared flag changes the recommendation and nothing here can detect it,
which is printed above every ranking as a property that no revision can soften.

WHAT THIS MODULE STRUCTURALLY CANNOT DO

It creates no link: `CausalEdge` is never constructed here and `ProvenanceClass.INFERRED` is
never assigned here, asserted over the AST by `tests/law/test_ranking_never_collapses.py`.
It returns no single answer where four are contractually required, enforced by the type. It
sequences on no bare scalar: `RankedCause.sort_key` is a tuple whose elements a reader can
read off one at a time. And it reports a PLATEAU as a plateau -- where every recommended
candidate carries one sequencing value the engine cannot separate them, and any sequence
imposed is arbitrary and says so.
"""

from causalog.causal_engine.root_cause_analyzer.analyze import (
    CANDIDATE_SEARCH_CEILING,
    RootCauseResult,
    analyze_root_causes,
)
from causalog.causal_engine.root_cause_analyzer.context import RootCauseContext
from causalog.causal_engine.root_cause_analyzer.ranking import (
    ActionabilityStanding,
    RankedCause,
    Recurrence,
)
from causalog.causal_engine.root_cause_analyzer.recurrence import recurrence_of
from causalog.causal_engine.root_cause_analyzer.report import (
    ACTIONABILITY_UNVALIDATED_NOTICE,
    ROOT_CAUSE_REPORT_SCHEMA_VERSION,
    RootCauseRanking,
    RootCauseReport,
    build_report,
    render_markdown,
)
from causalog.causal_engine.root_cause_analyzer.views import (
    TradeOff,
    ViewName,
    earliest,
    highest_consequence,
    most_actionable,
    recommended,
    trade_offs,
)

__all__ = [
    "ACTIONABILITY_UNVALIDATED_NOTICE",
    "CANDIDATE_SEARCH_CEILING",
    "ROOT_CAUSE_REPORT_SCHEMA_VERSION",
    "ActionabilityStanding",
    "RankedCause",
    "Recurrence",
    "RootCauseContext",
    "RootCauseRanking",
    "RootCauseReport",
    "RootCauseResult",
    "TradeOff",
    "ViewName",
    "analyze_root_causes",
    "build_report",
    "earliest",
    "highest_consequence",
    "most_actionable",
    "recommended",
    "recurrence_of",
    "render_markdown",
    "trade_offs",
]
