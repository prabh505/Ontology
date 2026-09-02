"""Apply a mapping to a record: source columns in, ontology addresses out.

`docs/architecture.md` §2 names `MappedRecordBatch` as module 2's output and module 3's
input. Module 2 shipped the specification, the loader, the coverage assessment and the
suggester, and nothing that applies a mapping to a row; this file is that missing half, and
it lives here rather than in `extraction` because the architecture assigns it here and
because it is the last place a source column may be named.

What a mapped record is, and what it is not
-------------------------------------------
A `MappedRecord` is a row **re-expressed in ontology vocabulary**. Every value is addressed
as `CONCEPT.attribute`; no source column name survives as a key. It is still a record --
LAW-EVENT puts the boundary at module 4's OUTPUT, and modules 3 and 4 are the last two that
may hold one -- but nothing downstream of them can accidentally read a column, because
there is no column left to read.

Three translations happen here and nowhere else
-----------------------------------------------
**Transforms.** Reused from `data_adapter.cleaning`, never reimplemented: a second cleaning
path would be a second answer to what a cell says. A caller working from module 1's clean
layer has already had them applied and passes `already_cleaned=True`.

**Value bindings.** A source value with no entry in an exhaustive map raises
`OntologyMappingError` naming the value. `unmapped_value_policy` admits exactly one member
and this is where it is honoured: never a pass-through, never a default, never a
fall-through to a catch-all (risk R-07, `CONVENTIONS.md` §7).

**Temporal bindings.** Through `cleaning.build_interval`, which widens and never narrows.
The interval is filed under every ontology address its column feeds, so an emission rule can
name an instant the way it names everything else -- by ontology address.

Natural keys are the SOURCE value, deliberately
-----------------------------------------------
An identifying key is composed from the cleaned column value, not from the mapped symbol,
even where the column carries a value binding. Two reasons, and the second is the load-
bearing one. A natural key is a citation into a file, and it should read as one. And a value
map is not required to be injective: two source keys mapping to one symbol would silently
merge two participants into one entity, which is exactly the failure content addressing
exists to make impossible.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from causalog.core.errors import DataQualityError, OntologyMappingError
from causalog.core.identifiers import canonical_sequence
from causalog.core.ports.source import RawRecord
from causalog.core.temporal import TimeInterval
from causalog.ingestion.schema_mapper.dsl import (
    SchemaMappingSpec,
    TargetKind,
    TemporalBindingSpec,
    Transform,
)
from causalog.ingestion.schema_mapper.transforms import apply_transforms, build_interval

__all__ = [
    "MappedRecord",
    "MappedRecordBatch",
    "MappingPlan",
    "apply_mapping",
    "map_batch",
]

#: A record whose fields the reader could not align with the header carries surplus entries
#: under this prefix. They are counted by module 1 and are not mappable, by definition.
_SURPLUS_PREFIX: Final[str] = "__surplus_"


def address_of(concept: str, attribute: str) -> str:
    """Return the one admissible textual address of a mapped value.

    One function, so the address the mapper writes and the address an emission rule reads
    cannot be assembled two ways. `CONCEPT.attribute`: the concept is `UPPER_SNAKE` and the
    attribute is `lower_snake` (`CONVENTIONS.md` §5), so the separator is unambiguous and
    the two halves are recoverable by eye.
    """
    return f"{concept}.{attribute}"


class MappedRecord(BaseModel):
    """One source record re-expressed in ontology vocabulary, with its citation.

    Every collection is sequenced, and an absent value is ABSENT rather than empty: a hole
    the source did not fill must stay distinguishable from a value it filled with nothing
    (`docs/architecture.md` §2, module 2).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_record_id: str
    row_number: int = Field(ge=1)
    values: tuple[tuple[str, str], ...] = ()
    """`CONCEPT.attribute` -> mapped value, sequenced by address."""
    natural_keys: tuple[tuple[str, str], ...] = ()
    """entity type -> composed natural key, sequenced by entity type. An entity type whose
    key columns are not all present is absent here, and yields no entity."""
    intervals: tuple[tuple[str, TimeInterval], ...] = ()
    """`CONCEPT.attribute` -> the interval the temporal binding produced for the column
    feeding that address, sequenced by address."""

    def value(self, address: str) -> str | None:
        """Return the mapped value at one address, or `None` when it is absent."""
        for key, value in self.values:
            if key == address:
                return value
        return None

    def interval(self, address: str) -> TimeInterval | None:
        """Return the interval at one address, or `None` when no temporal binding feeds it."""
        for key, interval in self.intervals:
            if key == address:
                return interval
        return None

    def natural_key(self, entity_type: str) -> str | None:
        """Return one entity type's composed key, or `None` when this record has none."""
        for key, value in self.natural_keys:
            if key == entity_type:
                return value
        return None


