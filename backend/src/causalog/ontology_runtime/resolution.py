"""Resolve a pack chain: a base pack plus an overlay, merged by identifier.

The merge rules are deliberately blunt, and the bluntness is the design (ADR-0027):

  * Entries merge **by identifier**, per namespace.
  * An overlay entry **replaces** the base entry wholesale. There is no field-level merge.
  * An identifier absent from the base is appended.
  * A base identifier is withdrawn only through an explicit `removes:` entry.

A deep merge would be friendlier to write and impossible to read: the effective declaration
would exist in no file, assembled from two, and an author reviewing either one would see
something other than what the engine loads. Whole-entry replacement means every effective
declaration is a block someone actually wrote.

Withdrawal is explicit for the same reason. If omission removed an inherited entry, then
"I did not think about this" and "I decided this does not apply" would be the same text.

The resolved pack is canonically sequenced by identifier in every namespace, so two packs
that declare the same things hash identically regardless of authoring sequence.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

from causalog.core.errors import ContractViolationError
from causalog.ontology_runtime.dsl import DomainPack, ResolvedPack

__all__ = ["MAX_CHAIN_DEPTH", "PACK_DOCUMENT_NAME", "resolve"]

#: The file every pack directory holds. Fixed rather than configurable: a seam whose
#: filename varies is a seam nobody can find (`docs/architecture.md` §5.1).
PACK_DOCUMENT_NAME = "ontology.yaml"

#: A chain longer than this is refused. Inheritance is meant to be one base plus one
#: overlay; a deep chain reproduces the readability problem whole-entry replacement exists
#: to avoid.
MAX_CHAIN_DEPTH = 8

_NAMESPACES: tuple[str, ...] = (
    "event_categories",
    "cost_classes",
    "severity_classes",
    "risk_classes",
    "entity_types",
    "relationship_types",
    "event_types",
    "external_event_types",
    "process_definitions",
    "measurement_definitions",
)

EntryT = TypeVar("EntryT")


def base_pack_path(pack_path: Path, base_pack_id: str) -> Path:
    """Return the document path of a base pack sitting beside `pack_path`'s directory."""
    return pack_path.parent.parent / base_pack_id / PACK_DOCUMENT_NAME


def _merge(
    base: tuple[EntryT, ...], overlay: tuple[EntryT, ...], withdrawn: tuple[str, ...]
) -> tuple[EntryT, ...]:
    """Apply one namespace's overlay and withdrawals to one namespace's base entries."""
    merged: dict[str, EntryT] = {getattr(entry, "id"): entry for entry in base}  # noqa: B009
    for identifier in withdrawn:
        merged.pop(identifier, None)
    for entry in overlay:
        merged[getattr(entry, "id")] = entry  # noqa: B009
    return tuple(merged[key] for key in sorted(merged))


def _withdrawals(pack: DomainPack, namespace: str) -> tuple[str, ...]:
    """Return the identifiers `pack` withdraws from `namespace`."""
    if pack.removes is None:
        return ()
    withdrawn: tuple[str, ...] = getattr(pack.removes, namespace)
    return withdrawn


def check_withdrawals(chain: tuple[DomainPack, ...]) -> tuple[str, ...]:
    """Return a message for every withdrawal naming an identifier its base never declared.

    A withdrawal that removes nothing is either a typo or a stale line left behind by a
    rename. Both read as deliberate, and neither is.
    """
    problems: list[str] = []
    available: dict[str, set[str]] = {namespace: set() for namespace in _NAMESPACES}
    for pack in chain:
        for namespace in _NAMESPACES:
            for identifier in _withdrawals(pack, namespace):
                if identifier not in available[namespace]:
                    problems.append(
                        f"pack '{pack.pack_id}' withdraws {namespace} '{identifier}', which "
                        "no pack it extends declares. A withdrawal that removes nothing is "
                        "a typo or a stale line, and both read as deliberate."
                    )
            available[namespace] -= set(_withdrawals(pack, namespace))
            available[namespace] |= {
                getattr(entry, "id")  # noqa: B009
                for entry in getattr(pack, namespace)
            }
    return tuple(problems)


def resolve(chain: tuple[DomainPack, ...]) -> ResolvedPack:
    """Fold a base-to-overlay chain into one canonically sequenced resolved pack.

    Args:
        chain: packs from outermost base to the authored overlay, which is last.

    Raises:
        ContractViolationError: if the chain is empty or exceeds `MAX_CHAIN_DEPTH`.
    """
    if not chain:
        raise ContractViolationError(
            "causalog.ontology_runtime.resolve was given an empty pack chain; there is "
            "nothing to resolve."
        )
    if len(chain) > MAX_CHAIN_DEPTH:
        raise ContractViolationError(
            f"pack chain is {len(chain)} deep; the limit is {MAX_CHAIN_DEPTH}. Inheritance "
            "is one base plus one overlay, not a hierarchy."
        )
    leaf = chain[-1]
    merged: dict[str, tuple[object, ...]] = {}
    for namespace in _NAMESPACES:
        accumulated: tuple[object, ...] = ()
        for pack in chain:
            accumulated = _merge(
                accumulated, getattr(pack, namespace), _withdrawals(pack, namespace)
            )
        merged[namespace] = accumulated
    return ResolvedPack(
        pack_schema_version=leaf.pack_schema_version,
        pack_id=leaf.pack_id,
        ontology_version=leaf.ontology_version,
        description=leaf.description,
        lineage=tuple(pack.pack_id for pack in chain[:-1]),
        **merged,  # type: ignore[arg-type]
    )
