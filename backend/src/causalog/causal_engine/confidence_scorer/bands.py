"""Bands, and the one outcome a band cannot express.

A scalar is not an instruction. "0.42" tells a reader nothing they can act on; "suggestive
-- worth investigating, not worth acting on alone" does. prd.md §49 forbids the unexplained
number, and the band is the half of that promise the interface keeps.

THE THRESHOLDS ARE NOT HERE
---------------------------
They are declared in the rule pack's `confidence_scoring.confidence_bands`, together with
the plain-language sentence each band carries (ADR-0053). A boundary written into engine
code -- and far worse, into UI code -- is a policy no reviewer of this repository can find,
that no test can pin, and that two screens showing one edge can silently disagree about.
This module reads the declaration and never supplies one: a pack that declares no bands gets
no labels, and the report says which knob is missing.

`INSUFFICIENT_EVIDENCE` IS NOT A BAND
--------------------------------------
It is a different OUTCOME, and this is the distinction the whole module is built around.
"This claim is weakly supported" is a measurement. "We did not measure enough to say" is the
absence of one, and a reader shown the second as though it were the first will act on a
number nobody computed. The same distinction already exists one layer down, between module
9's `NOT_RUNNABLE` and a generator that ran and found nothing; `ontology_runtime` introduced
a third severity for it; module 9's report refuses to collapse it. This is that refusal
carried into scoring.

An `INSUFFICIENT_EVIDENCE` edge still carries a full `ConfidenceVector` -- LAW-EVIDENCE is
not waivable and an empty vector is a defect. It carries no band, and it is never promoted.
"""

from __future__ import annotations

from enum import Enum

from causalog.rule_engine import ConfidenceBandSpec, ConfidenceScoringSpec

__all__ = ["BAND_ABSENT_NOTICE", "INSUFFICIENT_EVIDENCE_NOTICE", "ScoringOutcome", "band_for"]


class ScoringOutcome(str, Enum):
    """Whether an edge was scored at all, and if not, why not."""

    SCORED = "SCORED"
    """Enough components carried real support for the scalar to mean something."""

    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    """Too few components could be measured. **This is not a low score.**

    The scalar exists, because a vector without one is not constructible, and it must not
    be read as a weak claim. It is the arithmetic of a vector that is mostly absence.
    """


#: Carried verbatim wherever an `INSUFFICIENT_EVIDENCE` edge is rendered. Fixed text rather
#: than generated, so it cannot be softened per edge and so a reader who has seen it once
#: recognises it everywhere -- the same argument module 9 makes for `ASSOCIATION_DISCLAIMER`.
INSUFFICIENT_EVIDENCE_NOTICE = (
    "INSUFFICIENT EVIDENCE. Fewer components could be measured than this pack requires "
    "before it calls an edge scored. The scalar below is arithmetic over a vector that is "
    "mostly absence, and it is NOT a finding that the claim is weak -- it is a statement "
    "that not enough was measured to have a finding. Read the component breakdown: the "
    "components marked missing say what was never looked at."
)

#: Rendered where a band would go when the pack declares none.
BAND_ABSENT_NOTICE = (
    "No band. This rule pack declares no `confidence_scoring.confidence_bands`, so no "
    "plain-language label is available for this scalar. The engine does not supply one: a "
    "band boundary and its wording are domain policy, and inventing them here would put a "
    "judgement nobody authored in front of a reader (ADR-0053)."
)


def band_for(
    scalar: float,
    outcome: ScoringOutcome,
    parameters: ConfidenceScoringSpec,
) -> ConfidenceBandSpec | None:
    """Return the band this edge should be shown under, or None.

    None in three distinct situations, which the caller separates rather than merging:
    the outcome is `INSUFFICIENT_EVIDENCE` and no band applies; the pack declares no bands;
    or the scalar sits below every declared floor because the pack left a range unlabelled.
    """
    if outcome is ScoringOutcome.INSUFFICIENT_EVIDENCE:
        return None
    return parameters.band_for(scalar)
