# DECISIONS.md — Architecture Decision Record log

**Append-only.** Never edit an accepted ADR. To change a decision, write a new ADR whose
`Supersedes` field names the old one, and set the old one's status to `superseded`
(status is the only field that may ever be edited on a past ADR).

Read this file before proposing any architectural change. If your proposal contradicts an
`accepted` ADR, you must write the superseding ADR **before** writing code
(`CONTEXT.md` §0).

---

## ADR template

```markdown
## ADR-NNNN — <short imperative title>

- **Date:** YYYY-MM-DD
- **Status:** proposed | accepted | superseded by ADR-NNNN | reversed
- **Supersedes:** ADR-NNNN | —
- **Affects modules:** <from CONTEXT.md §3>
- **Affects interfaces:** <from CONTEXT.md §6>

### Context
What forced a decision. Cite prd.md sections and CONTEXT.md OQ ids. State what is
true today, not what we hope.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | ... | ... |
| B | ... | ... |
(Minimum two. "Do nothing" is a legitimate option and must be evaluated when the
decision is reversible-expensive.)

### Decision
One paragraph, imperative, unambiguous. A reader must be able to detect a violation
of this decision by reading code.

### Consequences
**Positive:** ...
**Negative:** ...   <- required; an ADR with no negative consequences is under-analyzed
**Obligations created:** tests, lint jobs, docs, migrations that now must exist.

### Reversibility cost
`low` | `medium` | `high` — plus a concrete statement of what would have to change.
```

**Status meanings.** `proposed`: written, not ratified, may not be relied on by code.
`accepted`: binding. `superseded`: replaced; kept for history. `reversed`: withdrawn
without replacement; the prior state returns.

---

## ADR-0001 — Use two databases: PostgreSQL as system of record, Neo4j as derived projection

- **Date:** 2026-08-23
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Data Adapter, Temporal Graph Builder, all persistence
- **Affects interfaces:** `TemporalPropertyGraph`, `Event`, `Entity`

### Context
prd.md §41 specifies PostgreSQL and Neo4j. prd.md §42 justifies the split — "PostgreSQL
stores facts. Neo4j stores relationships. Do not force graph reasoning into SQL." The PRD
does **not** state which store is authoritative, how they stay consistent, or what happens
when a write succeeds in one and fails in the other. No transaction spans both. Without a
ruling, two modules will each treat their own store as the truth (CONTEXT.md OQ-004).
Determinism (`CONVENTIONS.md` §3) is also unenforceable if graph state can be mutated
independently of the facts that produced it.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Single store (Postgres + recursive CTEs) | Rejected. Multi-hop propagation, cycle detection (prd.md §31), and path queries over a graph of this shape are exactly what prd.md §42 forbids forcing into SQL. Performance goals in §55 are unlikely to hold. |
| B | Single store (Neo4j only) | Rejected. Loses relational integrity, dataset versioning, and audit tables (prd.md §54). Tabular facts and immutable event history belong in a relational store. |
| C | Dual-write, both authoritative | Rejected. No transaction spans both engines; a partial failure yields split-brain with no reconciliation rule. |
| D | **Postgres system of record, Neo4j derived projection** | **Chosen.** Preserves §42's separation while giving exactly one authority. The graph becomes reproducible from facts, which is what makes the determinism guarantee testable. |

### Decision
PostgreSQL is the **system of record** for all facts: entities, events, states,
transitions, evidence records, audit log, dataset and ontology versions. Neo4j is a
**derived, fully rebuildable projection** of graph structure, keyed by
`(ontology_version, dataset_version, graph_projection_version)`. The projection is built
only by the Temporal Graph Builder and downstream inference modules writing through it.
**Any code path that writes to Neo4j without a corresponding Postgres fact is a defect.**
Dropping and rebuilding the entire Neo4j projection from Postgres must always be a safe
operation, and there must be a command that does it.

### Consequences
**Positive:** Exactly one authority. The graph is reproducible from facts, which makes the
byte-identical determinism requirement testable end to end. Recovery from graph corruption
is a rebuild, not a repair. Redis (prd.md §41) is unambiguously a cache of the projection
and never a source.

**Negative:** Rebuild cost grows with dataset size and is on the critical path for the
prd.md §55 targets (graph generation < 60s). Two schemas must be kept in step. A reader
querying Neo4j alone can observe a stale projection; every query result must carry the
projection version so staleness is detectable rather than invisible.

**Obligations created:** a rebuild command; a projection-version stamp on every graph
query response; a test that a rebuild from Postgres produces a byte-identical projection;
schema migration procedure covering both stores.

### Reversibility cost
**Medium.** Collapsing to a single store later means rewriting all graph traversal and
re-homing the audit tables. Changing *which* store is authoritative later is **high** —
every module's read path assumes it.

---

## ADR-0002 — Achieve domain independence through an ontology layer, not through configuration flags

- **Date:** 2026-08-23
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Schema Mapper, Entity Extractor, Event Generator, all core modules
- **Affects interfaces:** `SchemaMapping`, `Entity`, `Event`

### Context
prd.md §7, §35 and §62 require that the reasoning engine never depend on logistics
concepts and that replacing the ontology alone should enable a new domain. LAW-DOMAIN
makes this mechanically enforceable. But prd.md §21 itself defines a logistics event
vocabulary (`Inventory Reserved`, `Shipment Dispatched`, …) and prd.md §46 says business
rules must be configurable and never hardcoded. There is a live tension: the PRD names
domain vocabulary and simultaneously bans it (CONTEXT.md OQ-006).

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Domain flags / conditionals inside core algorithms | Rejected. Directly violates LAW-DOMAIN and turns every new domain into a core-code change. |
| B | Per-domain forks of the engine | Rejected. Guarantees divergence; contradicts prd.md §8 and §60. |
| C | Duck-typed generic code with no explicit ontology | Rejected. Domain assumptions leak invisibly and cannot be linted. |
| D | **Explicit ontology layer + banned-vocabulary lint** | **Chosen.** Makes the boundary both explicit and machine-checkable. |

### Decision
All domain vocabulary — entity types, event types, state names, transition legality, rule
definitions, cost scales — lives as **data** in `ontology/` and `rule_engine/`
definitions, never as identifiers or literals in reasoning code. prd.md §21's event
vocabulary is a **DataCo ontology instance**, not part of the engine. Core modules operate
solely on `Event`, `Entity`, `State`, `Transition`, `Relationship`. LAW-DOMAIN is enforced
by a CI lint job using word-boundary matching with an explicit allowlist; ontology and rule
**data** files are exempt from the lint, `rule_engine` **code** is not. The active ontology
is versioned and hashed, and `ontology_hash` appears in every output envelope.

### Consequences
**Positive:** A new domain is an ontology authoring task. The domain boundary is testable,
not aspirational. Ontology versioning gives reproducibility a stable key.

**Negative:** Indirection cost — no core code may name the thing it is reasoning about,
which makes debugging harder and error messages more abstract. Ontology authoring becomes
a first-class skill and a first-class failure mode: a bad ontology now produces silently
wrong causality rather than a crash. The lint has a false-positive surface
(`ordering`, `reorder`, `border`) that must be managed or the lint will be disabled.

**Obligations created:** the CI lint job and its allowlist; ontology schema and validator;
`ontology_hash` computation; error messages that stay useful without domain nouns.

### Reversibility cost
**High.** Domain independence is a structural property. Retrofitting it after logistics
concepts have leaked into core algorithms means rewriting the reasoning engine.

---

## ADR-0003 — Version 1 uses rules and deterministic graph algorithms; machine learning is deferred

- **Date:** 2026-08-23
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Candidate Cause Generator, Confidence Scorer, Root Cause Analyzer, Counterfactual Simulator, Intervention Optimizer
- **Affects interfaces:** `ConfidenceVector`, `CandidateEdge`

### Context
prd.md §45 stages ML across four versions and states plainly: "Version 1 must remain
useful without sophisticated ML. The intelligence comes from architecture rather than
model complexity." prd.md §38 requires deterministic-when-rules-are-explicit and
explainable-by-design. The Definition of Done requires byte-identical output for identical
inputs, seed, and ontology hash. prd.md §41 nonetheless lists pgmpy and DoWhy in the stack
(CONTEXT.md OQ-008).

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Ship Bayesian networks in V1 | Rejected. Requires a validated structure the dataset cannot supply yet; inference introduces nondeterminism and a confidence number that resists decomposition (LAW-EVIDENCE). |
| B | Ship a supervised delay predictor | Rejected outright. prd.md §62 explicitly says this is not a delay predictor. Building one would redefine the product. |
| C | Hybrid: rules with an ML fallback for unscored edges | Rejected for V1. Two confidence semantics in one graph; users cannot tell which produced a given edge; provenance classes blur. |
| D | **Rules + deterministic graph algorithms + explicit statistical support as a named component** | **Chosen.** Satisfies §45, keeps LAW-EVIDENCE and the determinism gate achievable. |

### Decision
V1 causal inference is produced by explicit rules, temporal constraints, entity-sharing,
and **frequency-based statistical support computed deterministically** — not by learned
models. `pgmpy`, `DoWhy`, and `PyTorch Geometric` are **not** V1 dependencies and may not
be imported by V1 code. Statistical association is a **named component** of
`ConfidenceVector` carrying provenance `STATISTICAL`; it is never silently promoted to
`INFERRED`. Introducing any nondeterministic component requires its own ADR and an explicit
seed contract.

### Consequences
**Positive:** Every edge is explainable by construction. The determinism gate is
achievable. V1 delivers value without training data or labels — of which this dataset has
none for causality. Dependency surface stays small.

**Negative:** Recall is bounded by rule coverage: causal relationships not expressible as
rules will be missed, and the system cannot tell the user what it missed. Rule authoring
is manual effort that scales with domain complexity. Confidence calibration is heuristic
and has no ground truth to validate against — prd.md §57's evaluation metrics will
therefore be qualitative in V1.

**Obligations created:** rule authoring format and validator; deterministic frequency
computation with canonical ordering; a dependency-policy check that blocks ML imports;
honest documentation of recall limits in explanations.

### Reversibility cost
**Low.** V2 adds ML behind the existing `ConfidenceVector` interface as additional named
components. This ADR is deliberately structured so that deferral costs nothing later.

---

## ADR-0004 — The Event is the atomic computational unit; rows are evidence, not units

- **Date:** 2026-08-23
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** all
- **Affects interfaces:** `Event`, `RawRecordBatch`

