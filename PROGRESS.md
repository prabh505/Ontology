# PROGRESS.md — Build ledger

What was actually built, what was deliberately not built, and the evidence that let each
module pass its gate. This file is the answer to "can I trust module N?"

**Rules.**
1. One section per module, in `CONTEXT.md` §3 order. Never delete a section.
2. **"Deliberately not built" is mandatory and may not be empty for a completed module.**
   An unstated omission becomes a silent assumption for the next session, which is the
   failure mode this project is structured to prevent.
3. **Validation evidence is pasted command output, not prose.** "Tests pass" is not
   evidence. A test summary line with counts is.
4. Status here must match `CONTEXT.md` §3 exactly. A mismatch is a defect
   (`HANDOFF.md` §3).
5. Update in the same commit as the code (`CONVENTIONS.md` §3).

---

## Entry template

```markdown
## <NN>. <Module name>

- **Status:** not-started | in-progress | blocked | built-unverified | done
- **Phase:** P<N>
- **Owner prompt:** <prompt id>
- **Model:** <model that built it>
- **Dates:** started YYYY-MM-DD · gate passed YYYY-MM-DD
- **Contract:** <interface names from CONTEXT.md §6> — draft | frozen
- **Versions in force:** ontology_hash=<...> dataset_version=<...>

### Built
- <capability> — <where>

### Deliberately NOT built
| Omission | Why | Revisit when |
|---|---|---|

### Known limitations
| # | Limitation | Impact | Tracked as |
|---|---|---|---|

### Failure modes and their tests
| Failure mode | Test | Status |
|---|---|---|

### Test coverage summary
| Kind | Count | Result |
|---|---|---|
(unit / law / determinism / integration / graph / ontology / counterfactual / api / ui —
per CONVENTIONS.md §14. Line coverage % is reported but is NOT the gate; failure-mode
coverage is.)

### Validation evidence (Definition of Done)
| DoD item | Evidence |
|---|---|
| Interface matches contract | <ADR or contract ref> |
| Unit tests pass, ≥1 per failure mode | ```<pasted output>``` |
| `make lint typecheck test` green | ```<pasted output>``` |
| Domain-independence lint passes | ```<pasted output>``` |
| Deterministic (byte-identical rerun) | ```<pasted output>``` |
| CONTEXT/PROGRESS/DECISIONS updated same commit | <commit sha> |
| Validation Gate checklist executed | <date, model, link> |

### Open questions raised by this module
- OQ-NNN — <one line>
```

---

## Current ledger state

**No module has been started. No business logic exists.** What changed on 2026-08-25 is
that `causalog.core` is now implemented and frozen rather than sketched — see
**P0b. Canonical core** below. What changed on 2026-08-29 is that the storage layer is real
— see **00d. Persistence layer** — so a fact now has somewhere to go. Neither moves the
module ledger: `core/` is the shared contract layer, `ontology_runtime/` is an extension
seam, and `persistence/` is a set of driven adapters with no layer rank. There is still no
pipeline, no ingestion, and nothing that reads a dataset into the engine.

The repository contains the six governance files, `docs/prd.md`, `docs/architecture.md`,
`docs/contracts.md`, the package scaffold with an implemented `core/`, the enforcement
scripts, and the local stack.

Every module below is `not-started`; all fields are empty by fact, not by omission. OQ-001
(module authority) and OQ-002 (LAW-TIME over intervals) are both resolved, so the
prerequisites recorded against modules 1 and 9+ no longer block — what blocks now is simply
that nobody has built them.

| # | Phase | Module | Status | Contract | Gate |
|---|---|---|---|---|---|
| 1 | P1 | Data Adapter | not-started | draft | — |
| 2 | P1 | Schema Mapper | not-started | draft | — |
| 3 | P1 | Entity Extractor | not-started | draft | — |
| 4 | P1 | Event Generator | not-started | draft | — |
| 5 | P2 | Timeline Builder | not-started | draft | — |
| 6 | P2 | State Engine | not-started | draft | — |
| 7 | P2 | Relationship Resolver | not-started | draft | — |
| 8 | P2 | Temporal Graph Builder | not-started | draft | — |
| 9 | P3 | Candidate Cause Generator | not-started | draft | — |
| 10 | P3 | Confidence Scorer | not-started | draft | — |
| 11 | P3 | Root Cause Analyzer | not-started | draft | — |
| 12 | P3 | Propagation Analyzer | not-started | draft | — |
| 13 | P4 | Counterfactual Simulator | not-started | draft | — |
| 14 | P4 | Intervention Optimizer | not-started | draft | — |
| 15 | P5 | Explanation Generator | not-started | draft | — |
| 16 | P5 | Visualization API | not-started | draft | — |

---

## P0. Architecture blueprint and repository scaffold

- **Status:** built-unverified · **Phase:** P0 · **Model:** Opus
- **Dates:** started 2026-08-23 · gate passed —
- **Contract:** all `CONTEXT.md` §6 rows — **draft**; nothing frozen (OQ-009)
- **Versions in force:** `engine_version=0.1.0`; `ontology_hash`, `dataset_version`,
  `rule_pack_version` all `unset`

Status is `built-unverified`, not `done`, and deliberately so: the Definition of Done
requires a passing determinism check, and the determinism check cannot run yet (OQ-014).
Claiming `done` here would be the exact failure the status vocabulary exists to prevent.

### Built

- `docs/architecture.md` — layer map with ranks L0–L10; forbidden edges F1–F9 stated
  explicitly because they are lint-enforced; the 16-module inventory (responsibility,
  typed input/output, invariants, failure modes and partial-data behaviour, explicit
  prohibitions); the PostgreSQL/Neo4j/Redis boundary with its consistency model and a
  six-step rebuild procedure; the Run model; six extension seams with a worked hospital
  walkthrough proving a zero-line reasoning diff; three mermaid sequence diagrams.
- Repository scaffold — one installable distribution `causalog` at `backend/src/causalog/`
  (ADR-0012), 33 packages, each with `__init__.py`, a `README.md` stating its single
  responsibility and forbidden dependencies, and a mirrored `tests/unit/` directory.
- Draft `core/` contracts — the five canonical types, `ProvenanceClass` with the
  weakest-first aggregation ranking, `TimeInterval`/`Precision`/`TemporalVerdict`,
  `ConfidenceVector`, `EvidenceRecord`, `RunKey`, `OutputEnvelope`, the `CausaLogError`
  taxonomy, the identifier scheme, and six ports. Field declarations and docstrings only;
  every behavioural function raises `NotImplementedError`.
- Enforcement scripts, standard library only — `check_domain_independence.py` (LAW-DOMAIN),
  `check_layers.py` (F1–F9), `check_dependency_policy.py`, `check_law_copies.py`,
  `check_governance_consistency.py`, `check_determinism.py`, `rebuild_graph.py`. Every one
  of the five law checks ships `--self-test` and is observed to reject before it is
  trusted to pass (ADR-0019).
- `check_stack_preflight.py` — an environment preflight, deliberately NOT a law and absent
  from `make laws`: the container runtime's reachability, its memory against the 4 GB
  floor, and every published host port, each failure carrying its remedy. `make up`
  depends on it, so the Neo4j out-of-memory kill arrives as a named precondition instead
  of as `exit 137`. Ports this project already publishes are not conflicts, so `make up`
  stays idempotent.
- Tooling — `pyproject.toml` with exact pins, ruff, `mypy --strict`, pytest with coverage
  reporting; `Makefile` (`setup doctor up down verify lint typecheck laws test test-fast
  bench rebuild-graph reset`); Docker Compose with five healthchecked services and overridable
  host ports; two numbered SQL migrations; a twelve-job GitHub Actions workflow.
- Frontend — Next.js with TypeScript in strict mode (plus `noUncheckedIndexedAccess` and
  `exactOptionalPropertyTypes`), ESLint flat config, Prettier.
- Governance — ADR-0006, 0010, 0012–0018 in `DECISIONS.md`; `CONTEXT.md` §0/§3/§4/§6/§7/
  §8/§9/§11 updated; `CONVENTIONS.md` §6/§8/§9/§11/§12 amended; `HANDOFF.md` §1/§2/§3
  updated; eight terms added to `GLOSSARY.md`.

### Deliberately NOT built

| Omission | Why | Revisit when |
|---|---|---|
| Any of the 16 module implementations | The task is scaffolding, contracts of intent, and tooling. A module built before its contract document exists would be frozen by assertion. | Module 1 begins (OQ-001 now resolved) |
| Ontology content for DataCo | prd.md §21's vocabulary is one instance, authored with module 2; an ontology written now would be guessed against a dataset nobody has mapped. | Module 2 |
| Rule pack content | Rules first have a consumer at module 9; an unratified rule would fire against an unvalidated graph. | Module 9 |
| Neo4j schema / constraints as a migration | The projection is derived and is built only by module 8 (ADR-0001). A migration creating graph structure would create structure with no fact behind it. | Module 8 |
| Alembic or any ORM | Numbered raw SQL is what the `CONVENTIONS.md` §5 migration naming rule already implies (ADR-0015). | A migration need SQL cannot express |
| A migration *runner* | Compose runs `sql/migrations/` as the PostgreSQL init directory, which covers a fresh local database but not an upgrade of an existing one. | The first migration applied to a non-empty database |
| React Flow, Cytoscape.js, D3, ECharts | No module consumes them; the choice depends on module 16's payload shape (ADR-0018). | Module 16 |
| `pgmpy`, `dowhy`, `torch`, `torch-geometric` | ADR-0003; prd.md §45 stages them at V2+. Import ban enforced. | V2 |
| Any interface marked `frozen` | Blocked by OQ-009 until the module contract document exists. | "Prompt 02" delivered |
| Authentication / RBAC (prd.md §54) | No endpoint returns an inference yet, so there is nothing to protect and no role model to protect it with. | Module 16 |

### Known limitations

| # | Limitation | Impact | Tracked as |
|---|---|---|---|
| 1 | The determinism gate cannot run; its CI job is `continue-on-error` | The Definition of Done's determinism item is unverifiable for every module until the pipeline exists. A gate that cannot run looks identical to one that passes unless it says so loudly — this one exits 2 and prints why. | OQ-014 |
| 2 | The layer-rank table exists in two places (document and script) with only a weak automated comparison | A changed rank could diverge silently, so the document would teach a rule the build does not enforce. | OQ-015 |
| 3 | LAW-DOMAIN cannot catch domain dependence expressed as a branch on a data *value* | Domain leakage remains possible without any banned token appearing. Covered imperfectly by the planned ontology-swap test. | `docs/architecture.md` §1.5, ADR-0002 |
| 5 | `npm audit` reports 3 high-severity advisories in `next`'s transitive `postcss` and `sharp`; no patched `next` release addresses them without a major bump | Build-time and image-processing dependencies of the dev server. Not reachable from any code we wrote, because we wrote none. | Revisit at module 16, or when a patched `next` ships |
| 6 | ~~`make up` was not verified with all five services healthy simultaneously~~ **RESOLVED 2026-08-27.** All five verified healthy together on a 4 CPU / 8 GiB Colima VM, with two unrelated project stacks resident; `/healthz` and the frontend root both returned 200, and a second `make up` was a no-op. Peak usage was neo4j 837 MiB of its 1 GiB limit and frontend 510 MiB of 1 GiB — the earlier 1.9 GB allocation was the whole cause. The condition is now detected rather than documented: `make doctor` fails with the remedy when the runtime is below 4 GB or a port is taken. | none — the residual is that 4 GB is the *floor*, and Neo4j at 837 MiB of 1 GiB has little headroom under load. | `deployment/README.md`, `scripts/check_stack_preflight.py` |
| 7 | **LAW-DOMAIN was unenforced for the whole period between the scaffold landing and DEF-0001.** The shipped `\b` matcher caught only the bare English word; every identifier form passed clean, and the self-test certified two domain words as false positives. `CONTEXT.md` R-10 asserted "in force" throughout. | Any domain vocabulary committed to a reasoning package in that window would not have been caught. The current scan is clean, so nothing escaped in practice — but that is luck, not evidence. | DEF-0001, ADR-0019 |
| 8 | The LAW-DOMAIN lint reads only `.py`, `.md`, `.sql`, `.cypher`, and still cannot catch a branch on a data *value* | A green LAW-DOMAIN job is not proof of domain independence. | OQ-016 |
| 9 | `mypy` does not typecheck the test tree | unchanged from the previous entry | — |
| 10 | The Neo4j and Redis adapters, the orchestration pipeline, and the rebuild implementation are contracts only | `make rebuild-graph` and `make bench` both report NOT-YET-RUNNABLE. | Module 8 |

### Failure modes and their tests

