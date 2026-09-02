# `ontology/packs/dataco`

**Single responsibility:** hold the DataCo SMART Supply Chain ontology **instance**.

prd.md §21 prints an event vocabulary. That vocabulary belongs here, as one instance — it is
not the engine's ontology and it is not part of the engine (ADR-0002). Replacing this
directory with a different one is how a new domain is added; no reasoning code changes
(`docs/architecture.md` §5).

```
ontology.yaml           the domain pack: entities, relationships, events, processes,
                        measurements, actionability
columns.manifest.yaml   the column names this pack is permitted to reference
```

## Two findings about this dataset, stated up front

**One event type is OBSERVED. Twenty are DERIVED.** DataCo is one row per order line
carrying a *terminal* status and a handful of date and duration columns. It does not log
occurrences. Only `ORDER_PLACED` is recorded directly — by the row's existence and its order
date. Everything else is reconstructed, is marked `observation: DERIVED`, names its basis,
and carries a default confidence. None of them may claim `OBSERVED` provenance; the loader
refuses it (ADR-0029), and
`tests/unit/ontology_runtime/test_dataco_pack_traceability.py` pins the ratio so a future
edit cannot quietly promote one.

The canonical case is `SHIPMENT_DISPATCHED`. DataCo carries a `shipping date` column and no
dispatch record. The date is strong evidence that a dispatch happened and is not itself the
occurrence. A pack calling it `OBSERVED` would put a fabricated fact into the system of
record with a real column standing behind it — the most convincing kind of wrong.

**Three prd.md §21 event types are absent, deliberately.** They are not gaps to be filled
later with assumptions:

| §21 event type | Why it is absent |
|---|---|
| Order Updated | No revision history. The row carries one terminal status and no trace of what it was before. |
| Customer Complaint | No complaint, contact, or service column of any kind. |
| Route Changed | No route, leg, waypoint, or carrier-movement column. |

Declaring them with `ASSUMED` attributes would manufacture occurrences the source never
recorded, which is the failure LAW-PROVENANCE exists to prevent.

There is also **no `CARRIER` entity type**. DataCo names a service level (`Shipping Mode`)
and never names a carrier, so the pack declares `SHIPPING_MODE` — which traces to a real
column — rather than assuming a carrier into existence.

## Traceability

Every attribute declares an `origin`:

| `origin` | Means | Must also supply |
|---|---|---|
| `SOURCE_COLUMN` | a named DataCo column carries the value | `source_column`, present in `columns.manifest.yaml` |
| `DERIVED` | the engine computes it | `derivation_basis` |
| `ASSUMED` | nothing in the dataset establishes it | `assumption` |

The manifest is **not** verified against a local file. The dataset is not in this repository
(`datasets/` holds a README; `datasets/raw/` is git-ignored and no `dataco.pin.json` exists),
so the column list is transcribed from the published distribution and carries
`verification: UNVERIFIED_AGAINST_LOCAL_FILE`. A green traceability check therefore means
"traces to the manifest", not "traces to the file". Module 1 (Data Adapter) flips that field
when it pins the dataset by hash, and a test asserts the field still says what it says.

## Expected warnings

Seven entity types load with `ONT-W-NO-LIFECYCLE`. That is correct and not a defect: a
reference entity (customer, product, category, department, site, shipping mode, market
region) genuinely carries structure and never changes state in this dataset. The warning's
own wording — "it can carry structure but never change" — is the accurate description.
