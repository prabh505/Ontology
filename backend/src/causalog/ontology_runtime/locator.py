"""Translate a logical address inside a resolved pack back to a line in an authored file.

Validation runs over the **resolved** pack; the author edits an **authored** file. Between
the two sits inheritance, which can shift every index. So addresses are expressed with
identifiers rather than positions -- `("event_types", "SOME_TYPE", "participants", 0)` --
and this module maps the identifier back to whatever position it occupies in the file the
author actually has open.

When a declaration was inherited rather than written locally, no local line exists. The
locator then reports the nearest ancestor it can find, which is the `extends` document
itself. Pointing at the file that inherited a broken declaration is less precise than
pointing at the declaration, and considerably more useful than pointing at nothing.
"""

from __future__ import annotations

from pathlib import Path

from causalog.ontology_runtime.yaml_source import SourceDocument

__all__ = ["PackLocator"]

Address = tuple[str | int, ...]


class PackLocator:
    """Resolve an identifier-addressed path to a file and line across a pack chain."""

    __slots__ = ("_documents", "_index")

    def __init__(self, documents: tuple[SourceDocument, ...]) -> None:
        """Index every identified entry in every document of the chain."""
        # Later documents win: the overlay is where a reader expects to be sent.
        self._documents = documents
        self._index: dict[tuple[str, str], tuple[SourceDocument, int]] = {}
        for document in documents:
            for namespace, entries in document.data.items():
                if not isinstance(entries, list):
                    continue
                for position, entry in enumerate(entries):
                    if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                        self._index[namespace, entry["id"]] = (document, position)

    def locate(self, address: Address) -> tuple[Path | None, int | None]:
        """Return the file and line for an address, or `(None, None)` if unlocatable."""
        if not address:
            return self._fallback()
        namespace = address[0]
        if not isinstance(namespace, str) or len(address) < 2:
            return self._fallback()
        entry_id = address[1]
        if not isinstance(entry_id, str):
            return self._fallback()
        found = self._index.get((namespace, entry_id))
        if found is None:
            return self._fallback()
        document, position = found
        return document.path, document.line_for((namespace, position, *address[2:]))

    def _fallback(self) -> tuple[Path | None, int | None]:
        """Return the outermost document with no line, for an address nothing matches."""
        if not self._documents:
            return None, None
        return self._documents[-1].path, None