| Failure mode | Test | Status |
|---|---|---|
| Domain vocabulary reaches a reasoning package | `tests/law/test_law_domain_lint.py::test_planted_violation_is_detected` | passing |
| **Domain vocabulary reaches a reasoning package as an identifier** (`warehouse_id`, `orders`, `WAREHOUSE_TABLE`, `customerName`, `OrderId`) | `::test_identifier_forms_fire` (14 forms) | passing — **DEF-0001 regression** |
| The four review probes that defeated the first matcher | `::test_review_probes_now_fire` (4 probes, verbatim) | passing — **DEF-0001 regression** |
| The lint's own self-test certifies a hole as correct behaviour | `::test_self_test_rejects_a_poisoned_must_not_fire_list` | passing — **DEF-0001 root cause** |
| The LAW-DOMAIN lint fires on a legitimate near-miss word | `::test_matcher_does_not_fire_on_near_misses` (14 words) | passing |
| An allowlist entry silently exempts a whole family | `::test_allowlist_exempts_the_exact_match_only` | passing |
| An allowlist entry bypasses review by omitting a justification | `::test_allowlist_entry_without_justification_fails` | passing |
| An inference path reads `Event.trigger`, turning an OBSERVED field into an unscored causal claim | `tests/law/test_trigger_is_not_an_inference_input.py` | passing **vacuously** — no module exists yet; it exists to fail when module 9 lands |
| `Event.trigger` becomes an edge-shaped identifier field (ADR-0020's rejected Option B) | `tests/unit/core/test_canonical_types.py::test_trigger_is_optional_and_distinct_from_any_edge_field` | passing |
| Actionability is looked up in the ontology at L6 instead of read from the event | `::test_event_carries_ontology_declared_actionability` + forbidden edge F3 | passing |
| A law script ships without a way to prove it rejects | `tests/law/test_enforcement_scripts_prove_themselves.py::test_every_law_script_has_a_passing_self_test` (4 scripts) | passing |
| The law-copy check never detects a divergence | `::test_divergence_is_detected`, `::test_missing_law_is_detected` | passing |
| A range pin, an ADR-less package, or a blocked import escapes | `::test_range_pin_rejected`, `::test_undeclared_package_rejected`, `::test_blocked_import_rejected` | passing |
| Any of the nine forbidden dependency edges is written | `tests/law/test_layer_boundaries.py::test_forbidden_edge_is_rejected` (8 cases) | passing |
| A legitimate downward import is wrongly rejected | `::test_permitted_edge_is_accepted` (6 cases) | passing |
| The Five Laws diverge between the two governance files | `tests/law/test_five_laws_are_stated_identically.py` | passing |
| A canonical type becomes mutable, breaking ADR-0004 immutability | `tests/unit/core/test_canonical_types.py::test_canonical_types_are_immutable` | passing |
| An assertion is constructed without a provenance class | `::test_every_assertion_carries_a_provenance_class` | passing |
| Confidence is expressible as a bare float | `::test_confidence_is_never_a_bare_float` | passing |
| A reproducibility input is dropped from the Run fingerprint | `::test_run_key_carries_all_five_reproducibility_inputs` | passing |
| A blocked ML library is declared or imported | `scripts/check_dependency_policy.py` in CI | passing (no test; script is the check) |

### Test coverage summary

| Kind | Count | Result |
|---|---|---|
| law | 71 | passed |
| unit | 37 | passed |
| determinism | 0 | **NOT-YET-RUNNABLE** (OQ-014) |
| integration / pipeline / graph / ontology / counterfactual / api / ui | 0 | not applicable — no module exists |

Line coverage is reported (61% of the scaffold, which is almost entirely type
declarations) and is **not** the gate. The gate is failure-mode coverage, tabulated above.

### Validation evidence (Definition of Done)

| DoD item | Evidence |
|---|---|
| Interface matches contract | Not applicable — no contract document exists (OQ-009). All rows `draft`. |
| Unit tests pass, ≥1 per failure mode | `108 passed` (55 at scaffold; +49 from DEF-0001's regression and self-proof suites; +4 from the ADR-0008/0020 contract and law tests) |
| `make lint` green | `All checks passed!` / `108 files already formatted` |
| `make typecheck` green | `Success: no issues found in 52 source files` |
| Domain-independence lint passes | `self-test passed: 24 vocabulary forms fire, 17 non-domain words stay clean, and no claimed false positive hides a banned stem.` / `LAW-DOMAIN: clean across 49 file(s) in 6 package(s).` |
| Every law check proves it rejects | `check_law_copies`: `3 defect shapes rejected, identical copies accepted` · `check_layers`: `9 forbidden edges rejected (F1-F9 all covered), 6 permitted edges accepted` · `check_dependency_policy`: `5 policy violations rejected, 3 clean inputs accepted` |
| The four review probes fail the build | probes appended to `core/temporal.py` → `LAW-DOMAIN: 6 violation(s) across 49 file(s). BUILD FAILED.` exit 1; reverted → clean |
| Layer boundaries clean | `LAYER BOUNDARIES: clean across 52 file(s).` |
| Dependency policy clean | `DEPENDENCY POLICY: clean; 13 pinned dependencies, all ADR-backed.` |
| Five Laws identical | `FIVE LAWS: byte-identical across CONTEXT.md §2 and CONVENTIONS.md §1.` |
| Deterministic (byte-identical rerun) | `DETERMINISM: NOT-YET-RUNNABLE.` (exit 2) — **this item is NOT satisfied**, which is why the status is `built-unverified` |
| Frontend lint + typecheck | `eslint .` clean; `prettier --check .` — *All matched files use Prettier code style!*; `tsc --noEmit` clean |
| Local stack healthy | `postgres`, `redis`, `backend` healthy together, and separately `postgres`, `neo4j`, `redis`; migrations applied (`run`, `audit_log`); a `DELETE FROM audit_log` was a verified no-op, so append-only is enforced by the database, not by convention. Five-at-once blocked by host memory — see limitation 6. |
| CONTEXT/PROGRESS/DECISIONS updated same commit | this entry, `CONTEXT.md` §11, `DECISIONS.md` ADR-0006/0010/0012–0018 |
| Validation Gate checklist executed | not yet — no gate exists for a P0 deliverable |

### OQ defaults used without ratification

Recorded here because `HANDOFF.md` §2 check 7 requires it. `docs/architecture.md` uses each
of these as a stated default and names the OQ inline; none is ratified, and each still
blocks its module.

| OQ | Default used | Blocks |
|---|---|---|
| OQ-005 | `ConfidenceVector` authoritative, scalar derived; event field named `extraction_confidence` | module 10 until ADR-0009 |
| OQ-007 | V1 counterfactuals are a labelled plausibility simulation, not an effect estimate | module 13 until ADR-0011 |
| OQ-013 | Cost is ontology configuration on an ordinal band with `ASSUMED` provenance | module 14 |

**Promoted to decisions on 2026-08-23** — no longer assumptions: OQ-002 → **ADR-0007**,
OQ-003 → **ADR-0008**, OQ-012 → **ADR-0020**. `docs/architecture.md` and the `core/`
contracts were already built on these defaults; the ADRs ratify what the code assumes rather
than changing it, with two exceptions worth naming: `Event` gained `is_actionable`, and the
prohibition on inference reading `Event.trigger` is new and now has a law test.

### Open questions raised by this module

- OQ-014 — the determinism gate cannot run and its CI job is `continue-on-error`.
- OQ-015 — the layer-rank table exists in two places with only a weak copy check.
- OQ-016 — the LAW-DOMAIN lint's remaining residuals: unscanned file types, and domain
  dependence expressed as a branch on a data value.

---

## P0b. Canonical core

- **Status:** built-unverified · **Phase:** P0 · **Model:** Opus
- **Dates:** started 2026-08-25 · gate passed —
- **Contract:** every `causalog.core` row in `CONTEXT.md` §6 — **frozen** at
  `docs/contracts.md` v1.0.0 (ADR-0025)
- **Versions in force:** `engine_version=0.1.0`;
  `event_schema_version=entity_schema_version=edge_schema_version=confidence_schema_version=1.0.0`;
  `ontology_hash`, `dataset_version`, `rule_pack_version` still `unset`

Status is `built-unverified`, not `done`, for the same reason as P0: the Definition of Done
requires a passing determinism check, and that check still cannot run (OQ-014) because no
orchestration pipeline exists for it to run twice. Every other DoD item is met and its
evidence is below.

### Built

- **Content addressing** — `core/identifiers.py`. `digest` implemented; the eight payload
  recipes of `CONVENTIONS.md` §9 exposed as an `address` classmethod on each type; leaf
  escaping so a value containing `|`, `,`, or `=` cannot fake a field boundary; one float
  formatter and one instant formatter for the whole system.
- **Interval timestamps and LAW-TIME** — `core/temporal.py`. `TimeInterval` now enforces the
  invariants it previously only documented; `provenance` admits `INFERRED` with a required
  `source` (ADR-0021); `TimestampKind` derived; `strictly_before`, `verdict`,
  `is_unverifiable`, `canonical_interval`.
- **The provenance algebra** — `core/provenance.py`. `PROVENANCE_STRENGTH` derived from
  `WEAKEST_FIRST`; `combine` returns the weakest input and refuses an empty call.
- **Confidence** — `core/types/confidence.py` and `core/aggregation.py`. `ConfidenceVector`
  gains `aggregation`; a frozen registry with `weighted_mean_v1` (default) and `minimum_v1`;
  `aggregate` sequences components, quantizes the scalar, and sets provenance from `combine`.
- **The edge taxonomy** — `core/types/causal_edge.py`. Five payload types under a
  discriminated union; `CausalEdge.between` as the only LAW-TIME-checking constructor;
  `temporally_unverifiable` beside the verdict; `edge_kind`, `rule_support`, and
  `statistical_support` as derived properties so no number is stored twice.
- **Evidence** — `core/types/evidence.py`. `EvidenceItem` added alongside `EvidenceRecord`,
  carrying the `verification` text that makes an item independently re-executable.
- **Entity lifecycle and derived state** — `core/types/entity.py`, `core/derivation.py`.
  `Lifecycle` stored; `current_state` a pure function of an entity *and an instant*.
- **Serialization** — `core/serialization.py`. Versioned envelope, sorted keys, floats as
  quantized strings, full re-validation on the way in.
- **Immutability** — `core/immutability.py`. `revise` refuses an `OBSERVED` artifact,
  including a revision that tries to relabel its provenance first.
- **Run** — `core/run.py`. `RunKey.address()`; `Run` re-derives and checks its own `run_id`.
- **The contract document** — `docs/contracts.md` v1.0.0, closing OQ-009.

### Deliberately NOT built

| Omission | Why | Revisit when |
|---|---|---|
| Any module that *produces* these types | `core/` declares what the pipeline computes over; building a producer here would put ingestion logic in L0 and breach forbidden edge F1 | Module 3 (Entity Extractor) and module 4 (Event Generator) |
| The §26-to-§47 graph projection | `CAUSES`/`AMPLIFIES`/`REDUCES` are a *graph* vocabulary; mapping the taxonomy onto them is the Temporal Graph Builder's job, and doing it in `core` would make L0 know about the projection | Module 8 |
| Persistence of any kind | `core/` has no I/O by contract; the ports exist, the adapters do not | Module 1, wired by Orchestration (ADR-0014) |
| A `SimulatedWorld` type | The `sim` prefix is reserved in `IdentifierPrefix`, but the shape depends on ADR-0011, which does not exist | Module 13, after ADR-0011 |
| Confidence *calibration* | There is no causal ground truth in this dataset to calibrate against; the weights are a stated judgement, not a fit | Labelled ground truth, if it ever exists |
| A `CandidateEdge` distinct from `CausalEdge` | `CONTEXT.md` §6 listed both; one type with a provenance class and a temporal verdict says the same thing, and two would need a promotion path that could drop invariants | If module 9 finds a field only a pre-scoring edge needs |

### Known limitations

| # | Limitation | Impact | Tracked as |
|---|---|---|---|
| 1 | An `INFERRED` interval can be mislabelled and nothing detects it | A guessed window with a plausible `source` passes every check; the two guards bound the damage but do not prevent the mislabelling | ADR-0021 negative consequences; `docs/contracts.md` §9 regret 2 |
| 2 | The `weighted_mean_v1` weights are asserted, not measured | Every ranking depends on six numbers no procedure derived | ADR-0009 negative consequences |
| 3 | Two serialization paths coexist | A module reaching for `model_dump_json` gets output that looks right and is not byte-stable; no check detects it | `docs/contracts.md` §9 |
| 4 | `temporally_unverifiable` is separate from the verdict | A consumer reading only the verdict conflates "could not separate" with "never placed" | `docs/contracts.md` §9 regret 4 |
| 5 | The contracts are frozen before any consumer exists | Frozen against anticipated rather than observed use; the first modules will find things that now cost an ADR | ADR-0025 negative consequences |
| 6 | Property tests are derandomized | A regression net, not a search — reruns stop finding new counterexamples | ADR-0024 negative consequences |
| 7 | **DEF-0002 — `CausalEdge.between` is the sanctioned constructor, not an enforceable one.** The artifact stores `source_event_id` and `target_event_id`, not the two intervals, so no validator can recompute the verdict. An `UNDETERMINED` verdict rewritten to `CERTAIN` — on the wire, or by a direct `CausalEdge(...)` call that never touched an `Event` — is accepted, and the edge may then carry `INFERRED`. A stored `VIOLATION` and a stored `OBSERVED` provenance *are* still refused, because those are banned values of a stored field. | The LAW-TIME guarantee is "enforced on the sanctioned path, re-checkable only in part". `causal_edge.py` and `docs/contracts.md` §6 both previously claimed the stronger version; both are corrected. Nothing in the repository exploits it — module 9 does not exist yet — so this is a live hole with no current instances. | `tests/law/test_law_time_survives_the_wire.py`; closing it is an ADR + `engine_version` bump |
| 8 | **LAW-EVIDENCE held by discipline until the audit.** Every confidence in the repository was already a `ConfidenceVector`, but no check made it one; the guarantee rested on nobody having written `confidence: float` yet. | Now enforced by `scripts/check_confidence_is_a_vector.py`. The residual is that the lint keys on the *name*: a judgement carried as `value: float` or inside a dict passes clean. It raises the cost of the mistake; the structural guarantee is still the field types on `Event` and `CausalEdge`. | `tests/law/test_law_confidence_lint.py` |

### Failure modes and their tests

| Failure mode | Test | Status |
|---|---|---|
| Same input yields two identifiers across processes | `test_the_identifier_survives_a_fresh_interpreter` | pass |
| A temporally undetermined edge is laundered into a CERTAIN one through the wire | `test_law_time_survives_the_wire.py::test_an_undetermined_verdict_rewritten_to_certain_is_accepted` | passing — **pins DEF-0002 as a known limit, not a guarantee** |
| An edge is constructed without any interval ever being consulted | `::test_direct_construction_never_evaluates_law_time` | passing — **pins DEF-0002** |
| A confidence enters the codebase as a bare float | `tests/law/test_law_confidence_lint.py::test_a_planted_violation_is_detected` | passing |
| The confidence lint fires on `EvidenceItem.strength` and gets disabled | `::test_evidence_item_strength_is_not_a_confidence` | passing |
| The confidence lint's self-test certifies a hole as correct behaviour | `::test_a_poisoned_must_not_fire_list_is_refused` | passing — **caught a real bug in the guard during the audit** |
| Two different payloads collide via an unescaped separator | `test_field_boundaries_are_unambiguous`, `test_leaf_escaping_is_injective` | pass |
| Overlapping intervals reported as precedence | `test_overlapping_intervals_never_precede_each_other` | pass |
| An inferred timestamp certifies an inference | `test_an_inferred_interval_never_yields_certain` | pass |
| An absent timestamp reported as a violation | `test_an_unverifiable_interval_yields_no_assertion_either_way` | pass |
| Provenance combination increases certainty | `test_the_result_is_never_stronger_than_any_input` | pass |
| A temporally invalid edge is constructed | `test_constructing_a_backwards_edge_raises` | pass |
| A rejected edge is reintroduced by deserialization | `test_a_violation_cannot_be_reintroduced_by_deserialization` | pass |
| An ambiguous or unverifiable edge is promoted to INFERRED | `test_an_undetermined_edge_may_never_be_promoted_to_inferred`, `test_an_unverifiable_edge_may_never_be_promoted_to_inferred` | pass |
| A law check is bypassed by an argument | `test_there_is_no_argument_that_bypasses_the_check` | pass |
| An observed fact is mutated | `test_attribute_assignment_is_refused`, `test_revising_an_observed_event_raises` | pass |
| An observed fact is relabelled then edited | `test_an_observed_fact_cannot_be_reclassified_by_revision` | pass |
| A revision reaches a state the constructor would refuse | `test_a_revision_is_revalidated_rather_than_copied_blindly` | pass |
| Serialization is not byte-stable | `test_serialization_is_byte_stable` | pass |
| An artifact is read without its envelope or across versions | `test_an_envelope_from_another_schema_version_is_refused`, `test_text_without_an_envelope_is_refused` | pass |
| Confidence is a bare float | `test_event_confidence_is_a_decomposition_not_a_float` | pass |
| An unknown aggregator silently falls back to the default | `test_an_unknown_aggregator_is_never_silently_replaced` | pass |

### Test coverage summary

| Kind | Count | Result |
|---|---|---|
| law | 126 | pass |
| unit (incl. property-based) | 106 | pass |
| determinism | 0 | NOT-YET-RUNNABLE (OQ-014) |
| integration / pipeline / graph / ontology / counterfactual / api / ui | 0 | not applicable — no module exists to integrate |
| **total** | **232** | **pass** |

Line coverage is reported, never the gate (`CONVENTIONS.md` §14). The gate is failure-mode
coverage, tabulated above.

### Validation evidence (Definition of Done)

| DoD item | Evidence |
|---|---|
| Interface matches contract | `docs/contracts.md` v1.0.0; ADR-0009, ADR-0021, ADR-0022, ADR-0023, ADR-0025 |
| Unit tests pass, ≥1 per failure mode | ```232 tests collected``` / ```232 passed``` |
| `make lint typecheck test` green | ```All checks passed!``` (ruff) · ```Success: no issues found in 57 source files``` (mypy) · ```232 passed``` (pytest) |
| Domain-independence lint passes | ```LAW-DOMAIN: clean across 54 file(s) in 6 package(s).``` |
| Layer boundaries hold | ```LAYER BOUNDARIES: clean across 57 file(s).``` |
| Five Laws stated identically | ```FIVE LAWS: byte-identical across CONTEXT.md §2 and CONVENTIONS.md §1.``` |
| Dependency policy holds | ```DEPENDENCY POLICY: clean; 14 pinned dependencies, all ADR-backed.``` |
| Governance record consistent | ```GOVERNANCE CONSISTENCY: clean; 10 question(s) closed by an existing ADR, 6 still open, supersessions acknowledged both ways.``` |
| Determinism gate | **NOT MET.** ```exit 2 NOT-YET-RUNNABLE``` — no orchestration pipeline exists to run twice (OQ-014). This is why the status is `built-unverified`. |

### OQ defaults used without ratification

None. OQ-005 and OQ-009 were the two defaults this work depended on, and both are now
ratified — by ADR-0009 and ADR-0025 respectively — rather than used and left open.

### Open questions raised by this module

None new. OQ-014 (the determinism gate cannot run) remains the blocker on moving this entry
and P0 from `built-unverified` to `done`, and it closes at the P1 exit rather than here.

---

## 00b. Ontology layer (extension seam, not a §36 module)

- **Status:** built-unverified
- **Phase:** P0 (Governance) — an extension seam, not one of the sixteen modules
- **Model:** Claude Opus 5
- **Dates:** started 2026-08-28 · gate passed —
- **Contract:** `OntologySpec` (`DomainPack` / `ResolvedPack`) — **frozen** at pack schema
  1.0.0 (ADR-0026); `ontology_hash` — **frozen** (ADR-0028); the loader API — draft
- **Versions in force:** `pack_schema_version=1.0.0`; `ontology_hash=ont:499e792c4dc0eac1`
  (`_base`), `ont:55b7f5c6adeeee2c` (`dataco`), `ont:11f8d5bddf4ed34c` (`hospital`);
  `dataset_version=unset`

### Built

- **The DSL** — `ontology_runtime/dsl.py`. Nine namespaces, every model
  `frozen=True, extra="forbid"`. Entity types with identifying keys, typed attributes
  carrying an explicit origin, and a lifecycle state machine; relationship types with
  cardinality and temporal validity; event types with pack-declared categories, participants
  by role, pre/postconditions as role/state assertions, and declared actionability; external
  event types declared and unpopulated; process definitions with variants and step
  annotations; measurement definitions as closed operator trees.
- **The published JSON Schema** — `ontology/_schema/ontology.schema.json`, **generated** from
  those models by `scripts/export_ontology_schema.py` and drift-checked by `--check`.
- **The loader** — `ontology_runtime/loader.py`, with `load_pack` (strict) and `inspect_pack`
  (returns every diagnostic without raising). Reads the pack and its `extends` chain,
  validates, resolves, and computes the hash.
- **Located diagnostics** — `yaml_source.py` builds a path→line index from PyYAML node marks;
  `locator.py` maps an identifier-addressed path back to a line in whichever document of the
  chain declares it. Every finding carries a file and a line, including operand-level
  addresses inside a measurement tree.
- **Structural validation** — `structural.py`, all `ERROR`: orphan references of every kind,
  duplicate identifiers (checked on the *authored* pack, before the merge that would hide
  them), well-formed state machines, unreachable states by BFS, terminal states with an exit,
  `CAUSES` as a relationship identifier, external event types referenced anywhere, derived/
  observed field-presence rules, unweighted confidence component names.
- **Semantic validation** — `semantic.py`, `WARNING` and `NOT_RUNNABLE`.
- **Inheritance** — `resolution.py`: merge by identifier, whole-entry replacement, explicit
  withdrawal, canonical sequencing, depth cap.
- **Versioning** — `hashing.py`: `digest(ONTOLOGY, to_canonical_json(resolved_pack))`.
- **Three packs** — `_base` (structure only), `dataco` (full reference domain + column
  manifest), `hospital` (unrelated domain, no dataset).
- **Onboarding procedure** — `docs/ontology.md` §4, a numbered checklist.

### Deliberately NOT built

| Omission | Why | Revisit when |
|---|---|---|
| `mapping.yaml`, `cost.yaml`, `labels.yaml` for any pack | Separate seams owned by modules 2 and 14 (`docs/architecture.md` §5.1). Folding them into the pack would collapse six seams into one and make a pack author responsible for four contracts at once. | Modules 2 and 14 |
| A rule pack for DataCo | Rule-pack shape is the Rule Engine's contract, not the ontology's. Its absence is *reported* by the loader as `ONT-N-RULE-COVERAGE`, not skipped. | The Rule Engine |
| `jsonschema` as a validator | Two validators for one contract, free to disagree, and no YAML line information. ADR-0026 option A. | Never, without an ADR reversing ADR-0026 |
| A `CARRIER` entity type in the DataCo pack | DataCo names a service level and never names a carrier. Declaring one would be an entity assumed into existence. | A dataset that carries carrier identity |
| `Order Updated`, `Customer Complaint`, `Route Changed` (prd.md §21) | No revision history, no service column, no route column. Declaring them with `ASSUMED` attributes would manufacture occurrences the source never recorded. | An external feed or a richer dataset |
| Any evaluation of a measurement tree | The ontology layer produces the tree; walking it is a consumer's job. Evaluating here would put arithmetic over domain attributes inside the seam that exists to hold no logic. | The module that reports metrics |

### Known limitations

| # | Limitation | Impact | Tracked as |
|---|---|---|---|
| 1 | A pack that validates cleanly can still be semantically wrong. Nothing checks that a transition matches reality, that a `derivation.basis` is sound, or that an actionability flag is true. | Silently wrong causality downstream — the failure ADR-0002 predicted. | **R-16** |
| 2 | Column traceability is traceability to a **manifest**, not to a file. The dataset is not in this repository. | A wrong column name in the manifest passes every check. | Manifest `verification: UNVERIFIED_AGAINST_LOCAL_FILE`; module 1 flips it |
| 3 | Rule coverage is unchecked because no rule pack exists. | An event type nothing can produce loads clean. | `ONT-N-RULE-COVERAGE`, emitted on every load |
| 4 | Domain independence is proved for the **schema**, not for engine output. | A reasoning package could still branch on a data value. | `docs/architecture.md` §1.5, §8; OQ-016 |
| 5 | Whole-entry replacement means an overlay restates a whole entry to change one field, and the two copies can drift with no check noticing. | Duplicated declarations in a long-lived overlay. | ADR-0027 negative consequences |
| 6 | The twenty DataCo default confidences are an editorial judgement with no ground truth, the same exposure `docs/contracts.md` §9 records for the aggregator weights. | Scores are only as good as an unvalidated guess. | ADR-0029 negative consequences |

### Failure modes and their tests

| Failure mode | Test | Status |
|---|---|---|
| Orphan reference (participant, category, entity type, event type, attribute, role, state, cost class, confidence component) | `test_invalid_packs.py::test_invalid_pack_reports_its_own_code_at_its_own_line` | pass |
| Unreachable state; terminal state with an exit; duplicate transition | same | pass |
| `CAUSES` declared as a relationship type | same | pass |
| External event type referenced by a process | same | pass |
| Duplicate identifier hidden by the inheritance merge | same | pass |
| Derived event with no basis; derived event claiming OBSERVED | `test_a_derived_event_without_a_basis_is_refused`, `test_no_derived_event_type_claims_observed_provenance` | pass |
| Undeclared key silently ignored | `test_an_undeclared_key_is_refused_rather_than_ignored` | pass |
| Missing `extends` target; withdrawal that removes nothing | `test_a_missing_base_pack_is_named`, `test_a_withdrawal_that_removes_nothing_is_refused` | pass |
| Empty or malformed YAML | `test_an_empty_document_is_refused`, `test_malformed_yaml_is_refused_rather_than_partially_parsed` | pass |
| Only the first error reported | `test_all_errors_are_reported_together_not_just_the_first` | pass |
| A diagnostic pointing at the wrong line | every located case re-reads the reported line and asserts the defect is on it | pass |
| Hash varying across processes | `test_hash_survives_a_fresh_interpreter` (subprocess) | pass |
| Hash moving on a reformat, or not moving on a semantic change | `test_comments_indentation_and_key_sequence_do_not_move_the_hash`, `test_any_semantic_change_moves_the_hash` | pass |
| Round trip losing identity | `test_pack_round_trips_to_an_identical_model`, `test_round_tripping_preserves_the_hash` | pass |
| A tampered wire payload reintroducing a refused state | `test_deserialization_reruns_the_invariants` | pass |
| Published schema drifting from the models | `test_schema_export_is_current.py`; `scripts/export_ontology_schema.py --check` | pass |
| A source column with no manifest entry | `test_every_source_column_attribute_names_a_manifest_column` | pass |
| A derived event quietly promoted to observed | `test_the_derived_share_is_declared_not_accidental` (pins the ratio) | pass |
| The DSL being secretly logistics-shaped | `tests/ontology/test_pack_is_not_domain_shaped.py` | pass |
| Domain vocabulary in the loader itself | `test_the_loader_names_no_domain_concept`; `scripts/check_domain_independence.py` (scope widened by ADR-0026) | pass |
| A check that could not run reading as one that passed | `test_every_pack_reports_the_check_it_could_not_run` | pass |

### Test coverage summary

| Kind | Count | Result |
|---|---|---|
| unit (`tests/unit/ontology_runtime/`) | 86 | pass |
| ontology (`tests/ontology/`) | 7 | pass |
| whole suite | 384 | pass |

### Validation evidence (Definition of Done)

| DoD item | Evidence |
|---|---|
| Interface matches contract | ADR-0026 (DSL), ADR-0027 (path + inheritance), ADR-0028 (hash), ADR-0029 (derived events); `docs/ontology.md` |
| Unit tests pass, ≥1 per failure mode | see below |
| `make lint typecheck test` green | see below |
| Deterministic | `test_hash_survives_a_fresh_interpreter`, `test_serializing_twice_yields_identical_bytes` — but the **pipeline** determinism gate is still NOT-YET-RUNNABLE (OQ-014), which is why this entry is `built-unverified` |
| Docs updated in the same commit | `CONTEXT.md` §0/§3/§6/§7/§9/§11, `DECISIONS.md`, `docs/architecture.md` §5/§8, `docs/contracts.md` 1.1.0, `docs/ontology.md`, `GLOSSARY.md`, `docs/README.md`, every `ontology/` README |

```
$ backend/.venv/bin/ruff check backend scripts
All checks passed!

$ backend/.venv/bin/ruff format --check backend scripts
149 files already formatted

$ cd backend && ../backend/.venv/bin/mypy
Success: no issues found in 68 source files

$ cd backend && ../backend/.venv/bin/pytest --no-cov
384 passed in 50.71s
```

```
$ make laws
--- self-tests: every law check must be observed to reject, not just to pass
self-test passed: 3 defect shapes rejected, identical copies accepted.
self-test passed: 24 vocabulary forms fire, 17 non-domain words stay clean, and no claimed
false positive hides a banned stem.
self-test passed: 12 bare-float shapes fire, 12 legitimate lines stay clean, and no
claimed false positive hides a violation.
self-test passed: 9 forbidden edges rejected (F1-F9 all covered), 7 permitted edges accepted.
self-test passed: 5 policy violations rejected, 3 clean inputs accepted.
self-test passed: 7 inconsistency shapes rejected, 1 consistent record accepted.
SELF-TEST: export_ontology_schema observed to reject a stale schema and accept a current one.
--- scans
FIVE LAWS: byte-identical across CONTEXT.md §2 and CONVENTIONS.md §1.
LAW-DOMAIN: clean across 66 file(s) in 7 package(s).
LAW-EVIDENCE: clean across 67 file(s); confidence is a vector everywhere.
LAYER BOUNDARIES: clean across 67 file(s).
DEPENDENCY POLICY: clean; 14 pinned dependencies, all ADR-backed.
GOVERNANCE CONSISTENCY: clean; 10 question(s) closed by an existing ADR, 6 still open,
supersessions acknowledged both ways.
ONTOLOGY SCHEMA: ontology/_schema/ontology.schema.json matches the DSL models.
```

```
$ cd backend && PYTHONHASHSEED=0 ../backend/.venv/bin/python -c "..."
_base      ont:499e792c4dc0eac1  errors=0 warnings=0 not_runnable=1
dataco     ont:55b7f5c6adeeee2c  errors=0 warnings=7 not_runnable=1
hospital   ont:11f8d5bddf4ed34c  errors=0 warnings=2 not_runnable=1
```

The seven DataCo warnings are all `ONT-W-NO-LIFECYCLE` on reference entity types, and are
correct: a customer, product, category, department, site, shipping mode and market region
genuinely carry structure and never change state in this dataset. The one `NOT_RUNNABLE` on
every pack is rule coverage, and stays until a rule pack exists.

### Defect found and fixed in neighbouring code

`scripts/check_layers.py` rejected `ontology_runtime` importing **itself** under forbidden
edge F3. `docs/architecture.md` §1.1 says a package may import its own layer, so the rule was
wrong — but it was unobservable while `ontology_runtime` was an empty package, and it fired
for the first time the moment that package acquired internal imports. Fixed with a
`source_package != target_package` clause and a `MUST_ACCEPT` self-test case, so the false
positive cannot return silently. Same class as DEF-0001: a check whose behaviour on a case
that never arose was never observed.

### OQ defaults used without ratification

None. OQ-013's ordinal cost treatment is *anticipated* by the `cost_classes` vocabulary but
not consumed — `cost.yaml` is module 14's seam and remains unwritten, so no default is in
use here.

### Open questions raised by this module

None new. OQ-014 loses one of its two blockers — `ontology_hash` now exists, so `run_id` is
computable — and stays open on the pipeline. OQ-016 is half-covered; the residual it names
is unchanged.

---

## 00c. Ontology acceptance-checklist hardening (ADR-0030)

- **Status:** done · **Phase:** P0 · **Date:** 2026-08-28 (ADR-0030, tightened same day by ADR-0031)
- **Scope:** no new capability. Two properties the ontology layer already had, moved from
  "true today" to "enforced in CI". Nothing in `causalog/` changed.

### The checklist, item by item

| # | Item | Verdict | Evidence |
|---|---|---|---|
| 1 | The hospital pack loads and validates with **zero** changes to any non-ontology file | **Now true for every pack.** It was true for `hospital` only because someone had registered it in three literal tuples (`docs/ontology.md` §4 step 9 said to). Discovery is now derived from the pack directory. | `tests/ontology_packs.discover_packs()`; `test_pack_is_not_domain_shaped.py`; probe below |
| 2 | Every DataCo event type traces to a column, or is explicitly DERIVED/ASSUMED with a stated basis | **Already covered.** `SOURCE_COLUMN` attributes must name a manifest column; `DERIVED` must state a basis; `ASSUMED` must state an assumption; the 1-observed/20-derived ratio is pinned so a later edit cannot quietly promote one. | `test_dataco_pack_traceability.py`, 9 tests |
| 3 | An invalid pack fails with a precise, actionable message | **Already covered, and stronger than asked.** 15 fixtures assert the diagnostic **code and the reported line**, by reading the line back out of the file; every error is reported in one pass, not the first. | `test_invalid_packs.py`, 20 fixtures under `tests/fixtures/ontology/invalid/` |
| 4 | Delay/cost/impact formulas declared in the ontology rather than in engine code | **Was true by construction, guarded by nothing.** The declaration half is structural (`MeasurementExpression`, closed operator set, no expression strings). The engine half is now a four-rule lint that follows the value, not just the name. | `scripts/check_metrics_are_declared.py` (ADR-0030, ADR-0031) |
| 5 | The ontology hash changes on a state-machine edit and is stable on cosmetic reformatting | **Already covered, in both directions**, including a fresh-interpreter subprocess run so a digest depending on hash randomization cannot pass. | `test_ontology_hash_stability.py`, 13 tests |

Items 2, 3 and 5 needed no work. Items 1 and 4 were the same failure shape as **DEF-0001**:
a property that holds, with nothing that would notice the day it stops.

### Built

| Artifact | What it is |
|---|---|
| `backend/tests/ontology_packs.py` | `discover_packs()` — globs `ontology/packs/*/ontology.yaml`, sorted; **raises** on an empty result, because zero parameterised tests report as a pass |
| `scripts/check_metrics_are_declared.py` | AST lint refusing metric arithmetic in the five reasoning packages, with intra-scope taint tracking and a hard-coded-threshold rule (ADR-0031); `--self-test`; `.lawmetric-allowlist`; exit 2 while the engine is scaffold |
| `.lawmetric-allowlist` | Empty but for its header, which is the healthy state |
| `CONVENTIONS.md` §6a | The lint's written specification, including what it deliberately does not catch |

### Evidence

```
$ cd backend && ../backend/.venv/bin/pytest tests/unit/ontology_runtime/test_packs_load.py -q --collect-only -v | grep probe
tests/unit/ontology_runtime/test_packs_load.py::test_shipped_pack_loads_without_errors[_probe]
tests/unit/ontology_runtime/test_packs_load.py::test_every_pack_reports_the_check_it_could_not_run[_probe]
tests/unit/ontology_runtime/test_packs_load.py::test_loading_twice_yields_the_same_hash[_probe]
```

A throwaway pack copied into `ontology/packs/_probe/` was picked up by the parameterised run
with **no test file edited**, and was then deleted. That is item 1 demonstrated rather than
asserted.

```
$ python3 scripts/check_metrics_are_declared.py --self-test
self-test passed: 12 metric-arithmetic shapes fire, 12 legitimate lines stay clean, and no
claimed false positive hides a computed metric.

$ python3 scripts/check_metrics_are_declared.py       # with a planted violation in graph_engine/
backend/src/causalog/graph_engine/_probe.py:6: ADR-0026 violation -- an arithmetic
expression assigned to 'actual_delay', a domain metric.
    actual_delay = arrival - promised
ADR-0026: 1 metric(s) computed in engine code across 14 file(s). BUILD FAILED.
$ echo $?
1

$ python3 scripts/check_metrics_are_declared.py       # probe removed
ADR-0026 metric declaration: NOT-YET-RUNNABLE.
  Every reasoning package (...) is scaffold only -- 13 file(s), none of which defines
  anything, because 0 of the 16 modules are built. [...]
$ echo $?
2
```

The lint has been **observed to reject**, which is the standard ADR-0019 sets and the one
DEF-0001 was created by ignoring.

```
$ backend/.venv/bin/ruff check backend scripts
All checks passed!

$ backend/.venv/bin/ruff format --check backend scripts
151 files already formatted

$ cd backend && ../backend/.venv/bin/mypy
Success: no issues found in 68 source files

$ cd backend && PYTHONHASHSEED=0 ../backend/.venv/bin/pytest --no-cov
391 passed in 32.22s

$ make laws
[7 self-tests passed, 7 scans clean, 1 NOT-YET-RUNNABLE reported loudly]
```

### Known limitations

Both limitations ADR-0030 recorded were closed the same day by **ADR-0031**, which
supersedes it. What remains is narrower and is listed below.

| # | Limitation | Impact | Tracked as |
|---|---|---|---|
| 1 | ~~The metric lint is name-based~~ — **closed by ADR-0031.** Rule 3 follows the *value*: a name bound from a metric-named attribute or string key is tainted, taint survives rebinding, and arithmetic on it fires however it is named. | — | ADR-0031 |
| 2 | ~~Comparison is not matched~~ — **closed by ADR-0031.** Rule 4 refuses a metric compared against a numeric literal. Comparison against a *variable* stays unmatched on purpose, and that limit is now a pinned test. | — | ADR-0031 |
| 3 | The scan cannot run: every reasoning package is scaffold. The matcher is proved by its self-test and by planted cases, not by a real scan. | Exit 2, reported loudly. Not a green tick. | Blocking at the P2 exit |
| 4 | `COUNT` and `RATIO` are `MeasurementKind` members excluded from the stem list. | A metric genuinely named `count` or `ratio` is invisible to the lint. | ADR-0030 Decision, argued rather than silent |
| 5 | Taint is a **source-order approximation**, not a dataflow analysis. A value assigned after it is read — a loop rebinding at the bottom, computing at the top — is missed, as is a metric passed through a function call (`helper(raw)`). | Laundering is harder, not impossible. | ADR-0031 negative consequences |
| 6 | Arithmetic on two genuinely unnamed values from unnamed sources (`v = a - b`, both parameters) is still clean. | No lint reachable from the standard library changes this; the answer if it matters is option C — ban arithmetic outright — revisited at the P2 exit. | ADR-0031 options table |

### Obligations created

Delete the exit-2 tolerance from `make laws` and from the `metrics-are-declared` CI job at
the P2 exit. `test_the_scan_reports_not_runnable_while_the_engine_is_unbuilt` fails the day
the first reasoning module lands, so the removal is forced rather than remembered.

At the same P2 exit, revisit ADR-0031 option C — forbidding arithmetic in the reasoning
packages outright, except inside a sanctioned tree-walking evaluator. If taint tracking is
by then producing more allowlist entries than findings, option C is the honest replacement
and the moment to take it is before the modules multiply.

### Follow-up, same day (ADR-0031)

Both limitations recorded above as 1 and 2 were closed rather than left standing. Evidence:

```
$ python3 scripts/check_metrics_are_declared.py     # planted probe in causal_engine/
_probe.py:7:  ADR-0026 violation -- arithmetic '-' on a value read from 'shipping_delay'
              and carried in 'raw', a domain metric.
    value = raw - baseline
_probe.py:13: ADR-0026 violation -- the hard-coded threshold 48 compared against 'delay',
              a domain metric.
    return delay > 48
ADR-0026: 2 metric(s) computed in engine code across 14 file(s). BUILD FAILED.

$ python3 scripts/check_metrics_are_declared.py --self-test
self-test passed: 20 metric-arithmetic shapes fire, 18 legitimate lines stay clean, and no
claimed false positive hides a computed metric.

$ cd backend && PYTHONHASHSEED=0 ../backend/.venv/bin/pytest --no-cov
397 passed in 33.52s
```

Neither rule was written and trusted: both were observed to reject the file above before the
probe was deleted. The threshold finding carries its own remedy text — a threshold belongs in
the pack beside the metric it bounds — because telling an author to "walk the tree instead"
would be the wrong instruction for that finding.

One thing worth recording because it is the check working on itself: the DEF-0001 guard
rejected a `MUST_NOT_FIRE` entry written while implementing ADR-0031. The entry was
multi-line, and the guard is line-blind by design. The fix was to keep the guard strict and
move that case to pytest — not to relax the guard to accommodate the table.

### Open questions raised by this module

None new. OQ-016's residual is narrowed, not closed: two classes of value-level domain
leakage — a metric recomputed in engine code, and a threshold on one hard-coded there — are
now refused, including where the metric reaches the arithmetic under an unrelated name.
Branching on a data value still is not.

---

## 00d. Persistence layer (infrastructure seam, not a §36 module)

- **Status:** built · **Phase:** P0 · **Date:** 2026-08-29
- **ADRs:** ADR-0032 (bi-temporality), ADR-0033 (migrations), ADR-0034 (the §47 projection);
  DEF-0003 fixed
- **Scope:** PostgreSQL as the system of record, Neo4j as the derived projection, Redis as
  the cache, the repository ports and their adapters, the rebuild and drift commands.
  `persistence/` carries no layer rank — it is a set of driven adapters (ADR-0014), so this
  does **not** move the module ledger. Zero of the sixteen §36 modules are built.

### What exists now that did not before

| Area | Before | After |
|---|---|---|
| PostgreSQL schema | 2 tables (`run`, `audit_log`) | 15 paired migrations; 26 tables; every table and column carries a `COMMENT ON` |
| Migrations | forward-only, applied by the container init directory, no ledger | forward + reverse, applied by a recorded runner with a checksum rule; `make migrate` / `make migrate-down` / `make migrate-status` |
| `scripts/rebuild_graph.py` | exit 2 NOT-YET-RUNNABLE (no adapter existed) | implements the six steps of `docs/architecture.md` §3.3 |
| Drift detection | none | `make verify-projection RUN_ID=…`, with `--self-test` |
| Repository ports | 4 read-only Protocols | write side, bi-temporal reads, run-scoped edge reads, plus `BulkFactWriter` and `SchemaMigrator` |
| Adapters | 4 empty scaffold packages | `postgres`, `neo4j`, `redis`, and `memory` fakes |
| Tests | 397 | 525 (520 fast + 5 marked `slow`) — 485 at the end of the build, +40 from the 2026-08-29 verification pass that found DEF-0004, DEF-0005 and DEF-0006 |

### Failure modes, and the test for each

`CONVENTIONS.md` §14: the gate is failure-mode coverage, not a percentage.

| Failure mode | Test |
|---|---|
| An event is UPDATEd or DELETEd | `tests/law/test_facts_are_append_only.py` — 9 tables × 2 operations, each asserting a **raise** |
| A rejected write reports success (DEF-0003) | `test_the_refusal_is_raised_and_not_swallowed` |
| An inferred artifact exists with no run | `test_an_inferred_artifact_cannot_exist_without_a_run` — `NOT NULL`, not application code |
| A causal edge claims OBSERVED provenance | `test_a_causal_edge_may_not_carry_observed_provenance` |
| A VIOLATION verdict is stored | `test_a_violating_temporal_verdict_has_no_admissible_row` |
| An UNDETERMINED edge is laundered to INFERRED | `test_an_undetermined_edge_may_not_claim_inferred_provenance` |
| A re-inference overwrites a past belief | `tests/integration/test_bitemporal_as_of.py` — 11 cases across both adapters |
| A closed system period is reopened | `test_reopening_a_closed_period_is_refused_by_the_database` |
| A migration does not reverse cleanly | `tests/integration/test_migrations_up_down.py` — checks the **system catalogue**, because `CREATE … IF NOT EXISTS` hides residue |
| An applied migration is edited | `test_editing_an_applied_migration_is_a_hard_error` |
| A rebuild is not idempotent | `tests/graph/test_rebuild_is_idempotent.py` |
| Dropping a run touches observed structure | `test_dropping_a_run_leaves_observed_structure_untouched` |
| The projection hash depends on process state | `tests/determinism/test_projection_hash_is_stable.py` — runs in a **fresh interpreter** |
| A read returns insertion order | `tests/unit/persistence/test_repository_contract.py` — seeds in reverse deliberately |
| The fake drifts from the real adapter | the same file, parameterized over **both** |
| The fast path enforces less than the row path | `test_the_bulk_path_stores_exactly_what_the_row_path_stores` |
| A relationship carries CAUSES | `test_a_causal_relationship_type_is_refused` |
| Facts span two dataset versions | `test_facts_spanning_two_dataset_versions_are_refused` |

### Three defects found while building this, recorded rather than smoothed over

**DEF-0003 — `audit_log` swallowed rejected writes.** Migration 0002 enforced append-only
with `CREATE RULE ... DO INSTEAD NOTHING`, which reports **success** for a write it
discarded. A rejected write indistinguishable from an accepted one, in the one table whose
whole purpose is being trustworthy. This is the DEF-0001 shape — a guard that cannot be
observed to fire reads exactly like a guard that passed. Migration 0014 replaces it with the
raising trigger every other fact table now uses; the reversal restores the defect verbatim,
because a reversal that "fixed" what it reverses would leave the database in a state no
migration describes.

**The F4 self-import hole — the second instance of the F3 one.** `scripts/check_layers.py`
rejected `persistence` importing `persistence`. ADR-0026 fixed exactly this in F3, where it
had stayed invisible until `ontology_runtime` held code; F4 had it too and stayed invisible
for the same reason — `persistence` was four empty scaffold packages, so the rule had nothing
to fire on. *A rule that cannot fire has not been observed to work.* Both now carry a
`MUST_ACCEPT` self-test case, side by side, with a comment saying it is the same hole twice.

**The bulk path dropped the LAW-EVIDENCE hook.** The first loader wrote
`confidence_component` and silently skipped `confidence_component_evidence` — the table
`CONVENTIONS.md` §8 requires so a confidence number can be reconstructed from an audit record
alone. The law therefore held on the row path and stopped holding on the path used for real
datasets, which is precisely backwards. Found by a test written *before* the fix, comparing
both paths table by table; that test is now the structural guard, and R-18 records the class.

Two lints also fired on this work and were **fixed rather than allowlisted**, following the
2026-08-23 precedent: LAW-DOMAIN caught the word `order` in a comment in
`core/ports/persistence.py` (reworded to "sequence"), and LAW-EVIDENCE caught
`_insert_confidence_vector` returning an `int` — the int is a `BIGSERIAL` surrogate and not a
confidence, so the method was renamed to `_store_decomposition`.

### The prd.md §55 load budget: MEASURED, AND NOT MET

| | |
|---|---|
| Reference shape | 180 519 events, 86 522 entities, 180 519 citations — measured from the real file, not assumed |
| Persistence path | **~33–41 s** against a **30 s** budget |
| Artifact construction | ~9 s (modules 1–4, not built; the fixture stands in) |
| Configuration measured | local PostgreSQL 14, default server settings |
| Configuration targeted | PostgreSQL 16 in the compose stack — **MEASURED 2026-08-29; see below** |

**The deployment configuration is now measured, and it is worse, not better.** A container
runtime became reachable on 2026-08-29 and the benchmark was run against the compose stack
that `docs/prd.md` §55 actually targets. The gap the previous entry left open is closed, and
what it reveals is that the earlier host measurement was the optimistic one.

| Configuration | Persistence path | Budget | Runs |
|---|---|---|---|
| compose PostgreSQL 16, `mem_limit: 512m` — **the deployment target** | **93.84 s** and **136.40 s** | 30 s | 2 |
| host PostgreSQL 14, unconstrained, machine under load | **52.26 s** | 30 s | 1 |
| host PostgreSQL 14, unconstrained, quiet machine (previous entry) | ~33–41 s | 30 s | — |

Two things follow, and neither is a tuning detail:

1. **The target configuration misses the budget by 3–4.5×, not by the ~10–35 % the host
   measurement implied.** Every number in the previous entry was taken on the configuration
   the product does not ship. R-17 was opened to be revisited "on the first measurement
   against the deployment configuration"; this is that measurement, and it makes the miss
   substantially larger rather than closing it.

2. **The memory-overcommit hypothesis was tested and is WRONG.** `connection.py` issues
   `SET LOCAL work_mem = '256MB'` and `SET LOCAL maintenance_work_mem = '512MB'` for the
   load transaction, inside a container with `mem_limit: 512m` and 160 MB already committed
   to `shared_buffers` — 768 MB of working memory requested inside roughly 350 MB of
   headroom. That looked like the obvious cause of the gap and it is recorded here because
   it was measured rather than argued:

   | `work_mem` / `maintenance_work_mem` | Elapsed |
   |---|---|
   | 256 MB / 512 MB (as shipped) | **81.60 s** |
   | 32 MB / 64 MB | 93.81 s |
   | 16 MB / 32 MB | 100.32 s |

   Lowering the settings made the load monotonically **slower**, not faster. The shipped
   values are the best of the three even inside the container, so the overcommit is not
   what costs the 2–2.6×. The settings are left exactly as they are.

   The cause is therefore still unknown. What the numbers rule out is the memory
   configuration; what they do not touch is CPU and I/O — the container shares a Docker VM
   that had six unrelated containers resident throughout, and every container measurement in
   this section was taken under that load. The next thing to test is a quiet host, not
   another setting.

The container runs span 81.60 s to 136.40 s across five measurements — a 67 % spread — so the
number is unstable and no single measurement of it should be trusted. The host run was also
taken on a machine with six unrelated containers resident, which is why it reads 52 s against
the earlier 33–41 s.

**`LOAD_BUDGET_SECONDS` is still 30 and the assertion is still left failing**, for the reason
the previous entry gives: raising it converts a known miss into an unknown one. R-17 stays
open and its scope grows.

Where the time goes, measured per phase and then per statement:

| Phase | Time | Share |
|---|---|---|
| `COPY` into staging | 2.4 s | 8 % |
| Promotion (`INSERT … SELECT`) | 27.5 s | 90 % |
| `ANALYZE`, staging setup/teardown | 0.3 s | 1 % |

Within the promotion, the `event` insert dominates (~7–10 s), then `event_evidence` (4.2 s),
`evidence_record` (2.5 s), `event_changed_attribute` (2.5 s), `confidence_component` (2.2 s),
`event_metadata` (2.1 s).

What was tried, with numbers:

- `COPY … FROM STDIN` instead of per-row `INSERT` — this is the whole of the speed-up.
- `FORMAT BINARY` — **reverted.** Binary carries no type information, so psycopg guesses
  from the first row and sends a four-byte integer into a `BIGINT`; PostgreSQL reports
  `insufficient data left in message`. Pinning types for seven statements and forty columns
  would put a second copy of the schema in the loader, free to drift from the migrations.
- One transaction, `UNLOGGED` staging, `synchronous_commit = off`.
- `work_mem = 256MB` and `maintenance_work_mem = 512MB`, `SET LOCAL` — measured 26.4 s → 24.7 s
  on a 20k-entity shape, about 7 %.
- `ORDER BY` on the promotions **kept**: removing it made the `event` insert *slower*
  (9.8 s → 11.2 s), because sorted insertion into indexes is cheaper.
- A GiST index on `event.occurred_over` — **removed.** ~3 s, about a tenth of the budget,
  and no built module issues the query it serves. The column stays.

**The assertion is left failing.** `LOAD_BUDGET_SECONDS` is a product requirement, and
raising it until the test goes green would convert a known miss into an unknown one. Tracked
as **R-17**, open, to be revisited on the first measurement against the deployment
configuration.

### The DataCo dataset: manifest verified against the real file

The dataset arrived during this work and was profiled. `ontology/packs/dataco/columns.manifest.yaml`
declares 53 columns and states `verification: UNVERIFIED_AGAINST_LOCAL_FILE`. Checked against
`DataCoSupplyChainDataset.csv` (sha256 `994b3c8d…6b9bc0d`, 180 519 data rows): **all 53
columns present, in the same order, none extra, none missing.**

The `verification` field is deliberately **not** flipped here. The manifest's own note, and
`CONTEXT.md` §0's rule about not modifying files outside the module you were told to build,
put that with module 1 when it writes `datasets/dataco.pin.json`. What is recorded is the
evidence that it will pass.

Four findings from the profile, all of which bear on modules 1–4:

1. **Timestamps carry clock time, not just dates.** `order date (DateOrders)` is
   `M/D/YYYY HH:MM` and 180 401 of 180 519 rows have a non-midnight time. This materially
   softens the premise of risk **R-14** (`UNDETERMINED` dominance), which was argued from
   "a day-granularity dataset". The derived event types remain day-granularity, because they
   are computed from `Days for shipping (real)`, so both precisions will coexist — R-14 is
   narrowed, not retired, and only a measurement from module 9 can retire it.
2. **The file is latin-1, not UTF-8.** It carries Spanish place names (`Rajastán`); reading
   it as UTF-8 raises at byte 1707. Module 1's `SourceReader` must declare the encoding.
3. **`Product Description` is empty in 100 % of rows**, and `Order Zipcode` in 86 %. Neither
   is referenced by `ontology.yaml`, so nothing is broken — but a mapping written later
   against a column list rather than against the data would map a column that is never
   populated.
4. **Shape:** 65 752 orders, 20 652 customers, 118 products, 180 519 order items; order dates
   span 2015-01-01 to 2018-01-31. `tests/integration/test_bulk_load_budget.py` re-reads the
   file and fails if any of these drift, so the benchmark's fixture cannot quietly stop
   resembling what it stands in for.

### Known gaps

- **DEF-0005 (FIXED 2026-08-29, migration 0016) — `TRUNCATE` was not refused. The append-only guarantee has a hole
  the size of the whole schema.** Migration 0004's `causalog_refuse_mutation` is attached
  `BEFORE UPDATE OR DELETE`. `TRUNCATE` is neither, so it bypasses the trigger entirely.
  Observed directly in `psql` against a migrated database holding one event: `UPDATE event
  SET provenance_class = 'INFERRED'` raised, `UPDATE … WHERE event_id = …` raised, `DELETE
  FROM event` raised — and then `TRUNCATE event CASCADE` **succeeded**, taking `event` and
  cascading into `event_entity`, `event_changed_attribute`, `event_metadata`,
  `event_evidence`, `state`, `state_transition`, `causal_edge`, `causal_edge_co_cause`,
  `causal_edge_evidence` and `causal_edge_fired_rule`. Row count after: 0. All 22
  non-internal triggers in the schema are `tgtype` 27 or 25 — `ROW|BEFORE|DELETE|UPDATE`
  and `ROW|AFTER|DELETE|UPDATE`. **Not one carries the `TRUNCATE` bit.** The word `TRUNCATE`
  does not appear anywhere in `deployment/sql/`, `backend/src`, `backend/tests` or
  `scripts/`, so it is neither guarded nor tested.

  **DEF-0006 was found while fixing this one**, by listing tables against triggers instead
  of reading the migrations: seven fact tables — `entity_evidence`,
  `confidence_component_evidence`, `causal_edge_evidence`, `causal_edge_co_cause`,
  `causal_edge_fired_rule`, `entity_lifecycle_state`, `entity_lifecycle_transition` — had no
  append-only trigger at all. `DELETE FROM confidence_component_evidence` succeeded and
  removed a row; the structurally identical `DELETE FROM event_evidence` raised. That is the
  LAW-EVIDENCE hook table of `CONVENTIONS.md` §8. Also fixed by migration 0016, which
  attaches the seven missing row guards. The class is closed as well as the instances:
  `test_every_fact_table_is_guarded` reads `pg_trigger` and fails on any table in `public`
  that is neither guarded nor listed in `MUTABLE_BY_DESIGN` with a written reason, so the
  eighth cannot arrive unnoticed.

  This is squarely inside the threat model migration 0004 states for itself: *"the reasoning
  modules are not the only thing that can hold a connection, and a `psql` session is one
  keystroke away from every fact in the system."* The migration also names the grant-based
  first line of defence and then says why the trigger must exist anyway — *"a superuser
  connection, a migration, and a psql session all bypass a grant"* — and `TRUNCATE` is
  exactly the verb that reaches the fact tables down that path. It is also the DEF-0001 /
  DEF-0003 shape once more: `tests/law/test_facts_are_append_only.py` enumerates 9 tables ×
  2 operations and observes each one raise, so the suite is green and reads as proof that
  history cannot be destroyed. It tests the two verbs that are guarded and never tries the
  third.

  **FIXED by migration 0016.** `causalog_refuse_truncate()` is attached `BEFORE TRUNCATE
  FOR EACH STATEMENT` to all 30 tables that assert immutability, driven by a catalogue query
  rather than a written-out list so it cannot disagree with the row-level guards.
  `test_truncate_raises` covers the full matrix and
  `test_truncating_a_parent_cannot_cascade_into_a_guarded_child` covers the cascade path
  that did the actual damage. Both were observed to FAIL before the migration (32 failures)
  and pass after it.
- ~~**The Neo4j adapter has not been run against a live Neo4j.**~~ **RESOLVED 2026-08-29.**
  A container runtime became reachable and the adapter was run against
  `neo4j:5.26.0-community`. `tests/graph`, `tests/determinism`,
  `tests/integration/test_bitemporal_as_of.py` and `test_migrations_up_down.py` all pass
  against the live services (29 tests, no skips). The rebuild was then exercised for real:
  the Neo4j volume was **destroyed** (`docker volume rm causalog_neo4j_data`, verified 0
  nodes / 0 edges / 0 constraints) and rebuilt from PostgreSQL alone. Byte-identical:
  content hash `9de5cd6cc97622fa`, version `gpv:dcc140c18e22af70`, 6 nodes / 2 edges, both
  builds. The registry superseded `_0000` and made `_0001` live; `check_projection_drift.py`
  reports the projection matches the facts. `drop_run` removed exactly the 1 inferred
  `CAUSES` edge and left all 6 observed nodes and 3 observed edges untouched.
- **DEF-0004 (FIXED 2026-08-29) — the Neo4j schema required Enterprise Edition; the compose
  file ships Community.** The very first live rebuild aborted:
  `Neo.DatabaseError.Schema.ConstraintCreationFailed — Property existence constraint
  requires Neo4j Enterprise Edition`. `persistence/neo4j/schema.py` declares node existence
  constraints (`event_type_exists`, `event_provenance_exists`, `recommendation_run_exists`,
  `intervention_run_exists`) plus the generated per-relationship `*_run_exists`,
  `*_provenance_exists` and `*_dataset_exists` constraints, and every one of them is
  Enterprise-only. `docker-compose.yml` pins `neo4j:5.26.0-community`. The six uniqueness
  constraints are fine; the existence constraints cannot be created at all, and
  `_apply_schema` runs every statement unconditionally, so `make rebuild-graph` fails on
  step 2 against the stack this repository ships. **The results recorded above were obtained
  by dropping the existence constraints for the run**, which means they verify the rebuild's
  determinism and run-isolation, and do NOT verify the constraints. This matters beyond the
  crash: `_inferred_edge_constraints` justifies itself with "a `CAUSES` edge with no run
  would be an inference with nothing to scope it -- the one thing ADR-0013 makes structurally
  impossible in PostgreSQL, and it must be equally impossible here or the projection becomes
  the way around it." On Community that guarantee did not exist.

  **FIXED 2026-08-29, without changing the image.** The edition is asked of the server
  (`dbms.components()`), and `schema_statements(existence_constraints=...)` applies the
  Enterprise family only where it can be created. On Community the same invariants are
  checked by `existence_invariant_queries()` after the projection is written and **before
  the swap**, so a violating projection never serves a reader. `make rebuild-graph` now
  completes against the shipped `neo4j:5.26.0-community` and produces content hash
  `9de5cd6cc97622fa` — identical to the hash obtained earlier with the constraints dropped
  by hand, so the repair changed the enforcement and not the projection.

  Three things are deliberately NOT claimed. First, the two paths are **not** equally
  strong: a constraint makes a violation unrepresentable, a check detects one that already
  happened, once per build rather than at every write. `ProjectionReport.enforcement`
  records which was in force and `rebuild_graph.py` prints it, so a report can never be
  mistaken for the stronger guarantee. Second, the Community check is observed to REJECT and
  not merely to pass (ADR-0019): `test_the_community_check_is_observed_to_reject` plants a
  `CAUSES` edge with no `run_id` and requires the refusal. Third, the choice of image is
  still an open decision — this makes Community correct and honest, it does not argue
  against Enterprise.

  One invariant that **no edition ever enforced** was found while writing the checks and is
  now covered: nothing verified that an OBSERVED edge carries no `run_id`. `drop_run` is
  safe only because observed edges have none to match, so a projection bug there would have
  let `drop_run` delete observed structure with every constraint green.
  `test_an_observed_edge_carrying_a_run_id_is_refused` closes it.
- ~~**The traceback is raw.**~~ **FIXED 2026-08-29.** The Enterprise failure surfaced as an
  unhandled `neo4j.exceptions.DatabaseError` stack trace rather than the `REBUILD FAILED: …`
  message, so the script's published exit-code contract (0 rebuilt / 1 a check failed / 2
  stack not reachable) was honoured only for `CausaLogError`. `rebuild_graph.py` now catches
  `ServiceUnavailable` as exit 2 and `Neo4jError` as exit 1, and prints which enforcement
  path the build used.
- ~~**`cypher-shell` cannot be run inside the Neo4j container.**~~ **FIXED 2026-08-29.**
  Running it starts a second JVM inside `mem_limit: 1g` and the container is OOM-killed
  (`exit 137`) — observed while querying a container that was healthy a second earlier. The
  compose **healthcheck ran `cypher-shell` every 10 s**, so the check could kill the service
  it was checking. Replaced with an HTTP probe against `:7474`, which costs a few megabytes;
  Bolt readiness is covered by the first real query the application makes. Verified: the
  container comes up healthy on the new probe.
- **One index has no justifying query, and nothing enforces that they must.** Audited
  2026-08-29 against a migrated database: of the 27 indexes the migrations declare
  explicitly, 26 carry a `COMMENT ON INDEX` naming the query that justifies them, several
  citing the `prd.md` §55 path they sit on. The exception is **`audit_log_run_idx`**
  (migration 0002), which predates the convention — 0014 commented the two indexes it added
  to the same table and left 0002's uncommented. **Fixed in migration 0016**, which gives it
  the justifying query it always had ("everything this run did, in sequence"). A further 7 indexes are constraint-backing
  (`*_key`, auto-created by `UNIQUE`); a constraint is arguably its own justification, but
  no rule says so. The real gap is that the convention is a habit, not a check: no script in
  `scripts/` verifies that a new index arrives with a comment, so the next one added without
  one will not be caught. This is the shape `make laws` exists to prevent, applied to a
  convention that does not yet have a law.
- **PostgreSQL 14 was used for every measurement**; 16 is the pinned target. **No longer
  true as of 2026-08-29** — see the load-budget section above, where 16 is measured and is
  the slower configuration.
- `Recommendation` and `Intervention` graph labels are constrained and have no writer —
  their modules do not exist (OQ-017).

---

## 01a. Modules 1 and 2 — Data Adapter and Schema Mapper (2026-08-30)

**Status: `built-unverified`.** `done` additionally requires the `CONVENTIONS.md` §3
Validation Gate checklist executed and recorded; that checklist does not yet exist for these
modules, so the status is the honest one.

### Gate output, pasted

```
$ backend/.venv/bin/ruff check backend scripts
All checks passed!

$ backend/.venv/bin/ruff format --check backend scripts
201 files already formatted

$ make laws                        (self-tests then scans)
self-test passed: 24 vocabulary forms fire, 17 non-domain words stay clean, no claimed
  false positive hides a banned stem, and all 9 in-scope packages really contribute files.
FIVE LAWS: byte-identical across CONTEXT.md §2 and CONVENTIONS.md §1.
LAW-DOMAIN: clean across 89 file(s) in 9 package(s).
LAW-EVIDENCE: clean across 95 file(s); confidence is a vector everywhere.
LAYER BOUNDARIES: clean across 95 file(s).
GOVERNANCE CONSISTENCY: clean; 10 question(s) closed by an existing ADR, 9 still open.
ONTOLOGY SCHEMA: ontology/_schema/ontology.schema.json matches the DSL models.
ADR-0026 metric declaration: NOT-YET-RUNNABLE (exit 2, as designed while L4+ is scaffold;
  its message said "0 of the 16 modules are built", which this work made false -- corrected)

$ cd backend && ../backend/.venv/bin/mypy
Success: no issues found in 95 source files

$ cd backend && PYTHONHASHSEED=0 ../backend/.venv/bin/pytest
513 passed, 87 skipped in 36.80s

    600 collected. The 87 skips are the container-dependent integration and graph tests --
    no container runtime is reachable on this machine, the same limitation R-17 records.
    NONE of the tests added by this work is among them.

    THIS WORK ADDS 75, all of which run here:
        53  tests/unit/ingestion/          (module 1 and module 2)
        19  tests/law/                     (two new files)
         3  tests/determinism/
    plus the strengthened manifest test and the widened check_domain_independence
    self-test, which replace assertions rather than adding collected tests.
```

**A counting discrepancy that predates this work, recorded rather than absorbed.** 600
collected minus the 75 above leaves **525** pre-existing tests, while the last figure in
`CONTEXT.md`'s changelog is **485**. So roughly forty tests were added at some point without
the recorded count being updated. This work did not add them and cannot account for them; the
number is stated here so the next session sees a discrepancy rather than inheriting a total
that silently absorbed it.

### The import, pasted

```
$ make import DATASET=dataco
[1/6] loading ontology pack  ontology/packs/dataco/ontology.yaml
      ontology_hash=ont:55b7f5c6adeeee2c  version=1.0.0
[2/6] probing source         datasets/raw/DataCoSupplyChainDataset.csv
      95,729,629 bytes  sha256=994b3c8d24049cc46bf20e8161fedece9a9b95376cc0dc929921d76cf6b9bc0d
      encoding='cp1252' rejected=['utf-8', 'utf-8-sig']  delimiter=',' sniffed=True  columns=53
[3/6] loading mapping        (a PROPOSED_UNCONFIRMED document is refused here)
      mapping_hash=map:7acd9e24866745fb  version=1.0.0
      coverage: 0 error(s), 0 warning(s), 19 not-runnable
      dataset_version=dataco@994b3c8d24049cc4+map7acd9e24866745fb
[4/6] importing              two streaming passes over the source
      rows read=180,519 clean=180,519 quarantined=0 reconciles=True
[5/6] column manifest        VERIFIED: all 53 declared columns are present in the file header
[6/6] report                 docs/reports/dataco/dataco@994b3c8d24049cc4+map7acd9e24866745fb
      report_sha256=cbe68d3b84dc678fca1479ae02f97948c1ef2f2b21c59cc1514145c9877c914a
      findings: 0 ERROR, 26 WARNING, 4 NOT_RUNNABLE

real    1m32s          (89.1s user; see the measurement table for the spread)
```

**Determinism confirmed by hand as well as by test.** Across four separate imports on this
machine the report digest was `cbe68d3b84dc678fca1479ae02f97948c1ef2f2b21c59cc1514145c9877c914a`
every time, with a byte-identical `data-quality.json` and a byte-identical `records.jsonl`
(228,736,650 bytes) — while the wall clock varied by more than 50%, which is exactly the
separation `CONVENTIONS.md` §11 requires: performance measurements vary, outputs do not.

### Failure modes, and the test for each

`CONVENTIONS.md` §14: the gate is failure-mode coverage, not a percentage.

| Failure mode | Test |
|---|---|
| Source not valid UTF-8, silently mis-decoded | `test_the_probe_detects_the_single_byte_encoding_rather_than_assuming_it` |
| Encoding changes only in the file's tail | `test_the_probe_reads_both_ends_of_the_file` — writes exactly that file |
| Delimiter unsniffable and silently defaulted | rule `DQ-SRC-DIALECT-UNSNIFFED`, reported not assumed |
| Row field count disagrees with the header | `test_field_count_positive` / `_negative`; short rows padded, long rows kept |
| Required bound column blank | `test_blank_required_positive` / `_negative` |
| Required value unparseable | `test_an_unparseable_required_value_raises_rather_than_returning_a_sentinel` |
| Timestamp missing | `test_a_blank_becomes_the_unbounded_unknown_interval_and_never_a_guess` |
| Timestamp unparseable under the declared format | `test_an_unreadable_instant_is_refused_rather_than_reparsed_by_a_second_format` |
| **Timestamp imputed** | `tests/law/test_cleaning_never_imputes_time.py` — 9 cases, enumerating the registry rather than sampling it |
| Delivery-before-order class (declared precedence inverted) | `test_precedence_negative` |
| Two instants temporally inseparable | `test_precedence_equal_is_reported_separately_from_an_inversion` |
| Orphan foreign key | `test_orphan_key_negative` |
| Forward reference wrongly called an orphan | `test_a_forward_reference_is_not_an_orphan` |
| Duplicate identity with conflicting attributes | `test_duplicate_identity_negative` / `_positive` |
| Value with no ontology binding | `test_unmapped_value_negative`, `test_an_unmapped_value_is_never_defaulted` |
| State outside the declared lifecycle | rules `DQ-CON-UNKNOWN-STATE`, `DQ-CON-UNREACHABLE-STATE` |
| Cardinality silently truncated | rule `DQ-DST-CARDINALITY-INEXACT` at `NOT_RUNNABLE` |
| A row lost between input and output | `test_every_planted_defect_row_is_quarantined_and_none_is_lost`; reconciliation asserted in `import_dataset` |
| Missing required ontology concept | `test_a_missing_required_concept_is_an_error_that_names_what_it_breaks` |
| Unlisted source column | `test_an_unlisted_column_is_a_hard_error` |
| A machine proposal reaching production | `test_an_unconfirmed_proposal_is_refused_not_warned_about` |
| Coverage assessed with no header, reported as clean | `test_omitting_the_header_reports_not_runnable_rather_than_passing` |
| Report differs between two runs | `tests/determinism/test_data_quality_report_is_stable.py` |
| Batch size changing the answer | `test_a_different_batch_size_does_not_change_the_answer` |
| Memory growing with the row count | `test_peak_memory_does_not_grow_with_the_row_count` |
| Raw file modified by reading it | `test_the_raw_file_is_not_modified_by_reading_it` |
| A row escaping above L2 | `tests/law/test_no_row_escapes_ingestion.py` |
| Reader not actually satisfying the port | `test_the_concrete_reader_satisfies_the_port` |

The golden fixture is 200 rows sliced deterministically from the head of the real file, kept
in `cp1252`, plus **7 hand-planted defect rows** — one per rule needing a negative case
against a realistically shaped row. `test_each_planted_defect_fires_its_rule` asserts every
one is caught; a planted defect nothing catches is a rule that is off.

### Four defects found while building this, three by the checks themselves

1. **The derivation audit measured its own conclusion.** It compared the two temporal
   columns' **bound** intervals. `shipping date` is bound at DAY, so its minutes were
   already discarded, and it reported **0.07%** agreement where the truth is **94.61%** — a
   measurement whose result was produced by the binding it existed to justify. The headline
   compounded it by asserting "in the great majority of rows" regardless of what came back.
   Fixed: `parse_source_instant` reads the SOURCE instant, and the headline is gated on the
   measured rate with a `DQ-TMP-DERIVATION-UNCONFIRMED` finding below 50%.
2. **`DQ-REF-DUPLICATE-IDENTITY` was registered and unreachable.** `IdentityIndex.conflicts()`
   computed the answer and the adapter never emitted it. Found by
   `test_each_planted_defect_fires_its_rule`, which is the DEF-0001 shape caught by a test
   written before the code was trusted.
3. **`read_pin` could not read what `write_pin` wrote.** `write_pin` emits canonical JSON with
   a schema envelope; `read_pin` called `model_validate` on the raw document and was refused
   by its own `extra="forbid"`. Found by the manifest test, which reads the pin through the
   real reader rather than through `json.load` precisely so a shape change cannot pass.
4. **Module 1 imported a concrete reader.** `scripts/check_layers.py` rejected it under F4.
   The fix put `SourceDescription` on the core port, so the adapter reports *how* a source had
   to be read without importing the thing that read it. The seam working, not being worked
   around.

Also, and worth recording separately: pointing the LAW-DOMAIN scan at `ingestion` for the
first time immediately produced **21 violations in the freshly written modules 1 and 2** —
`ordering`/`order`/`ordered` in prose, and DataCo column names used as docstring examples in
the suggester. All 21 were **reworded**; `.lawdomain-allowlist` is still empty, which is the
healthy state. And `scripts/check_confidence_is_a_vector.py` refused a
`confidence: float` field on the mapping suggester, which is why that field is called
`score` — LAW-EVIDENCE reserves the word for a decomposable vector.

### Measurements taken, including the unflattering ones

| | |
|---|---|
| Full import, 180,519 rows, 95.7 MB | **92 s – 149 s** wall clock across four runs on this machine (89–107 s user), against the contested `prd.md` §55 30 s budget — **OQ-019**. The range is reported rather than the best figure. Two passes, deliberately: exact quantiles and a correct orphan-key check need them, and the alternatives are sampling (forbidden, `CONVENTIONS.md` §11) or calling every forward reference an orphan. **The budget is missed and this says so**, in the same spirit as R-17: raising a budget until a measurement fits it converts a known miss into an unknown one. |
| Profiling pass 1, before optimisation | 368 s. A shape gate before the `strptime` loop plus a per-column classification memo took it to **24 s**, a 15× improvement, with no change to any reported value — the golden report is the evidence for that. |
| Rows quarantined from the reference dataset | **0 of 180,519.** The data satisfies every declared rule; the 26 warnings are about what the data *is*, not about rows being wrong. |
| Distinct-value cap hit | 4 columns. Reported at `NOT_RUNNABLE` as a floor, not a count. |
| `Product Description` | blank in **180,519 of 180,519** rows. |
| `Order Zipcode` | blank in **155,679 of 180,519** rows (86.24%) — dropped, with that number as the reason. |

### Known gaps in these two modules

- **The Validation Gate checklist does not exist** for modules 1 and 2, which is why the
  status is `built-unverified` and not `done`.
- **Nothing is persisted.** No PostgreSQL write; module 4 does not exist, so there are no
  `Event` values, and the report says so under "What this report did not check".
- **Semantic correctness of the mapping is unchecked and uncheckable here** (risk R-16). A
  mapping that loads cleanly can be bound to the wrong concepts and would produce silently
  wrong causality rather than an error.
- **The suggester's precision is unmeasured.** No labelled ground truth for
  column-to-concept mappings exists. That is why the proposal cannot load.
- **An UNDECLARED derivation is not detected.** `temporal_derivation_checks` measures what a
  mapping author already suspects; nothing searches for the pattern (R-20).
- **The encoding probe reads two ends, not the middle.** A file whose encoding changes in its
  interior would still fool it. Disclosed rather than fixed: decoding the whole file twice
  would double every import to catch a case nobody has observed.
- **`IdentityIndex` is bounded by identity cardinality, not by rows.** A dataset whose
  distinct identities exceed memory would need a spilling index. The count is in the profile,
  so this will be measured before it is a problem rather than guessed at.

---

## 02a. Modules 3 and 4 — Entity Extractor and Event Generator (2026-08-30)

**Status: `built-unverified` for both.** `done` additionally requires the `CONVENTIONS.md` §3
Validation Gate checklist executed and recorded; that checklist does not yet exist for these
modules, so the status is the honest one.

They share this section because they were built in one commit and cannot be measured apart:
module 4 resolves an event's participants against the entities module 3 mints, and module 3's
reconciliation report is only interesting once something consumes the entities.

### What had to be decided before any code could be written

`ontology.yaml` states every derived event type's `derivation.basis` in **prose** — *"Implied
by an Order Status of PROCESSING, COMPLETE or CLOSED"*. A human can audit that and nothing
can execute it. The pack was otherwise complete and machine-readable, so the only thing
standing between module 4 and being ontology-driven was that nothing said, executably, which
records witness which occurrence. Three ADRs resolve it, and the third is a correction:

- **ADR-0039** puts the emission condition in `mapping.yaml` as a closed operator tree, not
  in the frozen pack and not as an expression string. It also supplies `MappedRecordBatch`,
  which `docs/architecture.md` §2 named as module 2's output and module 2 shipped without.
- **ADR-0040** makes `RECORD_GAP` the default for a process step no field supports: the gap
  is reported and no event is fabricated. `EMIT_GAP_MARKER` is implemented and selectable.
- **ADR-0041** corrects `docs/architecture.md` §2, which stated module 4's invariant as
  `provenance_class = OBSERVED`. That is false against ADR-0029 and implementing it would
  have put nineteen fabricated observations into the system of record with real columns
  standing behind them.

### Gate output, pasted

```
$ make laws
FIVE LAWS: byte-identical across CONTEXT.md §2 and CONVENTIONS.md §1.
LAW-DOMAIN: clean across 102 file(s) in 9 package(s).
LAW-EVIDENCE: clean across 108 file(s); confidence is a vector everywhere.
LAYER BOUNDARIES: clean across 108 file(s).
DEPENDENCY POLICY: clean; 14 pinned dependencies, all ADR-backed.
GOVERNANCE CONSISTENCY: clean; 10 question(s) closed by an existing ADR, 11 still open,
                        supersessions acknowledged both ways.
migration pairs: every forward migration has its exact reverse.
ADR-0026 metric declaration: NOT-YET-RUNNABLE.        (exit 2, tolerated; see §00c)
ONTOLOGY SCHEMA: ontology/_schema/ontology.schema.json matches the DSL models.

$ ruff check backend scripts && ruff format --check backend scripts
All checks passed!
226 files already formatted

$ cd backend && mypy
Success: no issues found in 108 source files

$ cd backend && pytest -m "not slow"
633 passed, 85 skipped, 6 deselected in 57.91s
```

**LAW-DOMAIN fired on the first draft, as it did on modules 1 and 2, and every violation was
REWORDED rather than allowlisted.** Fourteen occurrences across five files, all in prose:
"order-level", "line items", "ordering", "deliverable". `.lawdomain-allowlist` is unchanged.
The rewording is not cosmetic — a docstring that explains a mechanism in one domain's
vocabulary teaches the next reader that the mechanism is about that domain.

### The ground truth, and the two defects it caught before anything else ran

`backend/tests/fixtures/dataco/expansion.py` holds twenty hand-built records and the
expansion they must produce: **146 events across nineteen event types**, stated as literal
per-order and per-line sets, hand-derived by reading each type's basis prose against each
record's status columns, plus independently hand-summed totals. It was written before the
generator produced anything, which is the only way an expectation is evidence rather than a
transcript — a generated golden agrees with whatever bug was present when it was recorded.

It found two things immediately, and both were real:

1. **The fixture itself was wrong.** Its first draft gave each line of one order a different
   order-date minute, which made every line a separate occurrence and would have silently
   defeated the deduplication the fixture exists to check. The real source carries one order
   instant per order; the fixture now does too, with a comment saying why.
2. **Deduplication was load-bearing and previously unmeasured.** Order-level occurrences on a
   line-item source fan out per line unless records witnessing one occurrence are merged.
   Without it the twenty-record fixture reports sixteen purchases where there are fifteen,
   and the reference dataset would report every order-level count inflated by its average
   line count.

The identifiers are checked against the RECIPE, not against a recorded value:
`test_every_identifier_equals_the_address_recipe_recomputed` rebuilds every `event_id` from
`CONVENTIONS.md` §9 using the fields the other tests have just asserted.

### Failure modes, and the test for each

`CONVENTIONS.md` §14: the gate is failure-mode coverage, not a percentage.

| Failure mode | Test |
|---|---|
| A heuristic mints an `OBSERVED` event | `test_every_event_construction_reads_its_provenance_from_the_pack` (AST), `test_no_derived_event_type_produces_an_observed_event` |
| …and the check for it never rejects anything | `test_the_ast_rule_is_observed_to_reject_a_planted_construction`, `test_a_pack_declaring_a_derived_type_observed_is_refused` |
| A row, mapped record or record view escapes L3 | `test_no_package_above_l3_names_a_record_of_any_kind` |
| A source column name rides out on an artifact rather than in a signature | `test_no_emitted_artifact_carries_a_source_column_name` |
| An emitted interval claims precision the source did not have | `test_no_emitted_interval_claims_exact_precision`, `test_no_policy_can_produce_exact_precision` |
| An absent instant is narrowed to a guessed window | `test_an_unknown_interval_is_never_narrowed`, `test_bounded_between_falls_back_to_unknown_when_a_bound_is_unknown` |
| A derived bound is indistinguishable from a typed-in one | `test_a_derived_bound_is_inferred_and_never_assumed` |
| A narrowed window certifies a causal edge | `test_an_inferred_interval_can_never_certify_a_precedence` |
| Two records witnessing one occurrence become two events | `test_the_two_lines_of_one_order_produce_one_placement_between_them` |
| Two participants merged on a similarity heuristic | `test_a_composite_key_missing_any_part_yields_no_entity_and_is_counted`, `test_identity_is_the_content_address_and_repeats_merge` |
| A disagreement is silently resolved | `test_a_conflict_is_reported_under_every_policy_that_tolerates_one`, `test_reject_refuses_a_disagreement_outright` |
| Enriching an entity renames it | `test_the_entity_address_excludes_attributes_so_enrichment_cannot_rename` |
| A numeric comparison silently compares text (`'9' > '10'`) | `test_numeric_comparison_is_arithmetic_and_never_lexicographic` |
| A rule that CANNOT fire looks like one that never matched | `test_an_absent_operand_makes_a_comparison_false_and_counts_it` |
| A typo'd symbol makes a rule silently never fire | `MAP-E-EMISSION-LITERAL-UNMAPPED` at mapping load |
| A missing step is fabricated as an event | `test_record_gap_emits_no_event_for_a_step_no_field_supports` |
| The active policy is invisible to a consumer | `test_the_policy_is_stamped_into_the_report` |
| Batch size changes the output | `test_batching_partitions_the_input_and_never_changes_it` |
| A report carries something ambient | `test_the_rendered_reports_are_free_of_anything_ambient` |
| Adding an event type requires a code change | `test_the_pack_directory_is_where_a_new_type_is_added` |
| A step the measurement cannot see is reported as missing | `test_a_step_the_anchor_cannot_see_is_reported_unmeasured_not_missing`, `test_the_rendered_report_says_a_step_was_not_measured` |
| Two identity bindings, or two emission rules, make output depend on document sequence | `test_two_identity_bindings_for_one_entity_type_are_refused`, `test_two_emission_rules_for_one_event_type_are_refused` |

### A defect this work found in its own report, and the shape of it

The 20,000-record slice reported `ITEM_PICKED` and `ITEM_PACKED` as **100% missing,
systematically** — while 19,222 events of each had just been emitted. The cause is not a
counting bug: process coverage is measured per anchor entity, and both event types declare
participants (`ORDER_ITEM`, `FULFILLMENT_SITE`) that include no participant of the anchor's
type, so no event of either can be connected to an instance. The measurement was blind and
reported its blindness as a finding.

That is the worst answer available here. "100% of instances lack this step" is confident and
quantified, and it was wrong about a step that fired on nearly every instance — the same
shape as DEF-0001 (a check that could not fire reading as a check that passed) and as the
derivation audit in DEF-0004 (a measurement whose result was created by the binding it
existed to justify). Third instance of the class.

`ProcessStepCoverage` now carries `attributable`. A step the anchor cannot see reports
**NOT MEASURED**, both counts are zero and say so, `systematically_missing` is false for it,
and the rendered report prints `n/a` rather than a rate it never counted. Two tests pin it,
one of which asserts the step in question actually produced events — so a future change that
made the case vacuous would fail rather than pass quietly. Connecting those steps to an
instance needs the structural relationship module 7 builds; until then the report says the
step is unmeasured, which is true, instead of missing, which was not.

### Three findings about the PACK, which these modules exist to be able to make

None of these is a defect in modules 3 or 4. They are what the first consumer of a pack
finds out, and finding them is the argument for building the reports before building the
graph. All three are R-16 realised — a pack that validates cleanly and is wrong about the
world — and all three are recorded as OQ-021 and OQ-022 rather than repaired here, because
each is a claim about the domain and belongs to whoever owns the pack.

1. **`order_profit` and `order_benefit` are line figures wearing order names.** Both are
   declared attributes of `ORDER`; both come from columns that vary between the lines of one
   order in 4,773 of the first 12,203 orders. The consequence is not cosmetic:
   `order_profit` is a required attribute of `ORDER_PLACED`, so it reaches
   `changed_attributes`, so one placement becomes several events — **19,997 `ORDER_PLACED`
   events for 12,203 orders.** Any count of placements is inflated by ~64%.
2. **`MARKET_REGION` is keyed at region granularity and given address-level attributes.**
   23 entities carry 46,575 disagreements between them, because a region contains many
   cities and every record says a different one.
3. **Three of the pack's declared bases are not separable in this source** (OQ-021):
   `PAYMENT_FAILED`, `ORDER_HELD` and `PAYMENT_REVIEW_OPENED` are all satisfied by
   `ON_HOLD`, and no column records which state an order arrived from.

The first two were found by the Reconciliation Report doing exactly its job, and the first
was only visible **because occurrence deduplication works**: without it every placement would
have been one event per line and the disagreement would have left no trace at all.

The example cap in that report was fixed on the strength of this: a flat cap of 100 filled
with `MARKET_REGION`'s 46,575 conflicts and showed none of `ORDER`'s 15,590, so the report
was exact in its arithmetic and unrepresentative in the part a reader looks at. Examples are
now capped **per `(entity_type, attribute)`**, so every distinct kind of disagreement appears.

### The seam proof, run rather than asserted

`docs/architecture.md` §5.3 promises the reasoning-code diff for a new domain is zero lines.
For module 4 that promise is now a test:
`tests/ontology/test_a_new_event_type_needs_no_code.py` copies the pack, adds one event type
and one emission rule — every identifier it needs (category, severity class, anchor entity
type, the attribute the condition reads) **discovered from the pack under test**, so the test
says nothing about any domain — reruns, and gets new events. It then **hashes every `.py`
file in the distribution before and after and asserts the digest is unchanged.**

### Measurements, including the unflattering ones

`tests/integration/test_full_expansion_budget.py` (marked `slow`) runs the whole reference
clean layer through both modules and prints both readings of OQ-018 — source records, and the
events they expand into — because nobody has ruled on which one `prd.md` §55's budget counts,
and the two differ by nearly an order of magnitude. Reported as measured; **not tuned.**

| Records | Entities | Events | Factor | Extraction | Generation | Peak RSS |
|---:|---:|---:|---:|---:|---:|---:|
| 20,000 | 46,040 | 158,175 | 7.91× | 6.0–10.6 s | 15.3–53.7 s | 875 MB |
| 60,000 | 114,989 | 458,310 | 7.64× | 34.9–106.9 s | 96.7–226.9 s | 907 MB |

**The counts are exact and reproduce; the wall clock on this host does not, and the ranges
say so instead of averaging them away.** Every count above is byte-identical across repeated
runs — that is what the determinism test asserts and what content addressing guarantees. The
timings are two runs of the same code on an 8 GB machine carrying ~10 GB of swap from
unrelated processes, and they differ by up to 3×. A range with both ends is the honest form;
a mean would imply a precision the measurement does not have. This is R-17's situation
repeated one layer up: the number that matters is measured on a host that is not the target,
and pretending otherwise would convert a known unknown into an unknown one.

**Peak memory is flat, and that is the load-bearing result.** 875 MB at 20,000 records and
907 MB at 60,000 — a 3× increase in input for a 4% increase in peak. The dominant term is a
fixed baseline, not the data, which is what makes single-process expansion of the whole file
a question of time rather than of feasibility.

**The expansion factor is ~7.9×, where OQ-018 estimated 21×.** ADR-0029 declares twenty event
types against one observed one, which is where 21× came from; the measured figure is lower
because eight of the nineteen witnessable types are conditional on a status most records do
not carry, and because occurrences are deduplicated. So the two readings §55 might mean are
**180,519** and **≈1.43 million** — still a passing budget and a badly failing one. The ruling
OQ-018 asks for is still needed, but it can now be made against numbers instead of an
estimate, which was the point of measuring both.

**Deduplication is doing real work, and one number proves it.** `records/event` is exactly
1.00 for every line-scoped event type and rises to 1.95 for order-scoped ones. Without it a
line-item source would report every order-level occurrence once per line — and the pack
defect in `order_profit` above shows what that looks like when it partially fails: 19,997
placements for 12,203 orders, a 64% inflation that is invisible unless something counts both.

**Events are STREAMED, and that is a correctness constraint rather than an optimisation.**
The first implementation collected them, and the reference expansion drove this machine into
swap: still running after fifty minutes with six minutes of CPU behind it. Holding the log is
affordable exactly where a report about it is least needed. `EventGenerator.stream` yields
each event as it is materialised and folds every figure the quality report states as the
events go past, so peak memory is a function of the number of distinct OCCURRENCES and their
citations — which pass A must hold to address an event at all — and never of the events
themselves. `EventGenerator.generate` still collects, for the fixtures and for any dataset
small enough that holding it is free, and its docstring states what that costs at scale.

**The remaining memory floor is the occurrence index, and it is not removable by tuning.**
`event_id` addresses `evidence_record_ids(sorted)` (`CONVENTIONS.md` §9), so an event's
identity is unknowable until every record has been read; pass A therefore holds one entry per
occurrence. If that ceiling is ever reached the answer is an external sort in pass A, **not**
a cap on citations — capping evidence would trade a memory bound for a LAW-EVIDENCE hole,
which is the wrong direction to trade in.

### Known gaps in these two modules

- **Attribute history cannot be persisted.** `entity_attribute` is keyed
  `(entity_id, attribute_name)` and holds one value per attribute, so the versions module 3
  computes exist only for the life of the run. Opened as OQ-020.
- **Three of the pack's declared bases are not separable in this source.** `PAYMENT_FAILED`,
  `ORDER_HELD` and `PAYMENT_REVIEW_OPENED` are all satisfied by `ON_HOLD` and no column
  records which state an order arrived from, so all three fire and occurrences on those
  records are over-counted. `ORDER_RELEASED` cannot be witnessed at all. Opened as OQ-021 and
  reported by every run rather than resolved by a judgement in a data file.
- **Two pack attributes are declared at the wrong granularity** (OQ-022), which inflates the
  placement count by ~64%. Reported, not repaired: it is a claim about the domain.
- **A step whose event type names no participant of the process anchor cannot be attributed
  to an instance**, so its coverage is reported as NOT MEASURED rather than as a rate.
  Resolving it needs the structural relationship module 7 builds.
- **Nothing compares an emission rule to the prose basis it transcribes.** That is R-16 with
  a second surface, and the mitigation is the same as the first: the two are in different
  files so a human can read them against each other, and coverage reports every derived
  emission at `NOT_RUNNABLE` rather than clean.
- **Neither module persists anything.** Forbidden edge F4 admits only `orchestration`, and no
  orchestration pipeline exists (OQ-014). Both runs end at artifacts and two reports.
- **The wall clock is measured on a host that is not the target** — 8 GB, heavily swapped.
  The counts reproduce exactly; the timings are reported as ranges and are not a budget claim.
- **The Validation Gate checklist for these modules does not exist**, which is why the status
  is `built-unverified` and not `done`.

---

## 03a. Modules 5 and 6 — Timeline Builder and State Engine (2026-08-31)

**Status: `built-unverified` for both.** `done` additionally requires the `CONVENTIONS.md` §3
Validation Gate checklist executed and recorded; that checklist does not yet exist for these
modules, so the status is the honest one.

They share this section because they were built in one commit and cannot be measured apart:
module 6 replays the `Timeline` values module 5 produces, and there is nothing to replay
until module 5 exists.

### What had to be decided before any code could be written

`Timeline` did not exist as a type — `docs/architecture.md` names modules 5 and 6's
input/output shapes precisely, but the interface registry carried `Timeline` `draft` with no
fields. A second, unplanned problem surfaced immediately on the first `make lint` run: both
modules' natural design read the ontology pack directly, and `scripts/check_layers.py`
forbade it outright — `graph_engine` is not in `ONTOLOGY_CONSUMERS` (F3), a rule that had
never fired in practice before because `graph_engine` had held no code. Three ADRs and one
new package resolve this:

- **ADR-0042** lands `Timeline`/`TimelineEntry`/`TimelineView`/`TimelineEntryKind` in `core`
  (the `Event`/`State`/`Transition` precedent) and adds `IdentifierPrefix.TIMELINE`
  additively.
- **ADR-0043** records the timeline adjacency tie-break rule (`event_id`, marked `ASSUMED`
  whenever `verdict` is not `CERTAIN`) and the matching State Engine convention: a state's
  `held_over` boundary widens and is marked `ASSUMED` rather than pinned with unwarranted
  confidence when the transitions bounding it tie.
- **`causalog.extraction.ontology_adapters`** (new module, in `extraction` — one of the three
  packages F3 permits) is the one place `ResolvedPack` is read for modules 5/6; it returns
  plain `causalog.core.ontology_view` shapes (`ProcessDefinitionView`, `LifecycleView`,
  `DurationMeasurementView`) that `graph_engine` consumes without ever importing
  `ontology_runtime`. `graph_engine` itself gained the first `MeasurementExpression`
  evaluator in the codebase (`state_engine/measurement.py`), scoped to `DURATION`/`DELAY`
  measurements only, walking the mirrored tree.

### LAW-DOMAIN fired on the first draft, again

Fourteen-plus occurrences of the `order` stem across `core/types/timeline.py` and every
`timeline_builder` file — not the DataCo entity, but the ordinary English sense ("the events'
order"), which is exactly the false positive `.lawdomain-allowlist`'s own header predicts and
tells the author to reword rather than allowlist ("Write 'sequence', 'sequenced', or
'sorted' instead"). Every occurrence was reworded (`sequence_provenance` replaces
`ordering_provenance` as the field name; `sequence` replaces `order` throughout prose and
identifiers); two literal domain words (`warehouse`, `carrier`) in an early draft of
`join.py`'s docstring, used as illustrative examples, were replaced with domain-neutral
language. `.lawdomain-allowlist` is unchanged.

A second, structural finding: `backend/tests/law/test_enforcement_scripts_prove_themselves.py`
carried a test that was DESIGNED to fail the day a reasoning module landed
(`test_the_scan_reports_not_runnable_while_the_engine_is_unbuilt`, docstring: "expected to
fail... which is the point"). It failed as documented. Replaced with
`test_the_scan_is_runnable_now_that_a_reasoning_module_exists`, asserting exit 0 and a
`"clean across"` banner; `.github/workflows/ci.yml`'s `metrics-are-declared` job lost its
`|| test $? -eq 2` tolerance in the same change, per the P2-exit instruction the removed
comment left.

### Gate output, pasted

```
$ python scripts/check_layers.py
LAYER BOUNDARIES: clean across 122 file(s).

$ python scripts/check_domain_independence.py
LAW-DOMAIN: clean across 116 file(s) in 9 package(s).

$ python scripts/check_metrics_are_declared.py
ADR-0026: clean across 24 file(s) in 5 package(s); every metric is declared, not computed.

$ python scripts/check_dependency_policy.py
DEPENDENCY POLICY: clean; 14 pinned dependencies, all ADR-backed.

$ python scripts/check_governance_consistency.py
GOVERNANCE CONSISTENCY: clean; 10 question(s) closed by an existing ADR, 12 still open,
                        supersessions acknowledged both ways.

$ python scripts/check_law_copies.py
FIVE LAWS: byte-identical across CONTEXT.md §2 and CONVENTIONS.md §1.

$ cd backend && ruff check . && ruff format --check .
All checks passed!

$ cd backend && mypy
Success: no issues found in 122 source files

$ cd backend && pytest tests/unit tests/law tests/determinism -q
[unit/law/determinism suites pass; integration/pipeline/graph/counterfactual/api suites
need a running PostgreSQL and were not exercised by this change -- modules 5/6 write
nothing to persistence (F4 admits only orchestration, which does not exist yet, OQ-014)]
```

### Test coverage against the task's four requirements

- **Golden timelines** (`tests/unit/graph_engine/timeline_builder/test_build.py`, 5 cases):
  happy path, a never-witnessed gap, a witnessable-elsewhere gap, an out-of-sequence pair
  (flagged, never resorted), and a tied pair (deterministic tie-break, marked `ASSUMED`).
- **State replay determinism**
  (`tests/determinism/test_timeline_and_state_are_stable.py`): two runs over one input,
  including a tied sub-case, produce byte-identical `Timeline`/`State`/`Transition`/report
  artifacts (models and rendered markdown).
- **Illegal transition detection**
  (`tests/unit/graph_engine/state_engine/test_replay.py`): a crafted repeated-trigger case
  is rejected as a named finding, the entity's replay stops at the offending event, and a
  second, legal entity in the same run is unaffected.
- **As-of correctness across transition boundaries**
  (`tests/unit/graph_engine/state_engine/test_as_of.py`): queries just before, just after,
  and (separately) exactly on a boundary are checked, and
  `core.derivation.current_state`'s overlap-contradiction raise is proven still intact
  against a hand-built genuine contradiction.
- **Uncertain-timestamp handling**
  (`tests/unit/graph_engine/state_engine/test_uncertain_boundaries.py`,
  `tests/law/test_timeline_never_overclaims_certainty.py`): a tied boundary widens the
  state and is flagged `ASSUMED`, never pinned to a fabricated instant; a parametrised law
  test re-derives `verdict` for synthetic interval pairs and asserts `sequence_provenance`
  never claims more than the data supports.

### What this build did NOT do

- **No real-DataCo-pipeline test.** Every test here uses the synthetic, domain-neutral
  fixtures `tests/fixtures/facts.py` already established (extended with a `timeline()`
  builder that reuses the real tie-break code rather than reimplementing it) — there is no
  golden fixture set from a "Prompt 06" anywhere in the repository (checked and confirmed
  absent before this build started), and extending `tests/extraction_harness.py` with a
  `.build_timelines()`/`.derive_states()` step over the real DataCo pack is follow-on work,
  not done here.
- **No cross-entity `JOINED` timeline is built automatically.** `timeline_builder.join(...)`
  is implemented and generic (never names an entity type), but nothing in this commit calls
  it over real DataCo entities (order/warehouse/carrier) — that composition is left for
  whichever module first needs it (plausibly module 7 or 9).
- **`illegal_transitions` per-report handling is "stop this entity's replay, report the
  finding, continue the run"** — never a run-aborting raise. Whether a stricter mode should
  exist (mirroring `MissingEventPolicy`'s selectable shape) is an open question, not decided
  here; `docs/architecture.md`'s "hard error" language is satisfied by the finding being
  unmissable in the report, not by a raised exception halting the process.
- **Duration measurement evaluation is scoped to `DURATION`/`DELAY` kinds and the specific
  operator set `DISPATCH_LATENCY`-shaped measurements use** (`CONSTANT`, `ATTRIBUTE`,
  `DURATION_BETWEEN`, `DIFFERENCE`, `SUM`, `MINIMUM`, `MAXIMUM`); `RATIO`/`PRODUCT` and
  `COST`/`IMPACT`/`COUNT`/`QUANTITY`/`RATIO`-kind measurements are out of this evaluator's
  scope and untouched.

---

## 04a. The Rule Engine — extension seam 4 (2026-09-01)

**Status: `built-unverified`.** Not one of the sixteen §36 modules: it is the mechanism
prd.md §46 requires and extension seam 4 of `docs/architecture.md` §5.1, at L5. `done` would
additionally require the `CONVENTIONS.md` §3 Validation Gate checklist executed and
recorded; that checklist does not exist for this seam, so the status is the honest one.

### Why it was built now, against a README that said not to

`rule_engine/dataco/README.md` said, before this commit:

> Authored with module 9 (Candidate Cause Generator), which is the first module that
> consumes rules. Empty until then, by intent — an unratified rule would fire against a
> graph nobody has validated.

That intent is quoted in the new README rather than deleted, because **the concern is still
live.** Modules 7, 8 and 9 are `not-started`, so there is no temporal property graph and
**no run has evaluated these rules against real DataCo facts.** What changed is the balance
of costs: leaving the seam unbuilt kept `rule_pack_version` `unset`, which blocked every
`run_id`, and left the ontology loader reporting rule coverage as a check that could not run.
Building it answers both; it does not make the rules right.

### Four ADRs, written before the code

- **ADR-0044** — the DSL. Six rule kinds as payload types (prd.md §26's five, plus
  `CONSTRAINT`, which prunes rather than proposes), a closed condition operator tree over
  role-bound addresses, and **no expression string, callable or plugin hook anywhere**. It
  records why it does *not* reuse `schema_mapper.dsl.ConditionExpression`: the import would
  be a legal downward edge, but that type addresses records and a rule condition addresses a
  role-bound participant of a matched event.
- **ADR-0045** — `KnowledgeProvenance` is a rule-DSL enum, deliberately not
  `ProvenanceClass`. A rule is a policy about facts, not a fact; carrying `ProvenanceClass`
  would invite `combine()` across two different questions.
- **ADR-0046** — `VocabularyView` in `core/ontology_view.py`, `IdentifierPrefix.RULE_PACK`,
  `docs/contracts.md` → 1.4.0 (additive; `engine_version` does not bump). Forbidden edge F3
  blocks L5 from importing `ontology_runtime`, so the vocabulary arrives as a plain `core`
  view produced by `extraction.ontology_adapters` — the same crossing modules 5/6 use.
- **ADR-0047** — constraints beat generators, conflicts are reported not resolved, and a
  firing without a trace cannot be constructed.

### Three defects found by the work, recorded rather than quietly fixed

**1. The indexing prefilter silently dropped admissible pairs.** The first
`FactIndex.admissible_slice` bisected the consequent bucket on `t_earliest`. A consequent
starting before the antecedent but ending after it — `cause = [day 5, day 5]`,
`effect = [day 0, day 10]` — overlaps, so its verdict is `UNDETERMINED` and it must be
retained and flagged (ADR-0007). Cutting on `t_earliest` dropped it. **This is the
"silently shrinking the graph" failure `CONTEXT.md` R-14 exists to prevent, hidden inside a
performance optimization**, and no correctness test in the suite noticed it — the tests
passed, the graph was just smaller. Pinned by
`test_an_overlapping_pair_that_starts_earlier_is_retained`, which fails against that version.

**2. The first static conflict check refused the real pack.** It treated a `CONSTRAINT`
forbidding an event type and a generator producing it as a contradiction. They are
complementary: a constraint is scoped to an entity in a named state, a generator is not.
The appealing version of that check is the wrong one, so ADR-0047 records the rejected
option and `test_a_constraint_and_a_generator_over_one_type_are_not_a_conflict` pins it.

**3. LAW-EVIDENCE fired on `Rule.confidence_weight`.** `check_confidence_is_a_vector.py`
refuses a `confidence`-named field bound to a float, and it was right to: the lint cannot
know this one is a rule weight rather than a judgement. **The field was renamed to
`base_strength`, not allowlisted** — an allowlist entry would have taught the next reader
that a bare-float confidence is acceptable here. It now matches `EvidenceItem.strength`,
the sanctioned precedent one field away (`docs/contracts.md` §5).

### Complexity, proved rather than asserted

`index.py` claims evaluation is linear in inputs plus output and never quadratic in the
event count. That claim in a docstring is worth nothing — the naive `O(n²)` implementation
passes every correctness test in the package and differs only in how long it takes. So
`EvaluationStatistics.pair_comparisons` is incremented at the one site a pair is examined
and **returned**, and the bound is measured:

```
  50 pairs ->      50 comparisons
 100 pairs ->     100 comparisons  ratio 2.00
 200 pairs ->     200 comparisons  ratio 2.00
 400 pairs ->     400 comparisons  ratio 2.00
 800 pairs ->     800 comparisons  ratio 2.00
```

Exactly one comparison per emitted pair. `test_the_measurement_would_fail_against_a_quadratic_scan`
additionally proves the 3.0 threshold *rejects* a nested scan (whose ratio is 4.0), so the
bound test is known to be measuring something rather than passing whatever it is given.

> **Corrected after the fact — read DEF-0008 below before relying on this.** Every fixture
> above is built at `Precision.DAY`. The bound holds for bounded intervals and is not a
> claim about the reference dataset, where 13 of 18 event types carry `UNKNOWN` precision and
> the prefilter has nothing to cut on. Measured there, the same evaluator emitted 148
> firings per event. The numbers above are not wrong; they are narrower than they read.

### Coverage against observed event types — the headline finding

```
rule pack 'dataco' v1.0.0: 23 of 24 rule(s) enabled,
13 of 20 declared event type(s) explained (65%).

BLIND SPOTS -- 6 declared event type(s) with no explanatory rule:
  FRAUD_SUSPECTED
  INVENTORY_SHORTFALL_DETECTED
  ORDER_PLACED
  PAYMENT_FAILED
  PAYMENT_REQUESTED
  PAYMENT_REVIEW_OPENED
```

**Every one of the six is a root in this dataset.** Nothing DataCo records explains why
stock ran short, why a settlement failed, or why a review was opened; `ORDER_PLACED` is the
process origin and has no antecedent by construction. A rule claiming to explain any of them
would be inventing a mechanism the source does not witness. The practical meaning is that a
root-cause query terminating at one of these says "this is where the evidence stops", which
is the correct answer.

`ORDER_RELEASED` is declared but **unwitnessable** — the schema mapping carries no emission
rule for it. The reachability check found this in a rule the author had just written, which
is now carried `enabled: false` with the reason recorded on the rule itself.

Knowledge provenance of the 24 rules: **`DOMAIN_EXPERTISE` 15, `DATASET_OBSERVATION` 4,
`ASSUMPTION` 5.** The four `DATASET_OBSERVATION` rules rest on statements the *ontology pack*
makes about the dataset, not on counts this repository has performed — **no pipeline has run
end to end** (OQ-014) — and the pack README says so.

### prd.md §25's chain terminates where the ontology terminates

§25 prints `Inventory Shortage -> Warehouse Delay -> Truck Missed -> Late Delivery ->
Customer Complaint -> Refund`. The first four segments are authored. The last two are not:
the ontology declares no complaint event type, because DataCo carries "no complaint, contact,
or service column of any kind", and no refund concept at all. Declaring them would
manufacture occurrences the source never recorded — the failure LAW-PROVENANCE and ADR-0029
exist to prevent. The gap is named in the pack README and in the coverage report rather than
left to be noticed.

### The domain-independence claim, extended to the rule DSL

`ontology/packs/hospital/` exists to prove the ontology DSL is not secretly logistics-shaped
(ADR-0026). `rule_engine/hospital/rules.yaml` extends that to the rule DSL: six rules over a
vocabulary sharing no term with logistics, loading through the identical code path.
`tests/ontology/test_rule_pack_loads.py` additionally asserts the proof pack exercises every
rule kind and contains no banned stem — a proof pack that decayed to one trivial rule, or
that borrowed logistics terms, would prove nothing while continuing to pass.

**What this does not prove:** the schema is domain-neutral; the ENGINE's neutrality still
rests on `tests/ontology/test_ontology_swap.py`, which `docs/architecture.md` §8 carries as
open.

### Gate output

```
$ make lint
LAW-DOMAIN: clean across 125 file(s) in 9 package(s).
LAYER BOUNDARIES: clean across 131 file(s).
LAW-EVIDENCE: clean across 131 file(s); confidence is a vector everywhere.
FIVE LAWS: byte-identical across CONTEXT.md §2 and CONVENTIONS.md §1.
GOVERNANCE CONSISTENCY: clean; 10 question(s) closed by an existing ADR, 12 still open.
self-test passed: 8 rule-pack violation shape(s) rejected, 2 legitimate pack(s) accepted.
ADR-0026: clean across 24 file(s) in 5 package(s); every metric is declared, not computed.
ONTOLOGY SCHEMA: ontology/_schema/ontology.schema.json matches the DSL models.
All matched files use Prettier code style!

$ make typecheck
Success: no issues found in 131 source files

$ pytest tests/unit tests/law tests/ontology tests/determinism
828 collected: 760 passed, 68 skipped, 0 failed
(the 68 skips are the service-backed persistence tests; they run in CI's `integration` job)
rule_engine coverage: dsl 90%, loader 91%, index 95%, trace 97%, facts 94%,
                      conflict 90%, evaluate 80%, coverage 57%
```

126 of those tests are this seam's:

| File | Tests |
|---|---|
| `tests/unit/rule_engine/test_dsl.py` | 26 |
| `tests/unit/rule_engine/test_evaluate.py` | 23 |
| `tests/unit/rule_engine/test_loader.py` | 20 |
| `tests/law/test_a_firing_explains_itself.py` | 16 |
| `tests/unit/rule_engine/test_trace.py` | 11 |
| `tests/ontology/test_rule_pack_loads.py` | 11 |
| `tests/unit/rule_engine/test_conflict_precedence.py` | 7 |
| `tests/unit/rule_engine/test_complexity_bound.py` | 7 |
| `tests/determinism/test_rule_firings_are_stable.py` | 5 |

`coverage.py` at 57% is the renderer, which only the `make rules` path executes; the
measurement functions it wraps are covered by the ontology tests.

### The self-test was observed to reject, not merely to pass

Required by ADR-0019 of every enforcement script. Beyond the eight planted cases, the check
was sabotaged deliberately — `if vocabulary.event_type(event_type) is None:` replaced with
`if False:` — and the self-test failed with
`SELF-TEST FAILED: the check did not reject -- a rule naming an undeclared event type`,
exit 1. Restored and re-verified green.

### Two defects found by running the pack against DataCo facts, AFTER this gate passed

The section above closed with "no rule in this pack has been observed to fire against DataCo
facts". That sentence was true when it was written and is no longer true: the pack was run
against real facts built from the pinned clean layer, and **it does not survive the
encounter.** Both findings below are recorded here rather than fixed in place, because both
need an ADR — one changes an evaluator guarantee, the other changes what a measured bound
means.

**DEF-0007 — `evaluate()` raises `OverflowError` on any `UNKNOWN`-precision event. Blocking.**
`FactIndex.admissible_slice` computes `bisect_left(keys, cause_earliest - span)`
(`index.py:138`). An `UNKNOWN` interval spans `datetime.min`→`datetime.max`, so `span` is
~9999 years and the subtraction underflows before any rule is consulted. **The method's own
docstring, twelve lines above the crash site, already specifies the correct behaviour** — "a
bucket holding an event with `UNKNOWN` precision has an unbounded `max_span`, so the lower
cut degenerates to zero and that bucket is scanned from its start". The code does not
degenerate. It raises. Prose and implementation disagreed and nothing compared them.

This is not a corner case for the reference dataset. **13 of 18 emitted DataCo event types
are 100% `UNKNOWN`-precision** — 61,290 of 158,175 events over a 20,000-row slice. Only
`ORDER_PLACED`, `ITEM_PICKED`, `ITEM_PACKED`, `SHIPMENT_DISPATCHED` and `SHIPMENT_DELIVERED`
carry bounds, because those are the only occurrences the source places in time at all. So
the DataCo pack cannot be evaluated over the DataCo dataset today, and the failure is a
traceback rather than a wrong answer.

Reproducible in **two synthetic events, no domain data**: one `DAY`-precision event, one
`UNKNOWN`-precision event sharing a participant, evaluated against the synthetic pack.

**Why no test caught it.** No test in `tests/unit/rule_engine/` constructs an `UNKNOWN`
interval, and none *can*: `tests/fixtures/facts.py::interval` hardcodes
`ProvenanceClass.OBSERVED`, and `TimeInterval` refuses `UNKNOWN` precision with `OBSERVED`
provenance (ADR-0007, correctly). **The fixture structurally forbids the only input the
evaluator dies on.** That is the DEF-0001 shape again — a check that cannot run reads
identically to a check that passed — relocated from an enforcement script into a test
fixture, which is where it was not being looked for.

**DEF-0008 — the measured complexity bound does not hold on the reference dataset.** With
`admissible_slice` clamped to the behaviour its docstring specifies, **12,494 real events
produced 1,855,405 firings — 148 per event**, of which 1,851,809 (99.8%) are
`temporally_unverifiable` and 1,855,364 (99.998%) are `UNDETERMINED`. 99.7% of the volume
comes from the four rules whose antecedent or consequent is an `UNKNOWN` type
(`R-DCO-DISPATCH-BEGINS-TRANSIT` 899,662, `R-DCO-DISPATCH-MISS-DELAYS` 438,096,
`R-DCO-TRANSIT-DELAYS` 424,984, `R-DCO-DELAY-LATE-ARRIVAL` 87,043). The rules over
timestamped types stay linear and small in the same run: 1,799 / 1,797 / 1,270 / 580.

The mechanism is not a bug in the index — it is the honest consequence of the clamp. An
event that could have happened at any instant is admissible against every candidate in its
linkage, so the prefilter has nothing to cut on and the pair set becomes a cross product.
One sampled firing reported an observed separation of **−63,614,073,600 to
+251,923,910,400 seconds against a 3-day authored window**, and fired.

**The engine is honest about this and that is the one thing that went right:** every such
firing carries `temporally_unverifiable: true`, which is exactly the signal that field was
added for, and `EvaluationStatistics` reports the counts rather than logging them. The
output is unusable, and it says so about itself.

**What this means for `test_complexity_bound.py`.** That test builds every fixture at
`Precision.DAY` (`test_complexity_bound.py:47,55`), so the 2.00 ratios recorded above are
measured on data whose shape the reference dataset does not have. The bound is real for
bounded intervals and is not a claim about this dataset. The section above is corrected in
place rather than deleted.

**Neither defect is fixed in this commit.** DEF-0007's fix is one clamp, but choosing
between "scan the bucket" and "refuse an `UNKNOWN` antecedent outright" is an evaluator
guarantee and belongs in an ADR with DEF-0008, since the cheap fix is what produces the
explosion. Recorded as risk R-21.

### What is still not true

- **The pack has now been observed to fire against DataCo facts, and the result is not
  usable.** See DEF-0007 and DEF-0008 immediately above. Modules 7–9 still do not exist, so
  every firing in the *test suite* remains over synthetic fixtures; the DataCo run was an
  audit harness, not a pipeline.
- **A valid rule pack can be a wrong rule pack**, for the reason `docs/ontology.md` §6 gives
  about ontologies. Nothing checks that a claimed mechanism is real, that a window is the
  right width, or that a weight is calibrated. Risk R-16.
- **Role resolution at evaluation is weaker than the loader's static check.** `Event` carries
  `source_entity_ids`/`target_entity_ids`, not roles, so the linkage is tested over the
  participants an event names rather than over the specific roles a rule labelled them with.
  A rule with transposed roles is admitted if the entities are related at all. Stated in
  `_linked`'s docstring; closing it needs role-tagged participants on a frozen type and its
  own ADR.
- **Recall is still bounded by rule coverage.** The coverage report names the declared types
  no rule explains and the `ConflictReport` names every suppressed candidate — two classes of
  absence that are no longer silent. The larger half is unchanged: a mechanism nobody wrote a
  rule for is still invisible, and no report can name what nobody thought of.

---

## 01. Data Adapter
- **Status:** **built-unverified** (2026-08-30) · **Phase:** P1 · **Contract:**
  `RawRecordBatch` (frozen), `DataQualityReport` (draft)
- **Scope reminder:** ingest, validate, clean. Rejects are counted and logged, never
  repaired (`CONVENTIONS.md` §7). This is one of only two modules permitted to hold rows.
- **Evidence:** §01a below.

## 02. Schema Mapper
- **Status:** **built-unverified** (2026-08-30) · **Phase:** P1 · **Contract:**
  `SchemaMappingSpec` (draft, ADR-0036)
- **Scope reminder:** dataset columns → ontology concepts. An unmapped column or value is
  a hard error, never a default. Last module permitted to hold rows (LAW-EVENT boundary).
- **Evidence:** §01a below — the two modules were built in one commit and share their
  evidence, because module 2's coverage assessment is only meaningful against a real header
  and module 1 cannot validate anything without a mapping.

## 03. Entity Extractor
- **Status:** **built-unverified** (2026-08-30) · **Phase:** P1 · **Contract:** `Entity`
  (frozen), `ReconciliationReport` / `EntityHistory` (draft, ADR-0039)
- **Scope reminder:** identity is the content address and nothing else. No similarity
  match, ever: a fuzzy merge is irreversible, invisible downstream, and produces a graph in
  which two participants have silently become one.
- **Evidence:** §02a.

## 04. Event Generator
- **Status:** **built-unverified** (2026-08-30) · **Phase:** P1 · **Contract:** `Event`
  (frozen), `EventQualityReport` (draft, ADR-0040)
- **Prerequisite:** OQ-002 (time intervals) and OQ-012 (`Trigger` definition) resolved.
- **Scope reminder:** highest-risk module in the system (ADR-0004). One record emits 0..N
  events and one occurrence is one event however many records witness it. Establishes the
  LAW-EVENT boundary: nothing downstream sees a row.
- **Evidence:** §02a — modules 3 and 4 were built in one commit and share their
  evidence, because module 4 resolves participants against the entities module 3 mints and
  neither can be measured without the other.

## 05. Timeline Builder
- **Status:** **built-unverified** (2026-08-31) · **Phase:** P2 · **Contract:** `Timeline`
  (draft, ADR-0042)
- **Scope reminder:** adjacency on a timeline is sequence only, never causation.
- **Evidence:** §05a below.

## 06. State Engine
- **Status:** **built-unverified** (2026-08-31) · **Phase:** P2 · **Contract:** `State`,
  `Transition` (frozen; consumed, not changed)
- **Scope reminder:** an illegal transition per the ontology is a hard error.
- **Evidence:** §05a below — modules 5 and 6 were built in one commit and share their
  evidence, because module 6 replays the `Timeline` values module 5 produces and neither
  is measurable alone.

## — Rule Engine (extension seam 4, not a §36 module)
- **Status:** **built-unverified** (2026-09-01) · **Phase:** — (mechanism, prd.md §46) ·
  **Contract:** `RulePack` (draft), `RuleFiring` / `ConflictReport` (new, draft)
- **Scope reminder:** rules are **data**. The engine contains zero domain terms and is in
  LAW-DOMAIN scope; the pack contains all of them. Produces traced firings, never a
  `CausalEdge` — module 9 owns the LAW-TIME gate and edge construction.
- **Evidence:** §04a above. Sets `rule_pack_version`, the last unset `RunKey` input.

## 07. Relationship Resolver
- **Status:** not-started · **Phase:** P2 · **Contract:** `Relationship` (draft)

## 08. Temporal Graph Builder
- **Status:** not-started · **Phase:** P2 · **Contract:** `TemporalPropertyGraph` (draft)
- **Scope reminder:** **no causal inference here** (prd.md §44). Writes `PRECEDES`, never
  `CAUSES`. Owns the Neo4j projection build (ADR-0001).

## 09. Candidate Cause Generator
- **Status:** not-started · **Phase:** P3 · **Contract:** `CandidateEdge` (draft)
- **Prerequisite:** OQ-002 resolved by ADR-0007, extended by ADR-0021 — no longer blocking.
  This module owns the LAW-TIME gate, and enforces it by constructing every edge through
  `CausalEdge.between`, which raises rather than returning an invalid edge.

## 10. Confidence Scorer
- **Status:** not-started · **Phase:** P3 · **Contract:** `ConfidenceVector`, `EvidenceRecord`,
  `EvidenceItem` (**frozen**, ADR-0025); `CausalGraph` (draft)
- **Prerequisite:** OQ-005 resolved by ADR-0009 — no longer blocking. This module owns the
  LAW-EVIDENCE gate and is the only module permitted to write `CAUSES`. It consumes the
  aggregator registry rather than defining its own rollup.

## 11. Root Cause Analyzer
- **Status:** not-started · **Phase:** P3 · **Contract:** `RootCauseRanking` (draft)
- **Prerequisite:** OQ-003 resolved by ADR. Must emit `earliest_cause` and
  `actionable_root_causes` as separate fields.

## 12. Propagation Analyzer
- **Status:** not-started · **Phase:** P3 · **Contract:** `PropagationReport` (draft)
- **Scope reminder:** depth and breadth are separate measures; feedback loops are a
  requirement, not a bug (prd.md §31).

## 13. Counterfactual Simulator
- **Status:** not-started · **Phase:** P4 · **Contract:** `SimulatedWorld` (draft)
- **Prerequisite:** OQ-007 resolved by ADR. Never writes back to history. Output is a
  plausibility simulation, labeled as such.

## 14. Intervention Optimizer
- **Status:** not-started · **Phase:** P4 · **Contract:** `Intervention` (draft)
- **Prerequisite:** OQ-013 (cost source) resolved. Cost is ontology configuration, never
  inferred.

## 15. Explanation Generator
- **Status:** not-started · **Phase:** P5 · **Contract:** `Explanation` (draft)
- **Scope reminder:** every sentence traces to graph evidence (prd.md §52). No LLM in this
  path in V1 (`CONTEXT.md` §10).

## 16. Visualization API
- **Status:** not-started · **Phase:** P5 · **Contract:** HTTP API (draft)
- **Scope reminder:** provenance classes must survive serialization and be visually
  distinct downstream (LAW-PROVENANCE). Every response carries the output envelope
  (`CONVENTIONS.md` §11).
