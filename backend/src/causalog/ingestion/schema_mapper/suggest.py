"""Auto-suggestion: a proposal for a human to confirm, and never a commitment.

What this produces is a `mapping.yaml` carrying `status: PROPOSED_UNCONFIRMED`, which
`load_mapping` **refuses**. A human reads it, corrects it, and removes the header in a
commit that records who confirmed it. That refusal is the entire confirmation mechanism, and
it is a refusal rather than a warning because a warning is a thing that gets read once.

The heuristics, and what they are worth
---------------------------------------
Three independent signals, multiplied:

* **Name similarity** -- token overlap plus a character-bigram Dice coefficient over
  normalised names. It matches a source header written in title case with spaces against an
  attribute written in lower snake case, which is the usual shape of the problem.
* **Type compatibility** -- the profiled `InferredType` against the pack's declared
  `AttributeType`. A hard zero on an incompatible pair, so a `TEXT` column never proposes
  itself for an `INSTANT` attribute however well the names read.
* **Value-pattern match** -- for an `ENUMERATION` attribute, the fraction of the column's
  observed distinct values that appear in the declared enumeration.

**Their precision is unmeasured.** There is no labelled ground truth for column-to-concept
mappings in this repository, so nothing here can say how often a high-scoring suggestion is
right. That is not a gap to be closed later by tuning; it is the reason the proposal cannot
load. Every suggestion carries the score and the basis that produced it, so a reviewer
checks the reasoning rather than the number.

The pack's own declared `source_column` is used where present -- and it is not a heuristic:
an attribute declaring `origin: SOURCE_COLUMN` NAMES its column, so the binding is exact and
is marked as such with `basis: pack_declared_source_column` and a score of 1.0. The
heuristics exist for the columns that remain.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from causalog.ingestion.data_adapter.profile import ColumnProfile, DatasetProfile, InferredType
from causalog.ingestion.schema_mapper.dsl import TargetKind, Transform
from causalog.ontology_runtime.dsl import (
    AttributeOrigin,
    AttributeSpec,
    AttributeType,
    ResolvedPack,
)

__all__ = [
    "MINIMUM_SUGGESTION_SCORE",
    "MappingProposal",
    "SuggestedBinding",
    "render_proposal_yaml",
    "suggest_mapping",
]

#: Suggestions scoring below this are not proposed at all. A proposal padded with guesses
#: nobody would accept is a proposal a reviewer skims instead of reading.
MINIMUM_SUGGESTION_SCORE: Final[float] = 0.35

#: Which profiled types may satisfy which declared attribute types. A pair absent here
#: scores zero however well the names match.
_TYPE_COMPATIBILITY: Final[dict[AttributeType, frozenset[InferredType]]] = {
    AttributeType.STRING: frozenset(
        {InferredType.TEXT, InferredType.INTEGER, InferredType.DECIMAL, InferredType.EMPTY}
    ),
    AttributeType.INTEGER: frozenset({InferredType.INTEGER, InferredType.BOOLEAN}),
    AttributeType.DECIMAL: frozenset(
        {InferredType.DECIMAL, InferredType.INTEGER, InferredType.BOOLEAN}
    ),
    AttributeType.BOOLEAN: frozenset({InferredType.BOOLEAN, InferredType.INTEGER}),
    AttributeType.INSTANT: frozenset({InferredType.DATE, InferredType.DATETIME}),
    AttributeType.DURATION: frozenset({InferredType.INTEGER, InferredType.DECIMAL}),
    AttributeType.ENUMERATION: frozenset(
        {InferredType.TEXT, InferredType.INTEGER, InferredType.BOOLEAN}
    ),
}

#: The transform chain proposed per declared attribute type. Conservative by design: the
#: proposal never suggests a lossy transform, because a reviewer approving a proposal is
#: approving every transform in it.
_TRANSFORMS_FOR: Final[dict[AttributeType, tuple[Transform, ...]]] = {
    AttributeType.STRING: (Transform.TRIM_WHITESPACE, Transform.NORMALIZE_UNICODE_NFC),
    AttributeType.INTEGER: (Transform.TRIM_WHITESPACE, Transform.PARSE_INTEGER),
    AttributeType.DECIMAL: (Transform.TRIM_WHITESPACE, Transform.PARSE_DECIMAL),
    AttributeType.BOOLEAN: (Transform.TRIM_WHITESPACE, Transform.PARSE_BOOLEAN_FLAG),
    AttributeType.INSTANT: (Transform.TRIM_WHITESPACE,),
    AttributeType.DURATION: (Transform.TRIM_WHITESPACE, Transform.PARSE_INTEGER),
    AttributeType.ENUMERATION: (Transform.TRIM_WHITESPACE, Transform.NORMALIZE_UNICODE_NFC),
}

_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")


class SuggestedBinding(BaseModel):
    """One proposed binding, with the score and the reasoning behind it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    column: str
    target_kind: TargetKind
    entity_type: str | None = None
    event_type: str | None = None
    attribute: str | None = None
    transforms: tuple[Transform, ...]
    score: float = Field(ge=0.0, le=1.0)
    """How well the heuristics agreed, 0 to 1.

    Deliberately NOT called `confidence`. LAW-EVIDENCE reserves that word for a
    `ConfidenceVector` whose components each trace to evidence (ADR-0009), and this is a
    string-similarity score with no evidence behind it at all. Naming it `confidence` would
    borrow the authority of a concept it does not implement --
    `scripts/check_confidence_is_a_vector.py` refuses it, which is how this field got its
    name."""

    basis: str = Field(min_length=1)
    """How this suggestion was reached, in words. A reviewer checks the reasoning; a bare
    number gives them nothing to check."""


