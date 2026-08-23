# CONVENTIONS.md — Engineering conventions

Binding on every session, every model, every contributor. A violation is a defect, not a
style preference. Where this file and `docs/prd.md` disagree, this file governs *how* and the
PRD governs *what* — and the disagreement itself is logged as an Open Question in
`CONTEXT.md` §8.

---

## 1. The Five Inviolable Laws

> Reproduced verbatim. Also present in `CONTEXT.md` §2. These two copies must remain
> byte-identical; a divergence between them is a defect.

1. **LAW-EVENT** — The reasoning core computes over `Event`, `Entity`, `State`, `Transition`, `Relationship`. Never over rows, never over DataFrames, never over CSV columns.
2. **LAW-TIME** — No causal edge may exist where `cause.timestamp >= effect.timestamp`. This is enforced in code, not by convention, and is unit-tested.
3. **LAW-PROVENANCE** — Every assertion carries a provenance class: `OBSERVED | ASSUMED | STATISTICAL | INFERRED | SIMULATED`. These are never merged, never silently promoted, and are visually distinct in the UI. Inferred results never overwrite observed facts.
4. **LAW-DOMAIN** — No file under `core/`, `graph_engine/`, `causal_engine/`, `counterfactual_engine/`, `recommendation_engine/` may contain the strings `warehouse`, `shipment`, `order`, `carrier`, `customer`, `delivery`, `inventory` (case-insensitive) outside of test fixtures. Enforced by a CI lint job.
5. **LAW-EVIDENCE** — Every confidence number decomposes into named, inspectable components with the evidence records that produced them. A bare float is a defect.

---

## 2. Model routing

Each module prompt carries a `MODEL:` tag. Respect it.

| Work type | Model | Why |
|---|---|---|
| Architecture, data model design, causal/statistical reasoning design, ADRs, ambiguity resolution, adversarial review | **Opus** | High-stakes irreversible decisions; errors here compound across the whole system |
| Module implementation, tests, refactors, UI components, wiring, docs generation | **Sonnet** | Volume work against an already-fixed contract |
| Validation Gates & drift audits | **Opus** | Reviewing needs a stronger reasoner than writing |

---

## 3. Definition of Done

A module is done only when **all** hold:

- Public interface matches the contract defined in Prompt 02 (or an ADR records the deviation).
- Unit tests pass, including at least one test per stated failure mode.
- `make lint typecheck test` is green; domain-independence lint passes.
- Deterministic: same inputs + same seed + same ontology hash ⇒ byte-identical outputs.
- `CONTEXT.md`, `PROGRESS.md`, and (if a decision was made) `DECISIONS.md` are updated in the same commit.
- The module's Validation Gate checklist in this document has been executed and its answers recorded.

Until then the module's status is `built-unverified`, never `done`. "I believe it works"
is not evidence; pasted command output in `PROGRESS.md` is.

---

## 4. Anti-drift rules

Include these in any session where the model appears to be wandering.

```
Hard rules for this session:
- Do not invent requirements. If the PRD is silent, stop and ask, or record the
  gap in CONTEXT.md under "Open Questions" with a proposed default.
- Do not expand scope. Version 1 excludes: streaming inference, autonomous
  execution, reinforcement learning, multi-company optimization, digital twins,
  predictive maintenance.
- Do not add ML where rules suffice. V1 intelligence comes from architecture,
  not model complexity.
- Do not modify files outside the module you were told to build.
- If you must deviate from a prior decision, write an ADR first and tell me.
```

---

## 5. Naming

| Thing | Convention | Example | Never |
|---|---|---|---|
| Python module / package | `snake_case` | `candidate_cause_generator` | `CandidateCauseGen` |
| Python class | `PascalCase` | `ConfidenceVector` | `confidence_vector` |
| Python function / variable | `snake_case` | `build_timeline` | `buildTimeline` |
| Constant | `UPPER_SNAKE` | `MAX_PROPAGATION_DEPTH` | magic literals inline |
| TypeScript component | `PascalCase` file + export | `CausalGraphExplorer.tsx` | `graph-explorer.tsx` |
| TS function / variable | `camelCase` | `fetchRootCause` | `fetch_root_cause` |
| API route | lowercase, hyphenated, plural nouns | `/root-cause/{order_id}` | `/getRootCause` |
| JSON field | `snake_case` | `provenance_class` | `provenanceClass` |
| Event type (ontology data) | `UPPER_SNAKE`, `<SUBJECT>_<PAST_PARTICIPLE>` | `INVENTORY_RESERVED` | `reserve_inventory` (an event is a thing that happened, not a command) |
| State (ontology data) | `UPPER_SNAKE`, adjectival | `SHIPMENT_DELAYED` | `DELAY` |
| Entity type (ontology data) | `UPPER_SNAKE` singular | `WAREHOUSE` | `WAREHOUSES` |
| Edge type (graph) | `UPPER_SNAKE` verb, present tense | `CAUSES`, `PRECEDES`, `AMPLIFIES` | `caused_by` (edges point cause → effect; never invert direction to read nicer) |
| Enum member | `UPPER_SNAKE` | `INFERRED` | `Inferred` |
| Test file | `test_<module>_<aspect>.py` | `test_confidence_scorer_determinism.py` | `tests.py` |
| Migration | `NNNN_<verb>_<subject>.sql` | `0003_add_provenance_class.sql` | dated filenames |

