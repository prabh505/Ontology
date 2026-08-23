# `ontology/dataco`

**Single responsibility:** hold the DataCo SMART Supply Chain ontology **instance**.

prd.md §21 prints an event vocabulary. That vocabulary belongs here, as one instance —
it is not the engine's ontology and it is not part of the engine (ADR-0002). Replacing this
directory with a different one is how a new domain is added; no reasoning code changes
(`docs/architecture.md` §5).

Expected files, authored with module 2:

| File | Supplies |
|---|---|
| `ontology.yaml` | entity types, event types, state names, legal transitions |
| `mapping.yaml` | dataset column and value bindings — no defaults, no catch-alls |
| `cost.yaml` | ordinal intervention cost bands (`LOW`/`MEDIUM`/`HIGH`), provenance `ASSUMED` (OQ-013) |
| `labels.yaml` | display strings; the only ontology data the presentation layer may read |
