"""Load a mapping document, refuse a proposal, and assess its coverage.

Two refusals live here, and both are refusals rather than warnings on purpose.

**A proposal never loads.** `status: PROPOSED_UNCONFIRMED` is written by the auto-suggester
and removed by a human in a commit. If loading a proposal merely warned, the warning would
be read once and the machine's guesses would be in production by the following week. The
whole confirmation mechanism is this one check, so it is a hard error with a message that
says exactly what to do.

**A mapping with coverage errors never loads.** `OntologyMappingError` is the existing
member of the closed taxonomy for exactly this (`core/errors.py`), and every error is
reported together with its downstream consequence rather than one per reload.

Line numbers come from `ontology_runtime.yaml_source`, which already solves "say WHERE, not
just what". Reusing it is deliberate: a second YAML reader would be a second answer to what
a document says, free to disagree with the first.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from causalog.core.errors import ContractViolationError, OntologyMappingError
from causalog.ingestion.schema_mapper.coverage import CoverageReport, assess_coverage
from causalog.ingestion.schema_mapper.dsl import (
    MAPPING_SCHEMA_VERSION,
    MappingStatus,
    SchemaMappingSpec,
)
from causalog.ingestion.schema_mapper.hashing import mapping_hash
from causalog.ontology_runtime.dsl import ResolvedPack
from causalog.ontology_runtime.yaml_source import read_document

__all__ = ["MAPPING_DOCUMENT_NAME", "LoadedMapping", "inspect_mapping", "load_mapping"]

#: The conventional filename beside `ontology.yaml` (`docs/architecture.md` §5.1, seam 3).
MAPPING_DOCUMENT_NAME = "mapping.yaml"


class LoadedMapping(BaseModel):
    """A validated mapping, its content address, and everything coverage had to say."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mapping: SchemaMappingSpec
    mapping_hash: str
    source_path: Path
    coverage: CoverageReport


def _parse(path: Path) -> SchemaMappingSpec:
    """Parse and structurally validate one mapping document, locating any failure."""
    document = read_document(path)
    try:
        return SchemaMappingSpec.model_validate(document.data)
    except ValidationError as failure:
        lines = []
        for error in failure.errors():
            line = document.line_for(tuple(error["loc"]))
            where = f"{path}:{line}" if line is not None else str(path)
            address = ".".join(str(part) for part in error["loc"]) or "<document>"
            lines.append(f"{where} {address}: {error['msg']}")
        raise ContractViolationError(
            f"{path} is not a well-formed schema mapping:\n" + "\n".join(lines)
        ) from failure


def inspect_mapping(
    path: Path,
    pack: ResolvedPack,
    *,
    header: Sequence[str] | None = None,
) -> tuple[SchemaMappingSpec, CoverageReport]:
    """Parse a mapping and assess it WITHOUT refusing it.

    The inspection half of `load_mapping`, split out so a tool can show an author every
    problem in a mapping that does not yet load. `load_mapping` is what a run uses.

    Raises:
        ContractViolationError: if the document is malformed or declares a DSL version this
            engine does not read. Neither is a coverage question, and neither is repairable.
    """
    mapping = _parse(path)
    if mapping.mapping_schema_version != MAPPING_SCHEMA_VERSION:
        raise ContractViolationError(
            f"{path} declares mapping_schema_version "
            f"{mapping.mapping_schema_version!r}; this engine reads "
            f"{MAPPING_SCHEMA_VERSION!r}. A version mismatch is a migration, never a "
            "best-effort parse."
        )
    return mapping, assess_coverage(mapping, pack, header=header)


def load_mapping(
    path: Path,
    pack: ResolvedPack,
    *,
    header: Sequence[str] | None = None,
) -> LoadedMapping:
    """Load one mapping for use in a run, refusing anything a run may not rely on.

    Args:
        path: the authored `mapping.yaml`.
        pack: the resolved pack the mapping claims to bind to.
        header: the probed source header. Omitting it does not make the
            every-column-accounted-for check pass -- it makes it report `NOT_RUNNABLE`.

    Raises:
        OntologyMappingError: if the document is an unconfirmed proposal, or if coverage
            reported any `ERROR`. The message carries every finding with its consequence.
        ContractViolationError: if the document is malformed or version-mismatched.
    """
    mapping, coverage = inspect_mapping(path, pack, header=header)
    if mapping.status is MappingStatus.PROPOSED_UNCONFIRMED:
        raise OntologyMappingError(
            f"{path} carries status {MappingStatus.PROPOSED_UNCONFIRMED.value}: it is a "
            "machine-generated proposal, not a mapping. Auto-suggestion produces a "
            "proposal for human confirmation and never a commitment. Review every binding, "
            "then set `status: CONFIRMED` in a commit that records who confirmed it."
        )
    if coverage.errors:
        rendered = "\n".join(finding.render() for finding in coverage.errors)
        raise OntologyMappingError(
            f"{path} does not cover everything pack '{pack.pack_id}' requires. "
            f"{len(coverage.errors)} error(s); each names what it breaks:\n{rendered}"
        )
    return LoadedMapping(
        mapping=mapping,
        mapping_hash=mapping_hash(mapping),
        source_path=path,
        coverage=coverage,
    )