class MappingProposal(BaseModel):
    """Every suggestion for one dataset against one pack, plus what was not suggested."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ontology_pack: str
    bindings: tuple[SuggestedBinding, ...] = ()
    unsuggested_columns: tuple[str, ...] = ()
    """Header columns no suggestion reached the threshold for. These need a human decision:
    a binding, or an entry under `dropped_columns` with a reason."""
    unbound_attributes: tuple[str, ...] = ()
    """Declared attributes no column was proposed for."""


def _normalise(text: str) -> list[str]:
    """Return a name's lowercase alphanumeric tokens."""
    return _TOKEN_RE.findall(text.lower())


def _bigrams(text: str) -> set[str]:
    """Return the character bigrams of a normalised name."""
    joined = "".join(_normalise(text))
    return {joined[index : index + 2] for index in range(len(joined) - 1)}


def _name_similarity(column: str, attribute: str) -> float:
    """Return a 0-1 similarity between a source column name and an attribute name.

    The maximum of token-set Jaccard and character-bigram Dice. Two measures rather than
    one because they fail differently: a token set is blind to a name that gained one extra
    token, while bigrams handle abbreviation and rearranged words that a token set scores as
    a near-miss.
    """
    left_tokens, right_tokens = set(_normalise(column)), set(_normalise(attribute))
    jaccard = (
        len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
        if left_tokens | right_tokens
        else 0.0
    )
    left_grams, right_grams = _bigrams(column), _bigrams(attribute)
    dice = (
        2 * len(left_grams & right_grams) / (len(left_grams) + len(right_grams))
        if left_grams and right_grams
        else 0.0
    )
    return max(jaccard, dice)


def _value_pattern_score(column: ColumnProfile, attribute: AttributeSpec) -> float:
    """Return how well a column's observed values match a declared enumeration.

    Neutral (1.0) when the attribute declares no enumeration -- there is nothing to match
    against, and scoring a non-enumeration attribute down would penalise it for a property
    it does not have.
    """
    if attribute.type is not AttributeType.ENUMERATION or not attribute.enumeration_values:
        return 1.0
    if not column.top_values:
        return 0.0
    declared = {value.strip().upper() for value in attribute.enumeration_values}
    observed = {value.strip().upper() for value, _ in column.top_values}
    return len(observed & declared) / len(observed)