Additional rules:
- **No abbreviations** outside a fixed list: `id`, `ts`, `db`, `api`, `url`, `utc`. Write
  `confidence`, not `conf`; `propagation`, not `prop`.
- **Event type names are ontology data, not identifiers.** `INVENTORY_RESERVED` appears in
  `ontology/`, never as a Python constant in a core module (LAW-DOMAIN).
- **Never name a thing after where it came from.** `dataco_event` is a defect; there is
  only `Event`.

---

## 6. Module boundaries

### Dependency direction

Strictly downward through the `CONTEXT.md` §4 layer stack and forward through the §36
pipeline. Concretely:

0. Layer ranks and the nine forbidden edges are stated in `docs/architecture.md` §1 and
   enforced by `scripts/check_layers.py` (ADR-0016). The rules below are that document's
   prose form; where they disagree, the divergence is a defect to be filed.
1. A module may import from modules **earlier** in the pipeline and from shared
   `core/` types. It may never import from a **later** module.
2. No cross-layer reach-through: the API layer talks to the Causal Intelligence Core, not
   directly to the graph store.
3. Circular imports are a defect, not a refactoring opportunity. If two modules need each
   other, the shared concept belongs in `core/`.
4. Modules communicate **only** through the typed interfaces registered in `CONTEXT.md`
   §6. Passing a bare dict, a DataFrame, or a database handle across a module boundary is
   a defect.

### The `core/` purity rule

`core/` holds the five canonical types (`Event`, `Entity`, `State`, `Transition`,
`Relationship`), the provenance enum, the confidence structure, the timestamp
representation, and nothing else. It has **no** dependencies on any other project module,
no database access, and no I/O.

### LAW-DOMAIN lint specification

The lint job that enforces LAW-DOMAIN must be specified precisely, because a lint with a
high false-positive rate gets disabled — which returns LAW-DOMAIN to convention-only
status, the exact failure it exists to prevent.

- **Scope:** all files under `core/`, `graph_engine/`, `causal_engine/`,
  `counterfactual_engine/`, `recommendation_engine/`.
- **Banned tokens:** `warehouse`, `shipment`, `order`, `carrier`, `customer`, `delivery`,
  `inventory`.
- **Matching (ADR-0019):** case-insensitive **stem-prefix**, anchored by a letter-only
  lookbehind: `(?<![A-Za-z])(warehous|shipment|order|carrier|customer|deliver|inventor)[A-Za-z0-9_]*`.
  The lookbehind excludes `reorder`, `recorder`, `border` — a preceding *letter* means the
  stem is inside a longer word. It is deliberately not `\w`: a preceding underscore or
  digit means a separate identifier component (`sort_order`, `v2_customer`), which is
  banned. The tail spans the whole identifier, so `warehouse_id`, `orders`, `customerName`,
  and `OrderId` all match — and the *reported text* is the full identifier, which is what
  an allowlist entry keys on.
- **This replaced word-boundary (`\b`) matching, which was ineffective.** `\b` requires a
  non-word character after the token and `_` is a word character, so every identifier form
  above passed clean; the lint caught only the bare English word in a comment. See DEF-0001
  and ADR-0019. Naive substring matching is still wrong for the original reason — it hits
  `reorder`, `recorder`, `border`, `ordinal`.
- **No suffix exceptions.** The whole `order` stem is banned, so `ordering` and `ordered`
  may not appear in a reasoning package, including in a comment. Write "sequence",
  "sequenced", or "sorted". A SQL or Cypher `ORDER BY` literal in an in-scope file needs an
  allowlist entry with a justification.
