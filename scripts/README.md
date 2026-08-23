# `scripts/`

**Single responsibility:** hold the executable checks and operations that turn the Five
Inviolable Laws and the Definition of Done from prose into build outcomes.

Every script here is standard-library only, so that no dependency upgrade can silently
disable a law (ADR-0016).

**Every law check ships `--self-test` and runs it in CI before its scan (ADR-0019).** A
check that has only ever been observed to pass is not evidence that a law is enforced:
DEF-0001 is a lint that passed review for the life of the scaffold while catching almost
nothing, because its self-test asserted the wrong invariant. `make laws` runs all four
self-tests first, then all four scans.

| Script | Enforces | Exit codes |
|---|---|---|
| `check_domain_independence.py` | LAW-DOMAIN (`CONVENTIONS.md` §6, ADR-0019). Stem-prefix matching, so identifier forms (`warehouse_id`, `orders`, `WAREHOUSE_TABLE`, `customerName`) are caught. `--self-test` proves 24 vocabulary forms fire, 17 non-domain words stay clean, and **no claimed false positive hides a banned stem** — the DEF-0001 root cause. | 0 clean · 1 violation |
| `check_layers.py` | The layer map and forbidden edges F1–F9 (`docs/architecture.md` §1, ADR-0016). `--self-test` proves each of F1–F9 rejects a synthetic import and 6 permitted edges do not. | 0 clean · 1 violation |
| `check_dependency_policy.py` | Exact pins, ADR-0015 coverage, the ADR-0003 import ban. `--self-test` proves a range pin, an ADR-less package, and a blocked declaration each fail. | 0 clean · 1 violation |
| `check_law_copies.py` | The Five Laws are byte-identical in `CONTEXT.md` §2 and `CONVENTIONS.md` §1. `--self-test` proves a planted divergence and a missing law are both detected. | 0 clean · 1 diverged |
| `check_governance_consistency.py` | The governance record is internally consistent: no question both struck and open, every closure names an existing ADR, supersessions acknowledged both ways, and **no open question already answered by an accepted ADR** — the class that produced the OQ-004 and OQ-008 slips. | 0 clean · 1 inconsistency |
| `check_determinism.py` | Two runs of one Run are byte-identical (`CONVENTIONS.md` §11) | 0 agree · 1 differ · **2 NOT-YET-RUNNABLE** |
| `rebuild_graph.py` | The ADR-0001 obligation that Neo4j is rebuildable from PostgreSQL alone | 0 rebuilt · **2 NOT-YET-RUNNABLE** |

Exit code **2 means the check could not run**, and it is reported loudly rather than
passed silently. A gate that cannot run is a known gap recorded in `PROGRESS.md`, never a
green tick.
