"""Precedence that a source COMPUTED rather than recorded, carried as a measurement.

The problem this exists to name
-------------------------------
`core.temporal.verdict` answers whether one interval strictly precedes another. It is the
most conservative test available and it is correct. But it is a test over *bounds*, and
bounds say nothing about where they came from. When a source's second instant is arithmetic
on its first -- column B equals column A plus a recorded day count -- the two intervals
still satisfy `cause.t_latest < effect.t_earliest`, and `verdict` still answers `CERTAIN`.
It is answering honestly: the intervals really do not overlap. What it cannot see is that
they never *could* have, because one was computed from the other.

A `CERTAIN` verdict on such a pair therefore carries no information. It is guaranteed by
construction, not established by observation, and a confidence component that reads it as
evidence is reporting the source's arithmetic back to the reader as a finding.

Module 1 already measures this. A mapping may declare that one column is derived from
another, and the adapter tests the claim over every evaluable row rather than taking it on
trust -- producing an agreement rate and a residual histogram. That measurement stopped at
the data-quality report. This module is the shape it moves in, so a scorer can ask "is
this pair's precedence arithmetic?" and get a measured answer.

Why this type lives at L0
-------------------------
The measurement is made in `ingestion` and consumed in `causal_engine`, five ranks apart.
Routing the concrete result type across that distance would put a reasoning package's
import edge on a package that reads files. A plain value type at L0 -- which every layer
may import -- keeps the edge from existing at all. This is the pattern `core.ontology_view`
already establishes.

**The join key is an opaque locator, and this module never parses it.**
`TimeInterval.source` names what produced an interval's bounds. `temporal_binding_source`
is the one recipe for the locator a mapping-bound interval carries, and `precedence_for`
compares locators by STRING EQUALITY and nothing else. Never split it, never pattern-match
it, never recover a column name from it. Equality against an opaque provenance locator is a
question about lineage; parsing one would make this engine code that reads the source
description, which is domain arriving as a value (`docs/architecture.md` §1.5) and is the
one form of the leak the vocabulary lint cannot see.

**A pair is directed, and the direction is load-bearing.** The derived column is the LATER
one, so `effect_interval_source` is the column that was computed and `cause_interval_source`
is the column it was computed from. Storing an undirected pair would flag the reverse
precedence too, which is a different claim and one the measurement does not support.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "DerivedPrecedence",
    "DerivedPrecedenceIndex",
    "temporal_binding_source",
]


def temporal_binding_source(column: str) -> str:
    """Return the `TimeInterval.source` locator for an interval bound to a mapping column.

    The single definition of the recipe. `ingestion.schema_mapper.transforms.build_interval`
    stamps it onto every interval it builds and the index below reconstructs it to match;
    two copies of the format string would drift and the join would fail silently, which is
    the worst available failure -- an empty index reads exactly like a clean dataset.

    Note that `ingestion.schema_mapper.coverage` builds a superficially similar address
    without this prefix. That one is a coverage address and is deliberately NOT this recipe.
    """
    return f"mapping.temporal_bindings[{column}]"


class DerivedPrecedence(BaseModel):
    """One measured claim that a source computed the later instant from the earlier one.

    Every field is a measurement or an identifier; nothing here is a judgement. What the
    number MEANS for a confidence component is decided by a declared parameter in the pack,
    never here.

    Invariants:
      * `evaluated` is positive. A check with no evaluable rows has an `agreement_rate` of
        zero as a division guard, and admitting it would turn "not measured" into
        "measured false" -- the substitution this whole module exists to prevent.
      * The two locators differ. A column derived from itself is not a precedence claim.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The declaring check's identifier, quoted back to the reader so the finding is traceable.
    check_id: str = Field(min_length=1)
    #: The locator of the interval the later one was computed FROM.
    cause_interval_source: str = Field(min_length=1)
    #: The locator of the interval that was COMPUTED. The derived one.
    effect_interval_source: str = Field(min_length=1)
    #: Share of evaluable rows in which the declared derivation held exactly.
    agreement_rate: float = Field(ge=0.0, le=1.0)
    #: Rows the check could evaluate. The denominator, carried so the rate can be read.
    evaluated: int = Field(gt=0)
    #: `(residual seconds, row count)`, most frequent first. A clean split at one or two
    #: values is a parse artifact in the source; a spread is noise. The distinction is
    #: diagnostic and is why the histogram travels rather than just the rate.
    residual_seconds: tuple[tuple[int, int], ...] = ()
    #: False when the residual histogram overflowed its cap upstream and stopped being exact.
    residuals_exact: bool = True
    #: The mapping's own stated reason for suspecting the derivation.
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_invariants(self) -> DerivedPrecedence:
        """Enforce the documented invariants at construction."""
        if self.cause_interval_source == self.effect_interval_source:
            raise ValueError(
                "DerivedPrecedence names one locator as both sides of the pair; an "
                "interval derived from itself is not a precedence claim."
            )
        return self

    def sort_key(self) -> tuple[str, str, str]:
        """Return the canonical sequence key (`CONVENTIONS.md` §11)."""
        return (self.effect_interval_source, self.cause_interval_source, self.check_id)


class DerivedPrecedenceIndex(BaseModel):
    """Every confirmed derived precedence in one run, keyed for lookup by a scorer.

    An EMPTY index and NO index are different facts and are represented differently: this
    type empty means the measurement was supplied and confirmed nothing, and callers say
    "not supplied" by holding `None` instead of an instance. Collapsing the two would let a
    run with no measurement report as a run with clean data, which is the shape of every
    defect this codebase's NOT RUNNABLE vocabulary exists to keep visible.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Sorted by `DerivedPrecedence.sort_key`, so serialization is stable across runs.
    entries: tuple[DerivedPrecedence, ...] = ()

    @classmethod
    def of(cls, entries: tuple[DerivedPrecedence, ...]) -> DerivedPrecedenceIndex:
        """Return the index over these entries, sequenced canonically."""
        return cls(entries=tuple(sorted(entries, key=lambda entry: entry.sort_key())))

    def precedence_for(
        self, cause_interval_source: str, effect_interval_source: str
    ) -> DerivedPrecedence | None:
        """Return the entry for this DIRECTED pair of locators, or None.

        String equality on both sides, and nothing else. See the module docstring for why
        this function may never parse either argument.

        A pair whose direction is reversed does not match, and that is the point: the
        measurement says one instant was computed from the other, which is a claim about
        one direction only.
        """
        for entry in self.entries:
            if (
                entry.cause_interval_source == cause_interval_source
                and entry.effect_interval_source == effect_interval_source
            ):
                return entry
        return None

    @model_validator(mode="after")
    def _check_sequence(self) -> DerivedPrecedenceIndex:
        """Refuse an unsequenced index, so two runs cannot serialize differently."""
        keys = [entry.sort_key() for entry in self.entries]
        if keys != sorted(keys):
            raise ValueError(
                "DerivedPrecedenceIndex.entries is not in canonical sequence "
                "(CONVENTIONS.md §11); build it with DerivedPrecedenceIndex.of()."
            )
        # Keyed on the PAIR, not on `sort_key` -- `sort_key` carries `check_id`, so two
        # checks declaring the same pair would sort distinctly and slip past a sort-key
        # uniqueness test while still leaving `precedence_for` with no defined answer.
        pairs = [
            (entry.cause_interval_source, entry.effect_interval_source) for entry in self.entries
        ]
        if len(set(pairs)) != len(pairs):
            raise ValueError(
                "DerivedPrecedenceIndex.entries names one locator pair twice; the lookup "
                "would return whichever came first, which is not a defined answer."
            )
        return self
