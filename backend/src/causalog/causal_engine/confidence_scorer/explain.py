"""`ComponentExplanation` -- the sentence beside the number, and the caveat beside that.

prd.md §49: "Confidence should never be represented by a single unexplained number." The
core type carries the decomposition; `ConfidenceComponent` is named, valued, provenance-
classed and traced to evidence. That is the audit trail. It is not yet an explanation: a
reader looking at `historical_support = 0.31` still cannot tell whether the pattern was
seen twice or two thousand times, what it was compared against, or why the number is not
higher.

This type is that missing half, and it is deliberately NOT a field on `ConfidenceComponent`.
`causalog.core` is frozen (ADR-0025), and prose is the wrong thing to freeze -- the wording
here will be revised many times and none of those revisions should be a core contract
change. So the explanation travels beside the vector, keyed by component name, inside
module 10's own output.

THREE FIELDS THAT ARE NOT DECORATION
------------------------------------
* `missing` distinguishes "we looked and found no support" from "we could not look".
  `ontology_runtime` introduced a third severity for exactly this confusion and module 9's
  report refuses to collapse `NOT_RUNNABLE` into zero; this is the same distinction one
  layer on. A missing component still scores zero -- absence costs confidence, it does not
  abstain -- but it is reported as missing and the report counts it.
* `caveats` is a tuple, not a sentence. A caveat that can be softened per edge is a caveat
  nobody reads twice, which is why `ASSOCIATION_DISCLAIMER` is a fixed string in module 9
  and why it is carried verbatim here.
* `inputs` is the arithmetic, as `(name, value)` pairs. A reader who wants to disagree with
  0.31 needs the counts that produced it, not a paraphrase of them.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from causalog.core.identifiers import format_float

__all__ = ["ComponentExplanation"]


class ComponentExplanation(BaseModel):
    """Why one component holds the value it holds, in words and in numbers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    component_name: str = Field(min_length=1)
    #: One sentence a non-engineer can read, stating what was measured.
    plain_language: str = Field(min_length=1)
    #: What this number does NOT establish. Never empty for a statistical component.
    caveats: tuple[str, ...] = ()
    #: The arithmetic, as `(label, value)` pairs in authored sequence. Floats are already
    #: rendered through `format_float`, so the explanation and the artifact agree digit for
    #: digit rather than differing by a rounding nobody declared.
    inputs: tuple[tuple[str, str], ...] = ()
    #: True when the data needed to compute this component was not available. The component
    #: is still emitted, still scores zero, and is still counted -- as missing.
    missing: bool = False
    #: Populated only when `missing` is True: what would have to exist for it to be scored.
    requirement: str | None = None

    @classmethod
    def absent(cls, component_name: str, requirement: str) -> ComponentExplanation:
        """Return the explanation for a component whose data could not be reached.

        The wording is fixed rather than generated per component, so that a reader who has
        seen one missing component recognises every other one on sight.
        """
        return cls(
            component_name=component_name,
            plain_language=(
                f"Not scored: {component_name} could not be computed for this edge, so it "
                "contributes nothing. This is an absence of measurement, not a measurement "
                "of absence -- the edge is scored lower for it, and the gap is reported "
                "rather than hidden."
            ),
            missing=True,
            requirement=requirement,
        )

    @staticmethod
    def number(label: str, value: float) -> tuple[str, str]:
        """Return one `(label, value)` input pair with the value canonically formatted."""
        return (label, format_float(value))

    @staticmethod
    def count(label: str, value: int) -> tuple[str, str]:
        """Return one `(label, value)` input pair for a whole count."""
        return (label, str(value))
