"""What happens when two rules disagree, and what the operator is told about it (ADR-0047).

The policy, stated once and asserted by a test:

    **CONSTRAINTS BEAT GENERATORS.**

A generated firing whose bindings and consequent are prohibited by a constraint that fired
over the same bindings is suppressed. Not weighed, not averaged, not decided by whichever
rule carries the larger `base_strength` -- a weight is a strength of belief about a
claim, and a constraint is a statement of impossibility. Comparing the two is a category
error, and it would make impossibility purchasable with a large enough weight.

**The suppression is reported, never silent.** Every one becomes a `ConflictFinding` naming
both rule identifiers, the shared bindings, and the suppressed firing itself. The precedence
policy decides what the graph gets; the report decides what the operator sees; those are not
the same decision, and collapsing them is how a system comes to prune candidates nobody can
audit.

This matters more than it looks. An absent edge is the one kind of error this system cannot
otherwise surface -- `docs/architecture.md` §8 carries it as the second open risk, "recall is
bounded by rule coverage, and the system cannot report what it missed". A suppression that
is reported is one absence that is no longer silent.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from causalog.rule_engine.trace import RuleFiring

__all__ = ["ConflictFinding", "ConflictReport"]


class ConflictFinding(BaseModel):
    """One suppression: which generator, which constraint, over which bindings.

    The suppressed firing is carried whole rather than summarized. A reader deciding whether
    the constraint was right needs the same trace the firing would have shipped with, and
    reconstructing it from a summary is exactly the work the trace exists to save.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    suppressed_rule_id: str
    constraint_rule_id: str
    shared_bindings: tuple[tuple[str, str], ...]
    suppressed_firing: RuleFiring

    def render(self) -> str:
        """Return the one-line form for a report or a test failure."""
        bound = " ".join(f"{label}={value}" for label, value in self.shared_bindings)
        return f"{self.constraint_rule_id} suppressed {self.suppressed_rule_id} over [{bound}]"


class ConflictReport(BaseModel):
    """Every suppression from one evaluation, in canonical sequence.

    An empty report is a real finding -- no generator met a constraint -- and is not the
    same as no report. The evaluator always returns one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    findings: tuple[ConflictFinding, ...] = ()

    def is_empty(self) -> bool:
        """Return whether no rule was suppressed in this evaluation."""
        return not self.findings

    def suppressed_rule_ids(self) -> tuple[str, ...]:
        """Return every generating rule that lost to a constraint, sorted, without repeats."""
        return tuple(sorted({finding.suppressed_rule_id for finding in self.findings}))
