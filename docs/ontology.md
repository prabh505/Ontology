# ontology.md — the domain-pack contract, and how to onboard a new domain

> **Scope.** This document is the truth about *how a domain is described*. `docs/prd.md` is
> the truth about intent, `docs/architecture.md` about structure, `docs/contracts.md` about
> the frozen core types, and `CONTEXT.md` about current state.
>
> **Status.** Pack schema version **1.1.0**, set by ADR-0026 and moved by **ADR-0067**. The
> `OntologySpec` seam is **frozen**; changing it requires an ADR and a coordinated update of
> every pack (`CONTEXT.md` §6), which is what ADR-0067 did.
>
> *1.1.0 (2026-09-07, ADR-0067): `AttributeSpec` gains three optional fields — `mutable`,
> `admissible_values` and `admissible_range` — so a pack can say which attributes a
> counterfactual may set differently. **Additive: a 1.0.0 pack's declarations are unchanged in
> meaning**, and it simply declares no changeable attribute. The default REFUSES: an absent
> `mutable` means no hypothetical may set that attribute, reported as a policy gap and never
> read as permission (ADR-0049's rule, in the direction that withholds). `admissible_values`
> and `admissible_range` are what the DOMAIN says is possible and are deliberately NOT the
> range a run witnessed — that is measured separately as a support envelope (ADR-0070),
> because a value can be entirely possible and entirely outside anything the data contains.
> `ontology_hash` moves, so `run_id` moves; `dataset_version` does not, so no re-import is
> needed.*

---

## 1. Why this layer exists

LAW-DOMAIN: no reasoning package may name the thing it reasons about. ADR-0002 made that
structural by ruling that **all** domain vocabulary lives as data. This layer is where that
data lives and how it is validated.

Two properties follow, and both are enforced rather than encouraged:

- **The engine reads the ontology; the ontology never imports engine code.** There is no
  executable code in a pack — no expression string, no callable reference, no plugin hook.
  A metric that cannot be written as a declarative operator tree needs a new operator and an
  ADR (ADR-0026), not an escape hatch.
- **Nothing above L3 may read the ontology at all.** Forbidden edge F3
  (`docs/architecture.md` §1.4) blocks it at import level, so a reasoning package cannot
  reach for domain semantics even if someone wants it to.

---

## 2. What a pack is

One file, `ontology/packs/<domain>/ontology.yaml`, validated against
`ontology/_schema/ontology.schema.json` — which is **generated** from the pydantic models in
`causalog.ontology_runtime.dsl`. The models are normative; the schema is published so
tooling outside Python can use it.

| Namespace | Declares |
|---|---|
| `event_categories` | the pack's own groupings. The engine knows none of the names. |
| `cost_classes`, `severity_classes` | ordinal vocabularies with an explicit `rank`, so a ranker compares members without reading names. Usually inherited from `_base`. |
| `entity_types` | identifying keys, attributes with type/semantics/origin, and a lifecycle state machine. |
| `relationship_types` | structural edges: `from`, `to`, cardinality, temporal validity. `CAUSES` is refused. |
| `event_types` | category, observation mode, participants by role, required attributes, pre/postconditions as state assertions, actionability. |
| `external_event_types` | declared and **unpopulated** in V1. Referencing one anywhere is an error. |
| `process_definitions` | the canonical happy-path sequence and its admissible variants. |
| `measurement_definitions` | how each domain metric is computed, as a closed operator tree. |

### The three rules a pack author will meet first

**Every attribute states its origin.** `SOURCE_COLUMN` (and names the column),
`DERIVED` (and names the basis), or `ASSUMED` (and says so). Exactly one; the loader refuses
two.

**A derived event never masquerades as an observed one (ADR-0029).** If the source implies
an occurrence rather than logging it, the event type is `observation: DERIVED`, carries
`derivation.basis` and a `default_confidence`, and may never declare `OBSERVED` provenance.

**Actionability is always `ASSUMED` (risk R-15).** No dataset establishes that an operator
can act on something. The claim is declared, inspectable, and never labelled stronger than
it is.

---

## 3. What the loader does, and what it cannot do

`causalog.ontology_runtime.load_pack(path)` reads the pack and everything it extends,
validates, resolves inheritance, and returns the pack with its `ontology_hash`.

**Structural findings are `ERROR` and refuse the pack:** orphan references of every kind,
duplicate identifiers, malformed or unreachable state machines, terminal states with an exit,
process steps that name no declared event type, measurement leaves that name no declared
attribute, `CAUSES` as a relationship, an external event type referenced anywhere, a
confidence component the default aggregator does not weight.

**Semantic findings are `WARNING` and do not:** an entity type with no identifying key, a
state with no exit transition that is not declared terminal, an entity type with no lifecycle,
an event type in no process definition.

**One finding is neither.** `NOT_RUNNABLE` reports a check the validator could not perform.
`ONT-N-RULE-COVERAGE` is emitted when no rule pack is supplied, so "every event type has a
producing rule" was **not checked**. It is reported rather than skipped: this repository has
twice mistaken a check that could not run for one that passed (DEF-0001, OQ-014), and a
third instance gets the same treatment as the first two. **Since 2026-09-01 a rule pack
exists** (ADR-0044), so a load that passes `produced_event_types` gets the real check and a
`ONT-W-NO-PRODUCING-RULE` warning per unexplained type; a load that omits it still gets the
`NOT_RUNNABLE`, because the check still did not run.

Every diagnostic carries a file and a line, and every problem is reported together rather
than one per reload.

### `ontology_hash`

`ont:<sha256(canonical_resolved_pack)[:16]>`, via `core.serialization.to_canonical_json` and
`core.identifiers.digest` — one hashing scheme, no second path. It is computed over the
**resolved** pack, so it is invariant to comments, indentation, key sequence, and how the
pack was split across a base and an overlay, and sensitive to every declared value. It
participates in `run_id` (ADR-0013).

---

## 4. Onboarding a new domain — the checklist

A numbered procedure, executable by someone who did not write this layer. Steps 1–7 are the
ontology; steps 8–11 are the other seams and land with the modules that own them.

1. **Create the directory.** `ontology/packs/<domain>/`, where `<domain>` is lower snake
   case and carries no leading underscore. Copy `ontology/packs/hospital/ontology.yaml` as
   a starting point — it is the shortest complete pack in the repository.

2. **Set the header.** `pack_schema_version: "1.2.0"` (the DSL's version, not yours),
   `pack_id: <domain>`, `ontology_version: "1.0.0"`, a `description`, and
   `extends: _base` unless you have a stated reason not to inherit the cost and severity
   vocabularies.

3. **Declare `event_categories`.** Your own groupings, in your own words. Do not copy
   DataCo's — `BUSINESS`/`WAREHOUSE`/`TRANSPORT` is one domain's shape, not the engine's.

4. **Declare `entity_types`.** For each: an `id`, at least one entry in `identifying_keys`
   (naming an attribute you also declare), the `attributes`, and a `lifecycle` if the thing
   changes state. Every attribute needs `type`, `semantics`, `description`, and an `origin`
   with its matching evidence field. Reference entities that never change state may omit the
   lifecycle and will load with a warning that says exactly that.

5. **Declare `relationship_types`.** Structural only. If you find yourself wanting a
   `CAUSES` relationship, that is a causal edge and the causal engine produces it; the
   loader will refuse the declaration.

6. **Declare `event_types`.** For each: `category`, `observation`, `provenance_class`,
   `participants` (each with a `role` — conditions refer to roles, not to entity types, so
   one event can involve two entities of the same type), any `required_attributes`, the
   `preconditions` and `postconditions` as role/state assertions, and `actionability`.
   Every state a postcondition names must be reachable by a declared transition on that
   role's entity type. For anything the source implies rather than logs, set
   `observation: DERIVED` and fill in `derivation`.

7. **Declare `process_definitions` and `measurement_definitions`.** One canonical sequence
   per process, plus a variant for every departure your source can express. Measurements are
   operator trees over attributes the referenced event types declare as required — a
   measurement may not read an attribute an event type does not guarantee to carry.

8. **Load it and read every diagnostic.**

   ```
   cd backend && ../backend/.venv/bin/python -c \
     "from pathlib import Path; from causalog.ontology_runtime import load_pack; \
      from causalog.ontology_runtime.diagnostics import render; \
      p = load_pack(Path('../ontology/packs/<domain>/ontology.yaml')); \
      print(p.ontology_hash); print(render(p.diagnostics))"
   ```

   Errors refuse the pack and name their file and line. **Read the warnings too** — a pack
   that validates cleanly can still be semantically wrong (risk R-16), and the warnings are
   most of what the validator can say about that.

9. **Confirm CI picked the pack up.** Nothing to edit: the three parameterisations
   (`test_packs_load.py`, `test_ontology_hash_stability.py`, `test_pack_round_trip.py`) are
   driven by `tests/ontology_packs.discover_packs()`, which globs
   `ontology/packs/*/ontology.yaml`. Confirm your directory is among them, and that the run
   grew:

   ```
   cd backend && ../backend/.venv/bin/pytest tests/unit/ontology_runtime -q --collect-only -v | grep <domain>
   ```

   A pack nothing loads in CI is a pack that breaks silently, which is why discovery is
   derived from the directory rather than from a list somebody has to remember to extend.

10. **Write the remaining five seams** (`docs/architecture.md` §5.1). None of them is code
    except the first:
    - `SourceReader` — `backend/src/causalog/persistence/sources/<domain>.py`. The one file.
      It reads bytes and contains no reasoning.
    - `mapping.yaml` — column, value, identity, temporal, precedence and referential
      bindings, with every unlisted column justified under `dropped_columns`. **The schema
      is `causalog.ingestion.schema_mapper.dsl` (ADR-0036)**, normative as pydantic models
      exactly as the pack DSL is. Generate a starting point with
      `make import DATASET=<domain> PROPOSE=1`, which writes a
      `mapping.proposal.yaml` beside the data-quality report; it carries
      `status: PROPOSED_UNCONFIRMED` and **the loader refuses it** until a human has read
      every binding and removed that line in a commit. Module 2.
    - **`event_emissions`, in the same `mapping.yaml` (ADR-0039).** One rule per event type,
      saying WHICH RECORDS WITNESS IT: a closed condition operator tree over
      `CONCEPT.attribute` addresses plus a declared `occurred_at` policy. This is the
      executable half of each derived type's `derivation.basis`, which is prose — the pack
      says what was reconstructed, the mapping says from which records. **Write the two so
      they can be read against each other**, because nothing compares them mechanically and
      a rule that transcribes the basis wrongly produces silently wrong causality (R-16).
      Auto-suggestion does NOT propose emissions: guessing which records witness an
      occurrence is a domain judgement, and a machine-written guess in a data file is
      exactly what the `PROPOSED_UNCONFIRMED` refusal exists to prevent. An event type with
      no rule is not an error — a dataset may legitimately carry no evidence of an
      occurrence the domain has — and coverage reports it as
      `MAP-W-EVENT-TYPE-NEVER-EMITTED` so the absence is a decision rather than an
      oversight. Modules 2 and 4.
    - `mapping.yaml`'s `identity_bindings[].observed_at` — the instant at which a record's
      statement ABOUT each entity type was true. Optional; omitting it means every attribute
      version carries the unbounded `UNKNOWN` interval, which is honest and is what a
      consumer needs to know before sequencing two versions by time. Module 3.
    - `cost.yaml` — cost class to ordinal band. Module 14.
    - `labels.yaml` — display strings. The only ontology data the presentation layer reads.
    - `rule_engine/<domain>/rules.yaml` — the rule pack. The schema is
      `causalog.rule_engine.dsl` (ADR-0044), normative as pydantic models exactly as the
      pack DSL is. Pass the loaded pack's `produced_event_types()` to
      `load_pack(..., produced_event_types=...)` and the `NOT_RUNNABLE` rule-coverage
      finding becomes a real check. Validate with
      `make rules DATASET=<domain>`, which checks every reference against this pack and
      writes a coverage report naming the event types no rule explains — **the blind spots
      of the whole system.** A domain with no rule pack yet is reported as `NOT-RUNNABLE`
      (exit 2), never as clean.

11. **Run the gate and record it.** `make lint typecheck test` must be green, and
    `PROGRESS.md` takes the pasted output — "I believe it works" is not evidence
    (`CONVENTIONS.md` §3). If the new domain forced a change to the DSL, that change needs
    an ADR, a `pack_schema_version` bump, `python scripts/export_ontology_schema.py --write`,
    and every existing pack revalidated in the same commit.

---

## 5. Changing the DSL

The models in `causalog.ontology_runtime.dsl` are normative. Changing them is not an edit:

1. Write the ADR first. It names every pack affected and the migration.
2. Bump `PACK_SCHEMA_VERSION` and this document's stated version.
3. Regenerate the published schema: `python scripts/export_ontology_schema.py --write`.
4. Update every pack in `ontology/packs/`, its tests, and `GLOSSARY.md`, in the same commit.
5. Note that every `ontology_hash` moves, and therefore every `run_id` (ADR-0013). Prior
   runs are not comparable to subsequent ones and must not be presented as if they were.

---

## 6. What this layer does not guarantee

Stated plainly, because a green load is easy to over-read.

- **A valid pack can be a wrong pack.** ADR-0002 predicted this: a bad ontology produces
  silently wrong causality rather than a crash. Nothing here checks that a declared
  transition matches how the business actually works, that a derivation basis is sound, or
  that an actionability flag is true. Tracked as risk **R-16**.
- **Rule coverage was unchecked until 2026-09-01, and is now a real check.** The
  `rule_engine/dataco/` pack exists (ADR-0044), so `load_pack(..., produced_event_types=...)`
  has a supplier and `ONT-N-RULE-COVERAGE` no longer reports `NOT_RUNNABLE`. What the check
  now says about DataCo is that **6 of 20 declared event types have no rule explaining
  them** — `docs/reports/dataco/rule-coverage.md` names them. That is a finding, not a
  failure: every one of the six is a root in this dataset, and a rule claiming to explain
  one would be inventing a mechanism the source does not witness. What is still true is the
  bullet above it: a valid pack, and now a valid rule pack, can be a wrong one.
- **DataCo column traceability was traceability to a manifest** until 2026-08-30. Module 1
  has now read the real file, pinned it by hash, and compared the two headers, so
  `columns.manifest.yaml` reads `VERIFIED` and names the `dataset_version` that verified it.
  The comparison re-runs on every import and a mismatch **fails** the import rather than
  rewriting the manifest to match whatever was on disk. What is still unverified is the
  *semantics*: that a column is bound to the RIGHT concept is checked by nothing (risk
  R-16).
- **Domain independence is proved for the schema, not for the output.** Two unrelated
  domains load through one code path and share no behavioural vocabulary. That a swap
  changes what the engine *concludes* still needs a pipeline —
  `tests/ontology/test_ontology_swap.py`, still open in `docs/architecture.md` §8.
