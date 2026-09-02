"""Row-level validation: structural, temporal, referential, and ontological contradiction.

Everything domain-specific arrives as DATA. This module compares two instants because
`mapping.yaml` declared a precedence pair; it checks a foreign key because the mapping
declared a referential constraint; it rejects a state because the ontology pack declared a
lifecycle. It does not know what any of them mean, and adding a check that required it to
would be LAW-DOMAIN failing at exactly the layer built to hold the boundary.

Two passes, because referential integrity needs the whole file
--------------------------------------------------------------
"Does this key reference an identity that exists?" cannot be answered while the identity in
question may still be five million bytes further down the file. Pass A builds the identity
index; pass B validates against it. The alternative -- assuming a forward reference is an
orphan -- would report a defect that is not there, and a validator that cries wolf is a
validator somebody disables (DEF-0001's actual lesson).

Contradiction is checked against the pack, not against intuition
----------------------------------------------------------------
A state value is a contradiction when the pack's lifecycle does not declare it, or declares
it but no transition can arrive at it. Both are `ERROR` and both quarantine the row. The
second finding deliberately does NOT say which of the data and the pack is wrong: nothing
here can tell, and a message that picked one would be inventing the answer. It says the two
disagree and points at risk R-16.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import timedelta

from pydantic import BaseModel, ConfigDict

from causalog.core.errors import DataQualityError
from causalog.core.temporal import (
    TemporalVerdict,
    TimeInterval,
    is_unverifiable,
    verdict,
)
from causalog.ingestion.data_adapter.cleaning import build_interval, parse_source_instant
from causalog.ingestion.schema_mapper.dsl import (
    SchemaMappingSpec,
    TargetKind,
    UnmappedValuePolicy,
)
from causalog.ontology_runtime.dsl import ResolvedPack

__all__ = [
    "DerivationAudit",
    "DerivationResult",
    "IdentityIndex",
    "RowIssue",
    "RowValidator",
    "reachable_states",
]


class RowIssue(BaseModel):
    """One rule firing on one row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    subject: str
    detail: str


def reachable_states(pack: ResolvedPack, entity_type: str) -> frozenset[str]:
    """Return the states of one entity type that a declared transition can arrive at.

    Initial states are reachable by definition -- an entity starts in one. Everything else
    must be the `to` of some declared transition; a state nothing transitions into is
    declared but unattainable, which is a pack the loader accepts and the data can
    contradict (risk R-16).
    """
    for entity in pack.entity_types:
        if entity.id != entity_type or entity.lifecycle is None:
            continue
        reachable = set(entity.lifecycle.initial_states)
        reachable.update(transition.to_state for transition in entity.lifecycle.transitions)
        return frozenset(reachable & set(entity.lifecycle.states))
    return frozenset()


class IdentityIndex:
    """Pass-A accumulator: which identities exist, and where one disagrees with itself.

    Bounded by the number of distinct identities, not by the number of rows. A dataset whose
    identity cardinality genuinely exceeds memory needs a spilling index, and that is a
    change to make when it is measured rather than guessed at -- the count is in the profile.
    """

    def __init__(self, mapping: SchemaMappingSpec) -> None:
        """Prepare an empty index for every declared identity binding."""
        self._key_columns = {
            binding.entity_type: tuple(binding.key_columns) for binding in mapping.identity_bindings
        }
        self._known: dict[str, set[str]] = {name: set() for name in self._key_columns}
        self._attribute_columns = {
            entity_type: tuple(
                sorted(
                    binding.column
                    for binding in mapping.column_bindings
                    if binding.target_kind is TargetKind.ENTITY_ATTRIBUTE
                    and binding.entity_type == entity_type
                    and binding.column not in set(columns)
                )
            )
            for entity_type, columns in self._key_columns.items()
        }
        self._fingerprints: dict[tuple[str, str], str] = {}
        self._conflicts: dict[str, int] = dict.fromkeys(self._key_columns, 0)
        self._conflict_examples: dict[str, str] = {}

    @staticmethod
    def _compose(values: Mapping[str, str], columns: Sequence[str]) -> str | None:
        """Return the composite key value, or `None` when any part is blank."""
        parts = []
        for column in columns:
            value = values.get(column, "").strip()
            if not value:
                return None
            parts.append(value)
        return "".join(parts)

    def observe(self, values: Mapping[str, str]) -> None:
        """Fold one row into the index."""
        for entity_type, columns in self._key_columns.items():
            key = self._compose(values, columns)
            if key is None:
                continue
            self._known[entity_type].add(key)
            attribute_columns = self._attribute_columns[entity_type]
            if not attribute_columns:
                continue
            fingerprint = "".join(values.get(column, "").strip() for column in attribute_columns)
            existing = self._fingerprints.get((entity_type, key))
            if existing is None:
                self._fingerprints[(entity_type, key)] = fingerprint
            elif existing != fingerprint:
                self._conflicts[entity_type] += 1
                self._conflict_examples.setdefault(entity_type, key)

    def contains(self, entity_type: str, value: str) -> bool:
        """Return whether one identity value was seen anywhere in the file."""
        return value in self._known.get(entity_type, set())

    def distinct_count(self, entity_type: str) -> int:
        """Return how many distinct identities of one type the file carries."""
        return len(self._known.get(entity_type, set()))

    def conflicts(self) -> tuple[tuple[str, int, str | None], ...]:
        """Return `(entity_type, conflicting_row_count, example_key)` for each type."""
        return tuple(
            (entity_type, count, self._conflict_examples.get(entity_type))
            for entity_type, count in sorted(self._conflicts.items())
            if count
        )

    def entity_types(self) -> tuple[str, ...]:
        """Return every entity type this index tracks, in a stable sequence."""
        return tuple(sorted(self._key_columns))


