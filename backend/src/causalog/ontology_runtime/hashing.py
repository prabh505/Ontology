"""`ontology_hash`: the content address of a resolved pack.

`ontology_hash` participates in `run_id` (ADR-0013), so it is not a convenience -- it is
half of what makes two conclusions comparable. Two runs over the same data with different
packs are different runs, and the identifier has to say so.

Computed over the **resolved** pack, through the canonical serializer, so the hash is:

  * invariant to comments, key sequence, indentation, and how the pack was split across a
    base and an overlay -- none of those changes what the pack means;
  * sensitive to every declared value -- a changed weight, a withdrawn state, a new
    transition all mint a new hash.

Nothing here re-implements hashing. `to_canonical_json` supplies the canonical bytes and
`digest` supplies the one hashing scheme (`docs/contracts.md` §2). A second hashing path
would be a second answer to "what is this pack", free to disagree with the first.
"""

from __future__ import annotations

from causalog.core.identifiers import IdentifierPrefix, digest
from causalog.core.serialization import to_canonical_json
from causalog.ontology_runtime.dsl import ResolvedPack

__all__ = ["ontology_hash"]


def ontology_hash(pack: ResolvedPack) -> str:
    """Return `ont:<sha256(canonical_pack)[:16]>` for a resolved pack."""
    return digest(IdentifierPrefix.ONTOLOGY, to_canonical_json(pack))
