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

**No module has been started. No business logic exists.** The repository now contains the
six governance files, `docs/prd.md`, `docs/architecture.md`, the package scaffold with
draft `core/` contracts, the enforcement scripts, and the local stack — see
**P0. Architecture blueprint and repository scaffold** below for what was built and what
was deliberately not.

Every module below is `not-started`; all fields are empty by fact, not by omission. The
first module may not begin until `CONTEXT.md` OQ-001 (module authority) is resolved, and
modules 9+ additionally require OQ-002 (LAW-TIME over intervals) resolved by ADR.

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
- Enforcement scripts, standard library only — `check_domain_independence.py` (LAW-DOMAIN,
  with a self-test), `check_layers.py` (F1–F9), `check_dependency_policy.py`,
  `check_law_copies.py`, `check_determinism.py`, `rebuild_graph.py`.
- Tooling — `pyproject.toml` with exact pins, ruff, `mypy --strict`, pytest with coverage
  reporting; `Makefile` (`setup up down lint typecheck laws test test-fast bench
  rebuild-graph reset`); Docker Compose with five healthchecked services and overridable
  host ports; two numbered SQL migrations; a nine-job GitHub Actions workflow.
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
| 6 | `make up` was not verified with all five services healthy simultaneously on this machine | Docker was allocated 1.9 GB and ~1.25 GB was held by unrelated containers, so Neo4j was OOM-killed (exit 137) whenever the frontend was also running. Groups of four were verified healthy. Documented as a 4 GB host requirement. | `deployment/README.md` |
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

## 01. Data Adapter
- **Status:** not-started · **Phase:** P1 · **Contract:** `RawRecordBatch` (draft)
- **Prerequisite:** OQ-001 resolved.
- **Scope reminder:** ingest, validate, clean. Rejects are counted and logged, never
  repaired (`CONVENTIONS.md` §7). This is one of only two modules permitted to hold rows.

## 02. Schema Mapper
- **Status:** not-started · **Phase:** P1 · **Contract:** `SchemaMapping` (draft)
- **Scope reminder:** dataset columns → ontology concepts. An unmapped column or value is
  a hard error, never a default. Last module permitted to hold rows (LAW-EVENT boundary).

## 03. Entity Extractor
- **Status:** not-started · **Phase:** P1 · **Contract:** `Entity` (draft)

## 04. Event Generator
- **Status:** not-started · **Phase:** P1 · **Contract:** `Event` (draft)
- **Prerequisite:** OQ-002 (time intervals) and OQ-012 (`Trigger` definition) resolved.
- **Scope reminder:** highest-risk module in the system (ADR-0004). One row emits 0..N
  events. Establishes the LAW-EVENT boundary: nothing downstream sees a row.

## 05. Timeline Builder
- **Status:** not-started · **Phase:** P2 · **Contract:** `Timeline` (draft)
- **Scope reminder:** adjacency on a timeline is ordering only, never causation.

## 06. State Engine
- **Status:** not-started · **Phase:** P2 · **Contract:** `State`, `Transition` (draft)
- **Scope reminder:** an illegal transition per the ontology is a hard error.

## 07. Relationship Resolver
- **Status:** not-started · **Phase:** P2 · **Contract:** `Relationship` (draft)

## 08. Temporal Graph Builder
- **Status:** not-started · **Phase:** P2 · **Contract:** `TemporalPropertyGraph` (draft)
- **Scope reminder:** **no causal inference here** (prd.md §44). Writes `PRECEDES`, never
  `CAUSES`. Owns the Neo4j projection build (ADR-0001).

## 09. Candidate Cause Generator
- **Status:** not-started · **Phase:** P3 · **Contract:** `CandidateEdge` (draft)
- **Prerequisite:** OQ-002 resolved by ADR. This module owns the LAW-TIME gate.

## 10. Confidence Scorer
- **Status:** not-started · **Phase:** P3 · **Contract:** `ConfidenceVector`, `CausalGraph`, `EvidenceRecord` (draft)
- **Prerequisite:** OQ-005 resolved. This module owns the LAW-EVIDENCE gate and is the
  only module permitted to write `CAUSES`.

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
