"""Wiring the modules 3 and 4 pipeline for tests, in one place.

Every extraction test needs the same five things -- a resolved pack, a mapping, a plan, a
mapped batch and an envelope -- and assembling them per test file would make five copies of
the pipeline's shape, which would then disagree. It is a module rather than a fixture
because `pytest.mark.parametrize` and the determinism tests need it before fixtures exist.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

from causalog.core.run import OutputEnvelope
from causalog.core.types.evidence import EvidenceRecord
from causalog.extraction.entity_extractor import ConflictPolicy, EntityExtractor, ExtractionResult
from causalog.extraction.event_generator import (
    EventGenerator,
    GenerationResult,
    MissingEventPolicy,
)
from causalog.ingestion.schema_mapper import (
    MappedRecordBatch,
    MappingPlan,
    SchemaMappingSpec,
    apply_mapping,
    inspect_mapping,
)
from causalog.ingestion.schema_mapper.transforms import apply_transforms
from causalog.ontology_runtime import load_pack
from causalog.ontology_runtime.dsl import ResolvedPack

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKS_ROOT = REPO_ROOT / "ontology" / "packs"

__all__ = [
    "PACKS_ROOT",
    "REPO_ROOT",
    "Expansion",
    "Harness",
    "build_batches",
    "envelope_for",
    "expand",
    "harness_for",
]


class Harness:
    """A pack, its mapping, and the compiled plan the record path needs."""

    def __init__(self, pack: ResolvedPack, ontology_hash: str, mapping: SchemaMappingSpec) -> None:
        """Hold the three artifacts every extraction test starts from."""
        self.pack = pack
        self.ontology_hash = ontology_hash
        self.mapping = mapping
        self.plan = MappingPlan.build(mapping)

    def extract(
        self,
        batches: Sequence[MappedRecordBatch],
        envelope: OutputEnvelope,
        *,
        policy: ConflictPolicy = ConflictPolicy.FIRST_WINS,
    ) -> ExtractionResult:
        """Run module 3 over the batches."""
        extractor = EntityExtractor(self.pack, self.mapping, self.ontology_hash, policy=policy)
        return extractor.extract(batches, envelope)

    def generate(
        self,
        batches: Sequence[MappedRecordBatch],
        extraction: ExtractionResult,
        envelope: OutputEnvelope,
        *,
        policy: MissingEventPolicy = MissingEventPolicy.RECORD_GAP,
        conflict_policy: ConflictPolicy = ConflictPolicy.FIRST_WINS,
    ) -> GenerationResult:
        """Run module 4 over the batches, against module 3's entities."""
        anchor_types = {item.anchor_entity_type for item in self.pack.process_definitions}
        anchors = frozenset(
            entity.entity_id for entity in extraction.entities if entity.entity_type in anchor_types
        )
        generator = EventGenerator(
            self.pack, self.mapping, self.ontology_hash, missing_event_policy=policy
        )
        return generator.generate(
            lambda: list(batches),
            anchors,
            extraction.entity_ids(),
            envelope,
            conflict_policy=conflict_policy.value,
        )


class Expansion(NamedTuple):
    """One end-to-end run of modules 3 and 4, named so a test can annotate it.

    A triple rather than three fixtures because the three are one run: an extraction and a
    generation over different batches would silently be a different experiment.
    """

    harness: Harness
    extraction: ExtractionResult
    generation: GenerationResult


def expand(
    raw_rows: Iterable[Mapping[str, str]],
    dataset_version: str,
    *,
    pack_id: str = "dataco",
    conflict_policy: ConflictPolicy = ConflictPolicy.FIRST_WINS,
    missing_event_policy: MissingEventPolicy = MissingEventPolicy.RECORD_GAP,
    batch_size: int = 1000,
) -> Expansion:
    """Run the whole of modules 3 and 4 over raw records, and return all three artifacts."""
    harness = harness_for(pack_id)
    batches = build_batches(raw_rows, harness, dataset_version, batch_size=batch_size)
    envelope = envelope_for(harness, dataset_version)
    extraction = harness.extract(batches, envelope, policy=conflict_policy)
    generation = harness.generate(
        batches,
        extraction,
        envelope,
        policy=missing_event_policy,
        conflict_policy=conflict_policy,
    )
    return Expansion(harness, extraction, generation)


def harness_for(pack_id: str = "dataco", packs_root: Path = PACKS_ROOT) -> Harness:
    """Load one shipped pack and its mapping, refusing neither and checking both."""
    loaded = load_pack(packs_root / pack_id / "ontology.yaml")
    mapping, _coverage = inspect_mapping(packs_root / pack_id / "mapping.yaml", loaded.pack)
    return Harness(loaded.pack, loaded.ontology_hash, mapping)


def build_batches(
    raw_rows: Iterable[Mapping[str, str]],
    harness: Harness,
    dataset_version: str,
    *,
    batch_size: int = 1000,
) -> tuple[MappedRecordBatch, ...]:
    """Turn raw records into mapped batches, through the real transform and mapping path.

    `batch_size` is a parameter so a determinism test can assert that batching is a
    partitioning of the input and never a change to it.
    """
    mapped = []
    for row_number, values in enumerate(raw_rows, start=1):
        cleaned = {
            column: apply_transforms(values.get(column), chain)
            for column, chain in harness.plan.transforms
        }
        evidence = EvidenceRecord.address(dataset_version, f"row:{row_number}")
        mapped.append(apply_mapping(cleaned, evidence, row_number, harness.plan))
    batches = []
    for index in range(0, len(mapped), batch_size):
        batches.append(
            MappedRecordBatch(
                dataset_version=dataset_version,
                ontology_hash=harness.ontology_hash,
                batch_index=index // batch_size,
                records=tuple(mapped[index : index + batch_size]),
            )
        )
    return tuple(batches)


def envelope_for(harness: Harness, dataset_version: str) -> OutputEnvelope:
    """Return the envelope a test's artifacts carry.

    `rule_pack_version` and `graph_projection_version` are `unset` because neither exists
    yet (`CONTEXT.md` §7); `execution_id` is fixed rather than random because it is excluded
    from every determinism comparison and a random one would be noise in a diff.
    """
    return OutputEnvelope(
        run_id="run:0000000000000000",
        ontology_version=harness.pack.ontology_version,
        ontology_hash=harness.ontology_hash,
        dataset_version=dataset_version,
        rule_pack_version="unset",
        engine_version="0.1.0",
        graph_projection_version="unset",
        seed=0,
        execution_id="test",
    )