- **Exempt:** files under `tests/fixtures/`; ontology and rule **data** files
  (`ontology/**`, `rule_engine/**/*.yaml|*.json`). `rule_engine` **source code** is
  **not** exempt.
- **Allowlist:** an explicit, reviewed list at `.lawdomain-allowlist`, keyed on the **exact
  reported text** (`warehouse_id`, not the `warehous` stem) so one entry exempts one
  occurrence and never a family. Every entry needs a one-line justification. Adding an entry
  requires review; it is a pressure valve, not a bypass.
- **Failure mode:** the job fails the build. It does not warn.
- **Implemented** as `scripts/check_domain_independence.py`. ADR-0010 added `core/` to the
  repository structure and closed OQ-006; ADR-0019 supersedes its matcher specification.
  The script ships a `--self-test` asserting two tables — every form vocabulary takes in
  code fires, and every genuinely non-domain word stays clean — plus a guard that refuses a
  claimed false positive which actually contains a banned stem. Both modes run as a
  required CI job.
- **Every enforcement script must be observed to reject, not merely to pass (ADR-0019).**
  All four law scripts (`check_domain_independence`, `check_layers`, `check_law_copies`,
  `check_dependency_policy`) ship `--self-test` and run it in CI before their scan. A check
  with only positive evidence is not evidence that a law is enforced — DEF-0001 is what
  that costs.
- **What it cannot catch:** domain dependence expressed as a branch on a data *value*
  rather than as vocabulary. That residual hole is stated in `docs/architecture.md` §1.5
  and §5.3, and is covered — imperfectly — by the ontology-swap test, not by this lint.

---

## 7. Error handling philosophy

**Fail loud on contract violation. Degrade explicitly on data quality. Never silently
drop an event.**

| Situation | Required behavior |
|---|---|
| Law violation (LAW-TIME, LAW-PROVENANCE, LAW-EVENT) | Raise immediately. Never repair, never skip. These are programming errors. |
| Interface contract violation (wrong type, missing required field) | Raise immediately at the boundary. Validate on entry, not on use. |
| Ontology mapping miss (a column/value with no ontology concept) | Hard error at mapping time with the unmapped value named. **Never** default, never guess, never fall through to "OTHER". |
| Malformed source record | Reject the record, increment a counter, record it in a reject log with a reason. The pipeline continues. The reject count appears in the run summary and in `PROGRESS.md`. |
| Missing timestamp | Not an error. Represent as `UNKNOWN` precision per §8. Never impute. |
| Ambiguous causality (interval overlap) | Not an error. Emit the edge as `UNDETERMINED`, blocked from `INFERRED` promotion. |
| Rule conflict at load time | Hard error at load. A rule set that contradicts itself may not be loaded. |
| External store unavailable | Raise with the store named and the projection version requested. Never serve a stale projection as if fresh. |

Rules:
- **A swallowed exception is a defect.** `except: pass` is never acceptable. If a failure
  is genuinely tolerable, it is logged at `WARNING` with the reason and counted.
- **Error types are a closed taxonomy** rooted at `CausaLogError`, with
  `LawViolationError`, `ContractViolationError`, `OntologyMappingError`,
  `DataQualityError`, `RuleConflictError`, `ProjectionStaleError`. Never raise a bare
  `Exception` or `ValueError` across a module boundary.
- **Error messages must be domain-neutral in core modules** (LAW-DOMAIN applies to strings
  too) and must name the offending identifier, the module, and the contract violated.
- **No error message may leak a raw record.** Reference the evidence record ID instead.

---

## 8. Logging and audit

### Logging

- Structured JSON only. No f-string prose logs.
- Required fields on every record: `timestamp` (UTC, ISO-8601 with offset), `level`,
  `module`, `run_id`, `execution_id`, `correlation_id`, `message`, `ontology_version`,
  `dataset_version`.
- Levels: `DEBUG` (developer tracing) · `INFO` (pipeline stage boundaries, counts) ·
  `WARNING` (tolerated data quality degradation, always with a count) · `ERROR` (an
  operation failed) · `CRITICAL` (a law was violated).
- **Amended by ADR-0013.** `run_id` is the *content-addressed* identifier of a Run —
  `"run:" + sha256(dataset_version | ontology_hash | rule_pack_version | engine_version |
  seed)[:16]` — and is stable across reruns of the same Run. `execution_id` is generated
  once per pipeline execution and threads through every stage; it is random and is excluded
  from every determinism comparison. `correlation_id` threads through an API request.
  Before ADR-0013 this file used `run_id` for both meanings.