### Context
prd.md §9 Principle 1 ("Events are first-class entities. Rows are not."), §18 ("The
fundamental computational unit is not a row. It is an Event."), and §20 ("The engine
should never reason directly over CSV rows") all state this. LAW-EVENT makes it binding.
The DataCo dataset is row-oriented and a single row encodes several events at different
timestamps, so the mapping is one-to-many and lossy in both directions if done casually.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Reason over DataFrames, treat events as a view | Rejected. Violates LAW-EVENT; temporal reasoning over row-aligned columns silently assumes one timestamp per record. |
| B | One event per row | Rejected. A DataCo row contains order, shipping, and delivery moments at different times; collapsing them destroys the temporal ordering the entire product depends on. |
| C | **Row is evidence; a row emits 0..N events, each with its own timestamp and provenance** | **Chosen.** |

### Decision
The `Event` is the atomic unit of all reasoning. A raw record is **evidence** from which
zero or more events are generated by the Event Generator, each with its own timestamp,
type, participating entities, provenance class, and a link back to the evidence record
that produced it. Downstream of the Event Generator, **no module may accept, return, or
hold a row, DataFrame, or CSV column**. Events are immutable once generated; correction
means emitting a new event, never mutating an old one (prd.md §54, "Immutable event
history").

### Consequences
**Positive:** Temporal reasoning becomes correct by construction, since every event has
exactly one time semantics. Domain independence becomes achievable — events are the shared
abstraction across domains. Provenance attaches naturally at the point of generation.

**Negative:** Event generation is the hardest and highest-risk module: a row-to-events
mapping error is invisible downstream and corrupts every conclusion. Storage expands
(N events per row). Debugging requires tracing an event back through evidence records
rather than reading a familiar table.

**Obligations created:** every `Event` carries `evidence_record_ids`; a round-trip test
that events reference real source records; immutability enforcement; the LAW-EVENT
boundary check in CI.

### Reversibility cost
**High.** This is the central abstraction. Reversing it means rewriting every module.

---

## ADR-0005 — Provenance classes are explicit, disjoint, and never silently promoted

- **Date:** 2026-08-23
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** all
- **Affects interfaces:** `Event`, `CandidateEdge`, `ConfidenceVector`, `EvidenceRecord`, `SimulatedWorld`, HTTP API

### Context
prd.md §37 requires the engine to distinguish Observed Facts, Business Assumptions,
Statistical Associations, Inferred Causes, and Counterfactual Simulations, and states they
"must never be conflated in the implementation or the user interface." prd.md §54 adds "No
inferred result should overwrite observed facts." prd.md §16 requires the distinction
between inferred and verified causality to remain visible. LAW-PROVENANCE binds this.
Without a single enforced field, this degrades into per-module conventions that diverge —
which is the exact cross-session failure mode this project is structured to prevent.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | A boolean `is_inferred` flag | Rejected. Collapses five distinct classes into two; cannot express `ASSUMED` vs `STATISTICAL` vs `SIMULATED`. |
| B | Separate tables/graphs per class, no shared field | Rejected. Joins reintroduce conflation at query time, and cross-class reasoning becomes untraceable. |
| C | Confidence score as an implicit proxy for provenance | Rejected. Conflates *how we know* with *how sure we are* — orthogonal axes. An `OBSERVED` fact and a high-confidence `INFERRED` edge are not the same kind of thing. |
| D | **A required, closed-set `provenance_class` field on every assertion, plus explicit promotion events** | **Chosen.** |

### Decision
Every assertion the system holds or emits — event, state, edge, confidence component,
propagation figure, intervention, explanation sentence — carries a required
`provenance_class` from the closed set `OBSERVED | ASSUMED | STATISTICAL | INFERRED |
SIMULATED`. The classes are **disjoint and never merged**. Promotion between classes never
happens implicitly: any promotion is an explicit, logged, evidence-bearing operation.
**An `INFERRED` or `SIMULATED` value may never overwrite an `OBSERVED` one** — simulation
writes to a separate world, never back to history. The classes are visually distinct in
the UI and preserved through every API response.

### Consequences
**Positive:** prd.md §16's honesty requirement becomes structural rather than editorial.
Audit and traceability (prd.md §54) come almost free. Counterfactual output cannot be
mistaken for history. Mixed-provenance aggregations become detectable defects.

**Negative:** Every schema, DTO, API response, and UI component carries the field —
pervasive and verbose. Aggregation across mixed provenance requires an explicit rule at
every call site (default: the aggregate takes the *weakest* class present). The five-class
distinction must be taught to users, or the UI will look cluttered without conveying why.

**Obligations created:** the field on every schema; the weakest-class aggregation rule; a
test asserting no `OBSERVED` record is ever written by an inference module; distinct UI
treatment; the assumption statement carried with `SIMULATED` output (see OQ-007).

### Reversibility cost
**High.** Retrofitting provenance onto an existing corpus means re-deriving the origin of
every stored assertion — for many of them, impossible after the fact.

---

## ADR-0006 — prd.md §36 modules are the authoritative unit of build; §44 names are deployment groupings

- **Date:** 2026-08-23
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** all 16
- **Affects interfaces:** all

### Context
prd.md §36 lists 16 logical modules in pipeline sequence. prd.md §44 lists 10 backend
services with overlapping but differently-named responsibilities (`Dataset Service`,
`Ontology Service`, `Event Builder`, …). Neither section claims authority over the other,
and no mapping between them exists. `CONTEXT.md` OQ-001 records the cost if this stays
open: two sessions build the same component twice under two names, the interface registry
fragments, and integration fails late. This must be settled before module 1 begins.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | §44 services are authoritative; §36 is an informal sketch | Rejected. §36 states "each module has a single responsibility and communicates through standardized interfaces" — it is the more precise text, and it is the one the pipeline in §48 and Appendix A follow. |
| B | Build both; treat §44 as a second decomposition | Rejected. Two decompositions means two ownership models and two interface registries for one system. |
| C | **§36 is the authoritative build/ownership unit; §44 names are deployment-level groupings of §36 modules** | **Chosen.** Keeps both sections meaningful without letting either be silently ignored. |
| D | Re-derive a fresh decomposition from first principles | Rejected. The PRD is the statement of intent; inventing a third naming would strand both. |

### Decision
The 16 modules of prd.md §36 are the authoritative unit of build, ownership, test, and
gate. Every module status, interface, and Definition-of-Done record is keyed to a §36
module. The 10 names in prd.md §44 are **deployment-level groupings** and carry no
ownership: they describe how modules may be packaged into running services, nothing more.
The mapping table in `CONTEXT.md` §3 is normative; `Visualization API` is unmapped in §44
and that is not a gap in §36. A document, prompt, or commit that names a §44 service as
the unit of work is a defect.

### Consequences
**Positive:** One decomposition, one registry, one ownership model. A module prompt has an
unambiguous subject. The §44 names remain usable for deployment topology without competing
for authority.

**Negative:** §44's service boundaries were written with deployment in mind and are
sometimes a better fit for a container than a §36 module is; deployment will therefore not
be one-container-per-module, and the mapping table has to be maintained by hand. A reader
coming from §44 must consult the mapping table to find the code.

**Obligations created:** the `CONTEXT.md` §3 mapping table stays current; every module
prompt names a §36 module; `PROGRESS.md` sections stay in §36 sequence.

### Reversibility cost
**Low.** The mapping table already exists in both directions; re-homing ownership onto §44
names would be a rename, not a restructure.

---

## ADR-0010 — `core/` exists, and the LAW-DOMAIN lint is specified precisely enough to survive contact

- **Date:** 2026-08-23
- **Status:** superseded by ADR-0019
- **Supersedes:** —
- **Affects modules:** all
- **Affects interfaces:** all

### Context
LAW-DOMAIN names `core/` as an in-scope directory, but prd.md §43's repository structure
has no `core/` at all. The law also specifies naive case-insensitive substring matching,
which fires on `ordering`, `reorder`, `recorder`, `border`, and `ordinal` — every one of
them legitimate in a temporal reasoning system. And prd.md §21 defines an event vocabulary
made entirely of the banned words. `CONTEXT.md` OQ-006 records the real risk: a lint with a
high false-positive rate gets disabled, and LAW-DOMAIN then holds by convention only —
exactly the failure it exists to prevent.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Keep naive substring matching | Rejected. It fails on the project's own vocabulary; the first `canonical_sort_ordering` identifier makes the lint a nuisance, and a nuisance lint gets a `# noqa` or a deletion. |
| B | Drop the lint; keep LAW-DOMAIN as a review convention | Rejected. `CONTEXT.md` R-10 already records that a stated-but-unenforced law is the thing this project is structured to prevent. |
| C | Scan identifiers only, not comments or strings | Rejected. Error messages are where domain nouns leak most naturally, and LAW-DOMAIN applies to strings (`CONVENTIONS.md` §7). |
| D | **Word-boundary matching, explicit scope, data-file exemption, justified allowlist, self-test** | **Chosen.** |

### Decision
`core/` is added to the repository structure, amending prd.md §43 (see also ADR-0012). The
LAW-DOMAIN lint is implemented as `scripts/check_domain_independence.py` with this exact
specification: word-boundary (`\b`), case-insensitive matching of the seven banned tokens;
scope of `core/`, `graph_engine/`, `causal_engine/`, `counterfactual_engine/`,
`recommendation_engine/`, and `rule_engine/` **source code**; exemption for
`tests/fixtures/**` and for ontology and rule **data** files; a reviewed
`.lawdomain-allowlist` where every entry carries a one-line justification and a malformed
entry fails the lint; and a `--self-test` mode that asserts the matcher fires on all seven
tokens and on none of the five near-misses. The job **fails the build; it does not warn**.
prd.md §21's event vocabulary is a DataCo ontology *instance* under `ontology/`, not part
of the engine.

### Consequences
**Positive:** LAW-DOMAIN is now a build outcome rather than an aspiration. The
false-positive surface is closed by construction and proved closed by the self-test, so the
pressure to disable the lint never builds. The allowlist makes every exception visible and
attributable.

**Negative:** Word boundaries make the bare English word that collides with the banned
vocabulary unusable in core code *and in its comments*, so authors must write "ordering",
"sequence", or "sorted" instead — a real and permanent friction, and one that makes some
prose slightly stilted. The lint still cannot catch domain dependence expressed as a branch
on a data *value* rather than as vocabulary; that hole is documented in
`docs/architecture.md` §1.5 and §5.3 rather than pretended away. Scanning only `.py`,
`.md`, `.sql`, and `.cypher` leaves other file types unchecked.

**Obligations created:** the script and its self-test run in CI as a required job; the
allowlist stays reviewed; `docs/architecture.md` §1.5 keeps stating what the lint cannot
catch; `tests/ontology/test_ontology_swap.py` supplies the empirical check the lint cannot.

### Reversibility cost
**Low** for the lint specification. **High** for domain independence itself — see ADR-0002.

---

## ADR-0012 — One installable Python distribution under `backend/src/`, deviating from prd.md §43

- **Date:** 2026-08-23
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** all
- **Affects interfaces:** all

### Context
prd.md §43 prints `backend/`, `frontend/`, `ontology/`, `graph_engine/`, `rule_engine/`,
`causal_engine/`, `counterfactual_engine/`, `recommendation_engine/`, `visualization/`,
`tests/`, `docs/`, `datasets/`, `scripts/`, and `deployment/` as sibling repository-root
directories, and says "every directory represents one bounded responsibility". Taken
literally, the reasoning packages are top-level Python packages with no shared import root:
there is no single installable distribution, `mypy`/`ruff`/`pytest` configuration
fragments, and `ontology/` and `rule_engine/` would each have to be both a data directory
and an importable package. The bounded-responsibility intent is sound; the physical layout
is not workable.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Literal §43 layout | Rejected. Name collision between the `rule_engine` data directory and the `rule_engine` package; no single import root; every tool needs per-directory configuration; `pip install -e .` has no target. |
| B | Flat `src/` with no sub-packages, modules distinguished by filename | Rejected. Layer ranks become unenforceable — the layer lint needs a package to attribute an import to. |
| C | **One distribution `causalog` at `backend/src/causalog/`, with the §43 engine names preserved as sub-packages; data directories stay at the repository root** | **Chosen.** Keeps §43's bounded responsibilities as real boundaries while giving the toolchain one root. |
| D | A monorepo of several distributions, one per engine | Rejected. Enormous ceremony for a single deployable, and cross-package refactoring becomes a release process. |

### Decision
All Python reasoning code lives in one installable distribution, `causalog`, rooted at
`backend/src/causalog/`. The prd.md §43 engine directory names are preserved verbatim as
sub-packages, so §43's bounded responsibilities survive as enforced package boundaries.
`ontology/` and `rule_engine/` remain repository-root **data** directories — which keeps
the `CONVENTIONS.md` §6 lint-exemption paths valid unchanged — while their code
counterparts are `causalog.ontology_runtime` and `causalog.rule_engine`, neither of which
is lint-exempt. `core/`, `ingestion/`, `extraction/`, `explanation_engine/`,
`orchestration/`, `persistence/`, and `api/` are added; each justifies itself in its own
`README.md`. **`visualization/` is deleted**: it is prd.md §36 module 16, it lives at
`causalog.api.visualization`, and a top-level directory for it cannot state a
responsibility distinct from `frontend/` and `api/`.

### Consequences
**Positive:** One `pyproject.toml`, one `mypy` invocation, one `ruff` configuration, one
import root, one layer-rank table. `pip install -e backend` works. The layer lint can
attribute every import to exactly one package.

**Negative:** A reader holding prd.md §43 will not find `graph_engine/` where the PRD says
it is, and this ADR is the only thing that explains why — a permanent extra hop for anyone
onboarding from the PRD. The nesting also makes import paths longer
(`causalog.causal_engine.confidence_scorer`), and the split between the `rule_engine` data
directory and the `causalog.rule_engine` package is a genuine subtlety that will be
mis-navigated at least once.

**Obligations created:** `docs/architecture.md` §1 documents the mapping from §43 names to
package paths; `CONTEXT.md` §3 carries a package-path column; each added directory carries
a one-sentence responsibility in its `README.md`.

### Reversibility cost
**Medium.** Flattening back to §43 is a mechanical move plus an import rewrite, but every
tool configuration, the layer lint's rank table, and the Dockerfiles would follow.

---

## ADR-0013 — `run_id` is content-addressed; the per-execution identifier is renamed `execution_id`

- **Date:** 2026-08-23
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** all
- **Affects interfaces:** `OutputEnvelope`, every inferred artifact, the audit trail

### Context
Reproducibility needs a name for "the complete set of inputs that determine the output":
dataset version, ontology hash, rule pack version, engine version, and seed.
`CONVENTIONS.md` §8 already uses `run_id` for something different — a per-pipeline-execution
identifier threaded through logs — and §9 explicitly permits it to be sequential or random
and excludes it from all determinism comparisons. One word is being asked to mean two
things: a stable fingerprint of inputs, and a volatile marker of one execution. Leaving
that collapsed guarantees that some module keys artifacts by a value that changes every
run, which silently destroys reproducibility.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Leave `run_id` volatile; introduce `run_key` for the fingerprint | Rejected. Artifacts would be keyed by `run_key` while logs and audit rows carry `run_id`, and every join between them becomes a place to use the wrong one. |
| B | Make `run_id` content-addressed and drop the per-execution identifier | Rejected. Two executions of the same Run must remain distinguishable in logs, or an incident cannot be traced to the execution that produced it. |
| C | **`run_id` becomes content-addressed; the per-execution identifier is renamed `execution_id`** | **Chosen.** The word that appears on artifacts means the reproducible thing, which is the reading every consumer will assume. |

### Decision
`run_id = "run:" + sha256(dataset_version | ontology_hash | rule_pack_version |
engine_version | seed)[:16]`, constructed with the `CONVENTIONS.md` §9 identifier scheme.
**Every inferred artifact is scoped to a `run_id`**; observed facts are scoped to
`dataset_version` and are never run-scoped. The per-execution identifier is `execution_id`:
random, present in logs, API correlation, and audit rows, and **excluded from every
determinism comparison** by `scripts/check_determinism.py`. `CONVENTIONS.md` §8 and §9 are
amended accordingly, citing this ADR. `correlation_id` is unchanged and remains
request-scoped.

### Consequences
**Positive:** "Same inputs implies same `run_id` implies byte-identical artifacts" becomes
a statement a test can assert. Inference cannot overwrite observation by construction,
because the two live in differently-scoped storage. Comparing two runs that differ in one
input isolates that input's effect.

**Negative:** Two governance sections are amended, so any prompt or session that memorized
the old §8/§9 wording is now wrong in a way that reads plausible. Two similar identifiers
now exist and will be confused; the log schema, the audit schema, and the envelope all
carry both. A content-addressed `run_id` also means re-running with the same inputs
*cannot* produce a distinguishable new run identity — deliberate, but it will surprise
someone expecting a fresh identifier per execution.

**Obligations created:** `CONVENTIONS.md` §8/§9 amendment; `execution_id` in the log
required-field list; `OutputEnvelope` carries both; `scripts/check_determinism.py`
normalizes `execution_id` and `correlation_id` explicitly rather than incidentally;
`GLOSSARY.md` defines `Run`, `run_id`, and `execution_id`.

### Reversibility cost
**Medium.** Reversing means re-keying every stored artifact and rewriting the envelope.

---

## ADR-0014 — Persistence is reached through ports declared in `core/`; only `orchestration` wires an adapter

- **Date:** 2026-08-23
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** all reasoning modules, all persistence
- **Affects interfaces:** `FactRepository`, `GraphProjection`, `DerivedCache`, `AuditSink`, `Clock`

### Context
ADR-0001 settles *which store is authoritative*. It does not settle *how a reasoning module
reaches a store*. `CONVENTIONS.md` §6 already forbids passing a database handle across a
module boundary and forbids the API reaching through to the graph store, but nothing yet
says what a module depends on instead. Without a ruling, each module imports a driver
directly, every module becomes untestable without a live database, and the two-store
boundary erodes one convenient import at a time.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Modules import drivers directly | Rejected. Every reasoning test needs PostgreSQL and Neo4j running; the store boundary is enforced by discipline only. |
| B | A shared `db` module every layer imports | Rejected. It becomes an upward-reaching god module and a cycle magnet. |
| C | **Ports declared in `core/ports/`, adapters in `persistence/`, wiring in `orchestration/`** | **Chosen.** Ports-and-adapters, with the boundary enforced by the layer lint (F4). |

### Decision
Every capability a reasoning package needs from infrastructure is declared as a `Protocol`
in `causalog.core.ports`. Concrete adapters live in `causalog.persistence.{postgres,neo4j,
redis}`. **Only `causalog.orchestration` may import `causalog.persistence`** — enforced as
forbidden edge F4 in `scripts/check_layers.py`. Reasoning packages depend on ports and are
handed an implementation; they never construct one, never import a driver, and never accept
a connection object across a boundary. Wall-clock access is a port too (`Clock`), because
`datetime.now()` inside a reasoning package is a determinism defect (`CONVENTIONS.md` §11).

### Consequences
**Positive:** Every reasoning module is testable with an in-memory fake and no running
service. The ADR-0001 store boundary becomes structural. Swapping a store is an adapter
change. The layer lint can enforce all of it.

**Negative:** Indirection: reading a query means opening the port, then the adapter, then
the SQL — three files where one would do. Ports are also a leaky abstraction for a graph
database, where the natural interface is a query language; expressing rich traversals
behind a narrow port will either bloat the port or push Cypher into strings that the port
cannot type-check. Expect pressure to widen `GraphProjection` over time, and expect that
pressure to be the early warning that the abstraction is wrong.

**Obligations created:** in-memory fakes for every port, living under `tests/`; a test that
flushing the `DerivedCache` changes latency but never an answer; `orchestration` is the
only wiring site and must stay thin.

### Reversibility cost
**Medium.** Collapsing to direct driver imports is mechanical but re-couples every module
to a live database, and every existing unit test would need a service.

---

## ADR-0015 — The pinned Version 1 dependency set

- **Date:** 2026-08-23
- **Status:** superseded by ADR-0024
- **Supersedes:** —
- **Affects modules:** all
- **Affects interfaces:** —

### Context
`CONVENTIONS.md` §12 requires an ADR **before** any third-party import is written, stating
for each dependency: what it solves that the standard library does not, whether it
introduces nondeterminism, whether it introduces domain assumptions, its license and
maintenance status, and its removal cost. prd.md §41 names a stack, but names it as a
wish-list — including `pgmpy` unqualified and `DoWhy`/`PyTorch Geometric` marked future.
ADR-0003 blocks the ML libraries for V1. This ADR is the single record covering everything
that is actually installed.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Install prd.md §41 in full | Rejected. `pgmpy` and `DoWhy` are blocked by ADR-0003; the visualization libraries have no module consuming them yet. |
| B | Standard library only | Rejected. Hand-rolling validation, an ASGI server, and three database drivers is a large surface with no benefit. |
| C | **A minimal pinned set, one ADR entry per package, ML libraries excluded** | **Chosen.** |

### Decision
The V1 dependency set is exactly the following, pinned to exact versions in
`backend/pyproject.toml`. No range, no `latest`. Adding to this list requires an ADR that
supersedes this one, and `scripts/check_dependency_policy.py` fails the build if
`pyproject.toml` and this ADR disagree.

| Package | Solves | Nondeterminism | Domain assumptions | License / removal cost |
|---|---|---|---|---|
| `pydantic` | The `CONVENTIONS.md` §12 "chosen data-validation library"; validate-on-entry at every boundary; frozen models give immutability | None | None | MIT; **high** removal cost — it is the base of every core type |
| `fastapi` | Module 16's HTTP surface with typed request/response models | None | None | MIT; medium — confined to `api/` |
| `uvicorn` | ASGI server for the backend container | None | None | BSD; low |
| `networkx` | Deterministic graph algorithms (prd.md §41): traversal, cycle detection, path enumeration | Iteration is insertion-sequenced; results are sorted before use per `CONVENTIONS.md` §11 | None | BSD; medium |
| `psycopg[binary]` | PostgreSQL driver for the system of record | None | None | LGPL; low — behind a port |
| `neo4j` | Bolt driver for the projection | None | None | Apache-2.0; low — behind a port |
| `redis` | Client for the derived cache | None | None | MIT; low — behind a port |
| `PyYAML` | Reads ontology and rule-pack data files | None | None | MIT; low |
| `ruff`, `mypy`, `pytest`, `pytest-cov` (dev) | Lint, strict typing, tests, coverage reporting | None | None | MIT/Apache; low |
| `hatchling` (build) | Builds the distribution | None | None | MIT; low |

**Not installed, deliberately:** `pgmpy`, `dowhy`, `torch`, `torch-geometric`,
`scikit-learn`, `tensorflow` (ADR-0003, prd.md §45 stages them at V2+); any ORM or
migration framework — migrations are numbered raw SQL, which `CONVENTIONS.md` §5's naming
rule already implies; any third-party import linter — the layer rules are project-specific
and are enforced by `scripts/check_layers.py` (ADR-0016); React Flow, Cytoscape.js, D3, and
Apache ECharts (ADR-0018).

The canonical ADR log is `DECISIONS.md`. There is no separate `docs/adr/` directory: it
would duplicate this file, and a duplicated record is a divergence waiting to happen.

### Consequences
**Positive:** A small, auditable surface. Every package has a stated reason and a stated
removal cost. The dependency check makes "someone quietly added a library" a build failure.

**Negative:** Exact pins mean security patches require a deliberate edit and an ADR review
rather than arriving automatically — an accepted maintenance burden, and one that will at
some point mean running a known-vulnerable pin for a few days. Raw SQL without a migration
framework means writing an apply-and-record runner by hand. `networkx` is pure Python and
will be the first thing to hit the prd.md §55 performance targets.

**Obligations created:** `scripts/check_dependency_policy.py` in CI; a superseding ADR for
every addition; a periodic pin review.

### Reversibility cost
**Low** per package for the leaf dependencies behind ports. **High** for `pydantic`, which
is the base class of every canonical type.

---

## ADR-0016 — Layer boundaries are enforced by a standard-library script, not a third-party import linter

- **Date:** 2026-08-23
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** all
- **Affects interfaces:** —

### Context
`CONVENTIONS.md` §6 states the dependency direction and forbids cross-layer reach-through,
but states it in prose. `docs/architecture.md` §1 turns it into eleven ranks and nine named
forbidden edges. Several of those edges are not expressible as a plain layer hierarchy: F3
restricts ontology consumption to three specific packages, F4 singles out `orchestration`,
F7 bans tabular libraries above a rank, and F8 caps `core`'s third-party surface at one
package.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | A third-party import linter | Rejected. Adds a dependency (ADR-0015), expresses layered contracts well but the value-specific edges (F7, F8, F9) awkwardly, and puts a law behind a package that a version bump can break or a configuration edit can quietly relax. |
| B | Code review only | Rejected. The same failure mode as an unenforced LAW-DOMAIN. |
| C | **A standard-library `ast` script encoding the rank table and F1–F9** | **Chosen.** No dependency, exact rules, error messages that name the rule and explain the reason. |

### Decision
`scripts/check_layers.py` parses every module in the distribution with `ast`, attributes
each import to a package, and fails the build on any of the forbidden edges F1–F9 defined
in `docs/architecture.md` §1.4. It uses only the standard library. The rank table in the
script is the machine-readable copy of the architecture document's table; a divergence
between them is a defect, and `make lint` is where it surfaces.

### Consequences
**Positive:** No law depends on a third-party package. Every violation message names the
rule identifier and states *why* the edge is forbidden, which is what makes a lint teach
rather than merely block. New rules are added as plain code.

**Negative:** We now own a linter, including its edge cases — conditional imports, imports
inside functions, `importlib` and other dynamic resolution, and re-exports are all
invisible to it, so a determined violation can slip through. A mature third-party tool
would handle some of these. The rank table also exists in two places (script and document)
and must be kept in step by hand.

**Obligations created:** the script runs as a required CI job; a negative test that plants a
forbidden import and asserts the script fails; the architecture document's table stays in
step with the script's.

### Reversibility cost
**Low.** Adopting a third-party linter later means translating one table and nine rules.

---

## ADR-0017 — The PRD moves to `docs/prd.md`

- **Date:** 2026-08-23
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** —
- **Affects interfaces:** —

### Context
`CONTEXT.md` §0 and `HANDOFF.md` §1 both instruct every new session to read `docs/prd.md`.
The file was at `./prd.md`. `CONTEXT.md` OQ-010 records the consequence: a failed read at
the start of every session, and two live readings of where the PRD is. Low cost, but it
recurs every single session, and both files already carry a parenthetical correction —
which is the shape of a defect that has been documented instead of fixed.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Keep `./prd.md`; amend the ritual text in both files | Viable. Rejected because `docs/` now also holds `architecture.md`, and intent documents belong together while the root holds the governance files read at every session start. |
| B | **Move the file to `docs/prd.md`; the ritual text becomes correct as written** | **Chosen.** One move; three references stop being wrong. |
| C | Leave both readings live | Rejected. `HANDOFF.md` §4.4 lists exactly this as an unacceptable resolution. |

### Decision
`prd.md` moves to `docs/prd.md`. The session ritual in `CONTEXT.md` §0 and `HANDOFF.md` §1
is correct as written and its parenthetical correction is removed. `docs/` holds intent
documents (`prd.md`, `architecture.md`); the repository root holds the governance files
read at the start of every session. OQ-010 is closed.

### Consequences
**Positive:** The ritual is executable verbatim. Intent documents sit together.

**Negative:** Every existing link or bookmark to `./prd.md` breaks, and any prompt or
transcript that hardcodes the old path silently fails to read the file — the same class of
failure this ADR is fixing, just pointed the other way for anyone holding an old reference.

**Obligations created:** update the two ritual references and the `CONTEXT.md` §0 file
location note; `CONTEXT.md` §11 changelog line.

### Reversibility cost
**Low.**

---

## ADR-0018 — Frontend visualization libraries are deferred until a module consumes them

- **Date:** 2026-08-23
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Visualization API, frontend
- **Affects interfaces:** HTTP API

### Context
prd.md §41 names React Flow, Cytoscape.js, D3.js, and Apache ECharts for the frontend. No
module consumes them: module 16 is not started and no workspace exists.
`CONVENTIONS.md` §12 requires an ADR before an import is written and forbids adding a
dependency to satisfy a deferred item. Installing four visualization libraries now would
mean four unjustified dependencies, four upgrade obligations, and four choices made before
the data they render has a shape.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Install all four now | Rejected. Nothing consumes them; §12 forbids it; the choice between React Flow and Cytoscape depends on the graph payload shape, which module 16 defines. |
| B | Pick one graph library now and commit | Rejected. Same objection, one quarter the size. The two libraries have different strengths and the deciding factor — expected node counts and interaction model — is not known yet. |
| C | **Install none; the frontend ships Next.js, React, TypeScript, ESLint, and Prettier only** | **Chosen.** |

### Decision
The frontend's dependency set is `next`, `react`, `react-dom`, `typescript`, `eslint`,
`eslint-config-next`, `@eslint/eslintrc`, `prettier`, and the three `@types/*` packages,
pinned exactly. (`@eslint/eslintrc` is present because `eslint-config-next` still ships
eslintrc-style configuration and ESLint 9 flat config reaches it through `FlatCompat` —
Next.js's own documented bridge.) The prd.md §41 visualization
libraries are **not** installed. They are selected and added by a superseding ADR when
module 16 defines the graph and timeline payload shapes, at which point the choice can be
made against a real payload rather than a guess.

### Consequences
**Positive:** No unjustified dependency, no premature commitment, no upgrade obligation for
code that does not exist. The library choice is made with the payload in hand.

**Negative:** Frontend work cannot begin on real graph rendering until that ADR is written,
so there is a period where the UI is a shell — which will look like a gap to anyone reading
prd.md §51 and expecting six workspaces. Deferring also risks discovering late that the
chosen library constrains the payload shape module 16 already froze.

**Obligations created:** a superseding ADR at module 16; `frontend/README.md` states the
deferral so the absence reads as a decision rather than an oversight.

### Reversibility cost
**Low.**

---

## ADR-0019 — LAW-DOMAIN matches banned concepts by stem, not by whole word

- **Date:** 2026-08-23
- **Status:** accepted
- **Supersedes:** ADR-0010
- **Affects modules:** all
- **Affects interfaces:** none

### Context
ADR-0010 specified word-boundary (`\b`) matching for the LAW-DOMAIN lint, and
`CONVENTIONS.md` §6 restated it. Review found the implementation catches almost nothing.

`\b` requires a non-word character on each side of the token, and `_` **is** a word
character. So `warehouse_id`, `order_id`, `customer_name`, `WAREHOUSE_TABLE`, `orders`,
`shipments`, `customers`, and `OrderId` all passed clean. Those are the forms domain
vocabulary actually takes in code. The lint caught essentially only the bare English word
in a comment — the one form domain vocabulary almost never takes.

Two aggravating factors made this survive review:

1. **The stated rationale named the wrong mechanism.** The code comment claimed the
   underscore behaviour was the safeguard — "`\b` treats `_` as a word character, so
   `reorder_key` does not match". `reorder_key` is excluded by the `re` **prefix**, not by
   the underscore. The underscore behaviour was the hole, documented as the feature.
2. **The self-test certified the hole.** ADR-0010's own obligation was a `--self-test`
   proving the false-positive surface closed. That test listed `shipments` and
   `customers_table_in_a_name` among the words that must **never** fire. Both are domain
   vocabulary. The control designed to prevent exactly this failure was asserting the
   wrong invariant, so a green build was evidence of nothing.

`CONTEXT.md` R-10 read "in force as of 2026-08-23" throughout. It was not in force.
Classified Class C under `HANDOFF.md` §4.2 — the code did exactly what the specification
said; the specification was wrong — and filed as DEF-0001.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Keep `\b`; rely on review to catch identifier forms | Rejected. That is convention-only enforcement, which is the precise failure ADR-0010 existed to prevent. |
| B | Naive substring matching | Rejected. This is the original problem: it fires on `reorder`, `recorder`, `border`, `ordinal`, and a lint that cries wolf gets disabled. |
| C | Suffix rules on the `order` stem — allow `-ing`/`-ed`, ban `-s`/`-_`/`-Id` | Rejected. The most matcher logic and the largest escape surface, in a component whose defining failure was a subtle escape nobody noticed. Preserving one word's convenience is not worth reintroducing that class of bug. |
| D | Stem-prefix matching with a global allowlist of non-domain forms | Rejected for now. Every allowlist entry is a documented hole, and `ordered items` / `order by customer` both read domain-ish. The per-path allowlist already covers genuine exceptions with review attached. |
| E | **Stem-prefix matching with a letter-only lookbehind and no suffix exceptions** | **Chosen.** |

### Decision
The lint matches **stems**, truncated to each banned concept's invariant root —
`warehous`, `shipment`, `order`, `carrier`, `customer`, `deliver`, `inventor` — using:

```
(?<![A-Za-z])(<stem>|...)[A-Za-z0-9_]*     case-insensitive
```

The lookbehind is `[A-Za-z]` and deliberately **not** `\w`: a preceding *letter* means the
stem sits inside a longer word (`reorder`, `recorder`, `border`) and is not domain
vocabulary, while a preceding underscore or digit means it is a separate identifier
component (`sort_order`, `v2_customer`) and is. The tail spans the whole identifier so the
reported text — and therefore the allowlist key — is `warehouse_id`, not `warehouse`.

**There are no suffix exceptions.** The whole `order` stem is banned, so `ordering` and
`ordered` are unusable in a reasoning package including in its comments; write "sequence",
"sequenced", or "sorted". Allowlist entries key on the **exact reported text** and exempt
one occurrence, never a family.

The self-test is replaced by two explicit tables — `MUST_FIRE` (every form vocabulary takes
in code, including the four review probes verbatim) and `MUST_NOT_FIRE` — plus a guard that
**refuses a `MUST_NOT_FIRE` entry which actually contains a banned stem**. The guard uses an
independent strict stem search, so weakening the matcher cannot make a poisoned entry look
correct. This makes the DEF-0001 root cause structurally uncommittable.

Separately, this ADR **corrects the clause in ADR-0002's Decision paragraph** reading
"enforced by a CI lint job using word-boundary matching with an explicit allowlist" to read
stem matching. ADR-0002 is **not** superseded: its substance is the ontology-layer strategy,
which is unaffected and remains binding.

Finally, and generalising beyond LAW-DOMAIN: **every enforcement script must be observed to
reject, not merely to pass.** The four law scripts existing at the time of this ADR ship
`--self-test` asserting both directions, and each CI job runs it before its scan. The rule
is general and binds every enforcement script added afterwards; `CONVENTIONS.md` §6 holds
the current inventory.

### Consequences
**Positive:** The lint now catches the forms domain vocabulary actually takes — plural,
`snake_case`, `SCREAMING_SNAKE`, `camelCase`, `PascalCase`. The four review probes are
regression cases. Stems cover inflections without enumeration. The re-poisoning guard means
the specific failure that produced DEF-0001 cannot recur silently. Every law check now
proves itself in its own CI log.

**Negative:** `ordering` and `ordered` are now build failures in reasoning packages, which
directly contradicts ADR-0010's own advice to prefer them; three lines were reworded and
future authors will hit this. A SQL or Cypher `ORDER BY` literal in an in-scope file now
requires an allowlist entry, and `CONVENTIONS.md` §11 mandates `ORDER BY` on every pipeline
query — so that entry is a matter of when, not if. Truncated stems over-reach slightly:
`deliver` also matches `deliverable` and `delivered`, `inventor` also matches `inventor`.
The lint is now stricter than the law strictly requires, and that asymmetry is deliberate —
a false positive costs a reworded line, a false negative costs the law.

**Still not caught, and stated plainly:** domain dependence expressed as a branch on a data
*value* rather than as vocabulary; and any file type outside `.py`, `.md`, `.sql`,
`.cypher`. Neither is a matcher problem and neither is fixed here.

**Obligations created:** the two-table self-test with its re-poisoning guard; the four
review probes as permanent regression cases; `--self-test` on every law script — four when
this was written — and in every one of their CI jobs; negative pytest cases for the law-copy and dependency-policy checks;
`CONVENTIONS.md` §6, `CONTEXT.md` R-10 and OQ-006, and `docs/architecture.md` §1.5 restated.

### Reversibility cost
**Low** for the matcher. **High** for what it protects — see ADR-0002. The four reworded
lines are the entire migration cost of this change.

---

## ADR-0007 — LAW-TIME is evaluated over intervals, and temporal ambiguity is retained rather than resolved

- **Date:** 2026-08-23
- **Status:** superseded by ADR-0021
- **Supersedes:** —
- **Affects modules:** Event Generator, Timeline Builder, Candidate Cause Generator, Confidence Scorer, Propagation Analyzer
- **Affects interfaces:** `Event`, `TimeInterval`, `CandidateEdge`

### Context
LAW-TIME forbids any causal edge where `cause.timestamp >= effect.timestamp`, and prd.md
§23 states the constraint as a strict inequality over point instants: "Cause Timestamp <
Effect Timestamp". The DataCo dataset is day-granularity in places, so a cause and its
effect recorded on the same day is the common case, not an edge case.

Under point semantics there are only two ways to handle a tie and both are wrong. Strict
`<` discards every same-day edge, including the true ones — mass loss of real causality,
invisible to the user. Loose `<=` admits every same-day pair, including the reversed ones —
mass admission of false causality, equally invisible. Either choice invalidates root-cause
output, which is the product's headline (CONTEXT.md OQ-002, R-01).

The deeper problem is that a point timestamp cannot express what the data actually says. The
source does not assert "this happened at 00:00:00 on the 14th"; it asserts "this happened on
the 14th". Forcing that into a point manufactures precision the record never had, and every
downstream comparison then reasons over a fact nobody observed.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Strict `<` on point timestamps | Rejected. Silently discards every same-day edge. The graph shrinks and nothing reports that it did. |
| B | Loose `<=` on point timestamps | Rejected. Admits reversed edges as readily as real ones, and LAW-TIME becomes decorative. |
| C | Impute a time-of-day (sequence within the day, business-hours heuristic, process ordering) | Rejected, emphatically. Imputation manufactures causality out of nothing (`CONVENTIONS.md` §10). An imputed ordering would then be *indistinguishable* from an observed one in every downstream computation. |
| D | Discard day-granularity records at ingestion | Rejected. Discards most of the dataset to protect a representation choice, and the reject counter would report a data-quality problem the data does not have. |
| E | **Interval timestamps plus a three-valued temporal test that retains ambiguity** | **Chosen.** |

### Decision
Every event timestamp is a `TimeInterval` — `[t_earliest, t_latest]` with a `precision` tag
and its own provenance (`CONVENTIONS.md` §10). A day-granularity record yields an interval
spanning the day; it is never collapsed to a point.

LAW-TIME is evaluated as a **three-valued** test, declared as `TemporalVerdict` in
`causalog.core.temporal`:

| Condition | Verdict | Effect on the edge |
|---|---|---|
| `cause.t_latest < effect.t_earliest` | `CERTAIN` | Temporally admissible; may be promoted to `INFERRED`. |
| `cause.t_earliest >= effect.t_latest` | `VIOLATION` | Rejected. The edge is never created. |
| the intervals overlap | `UNDETERMINED` | Retained as a `CandidateEdge`, flagged, and **blocked from promotion to `INFERRED`**. |

`UNDETERMINED` is **retained, not discarded**. That is the whole point of the decision: a
temporal ambiguity is a fact about the data, and hiding it by dropping the edge would make a
data-quality problem look like an absence of causality. An `UNDETERMINED` edge is visible,
countable, and inspectable — it simply may not be asserted as inferred causality.

Two consequences that follow and are binding: an event whose `precision` is `UNKNOWN` may
appear on a timeline but may **never** participate in an `INFERRED` edge; and **imputation
remains forbidden everywhere** — not `now()`, not epoch, not the previous event's time, not
the median.

### Consequences
**Positive:** The representation matches what the source actually asserts, so no downstream
computation reasons over invented precision. LAW-TIME becomes decidable rather than
arbitrary on ties. Temporal ambiguity is surfaced instead of silently resolved in either
direction, which is the honest treatment of R-01. The rule is uniform across domains — a
second-precision dataset simply produces more `CERTAIN` verdicts with no code change.

**Negative, and this one is serious:** on a day-granularity dataset `UNDETERMINED` may
**dominate**. If most candidate edges are unpromotable, the causal graph is thin and the
product's headline output is correspondingly thin — and no amount of engineering fixes that,
because the ordering information is not in the data. This ADR chooses to make that visible
rather than to manufacture a graph that looks fuller than the evidence supports. Interval
arithmetic is also more expensive and more error-prone than point comparison, every duration
carries bounds rather than a value (`DurationBound`), and three-valued logic is harder to
reason about than two-valued — a contributor who thinks in `<` will write subtly wrong code.

**Obligations created:** every run summary reports the `CERTAIN` / `UNDETERMINED` /
`VIOLATION` counts and their ratio; a run where `UNDETERMINED` dominates is reported as a
**finding about the dataset**, never tuned away by loosening the test; `tests/law/` asserts
no `INFERRED` edge exists with a non-`CERTAIN` verdict; `tests/law/` asserts no
`UNKNOWN`-precision event participates in an `INFERRED` edge; the UI distinguishes an
`UNDETERMINED` edge from a `CERTAIN` one visually.

### Reversibility cost
**High.** The interval representation is on `Event`, which every module downstream consumes.
Reverting to point timestamps means rewriting every temporal comparison, every duration, and
re-deriving precision that would no longer be recorded.

---

## ADR-0008 — Root cause is reported as two distinct fields, and actionability is ontology-declared

- **Date:** 2026-08-23
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Event Generator, Root Cause Analyzer, Intervention Optimizer, Explanation Generator, Visualization API
- **Affects interfaces:** `Event`, `OntologySpec`, `RootCauseRanking`

### Context
prd.md defines root cause twice, and the definitions disagree:

- §12 — "The earliest actionable event whose modification **could prevent downstream
  consequences**."
- §29 — "The earliest actionable event whose modification **would prevent the largest amount
  of downstream impact**."

§29 then resolves its own ambiguity with an example, and the example is the decisive text:

> Storm → Traffic → Late Dispatch → Customer Complaint. "The storm may be earliest. Late
> Dispatch may be actionable. **The system should distinguish both.**"

Earliest and largest-impact-actionable are different events, and the PRD says so. Without a
ruling, the product's headline output means two different things to two modules and the
explanation contradicts the ranking (CONTEXT.md OQ-003).

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Adopt §12 — earliest actionable event | Rejected. "Could prevent downstream consequences" is satisfied by almost any upstream event; it does not rank, so it cannot produce the ranked output prd.md §29 and §50 require. |
| B | Adopt §29 and return a single ranked list | Rejected. Discards the structural head of the chain, which is exactly what §29's example says the system should still distinguish. A user asking "where did this start?" gets an answer to a different question. |
| C | Blend earliness and impact into one score | Rejected. The two are not commensurable, the weighting would be an unexplainable magic constant, and LAW-EVIDENCE forbids a number whose components cannot be inspected. |
| D | **Adopt §29 for ranking, and return `earliest_cause` and `actionable_root_causes` as two fields that are never blended** | **Chosen.** It is what §29's example literally asks for. |

### Decision
`RootCauseRanking` carries **two distinct fields**:

- `earliest_cause` — structural. The head of the causal chain, whether or not anyone can act
  on it. This is the answer to "where did this start?"
- `actionable_root_causes` — a **ranked list**, sorted by impact-averted × confidence, ties
  broken by earliness. This is the answer to "what should we change?"

They are never collapsed into a single "the root cause is X". A module, API response, or UI
that presents one number or one event as *the* root cause is a defect.

**Actionability is ontology-declared, and is stamped onto the event at generation time.**
§29's criterion turns on whether an event is actionable, and "a storm is not actionable, a
dispatch is" is domain knowledge. The Root Cause Analyzer is L6, and forbidden edge F3
(`docs/architecture.md` §1.4) forbids any package at L4–L10 from reading the ontology — so
actionability cannot be looked up where it is used. Therefore:

1. The ontology declares an `actionable` flag per event type, alongside the ordinal cost
   bands, as configuration — **never inferred** (the OQ-013 treatment, for the same reason).
2. `OntologySpec` exposes `event_type_is_actionable(event_type)`.
3. The **Event Generator** (L3, which may read the ontology) stamps `is_actionable` onto
   each `Event` with provenance `ASSUMED`.
4. The Root Cause Analyzer reads a field on a canonical type. It never learns that an
   ontology exists.

The alternative — orchestration injecting an actionability map into L6 at runtime — was
rejected because it keeps domain-derived data flowing into a reasoning package, whereas the
architecture's consistent approach is to bake every ontology decision into the canonical
types at L2/L3 and let the reasoning core see only `Event`, `Entity`, `State`, `Transition`,
`Relationship`.

### Consequences
**Positive:** The product's headline output has exactly one meaning. §29's storm example is
answerable as §29 says it should be. The Explanation Generator can say "this began with X;
the thing you can change is Y" — two sentences, both traceable. Domain independence survives
a criterion that is inherently domain-flavoured, and the mechanism is the one already used
for cost. A new domain declares actionability in a data file, not in code.

**Negative:** A **mis-declared `actionable` flag silently changes the headline ranking, and
nothing in the system can detect it** — the same failure class as a fabricated cost under
OQ-013, and equally unfalsifiable, because there is no ground truth for "should this have
been actionable". Actionability is also modelled per event *type*, which is coarser than
reality: the same event type may be actionable in one context and not another, and V1 cannot
express that. Two fields also mean two things for the UI to explain without the user reading
them as competing answers, and a user who wants one answer will pick whichever field suits
them. Adding `is_actionable` widens `Event`, which is already the most-consumed type.

**Obligations created:** the ontology schema carries `actionable` per event type, and a
missing declaration is a hard error rather than a default (`CONVENTIONS.md` §7); the flag is
provenance `ASSUMED` and surfaced in explanations, never silently applied;
`tests/law/` asserts `earliest_cause` and `actionable_root_causes` are never merged;
`tests/ontology/` asserts flipping the flag changes the ranking with no code change; the API
contract and the UI present both fields distinctly.

### Reversibility cost
**Medium.** The two-field shape is confined to `RootCauseRanking` and its consumers.
Removing `is_actionable` from `Event` is harder — it is a field on the central type — and
re-deriving actionability after the fact would require the ontology version that produced
each run.

---

## ADR-0020 — `Trigger` is a property of one event; `Cause` is a relation between two

- **Date:** 2026-08-23
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Event Generator, Candidate Cause Generator, Confidence Scorer, Explanation Generator
- **Affects interfaces:** `Event`, `CandidateEdge`

### Context
prd.md §20 makes `Trigger` a **required** field on every `Event` and never defines it
anywhere in the document. prd.md §12 defines `Cause` as "an event contributing to another
event". Read together, the two read as the same idea expressed twice, and there is no text
that says which is which.

That is a cross-session hazard of exactly the kind this project is structured to prevent:
one session populates `trigger` with the identifier of an upstream event, another populates
it with a mechanism string, a third starts reading it to draw edges — and the graph then
contains causal claims nobody inferred and nothing scored (CONTEXT.md OQ-012).

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Treat `Trigger` as a synonym for `Cause` and drop the field | Rejected. prd.md §20 requires it, and the record genuinely carries information about *why this event occurred* that is distinct from any inter-event relation. Dropping it loses observed evidence. |
| B | `Trigger` holds the id of the causing event | **Rejected, and this is the dangerous option.** It puts an inter-event causal claim in an `OBSERVED` field, so a relation nobody inferred, scored, or temporally checked would enter the graph — a LAW-PROVENANCE and LAW-TIME violation by construction, wearing the costume of a fact. |
| C | **`Trigger` is the proximate mechanism recorded on the event; `Cause` is an inferred edge between events** | **Chosen.** Ratifies `GLOSSARY.md` §2.1. |

### Decision
A **Trigger** is the proximate mechanism recorded *on* a single event: intrinsic to that
event, sourced from the record, provenance `OBSERVED`, carried as an ontology concept string.
It answers "what was the immediate occasion of this event, as observed?"

A **Cause** is an inferred edge *between* two events, produced by the Candidate Cause
Generator and scored by the Confidence Scorer, provenance `INFERRED`.

The operative test for any author, stated so a violation is detectable by reading code: **if
you are populating a field on an `Event`, you mean trigger; if you are drawing an edge, you
mean cause.**

**No module may read `Event.trigger` to create, filter, or score a `CandidateEdge`.** Trigger
is evidence a human reads and an explanation may quote; it is not an input to inference. The
moment inference consumes it, an `OBSERVED` field has become a causal assertion that skipped
the LAW-TIME gate and the LAW-EVIDENCE gate at once.

### Consequences
**Positive:** Two fields that read alike now have a one-sentence test that distinguishes
them, so sessions cannot populate them inconsistently. Observed mechanism and inferred
causality stay in separate provenance classes, which is LAW-PROVENANCE working as intended.
Explanations gain a genuinely useful observed detail to quote without it being mistaken for a
causal claim.

**Negative:** The distinction is subtle and will be got wrong at least once, because "the
trigger of this event" reads in ordinary English as "the cause of this event" — the ADR is
fighting the natural meaning of the word, and losing that fight is a silent defect rather
than a loud one. Forbidding inference from reading `trigger` also discards genuinely
informative signal: a recorded mechanism is often the best available evidence about causality,
and V1 deliberately does not use it. That is a real cost paid for provenance integrity, and
a future ADR may revisit it — but only by promoting the signal through the scoring path as a
named `ConfidenceVector` component, never by reading the field directly.

**Obligations created:** `GLOSSARY.md` §2.1 is the canonical statement and stays in step;
`tests/law/` asserts no causal-engine code path references `Event.trigger` — checkable
statically now because no implementation exists, and **must be re-asserted when module 9 is
written**; the Event Generator validates `trigger` against the ontology's mechanism
vocabulary rather than accepting free text.

### Reversibility cost
**Low** for the definition. **High** for the data: a corpus in which `trigger` was populated
with event identifiers cannot be distinguished after the fact from one populated with
mechanisms, so the cost of getting this wrong is paid at correction time, not now.

---

## ADR-0009 — Confidence is a decomposition with a named, pluggable aggregation function

- **Date:** 2026-08-25
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Confidence Scorer, Event Generator, Root Cause Analyzer, Propagation Analyzer, Recommendation Engine, Explanation Generator
- **Affects interfaces:** `ConfidenceVector`, `ConfidenceComponent`, `Event`, `CausalEdge`, `Aggregator`

### Context
OQ-005, open since the scaffold. prd.md §28 makes confidence "a 0–1 float"; prd.md §49
requires seven named components and states that "Confidence should never be represented by
a single unexplained number"; LAW-EVIDENCE hardens that to "a bare float is a defect". The
three cannot all be satisfied by one field. prd.md §20 compounds it by putting `Confidence`
on `Event` itself, conflating *was this event correctly extracted* with *did this event
occur*, the second of which is already answered by `provenance_class`.

`core/types/confidence.py` shipped `ConfidenceVector` at the scaffold as OQ-005's proposed
default, with `scalar` documented as derived and non-authoritative — but nothing said which
function produced the scalar, so a consumer could not recompute it, and "derived" was a
claim rather than a checkable property. `docs/architecture.md` §2 records the rollup as
"OQ-005 default in use, pending ADR-0009". This is that ADR. Module 10 may not be built
until it exists, and `confidence_schema_version` cannot leave `unset` without it.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Keep the scalar, leave the function implicit | Rejected. It is exactly the unexplained number prd.md §49 forbids: two modules could roll up differently and nothing would detect the disagreement. |
| B | Drop the scalar; expose components only | Rejected. Ranking needs a total precedence over candidates, and every consumer would then invent its own rollup — the same divergence, pushed outward where it cannot be governed. |
| C | One hard-coded aggregation formula | Rejected. There is no causal ground truth in this dataset to justify any particular formula, so freezing one as *the* answer overstates what is known. |
| D | **Named, registered aggregators; the name travels with the data; weakest-provenance rule separate from the arithmetic** | **Chosen.** The rollup stays available and stays arguable. |

### Decision
Confidence is a `ConfidenceVector`: a non-empty tuple of named `ConfidenceComponent`s
sequenced by `component_name`, a derived `scalar`, the `aggregation` name that produced the
scalar, and a `provenance_class`.

An aggregator is a pure function from components to a scalar in `[0.0, 1.0]`, registered by
name in `causalog.core.aggregation.AGGREGATORS`. Two ship: `weighted_mean_v1`, the default,
which renormalizes declared weights over the components actually present so an absent
component abstains rather than scoring zero; and `minimum_v1`, name-agnostic and
conservative. The declared weights live in one module-level table, `DEFAULT_COMPONENT_WEIGHTS`,
and are an editorial judgement stated openly rather than a measurement.

`weighted_mean_v1` refuses a component name it has no weight for. The component names are
part of `confidence_schema_version`; guessing a weight would let a schema change pass
silently and shift every score in the system.

**The provenance class of a vector is the weakest class among its components (ADR-0005),
computed by `causalog.core.provenance.combine` and never by the aggregator.** The scalar and
the provenance answer different questions, and a high scalar over `ASSUMED` inputs is still
`ASSUMED`.

`Event.extraction_confidence: float` is replaced by `Event.confidence: ConfidenceVector`.
OQ-005's proposed default kept the scalar under a clearer name; that is rejected here.
LAW-EVIDENCE says a bare float is a defect without exempting the event, and the reason it
holds on an edge — a number nobody can decompose is a number nobody can check — holds
identically on an extraction.

### Consequences
**Positive:** Every confidence figure can be recomputed from the artifact alone and
disagreed with. Adding an aggregator is additive. The weights are in one findable place, so
the judgement is arguable rather than buried in a scoring loop.

**Negative:** Every event now carries a full vector where it carried one float, which is a
real storage and payload cost on the largest table in the system for a value most consumers
will only read as a scalar. The declared weights are not derived from anything and cannot
be validated against this dataset, so they are an assertion wearing the shape of a
measurement — the mitigation is that they are visible, not that they are right. And
`weighted_mean_v1` refusing unknown names makes introducing a component a two-part change
(new name plus new aggregator version), which will be experienced as friction long before
it is experienced as safety.

**Obligations created:** `confidence_schema_version` moves to `1.0.0` in `CONTEXT.md` §7 and
the component name set is part of it; `tests/unit/core/test_confidence_aggregation.py`
asserts the range, sequence, and weakest-provenance properties; `docs/architecture.md` §2's
"pending ADR-0009" note is now satisfied; the Explanation Generator must surface the
aggregation name alongside any scalar it displays.

### Reversibility cost
**Low** to add an aggregator or change the default. **Medium** to change what an existing
`_v1` name computes — that is a `confidence_schema_version` bump and a re-scoring of every
stored vector, which is why the shipped names carry the suffix. **High** to remove the
scalar entirely, which would touch every ranking and every UI surface.

---

## ADR-0021 — A timestamp interval may be INFERRED, and always names its source

- **Date:** 2026-08-25
- **Status:** accepted
- **Supersedes:** ADR-0007
- **Affects modules:** Event Generator, Timeline Builder, State Engine, Candidate Cause Generator
- **Affects interfaces:** `TimeInterval`, `Event`, `State`, `Relationship`, `CausalEdge`

### Context
ADR-0007 established interval timestamps and the three-valued `TemporalVerdict`, and
restricted `TimeInterval.provenance` to `OBSERVED | ASSUMED`. That restriction was correct
about the danger — `CONVENTIONS.md` §10's "Never impute" exists because a manufactured
instant manufactures causality — but it conflates two operations that are not alike.

Narrowing bounds from other evidence is not imputation. If a state is known to have begun
before an event that is itself placed, the state's window can be legitimately tightened, and
the result is *more* honest than the wide window it replaces. Under ADR-0007 such a bound
had to be labelled `ASSUMED`, which is the class for configuration and process constraints,
and so became indistinguishable from a value somebody typed into a config file.

ADR-0007 also left the interval unable to say where it came from. `CONVENTIONS.md` §10 puts
the source *timezone* on the `EvidenceRecord`, which is right, but nothing recorded the
*derivation*, so tracing a bound meant finding and reading the module that produced it.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Do nothing; keep `OBSERVED \| ASSUMED` | Rejected. Derived bounds are mislabelled as configuration, and the distinction that matters most for LAW-TIME is the one the field cannot express. |
| B | Add `INFERRED`, unrestricted | Rejected. An unrestricted `INFERRED` timestamp with `EXACT` precision is imputation with a nicer label, and it would let one inference certify another. |
| C | **Add `INFERRED` with two guards: never `EXACT`, and never `CERTAIN`; add a required `source` field** | **Chosen.** |
| D | Model the four timestamp kinds as a discriminated union | Rejected for now. It matches the vocabulary more directly but supersedes `CONVENTIONS.md` §10's storage shape and touches every consumer, for a gain that a derived `kind` property already delivers. |

### Decision
`TimeInterval.provenance` admits `OBSERVED | ASSUMED | INFERRED`, declared as
`TIMESTAMP_PROVENANCE_CLASSES`. `STATISTICAL` and `SIMULATED` remain inadmissible: a
timestamp drawn from a frequency distribution or invented inside a hypothetical world is
imputation, whatever it is called.

Two guards make `INFERRED` safe, both enforced in `TimeInterval`'s validator:

1. **An `INFERRED` interval may never carry `EXACT` precision.** Narrowing a window is
   admissible; collapsing it to a point instant is manufacturing one.
2. **An `INFERRED` interval never yields a `CERTAIN` verdict.** `causalog.core.temporal.verdict`
   returns `UNDETERMINED` for any pair involving one. Without this, an inference could be
   promoted on the strength of bounds that were themselves inferred, with no observation
   anywhere underneath the chain.

`TimeInterval` gains a required non-empty `source`: the derivation or locator that produced
these bounds. It is excluded from the content-addressed payload — how a bound was obtained
is not which moment is being described — while the bounds themselves participate, so
narrowing an interval correctly mints a new identifier.

`TimestampKind` (`EXACT | INTERVAL | INFERRED | UNKNOWN`) is exposed as a **derived
property** of precision and provenance, never a stored field, so it cannot contradict them.

Everything else in ADR-0007 stands unchanged and is restated here rather than left dangling:
intervals over point instants, the three-valued verdict, `UNDETERMINED` retained rather than
discarded, `UNKNOWN` precision implying `ASSUMED` provenance and unbounded bounds, and no
`UNKNOWN`-precision event participating in an `INFERRED` edge.

### Consequences
**Positive:** A derived bound is now distinguishable from a configured one, which is the
distinction LAW-PROVENANCE exists to preserve. Every interval says where it came from
without a reader having to find the producing module.

**Negative:** This reopens a door ADR-0007 deliberately shut, and the guard is a validator
plus a docstring rather than a proof. Nothing structurally prevents a module from labelling
a guessed window `INFERRED` with a plausible `source` string; the two guards bound the
damage but do not prevent the mislabelling, and no test can detect it because there is no
ground truth to check the bound against. `source` is also free text, so it will drift toward
uninformative values unless review holds the line. Adding a required field to `TimeInterval`
is a breaking change to every construction site — cheap now, when there are no persisted
artifacts, and the reason this ADR is written before module 4 rather than after.

**Obligations created:** `CONVENTIONS.md` §10's `TimeInterval` specification is updated in
the same commit; `tests/unit/core/test_temporal_comparison.py` asserts that an `INFERRED`
interval never yields `CERTAIN`; risk R-01's mitigation text in `CONTEXT.md` §9 stays
accurate; any module producing an `INFERRED` interval states its derivation in `source`.

### Reversibility cost
**Medium.** Removing `INFERRED` means reclassifying every interval that carries it and
re-deriving every verdict that depended on those bounds. Removing `source` is mechanical but
touches every construction site.

---

## ADR-0022 — The causal edge taxonomy is five payload types, not one labelled edge

- **Date:** 2026-08-25
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Candidate Cause Generator, Confidence Scorer, Propagation Analyzer, Counterfactual Simulator, Explanation Generator, Temporal Graph Builder
- **Affects interfaces:** `CausalEdge`, `CausalEdgeKind`, `CausalEdgePayload`, `CandidateEdge`

### Context
prd.md §26 names five edge categories — DIRECT, CONDITIONAL, CONTRIBUTING, AMPLIFYING,
INHIBITING — in one sentence each, and specifies no payload for any of them. prd.md §25's
seven-field edge shape is the only structure given and applies to all five uniformly.
`GLOSSARY.md` sharpens the meanings with negative definitions but names no fields either.

That is not enough to build on. A `CONDITIONAL` edge without its condition cannot be
evaluated, a `CONTRIBUTING` edge without its group cannot be reassembled into the joint
cause it belongs to, and an `AMPLIFYING` edge without a magnitude carries no effect to
propagate. Worse, `edge_type` participates in the `edg` content address (`CONVENTIONS.md`
§9) and in the canonical edge sort key (§11), so the set of admissible values is
load-bearing for determinism and was undefined.

There is a second, quieter gap: prd.md §47's graph relationship types include `AMPLIFIES`,
`REDUCES`, and `BLOCKS` but have no `CONDITIONAL` or `CONTRIBUTING`, so the taxonomy and the
graph vocabulary do not correspond one to one.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | One `CausalEdge` with `edge_kind: str` and optional fields for everything | Rejected. Every consumer must re-check which fields are meaningful, and an edge missing its required data constructs cleanly and fails far downstream where the cause is no longer visible. |
| B | Five unrelated edge classes | Rejected. Propagation, ranking, and serialization all want one type to hold; five sibling types push the union into every signature. |
| C | **One `CausalEdge` holding a discriminated union of five payload types** | **Chosen.** The required data is required by the type; the edge stays one thing. |

### Decision
`CausalEdgeKind` is the closed set `DIRECT | CONDITIONAL | CONTRIBUTING | AMPLIFYING |
INHIBITING`. Each has a frozen payload type carrying exactly what it requires:

| Kind | Payload | Constraint |
|---|---|---|
| `DirectCause` | *(no fields)* | The absence of extra data is the claim. |
| `ConditionalCause` | `condition_expression`, `condition_holds` | Expression non-empty and exactly as evaluated; a paraphrase is not re-checkable. |
| `ContributingCause` | `joint_cause_group_id`, `co_cause_event_ids` | Both non-empty; co-causes sorted. Conjunctive, never a ranked list. |
| `AmplifyingCause` | `magnitude_multiplier` | `> 1.0`. |
| `InhibitingCause` | `magnitude_multiplier` | `0.0 <= m < 1.0`. |

`CausalEdge.payload` is a union discriminated on `edge_kind`, so deserialized data cannot
land in the wrong branch. `CausalEdge.edge_kind` is a **derived property** reading the
payload, so the two cannot disagree. `rule_support` and `statistical_support` are likewise
derived, reading the named components of the edge's `ConfidenceVector`: prd.md §25 lists
them as edge fields and prd.md §49 as confidence components, and storing both would be one
number in two places, free to diverge.

**`CausalEdge.between` is the only sanctioned constructor.** It takes the two `Event`
objects rather than their identifiers, because an edge built from identifiers alone cannot
evaluate LAW-TIME, and a check that cannot run is indistinguishable from one that passes. It
raises `LawViolationError` on a `VIOLATION` verdict, and stamps `temporal_verdict` and
`temporally_unverifiable` itself — a caller able to supply them could launder a rejected
edge into the graph. The same invariants are re-asserted by a model validator, so
deserialization cannot reintroduce a rejected edge either.

**`temporally_unverifiable` is a separate boolean beside the verdict, not a fourth verdict
member.** `UNDETERMINED` means the data placed both events and could not separate them;
`temporally_unverifiable` means the data never placed one of them. Both block promotion to
`INFERRED`, but they are different findings about the dataset and collapsing them would hide
which one a run actually hit — which matters directly to risk R-14.

`CausalEdge.provenance_class` may never be `OBSERVED`: causation is never read from a source
record. The projection from these five kinds onto prd.md §47's graph relationship names
belongs to the Temporal Graph Builder, not to `core`, and `CONDITIONAL` and `CONTRIBUTING`
project onto `CAUSES` carrying their payload as edge properties.

### Consequences
**Positive:** An unusable edge is unconstructible rather than merely discouraged. The
`edge_type` value set is closed, so the `edg` address and the canonical sort key are
well-defined. LAW-TIME is enforced on every path including deserialization.

**Negative:** The union is in every signature that touches an edge, and consumers that only
care about source, target, and confidence pay for a discriminator they never read. Changing
an existing payload's shape breaks the `edg` address and forces a re-derivation of every
edge identifier, so the five payloads are effectively frozen from now on — adding a sixth
kind is cheap, altering one of these five is not. The `AMPLIFYING`/`INHIBITING` split at
1.0 is a modelling choice that makes an edge with a multiplier of exactly 1.0
unrepresentable; that is deliberate, and it will at some point reject a legitimately
computed no-op amplifier and force the caller to decide what it meant.

**Obligations created:** `edge_schema_version` moves to `1.0.0` in `CONTEXT.md` §7;
`tests/law/test_law_time_is_enforced_at_construction.py` asserts the construction and
deserialization guarantees and the absence of any bypass argument; the Temporal Graph Builder
owns the §26-to-§47 projection and must state it in its module contract; `GLOSSARY.md` gains
the payload type names.

### Reversibility cost
**Low** to add a sixth kind. **High** to alter an existing payload — every `edg` identifier
in every store changes, which is a full re-derivation and an `engine_version` bump.
**Medium** to promote `temporally_unverifiable` into a fourth `TemporalVerdict` member:
mechanical, but it touches every consumer that reads the verdict.

---

## ADR-0023 — Canonical serialization is a versioned envelope with quantized floats

- **Date:** 2026-08-25
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** all
- **Affects interfaces:** every canonical type

### Context
`CONVENTIONS.md` §11 requires byte-identical output for identical inputs, and
`scripts/check_determinism.py` diffs two runs to prove it. That gate is only meaningful if
the encoding underneath it is itself stable, and pydantic's default JSON output is not:
key sequence follows field declaration rather than name, float repr varies, and nothing
stamps the payload with what it is. A determinism failure caused by the encoder is
indistinguishable from one caused by the pipeline, and the real signal is lost.

`CONVENTIONS.md` §11 already mandates 6-decimal float quantization and canonical sort keys.
Nothing implemented them, and no ADR named the wire shape.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | `model_dump_json()` as-is | Rejected. Not byte-stable and carries no version stamp. |
| B | A binary format | Rejected. Determinism diffs are read by people; a binary payload makes the gate's output unreadable at exactly the moment it matters. |
| C | **Sorted-key JSON, floats as quantized strings, wrapped in a versioned envelope** | **Chosen.** |

### Decision
`causalog.core.serialization` is the single encoding boundary.
`to_canonical_json` emits a JSON object with three keys — `payload`, `schema_version`,
`type` — where `schema_version` is `CANONICAL_SCHEMA_VERSION`, currently `1.0.0`, and `type`
is the artifact's type name. Keys are sorted at every depth, separators are fixed, instants
are ISO-8601 with an explicit UTC offset, and floats are quantized through
`causalog.core.identifiers.format_float`.

**Floats are emitted as strings, not JSON numbers.** A JSON number is re-formatted by
whichever parser reads it next, so the byte-identity guarantee would not survive a round
trip through another language's encoder.

`from_canonical_json` re-runs every invariant, so a hand-edited or downgraded payload cannot
reintroduce a state the constructor would have refused — this is what makes the LAW-TIME
guarantee hold for stored data. A missing envelope, a different `schema_version`, or a
mismatched `type` is a `ContractViolationError`; none is repaired.

`CANONICAL_SCHEMA_VERSION` versions the *wire shape* — key sequence, float resolution,
instant format, envelope structure. The per-artifact schema versions in `CONTEXT.md` §7 move
independently.

### Consequences
**Positive:** Two runs are comparable with `diff`. A stored artifact says what it is. The
round-trip property is testable and tested.

**Negative:** Quantization is lossy, so round-trip equality holds only for artifacts whose
floats are already at six decimal places — the intended state, but it means an artifact
constructed with an unquantized float round-trips to a *different* artifact, and the loss
surfaces at the serialization boundary rather than where the value was computed. Floats as
strings will surprise every external consumer and makes the payload larger. And this
encoder is a second serialization path alongside pydantic's own, so a module that reaches
for `model_dump_json` gets output that looks right and is not byte-stable; nothing currently
detects that.

**Obligations created:** `tests/unit/core/test_serialization_round_trip.py` covers every
canonical type, and a type added without a case there is a gap; every persistence adapter
and API response encodes through this module; `scripts/check_determinism.py` compares its
output.

### Reversibility cost
**Medium.** Changing the wire shape is a `CANONICAL_SCHEMA_VERSION` bump plus a reader that
accepts both versions during migration. Persisted payloads would need rewriting or a
version-dispatching parser.

---

## ADR-0024 — Add `hypothesis` to the pinned dependency set, derandomized

- **Date:** 2026-08-25
- **Status:** accepted
- **Supersedes:** ADR-0015
- **Affects modules:** all (test tooling)
- **Affects interfaces:** —

### Context
The canonical core's guarantees are universally quantified: *no* payload pair collides,
*no* overlapping interval reports precedence, provenance combination *never* increases
certainty. Example-based tests assert these at the points somebody thought of, which is
precisely the wrong coverage for a law — the counterexample that matters is the one nobody
imagined.

ADR-0015 requires a superseding ADR for any addition to the dependency set, and
`CONVENTIONS.md` §12 requires five specific statements per dependency. `hypothesis` is a
randomized generator, so §12 item 2 and §11's determinism guarantee both bite directly.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Do nothing; hand-write examples | Rejected. The properties are universal; hand-picked examples cannot express them, and the identifier-collision case in particular is not reachable by inspection. |
| B | Hand-roll a generator loop | Rejected. It would need shrinking to be usable, and a bespoke shrinker is a larger maintenance surface than the library. |
| C | **`hypothesis`, pinned exactly, with a `derandomize=True` profile as the seed contract** | **Chosen.** |

### Decision
The V1 dependency set is ADR-0015's table with one row added to the dev extra:

| Package | Solves | Nondeterminism | Domain assumptions | License / removal cost |
|---|---|---|---|---|
| `hypothesis==6.165.10` (dev) | Property-based tests for the canonical core: identifier determinism, timestamp comparison under uncertainty, the provenance algebra, aggregation bounds, serialization round-trip | **Yes — and this is the seed contract.** `backend/tests/conftest.py` registers a `deterministic` profile with `derandomize=True` and loads it at import. Hypothesis then derives its choices from a hash of the test itself rather than from entropy, so a given commit explores the same inputs on every machine and a failure reproduces from the test name alone. `print_blob` is off, since its token would make two otherwise identical failure reports differ. | None; fixtures are synthetic and domain-neutral (`CONVENTIONS.md` §14) | MPL-2.0; **low** — test-only, and the properties can be rewritten as example tests |

Every other row of ADR-0015 stands unchanged, including the blocklist: `pgmpy`, `dowhy`,
`torch`, `torch-geometric`, `scikit-learn`, `tensorflow` remain excluded by ADR-0003.

`hypothesis` is a **dev** dependency. It may not be imported from `backend/src/`, where it
would breach forbidden edge F8 — `core/` takes no third-party dependency beyond pydantic.

### Consequences
**Positive:** The laws are asserted over generated inputs rather than remembered examples.
Shrinking means a failure arrives as a minimal counterexample. Determinism is preserved.

**Negative:** A derandomized suite stops finding *new* counterexamples on reruns — it is a
regression net, not a search, and the search only happens when someone deliberately runs
with `--hypothesis-seed=random`. In practice nobody will, so the real exploration happens
once, when a property is written. Property tests are also slower and harder to read than
examples, and a badly chosen strategy can pass convincingly while generating almost nothing
interesting, which is a failure mode with no external symptom. One more pin to maintain.

**Obligations created:** the `deterministic` profile in `backend/tests/conftest.py` is
part of the determinism guarantee and may not be removed without a superseding ADR; the
`property` pytest marker is registered in `backend/pyproject.toml`; strategies stay
domain-neutral; a periodic deliberate run with a random seed is worth scheduling, and its
absence is the known weakness above.

### Reversibility cost
**Low.** Test-only. Removing it means rewriting the property tests as example tests, losing
coverage but breaking nothing that ships.

---

## ADR-0025 — `docs/contracts.md` is the module contract document, and the canonical core is frozen at 1.0.0

- **Date:** 2026-08-25
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** all
- **Affects interfaces:** every `causalog.core` public type

### Context
OQ-009 has blocked freezing since the scaffold: the module contract document the Definition
of Done refers to did not exist, so its proposed default held every row of `CONTEXT.md` §6
at `draft` and `docs/architecture.md` §0 stated that "nothing may be marked `frozen` until
the module contract document exists".

That default was correct and has become the binding constraint. `core/` is now implemented
rather than sketched: identifiers, temporal comparison, the provenance algebra, confidence
aggregation, the edge taxonomy, serialization, and their property tests. Sixteen modules are
meant to compute over these types, and none can be built against a contract that may still
move. A contract nobody has written down cannot be frozen; a contract nobody can rely on is
not a contract.

`CONTEXT.md` §7 rule 1 adds a second lock: "`unset` blocks freezing. No interface may move
to `frozen` while a contract it depends on is `unset`." Four schema versions are `unset` and
are set by this ADR.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Keep everything `draft` until more modules exist | Rejected. It inverts the dependency: the modules exist *to* compute over these types, so waiting for them means every module is built against a moving target and the churn is paid sixteen times. |
| B | Freeze by asserting it in `CONTEXT.md` §6 | Rejected. This is precisely OQ-009's stated failure mode — "contracts get frozen by assertion rather than by specification". |
| C | **Write the contract document, set the four schema versions, then freeze the rows it specifies** | **Chosen.** |

### Decision
`docs/contracts.md` is the module contract document OQ-009 referred to. It states, for every
public type in `causalog.core`: its fields and their types, its invariants, how it fails,
and what it is forbidden from doing — the shape `docs/architecture.md` §2 requires. It
carries its own version, `1.0.0`, and three sections that govern behaviour rather than
shape: the timestamp comparison semantics, the hashing scheme and its collision bound, and
the provenance algebra table.

Four contracts in `CONTEXT.md` §7 move from `unset` to `1.0.0`: `event_schema_version`,
`entity_schema_version`, `edge_schema_version`, and `confidence_schema_version`. The
component name set is part of the last of these (ADR-0009) and the closed `edge_kind` value
set is part of the third (ADR-0022).

Every `causalog.core` row in `CONTEXT.md` §6 moves to `frozen`. Per §6's own vocabulary a
`frozen` interface may still change, but only through an ADR and a coordinated update of
every consumer. Rows owned by modules that do not yet exist — `Timeline`,
`TemporalPropertyGraph`, `RootCauseRanking`, `PropagationReport`, `SimulatedWorld`,
`Intervention`, `Explanation`, the HTTP API — stay `draft`. Freezing a type nobody has built
would be the same assertion-not-specification error in a new place.

OQ-009 is closed by this ADR.

### Consequences
**Positive:** Sixteen modules can now be built against a stated, versioned contract. The
freeze is backed by a specification and a test suite rather than by assertion, which is what
OQ-009 asked for.

**Negative:** Freezing before any module consumes these types means the contract is frozen
against *anticipated* use, not observed use. The first two or three modules will find things
that want changing, and each will now cost an ADR and a coordinated update instead of an
edit — this ADR trades cheap early churn for expensive late churn, deliberately, on the
judgement that sixteen consumers of a moving target is the worse failure. Setting four
schema versions to `1.0.0` also asserts stability for shapes no persistence layer has yet
stored, so the first migration will be written against a version that was never actually
deployed.

**Obligations created:** `docs/contracts.md` is updated in the same commit as any change to
a frozen type, and its version bumps with it; `docs/README.md` lists it; `CONTEXT.md` §6, §7,
§8, and §11 are updated in this commit; a change to any frozen row requires an ADR naming
every consumer.

### Reversibility cost
**Low** today — nothing consumes the frozen types yet, so unfreezing is an edit to
`CONTEXT.md`. **High** once modules exist, which is the entire point of freezing now.

---

## ADR-0026 — The domain pack is a declarative DSL whose pydantic models are normative and whose JSON Schema is generated

- **Date:** 2026-08-28
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Schema Mapper, Entity Extractor, Event Generator, Timeline Builder, State Engine, Relationship Resolver, Root Cause Analyzer, Intervention Optimizer
- **Affects interfaces:** `OntologySpec`

### Context
ADR-0002 ruled that all domain vocabulary lives as data in `ontology/`. Until now that was
a promise with nothing behind it: `ontology/` held three READMEs and no data file,
`causalog.ontology_runtime` was an empty package, and `ontology_version` was `unset` in
`CONTEXT.md` §7 — which blocks `run_id` (ADR-0013) and therefore keeps the determinism gate
NOT-YET-RUNNABLE (OQ-014). The scaffold's sketch of `ontology.yaml` covered entity types,
event types, states, and legal transitions, which is not enough for the modules that will
read it: the timeline builder needs process definitions, the root-cause ranker needs
declared actionability and cost class (ADR-0008, risk R-15), and every metric the engine
reports needs a formula that is not written into a reasoning module.

The module brief additionally required the pack to be "JSON-Schema-validated". `jsonschema`
is not in the pinned dependency set, and `CONVENTIONS.md` §12 requires an ADR before any
new dependency.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Hand-author the JSON Schema as normative; add `jsonschema` to validate against it | Rejected. Two validators for one contract — JSON Schema for structure, pydantic for the resolved model — free to disagree; the disagreement surfaces as a pack one accepts and the other rejects with nobody able to say which is right. JSON Schema also carries no YAML line information, so actionable file/line errors would still have to be built by hand. Costs a dependency for none of the benefit. |
| B | Hand-rolled Python validation with no schema artifact at all | Rejected. Nothing outside Python could check a pack, and the brief's requirement is unmet. |
| C | **Pydantic models normative; JSON Schema generated from them and checked in** | **Chosen.** Pydantic is already the chosen data-validation library (`CONVENTIONS.md` §12), is F8-clean, and reports a structured `loc` path that joins cleanly to a YAML line index. One description of the contract; the published schema is rendered from it and a build check fails on drift. No new dependency. |
| D | Allow a pack to reference Python callables for metrics it cannot express | Rejected outright. That is executable code inside a data file, and it re-opens every door LAW-DOMAIN closes. |

### Decision
The domain pack DSL is defined by the pydantic models in
`causalog.ontology_runtime.dsl`, versioned by `PACK_SCHEMA_VERSION`, set to `1.0.0`. A pack
declares `event_categories`, `cost_classes`, `severity_classes`, `entity_types`,
`relationship_types`, `event_types`, `external_event_types`, `process_definitions`, and
`measurement_definitions`. Every model is `frozen=True, extra="forbid"`.
`ontology/_schema/ontology.schema.json` is **generated** from those models by
`scripts/export_ontology_schema.py`, and `--check` fails the build when the published file
and the models disagree; it runs in `make laws` and in its own CI job.

**No pack may carry executable code.** There is no expression string, no callable reference,
and no plugin hook anywhere in the schema. A measurement is a closed operator tree
(`CONSTANT`, `ATTRIBUTE`, `SUM`, `DIFFERENCE`, `PRODUCT`, `RATIO`, `DURATION_BETWEEN`,
`MINIMUM`, `MAXIMUM`); a metric that cannot be expressed in it requires a new operator, an
ADR, a `PACK_SCHEMA_VERSION` bump, and every pack revalidated.

The loader reports **every** diagnostic together, each with a file and a line, in three
severities: `ERROR` (refuses the pack), `WARNING` (does not), and `NOT_RUNNABLE` — a check
the validator could not perform. `NOT_RUNNABLE` is not a convenience: DEF-0001 and OQ-014
are both instances of a check that could not run being read as one that passed, and the
rule-coverage check is unrunnable today because no rule pack exists.

`causalog.ontology_runtime` is added to `IN_SCOPE_PACKAGES` in
`scripts/check_domain_independence.py`. The one package built to keep the domain out was
the one package not being checked for it.

### Consequences
**Positive:** `ontology_version` moves off `unset`, which unblocks `run_id` and therefore
the determinism gate. Every metric formula, process expectation, and actionability claim is
data, inspectable and diffable. A malformed pack fails at load with a located, actionable
message rather than producing silently wrong causality further downstream. No new
dependency.

**Negative:** The DSL is considerably larger than the scaffold's sketch, and a pack author
now meets nine namespaces rather than four — pack authoring becomes a real skill and a real
failure mode, exactly as ADR-0002 predicted. Freezing the schema at `1.0.0` before any
consuming module exists repeats the ADR-0025 trade knowingly: the first modules to read a
pack will find things they want changed, and each now costs an ADR. The closed operator set
will at some point reject a legitimate metric and force a schema change rather than a
workaround, which is the intended behaviour and will still be experienced as friction. And
the central limitation stands: **a pack that validates cleanly can still be semantically
wrong**, and nothing in this layer can detect it — recorded as risk R-16.

**Obligations created:** `scripts/export_ontology_schema.py` with `--self-test`, `--write`,
and `--check`, wired into `make laws` and CI; `docs/ontology.md` as the onboarding
procedure; the DSL, the published schema, and every pack updated in one commit whenever the
schema changes.

### Reversibility cost
**Medium-high.** Reversing the DSL means rewriting every pack and every module that reads
one. Reversing the *generated-schema* half is cheap today and gets no cheaper: it is one
script and one CI job.

---

## ADR-0027 — Packs live at `ontology/packs/<domain>/` and inherit by whole-entry replacement

- **Date:** 2026-08-28
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Schema Mapper, Entity Extractor, Event Generator
- **Affects interfaces:** `OntologySpec`, `SchemaMappingSpec`, `CostModel`, `PresentationLabels`

### Context
`docs/architecture.md` §5.1 placed the ontology seam at `ontology/<domain>/ontology.yaml`.
With a schema directory (`_schema/`) and a structural base pack now both needing a home,
that layout puts two non-domains as siblings of every real domain, and `ontology/_base/`
reads as a domain whose name begins with an underscore. Separately, a base pack is only
useful if the merge semantics are stated: ADR-0026 introduces `extends`, and an unstated
merge rule is a rule every author will guess differently.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Keep `ontology/<domain>/`; put the base beside the domains | Rejected. `_schema`, `_base`, `dataco`, `hospital` as four peers gives no signal about which two are domains. |
| B | **`ontology/packs/<domain>/`, with `_schema/` outside it** | **Chosen.** One directory holds packs and nothing else; `_base` is unambiguously a pack, and the leading underscore marks it as not a domain. Costs an amendment to `docs/architecture.md` §5.1 and the `CONTEXT.md` §6 seam rows. |
| C | Deep field-level merge for overlays | Rejected. The effective declaration would exist in no file, assembled from two, and an author reading either would see something other than what the engine loads. |
| D | Omission removes an inherited entry | Rejected. "I did not think about this" and "I decided this does not apply" would be the same text. |

### Decision
Domain packs live at `ontology/packs/<domain>/ontology.yaml`; the generated schema stays at
`ontology/_schema/`. A pack identifier is lower snake case and may carry a leading
underscore only when it is not a domain — today, `_base`, which declares the ordinal cost
and severity vocabularies and nothing else. `docs/architecture.md` §5.1 is amended to the
new path; the seam is otherwise unchanged, and `mapping.yaml`, `cost.yaml`, `labels.yaml`
and the rule pack remain separate seams owned by their own modules rather than being folded
into the pack.

Inheritance is **whole-entry replacement, keyed by identifier, per namespace.** An overlay
entry replaces the base entry with the same identifier in full; a new identifier is
appended; a base identifier is withdrawn only through an explicit `removes:` block, and a
withdrawal naming an identifier no ancestor declares is a load error. There is no
field-level merge. The resolved pack is canonically sequenced by identifier in every
namespace, and chains deeper than `MAX_CHAIN_DEPTH` (8) are refused.

### Consequences
**Positive:** Every effective declaration is a block someone actually wrote and can be read
in one file. A stale `removes:` line fails loudly instead of doing nothing. The `packs/`
namespace makes "what is a domain here" answerable by listing a directory.

**Negative:** Whole-entry replacement is verbose: an overlay changing one field of an
inherited entity type must restate the whole entity type, and the two copies can then drift
without any check noticing. That is a real cost, accepted in exchange for readability. The
path change also invalidates every prior reference to `ontology/dataco/`, including in
documents outside this repository.

**Obligations created:** `docs/architecture.md` §5.1 and §5.2, the `CONTEXT.md` §6 seam
rows, `ontology/README.md`, and `ontology/_schema/README.md` amended in this commit;
`docs/ontology.md` states the merge rule where a pack author will meet it.

### Reversibility cost
**Low.** A directory move and a documentation amendment. No identifier and no hash depends
on the path.

---

## ADR-0028 — `ontology_hash` addresses the resolved pack through the one existing hashing scheme

- **Date:** 2026-08-28
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** all (via `run_id`)
- **Affects interfaces:** `IdentifierPrefix`, `RunKey`, `OntologySpec`

### Context
`run_id = "run:" + sha256(dataset_version | ontology_hash | rule_pack_version |
engine_version | seed)[:16]` (ADR-0013). `ontology_hash` had no definition and
`CONTEXT.md` §7 carried it as `unset`, so no Run could be minted. `docs/contracts.md` §2
defines one hashing scheme — `digest(prefix, canonical_payload)` over a closed
`IdentifierPrefix` enum, which is frozen by ADR-0025 and has no member for an ontology.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Hash the pack file's bytes | Rejected. A comment, a reindent, or splitting a pack across a base and an overlay would each mint a new ontology and invalidate every prior `run_id`, while changing nothing about what the pack says. |
| B | Compute the digest locally in `ontology_runtime` with `hashlib`, avoiding the enum | Rejected. A second hashing path is a second answer to "what is this pack", free to disagree with the first. `docs/contracts.md` §9 already lists two coexisting serialization paths as a thing to watch; adding a third of the same kind is the error, not the fix. |
| C | **Add `ONTOLOGY = "ont"` to `IdentifierPrefix` and hash the canonically serialized resolved pack** | **Chosen.** Purely additive to the frozen enum: no existing address recipe changes, so no identifier in any store moves and no `engine_version` bump is required. Reuses `to_canonical_json` and `digest` exactly as every other artifact does. |

### Decision
`ontology_hash(pack) = digest(IdentifierPrefix.ONTOLOGY, to_canonical_json(resolved_pack))`,
yielding `ont:<16 hex>`. `IdentifierPrefix` gains `ONTOLOGY = "ont"`; `docs/contracts.md`
moves to **1.1.0** and its §2 payload table gains the `ont` row. The hash is computed over
the **resolved** pack, so it is invariant to comments, indentation, key sequence, and how
the pack was split across an inheritance chain, and sensitive to every declared value.
`CONTEXT.md` §7 sets `ontology_version` to `1.0.0` and names this recipe.

`ResolvedPack.lineage` participates in the hash. Two packs declaring identical content, one
written out in full and one assembled from a base, therefore hash *differently* — pinned by
a test that asserts the two are otherwise identical, so the fact is recorded rather than
discovered later.

### Consequences
**Positive:** `run_id` becomes computable, which removes one of the two blockers on the
determinism gate (OQ-014; the other is the pipeline itself). Reformatting a pack no longer
looks like a changed ontology. One hashing scheme, one answer.

**Negative:** This is the first amendment to a contract frozen three days earlier, which
tests the freeze process rather than the freeze. `lineage` participating in the hash means
flattening a pack for readability *does* change its identity — defensible, since lineage is
part of what the resolved pack is, and a surprise to anyone who expects the hash to depend
only on declarations. And a pack that is semantically wrong hashes as confidently as one
that is right; the hash establishes identity, never correctness.

**Obligations created:** `docs/contracts.md` bumped to 1.1.0 with the `ont` row in §2;
`CONTEXT.md` §6 and §7 updated in this commit; any future change to the resolved-pack shape
is an `ontology_hash` change and therefore a `run_id` change for every stored run.

### Reversibility cost
**Medium.** Removing the enum member is trivial; changing the recipe re-derives every
`ontology_hash` and therefore every `run_id`, and prior runs stop being comparable to
subsequent ones.

---

## ADR-0029 — A derived event type is declared as derived, names its basis, and may never claim OBSERVED provenance

- **Date:** 2026-08-28
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Event Generator, Timeline Builder, Candidate Cause Generator, Confidence Scorer
- **Affects interfaces:** `OntologySpec`, `Event`

### Context
DataCo is one row per order line carrying a *terminal* `Order Status` and a handful of date
and duration columns. It does not log occurrences. A dispatch is implied by a `shipping
date` column; a payment approval is implied by a status value that survived; a delivery is
implied by `Delivery Status` together with `Days for shipping (real)`. Modelled naively,
every one of these becomes an event indistinguishable from one the source actually recorded
— and LAW-PROVENANCE would then be satisfied in form and violated in substance, because
`OBSERVED` would be carried by facts nobody observed.

The failure is quiet and convincing: a fabricated occurrence with a real column standing
behind it reads as better evidence than an honest gap.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Treat any event derivable from a column as `OBSERVED` | Rejected. It is exactly the substance-level LAW-PROVENANCE violation described above, and no downstream module could detect it. |
| B | Omit every event the source does not log | Rejected. It would leave the canonical process with two steps and make the timeline builder unable to express the flow the business actually runs. |
| C | **Declare it explicitly as `observation: DERIVED` with a basis and a default confidence** | **Chosen.** The occurrence is available to the engine, and its status as a reconstruction travels with it, structurally, from the ontology to the `Event`. |

### Decision
An `EventTypeSpec` declares `observation: OBSERVED | DERIVED`. A `DERIVED` type **must**
carry `derivation.basis` (prose naming what it is reconstructed from), may carry
`derivation.source_columns`, and **must** carry `derivation.default_confidence` — a
component/value vector whose names are validated against
`DEFAULT_COMPONENT_WEIGHTS` and whose `provenance_class` may not be `OBSERVED`. A `DERIVED`
type may **never** declare `provenance_class: OBSERVED`; the model validator refuses it and
`structural.py` refuses it again on the resolved pack. An `OBSERVED` type may not carry a
`derivation` at all.

The default confidence is deliberately *not* a `core.types.ConfidenceVector`: that type
requires `evidence_record_ids`, and a pack has no evidence records — they are minted when a
record is read. The pack declares names and weights; the Event Generator materializes the
vector against real evidence.

In the DataCo pack this makes exactly one event type `OBSERVED` (`ORDER_PLACED`) and twenty
`DERIVED`. That ratio is a finding about the dataset and is pinned by a test, so a later
edit cannot quietly promote one.

### Consequences
**Positive:** "This dataset logs one occurrence and implies the rest" becomes a visible,
enforced property rather than a thing a reader has to notice. Every reconstruction states
what it was reconstructed from, in the pack, next to the declaration. Confidence Scorer and
Candidate Cause Generator inherit an honest floor without having to know anything about
logistics.

**Negative:** A twenty-to-one derived ratio will make the DataCo graph look weak next to
what a naive modelling would have produced, and the temptation to reclassify will be
constant and will always be available — the guard is a validator and a test, not a proof.
The default confidences are an editorial judgement with no ground truth behind them, the
same exposure `docs/contracts.md` §9 records for the `weighted_mean_v1` weights, now
multiplied across twenty event types. Nothing can validate a `derivation.basis`: a wrong
basis is prose, and prose passes every check in this repository.

**Obligations created:** the ratio test in
`tests/unit/ontology_runtime/test_dataco_pack_traceability.py`; the finding stated in
`ontology/packs/dataco/README.md`; every future pack author meets the rule in
`docs/ontology.md` §2.

### Reversibility cost
**Low** to change a single event type's classification; **high** to abandon the distinction,
which would mean re-deriving every event and every edge that cited one.

---

## ADR-0030 — Pack discovery is derived from the pack directory, and metric arithmetic in reasoning code is refused by lint

- **Date:** 2026-08-28
- **Status:** superseded by ADR-0031
- **Supersedes:** —
- **Affects modules:** Timeline Builder, State Engine, Propagation Analyzer, Counterfactual Simulator, Intervention Optimizer, Explanation Generator
- **Affects interfaces:** `OntologySpec`

### Context
Two properties the ontology layer is supposed to have were true on 2026-08-28 and enforced
by nothing.

**Onboarding is supposed to touch `ontology/` alone.** It did not.
`docs/ontology.md` §4 step 9 instructed a new pack's author to add the pack id to three
literal tuples — `SHIPPED_PACKS` in `test_packs_load.py` and `PACKS` in
`test_ontology_hash_stability.py` and `test_pack_round_trip.py`. The hospital pack loads with
no engine change only because somebody performed that editing; a fourth pack added without
it would load, be tested by nothing, and break silently — which is the outcome that same
step exists to prevent.

**Metrics are supposed to be declared, not computed.** The declaration half is structural:
`MeasurementExpression` is a closed operator tree, and ADR-0026 leaves no way to put an
expression string in a pack. The engine half had no guard at all. Nothing stopped a future
reasoning module computing a delay inline, and the failure would be quiet: the number looks
right, the pack still validates, and the ontology stops being where the metric is defined.
Swapping the pack would then change the declaration and not the arithmetic — LAW-DOMAIN
defeated by a value rather than by a word, which is precisely the residual
`docs/architecture.md` §1.5 states the vocabulary lint cannot see.

Both are the DEF-0001 shape: a property that holds today, with nothing in CI that would
notice the day it stops.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Leave both as prose; rely on review | Rejected. This repository has already been burned once by exactly that (DEF-0001), and `PROGRESS.md` already carried the metric rule as prose while nothing checked it. |
| B | Glob the pack directory at collection time; add an AST lint refusing metric arithmetic in reasoning packages | **Chosen.** Both are cheap, both are checkable, and the lint is free to add now because every reasoning package is still empty — no existing code has to be argued about. |
| C | Evaluate measurement trees inside `ontology_runtime` so no engine ever does arithmetic | Rejected. It would put arithmetic over domain attributes inside the seam that exists to hold no logic (`PROGRESS.md`, the ontology layer's deliberate omissions). The tree is produced here and walked by the module that reports the metric; moving evaluation inward trades one violation for a worse one. |
| D | Regex-match arithmetic on metric-named identifiers | Rejected. It fires on `# the cost of a rerun` and on `"impact"` in a string literal, and a lint that cries wolf in prose is deleted within a week. |

### Decision
**Pack discovery is derived.** `backend/tests/ontology_packs.discover_packs()` globs
`ontology/packs/*/ontology.yaml` and returns the directory names, sorted. The three
parameterisations call it. An empty result raises rather than parameterising zero tests,
because zero tests report as a pass. Adding a domain requires no edit outside `ontology/`.

**Metric arithmetic in reasoning code is refused.**
`scripts/check_metrics_are_declared.py` walks the AST of every `.py` file under
`graph_engine/`, `causal_engine/`, `counterfactual_engine/`, `recommendation_engine/`, and
`explanation_engine/` and fails the build on either shape: arithmetic whose operand is named
for a domain metric, or an assignment binding a metric-named target to an arithmetic
expression (`delay = arrival - promised`, the commonest form). Metric stems track
`MeasurementKind` — delay, duration, cost, impact, quantity — plus the words a pack author
reaches for. `COUNT` and `RATIO` are members of that enum and are deliberately excluded:
both are ordinary program bookkeeping, and a lint that fires on `count += 1` gets disabled.
`core/` is out of scope because `core/aggregation.py` does arithmetic over confidence
components, which are engine concepts (ADR-0009); `ontology_runtime/` is out of scope
because it builds the tree and never evaluates it. A reviewed exception goes in
`.lawmetric-allowlist` with a justification.

While every reasoning package is scaffold-only the scan exits **2 — NOT-YET-RUNNABLE**, and
says so loudly. Emptiness is measured by content, not by file count: thirteen docstring-only
`__init__.py` files must not report as "13 files, clean".

### Consequences
**Positive:** the first checklist item is now true for every pack rather than for the one
pack somebody remembered to register. The metric rule becomes a build outcome before any
engine code exists, so it is never argued about retroactively — the cheapest moment to add
a constraint is before anything violates it.

**Negative:** the metric lint is a name-based check and inherits every limit of one. A
formula carried under a name that says nothing (`value = a - b`) passes clean, as does one
split across statements. Comparison is not matched — a threshold on a metric is domain
policy too, but a comparison computes nothing, and a lint firing on every guard clause would
be routed around. The stem list is an editorial judgement that will need extending as packs
name metrics the list does not anticipate. And the scan's exit 2 means the check is proved
only by its self-test until the P2 exit; it has been observed to reject a planted violation,
which is the most that can be said today.

**Obligations created:** delete the exit-2 tolerance from `make laws` and from the
`metrics-are-declared` CI job at the P2 exit — `test_the_scan_reports_not_runnable_while_the_engine_is_unbuilt`
in `backend/tests/law/test_enforcement_scripts_prove_themselves.py` fails the day the first
reasoning module lands, which is what forces the removal to be noticed rather than
remembered.

### Reversibility cost
**Low** for both. Discovery is one function and three call sites; the lint is one
standard-library script and its registrations.


---

## ADR-0031 — The metric lint follows the value, and refuses a hard-coded threshold

- **Date:** 2026-08-28
- **Status:** accepted
- **Supersedes:** ADR-0030
- **Affects modules:** Timeline Builder, State Engine, Propagation Analyzer, Counterfactual Simulator, Intervention Optimizer, Explanation Generator
- **Affects interfaces:** `OntologySpec`

### Context
ADR-0030 shipped a name-based matcher and recorded two holes in its own Consequences. Both
were reachable by an author who was not even trying to evade the check.

**A metric laundered through an unnamed variable.** The matcher reads identifiers. A
declared quantity enters engine code through a *string* — `event["shipping_delay"]` — and
one rebinding is enough to strip every metric name off the arithmetic:

```python
raw = event["shipping_delay"]
value = raw - baseline          # clean under ADR-0030
```

That is not an exotic form. It is what ordinary code looks like once a value has been read
out of a record, and a rule that misses it enforces a naming convention rather than
ADR-0026.

**A hard-coded threshold.** `if delay > 48:` computes no metric, so ADR-0030 let it pass and
said so. But 48 is domain policy — the same policy the pack exists to hold — and it does not
move when the ontology is swapped. The stated reason for excluding comparison was that a
lint firing on every guard clause gets routed around. That reason applies to
`delay > threshold`, where the bound comes from elsewhere. It does not apply to a numeric
literal, which is the actual defect and is separable.

Nothing in `causalog/` changed under either ADR: the reasoning packages are still empty. That
is the whole reason to tighten now.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Keep ADR-0030 as shipped; document both holes | Rejected. Both holes are reachable by accident, and the repository's own standard is that a stated limitation with no check behind it is what DEF-0001 was made of. |
| B | **Intra-scope taint tracking, plus metric-versus-literal comparison** | **Chosen.** Follows the value instead of the name, and separates the threshold form that is a real defect from the guard form that is not. |
| C | Ban arithmetic outright in the reasoning packages, permitting only a sanctioned tree-walking evaluator | Rejected *for now*. It is the strongest guarantee and it is free today, but it refuses legitimate index, depth, and counter arithmetic that every one of those modules will need, and each exception would arrive as an allowlist entry — turning the allowlist into the pressure valve it is explicitly not meant to be. Revisit if taint tracking proves too weak in P2. |
| D | Match every comparison involving a metric | Rejected. `if duration is None`, bounds checks, and sort keys all fire. This is the shape that gets a lint disabled. |
| E | Add a `thresholds` namespace to the DSL so a policy constant has a declared home, then refuse literals | Rejected as premature, not as wrong. It is a DSL change: its own ADR, `pack_schema_version` to 1.1.0, schema regeneration, every pack revalidated, and every `ontology_hash` moves — for a namespace no module consumes yet. The lint names the problem now; module 14 can declare the home when it has one. |

### Decision
Everything ADR-0030 decided about **pack discovery** stands unchanged and is restated here
so nothing is lost in the supersession: discovery is derived from `ontology/packs/*/ontology.yaml`
via `tests/ontology_packs.discover_packs()`, which raises on an empty result.

`scripts/check_metrics_are_declared.py` now matches **four** shapes rather than two. Rules 1
and 2 are ADR-0030's, unchanged. Rule 3: arithmetic on a **tainted** value — a name bound,
anywhere earlier in the same scope, from a metric-named attribute or a metric-named string
key. Taint propagates through rebinding and is tracked **per scope**, so a `value` holding a
metric in one function does not taint an unrelated `value` in the next. Rule 4: a
**comparison between a metric and a numeric literal**. Comparison against a *variable* stays
unmatched, and that limit is now a pinned test rather than a paragraph.

Taint is a source-order approximation, not a dataflow analysis: this file is
standard-library only (ADR-0016), and the alternative is a type checker.

The `MUST_NOT_FIRE` self-test table stays single-line wherever a metric stem appears, because
the DEF-0001 guard that polices it is deliberately line-blind and a multi-line entry could
hide a stem on one line and the arithmetic on the next. The one negative case that genuinely
needs several lines — taint must not cross a function boundary — is asserted in pytest
instead. This was found by the guard rejecting a table entry written while implementing this
ADR, which is the guard doing exactly its job.

### Consequences
**Positive:** the check now follows the value, which is what ADR-0026 is actually about; the
laundering form that motivated this ADR is caught, and so is every rebinding of it. A
hard-coded policy constant is refused at the point it is written rather than found in review.
Both new rules were observed to reject a planted file before being trusted.

**Negative:** taint tracking is a source-order approximation and will miss a value assigned
after it is read — a loop that rebinds at the bottom and computes at the top. It also cannot
follow a metric through a function call, so `helper(raw)` launders it as effectively as a
rename did before. Arithmetic on a genuinely unnamed value from an unnamed source
(`v = a - b`, both parameters) is still clean, and no lint reachable from the standard
library will change that. Rule 4 will fire on a legitimate numeric comparison against a
metric — a unit conversion guard, a sanity bound — and those will need allowlist entries or
renaming; the count of them is unknown because no module exists yet.

**Obligations created:** revisit option C at the P2 exit alongside the exit-2 tolerance
removal ADR-0030 already obliges. If taint tracking is producing more allowlist entries than
findings by then, the ban-arithmetic-outright option is the honest replacement.

### Reversibility cost
**Low.** One standard-library script and its self-test tables.

---

## ADR-0032 — Bi-temporal storage: valid time is the core interval, system time is database-managed

- **Date:** 2026-08-29
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** State Engine, Relationship Resolver, Root Cause Analyzer, Visualization API
- **Affects interfaces:** `FactRepository` (draft), `State`, `Relationship` (frozen — **unchanged**)

### Context
Re-inference is routine in this engine. A Run is re-derived whenever the ontology, the rule
pack, or the engine version changes (ADR-0013), and a re-derivation can legitimately narrow a
state's validity interval — a better ontology places a transition more precisely.

With a single time axis, that correction **overwrites** the interval a past conclusion was
computed against. Three properties `docs/architecture.md` §4.4 promises then fail at once: the
conclusion cannot be reproduced, because its inputs are gone; it cannot be audited, because
the audit record cites a state that now says something else; and it cannot be compared against
the new conclusion, because there is nothing left to compare. prd.md §54's "no inferred result
should overwrite observed facts" fails **silently**, which is the worst available failure mode.

`State.held_over` and `Relationship.valid_over` are frozen (ADR-0025). Whatever is done here
must not change them.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Single time axis; corrections overwrite | Rejected. Loses reproducibility, auditability, and comparability at the same moment, and loses them without any signal. |
| B | Add `system_from`/`system_to` to the frozen core types | Rejected. Changing a frozen contract needs an ADR *and* a coordinated update of every consumer, and would put insertion wall-clock inside a content address — two runs over identical inputs would stop sharing an identifier, which destroys ADR-0013. |
| C | **Valid time is the existing frozen interval; system time is added as database-managed columns that appear in no core type and no content address** | **Chosen.** |
| D | Full temporal tables / a history side-table per fact table | Rejected for V1. Doubles the object count and the reversal surface for a property option C gets from two columns and one trigger. |

### Decision
`state`, `state_transition`, and `relationship` carry two independent axes.

**Valid time** is `valid_from`, `valid_to`, `valid_precision`, `valid_provenance`,
`valid_source` — the frozen `TimeInterval` flattened, because an interval carries four facts
and a range type holds two. A generated `tstzrange` sits beside them for containment queries
and is never authoritative.

**System time** is `system_from` and `system_to` (`'infinity'` while current). It appears in
**no** content address, **no** `causalog.core` type, and **no** output envelope, and no
reasoning module may read it. `system_from` is supplied by the caller from the `Clock` port
rather than defaulted to `now()`: `CONVENTIONS.md` §11 requires time to be injected, and a
column default would also make the behaviour untestable, because a test cannot assert an
as-of read against an instant it did not choose.

**One sanctioned mutation.** `causalog_close_system_period()` admits exactly one `UPDATE` —
closing an open system period, once. It refuses `DELETE`, refuses reopening, refuses closing
at or before `system_from`, and refuses any change to row content. Content change is detected
by comparing the whole row as `jsonb` minus the two system-period columns, rather than
against a per-table column list that could drift from the table it guards.

Two implementation facts that are not free choices and are recorded so they are not
"simplified" later:

- The trigger is `AFTER`, not `BEFORE`. PostgreSQL has not computed `GENERATED` columns in a
  `BEFORE` trigger, so `NEW.held_over` is `NULL` while `OLD.held_over` holds a value, and
  every legitimate retraction would read as a content change.
- The comparison is not a generated `row_identity` column. That was the first attempt and
  PostgreSQL rejects it: a generation expression must be `IMMUTABLE`, and every rendering of
  a `timestamptz` (`::text`, `to_char`) is only `STABLE` because it depends on the session
  `TimeZone`.

The as-of predicate is half-open on the upper bound — `system_from <= t < system_to` — so a
belief closed at exactly `t` is not returned as of `t`. An inclusive bound would return two
beliefs for one state at the moment of retraction, and `core.derivation.current_state` raises
on two rather than resolving one by arbitrary choice.

### Consequences
**Positive:** "What did the engine believe on date X, and what does it believe now" are two
queries over one table. A disputed conclusion is re-derived rather than re-argued. No frozen
contract changed, no identifier moved, and `engine_version` does not bump.

**Negative:** every bi-temporal read must remember to filter, and the ordinary read and the
as-of read are two different repository methods precisely so an ordinary read cannot return
stale history by accident — which means a caller who wants history has to know to ask. The
tables grow with corrections rather than with facts, and nothing prunes them; that is
correct today and will need a retention decision on a long-lived deployment. A reader
querying the table directly, outside the repository, gets every belief unless they filter,
and the schema cannot stop them.

**Obligations created:** the `Clock` port must be wired before module 6 writes its first
state, or the fallback in `fact_repository._database_now` becomes the de-facto path. A
retention policy for superseded beliefs, at whatever point one is needed.

### Reversibility cost
**Medium.** The columns and the trigger are droppable, but every superseded belief would be
lost at that moment, and any conclusion whose audit trail depended on one becomes
unreproducible.

---

## ADR-0033 — Migrations are paired forward/reverse raw SQL applied by a recorded runner

- **Date:** 2026-08-29
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** all
- **Affects interfaces:** `SchemaMigrator` (draft)

### Context
ADR-0015 excludes "any ORM or migration framework — migrations are numbered raw SQL", and its
negative consequences already name the price: "Raw SQL without a migration framework means
writing an apply-and-record runner by hand." Until this ADR that runner did not exist, so the
migration series was applied by PostgreSQL's init directory, which runs `*.sql` in lexical
order on first initialization.

Two things were wrong with that. It applies migrations **without writing any ledger**, so a
database whose schema exists and a database nobody has migrated look identical — and they
need different actions. And `deployment/README.md` described the series as "forward-only",
which means "irreversible during an incident".

The task that prompted this work asked for Alembic. Adopting it would need an ADR superseding
ADR-0015, a new pinned dependency, an amendment to `scripts/check_dependency_policy.py`, and
a rework of the compose wiring — and would still not give reversibility that paired files do
not.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Keep the init directory, forward-only | Rejected. No ledger, no reversal, and a silent divergence between schema and history. |
| B | Adopt Alembic, superseding ADR-0015 | Rejected. A new dependency and a compose rework to obtain a property option C already provides. Reconsider if the series ever needs branching or data migrations with Python logic — neither is true today. |
| C | **Paired `NNNN_x.sql` forward and reverse files, applied by a hand-written runner that records every application** | **Chosen.** |

### Decision
`deployment/sql/migrations/NNNN_<verb>_<subject>.sql` and
`deployment/sql/down/NNNN_<verb>_<subject>.sql`, same basename. Two directories rather than a
`.down.sql` suffix, because the suffix sorts wrong — `0003_x.down.sql` precedes `0003_x.sql`
lexically, so any tool reading a directory in name order runs the reversal first.

`causalog.persistence.postgres.migrator` applies them, one migration per transaction
(PostgreSQL has transactional DDL, so a failed migration leaves nothing behind), under a
fixed advisory lock so two concurrent runs serialize rather than race. Every application is
recorded in `schema_migration` with the version, the name, the **sha256 of the bytes
applied**, the instant, and the duration. **An applied migration whose file has changed is a
hard error naming the version** — not a skip, not a re-application.

Discovery is derived from the directory, never from a checked-in list, for the same reason
ADR-0030 derived pack discovery: a list is one more place to forget, and zero applied
migrations report exactly like a clean run.

`scripts/check_migration_pairs.py` fails the build on an unpaired file, an unmatched reverse,
a filename outside `NNNN_<verb>_<subject>.sql`, or a gap in the series. It ships `--self-test`
and is observed to reject before it scans (ADR-0019).

The init-directory mount is removed. `make up` no longer leaves a migrated database; `make
migrate` does.

### Consequences
**Positive:** the ledger is the authority on what schema exists, and it cannot silently
disagree with the files. Reversal is tested rather than assumed —
`tests/integration/test_migrations_up_down.py` applies, reverses to empty, and re-applies,
checking the system catalogue rather than whether the statements succeeded, because
`CREATE ... IF NOT EXISTS` hides residue. No new dependency.

**Negative:** `make up` followed by an application start now fails until `make migrate` runs,
which is a new step people will forget; the failure is loud but it is a failure. Every
migration costs a second file. The runner is ours to maintain, including the failure modes a
framework would have handled — it has no branching, no squash, and no data-migration helpers,
and adding any of those is real work rather than a flag.

**Obligations created:** the reverse file is part of the migration, not a follow-up. A
migration whose reversal is genuinely impossible needs an ADR saying so, not an empty file.

### Reversibility cost
**Low.** Adopting a framework later means importing the existing series as a baseline.

---

## ADR-0034 — The projection materializes every prd.md §47 label, and derived labels name the facts they are a function of

- **Date:** 2026-08-29
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Temporal Graph Builder, Propagation Analyzer, Visualization API
- **Affects interfaces:** `GraphProjection` (draft)

### Context
prd.md §47 lists eight node types and eleven relationship types. ADR-0001 requires every
projected element to trace to a PostgreSQL fact and calls a write with no backing fact a
defect. Three §47 labels have no fact table behind them: `Time` is not a row anywhere;
`Location` and `External Event` are renderings of `Entity` and `Event` rows whose ontology
type marks them as a place or as externally originated; `Recommendation` and `Intervention`
belong to modules 13 and 14, which do not exist.

"Exactly §47" and "every node traces to a fact" cannot both hold as written.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Project only fact-backed labels; record the rest as absent | Rejected by the product owner. It is the ADR-0029 precedent and would have been defensible, but it leaves the published §47 contract partly unimplemented. |
| B | **Project every §47 label, and state which are derived and what they are a function of** | **Chosen.** |
| C | Project everything except `Time` | Rejected. `Time` is the one that most needs an explicit account, and omitting it silently is worse than materializing it with one. |

### Decision
Every §47 label is materialized. Three are **derived**, and the derivation is recorded so it
is not mistaken for an exception to ADR-0001:

- **`Time`** — day buckets computed from `event.t_earliest`, in Python, from the event's own
  bounds and nothing else. A pure function of the event table: same events, same buckets,
  and the buckets participate in the projection content hash like every other element. An
  event with `UNKNOWN` precision is left unbucketed — placing it in a bucket would assert a
  day the source never recorded, which is imputation under another name.
- **`Location`** and **`ExternalEvent`** — **additional** labels on `Entity` and `Event`
  nodes, never replacements. Their counts are therefore **subsets** of `Entity` and `Event`,
  which the drift check must not treat as extra nodes; a self-test case pins that.
- **`Recommendation`** and **`Intervention`** — constrained, with no writer. An empty
  constrained label is honest: the shape is declared, nothing is invented, and the first
  write lands against a constraint rather than creating one.

The five payload kinds of prd.md §26 map onto the §47 inferred vocabulary explicitly, because
the two lists were written for different purposes and are different lengths:
`DIRECT`/`CONDITIONAL` → `CAUSES`, `CONTRIBUTING` → `AFFECTS`, `AMPLIFYING` → `AMPLIFIES`,
`INHIBITING` → `REDUCES`. `BLOCKS` and `RECOMMENDS` have no edge kind behind them today, and
that absence is recorded rather than filled with a default.

Every node key is `(content_address, namespace)`, not the address alone. Community Edition
serves one database, so staging is a property rather than a separate store — and a `MERGE`
keyed on the address alone would match the **live** node and overwrite it, which is exactly
the in-place mutation `docs/architecture.md` §3.3 step 2 forbids.

### Consequences
**Positive:** §47 is implemented as published, so a frontend traversal written against it
works. The observed and inferred edge families are structurally separate — observed edges
carry `dataset_version` and never `run_id`, inferred edges carry `run_id` under an existence
constraint — so dropping one run's inferences is incapable of touching observed structure.

**Negative:** `Time` nodes are index structure with a label, and a reader who takes §47 at
face value will assume they are facts; this ADR and `docs/data-model.md` are the only things
that say otherwise. `Location` and `ExternalEvent` being additional labels means any count
that sums labels double-counts, and that mistake is one line away in any new query. During a
rebuild the store holds two copies of the graph, and a failed rebuild leaves its staged copy
until the next one drops it.

### Reversibility cost
**Low-Medium.** Dropping a derived label is a Cypher statement and a rebuild. Changing the
node key away from the composite would require re-deriving every projection.

---

## ADR-0035 — `dataset_version` names the file and the mapping, in one legible composite

- **Date:** 2026-08-30
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Data Adapter, Schema Mapper, every module that reads an `OutputEnvelope`
- **Affects interfaces:** `RunKey` (frozen — **not changed**), `dataset_version` (§7, was `unset`)

### Context
`CONTEXT.md` §7 carried `dataset_version: unset`, which blocks freezing anything that depends
on it and leaves `run_id` uncomputable in practice. Module 1 has to set it.

The requirement that arrived with modules 1 and 2 was that the **mapping** participate in run
identity: two runs that read the same bytes through different bindings reached different
conclusions and are not comparable. `RunKey` is **frozen** at five fields with
`extra="forbid"` (ADR-0013, ADR-0025), so a sixth field is not an edit — it is an ADR, a
`docs/contracts.md` major bump, a migration on the run registry, and a coordinated update of
every consumer, for a system where nothing has yet been persisted.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Add `mapping_hash` as a sixth `RunKey` field | Rejected by the product owner. It is the structurally cleanest answer and would be the right one if `RunKey` were not frozen; the blast radius is a frozen-contract change to buy a property option B already delivers. |
| B | **Fold the mapping hash into `dataset_version`, as a legible composite** | **Chosen.** |
| C | Record `mapping_hash` outside `run_id` entirely | Rejected. Two runs with different mappings would then share a `run_id`, which is the determinism guarantee failing silently — the exact class of defect `run_id` exists to make impossible. |

### Decision
```
dataset_version = "<dataset_id>@<content_sha256[:16]>+map<mapping_digest[:16]>"
```
For the reference dataset today: `dataco@994b3c8d24049cc4+map7acd9e24866745fb`.

Built by `causalog.persistence.sources.delimited.compose_dataset_version`, which refuses a
mapping hash that does not carry its `map:` content-address prefix.

Deliberately **not** a single opaque digest of the two halves. Option B's cost is that
`dataset_version` no longer names the file alone; a legible composite is the only real
mitigation, because either half can then be recovered by eye or by `str.split` and checked
against `datasets/<id>.pin.json`, which records both in full alongside the byte count, the row
count, the header, the chosen codec and the `ontology_hash`.

`mapping_hash = digest(MAPPING, to_canonical_json(mapping))` — the ADR-0028 recipe exactly,
through the same two functions, over the resolved mapping so it is invariant to comments and
key sequence. `IdentifierPrefix` gains `MAPPING = "map"` **additively**; no existing address
recipe moves, so this is the ADR-0028 precedent and `docs/contracts.md` goes to 1.2.0.

### Consequences
**Positive:** `dataset_version` moves from `unset` to a defined, reproducible recipe, which
removes one of the two things blocking `run_id` from being computed for real. Re-mapping a
dataset correctly produces a different run. `RunKey` is untouched, so no frozen contract
moved and no migration was needed.

**Negative, and this is the cost of the choice — recorded as risk R-19.** Observed facts are
**dataset-scoped**, not run-scoped (ADR-0013), and that asymmetry is what makes "inference
never overwrites observation" structural. Folding the mapping into `dataset_version` means a
changed mapping now re-scopes **observed facts** as though the source file had changed. That
is arguably correct — a fact read through a different binding is a different fact — but it is
a semantic the frozen design did not intend, and it means the observed-fact store will hold
one copy per (file, mapping) pair rather than one per file.

### Reversibility cost
**Medium.** The recipe is one function and the pin decomposes it, so changing it later is a
re-derivation rather than a migration. But every `run_id` computed under this recipe moves,
so prior runs stop being comparable to subsequent ones and must not be presented as if they
were.

---

## ADR-0036 — `SchemaMappingSpec`: a declarative mapping, and a proposal that cannot load

- **Date:** 2026-08-30
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Schema Mapper, Data Adapter, Entity Extractor, Event Generator
- **Affects interfaces:** `SchemaMappingSpec` (draft), extension seam 3

### Context
Extension seam 3 (`docs/architecture.md` §5.1) named `ontology/packs/<domain>/mapping.yaml`
and specified only that unlisted columns are a hard error. Module 2 needs the whole schema.

The module brief additionally required auto-suggestion of mappings that "produces a proposal
for human confirmation, never a silent commitment". A suggestion mechanism that merely warns
is a suggestion mechanism whose warning is read once.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Transforms as expression strings evaluated at load | Rejected. Executable code in a data file, which ADR-0026 refused for the ontology DSL for the same reasons: it defeats review, diffing, and hashing, and it cannot be made deterministic by inspection. |
| B | **A closed transform registry, and a `status` field the loader refuses** | **Chosen.** |
| C | Suggestion writes `mapping.yaml` directly, with a warning | Rejected. See above. |

### Decision
`SchemaMappingSpec` (pydantic, normative, `draft`) declares eight namespaces:
`column_bindings`, `value_bindings`, `identity_bindings`, `temporal_bindings`,
`precedence_pairs`, `temporal_derivation_checks`, `referential_constraints`, and
`dropped_columns`. Three rules make it a mapping rather than a suggestion:

- **No expression strings.** `Transform` is a closed enum. A transform the registry cannot
  express needs a new member and an ADR.
- **No silent defaults.** `unmapped_value_policy` exists and admits exactly one value,
  `ERROR`. It is a field rather than an assumption so a future proposal to default an
  unmapped value has to change a declared contract in a diff somebody reads (risk R-07).
- **No unlisted columns.** Every header column is bound or appears under `dropped_columns`
  with a reason. "We did not map it" and "we did not notice it" are otherwise
  indistinguishable, and only one is a decision.

**`status: PROPOSED_UNCONFIRMED` is REFUSED by `load_mapping`.** `suggest_mapping` writes it;
a human removes it in a commit. That refusal is the entire confirmation mechanism.

`TemporalBindingSpec` declares `source_format` (never sniffed — the difference between
`%m/%d/%Y` and `%d/%m/%Y` is silent for eleven days of every month) and refuses
`precision: EXACT` outright, so imputation cannot enter through a configuration field.

Coverage is assessed against the resolved pack, and **every finding carries a
`downstream_consequence` with `min_length=1`** — the requirement is structural rather than a
habit. A derived event type's occurrence reports `NOT_RUNNABLE`, not clean: ADR-0029 puts its
reconstruction in module 4, so coverage of its instant **was not checked here**.

### Consequences
**Positive:** a mapping is data, diffable, hashable, and reviewable, and the engine's
dependence on it is a content address. What is unmapped is reported with what it breaks
rather than as a count. Auto-suggestion is genuinely advisory.

**Negative:** the closed transform registry will need extending, and each extension is an
ADR — deliberate friction that will feel disproportionate the first time a mapping needs one
transform the registry lacks. The suggester's precision is **unmeasured**: there is no
labelled ground truth for column-to-concept mappings anywhere in this repository, so a high
score means the signals agreed, not that the binding is right. That is not a gap to close by
tuning; it is the reason the proposal cannot load. Its match score is named `score` and not
`confidence` — LAW-EVIDENCE reserves that word for a decomposable vector, and
`scripts/check_confidence_is_a_vector.py` refused the first draft, which is how the field got
its name.

### Reversibility cost
**Low.** `SchemaMappingSpec` is `draft` and has one consumer.

---

## ADR-0037 — LAW-DOMAIN's scan covers `ingestion` and `extraction`, and its package list is itself checked

- **Date:** 2026-08-30
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** all of L2 and L3
- **Affects interfaces:** —

### Context
`scripts/check_domain_independence.py::IN_SCOPE_PACKAGES` did not include `ingestion` or
`extraction`. Modules 1 and 2 are the modules that come **closest** to the domain — they read
the mapping that names its columns — so the constraint "this module may reference the
ontology, never hardcoded column names" would have held by convention alone.

This is the ADR-0026 situation exactly: "the one package built to keep the domain out was the
one package not being checked for it."

### Decision
`ingestion` and `extraction` join the scan. The lint immediately reported **21 violations in
the freshly written modules 1 and 2** — `ordering`, `order`, `ordered` in prose, and DataCo
column names used as docstring examples in the suggester. All 21 were **reworded**, not
allowlisted: `.lawdomain-allowlist` is a pressure valve, and an empty allowlist is the healthy
state. Per ADR-0019 the `order` stem has no suffix exceptions, so the vocabulary is
"sequence", "sequenced", "precedence".

DataCo column names now appear in exactly three places, and nowhere else in the distribution:
`ontology/packs/dataco/ontology.yaml` and `mapping.yaml` (ontology **data**, exempt under
ADR-0010), and `causalog.persistence.sources.dataco` (outside the scan by design — see that
package's README for the three rules that make it the only location that works).

**The package list is now checked too.** `every_in_scope_package_is_really_scanned()` refuses
an entry that does not resolve or that contributes no file with a scanned suffix. A misspelled
package name scans zero files and reports clean, which is indistinguishable from a package
that was scanned and found innocent — the DEF-0001 shape, in the membership of a tuple. The
guard was observed to reject a planted `ingeston_typo` before being trusted.

### Consequences
**Positive:** the module brief's LAW-DOMAIN constraint is a check rather than a claim, and it
was observed to catch real violations in the code it was added for. The residual documented in
`docs/architecture.md` §1.5 is unchanged: none of the three lints catches a branch on a data
*value*.

**Negative:** writing about temporal precedence inside L2 and L3 now requires avoiding an
ordinary English word, which reads as pedantry until one remembers DEF-0001. One genuinely
domain-ish identifier survives — a docstring in the mapping DSL uses `finished_at`/`started_at`
as a worked example, and neither contains a banned stem. That is the residual hole, not a
loophole being used.

### Reversibility cost
**Low.** Two tuple entries and a rewording pass.

---

## ADR-0038 — Encoding is detected from both ends of the file, and precision is never asserted from a format

- **Date:** 2026-08-30
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Data Adapter, Schema Mapper
- **Affects interfaces:** `SourceReader`, `SourceDescription` (both draft)

### Context
The published DataCo distribution is not valid UTF-8. The obvious implementation is
`encoding="latin-1"` in the reader — which is correct today, silent when the publisher
re-encodes, and produces mojibake rather than an error when it is wrong. Every identifier
content-addressed over a mis-decoded string then differs from the identifier the correct
decoding would produce, and nothing anywhere reports it.

A second, subtler version of the same problem appeared once the file was actually read. See
DEF-0004.

### Decision
**Encoding is probed, never declared.** An ordered candidate list is strict-decoded against a
bounded prefix **and the tail**; the first clean candidate wins; the chosen codec, the
rejected ones, and the byte offset that defeated the strictest are all reported as
`DQ-SRC-ENCODING-FALLBACK`. `latin-1` must be last, because it decodes any byte sequence and
would otherwise win every probe and no fallback would ever be reported.

Both ends are read on purpose: a file that is ASCII for its first megabyte and single-byte
thereafter decodes cleanly from a prefix alone, which is a detector reporting success for a
check it did not perform. A test writes exactly that file and asserts the probe is not fooled.

**Precision is a measured claim, not a formatting one.** `TemporalBindingSpec` carries the
declared `source_format` and refuses `EXACT`; `PRECISION_SPANS` contains only entries that
widen; and `mapping.yaml` may declare a `temporal_derivation_check`, which the adapter
**measures** over every row — agreement rate plus a residual histogram — so a suspicion that a
column's precision is arithmetic on another column becomes a number rather than a note.

`SourceReader` gains `describe() -> SourceDescription` so module 1 can report *how* a source
had to be read without importing the reader that read it. Forbidden edge F4 permits only
`orchestration` to import `causalog.persistence.*`; the first draft of module 1 imported
`DelimitedTextSource` for a type annotation and `scripts/check_layers.py` rejected it, which
is the seam working.

### Consequences
**Positive:** a re-encoded source is noticed instead of silently mis-decoded. The one
independently observed instant in the reference dataset is bound at the precision it actually
carries, and the manufactured one is widened with the measurement that justifies it printed in
a committed report.

**Negative:** the probe reads two megabytes before the first record, and a file whose encoding
changes in its **middle** would still fool it. That is disclosed rather than fixed: decoding
the whole file twice to be certain would double the cost of every import to catch a case
nobody has observed.

### Reversibility cost
**Low.**

---

## DEF-0004 — DataCo is not day-granular, and the manifest was called verified before it was

- **Date:** 2026-08-30
- **Class:** B (a stated premise that the data contradicts) + A (doc lag)
- **Status:** fixed; the corrected premises are recorded rather than overwritten

### What was wrong

**First, the temporal premise.** `CONTEXT.md`, OQ-002, ADR-0007, ADR-0021 and risk R-14 all
rest on "DataCo timestamps are day-granularity". The module brief for modules 1 and 2 repeated
it. **Measured against the actual file, it is false in both directions:**

- `order date (DateOrders)` is **minute-granular**. 180,401 of 180,519 values carry a
  non-midnight time component. It is the one independently observed instant in the dataset.
- `shipping date (DateOrders)` *displays* a minute and **has not observed one**. Its value
  equals `order date` plus `Days for shipping (real)` whole days, exactly to the minute, in
  170,782 of 180,519 rows (94.61%). The remaining 9,737 rows miss by exactly **+12h (5,080)**
  or **−12h (4,657)** and by nothing else — and 9,737 is precisely the number of `Same Day`
  shipments. The instant is arithmetic under two construction rules.
- `Days for shipping (real)` equals the calendar-day difference in **180,519 of 180,519** rows.

So the project's *conclusion* — that intra-day precedence is largely unrecoverable — is right,
and its *reason* was wrong. The reason is not coarse precision. It is **manufactured
precision**, which is worse: a coarse column announces its limits, and a column that displays
`22:56` because a different column said `22:56` does not.

**Second, the doc lag.** `CONTEXT.md` §0 asserted that the DataCo column manifest "is verified
against it" while `columns.manifest.yaml` still read `UNVERIFIED_AGAINST_LOCAL_FILE` and
`tests/unit/ontology_runtime/test_dataco_pack_traceability.py` asserted that it did. Prose and
record disagreed, in the direction of claiming more verification than existed — the OQ-004 /
OQ-008 class, third instance.

**Third, found while fixing the first: the derivation audit measured the wrong thing.** Its
first implementation compared the two columns' **bound intervals**. `shipping date` is bound at
DAY precision, so its minutes were already discarded, and the audit reported 0.07% agreement
where the truth was 94.61% — a measurement whose result was created by the binding it was
supposed to justify. The headline text compounded it by asserting "in the great majority of
rows" regardless of what came back. Both are fixed: the audit reads **source** instants
through `parse_source_instant`, and the headline is gated on the measured rate with a
`DQ-TMP-DERIVATION-UNCONFIRMED` finding below the threshold.

### What changed
`mapping.yaml` binds `order date` at MINUTE and `shipping date` at **DAY**, with the reason in
the file. `mapping.yaml` declares the derivation, the adapter measures it, and the report
carries it as a headline constraint with its numbers. The manifest is flipped to `VERIFIED`
and the test that guarded the flip is **inverted and strengthened** rather than deleted:
`verified_by` must name a `dataset_version` that a real, readable pin carries, with a header
matching the manifest.

### Why it is recorded rather than tidied away
A premise four ADRs rest on turned out to be wrong about the one dataset in the repository,
and the check that revealed it was written to test something else. Overwriting the old
statement would delete the evidence that a widely-repeated claim about this dataset had never
been measured. R-14 stands, with a measured number and a corrected mechanism.

---

## ADR-0039 — An event type's emission condition is data in `mapping.yaml`, as a closed operator tree

- **Date:** 2026-08-30
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Schema Mapper, Entity Extractor, Event Generator
- **Affects interfaces:** `SchemaMappingSpec` (draft), `MappedRecord`/`MappedRecordBatch` (new, draft)

### Context
ADR-0029 declares every DataCo event type derived except one, and each derived type carries a
`derivation.basis` in **prose**: *"Implied by an Order Status of PROCESSING, COMPLETE or
CLOSED."* A human can audit that sentence and no code can execute it. The pack is otherwise
complete and machine-readable — participants, pre/postconditions, lifecycle transitions with
`triggered_by`, default confidences, process definitions — so the only thing standing between
module 4 and being ontology-driven is that nothing states, executably, **which records
witness which occurrence**.

Without it, module 4 has to hold nineteen `if` statements over DataCo column values, which
`docs/architecture.md` §5.3 promises it does not, LAW-DOMAIN's lint would refuse, and the
ontology-swap test could never pass.

A second, smaller gap: `docs/architecture.md` §2 names `MappedRecordBatch` as module 2's
output and module 3's input, and module 2 shipped no such type and nothing that applies a
mapping to a record.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Extend `EventTypeSpec` in `ontology.yaml` with an `emission` block | Rejected. The pack schema is **frozen** at 1.0.0 (ADR-0026), so this needs an amendment to a frozen contract, and it changes `ontology_hash` — which re-addresses every `Entity` and every `Event`, not merely `run_id`. It is also wrong on the merits: a condition over source values is a claim about ONE DATASET'S ENCODING, and putting it in the domain description would make the pack unreusable for a second source in the same domain |
| B | An `event_emissions` namespace in `mapping.yaml` | **Chosen.** The mapping is the dataset-specific file, `SchemaMappingSpec` is `draft` precisely awaiting its first consumer (`CONTEXT.md` §6), and conditions written over MAPPED symbols keep the pack reusable |
| C | Derive events by walking the lifecycle's `triggered_by` transitions | Rejected. It needs no new contract at all and covers seventeen of nineteen derived types — but it structurally cannot express `SHIPMENT_DELAYED` or `INVENTORY_SHORTFALL_DETECTED`, because neither changes a state. `SHIPMENT_DELAYED` is the single most causally interesting type in the pack, and a mechanism that cannot express the delay is not a mechanism for this project |
| D | An expression string evaluated at run time | Rejected on ADR-0026's grounds, unchanged: executable code in a data file defeats review, defeats hashing, and cannot be checked before it runs |

### Decision
**A `SchemaMappingSpec` carries `event_emissions`: at most one `EventEmissionSpec` per event
type, each declaring `when` (a `ConditionExpression` operator tree), `occurred_at` (an
`OccurredAtSpec`), and a `rationale`.** `mapping_schema_version` moves to 1.1.0.

`ConditionExpression` is a closed recursive operator set — `ALWAYS ATTRIBUTE CONSTANT EQUALS
NOT_EQUALS GREATER_THAN LESS_THAN IN IS_PRESENT IS_ABSENT AND OR NOT` — modelled directly on
`MeasurementExpression`. Leaves address values as `CONCEPT.attribute`, in **ontology**
vocabulary: which column supplies an address is `column_bindings`' business and which source
value means a symbol is `value_bindings`' business, so no source column name appears in a
condition or crosses into L3.

**An emission rule names no provenance class, and no participants.** The emitted event takes
the class its `EventTypeSpec` declares, and the pack refuses `OBSERVED` on a `DERIVED` type
(ADR-0029) — so a condition-tree emission has no path to an `OBSERVED` event, by construction
rather than by review. Participants come from the pack's `ParticipantSpec` resolved through
the mapping's one identity binding per entity type; restating them would create a second
place for the two to disagree. A role named by the event type's `postconditions` is a
`source_entity`; every other role is a `target_entity`; with no postconditions, `required`
decides.

`occurred_at` admits four policies and no fifth: `FROM_TEMPORAL_BINDING` (the mapping's own
interval, unchanged — the only policy an OBSERVED type may use), `BOUNDED_BETWEEN` (a window
between two observed instants, `INFERRED`, precision the coarser of the two),
`OFFSET_FROM` (an anchor advanced by a whole-day count the source recorded, `INFERRED`,
the anchor's precision), and `UNKNOWN`. None narrows and none manufactures a bound.

**Two structural additions this forced, recorded because they are module-boundary changes
rather than implementation detail.** `ingestion/schema_mapper/apply.py` supplies the missing
`MappedRecord` / `MappedRecordBatch` / `apply_mapping`, in module 2 because
`docs/architecture.md` §2 assigns them there. And the transform registry and interval builder
moved from `data_adapter/cleaning.py` to `schema_mapper/transforms.py`, verbatim and
re-exported: they interpret `Transform` and `TemporalBindingSpec`, which is mapping
semantics, and module 2's own record mapper reaching them through module 1 would have been a
circular import — a defect under `CONVENTIONS.md` §6, not a refactoring opportunity. Module
1's public surface is unchanged.

### Consequences
**Positive:** module 4 holds no domain vocabulary and adding an event type is two data edits,
which `tests/ontology/test_a_new_event_type_needs_no_code.py` proves by hashing the whole
distribution before and after. Coverage now reports, before a record is read, an event type
the pack declares that no rule can witness, and a literal compared against an attribute whose
value map cannot produce it — a typo in a symbol was previously a rule that silently never
fired.

**Negative, and it is the accepted cost:** `mapping_hash` changes, so `dataset_version`
changes, so `run_id` changes and the reference file had to be re-pinned and re-imported. That
is **risk R-19 realised**, exactly as ADR-0035 predicted when it folded the mapping into
dataset identity. `map:7acd9e24866745fb` becomes `map:a85a911e567f73c2` and
`dataco@994b3c8d24049cc4+map7acd9e24866745fb` becomes
`dataco@994b3c8d24049cc4+mapa85a911e567f73c2`.

**Negative:** R-16's surface widens. Nineteen emission rules are now nineteen more places a
pack can validate cleanly and be semantically wrong, and nothing mechanically compares a
rule to the prose basis it transcribes. The two are deliberately kept in different files so a
human can read them against each other, and coverage reports every derived emission at
`NOT_RUNNABLE` rather than clean, so the unchecked thing is visible rather than absent.

**Negative, disclosed at authoring time:** an `Order Status` of `ON_HOLD` satisfies the
declared basis of three event types, and no column records which state an order arrived from,
so all three fire and occurrences on those records are over-counted. `ORDER_RELEASED` cannot
be witnessed at all — its basis needs a history this source does not carry. Both are recorded
in the mapping and reported by the run rather than resolved by a judgement in a data file.

### Reversibility cost
**Medium.** The DSL is additive and `event_emissions` defaults to empty, so a mapping written
under 1.0.0 still loads. Undoing the identity churn does not: every artifact addressed under
the new `dataset_version` would have to be re-derived.

---

## ADR-0040 — A required event no field supports is recorded as a gap, not fabricated as an event

- **Date:** 2026-08-30
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Event Generator
- **Affects interfaces:** `EventQualityReport` (new, draft)

### Context
A process definition declares a canonical sequence. The DataCo pack declares `ITEM_PICKED`
and `ITEM_PACKED` as steps the business performs and the dataset omits entirely, and
`ORDER_RELEASED` as a step no column can witness. Something has to happen at those steps, and
the two available answers give the causal engine different worlds to reason over — which
makes this a decision rather than an implementation detail.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Emit the expected event with `UNKNOWN` precision and low confidence | Rejected as the DEFAULT, kept as a selectable policy. See below |
| B | Emit nothing; record the gap in the coverage report | **Chosen as the default** |
| C | Pick one and hard-code it | Rejected. The prompt that commissioned this module required the choice to be configurable, and it is right to: a consumer that needs a complete sequence with explicitly weak links has a real need, and it is not the same need as a consumer building a causal graph |

### Decision
**`MissingEventPolicy.RECORD_GAP` is the default: no event is emitted and the gap is reported
per process, per step, with the count of instances expecting it and whether ANY record could
ever witness it.** `EMIT_GAP_MARKER` is implemented and selectable; a marker carries the
unbounded `UNKNOWN` interval, the pack's declared provenance class, and a single
`rule_support` component of exactly **0.0**. The active policy is stamped into the
`EventQualityReport`, because it changes what the causal engine can conclude and a consumer
holding the events must not have to ask how the run was invoked.

The reasoning for the default, stated so it can be argued with: a fabricated event is a real
node the causal engine can attach edges to. One with no supporting field has `UNKNOWN`
precision, so `core.temporal.verdict` returns `UNDETERMINED` for every pair it touches and it
can never be promoted to `INFERRED` (`CONVENTIONS.md` §10). It therefore adds graph mass
carrying no verifiable content, while looking from the inside like a more complete history
than the dataset supports. The information it would have carried — that the process expects a
step and the source does not witness it — is preserved in the coverage report, where it can
be read without being reasoned over. Module 5 already owns timeline gap markers (risk R-02),
which is the layer where a gap belongs.

Under `EMIT_GAP_MARKER`, a marker is emitted only for a step **no rule can witness**. A step
that CAN be witnessed and was not is a fact about that instance, and marking it would assert
an occurrence the dataset actively did not record — a different and stronger claim than "no
field could ever record this".

### Consequences
**Positive:** the default event store contains only occurrences some field witnesses, and the
process shape is fully legible in a report that states its own coverage. Both policies are
tested and both are deterministic.

**Negative:** a consumer walking events alone sees a sequence with holes and has to read the
coverage report to learn which holes are properties of the source. That is a documentation
burden the report is designed to carry, and it is the burden `EMIT_GAP_MARKER` exists to
lift for consumers who would rather have the marker.

**Negative:** zero is a confidence value, and a downstream ranker that multiplies by
confidence will treat a marker as weightless. That is intended and is why the number is zero
rather than small.

### Reversibility cost
**Low.** The policy is a parameter; changing the default changes one enum member and the
artifacts of any run made under the old one.

---

## ADR-0041 — An emitted event's provenance class is the one its ontology type declares

- **Date:** 2026-08-30
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Event Generator
- **Affects interfaces:** `Event` (frozen; no field changes)

### Context
`docs/architecture.md` §2 states module 4's invariants as: *"Every event carries a non-empty
`evidence_record_ids`, exactly one `TimeInterval`, and `provenance_class = OBSERVED`."*

That last clause is false against ADR-0029, which declares one `OBSERVED` event type in the
DataCo pack and nineteen `DERIVED` ones that may never claim `OBSERVED` provenance. The
document predates the pack. Writing module 4 to the document would put nineteen fabricated
observations into the system of record with real columns standing behind them; writing it to
the ADR and quietly leaving the document wrong would leave the next session reading a
contract the code does not keep — the OQ-004 / DEF-0004 class, a fourth instance.

No frozen type changes. `Event.provenance_class` already admits every class; only the
document's claim about what module 4 puts in it is wrong.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Implement to the document | Rejected. It contradicts an accepted ADR and would violate LAW-PROVENANCE on nineteen event types |
| B | Implement to ADR-0029 and edit the document silently | Rejected. `CONVENTIONS.md` §13: a contradiction between a decision and a document is resolved by an ADR, not by an edit nobody reviews |
| C | Implement to ADR-0029 and correct the document by ADR | **Chosen** |

### Decision
**Module 4's invariant is corrected to: an emitted event's `provenance_class` is the one its
ontology `EventTypeSpec` declares, and no heuristic may produce an `OBSERVED` event.** The
`OBSERVED` guarantee that survives is narrower and is about evidence rather than provenance:
every emitted event carries a non-empty `evidence_record_ids` and exactly one `TimeInterval`.

This is enforced structurally, not by review. Every `Event(...)` construction in
`event_generator` passes `provenance_class=spec.provenance_class` and nothing else, asserted
over the **AST** by `tests/law/test_derived_events_are_never_observed.py`, which is
additionally observed to reject a planted construction that hard-codes a class (the DEF-0001
rule: a check with only positive evidence is not evidence).

### Consequences
**Positive:** the document and the code agree, and the disagreement is on the record instead
of being overwritten. LAW-PROVENANCE holds by construction at the module ADR-0004 calls the
highest-risk in the system.

**Negative:** on the reference dataset the great majority of events are `INFERRED` rather
than `OBSERVED`. That is not a regression — it is what the source supports, made visible.
Any downstream module that assumed module 4's output was uniformly observed was assuming
something that was never true of this dataset.

### Reversibility cost
**Low** for the document. **None** for the behaviour: reversing it would violate ADR-0029.

---

## ADR-0042 — `Timeline` lands as a `core` type; `IdentifierPrefix` gains `TIMELINE`

- **Date:** 2026-08-31
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Timeline Builder
- **Affects interfaces:** `core.identifiers.IdentifierPrefix` (frozen; additive member),
  `Timeline`, `TimelineEntry` (new; `core`, draft)

### Context
Module 5 needed its declared output type, `Timeline`, which did not exist: the interface
registry carried it as `draft`, owned by Timeline Builder, with no fields specified
(`CONTEXT.md` §6). Two questions had to be settled before writing it: where the type lives,
and how it gets a content-addressed identifier.

**Where it lives.** `Timeline` is consumed by more than its author — State Engine and,
later, Candidate Cause Generator (`CONTEXT.md` §6) — which is exactly the shape `Event`,
`State`, and `Transition` already have: authored by one module, declared in `core` so every
consumer imports one canonical definition rather than each other's package. Declaring it
inside `graph_engine.timeline_builder` instead would have made every consumer of a
`Timeline` import a package ranked above them the moment a second consumer existed.

**Identifiers.** `IdentifierPrefix` is a closed, frozen enum (`core/identifiers.py`) with no
member for a timeline. ADR-0028 and ADR-0035 already added `ONTOLOGY` and `MAPPING` the same
way: additively, with no existing recipe moved.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Define `Timeline` inside `graph_engine.timeline_builder`, hand State Engine a duck-typed structure | Rejected. Reintroduces exactly the cross-package-import problem `core`-hosted canonical types exist to avoid, and gives `Timeline` no `address()` recipe to be content-addressed by |
| B | Define `Timeline` in `core`, following the `Event`/`State`/`Transition` precedent | **Chosen** |
| C | Give `Timeline` a hand-assigned identifier instead of a content address | Rejected outright. Every other artifact in the system is content-addressed (`CONVENTIONS.md` §9); a `Timeline` would be the one exception, and a rerun over identical input would then mint different timeline identifiers depending on what an accumulator happened to be handed first |

### Decision
**`Timeline`, `TimelineEntry`, `TimelineEntryKind`, and `TimelineView` are declared in
`causalog.core.types.timeline`, exported from `core.types` alongside `Event`/`State`/
`Transition`.** `IdentifierPrefix` gains `TIMELINE = "tml"`, additively; no existing prefix
value moves. `Timeline.address()` follows the established recipe shape: `ontology_hash |
view | process_definition_id | subject_entity_ids(sorted) | event_ids(sorted)`. Gap markers
are excluded from the payload — they are derived from the process definition and the placed
events, not an independent fact, so their presence never changes a timeline's identity.

`TimelineEntry.sequence_provenance` (see ADR-0043 for its content) is likewise a new field
on a still-`draft` type, so it required no ADR of its own to add; only the frozen
`IdentifierPrefix` change and the fact of `Timeline`'s existence needed to be recorded here.

### Consequences
**Positive:** every consumer of a `Timeline` — State Engine today, Candidate Cause Generator
later — imports one definition from `core`, matching the pattern the rest of the pipeline
already established. `Timeline.timeline_id` is reproducible from its content alone.

**Negative:** `core` now defines a type whose only current author is a single module
(Timeline Builder), which is the same shape `Event` had when `ADR-0025` froze `core` "early,
against anticipated rather than observed use" (that ADR's own admitted cost). `Timeline`
stays `draft`, unlike `Event`, so this repeats the shape without repeating the freeze.

### Reversibility cost
**Low.** `IdentifierPrefix` additions are one-way only in the sense that a shipped prefix
should not be reassigned once artifacts exist under it; nothing yet exists under `tml:`.

---

## ADR-0043 — Timeline adjacency's tie-break rule, and how State Engine carries the
resulting uncertainty

- **Date:** 2026-08-31
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Timeline Builder, State Engine
- **Affects interfaces:** `TimelineEntry.sequence_provenance` (new field, draft type),
  `State.held_over` usage (no field change; a usage convention)

### Context
Two adjacent events on a timeline can have temporally incomparable intervals — identical or
overlapping bounds, the day-granularity tie case ADR-0007 and R-14 already name.
`docs/architecture.md` requires a Timeline's sequencing to be "total and deterministic," but
`core.temporal.verdict` is explicit that overlap is `UNDETERMINED`, never resolved by a tie
broken on a bound or a position (`core/temporal.py` module docstring). Rendering a timeline
at all therefore requires SOME deterministic position for a tied pair, and the type system
gives no way to represent "unordered" — `Timeline.entries` is a sequence. The two facts
together mean a tie-break has to exist, and it has to be visibly marked as an assumption
rather than left indistinguishable from a verified order (the task commissioning this module
required exactly that: "the rule must be explicit, stable, and marked as an assumption, not
a fact").

A second, related question surfaced building State Engine: a `State.held_over` interval's
outer bound is normally the next transition's causing-event timestamp. When that next event
ties or overlaps with the one that opened the state, pinning the boundary to it anyway would
assert an ordering the data does not support — silently converting the same kind of
uncertainty into a confident-looking number.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Refuse to sequence a tied pair at all (raise) | Rejected. A day-granularity dataset makes ties common (R-14); refusing to build a timeline over ordinary data is not a usable default, and `docs/architecture.md` requires total, deterministic sequencing |
| B | Tie-break by an arbitrary but undocumented rule (e.g. dict iteration order) | Rejected outright — nondeterministic across runs/interpreters, and even if pinned, indistinguishable from a real order to any reader |
| C | Tie-break by `event_id` (content hash), marking the affected adjacency `ASSUMED` | **Chosen** |
| D (state boundaries) | Pin `held_over.t_latest` to the next event's timestamp regardless of verdict | Rejected. Produces a `held_over.provenance = OBSERVED` claim about a boundary the data cannot support |
| E (state boundaries) | Widen the interval and mark `held_over.provenance = ASSUMED` when the bounding verdict is not `CERTAIN` | **Chosen** |

### Decision
**Sequencing (Timeline Builder).** Events are sorted by `(t_earliest, t_latest, event_id)`
(unchanged, `CONVENTIONS.md` §11). For each adjacent pair, `core.temporal.verdict` is
consulted: `CERTAIN` sets `TimelineEntry.sequence_provenance = OBSERVED`; anything else
(`UNDETERMINED`, and `VIOLATION` if it were ever reachable post-sort) sets it to `ASSUMED`.
The `event_id` ordering is what makes the tie-broken position **stable and reproducible**
across runs of identical input — it is a rendering choice, not a claim about which event
truly happened first, and `ASSUMED` is what marks that distinction on the artifact itself
rather than only in prose.

**State boundaries (State Engine).** A state's `held_over.t_latest` is the causing event of
the transition that follows it, UNLESS the verdict between that event and the one that
opened the state is not `CERTAIN`, in which case the interval is widened (kept at the next
event's `t_earliest` as the practical bound, since no finer information exists — see
`graph_engine/state_engine/replay.py` for the exact construction) and
`held_over.provenance` is set to `ASSUMED`. The state's own `provenance_class` stays
`OBSERVED` throughout: the transition genuinely happened, only the exact instant it
happened relative to its neighbour is uncertain. `held_over.provenance` never becomes
`INFERRED` here — `docs/architecture.md` forbids `INFERRED` provenance anywhere in State
Engine's output, and `core.temporal.verdict` already refuses to call an `INFERRED` interval
`CERTAIN` for the same reason (ADR-0021).

Both mechanisms are counted, not just flagged inline: `TimelineQualityReport.
uncertain_sequence_timelines` and `StateQualityReport.uncertain_boundary_states`.

### Consequences
**Positive:** every timeline is total and deterministic as required, and nothing downstream
can mistake a tie-broken position for a verified one without deliberately ignoring
`sequence_provenance`/`held_over.provenance`. `core.derivation.current_state`'s
overlap-contradiction raise is preserved untouched for genuine contradictions (verified by
`tests/unit/graph_engine/state_engine/test_as_of.py::
test_current_state_still_raises_on_a_genuine_contradiction`) — this ADR's widening only
prevents *routine* adjacent-transition boundaries from tripping that guard; a state machine
that is actually self-contradictory still trips it.

**Negative:** an `ASSUMED`-tie-broken position is still A position — a reader who does not
check `sequence_provenance` sees an ordinary-looking sequence. This is the same shape of
residual risk R-16 already accepts for pack semantics: the marker exists and is inspectable,
but nothing forces a reader to inspect it.

**Negative:** on a dataset where ties dominate (the day-granularity case R-14 already
flags for candidate edges), `uncertain_sequence_timelines`/`uncertain_boundary_states` may
be large. Disclosed, not tuned away — matching R-14's own resolution.

### Reversibility cost
**Low.** The tie-break function and the widening rule are both pure and local to their
modules; changing either changes output for affected runs but touches no frozen contract.

---

## ADR-0044 — The rule DSL: five rule kinds as payload types, a closed condition tree, no escape hatch

- **Date:** 2026-09-01
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Rule Engine (L5, mechanism), Candidate Cause Generator (future consumer)
- **Affects interfaces:** `RulePack` (seam 4, draft), `causalog.rule_engine.dsl` (new)

### Context
prd.md §46 is categorical: "Never hardcode logistics logic into source code." Seam 4 of
`docs/architecture.md` §5.1 has been `draft` with no fields specified since the scaffold,
and `CONTEXT.md` §7 has carried `rule_pack_version: unset` — the last unset `RunKey` input,
so no `run_id` could be minted at all.

Two questions had to be settled before writing a line of the pack.

**How a rule expresses a condition.** `causalog.ingestion.schema_mapper.dsl` already ships a
`ConditionExpression` / `ConditionOperator` pair with exactly the discipline wanted: closed
operator set, no expression strings, no callables (ADR-0039). `rule_engine` is L5 and
`ingestion` is L2, so importing it is a legal downward edge.

**What a rule kind is.** prd.md §26 names five causal edge categories, and
`core/types/causal_edge.py` already models them as payload *types* rather than string
labels (ADR-0022). A rule pack that named its kinds as free strings would immediately be a
second, weaker vocabulary for the same five things.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Import `schema_mapper`'s `ConditionExpression` into the rule DSL | Rejected. Legal but wrong: its addresses are `CONCEPT.attribute` over *records* — a mapping question — whereas a rule condition addresses a **role-bound participant of a matched event**, which is a different address space entirely. Sharing the type would force one of them to carry an address form the other cannot evaluate, and the first divergence would be a silent mis-evaluation rather than a type error |
| B | Lift a shared condition tree into `core/` | Rejected for V1. `docs/contracts.md` is frozen at 1.3.0; adding a type that two layers evaluate differently is not a shared contract, it is a shared name. Revisit if a third address space appears |
| C | A rule DSL with its own closed condition tree over `RoleAddress` | **Chosen** |
| D | Rule kinds as free strings, validated by convention | Rejected. ADR-0022 already ruled on this shape for `CausalEdge`; a pack repeating the mistake would be the second vocabulary for prd.md §26 |
| E | Allow an expression string or a Python callback reference for "hard" rules | Rejected outright. `ontology/README.md`'s "Forbidden" paragraph applies verbatim: a rule that needs an escape hatch needs a new operator and an ADR. An `eval` in a rule pack makes the pack executable code, which is what prd.md §46 forbids |

### Decision
**`causalog.rule_engine.dsl` declares its own normative pydantic models**, at
`rule_pack_schema_version` **1.0.0**, exactly as `ontology_runtime.dsl` and
`schema_mapper.dsl` are normative for their seams.

`ConditionExpression` carries the closed operator set `ALWAYS`, `ATTRIBUTE`, `CONSTANT`,
`EQUALS`, `NOT_EQUALS`, `GREATER_THAN`, `LESS_THAN`, `IN`, `IS_PRESENT`, `IS_ABSENT`, `AND`,
`OR`, `NOT`, over a `RoleAddress(binding, role, attribute)` — `binding` naming which matched
event of the rule the address refers to. **There is no expression string, no callable
reference, and no plugin hook anywhere in the schema.**

Five rule bodies, discriminated by `kind`, mirroring prd.md §26 and the `CausalEdge` union:
`CAUSAL`, `CONDITIONAL`, `JOINT`, `AMPLIFICATION`, `INHIBITION` — plus `CONSTRAINT`, which
has no edge counterpart because it produces a **prohibition** rather than a claim.
`CONSTRAINT` is the sixth kind and is deliberately not a "negative causal rule": pruning an
impossible candidate is a different act from proposing a possible one, and collapsing them
would make a constraint rankable.

`TemporalWindow` carries `min_separation_seconds` / `max_separation_seconds` with an
explicit `inclusive` flag on each end, so boundary semantics are **data** and can be tested
rather than being a convention buried in a comparison operator.

### Consequences
**Positive:** the pack is inert data. A reader can audit every rule without reading Python.
The five prd.md §26 categories have one vocabulary across `core` and the pack.

**Negative:** two condition trees now exist in the distribution with a similar shape and no
shared code, and they can drift. The drift is bounded — each is validated by its own tests
and neither can evaluate the other's addresses — but it is real, and it is the cost of
option C over option B. Recorded rather than hidden.

### Reversibility cost
**Medium.** `rule_pack_schema_version` is authored into the pack, so a DSL change follows
the `docs/ontology.md` §5 procedure: ADR, version bump, every pack updated in the same
commit. Every `rule_pack_hash` moves, and therefore every `run_id` (ADR-0013).

---

## ADR-0045 — A rule's `knowledge_provenance` is not a `ProvenanceClass`

- **Date:** 2026-09-01
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Rule Engine
- **Affects interfaces:** `causalog.rule_engine.dsl.KnowledgeProvenance` (new)

### Context
The rule pack must record, per rule, where the knowledge came from: an expert's judgement,
an observation about this dataset, or an assumption nobody has evidence for. LAW-PROVENANCE
already defines a closed five-member `ProvenanceClass`, and reaching for it here is the
obvious move.

It is also wrong, and the wrongness is not cosmetic. `ProvenanceClass` answers *how a fact
came to be known* and is combined by `core.aggregation.combine` under the weakest-input
rule (`docs/contracts.md` §4). A rule is not a fact; it is a **policy about facts**. If a
rule carried `ASSUMED`, then a firing of that rule over two `OBSERVED` events would invite
exactly one arithmetic — combine them — and the result would silently claim that an
assumption about the world is the same kind of thing as an unrecorded timestamp.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Reuse `ProvenanceClass` on rules | Rejected. Invites `combine()` across two different questions and makes a rule's pedigree indistinguishable from an assertion's provenance |
| B | A free-text `source` field per rule | Rejected. Unaggregatable, unreportable, and unenforceable — the coverage report could not count assumptions |
| C | A separate closed enum, local to the rule DSL | **Chosen** |

### Decision
**`KnowledgeProvenance` is a closed enum in `causalog.rule_engine.dsl` with three members:
`DOMAIN_EXPERTISE`, `DATASET_OBSERVATION`, `ASSUMPTION`.** It never participates in
`core.aggregation.combine` and is never written into an artifact's `provenance_class`.

Every rule additionally carries a non-empty `evidence_basis`. For `ASSUMPTION` the loader
enforces it separately and refuses a rule that leaves it blank: an assumption whose content
nobody wrote down is not inspectable, and prd.md's whole premise is that a user sees what
the system is assuming.

### Consequences
**Positive:** "how many of these rules are assumptions?" is a countable, reportable
property. The coverage report prints the ratio, so an assumption-heavy pack cannot be
mistaken for an evidence-backed one.

**Negative:** two provenance vocabularies exist in the system and a reader must know which
question each answers. `GLOSSARY.md` carries both, side by side, with the distinction
stated.

### Reversibility cost
**Low.** The enum is authored in pack data; renaming a member is a pack edit plus a schema
version bump.

---

## ADR-0046 — `VocabularyView` in `core`; `IdentifierPrefix` gains `RULE_PACK`

- **Date:** 2026-09-01
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Rule Engine, Entity Extractor / Event Generator (adapter host)
- **Affects interfaces:** `core.ontology_view` (additive), `core.identifiers.IdentifierPrefix`
  (frozen; additive member), `docs/contracts.md` → 1.4.0

### Context
Static rule validation has to answer "does this rule name a declared event type?" — and
forbidden edge F3 (`docs/architecture.md` §1.4) blocks every package at L4–L10 from
importing `ontology_runtime`. `rule_engine` is L5. The rule engine therefore **cannot read
the ontology**, and must not be given a way to.

This is not a new problem. `core/ontology_view.py` already exists for exactly it: plain,
DSL-independent views of ontology-declared configuration, produced by an adapter in
`extraction` (one of the three packages F3 permits) and consumed at L0 where every layer may
import from. Its own docstring names the pattern.

Separately, a rule pack needs a content address, and `IdentifierPrefix` has no member for
one.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Let `rule_engine` import `ontology_runtime` and add an F3 exception | Rejected outright. F3 has no exceptions by construction (`docs/architecture.md` §1.1: "no configuration flag that relaxes it"), and the exception would be granted to the one package whose entire content is domain policy |
| B | Validate rule references in `scripts/` only, and give the engine nothing | Rejected as the *sole* mechanism. The loader must be able to report `NOT_RUNNABLE` versus checked, which requires it to accept a vocabulary when one is available |
| C | Extend `core/ontology_view.py` with vocabulary views, produced by `extraction.ontology_adapters` | **Chosen** |

### Decision
**`core/ontology_view.py` gains `ParticipantView`, `EventTypeView`, `EntityTypeView`,
`RelationshipTypeView`, and `VocabularyView`**, each canonically sorted.
`extraction/ontology_adapters.py` gains `vocabulary_of(pack) -> VocabularyView`, beside the
existing `process_definitions_of` / `lifecycles_of` / `duration_measurements_of`. That module
remains the single sanctioned crossing point.

**`IdentifierPrefix` gains `RULE_PACK = "rul"`**, additively — the same shape as ADR-0028
(`ONTOLOGY`), ADR-0035 (`MAPPING`), and ADR-0042 (`TIMELINE`). `rule_pack_hash` is
`digest(RULE_PACK, to_canonical_json(pack))`, reusing `core.serialization` and
`core.identifiers` so there is one hashing scheme and no second path.

`docs/contracts.md` moves to **1.4.0**. The change is purely additive: no frozen type gains,
loses, or retypes a field; no address recipe moves; no identifier in any store changes;
**`engine_version` does not bump.**

### Consequences
**Positive:** F3 holds without an exception. The rule engine can validate its references and
still be structurally incapable of reading domain semantics.

**Negative:** `VocabularyView` is a third partial projection of the pack, and a projection
that omits a field cannot validate against it. What it omits is stated in its docstring
rather than discovered.

### Reversibility cost
**Low** for the views. **One-way** for the prefix in the usual sense: a shipped prefix must
not be reassigned once artifacts exist under it. Nothing yet exists under `rul:`.

---

## ADR-0047 — Constraints beat generators; conflicts are reported, not resolved; a firing without a trace cannot be constructed

- **Date:** 2026-09-01
- **Status:** accepted
- **Supersedes:** —
- **Affects modules:** Rule Engine
- **Affects interfaces:** `causalog.rule_engine.trace.RuleFiring`,
  `causalog.rule_engine.conflict.ConflictReport` (both new)

### Context
Two rules can disagree: a `CAUSAL` rule proposes that A produced B for some binding, and a
`CONSTRAINT` rule holds that the entity in that binding could not have produced B at all.
`CONVENTIONS.md` §7 forbids resolving that at runtime by preference, and the `RulePack`
port's own docstring says a contradictory pack raises `RuleConflictError` **at load time,
never a runtime coin-flip**.

But not every disagreement is statically detectable. A constraint whose applicability
depends on an entity's observed state cannot be compared against a causal rule's pattern
without the facts. Something has to happen when the facts arrive and the two disagree.

Separately, the task this module exists for states that a rule firing with no explanation is
a defect. "Defect" is worth what the code makes it worth.

### Options considered
| Option | Description | Why rejected / chosen |
|---|---|---|
| A | Let the higher rule weight (`base_strength`) win | Rejected. A weight is a strength-of-belief about a *claim*; a constraint is a statement of impossibility. Comparing them is a category error, and it would make impossibility purchasable with a large enough weight |
| B | Author precedence per rule pair in the pack | Rejected. `n²` policy nobody will maintain, and the first unmaintained pair is a silent coin-flip |
| C | Constraints beat generators, unconditionally and documented, with the conflict reported | **Chosen** |
| E | Detect the constraint/generator pair statically and refuse the pack | Rejected once implemented and tested against the real DataCo pack, which it refused. See the Decision below |
| D | Emit both and let the Confidence Scorer sort it out | Rejected. Passes a known contradiction downstream as if it were evidence |

### Decision
**Statically detectable contradictions raise `RuleConflictError` at load**, as the port
already requires. Exactly two shapes are decidable without facts, and the loader claims no
others:

- **Opposed modifiers** — an `AMPLIFICATION` and an `INHIBITION` naming the same target
  rule, the same modifier event type and the same linkage, with no condition on either. One
  trigger is asserted to raise and lower one claim's magnitude at once, so which applies
  depends on evaluation sequence. That is the coin-flip `CONVENTIONS.md` §7 forbids.
- **Duplicated rules** — two enabled rules identical in kind, pattern, linkage and
  condition, differing only in identity or weight. Both fire on every match, so every
  candidate they propose is counted twice by two rules nobody meant to be two.

**A constraint and a generator naming one event type are explicitly NOT a contradiction**,
and a first draft of this loader wrongly treated them as one. A constraint is scoped to an
entity in a named state — "a line already withdrawn cannot be dispatched" — and a generator
is not. They are complementary: the generator proposes, the constraint prunes the subset the
state rules out. Refusing that pair at load would refuse the exact pack this seam exists to
support, and would push authors toward constraints too weak to prune anything. The error is
recorded here rather than quietly corrected, because the appealing version of this check is
the wrong one and the next author will reach for it too.

**Fact-dependent disagreements are resolved at evaluation by one documented policy:
constraints beat generators.** A generated firing whose bindings and effect are prohibited
by a constraint that fired over the same bindings is **suppressed**.

**The suppression is reported, never silent.** Every suppression becomes a `ConflictReport`
entry naming both rule identifiers, the shared bindings, and the suppressed firing itself.
The report is returned alongside the surviving firings. Reporting the conflict rather than
resolving it silently is the requirement; the precedence policy decides what the *graph*
gets, and the report decides what the *operator* sees, and those are not the same decision.

**A firing cannot be constructed without its trace.** `RuleFiring` validates at construction
that `evaluated_conditions` is non-empty for any rule whose condition tree is not `ALWAYS`,
and that every matched event identifier appears in the bindings. A firing that cannot
explain itself raises `ContractViolationError`, so it does not exist to be persisted,
scored, or displayed. This is the enforceable reading of "a rule that cannot explain itself
may not fire"; a lint or a review would leave it as an intention.

### Consequences
**Positive:** the precedence policy is one sentence, written once, and asserted by a test. A
suppressed candidate is visible rather than absent — which matters because an absent edge is
the one kind of error this system cannot otherwise report (`docs/architecture.md` §8 risk 2).

**Negative:** constraint authorship becomes high-leverage. A wrong constraint silently
removes true candidates, and the report shows the suppression but cannot say the constraint
was wrong. This is the same class as risk R-16 — a valid pack can be a wrong pack — and it
is tracked there rather than given a new number.

### Reversibility cost
**Low.** The policy is one comparison in one module; the report is additive.
