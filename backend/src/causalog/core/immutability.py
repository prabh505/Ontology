"""The type-level guarantee that inference cannot mutate an observed fact.

LAW-PROVENANCE: "Inferred results never overwrite observed facts." Three mechanisms hold
that up, and they are layered because each one alone has a gap.

1. **Every canonical type is `frozen=True`.** Attribute assignment raises. This stops the
   direct mutation and nothing else.
2. **`revise` refuses an `OBSERVED` artifact.** Producing a modified copy is the way a
   frozen object is "changed", so the copy path needs the same guard the assignment path
   already has -- otherwise the freeze only moves the mutation one method along.
3. **Run scoping** (ADR-0013, `docs/architecture.md` §4.3). Inferred artifacts are written
   into run-scoped storage and observed facts into dataset-scoped storage, so an inference
   module is *incapable* of addressing an observed row rather than merely forbidden from
   it. That is enforced at the persistence boundary, not here, and it is the mechanism
   that survives someone deciding to bypass this module.

`revise` is the versioning path: a correction is a new version, never an edit (ADR-0004).
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

from causalog.core.errors import ContractViolationError, LawViolationError
from causalog.core.provenance import ProvenanceClass

__all__ = ["revise"]

ArtifactT = TypeVar("ArtifactT", bound=BaseModel)


def revise(artifact: ArtifactT, **updates: Any) -> ArtifactT:  # noqa: ANN401 -- field values are arbitrary by design
    """Return a new version of an artifact with some fields replaced.

    The replacement is fully re-validated, so a revision cannot reach a state the original
    constructor would have refused -- a `CausalEdge` cannot be revised into a LAW-TIME
    violation, and a `TimeInterval` cannot be revised into a naive datetime.

    The caller is responsible for supplying a recomputed identifier when the revision
    changes a field that participates in the content address. This function deliberately
    does not recompute it: the payload recipe differs per type (`CONVENTIONS.md` §9), and a
    helper that guessed would silently mint an identifier that disagrees with the recipe.

    Raises:
        LawViolationError: if the artifact carries `OBSERVED` provenance. An observed fact
            is what the source said; revising it does not correct the world, it discards
            the record of what was actually seen. A correction is a *new* artifact with its
            own provenance, sitting alongside the observation rather than on top of it.
        ContractViolationError: if `updates` is empty, or names a field the type does not
            declare. An unknown field would otherwise be dropped silently and the caller
            would believe a change was applied.
    """
    provenance = getattr(artifact, "provenance_class", None)
    if provenance is ProvenanceClass.OBSERVED:
        raise LawViolationError(
            f"LAW-PROVENANCE: refusing to revise an OBSERVED "
            f"{type(artifact).__name__}. An inferred result never overwrites an observed "
            "fact; record the correction as a new artifact alongside it (ADR-0004, "
            "ADR-0005)."
        )
    if not updates:
        raise ContractViolationError(
            f"causalog.core.immutability.revise called on {type(artifact).__name__} with "
            "no updates; a revision that changes nothing is a defect, not a copy."
        )
    unknown = sorted(set(updates) - set(type(artifact).model_fields))
    if unknown:
        raise ContractViolationError(
            f"causalog.core.immutability.revise received field(s) {unknown} that "
            f"{type(artifact).__name__} does not declare; an unknown field would be "
            "dropped silently and the change would appear to have been applied."
        )
    return type(artifact).model_validate({**dict(artifact), **updates})