- **Never log** raw source records, credentials, or full graph dumps.

### Audit (prd.md §54 — separate from logging, and durable)

The audit trail lives in Postgres, is append-only, and is retained independently of logs.
It must record:

| Auditable event | Must capture |
|---|---|
| Dataset import | dataset_version, source hash, record counts, reject counts |
| Ontology change | old and new `ontology_hash`, diff, actor |
| Rule set change | rule ids added/removed/modified, actor |
| Every inferred causal edge | edge id, source, target, `ConfidenceVector`, **evidence record IDs**, rule ids fired, run_id |
| Every recommendation | intervention id, ranking inputs, confidence, the root-cause analysis it derives from |
| Every counterfactual run | base world id, mutations applied, resulting `SimulatedWorld` id |
| Access to any endpoint returning inferences | actor, role, endpoint, correlation_id |

**LAW-EVIDENCE hook:** it must be possible, from an audit record alone, to reconstruct why
a confidence number has the value it has. If a confidence component cannot be traced to
evidence record IDs, the module is not done.

---

## 9. ID generation

**Deterministic, content-addressed. No UUID4, no autoincrement, no timestamps-as-IDs
anywhere in the reasoning pipeline.** The Definition of Done requires byte-identical
output across reruns; random or sequence-dependent IDs make that impossible.

```
<type_prefix>:<sha256(canonical_payload)[:16]>

evt:  Event          canonical_payload = ontology_hash | event_type | entity_ids(sorted)
                                        | timestamp_interval | changed_attributes(sorted)
                                        | evidence_record_ids(sorted)
ent:  Entity         = ontology_hash | entity_type | natural_key
sta:  State          = entity_id | state_name | timestamp_interval
trn:  Transition     = from_state_id | to_state_id | causing_event_id
edg:  CandidateEdge  = source_event_id | target_event_id | edge_type
evd:  EvidenceRecord = dataset_version | source_locator
sim:  SimulatedWorld = base_graph_id | mutations(canonically serialized)
run:  Run            = dataset_version | ontology_hash | rule_pack_version
                                       | engine_version | seed          (ADR-0013)
```

Rules:
- `canonical_payload` is a UTF-8 string with `|` separators, all collections sorted by
  their canonical sort key (§10), all floats formatted per §10.
- Collisions are checked at insert; a collision on differing payloads is a `CRITICAL`
  defect, not a retry.
- Postgres surrogate keys may exist for storage efficiency but are **never** exposed
  across a module boundary or in an API response.
- Sequential or random IDs are permitted only for `execution_id` and `correlation_id`,
  which are excluded from all determinism comparisons. **Amended by ADR-0013:** `run_id` is
  content-addressed like every other identifier here —
  `run_id = "run:" + sha256(dataset_version | ontology_hash | rule_pack_version |
  engine_version | seed)[:16]` — and is therefore *included* in determinism comparisons. It is the thing determinism is
  asserted against. The per-execution identifier this rule previously called `run_id` is
  now `execution_id`.

---

## 10. Timestamps, timezones, and temporal uncertainty

This is a temporal reasoning system. Time handling is not a detail; LAW-TIME depends
entirely on it. These rules are strict and admit no exceptions.

### Storage

- **All timestamps are stored in UTC. Always.** Postgres `TIMESTAMPTZ`; Python
  timezone-aware `datetime` with `tzinfo=UTC`; JSON as ISO-8601 with an explicit `Z` or
  numeric offset.
- **A naive datetime is a defect.** It may not be constructed, parsed into, stored, or
  passed across any boundary.
- **Local time never exists inside the system.** It is a rendering concern, applied in the
  UI at display time only. Because local time never exists internally, DST is not a
  concern anywhere in the engine — and this is the reason the rule is absolute.
- The original source timezone (or its absence) is recorded on the `EvidenceRecord`, never
  on the `Event`.

### Representation — every event timestamp is an interval

A single `datetime` cannot express "this happened on 2017-03-14, precision unknown within
the day." The DataCo dataset is day-granularity in places, so this is the common case, not
an edge case.

```
TimeInterval:
    t_earliest : datetime  (UTC, inclusive)
    t_latest   : datetime  (UTC, inclusive)
    precision  : EXACT | SECOND | MINUTE | HOUR | DAY | UNKNOWN
    provenance : OBSERVED | ASSUMED
```

