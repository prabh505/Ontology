"""Module 2's contract: a proposal never loads, coverage names what breaks, no silent default."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from causalog.core.errors import ContractViolationError, OntologyMappingError
from causalog.ingestion.schema_mapper import (
    MappingStatus,
    SchemaMappingSpec,
    assess_coverage,
    load_mapping,
    mapping_hash,
)
from causalog.ontology_runtime.diagnostics import Severity


def _repository_root() -> Path:
    """Walk up to the directory holding `ontology/packs`.

    A hard-coded `parents[N]` is silently wrong the moment a test file moves one directory
    deeper, and it fails as "file not found" rather than as "your index is off by one".
    """
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "ontology" / "packs").is_dir():
            return candidate
    raise RuntimeError("no repository root above this file holds ontology/packs")


DATACO_PACK = _repository_root() / "ontology" / "packs" / "dataco"


def _write(tmp_path: Path, mapping: SchemaMappingSpec) -> Path:
    """Write a mapping out as YAML-compatible JSON so the loader can read it back."""
    import json

    path = tmp_path / "mapping.yaml"
    path.write_text(json.dumps(mapping.model_dump(mode="json")), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------------------
# The confirmation mechanism
# ---------------------------------------------------------------------------------------


def test_an_unconfirmed_proposal_is_refused_not_warned_about(
    tmp_path: Path, dataco_pack: Any, dataco_mapping: Any, sample_probe: Any
) -> None:
    """The entire human-confirmation mechanism. A warning here would be read once."""
    proposal = dataco_mapping.model_copy(update={"status": MappingStatus.PROPOSED_UNCONFIRMED})
    with pytest.raises(OntologyMappingError, match="PROPOSED_UNCONFIRMED"):
        load_mapping(_write(tmp_path, proposal), dataco_pack, header=sample_probe.header)


def test_the_confirmed_mapping_loads(dataco_pack: Any, sample_probe: Any) -> None:
    loaded = load_mapping(DATACO_PACK / "mapping.yaml", dataco_pack, header=sample_probe.header)
    assert loaded.mapping.status is MappingStatus.CONFIRMED
    assert loaded.mapping_hash.startswith("map:")


def test_a_generated_proposal_carries_the_status_that_refuses_it(
    dataco_pack: Any, sample_probe: Any
) -> None:
    """Suggestion and refusal have to agree, or the guard is decorative."""
    from causalog.ingestion.data_adapter import Profiler
    from causalog.ingestion.schema_mapper import render_proposal_yaml, suggest_mapping
    from causalog.persistence.sources.delimited import DelimitedTextSource
    from tests.fixtures.dataco import SAMPLE_CSV

    source = DelimitedTextSource(SAMPLE_CSV, "sample@x+mapx", probe=sample_probe)
    profiler = Profiler(sample_probe.header)
    for batch in source.read():
        for record in batch.records:
            profiler.observe_first(record.fields)
    proposal = suggest_mapping(profiler.result(), dataco_pack)
    rendered = render_proposal_yaml(
        proposal, mapping_id="dataco", mapping_version="1.0.0", header=sample_probe.header
    )
    assert "status: PROPOSED_UNCONFIRMED" in rendered
    assert proposal.bindings, "a proposal with no suggestions proves nothing"
    for binding in proposal.bindings:
        assert binding.basis.strip(), "every suggestion must carry the reasoning behind it"


# ---------------------------------------------------------------------------------------
# Coverage: what is unmapped, and what that breaks
# ---------------------------------------------------------------------------------------


def test_the_shipped_mapping_covers_every_required_concept(
    dataco_pack: Any, sample_probe: Any
) -> None:
    coverage = assess_coverage(
        load_mapping(DATACO_PACK / "mapping.yaml", dataco_pack, header=sample_probe.header).mapping,
        dataco_pack,
        header=sample_probe.header,
    )
    assert coverage.errors == ()


def test_a_missing_required_concept_is_an_error_that_names_what_it_breaks(
    dataco_pack: Any, dataco_mapping: Any, sample_probe: Any
) -> None:
    stripped = dataco_mapping.model_copy(
        update={
            "column_bindings": tuple(
                binding
                for binding in dataco_mapping.column_bindings
                if binding.target_kind.value != "EVENT_OCCURRED_AT"
            )
        }
    )
    coverage = assess_coverage(stripped, dataco_pack, header=sample_probe.header)
    codes = {finding.code for finding in coverage.errors}
    assert "MAP-E-OCCURRED-AT-UNBOUND" in codes
    for finding in coverage.errors:
        assert finding.downstream_consequence.strip()


def test_a_missing_identity_binding_is_an_error(
    dataco_pack: Any, dataco_mapping: Any, sample_probe: Any
) -> None:
    stripped = dataco_mapping.model_copy(update={"identity_bindings": ()})
    coverage = assess_coverage(stripped, dataco_pack, header=sample_probe.header)
    assert "MAP-E-IDENTITY-UNBOUND" in {finding.code for finding in coverage.errors}


def test_an_unlisted_column_is_a_hard_error(
    dataco_pack: Any, dataco_mapping: Any, sample_probe: Any
) -> None:
    """'We did not map it' and 'we did not notice it' must not be indistinguishable."""
    stripped = dataco_mapping.model_copy(
        update={"dropped_columns": dataco_mapping.dropped_columns[:-1]}
    )
    coverage = assess_coverage(stripped, dataco_pack, header=sample_probe.header)
    assert "MAP-E-COLUMN-UNLISTED" in {finding.code for finding in coverage.errors}


def test_omitting_the_header_reports_not_runnable_rather_than_passing(
    dataco_pack: Any, dataco_mapping: Any
) -> None:
    """A check that could not run must never look like a check that passed."""
    coverage = assess_coverage(dataco_mapping, dataco_pack, header=None)
    codes = {finding.code for finding in coverage.not_runnable}
    assert "MAP-N-HEADER-UNAVAILABLE" in codes


def test_a_derived_event_type_reports_not_runnable_rather_than_clean(
    dataco_pack: Any, dataco_mapping: Any, sample_probe: Any
) -> None:
    """ADR-0029: their occurrence is module 4's job and cannot be assessed here."""
    coverage = assess_coverage(dataco_mapping, dataco_pack, header=sample_probe.header)
    deferred = [
        finding
        for finding in coverage.findings
        if finding.code == "MAP-N-DERIVED-OCCURRENCE-DEFERRED"
    ]
    assert deferred
    assert all(finding.severity is Severity.NOT_RUNNABLE for finding in deferred)


