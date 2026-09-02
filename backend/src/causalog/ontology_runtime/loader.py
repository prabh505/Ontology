"""Load, validate, and version one domain pack.

The single public entry point is `load_pack`. It reads the authored document and everything
it extends, validates the shape against the DSL, resolves inheritance, runs structural and
semantic validation, and computes the pack's `ontology_hash`.

Two properties this module is responsible for:

**Every problem is reported, not the first.** A pack with six errors reports six. An author
who has to reload once per message stops reading the messages.

**Every problem carries a file and a line.** Pydantic reports an address inside the
document; `yaml_source` remembers where each address sits; `locator` joins them across the
inheritance chain. A validator that can say what is wrong but not where is a validator
people route around.
"""

from __future__ import annotations

from collections.abc import Collection
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from causalog.core.errors import ContractViolationError
from causalog.ontology_runtime.diagnostics import Diagnostic, Severity, render
from causalog.ontology_runtime.dsl import DomainPack, ResolvedPack
from causalog.ontology_runtime.hashing import ontology_hash
from causalog.ontology_runtime.locator import PackLocator
from causalog.ontology_runtime.resolution import (
    MAX_CHAIN_DEPTH,
    PACK_DOCUMENT_NAME,
    base_pack_path,
    check_withdrawals,
    resolve,
)
from causalog.ontology_runtime.semantic import validate_semantics
from causalog.ontology_runtime.structural import (
    validate_authored_uniqueness,
    validate_structure,
)
from causalog.ontology_runtime.yaml_source import SourceDocument, read_document

__all__ = ["LoadedPack", "inspect_pack", "load_pack", "read_pack_chain"]


class LoadedPack(BaseModel):
    """A validated pack, its content address, and everything the validator had to say."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pack: ResolvedPack
    ontology_hash: str
    source_path: Path
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def warnings(self) -> tuple[Diagnostic, ...]:
        """Return the diagnostics that did not block the load."""
        return tuple(item for item in self.diagnostics if item.severity is Severity.WARNING)

    @property
    def unchecked(self) -> tuple[Diagnostic, ...]:
        """Return the checks that could not run at all. Never empty by accident."""
        return tuple(item for item in self.diagnostics if item.severity is Severity.NOT_RUNNABLE)


def _schema_diagnostics(error: ValidationError, document: SourceDocument) -> tuple[Diagnostic, ...]:
    """Turn pydantic's report into located diagnostics, one per failure."""
    findings: list[Diagnostic] = []
    for entry in error.errors():
        address = tuple(entry["loc"])
        rendered = ""
        for part in address:
            if isinstance(part, int):
                rendered += f"[{part}]"
            else:
                rendered += f".{part}" if rendered else str(part)
        findings.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="ONT-E-SCHEMA",
                message=entry["msg"],
                path=rendered,
                file=document.path,
                line=document.line_for(address),
            )
        )
    return tuple(findings)


def read_pack_chain(pack_path: Path) -> tuple[tuple[DomainPack, ...], tuple[SourceDocument, ...]]:
    """Read the authored pack and everything it extends, base first.

    Raises:
        ContractViolationError: on an unreadable or malformed document, an `extends` target
            that does not exist, a cycle, or a chain deeper than `MAX_CHAIN_DEPTH`.
    """
    packs: list[DomainPack] = []
    documents: list[SourceDocument] = []
    seen: list[str] = []
    current = pack_path
    while True:
        document = read_document(current)
        try:
            pack = DomainPack.model_validate(document.data)
        except ValidationError as error:
            raise ContractViolationError(
                f"{current} does not validate against the domain-pack schema:\n"
                + render(_schema_diagnostics(error, document))
            ) from error
        except ContractViolationError as error:
            # A DSL model validator raised. Pydantic propagates a non-ValueError unwrapped
            # (docs/contracts.md §6), which is what lets a contract breach stay a contract
            # breach rather than becoming a generic validation failure. The message carries
            # no location of its own, so the file is prefixed here.
            raise ContractViolationError(f"{current}: {error}") from error
        if pack.pack_id in seen:
            raise ContractViolationError(
                f"pack '{pack.pack_id}' extends itself, directly or through "
                f"{' -> '.join(seen)}. A cyclic chain resolves to nothing."
            )
        seen.append(pack.pack_id)
        packs.append(pack)
        documents.append(document)
        if len(packs) > MAX_CHAIN_DEPTH:
            raise ContractViolationError(
                f"pack chain from {pack_path} is deeper than {MAX_CHAIN_DEPTH}."
            )
        if pack.extends is None:
            break
        current = base_pack_path(current, pack.extends)
        if not current.is_file():
            raise ContractViolationError(
                f"pack '{pack.pack_id}' extends '{pack.extends}', which has no "
                f"{PACK_DOCUMENT_NAME} at {current}."
            )
    packs.reverse()
    documents.reverse()
    return tuple(packs), tuple(documents)


def inspect_pack(
    pack_path: Path,
    *,
    produced_event_types: Collection[str] | None = None,
) -> tuple[ResolvedPack, tuple[Diagnostic, ...]]:
    """Resolve a pack and return every diagnostic, including errors, without raising.

    This is the form an editor integration or a batch audit wants: a pack with errors still
    resolves far enough to describe what is wrong with it, and reporting six problems at
    once is the difference between a validator people use and one they route around.

    `load_pack` is the strict form built on this one. Failures that prevent resolution
    entirely -- an unreadable file, a schema breach, a broken `extends` chain -- still
    raise here, because there is no pack to describe.

    Raises:
        ContractViolationError: if the pack cannot be resolved at all.
    """
    chain, documents = read_pack_chain(pack_path)
    locator = PackLocator(documents)

    withdrawal_problems = check_withdrawals(chain)
    if withdrawal_problems:
        raise ContractViolationError(
            f"{pack_path} declares a withdrawal that removes nothing:\n"
            + "\n".join(f"  {problem}" for problem in withdrawal_problems)
        )

    resolved = resolve(chain)
    findings = (
        *(
            finding
            for authored in chain
            for finding in validate_authored_uniqueness(authored, locator)
        ),
        *validate_structure(resolved, locator),
        *validate_semantics(resolved, locator, produced_event_types=produced_event_types),
    )
    return resolved, findings


def load_pack(
    pack_path: Path,
    *,
    produced_event_types: Collection[str] | None = None,
) -> LoadedPack:
    """Load and validate one domain pack, returning it with its `ontology_hash`.

    Args:
        pack_path: the authored `ontology.yaml`.
        produced_event_types: event type identifiers a rule pack is known to produce.
            `None` -- the default, and today the only possible value, since no rule pack
            exists yet -- makes the rule-coverage check report `NOT_RUNNABLE`.

    Raises:
        ContractViolationError: if any diagnostic is an `ERROR`. The message carries every
            error, each with its file and line.
    """
    resolved, findings = inspect_pack(pack_path, produced_event_types=produced_event_types)
    errors = tuple(item for item in findings if item.severity is Severity.ERROR)
    if errors:
        raise ContractViolationError(
            f"{pack_path} is not a valid domain pack; {len(errors)} error(s):\n" + render(errors)
        )
    return LoadedPack(
        pack=resolved,
        ontology_hash=ontology_hash(resolved),
        source_path=pack_path,
        diagnostics=findings,
    )