def _score(column: ColumnProfile, attribute: AttributeSpec) -> tuple[float, str]:
    """Return the combined score and the basis sentence explaining it."""
    compatible = _TYPE_COMPATIBILITY.get(attribute.type, frozenset())
    if column.inferred_type not in compatible:
        return (
            0.0,
            f"profiled type {column.inferred_type.value} cannot satisfy declared type "
            f"{attribute.type.value}",
        )
    name = _name_similarity(column.name, attribute.name)
    values = _value_pattern_score(column, attribute)
    return (
        name * values,
        f"name similarity {name:.3f}, type {column.inferred_type.value} satisfies "
        f"{attribute.type.value}, value-pattern match {values:.3f}",
    )


def _entity_attributes(pack: ResolvedPack) -> list[tuple[str, AttributeSpec]]:
    """Return every `(entity_type, attribute)` the pack declares."""
    return [
        (entity.id, attribute) for entity in pack.entity_types for attribute in entity.attributes
    ]


def suggest_mapping(
    profile: DatasetProfile,
    pack: ResolvedPack,
    *,
    minimum_score: float = MINIMUM_SUGGESTION_SCORE,
) -> MappingProposal:
    """Propose a binding for every declared attribute the profile can plausibly satisfy.

    Exact first, heuristic second. An attribute declaring `origin: SOURCE_COLUMN` names its
    column, and if the profile has that column the binding is exact -- a score of 1.0 with a
    basis that says it was declared, not guessed. Heuristics run only for the remainder, and
    every one of their suggestions carries its score.
    """
    header = {column.name: column for column in profile.columns}
    bindings: list[SuggestedBinding] = []
    suggested_columns: set[str] = set()
    unbound: list[str] = []

    for entity_type, attribute in _entity_attributes(pack):
        address = f"{entity_type}.{attribute.name}"
        declared = attribute.source_column
        if attribute.origin is AttributeOrigin.SOURCE_COLUMN and declared in header:
            bindings.append(
                SuggestedBinding(
                    column=declared,
                    target_kind=TargetKind.ENTITY_ATTRIBUTE,
                    entity_type=entity_type,
                    attribute=attribute.name,
                    transforms=_TRANSFORMS_FOR.get(attribute.type, (Transform.IDENTITY,)),
                    score=1.0,
                    basis=(
                        "pack_declared_source_column: the pack names this column on the "
                        "attribute, so the binding is read rather than inferred"
                    ),
                )
            )
            suggested_columns.add(declared)
            continue
        best: tuple[float, str, str] | None = None
        for column_name, column in header.items():
            score, basis = _score(column, attribute)
            if best is None or score > best[0]:
                best = (score, column_name, basis)
        if best is None or best[0] < minimum_score:
            unbound.append(address)
            continue
        bindings.append(
            SuggestedBinding(
                column=best[1],
                target_kind=TargetKind.ENTITY_ATTRIBUTE,
                entity_type=entity_type,
                attribute=attribute.name,
                transforms=_TRANSFORMS_FOR.get(attribute.type, (Transform.IDENTITY,)),
                score=round(best[0], 6),
                basis=f"heuristic: {best[2]}",
            )
        )
        suggested_columns.add(best[1])

    for event in pack.event_types:
        for attribute in event.required_attributes:
            declared = attribute.source_column
            if attribute.origin is not AttributeOrigin.SOURCE_COLUMN or declared not in header:
                continue
            bindings.append(
                SuggestedBinding(
                    column=declared,
                    target_kind=TargetKind.EVENT_ATTRIBUTE,
                    event_type=event.id,
                    attribute=attribute.name,
                    transforms=_TRANSFORMS_FOR.get(attribute.type, (Transform.IDENTITY,)),
                    score=1.0,
                    basis=(
                        "pack_declared_source_column: the pack names this column on the "
                        "event type's required attribute"
                    ),
                )
            )
            suggested_columns.add(declared)

    return MappingProposal(
        ontology_pack=pack.pack_id,
        bindings=tuple(
            sorted(
                bindings,
                key=lambda item: (
                    item.target_kind.value,
                    item.entity_type or item.event_type or "",
                    item.attribute or "",
                    item.column,
                ),
            )
        ),
        unsuggested_columns=tuple(sorted(name for name in header if name not in suggested_columns)),
        unbound_attributes=tuple(sorted(unbound)),
    )


