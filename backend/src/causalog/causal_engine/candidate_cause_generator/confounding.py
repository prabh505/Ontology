"""Making confounding VISIBLE. Nothing here resolves it, and nothing at V1 can.

prd.md §59 names "hidden confounders" as a risk that "must be explicitly surfaced to
users", and `CONTEXT.md` R-05 records it as "cannot be mitigated, only disclosed". This
module is the disclosure: it walks the candidate multigraph for two structures that are
*classically* the shapes under which an association is explained by something other than a
direct effect, and flags them.

TWO STRUCTURES
--------------
Both are purely structural -- graph shape over already-gated candidates, no arithmetic, no
threshold, no judgement:

* **`POSSIBLE_MEDIATION`** -- `X -> Z` exists, and so do `X -> Y` and `Y -> Z`. The direct
  claim `X -> Z` may be wholly or partly *carried through* Y. Flagged on the `X -> Z`
  candidates.
* **`POSSIBLE_COMMON_CAUSE`** -- `X -> Y` and `X -> Z` exist, and so does `Y -> Z`. The
  `Y -> Z` association may be explained by their shared parent X rather than by any effect
  of Y on Z. Flagged on the `Y -> Z` candidates.

WHAT A FLAG IS AND IS NOT
-------------------------
A flag is a **separate artifact** referencing candidate identifiers. It never mutates an
edge, never removes one, and never reduces one -- candidates are frozen and per-generator,
and a module forbidden from ranking is equally forbidden from de-ranking.

A flag is also **not a finding of confounding**. It says: this triple has the shape under
which confounding would be indistinguishable from a direct effect *in these data*, and the
system cannot tell the two apart. The absence of a flag is emphatically not a finding of NO
confounding: an unobserved common cause leaves no shape in a graph built only from observed
events, and that is precisely why R-05 is disclosed rather than mitigated.

DETERMINISM AND COST
--------------------
Both walks are over sorted adjacency built from sorted candidates, so two runs produce one
result. The triple enumeration is bounded by the per-effect cap that `graph.py` has already
applied, which is what keeps it from becoming cubic in the event count.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from causalog.core.types import CandidateEdge

__all__ = [
    "CONFOUNDING_UNRESOLVED_NOTICE",
    "ConfoundingFlag",
    "ConfoundingStructure",
    "detect_confounding",
]

#: Carried verbatim on every flag. Fixed rather than generated, so it cannot be softened
#: per-flag and so a reader who has seen it once recognises it everywhere.
CONFOUNDING_UNRESOLVED_NOTICE = (
    "This flag makes a structure visible; it does not resolve it. Nothing in V1 "
    "distinguishes a direct effect from one explained by the third event, and the absence "
    "of a flag is not evidence of no confounding -- an unobserved common cause leaves no "
    "shape in a graph built from observed events (prd.md §59, CONTEXT.md R-05)."
)


class ConfoundingStructure(str, Enum):
    """The closed set of structures this module can see."""

    POSSIBLE_MEDIATION = "POSSIBLE_MEDIATION"
    """`X -> Z` may be carried through `Y`, because `X -> Y` and `Y -> Z` both exist."""

    POSSIBLE_COMMON_CAUSE = "POSSIBLE_COMMON_CAUSE"
    """`Y -> Z` may be explained by shared parent `X`, because `X -> Y` and `X -> Z` exist."""


class ConfoundingFlag(BaseModel):
    """One visible structure, naming the three events and the candidates that form it.

    `flagged_candidate_ids` are the candidates whose interpretation the structure bears on
    -- the `X -> Z` edges for mediation, the `Y -> Z` edges for a common cause. Plural
    because the graph is a multigraph: several generators may have proposed the same pair,
    and the structure bears on every one of their proposals equally.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    structure: ConfoundingStructure
    #: The third event: the mediator, or the shared parent.
    third_event_id: str
    source_event_id: str
    target_event_id: str
    flagged_candidate_ids: tuple[str, ...] = Field(min_length=1)

    @property
    def notice(self) -> str:
        """Return the fixed statement that visibility is not resolution.

        A property over a module constant rather than a stored field, and the difference is
        not cosmetic. Storing it put the same 400-character string on every flag: on a
        150-row slice of the reference dataset that is 68,580 copies and a 38 MB artifact,
        which is a committed report nobody can open. It also achieved nothing the constant
        does not -- the reason for attaching it was that it must not be softenable per flag,
        and there is exactly one of it either way.

        Every flag still carries the notice when a reader holds one. It is simply not
        serialized 68,580 times to say one thing once.
        """
        return CONFOUNDING_UNRESOLVED_NOTICE

    def sort_key(self) -> tuple[str, str, str, str]:
        """Return the canonical sequence key (`CONVENTIONS.md` §11)."""
        return (
            self.structure.value,
            self.source_event_id,
            self.target_event_id,
            self.third_event_id,
        )


def detect_confounding(candidates: tuple[CandidateEdge, ...]) -> tuple[ConfoundingFlag, ...]:
    """Return every visible structure over the candidate multigraph, in canonical sequence.

    The candidates are reduced to a plain edge set first: both structures are properties of
    the PAIRS, not of the parallel proposals over them. Reducing keeps the enumeration over
    unique pairs, while each flag still names every parallel candidate the structure bears
    on -- a mediation finding about `X -> Z` bears equally on the rule-based proposal and
    the proximity proposal over that pair.

    **One triangle produces BOTH flags, and that is correct rather than redundant.** Given
    `X -> Y`, `Y -> Z` and `X -> Z` all proposed, there are two distinct readings and the
    data cannot separate them: the `X -> Z` claim may be carried through Y (mediation), and
    the `Y -> Z` claim may be explained by the shared parent X (common cause). Emitting one
    and not the other would be choosing between them, which is a resolution this module is
    explicitly not able to make. They are emitted as two flags on two different pairs.
    """
    pairs: dict[tuple[str, str], list[str]] = {}
    for candidate in candidates:
        key = (candidate.source_event_id, candidate.target_event_id)
        pairs.setdefault(key, []).append(candidate.candidate_edge_id)
    edges = {key: tuple(sorted(value)) for key, value in sorted(pairs.items())}

    successors: dict[str, list[str]] = {}
    for source, target in sorted(edges):
        successors.setdefault(source, []).append(target)

    flags: list[ConfoundingFlag] = []
    for first, second in sorted(edges):
        for third in successors.get(second, ()):
            if third == first or (first, third) not in edges:
                continue
            # The triangle first -> second -> third with first -> third also present.
            flags.append(
                ConfoundingFlag(
                    structure=ConfoundingStructure.POSSIBLE_MEDIATION,
                    third_event_id=second,
                    source_event_id=first,
                    target_event_id=third,
                    flagged_candidate_ids=edges[(first, third)],
                )
            )
            flags.append(
                ConfoundingFlag(
                    structure=ConfoundingStructure.POSSIBLE_COMMON_CAUSE,
                    third_event_id=first,
                    source_event_id=second,
                    target_event_id=third,
                    flagged_candidate_ids=edges[(second, third)],
                )
            )
    unique = {flag.sort_key(): flag for flag in flags}
    return tuple(unique[key] for key in sorted(unique))