@dataclass(frozen=True)
class RecordView:
    """One mapped record with its three collections indexed for lookup.

    `MappedRecord` stores sequenced tuples because it is a frozen, canonically serializable
    artifact and a mapping does not serialize one way (`CONVENTIONS.md` §11). Reading a
    value out of a tuple is a linear scan, and module 4 reads several values per emission
    rule per record: on the reference dataset that is nineteen rules over a fifty-entry
    tuple for each of 180,519 records, twice, which is most of a billion comparisons and was
    measured taking longer than every other stage of the pipeline combined.

    This view is built ONCE per record per pass and holds the same information keyed. It is
    deliberately not a cached property on the model: the model is frozen, and a cache on a
    frozen artifact is a mutable field wearing a decorator.
    """

    evidence_record_id: str
    row_number: int
    values: Mapping[str, str]
    natural_keys: Mapping[str, str]
    intervals: Mapping[str, TimeInterval]

    @classmethod
    def of(cls, record: MappedRecord) -> RecordView:
        """Index one mapped record for lookup."""
        return cls(
            evidence_record_id=record.evidence_record_id,
            row_number=record.row_number,
            values=dict(record.values),
            natural_keys=dict(record.natural_keys),
            intervals=dict(record.intervals),
        )

    def value(self, address: str) -> str | None:
        """Return the mapped value at one address, or `None` when it is absent."""
        return self.values.get(address)

    def interval(self, address: str) -> TimeInterval | None:
        """Return the interval at one address, or `None` when none feeds it."""
        return self.intervals.get(address)

    def natural_key(self, entity_type: str) -> str | None:
        """Return one entity type's composed key, or `None` when this record has none."""
        return self.natural_keys.get(entity_type)