def render_proposal_yaml(
    proposal: MappingProposal,
    *,
    mapping_id: str,
    mapping_version: str,
    header: Sequence[str],
) -> str:
    """Render a proposal as a `mapping.yaml` a human edits into a real mapping.

    The document carries `status: PROPOSED_UNCONFIRMED`, which `load_mapping` refuses. Every
    unsuggested column is written into `dropped_columns` with a reason that says a human has
    not decided yet -- so the document is structurally complete and semantically honest, and
    a reviewer's job is to replace each of those placeholders rather than to notice a column
    is missing.
    """
    lines = [
        "# GENERATED PROPOSAL -- NOT A MAPPING.",
        "#",
        "# `causalog.ingestion.schema_mapper.suggest` wrote this from a column profile and",
        "# an ontology pack. `load_mapping` REFUSES a document carrying",
        "# `status: PROPOSED_UNCONFIRMED`, so nothing can consume it until a human has read",
        "# every binding, corrected what is wrong, replaced every REVIEW placeholder, and",
        "# removed the status line in a commit.",
        "#",
        "# The heuristics' precision is UNMEASURED: there is no labelled ground truth for",
        "# column-to-concept mappings, so a high score here means the signals agreed,",
        "# not that the binding is right. Read the `basis` on each one.",
        "",
        'mapping_schema_version: "1.0.0"',
        f"mapping_id: {mapping_id}",
        f'mapping_version: "{mapping_version}"',
        f"ontology_pack: {proposal.ontology_pack}",
        "description: >-",
        "  GENERATED PROPOSAL. Replace this description with a statement of what this",
        "  mapping binds and on whose authority.",
        "status: PROPOSED_UNCONFIRMED",
        "",
        "column_bindings:",
    ]
    for binding in proposal.bindings:
        lines.append(f"  # score {binding.score:.6f} -- {binding.basis}")
        lines.append(f"  - column: {binding.column!r}")
        lines.append(f"    target_kind: {binding.target_kind.value}")
        if binding.entity_type:
            lines.append(f"    entity_type: {binding.entity_type}")
        if binding.event_type:
            lines.append(f"    event_type: {binding.event_type}")
        if binding.attribute:
            lines.append(f"    attribute: {binding.attribute}")
        lines.append(
            "    transforms: [" + ", ".join(item.value for item in binding.transforms) + "]"
        )
    lines.append("")
    lines.append("# Every header column not bound above. Each needs a HUMAN decision: bind")
    lines.append("# it, or replace the placeholder reason with a real one.")
    lines.append("dropped_columns:")
    for column in proposal.unsuggested_columns:
        lines.append(f"  - column: {column!r}")
        lines.append("    reason: >-")
        lines.append("      REVIEW: no binding was suggested and no human decision has been")
        lines.append("      recorded. An unlisted column is a hard error; a column dropped")
        lines.append("      with this placeholder is a decision nobody has made yet.")
    lines.append("")
    lines.append("# Declared attributes NO column was proposed for. Each is a concept the")
    lines.append("# dataset may simply not carry -- confirm that, or find the column.")
    for address in proposal.unbound_attributes:
        lines.append(f"#   {address}")
    lines.append("")
    lines.append(f"# Source header, {len(header)} columns, in file sequence:")
    lines.extend(f"#   {index}. {name}" for index, name in enumerate(header))
    lines.append("")
    return "\n".join(lines)
