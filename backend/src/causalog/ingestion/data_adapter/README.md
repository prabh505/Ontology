# `causalog.ingestion.data_adapter`

**Layer rank:** `L2` · **Module 1** · Status `built-unverified`

## Single responsibility

Read, validate, and reject raw source records (module 1).

Concretely: two streaming passes over a pinned source producing a `DataQualityReport`, a
versioned clean layer, and a quarantine. Never an `Event` — that is module 4, across the
LAW-EVENT boundary.

## Public surface

`import_dataset(source, mapping, pack, coverage, …) -> ImportResult`. Everything
domain-specific arrives as data: the ontology pack and the schema mapping. The source
**reader is supplied**, never imported (forbidden edge F4) — it reaches this package as the
`SourceReader` protocol declared in `causalog.core.ports.source`.

## What it guarantees

- **Nothing is dropped silently.** Every row read is written to exactly one of two files,
  and a quarantined row carries the rule codes that put it there.
  `rows_read == rows_clean + rows_quarantined` is asserted; a run that cannot reconcile
  raises rather than publishing a report whose own arithmetic disagrees with itself.
- **Raw is never modified.** The source is opened read-only in both passes. Cleaning
  produces a new layer keyed by `dataset_version`.
- **No timestamp is imputed.** The mapping DSL refuses to declare `EXACT` precision, the
  precision-span table holds only entries that widen, and a missing instant becomes
  `UNKNOWN` + `ASSUMED` with unbounded bounds. Enforced by
  `tests/law/test_cleaning_never_imputes_time.py`, which enumerates the transform registry
  rather than sampling it.
- **Every finding names what it breaks.** `downstream_consequence` is `min_length=1` on the
  model, so the requirement is structural rather than editorial.
- **A check that could not run says so.** `NOT_RUNNABLE` is a severity, not a silence.
- **Determinism.** Same bytes, same mapping, same pack ⇒ byte-identical report, clean layer
  and quarantine, and an identical `report_sha256`. Batch size is a memory decision and
  never an output decision.

## Forbidden dependencies

`extraction` and above; may never emit an `Event`; may never import `causalog.persistence.*`
(F4). **In LAW-DOMAIN scope since ADR-0037** — no file here may name a column, a value, or a
concept of any domain. DataCo column names live in `ontology/packs/dataco/mapping.yaml` and
in `causalog.persistence.sources.dataco`, and nowhere else.

Enforced by `scripts/check_layers.py` and `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the layer map and §2 for this package's module contract.
