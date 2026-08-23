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
- **Status:** accepted
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
reject, not merely to pass.** All four law scripts now ship `--self-test` asserting both
directions, and each CI job runs it before its scan.

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
review probes as permanent regression cases; `--self-test` on all four law scripts and in
all four CI jobs; negative pytest cases for the law-copy and dependency-policy checks;
`CONVENTIONS.md` §6, `CONTEXT.md` R-10 and OQ-006, and `docs/architecture.md` §1.5 restated.

### Reversibility cost
**Low** for the matcher. **High** for what it protects — see ADR-0002. The four reworded
lines are the entire migration cost of this change.

---

## ADR-0007 — LAW-TIME is evaluated over intervals, and temporal ambiguity is retained rather than resolved

- **Date:** 2026-08-23
- **Status:** accepted
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