class RowValidator:
    """Pass-B validator: everything checkable about one row, given the whole-file index."""

    def __init__(
        self,
        mapping: SchemaMappingSpec,
        pack: ResolvedPack,
        index: IdentityIndex,
        header: Sequence[str],
    ) -> None:
        """Precompute every lookup the per-row path needs."""
        self._mapping = mapping
        self._header = tuple(header)
        self._index = index
        self._required_columns = tuple(
            sorted(binding.column for binding in mapping.column_bindings if binding.required)
        )
        self._temporal = {binding.column: binding for binding in mapping.temporal_bindings}
        self._value_maps = {
            binding.column: (dict(binding.values), binding) for binding in mapping.value_bindings
        }
        self._reachable = {
            binding.describes_lifecycle_state_of: reachable_states(
                pack, binding.describes_lifecycle_state_of
            )
            for binding in mapping.value_bindings
            if binding.describes_lifecycle_state_of is not None
        }
        self._declared_states = {
            entity.id: frozenset(entity.lifecycle.states) if entity.lifecycle else frozenset()
            for entity in pack.entity_types
        }

    def check(
        self, values: Mapping[str, str], surplus: int
    ) -> tuple[list[RowIssue], dict[str, TimeInterval]]:
        """Return every issue found in one row, and the intervals it built.

        The intervals come back rather than being discarded so `DerivationAudit` can reuse
        them. Parsing each temporal column twice would be wasted work and, worse, a second
        parsing path free to disagree with the first about what a value means.

        Every rule runs; none short-circuits. A row with three defects reports three.
        """
        issues: list[RowIssue] = []
        self._check_structure(values, surplus, issues)
        intervals = self._check_temporal(values, issues)
        self._check_precedence(intervals, issues)
        self._check_values(values, issues)
        self._check_references(values, issues)
        return issues, intervals

    def _check_structure(
        self, values: Mapping[str, str], surplus: int, issues: list[RowIssue]
    ) -> None:
        """Field count and required-column presence."""
        if surplus:
            issues.append(
                RowIssue(
                    code="DQ-STR-FIELD-COUNT",
                    subject="<row>",
                    detail=(
                        f"carries {surplus} field(s) beyond the {len(self._header)}-column "
                        "header"
                    ),
                )
            )
        for column in self._required_columns:
            if not values.get(column, "").strip():
                issues.append(
                    RowIssue(
                        code="DQ-STR-BLANK-REQUIRED",
                        subject=column,
                        detail="is bound as required and is blank",
                    )
                )

    def _check_temporal(
        self, values: Mapping[str, str], issues: list[RowIssue]
    ) -> dict[str, TimeInterval]:
        """Parse every temporally bound column, reporting blanks and parse failures."""
        intervals: dict[str, TimeInterval] = {}
        for column, binding in self._temporal.items():
            raw = values.get(column, "")
            if not raw.strip():
                issues.append(
                    RowIssue(
                        code="DQ-TMP-MISSING",
                        subject=column,
                        detail="is blank; the instant becomes UNKNOWN and is never guessed",
                    )
                )
            try:
                intervals[column] = build_interval(raw, binding)
            except DataQualityError as failure:
                issues.append(
                    RowIssue(code="DQ-TMP-UNPARSEABLE", subject=column, detail=str(failure))
                )
        return intervals

    def _check_precedence(
        self, intervals: Mapping[str, TimeInterval], issues: list[RowIssue]
    ) -> None:
        """Compare each declared precedence pair over the intervals just built."""
        for pair in self._mapping.precedence_pairs:
            earlier = intervals.get(pair.earlier_column)
            later = intervals.get(pair.later_column)
            if earlier is None or later is None:
                continue
            if is_unverifiable(earlier) or is_unverifiable(later):
                continue
            # The engine's own LAW-TIME function, not a reimplementation of it. What this
            # check counts is therefore EXACTLY what module 9 will face: an UNDETERMINED
            # here is an edge that cannot be promoted to INFERRED there. A hand-written
            # endpoint comparison would be a second answer to "which came first", free to
            # disagree with the one the causal engine uses.
            outcome = verdict(earlier, later)
            if outcome is TemporalVerdict.VIOLATION:
                issues.append(
                    RowIssue(
                        code="DQ-TMP-PRECEDENCE-VIOLATION",
                        subject=pair.id,
                        detail=(
                            f"{pair.later_column} [{later.t_earliest.isoformat()}, "
                            f"{later.t_latest.isoformat()}] cannot follow "
                            f"{pair.earlier_column} [{earlier.t_earliest.isoformat()}, "
                            f"{earlier.t_latest.isoformat()}]: LAW-TIME returns VIOLATION"
                        ),
                    )
                )
            elif outcome is TemporalVerdict.UNDETERMINED and pair.allow_equal:
                issues.append(
                    RowIssue(
                        code="DQ-TMP-PRECEDENCE-EQUAL",
                        subject=pair.id,
                        detail=(
                            f"{pair.earlier_column} [{earlier.t_earliest.isoformat()}, "
                            f"{earlier.t_latest.isoformat()}] and {pair.later_column} "
                            f"[{later.t_earliest.isoformat()}, {later.t_latest.isoformat()}] "
                            "OVERLAP: LAW-TIME returns UNDETERMINED and the pair is "
                            "temporally inseparable"
                        ),
                    )
                )
            elif outcome is TemporalVerdict.UNDETERMINED:
                issues.append(
                    RowIssue(
                        code="DQ-TMP-PRECEDENCE-VIOLATION",
                        subject=pair.id,
                        detail=(
                            f"{pair.earlier_column} and {pair.later_column} overlap and the "
                            "pair declares allow_equal: false, so an inseparable pair is a "
                            "defect for this constraint"
                        ),
                    )
                )

    def _check_values(self, values: Mapping[str, str], issues: list[RowIssue]) -> None:
        """Value-domain and state-machine contradiction."""
        for column, (value_map, binding) in self._value_maps.items():
            raw = values.get(column, "").strip()
            if not raw:
                continue
            symbol = value_map.get(raw)
            if symbol is None:
                if binding.unmapped_value_policy is UnmappedValuePolicy.ERROR:
                    issues.append(
                        RowIssue(
                            code="DQ-CON-UNMAPPED-VALUE",
                            subject=column,
                            detail=f"value {raw!r} has no binding in the mapping",
                        )
                    )
                continue
            entity_type = binding.describes_lifecycle_state_of
            if entity_type is None:
                continue
            if symbol not in self._declared_states.get(entity_type, frozenset()):
                issues.append(
                    RowIssue(
                        code="DQ-CON-UNKNOWN-STATE",
                        subject=column,
                        detail=(
                            f"value {raw!r} maps to {symbol!r}, which {entity_type}'s "
                            "lifecycle does not declare"
                        ),
                    )
                )
            elif symbol not in self._reachable.get(entity_type, frozenset()):
                issues.append(
                    RowIssue(
                        code="DQ-CON-UNREACHABLE-STATE",
                        subject=column,
                        detail=(
                            f"value {raw!r} maps to {symbol!r}, a declared state of "
                            f"{entity_type} that no declared transition arrives at; the "
                            "data and the pack disagree and neither is known to be right"
                        ),
                    )
                )

    def _check_references(self, values: Mapping[str, str], issues: list[RowIssue]) -> None:
        """Orphan foreign keys, against the whole-file identity index."""
        for constraint in self._mapping.referential_constraints:
            raw = values.get(constraint.column, "").strip()
            if not raw:
                continue
            if not self._index.contains(constraint.references_entity_type, raw):
                issues.append(
                    RowIssue(
                        code="DQ-REF-ORPHAN-KEY",
                        subject=constraint.id,
                        detail=(
                            f"{constraint.column}={raw!r} references no "
                            f"{constraint.references_entity_type} identity anywhere in the "
                            "dataset"
                        ),
                    )
                )


