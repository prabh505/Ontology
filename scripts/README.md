# `scripts/`

**Single responsibility:** hold the executable checks and operations that turn the Five
Inviolable Laws and the Definition of Done from prose into build outcomes.

Every script here is standard-library only, so that no dependency upgrade can silently
disable a law (ADR-0016).

**Every law check ships `--self-test` and runs it in CI before its scan (ADR-0019).** A
check that has only ever been observed to pass is not evidence that a law is enforced:
DEF-0001 is a lint that passed review for the life of the scaffold while catching almost
nothing, because its self-test asserted the wrong invariant. `make laws` runs every
self-test first, then every scan.

| Script | Enforces | Exit codes |
|---|---|---|
| `check_domain_independence.py` | LAW-DOMAIN (`CONVENTIONS.md` §6, ADR-0019). Stem-prefix matching, so identifier forms (`warehouse_id`, `orders`, `WAREHOUSE_TABLE`, `customerName`) are caught. `--self-test` proves 24 vocabulary forms fire, 17 non-domain words stay clean, and **no claimed false positive hides a banned stem** — the DEF-0001 root cause. | 0 clean · 1 violation |
| `check_layers.py` | The layer map and forbidden edges F1–F9 (`docs/architecture.md` §1, ADR-0016). `--self-test` proves each of F1–F9 rejects a synthetic import and 6 permitted edges do not. | 0 clean · 1 violation |
| `check_dependency_policy.py` | Exact pins, ADR-0015 coverage, the ADR-0003 import ban. `--self-test` proves a range pin, an ADR-less package, and a blocked declaration each fail. | 0 clean · 1 violation |
| `check_law_copies.py` | The Five Laws are byte-identical in `CONTEXT.md` §2 and `CONVENTIONS.md` §1. `--self-test` proves a planted divergence and a missing law are both detected. | 0 clean · 1 diverged |
| `check_governance_consistency.py` | The governance record is internally consistent: no question both struck and open, every closure names an existing ADR, supersessions acknowledged both ways, and **no open question already answered by an accepted ADR** — the class that produced the OQ-004 and OQ-008 slips. | 0 clean · 1 inconsistency |
| `check_confidence_is_a_vector.py` | LAW-EVIDENCE (`docs/contracts.md` §5, ADR-0009). A confidence-named symbol bound to a numeric type is the unexplained number prd.md §49 forbids. `--self-test` proves 12 bare-float shapes fire, 12 legitimate lines stay clean, and **no claimed false positive hides a violation**. | 0 clean · 1 violation |
| `check_metrics_are_declared.py` | ADR-0026, ADR-0031 (`CONVENTIONS.md` §6a). A domain metric is declared in the pack as a `MeasurementExpression` tree and walked, never recomputed in engine code. AST-based with intra-scope **taint tracking**, so a metric laundered through an unnamed variable is still caught, and a metric compared against a **numeric literal** is refused as a hard-coded policy constant. `--self-test` proves 20 shapes fire and 18 legitimate lines stay clean. | 0 clean · 1 violation · **2 NOT-YET-RUNNABLE** |
| `export_ontology_schema.py` | `ontology/_schema/ontology.schema.json` is what the normative pydantic models produce (ADR-0026). `--self-test` proves a stale schema is rejected and a current one accepted. | 0 current · 1 stale |
| `check_determinism.py` | Two runs of one Run are byte-identical (`CONVENTIONS.md` §11) | 0 agree · 1 differ · **2 NOT-YET-RUNNABLE** |
| `rebuild_graph.py` | The ADR-0001 obligation that Neo4j is rebuildable from PostgreSQL alone | 0 rebuilt · **2 NOT-YET-RUNNABLE** |

Exit code **2 means the check could not run**, and it is reported loudly rather than
passed silently. A gate that cannot run is a known gap recorded in `PROGRESS.md`, never a
green tick.

## Persistence checks (added 2026-08-29)

| Script | Claim it defends | Make target |
|---|---|---|
| `check_migration_pairs.py` | Every forward migration has an exact reverse, the series is contiguous, and every filename matches `NNNN_<verb>_<subject>.sql` (ADR-0033). ADR-0015 excludes every migration framework, so the property a framework gives for free has to be checked. | `make laws` |
| `check_projection_drift.py` | The derived graph matches the facts it was built from — per-family counts **and** the content hash the registry recorded at swap time (ADR-0001). Counts alone miss an element edited in place. | `make verify-projection RUN_ID=…` |
| `migrate.py` | Not a check. Applies or reverses the series through the recorded runner, so the `schema_migration` ledger stays the authority on what schema exists. | `make migrate`, `make migrate-down TARGET=…`, `make migrate-status` |
| `rebuild_graph.py` | Not a check. The six-step rebuild of `docs/architecture.md` §3.3 — stage, stream, verify, swap, and assert against the previous build's hash. | `make rebuild-graph RUN_ID=…` |

Both checks ship `--self-test` and are observed to reject before they scan (ADR-0019), and
both are wired into `make laws` and CI. `check_projection_drift.py` runs only its self-test
in CI: the scan needs a live stack and a `run_id`.

**Neither repairs anything.** A drifted projection is rebuilt, never patched — a graph that
matches the facts without having been derived from them is indistinguishable from one that
was. An edited migration is a hard error naming the version, never a silent re-application.

---

## Ingestion (module 1 · not a check)

| Script | What it does | Command |
|---|---|---|
| `import_dataset.py` | Runs one dataset import end to end: probes and pins the source, loads and validates the mapping against the pack, streams two passes, writes the clean layer and the quarantine, and publishes the Data Quality Report. | `make import DATASET=dataco [PROPOSE=1]` |
| `build_event_log.py` | Expands one clean layer into entities and events: resolves identity under a declared `ConflictPolicy`, streams both generation passes, and publishes the Reconciliation Report and the Event Quality Report. Events are STREAMED, never collected — the reference expansion does not fit in memory as models on an 8 GB machine, which is measured rather than assumed. | `make events DATASET=dataco [EVENTS=out.jsonl]` |

**It writes nothing to PostgreSQL.** Module 4 (Event Generator) does not exist, so there are
no `Event` values to persist; a persistence path for records that are not yet facts would put
rows into the system of record with no evidence chain behind them. The report says so under
"What this report did not check", rather than the absence being something a reader has to
notice.

**Exit codes are three, not two.**

| Code | Meaning |
|---|---|
| 0 | the import ran and the report was written |
| 1 | the mapping was refused, the source could not be read, the manifest disagreed with the file, or the row count did not reconcile |
| 2 | the import ran and the report carries `ERROR` findings |

1 and 2 are deliberately different. A refused mapping is a broken configuration; `ERROR`
findings are a *successful measurement of bad data*, and a run that measured bad data has
done its job. Collapsing them would make "the adapter is misconfigured" and "the dataset has
defects" indistinguishable at the exit code, which is where CI reads.

`PROPOSE=1` additionally writes a `mapping.proposal.yaml` beside the report. It carries
`status: PROPOSED_UNCONFIRMED` and **cannot be loaded** — promoting it is a human editing the
file in a commit.
