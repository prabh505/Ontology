"""Path confidence composition: how a chain's belief is derived from its links.

`core.aggregation` answers "how do one claim's components roll up into one number".
This module answers a different question that has the same shape and must not be confused
with it: **how do the numbers on a sequence of claims compose into a belief about the
sequence as a whole.** A chain is only as strong as its weakest link, and this is where
that sentence stops being a slogan and becomes a named function.

The three rules of `core.aggregation` are carried here unchanged, because the argument for
them is identical:

1. **The composition is derived, never authoritative.** The per-link vectors are the value.
   A composed scalar is a convenience for sequencing and display, and discarding it must
   never lose information -- which is why `PathConfidence` in the propagation package
   carries the link scalars alongside the composed one.
2. **The function is named in the artifact.** A consumer can recompute the composition and
   disagree with it. An unnamed rollup is the unexplained number prd.md §49 forbids, one
   level up from the level ADR-0009 forbade it at.
3. **Provenance does not compose the same way.** `core.provenance.combine` takes the
   weakest class present, whatever the arithmetic here produces.

WHY `weakest_link_v1` IS THE DEFAULT, in four parts, because a later session will otherwise
switch it to the product and believe that is the more principled choice.

**It is the doctrine this repository already holds, in a third place.**
`core.provenance.combine` returns the weakest input and never a stronger one.
`core.aggregation.minimum_v1` calls the minimum "the conservative rollup ... mirroring the
provenance algebra". Composing a chain by its weakest link is the same rule applied to a
sequence rather than to a set. Three mechanisms, one doctrine, and a reader who learns it
once has learned it everywhere.

**The product would be arithmetic with semantics these numbers do not have.** Multiplying
per-link values treats them as independent probabilities. They are neither. They are not
calibrated -- `CONTEXT.md` OQ-024 states that plainly, and states that nothing in this
repository can make them calibrated -- and consecutive links over one process instance
share evidence, so they are not independent either. Under a product a chain of six links
each scoring 0.9 composes to 0.53, and a chain of two links each scoring 0.7 composes to
0.49; the six-link chain would then outrank a chain no part of which is weaker than any
part of it. The number would be reporting path length while appearing to report belief.

**It is monotonically non-increasing along a path, and idempotent.** Extending a path by a
link at least as strong as the current minimum changes nothing, which is what "only as
strong as its weakest link" literally asserts. `tests/unit/core/test_composition.py`
asserts the monotonicity over generated inputs for every registered composer, so a future
addition that breaks it fails rather than ships.

**Its cost, stated here rather than discovered later.** The minimum ties heavily. On the
measured slice 310 scored links sit at exactly 0.400000, so many distinct chains compose to
one indistinguishable value -- `minimum_v1`'s own docstring already warns that "one weak
component pins every score to the floor", and the same is true of one weak link. Two
consequences follow and both are deliberate. `independent_product_v1` is registered beside
the default so a reader who wants the length-sensitive figure can have it, reported in its
own column and never blended into the first. And **path length is reported next to the
composed value, never folded into it** -- the ADR-0008 never-blend ruling, applied one level
down from the ruling itself.

Adding a composer is additive. Changing what an existing name computes is a breaking change,
which is why the shipped names carry a `_v1` suffix.

**No domain vocabulary appears below.** Nothing here knows what a link connects.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from types import MappingProxyType
from typing import Final, Protocol

from causalog.core.errors import ContractViolationError
from causalog.core.identifiers import FLOAT_QUANTIZATION_PLACES

__all__ = [
    "DEFAULT_COMPOSER",
    "PATH_COMPOSERS",
    "PathComposer",
    "compose",
    "independent_product_v1",
    "weakest_link_v1",
]


class PathComposer(Protocol):
    """A pure function from a sequence of per-link scalars to one composed scalar.

    Every composer must be **monotonically non-increasing**: composing a longer sequence
    that contains this one may never produce a larger value. That is not a style
    preference. A composition that could rise as a chain lengthens would let the engine
    claim more confidence about a longer inferential leap than about a shorter one, which
    is the opposite of what a chain of inference does to belief.
    """

    def __call__(self, link_values: Sequence[float]) -> float:  # pragma: no cover -- protocol
        """Return the composed scalar in `[0.0, 1.0]`."""
        ...


def _quantize(value: float) -> float:
    """Return the value rounded to the canonical float resolution.

    The same quantization `core.aggregation` applies, and for the same reason: the stored
    composed value must equal the recomputed one exactly, so a consumer checking the
    composition does not have to know a comparison tolerance.
    """
    quantum = Decimal(1).scaleb(-FLOAT_QUANTIZATION_PLACES)
    return float(Decimal(repr(value)).quantize(quantum))


def weakest_link_v1(link_values: Sequence[float]) -> float:
    """Return the smallest per-link value: the chain is as strong as its weakest link.

    The default, for the four reasons this module's docstring gives. Name-agnostic and
    unit-agnostic; it reads no field but the number.
    """
    return _quantize(min(link_values))


def independent_product_v1(link_values: Sequence[float]) -> float:
    """Return the product of the per-link values.

    Registered, reported beside the default, and **never blended with it**. This is the
    figure a reader gets when they want length sensitivity, and it carries the caveat the
    module docstring states: it treats the links as independent probabilities, and they are
    neither independent nor calibrated. It is monotonically non-increasing because every
    value lies in `[0.0, 1.0]`, which is what makes it admissible here at all.
    """
    composed = 1.0
    for value in link_values:
        composed = composed * value
    return _quantize(composed)


#: Registry keyed by name, as `core.aggregation.AGGREGATORS` is. The name travels with the
#: data; a consumer that has the name and the link values can recompute and disagree.
PATH_COMPOSERS: Final[Mapping[str, PathComposer]] = MappingProxyType(
    {
        "weakest_link_v1": weakest_link_v1,
        "independent_product_v1": independent_product_v1,
    }
)

#: Named rather than positional, so a pack that declares nothing still records WHICH
#: composition its numbers came from. Changing this constant does not reinterpret an
#: existing artifact: every artifact carries the name it was composed under.
DEFAULT_COMPOSER: Final[str] = "weakest_link_v1"


def compose(link_values: Sequence[float], composer_name: str = DEFAULT_COMPOSER) -> float:
    """Compose one path's per-link scalars into a single value under a named function.

    Raises:
        ContractViolationError: if `link_values` is empty, if any value falls outside
            `[0.0, 1.0]`, or if `composer_name` is not registered. An empty sequence is a
            defect and never "no confidence": a path with no links is not a path, and
            returning zero would put a manufactured number where an absence belongs. An
            unknown name is never silently replaced by the default, which would produce an
            artifact whose recorded composition misdescribes its own value.
    """
    if not link_values:
        raise ContractViolationError(
            "causalog.core.composition.compose requires at least one link value; a path "
            "with no links is not a path, and composing it to zero would report an "
            "absence as a measurement (LAW-EVIDENCE)."
        )
    outside = tuple(value for value in link_values if value < 0.0 or value > 1.0)
    if outside:
        raise ContractViolationError(
            f"causalog.core.composition.compose received value(s) outside [0.0, 1.0]: "
            f"{sorted(outside)}. Every registered composer's monotonicity guarantee rests "
            "on that range, and a value beyond it would silently break the guarantee "
            "rather than being refused."
        )
    if composer_name not in PATH_COMPOSERS:
        raise ContractViolationError(
            f"causalog.core.composition.compose received unknown composer "
            f"'{composer_name}'; registered names are {sorted(PATH_COMPOSERS)}."
        )
    return PATH_COMPOSERS[composer_name](tuple(link_values))
