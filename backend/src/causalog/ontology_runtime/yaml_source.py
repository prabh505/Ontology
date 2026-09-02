"""Read a pack document while remembering where every value came from.

`yaml.safe_load` throws away position information, so a validation failure over its output
can say what is wrong and not where. That is the difference between a validator someone uses
and one someone works around. This module loads the same documents through a loader that
records `start_mark` for every node, and publishes a path -> line index alongside the plain
data.

The index is keyed by the same tuple shape pydantic reports in `ValidationError.errors()[i]
["loc"]`, so joining the two is a lookup rather than a parse.

Only `yaml.SafeLoader` is ever used. A pack is untrusted input in the sense that matters
here -- it is data, and data never constructs Python objects (`yaml.Loader` would).

PyYAML ships no type stubs, so its node classes resolve to `Any` under `--strict`. They are
kept behind `Any`-typed parameters in this one module rather than pulling in a stub package,
which `CONVENTIONS.md` §12 would require an ADR for. Nothing outside this module sees an
untyped value: `SourceDocument` publishes plain data and a `dict` of integers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from causalog.core.errors import ContractViolationError

__all__ = ["SourceDocument", "read_document"]

_PathKey = tuple[str | int, ...]


class SourceDocument:
    """A parsed pack document plus the line index for every value inside it."""

    __slots__ = ("data", "lines", "path")

    def __init__(self, path: Path, data: Any, lines: dict[_PathKey, int]) -> None:  # noqa: ANN401
        """Hold a parsed document beside the line index built from its nodes."""
        self.path = path
        self.data = data
        self.lines = lines

    def line_for(self, address: _PathKey) -> int | None:
        """Return the line for an address, walking up to the nearest located ancestor.

        Walking up matters: pydantic reports the missing field, and a missing field has no
        node of its own. Its parent does, and pointing at the parent is far more useful than
        pointing at nothing.
        """
        probe = tuple(address)
        while probe:
            if probe in self.lines:
                return self.lines[probe]
            probe = probe[:-1]
        return self.lines.get(())


def _index(node: Any, prefix: _PathKey, lines: dict[_PathKey, int]) -> None:  # noqa: ANN401
    """Record `node`'s line at `prefix`, then recurse into its children."""
    lines[prefix] = node.start_mark.line + 1
    if isinstance(node, yaml.MappingNode):
        for key_node, value_node in node.value:
            if isinstance(key_node, yaml.ScalarNode):
                _index(value_node, (*prefix, str(key_node.value)), lines)
    elif isinstance(node, yaml.SequenceNode):
        for position, item in enumerate(node.value):
            _index(item, (*prefix, position), lines)


def read_document(path: Path) -> SourceDocument:
    """Parse one pack document, returning its data and its path -> line index.

    Raises:
        ContractViolationError: if the file is absent, is not valid YAML, or does not hold
            a mapping at the top level. None of the three is repaired -- a document that is
            not a mapping has no pack in it to validate.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ContractViolationError(
            f"causalog.ontology_runtime cannot read the pack at {path}: {error}."
        ) from error
    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.YAMLError as error:
        raise ContractViolationError(
            f"{path} is not valid YAML: {error}. A malformed pack is refused, never "
            "partially parsed."
        ) from error
    if root is None:
        raise ContractViolationError(
            f"{path} is empty; a pack declares at minimum its schema version and identity."
        )
    lines: dict[_PathKey, int] = {}
    _index(root, (), lines)
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ContractViolationError(
            f"{path} holds a {type(data).__name__} at the top level; a pack is a mapping."
        )
    return SourceDocument(path=path, data=data, lines=lines)