| precision | Meaning | Interval construction |
|---|---|---|
| `EXACT` | Sub-second known | `t_earliest == t_latest` |
| `SECOND` / `MINUTE` / `HOUR` / `DAY` | Known to that granularity | interval spans the full containing bucket |
| `UNKNOWN` | No time information | `t_earliest = -inf`, `t_latest = +inf`, provenance `ASSUMED` |

### Missing and imprecise timestamps

- **Never impute.** Not `now()`, not epoch, not the previous event's time, not the median.
  Imputation manufactures causality out of nothing.
- Missing ⇒ `precision = UNKNOWN`, provenance `ASSUMED`.
- A bound derived from process constraints (e.g. "after the event that caused it") may
  narrow the interval, but the result is provenance `ASSUMED` and the derivation is
  recorded as an evidence record.
- An event with `UNKNOWN` precision may exist in the graph and appear on a timeline, but
  it may never participate in an `INFERRED` causal edge.

### LAW-TIME evaluation over intervals

LAW-TIME states `cause.timestamp >= effect.timestamp` is forbidden. With intervals that
becomes a three-valued test:

| Condition | Verdict | Effect on the edge |
|---|---|---|
| `cause.t_latest < effect.t_earliest` | `CERTAIN` | Edge is temporally admissible; may be promoted to `INFERRED`. |
| `cause.t_earliest >= effect.t_latest` | `VIOLATION` | Edge is rejected. Never created. |
| intervals overlap | `UNDETERMINED` | Edge may exist as a `CandidateEdge`, is flagged `UNDETERMINED`, and is **blocked from promotion to `INFERRED`**. |

`UNDETERMINED` is retained rather than discarded so that a data-quality problem stays
visible instead of silently shrinking the graph. The `UNDETERMINED` count is reported in
every run summary. See `CONTEXT.md` OQ-002 — this interpretation is the proposed default
and requires an ADR before module 9 is built.

### Duration and arithmetic

- Durations are stored as integer **seconds**, never as floats, never as strings.
- A duration derived from two intervals carries its own uncertainty
  (`[min_duration, max_duration]`) and is never collapsed to a point estimate in storage.
  Collapsing for display is permitted; collapsing for computation is a defect.
- Never compare timestamps across differing `dataset_version`s without recording it.

---

## 11. Determinism and seeding

**Guarantee:** identical inputs + identical seed + identical `ontology_hash` ⇒
**byte-identical** outputs.

"Byte-identical" covers: all persisted artifacts, all API response bodies, all generated
IDs, all serialized graphs, all explanation text. It does not cover `execution_id`,
`correlation_id`, wall-clock log timestamps, or performance measurements — these are the
only permitted sources of run-to-run variation and must be excluded from comparison
explicitly, not accidentally. `scripts/check_determinism.py` performs exactly those
exclusions and no others.

Required practices:

| Threat to determinism | Required practice |
|---|---|
| Random IDs | Content-addressed IDs (§9). |
| Unordered iteration (`set`, `dict` before insertion order, graph adjacency, DB rows without `ORDER BY`) | **Canonical sort key on every iteration** that affects output. Every SQL query feeding the pipeline has an explicit `ORDER BY` on a unique key. Cypher results are sorted before use. |
| Float non-associativity | Accumulate in a canonical order; **quantize confidence values to 6 decimal places at every serialization boundary**; never compare floats for equality. |
| Hash randomization | `PYTHONHASHSEED=0` in every pipeline entry point and CI job. |
| Parallelism | Results are reduced in a canonical order independent of completion order. |
| Wall-clock reads | Time is injected, never read from the ambient clock inside the pipeline. `datetime.now()` in a reasoning module is a defect. |
| Library nondeterminism | Blocked for V1 by ADR-0003. Any introduction requires an ADR + a named seed contract. |

**Canonical sort keys** (use these, do not invent alternatives): events by
`(t_earliest, t_latest, event_id)`; entities by `entity_id`; edges by
`(source_event_id, target_event_id, edge_type)`; confidence components by `component_name`.

**Output envelope.** Every artifact and API response carries `run_id`, `ontology_version`,
`ontology_hash`, `dataset_version`, `rule_pack_version`, `engine_version`,
`graph_projection_version`, `seed`, and `execution_id` (ADR-0013). An output without its
envelope cannot be verified and is a defect.

**Determinism test.** Every module ships one: run twice, assert byte-identical output.
This is a Definition-of-Done item, not an optional extra.

---

## 12. Dependency policy

Adding any third-party dependency requires an **ADR** before the import is written. The
ADR must state:

