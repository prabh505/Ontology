"""Which packs the repository ships, derived from the pack directory rather than a list.

Onboarding a new domain must touch `ontology/` and nothing else (`docs/ontology.md` §4).
A literal tuple in a test file breaks that: the pack loads, and no test loads the pack, so
the first thing anyone learns about a broken new domain is a failure somewhere downstream.
Three parameterisations used to carry that list, and the onboarding checklist used to
instruct the author to edit all three.

This module is imported at collection time rather than exposed as a fixture, because
`pytest.mark.parametrize` needs its values before fixtures exist.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["PACKS_ROOT", "discover_packs"]

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKS_ROOT = REPO_ROOT / "ontology" / "packs"

#: The authored document every pack directory must contain. Duplicated from
#: `causalog.ontology_runtime.PACK_DOCUMENT_NAME` deliberately: importing the distribution
#: here would make a collection-time glob depend on the package under test being importable,
#: and a discovery failure would then present as an import error rather than as itself.
PACK_DOCUMENT_NAME = "ontology.yaml"


def discover_packs() -> tuple[str, ...]:
    """Return every shipped pack id, sorted.

    Raises:
        RuntimeError: if the pack directory holds none. An empty discovery would
            parameterise zero tests, and zero tests report as a pass -- the DEF-0001 shape
            exactly, a check that cannot run being mistaken for a check that ran.
    """
    found = tuple(sorted(path.parent.name for path in PACKS_ROOT.glob(f"*/{PACK_DOCUMENT_NAME}")))
    if not found:
        raise RuntimeError(
            f"no pack found under {PACKS_ROOT}. Pack discovery drives three "
            f"parameterisations; an empty result would silently run none of them."
        )
    return found
