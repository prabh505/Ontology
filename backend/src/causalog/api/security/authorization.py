"""The permission matrix (prd.md §54), as data.

prd.md §54 says "Role-based access" and enumerates nothing. prd.md §10 names five user
types and the document names no sixth anywhere, so the roles are those five and only those
five -- inventing an administrator would be inventing a requirement (`CONVENTIONS.md` §4),
and the gap that creates is recorded as an open question rather than filled silently. See
`ADMINISTRATIVE_CAPABILITIES` below.

**The matrix is data, not decorators.** A capability declared with `@requires_role("...")`
on each handler is a matrix nobody can read: answering "what can an executive do" means
grepping every route file and trusting that you found them all. Here it is one table, a
test enumerates every (role, capability) pair against it, and a second test fails if any
route declares a capability this table does not govern. That is what makes the matrix
*documented* in the sense §54 needs rather than merely implemented.

**Why capabilities and not endpoints.** A matrix keyed by route path has to be edited every
time a path is added, and the edit is invisible if forgotten -- the new route simply has no
row. Keyed by capability, a new route must name one of a closed set, and naming a
capability is a decision a reviewer can see in the diff.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

from causalog.core.ports.identity import Role

__all__ = [
    "ADMINISTRATIVE_CAPABILITIES",
    "PERMISSIONS",
    "Capability",
    "permitted",
    "roles_with",
]


class Capability(Enum):
    """What an operation needs, as a closed set.

    The distinctions that carry weight:

    * `READ_OBSERVED` vs `READ_INFERRED` -- LAW-PROVENANCE's line drawn in access control.
      Reading what was observed and reading what the engine concluded are different acts,
      and only the second is audited as an inference access (`CONVENTIONS.md` §8).
    * `READ_DIAGNOSTIC` is separate from `READ_INFERRED` and is the narrowest read
      capability here. It reaches the `UNPROMOTED_DIAGNOSTIC` standing -- output the engine
      explicitly disowns (ADR-0059). OQ-026 records that its four structural defences do
      not survive a screenshot; restricting who can produce the screenshot is the one
      further defence an API can add.
    * `SIMULATE` is separate from every read. A counterfactual is the most expensive
      operation on this surface and the easiest to misread as a prediction (OQ-007), so who
      may run one is a decision rather than a consequence of being able to read a graph.
    """

    READ_OBSERVED = "READ_OBSERVED"
    READ_INFERRED = "READ_INFERRED"
    READ_DIAGNOSTIC = "READ_DIAGNOSTIC"
    READ_EVIDENCE = "READ_EVIDENCE"
    READ_RULES = "READ_RULES"
    READ_RECOMMENDATIONS = "READ_RECOMMENDATIONS"
    SIMULATE = "SIMULATE"
    MUTATE_DATASET = "MUTATE_DATASET"
    EXECUTE_PIPELINE = "EXECUTE_PIPELINE"
    DELETE_INFERRED = "DELETE_INFERRED"


#: The capabilities prd.md gives no holder. Named here so the gap is visible in code and
#: not only in `CONTEXT.md` §8: prd.md §10's five user types are all *consumers* of
#: analysis, and none of them is described as administering the system. The defaults below
#: give them to `DATA_SCIENTIST` (the only §10 type whose stated need -- "causal graphs and
#: supporting evidence" -- implies producing runs) and `EXECUTE_PIPELINE` additionally to
#: `PROCESS_IMPROVEMENT`. That is a proposed default awaiting a product owner's ruling, not
#: a decision this layer is entitled to make.
ADMINISTRATIVE_CAPABILITIES: Final[frozenset[Capability]] = frozenset(
    {
        Capability.MUTATE_DATASET,
        Capability.EXECUTE_PIPELINE,
        Capability.DELETE_INFERRED,
    }
)


def _grants() -> dict[Role, frozenset[Capability]]:
    """Build the matrix. A function so the reasoning sits beside each row.

    Read this as five answers to "what does prd.md §10 say this person needs?", because
    that is the only evidence available and inventing more would be inventing requirements.
    """
    read_operational = {
        Capability.READ_OBSERVED,
        Capability.READ_INFERRED,
        Capability.READ_EVIDENCE,
        Capability.READ_RULES,
    }
    return {
        # "Needs rapid explanation of operational failures." Reads inferences and the rules
        # behind them; does not simulate, because a counterfactual is not an explanation of
        # what happened (prd.md §37's non-conflation), and does not administer.
        Role.OPERATIONS_MANAGER: frozenset(read_operational | {Capability.READ_RECOMMENDATIONS}),
        # "Needs historical investigation." The broadest READ role: investigation is
        # exactly the activity that needs the disowned diagnostic view, and it is the one
        # §10 type whose stated need cannot be met without seeing what fell short.
        Role.HISTORICAL_ANALYST: frozenset(
            read_operational | {Capability.READ_DIAGNOSTIC, Capability.READ_RECOMMENDATIONS}
        ),
        # "Needs strategic patterns rather than individual incidents." Deliberately NOT
        # granted READ_DIAGNOSTIC: OQ-026's risk is a disowned figure quoted as a finding,
        # and the executive summary is where that quotation does the most damage.
        Role.EXECUTIVE: frozenset(
            {
                Capability.READ_OBSERVED,
                Capability.READ_INFERRED,
                Capability.READ_RECOMMENDATIONS,
            }
        ),
        # "Needs causal graphs and supporting evidence." Everything, including the
        # administrative capabilities, under the proposed default above.
        Role.DATA_SCIENTIST: frozenset(Capability),
        # "Needs intervention opportunities." Simulation and recommendations are its
        # subject matter; it may run a pipeline but may not delete a run's inferences or
        # change a dataset.
        Role.PROCESS_IMPROVEMENT: frozenset(
            read_operational
            | {
                Capability.READ_RECOMMENDATIONS,
                Capability.SIMULATE,
                Capability.EXECUTE_PIPELINE,
            }
        ),
    }


#: The published matrix. Rendered into `docs/api.md` from this value rather than retyped,
#: so the document and the enforcement cannot disagree.
PERMISSIONS: Final[dict[Role, frozenset[Capability]]] = _grants()


def permitted(role: Role, capability: Capability) -> bool:
    """Return whether a role holds a capability.

    Total over both enums: a role absent from the matrix holds nothing, which is the safe
    direction. It cannot happen -- a test enumerates `Role` against `PERMISSIONS` -- and the
    `.get` is here so that if it ever does, the failure is a refusal rather than a KeyError
    surfacing as a 500.
    """
    return capability in PERMISSIONS.get(role, frozenset())


def roles_with(capability: Capability) -> tuple[Role, ...]:
    """Return every role holding a capability, in declaration sequence."""
    return tuple(role for role in Role if permitted(role, capability))