1. What problem it solves that the standard library and existing dependencies do not.
2. Whether it introduces nondeterminism (if yes, see §11 — it needs a seed contract).
3. Whether it introduces domain assumptions (LAW-DOMAIN).
4. License, maintenance status, and transitive dependency count.
5. The removal cost if it is later abandoned.

Rules:
- **Pin exact versions.** No ranges, no `latest`.
- **Blocked for V1:** `pgmpy`, `dowhy`, `torch`, `torch-geometric`, and any ML training or
  probabilistic-inference library (ADR-0003). `scripts/check_dependency_policy.py` enforces
  the import ban, asserts every pin is exact, and fails if `pyproject.toml` declares a
  package ADR-0015 does not name.
- **`core/` takes no third-party dependencies at all** beyond the standard library and the
  chosen data-validation library.
- No dependency may be added to satisfy a deferred/out-of-scope item (`CONTEXT.md` §10).

---

## 13. Commit messages

```
<type>(<module>): <imperative summary, <=72 chars>

<body: what changed and why. Wrap at 80. Explain the why; the diff shows the what.>

Context-Updated: yes | no-change-required
ADR: ADR-NNNN | none
OQ: OQ-NNN[, OQ-NNN] | none
Gate: passed | not-applicable | deferred(<reason>)
```

- `type` ∈ `feat` · `fix` · `refactor` · `test` · `docs` · `chore` · `adr` · `gate`.
- `module` is a `CONTEXT.md` §3 module name in `snake_case`, or `governance`.
- **`Context-Updated: no-change-required` is a claim that will be audited.** Per the
  Definition of Done, code changes and their `CONTEXT.md` / `PROGRESS.md` /
  `DECISIONS.md` updates ship in the **same commit** — never a follow-up.
- A commit that changes a `frozen` interface without an `ADR:` trailer is rejected.
- One logical change per commit. Do not mix a refactor with a behavior change.

---

## 14. Test taxonomy

Derived from prd.md §56 and extended for the laws. Each kind has a distinct job; do not
collapse them.

| Kind | Location | Asserts | May NOT assert | Gate role |
|---|---|---|---|---|
| **Unit** | `tests/unit/` | One module's behavior in isolation, all stated failure modes | Cross-module integration | DoD: required, ≥1 test per failure mode |
| **Law** | `tests/law/` | LAW-TIME never violated; `OBSERVED` never overwritten; core module holds no row/DataFrame; confidence never a bare float | Business correctness | **Blocking. A failure here is `CRITICAL`.** |
| **Determinism** | `tests/determinism/` | Two runs, same seed + ontology hash ⇒ byte-identical output | Correctness of the output, only its stability | DoD: required per module |
| **Integration** | `tests/integration/` | Adjacent modules interoperate across the registered interface | Whole-pipeline outcomes | Required at phase boundaries |
| **Pipeline** | `tests/pipeline/` | End-to-end run on a fixture dataset produces a well-formed graph | Causal accuracy (no ground truth exists) | Required to exit a phase |
| **Graph invariant** | `tests/graph/` | Edge direction, no temporal violations, cycle detection correctness, propagation depth arithmetic | Whether a specific edge is *true* | Required for modules 8–12 |
| **Ontology mapping** | `tests/ontology/` | Every dataset column maps or hard-fails; ontology swap changes output without code change | Reasoning quality | Required for modules 2–4 |
| **Counterfactual consistency** | `tests/counterfactual/` | A null intervention reproduces the base world; mutations never write back to history; `SIMULATED` provenance preserved | Real-world accuracy of the simulation | Required for module 13 |
| **API contract** | `tests/api/` | Response schema, provenance fields present, output envelope present | UI behavior | Required for module 16 |
| **UI** | `tests/ui/` | Graph interaction, provenance classes visually distinct | Backend logic | Required for the frontend |

Rules:
- **Fixtures are synthetic and domain-neutral by default.** DataCo-derived fixtures live
  only in `tests/fixtures/dataco/` and are the sole place LAW-DOMAIN vocabulary may appear
  in tests.
- **No test may assert a causal conclusion is correct** — there is no ground truth for
  causality in this dataset. Tests assert *structural* properties (ordering, provenance,
  determinism, decomposability), not truth. Claiming otherwise in a test name is a defect.
- A bug fix ships with a regression test that fails before the fix.
- Coverage percentage is reported, never used as the gate. The gate is failure-mode
  coverage: every failure mode named in `PROGRESS.md` has a test.
