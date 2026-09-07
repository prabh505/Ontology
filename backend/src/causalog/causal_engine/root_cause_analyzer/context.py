"""Everything module 11 reads, supplied by value, never fetched.

The shape modules 9, 10, 12 and the Causal Graph Builder established, and for the same two
reasons: forbidden edge F4 means no reasoning package may reach a store, and a context
assembled by the caller is a context a test can build by hand.

`actionability`, `cost_classes` and `severity_classes` arrive as `core.ontology_view` values
produced by `extraction.ontology_adapters`. ADR-0008 rules that this module reads a field on
a canonical type and never learns that an ontology exists -- and `Event.is_actionable` is
that field. These views carry what the boolean cannot: prd.md §29 asks which actionable
event to change, and two actionable events differ in what changing them costs. **The boolean
on the event remains authoritative**; the views only refine a set the boolean has already
selected, and a disagreement between them is reported rather than resolved.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from causalog.causal_engine.propagation_analyzer import PropagationContext
from causalog.core.ontology_view import ActionabilityView, OrdinalClassView
from causalog.core.types import Event
from causalog.rule_engine import RootCauseAnalysisSpec

__all__ = ["RootCauseContext"]


class RootCauseContext(BaseModel):
    """One run's inputs to root cause ranking.

    Fields, and why each is needed rather than derivable:

    * `propagation` -- module 12's context, carried whole rather than unpacked. Ranking asks
      counterfactual questions of the same graph the propagation walked, under the same
      bounds, so the two must not be able to disagree about which graph or which depth.
      One context means one answer.
    * `actionability` -- the declared cost and severity beside the flag. See above.
    * `cost_classes` / `severity_classes` -- the ordinal vocabularies those names resolve
      against. Held here rather than inside the views because a view that carried its own
      lookup table would be a store.
    * `parameters` -- the pack's `root_cause_analysis` block. An absent declaration means
      the policy cannot run and is reported, never defaulted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    propagation: PropagationContext
    actionability: tuple[ActionabilityView, ...] = ()
    cost_classes: tuple[OrdinalClassView, ...] = ()
    severity_classes: tuple[OrdinalClassView, ...] = ()
    parameters: RootCauseAnalysisSpec
    run_id: str = Field(min_length=1)

    _actionability_by_type: dict[str, ActionabilityView] | None = PrivateAttr(default=None)

    def declaration_for(self, event_type: str) -> ActionabilityView | None:
        """Return one type's actionability declaration, or None if the pack omits it."""
        if self._actionability_by_type is None:
            self._actionability_by_type = {view.event_type: view for view in self.actionability}
        return self._actionability_by_type.get(event_type)

    def cost_rank(self, event_type: str) -> int | None:
        """Return the declared cost rank of acting on this type, or None if undeclared.

        `None` is returned for three different situations -- no declaration, an
        unactionable type, and a cost naming a class the vocabulary omits -- and the caller
        reports which. They are collapsed here only because all three mean the same thing
        to the arithmetic: there is no rank to compare.
        """
        declared = self.declaration_for(event_type)
        if declared is None or declared.cost_class is None:
            return None
        for member in self.cost_classes:
            if member.id == declared.cost_class:
                return member.rank
        return None

    def severity_rank(self, event_type: str) -> int | None:
        """Return the declared severity rank of this type, or None if undeclared."""
        declared = self.declaration_for(event_type)
        if declared is None:
            return None
        for member in self.severity_classes:
            if member.id == declared.severity_class:
                return member.rank
        return None

    def declares_actionable(self, event: Event) -> bool | None:
        """Return what the PACK says about this event's type, for cross-checking the stamp.

        `None` means the pack declares nothing for the type. The event's own
        `is_actionable` is what ranking uses either way (ADR-0008); this exists so a
        disagreement between the stamp and the current pack can be REPORTED. A run whose
        events were generated under an earlier ontology is exactly the situation where the
        two diverge, and a silent divergence would move the headline answer with nothing
        recording that it had.
        """
        declared = self.declaration_for(event.event_type)
        return None if declared is None else declared.actionable
