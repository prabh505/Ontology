"""One run's inputs to intervention recommendation, supplied by value.

Everything module 14 needs arrives as data. This package opens no connection, reads no
pack, and reaches through nothing: the `GraphFacts` protocol the rule engine established
carries the facts, `ontology_adapters` flattens the declarations, and a caller outside the
engine assembles both. Forbidden edge F3 makes that structural rather than tidy -- L7 may
not import `ontology_runtime` at all, so a cost class reaches this package as a name and a
rank or it does not reach it.

WHY TWO CONTEXTS RATHER THAN ONE
---------------------------------
`propagation` is module 12's context and `simulation` is module 13's. Module 14 holds both
because it asks both questions and must not answer either itself: what a node's removal
takes with it is module 12's `prevented_by_removing`, and what a change is worth is module
13's `simulate`. Merging them into one flattened context would have meant restating their
fields here, and a restated field is a field that can disagree with the one it copies.

Both carry a `GraphView`, and the two must be the same view. A recommendation whose benefit
was simulated over one graph and whose consequence was attributed over another is a
recommendation about no graph at all, so the invariant is checked here rather than trusted.

**No domain vocabulary appears below.**
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalog.causal_engine.causal_graph_builder import FeedbackLoop, JointCauseGroup
from causalog.causal_engine.propagation_analyzer import GraphStanding, PropagationContext
from causalog.core.errors import ContractViolationError
from causalog.core.ontology_view import ActionabilityView, OrdinalClassView
from causalog.counterfactual_engine import SimulationContext
from causalog.rule_engine.dsl import RecommendationSpec

__all__ = ["RecommendationContext", "vocabulary_rank", "vocabulary_span"]


def vocabulary_span(vocabulary: tuple[OrdinalClassView, ...]) -> int:
    """Return how many members an ordinal vocabulary holds.

    Zero for a pack that declares none. Callers pass this to
    `core.scalarization`, which refuses a span below one -- so an undeclared vocabulary is
    refused at the arithmetic rather than silently normalized against nothing.
    """
    return len(vocabulary)


def vocabulary_rank(vocabulary: tuple[OrdinalClassView, ...], class_id: str | None) -> int | None:
    """Return the rank of a named member, or `None` when it is absent or undeclared.

    `None` for an absent name is the whole point of ADR-0073: an undeclared operational risk
    ranks NOWHERE on that objective and costs the candidate its risk term. It is never read
    as the best member, which is what returning zero would have made it.

    `None` for a name the vocabulary does not hold cannot happen through a validated pack --
    the loader refuses a dangling reference -- and is handled anyway, because this function
    is also reachable from a hand-built context in a test.
    """
    if class_id is None:
        return None
    for member in vocabulary:
        if member.id == class_id:
            return member.rank
    return None


class RecommendationContext(BaseModel):
    """Module 14's inputs. Frozen, by value, and self-checking about the graph it walks.

    Fields, and why each is needed rather than derivable:

    * `propagation` -- module 12's context. Supplies the facts, the process instances, the
      adjacency, the declared measurements and the standing.
    * `simulation` -- module 13's context. Supplies the ontology declarations a hypothetical
      is validated against, which is what stops this module proposing an impossible act.
    * `actionability` -- per event type, whether an operator can act and at what cost,
      severity and operational risk. The one thing that decides whether a candidate may be
      recommended at all.
    * `cost_vocabulary` / `risk_vocabulary` / `severity_vocabulary` -- the ordinal
      vocabularies those class names are members of. Carried separately because a view that
      held its own lookup table would be a store (`core.ontology_view` says so).
    * `joint_groups` -- which contributors produce an effect only together. A cut set that
      split one of these would recommend an act that cannot work.
    * `loops` -- detected feedback loops over the event-TYPE projection, carrying their own
      `weakest_link_index`. Module 14 reads that index; it never re-detects a loop.
    * `outcome_event_ids` -- the outcomes worth protecting. Supplied rather than inferred:
      "which outcome matters" is a domain question and this engine has no standing to
      answer it.
    * `parameters` -- the pack's `recommendation` block. Every bound and every weight. An
      absent one means the policy cannot run and says which.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    propagation: PropagationContext
    simulation: SimulationContext
    actionability: tuple[ActionabilityView, ...] = ()
    cost_vocabulary: tuple[OrdinalClassView, ...] = ()
    risk_vocabulary: tuple[OrdinalClassView, ...] = ()
    severity_vocabulary: tuple[OrdinalClassView, ...] = ()
    joint_groups: tuple[JointCauseGroup, ...] = ()
    loops: tuple[FeedbackLoop, ...] = ()
    outcome_event_ids: tuple[str, ...] = ()
    parameters: RecommendationSpec
    run_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_one_graph(self) -> RecommendationContext:
        """Refuse two contexts that disagree about which graph this run is about."""
        walked = self.propagation.view.standing
        simulated = self.simulation.propagation.view.standing
        if walked is not simulated:
            raise ContractViolationError(
                f"RecommendationContext holds a propagation context standing at "
                f"{walked.value} and a simulation context standing at {simulated.value}. A "
                "recommendation whose consequence was attributed over one graph and whose "
                "benefit was simulated over another describes no graph at all, and the two "
                "figures printed beside each other would be about different worlds."
            )
        if self.simulation.run_id != self.run_id or self.propagation.run_id != self.run_id:
            raise ContractViolationError(
                "RecommendationContext holds contexts from different runs. Every inferred "
                "artifact is scoped to a run_id (ADR-0013), and mixing two runs would "
                "produce a recommendation traceable to neither."
            )
        return self

    @property
    def standing(self) -> GraphStanding:
        """Return the standing of the graph this run walks. Recorded on every artifact."""
        return self.propagation.view.standing

    def actionability_for(self, event_type: str) -> ActionabilityView | None:
        """Return the declaration for one event type, or `None` if the pack declares none.

        `None` is a refusal, not a lookup miss to be worked around: the caller turns it into
        a refused candidate naming the declaration that would have admitted it. ADR-0049's
        absent-means-CANNOT-RUN rule, in the direction that refuses.
        """
        for view in self.actionability:
            if view.event_type == event_type:
                return view
        return None