# ---------------------------------------------------------------------------------------
# Structural refusals
# ---------------------------------------------------------------------------------------


def test_a_column_cannot_be_both_bound_and_dropped(dataco_mapping: Any) -> None:
    with pytest.raises(ValueError, match="both bound and listed"):
        dataco_mapping.model_copy(
            update={"dropped_columns": (*dataco_mapping.dropped_columns,)}
        ).model_validate(
            {
                **dataco_mapping.model_dump(mode="json"),
                "dropped_columns": [
                    *[entry.model_dump(mode="json") for entry in dataco_mapping.dropped_columns],
                    {"column": dataco_mapping.column_bindings[0].column, "reason": "clash"},
                ],
            }
        )


def test_a_version_mismatch_is_a_migration_not_a_best_effort_parse(
    tmp_path: Path, dataco_pack: Any, dataco_mapping: Any, sample_probe: Any
) -> None:
    future = dataco_mapping.model_copy(update={"mapping_schema_version": "2.0.0"})
    with pytest.raises(ContractViolationError, match="migration"):
        load_mapping(_write(tmp_path, future), dataco_pack, header=sample_probe.header)


def test_the_mapping_hash_is_stable_and_ignores_formatting(dataco_mapping: Any) -> None:
    assert mapping_hash(dataco_mapping) == mapping_hash(dataco_mapping.model_copy())


def test_the_mapping_hash_moves_when_a_declared_value_moves(dataco_mapping: Any) -> None:
    changed = dataco_mapping.model_copy(update={"mapping_version": "1.0.1"})
    assert mapping_hash(changed) != mapping_hash(dataco_mapping)