class DerivationAudit:
    """Measure every declared `temporal_derivation_check` over the whole file.

    A per-row issue could not express this finding: what matters is the AGREEMENT RATE and
    the shape of the residuals, and both are properties of the dataset rather than of any
    row. A derivation that holds in 94% of rows and misses the rest by one constant is a
    different fact about the data than one that misses randomly, and only the residual
    histogram distinguishes them.

    Residual deltas are counted exactly up to a cap. Beyond the cap the audit reports that
    it stopped counting distinct values rather than silently reporting the ones it kept.
    """

    #: Distinct residual deltas held before the audit admits it stopped being exact.
    RESIDUAL_CAP = 64

    def __init__(self, mapping: SchemaMappingSpec) -> None:
        """Prepare a counter per declared check."""
        self._checks = tuple(mapping.temporal_derivation_checks)
        self._temporal = {binding.column: binding for binding in mapping.temporal_bindings}
        self._matches: dict[str, int] = dict.fromkeys((c.id for c in self._checks), 0)
        self._mismatches: dict[str, int] = dict.fromkeys((c.id for c in self._checks), 0)
        self._unevaluable: dict[str, int] = dict.fromkeys((c.id for c in self._checks), 0)
        self._residuals: dict[str, dict[int, int]] = {c.id: {} for c in self._checks}
        self._residuals_exact: dict[str, bool] = dict.fromkeys((c.id for c in self._checks), True)

    def observe(self, values: Mapping[str, str]) -> None:
        """Fold one row into every declared check.

        Reads the SOURCE instants, not the bound intervals. A column bound at DAY precision
        has already had its minutes discarded, and comparing that against a MINUTE-bound
        column would measure the binding rather than the data.
        """
        for check in self._checks:
            left_binding = self._temporal.get(check.equals_column)
            right_binding = self._temporal.get(check.column)
            if left_binding is None or right_binding is None:
                self._unevaluable[check.id] += 1
                continue
            left = parse_source_instant(values.get(check.equals_column), left_binding)
            right = parse_source_instant(values.get(check.column), right_binding)
            if left is None or right is None:
                self._unevaluable[check.id] += 1
                continue
            offset_days = 0
            if check.plus_days_column is not None:
                raw = values.get(check.plus_days_column, "").strip()
                try:
                    offset_days = int(raw)
                except ValueError:
                    self._unevaluable[check.id] += 1
                    continue
            expected = left + timedelta(days=offset_days)
            residual = int((right - expected).total_seconds())
            if residual == 0:
                self._matches[check.id] += 1
                continue
            self._mismatches[check.id] += 1
            counts = self._residuals[check.id]
            if residual in counts or len(counts) < self.RESIDUAL_CAP:
                counts[residual] = counts.get(residual, 0) + 1
            else:
                self._residuals_exact[check.id] = False

    def results(self) -> tuple[DerivationResult, ...]:
        """Return one result per declared check, canonically sequenced."""
        return tuple(
            DerivationResult(
                check_id=check.id,
                column=check.column,
                equals_column=check.equals_column,
                plus_days_column=check.plus_days_column,
                rationale=check.rationale,
                matches=self._matches[check.id],
                mismatches=self._mismatches[check.id],
                unevaluable=self._unevaluable[check.id],
                residual_seconds=tuple(
                    sorted(
                        self._residuals[check.id].items(),
                        key=lambda item: (-item[1], item[0]),
                    )
                ),
                residuals_exact=self._residuals_exact[check.id],
            )
            for check in sorted(self._checks, key=lambda item: item.id)
        )


class DerivationResult(BaseModel):
    """What one declared derivation check measured across the whole dataset."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    check_id: str
    column: str
    equals_column: str
    plus_days_column: str | None
    rationale: str
    matches: int
    mismatches: int
    unevaluable: int
    residual_seconds: tuple[tuple[int, int], ...]
    """`(residual_seconds, row_count)`, most frequent first. A derivation that misses by ONE
    constant is a corrupted derivation; one that misses randomly is not a derivation."""
    residuals_exact: bool

    @property
    def evaluated(self) -> int:
        """Return how many rows the check could be evaluated on."""
        return self.matches + self.mismatches

    @property
    def agreement_rate(self) -> float:
        """Return the fraction of evaluable rows where the derivation held exactly."""
        return self.matches / self.evaluated if self.evaluated else 0.0