class MappedRecordBatch(BaseModel):
    """A bounded, deterministically sequenced group of mapped records.

    Carries `ontology_hash` as well as `dataset_version`: a mapped record is expressed in
    one pack's vocabulary, and an artifact derived from it addresses that pack in its
    content address. A batch that did not say which pack it was mapped against would let two
    vocabularies meet downstream with nothing to notice it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_version: str
    ontology_hash: str
    batch_index: int = Field(ge=0)
    records: tuple[MappedRecord, ...] = ()


@dataclass(frozen=True)
class MappingPlan:
    """Everything one mapping decides, computed once instead of per record.

    Built from a `SchemaMappingSpec` alone. Holding it apart from the spec is what keeps the
    per-record path free of scans over binding tuples: a 180,519-row dataset with 55
    bindings is ten million tuple walks that no longer happen.
    """

    transforms: tuple[tuple[str, tuple[Transform, ...]], ...]
    value_maps: Mapping[str, Mapping[str, str]]
    addresses: Mapping[str, tuple[str, ...]]
    key_columns: tuple[tuple[str, tuple[str, ...]], ...]
    temporal: tuple[tuple[str, TemporalBindingSpec], ...]

    @classmethod
    def build(cls, mapping: SchemaMappingSpec) -> MappingPlan:
        """Compile a mapping into the lookups the per-record path needs.

        Raises:
            DataQualityError: if two bindings on one column declare different transform
                chains. One cell cannot be cleaned two ways, and resolving it by document
                sequence would make the cleaned value a function of YAML layout. This is the
                same refusal `data_adapter.adapter._cleaning_plan` makes, for the same
                reason, and it is repeated rather than shared because a caller may build a
                plan without ever running an import.
        """
        chains: dict[str, tuple[Transform, ...]] = {}
        addresses: dict[str, list[str]] = {}
        for binding in mapping.column_bindings:
            existing = chains.get(binding.column)
            if existing is not None and existing != binding.transforms:
                raise DataQualityError(
                    f"column {binding.column!r} is bound more than once with disagreeing "
                    f"transform chains {[item.value for item in existing]} and "
                    f"{[item.value for item in binding.transforms]}. One cell cannot be "
                    "cleaned two ways; the mapping must declare one."
                )
            chains[binding.column] = binding.transforms
            if binding.target_kind is TargetKind.EVENT_OCCURRED_AT:
                # Supplies an interval, not an attribute value. The interval reaches the
                # record through the temporal binding on the same column.
                continue
            concept = binding.entity_type or binding.event_type
            attribute = binding.attribute
            if concept is None or attribute is None:  # pragma: no cover - the DSL refuses it
                continue
            addresses.setdefault(binding.column, []).append(address_of(concept, attribute))
        return cls(
            transforms=tuple(sorted(chains.items())),
            value_maps={binding.column: dict(binding.values) for binding in mapping.value_bindings},
            addresses={column: tuple(sorted(items)) for column, items in addresses.items()},
            key_columns=tuple(
                sorted(
                    (binding.entity_type, tuple(binding.key_columns))
                    for binding in mapping.identity_bindings
                )
            ),
            temporal=tuple(
                sorted((binding.column, binding) for binding in mapping.temporal_bindings)
            ),
        )


def clean_values(record: RawRecord, plan: MappingPlan) -> dict[str, str | None]:
    """Apply the declared transform chains to one raw record.

    Only for a caller starting from a raw record. A caller reading module 1's clean layer
    already holds the output of this and must not run it twice: a chain containing
    `PARSE_DECIMAL` is not idempotent in its receipts, and re-running it would double-count
    every change against a ledger this module does not own.

    Raises:
        DataQualityError: from the first transform that cannot express a value.
    """
    raw = {name: value for name, value in record.fields if not name.startswith(_SURPLUS_PREFIX)}
    return {column: apply_transforms(raw.get(column), chain) for column, chain in plan.transforms}


def apply_mapping(
    values: Mapping[str, str | None],
    evidence_record_id: str,
    row_number: int,
    plan: MappingPlan,
) -> MappedRecord:
    """Re-express one record's CLEANED column values in ontology vocabulary.

    Args:
        values: cleaned column values, as module 1's clean layer writes them. An absent key
            and a `None` value mean the same thing and are both treated as absent.
        evidence_record_id: the citation this record carries.
        row_number: the 1-based source row number, kept for reporting only.
        plan: the compiled mapping.

    Raises:
        OntologyMappingError: if a present value has no entry in an exhaustive value map.
            Never a default and never a pass-through: an unrecognised value quietly becoming
            something plausible is risk R-07 exactly.
    """
    mapped: dict[str, str] = {}
    for column, targets in plan.addresses.items():
        raw = values.get(column)
        if raw is None or not raw.strip():
            continue
        translated = _translate(column, raw, plan)
        for target in targets:
            mapped[target] = translated

    keys: dict[str, str] = {}
    for entity_type, columns in plan.key_columns:
        parts: list[str] = []
        for column in columns:
            part = values.get(column)
            if part is None or not part.strip():
                parts = []
                break
            parts.append(part.strip())
        if parts:
            keys[entity_type] = canonical_sequence(parts)

    intervals: dict[str, TimeInterval] = {}
    for column, binding in plan.temporal:
        built = build_interval(values.get(column), binding)
        for target in plan.addresses.get(column, ()):
            intervals[target] = built

    return MappedRecord(
        evidence_record_id=evidence_record_id,
        row_number=row_number,
        values=tuple(sorted(mapped.items())),
        natural_keys=tuple(sorted(keys.items())),
        intervals=tuple(sorted(intervals.items(), key=lambda item: item[0])),
    )


def _translate(column: str, value: str, plan: MappingPlan) -> str:
    """Return the ontology symbol for a source value, or refuse it.

    Raises:
        OntologyMappingError: naming the column and the value. The message says what is
            missing rather than what went wrong, because the fix is an entry in the map.
    """
    table = plan.value_maps.get(column)
    if table is None:
        return value
    symbol = table.get(value)
    if symbol is None:
        raise OntologyMappingError(
            f"column {column!r} carries value {value!r}, which its value binding does not "
            f"map. The map is exhaustive by contract and admits {sorted(table)}; an "
            "unmapped value is never defaulted, never passed through, and never resolved "
            "to a catch-all (unmapped_value_policy = ERROR, risk R-07)."
        )
    return symbol


def map_batch(
    records: Iterable[tuple[int, str, Mapping[str, str | None]]],
    plan: MappingPlan,
    *,
    dataset_version: str,
    ontology_hash: str,
    batch_index: int,
) -> MappedRecordBatch:
    """Map one batch of `(row_number, evidence_record_id, cleaned values)` triples."""
    return MappedRecordBatch(
        dataset_version=dataset_version,
        ontology_hash=ontology_hash,
        batch_index=batch_index,
        records=tuple(
            apply_mapping(values, evidence_record_id, row_number, plan)
            for row_number, evidence_record_id, values in records
        ),
    )


def mapped_addresses(mapping: SchemaMappingSpec) -> tuple[str, ...]:
    """Return every ontology address this mapping can supply, sequenced.

    Used by coverage to answer "does this emission rule read something the mapping
    supplies", which is the difference between a rule that never fires and a rule that
    fires -- and between a report that says so and one that does not.
    """
    return tuple(sorted(_declared_addresses(mapping)))


def _declared_addresses(mapping: SchemaMappingSpec) -> set[str]:
    """Return the address set the bindings declare, without compiling a plan."""
    found: set[str] = set()
    for binding in mapping.column_bindings:
        if binding.target_kind is TargetKind.EVENT_OCCURRED_AT:
            continue
        concept = binding.entity_type or binding.event_type
        if concept is not None and binding.attribute is not None:
            found.add(address_of(concept, binding.attribute))
    return found


def sequence_columns(mapping: SchemaMappingSpec) -> Sequence[str]:
    """Return every source column the mapping binds, sequenced, for a caller reading a file."""
    return sorted({binding.column for binding in mapping.column_bindings})
