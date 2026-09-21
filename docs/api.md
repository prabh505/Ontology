# api.md — the HTTP contract of Project CausaLog

> **Scope.** This document is the truth about *how results are served*. `docs/prd.md` is the
> truth about intent, `docs/architecture.md` about structure, `docs/contracts.md` about the
> frozen core types, `docs/ontology.md` about the domain-pack contract, and `CONTEXT.md`
> about current state.
>
> **Status.** `api_schema_version` **1.0.0**, set and **FROZEN** on 2026-09-20 by ADR-0085.
> The freeze covers the **shell** and not the payload bodies — see §1. The machine-readable
> form is `docs/openapi.json`, generated from the application by
> `scripts/export_openapi.py` and drift-checked in `make laws` and CI. **This document and
> that file are both derived from the code; where any of the three disagree, the code is
> right and the disagreement is a defect.**

---

## 0. The one thing this API is for

Every number it returns arrives with its evidence and its epistemic status attached.

That is not a slogan; it is four structural guarantees, each enforced by a type or a test
rather than by review:

1. **Every response carries its `OutputEnvelope`** — the nine fields that identify the run
   and the versions that produced it. `CONVENTIONS.md` §11: "an output without its envelope
   cannot be verified and is a defect."
2. **No confidence number arrives without its decomposition.** `ConfidenceView.components`
   carries `min_length=1`, so a bare float wearing a confidence's name is unconstructable
   (LAW-EVIDENCE).
3. **The five provenance classes are never flattened.** Every body carries both the weakest
   class present and the full set.
4. **An empty result says why it is empty, and a disowned one says it is disowned.**

---

## 1. What is frozen, and what is not

**Frozen at `api_schema_version` 1.0.0** (changing any of it requires an ADR and a
coordinated update of every consumer):

- the route set, their methods and their status codes;
- `ApiResponse` and `ResponseScope`;
- the error taxonomy and its status mapping;
- pagination;
- the authentication and role contract;
- idempotency;
- the job and stage shapes.

**Not frozen — still `draft`:** the payload *bodies*. Every reasoning artifact this API
serializes is `draft` in `CONTEXT.md` §6, and three of their owning modules (7, 8, 15) do
not exist. Freezing them here would be the assertion-not-specification error OQ-009 exists
to prevent, committed in a new place.

In practice: **the fields you may rely on are the hand-written views** listed in §6. An
endpoint marked **`draft body`** below returns
`causalog.core.serialization.canonical_form` output — the frozen canonical wire shape
(ADR-0023), carrying its own `schema_version`, but whose *contents* may change when its
owning module changes.

---

## 2. The layers behind a request

```
client → api (L10) → orchestration (L9) → reasoning modules (L2–L8) → core contracts (L0)
```

Forbidden edge **F5** gives `causalog.api` exactly three import targets: `core`,
`orchestration`, and itself. It physically cannot name `PromotedGraph`,
`RootCauseRanking`, `SimulatedWorld` or even `GraphStanding`. That is why every payload is
translated in `causalog.orchestration.views` and why a route handler contains no branch: a
handler that could reach a reasoning package could compute something, and
`docs/architecture.md` §2 forbids this layer from "computing anything that changes a
conclusion".

`causalog.orchestration` has no module entry in `docs/architecture.md` §2 because it is not
a §36 module. Its contract is: compose a Run by wiring adapters into the pipeline; be the
only package that imports `causalog.persistence` (F4); expose `EngineFacade` as the only
surface L10 may call.

---

## 3. Routes

prd.md §53 lists ten *example* endpoints. Two of them name their path parameter with a
LAW-DOMAIN banned stem, and `causalog.api` is now in that lint's scan (ADR-0081), so the
paths are generalized. **A path is the most durable vocabulary a system publishes** —
renaming one breaks every client — so it is the last place a domain word should land.

| prd.md §53 example | Actual route | Notes |
|---|---|---|
| `POST /dataset/upload` | `POST /v1/jobs` | An import is a stage of a pipeline execution, not a separate upload |
| `POST /dataset/map` | *(mapping is pack data)* | `ontology/packs/<domain>/mapping.yaml`, participating in `dataset_version` through its hash (ADR-0035). Accepting one over HTTP would let a request change an input to `run_id` without changing anything the pin can see. A mapping is edited, reviewed and committed, not POSTed |
| — | `GET /v1/datasets/{dataset_id}/validation` | What an author actually needs from both rows above: is this dataset **described**, and is it **usable** |
| `GET /events` | `GET /v1/runs/{run_id}/events` | Cursor-paginated |
| `GET /timeline/{order}` | `GET /v1/runs/{run_id}/timelines/{process_instance_id}` | |
| `GET /graph` | `GET /v1/runs/{run_id}/graph` | Subgraph extraction |
| `GET /root-cause/{order}` | `GET /v1/runs/{run_id}/root-causes/{outcome_event_id}` | Four never-merged views |
| `GET /counterfactual` | `POST /v1/runs/{run_id}/counterfactuals` | POST, because an intervention set is a structured typed value |
| `GET /recommendations` | `GET /v1/runs/{run_id}/recommendations` | Every act carries Principle 5's four requirements as **required** fields; the withheld set is published beside the ranked one |
| `GET /report/{order}` | `GET /v1/runs/{run_id}/reports/{process_instance_id}` | Declared, and always `NOT_RUNNABLE` today: module 15 is `not-started`. The route exists so a client can bind now and so the gap is stated rather than absent |
| — | `GET /v1/runs/{run_id}/propagation/{seed_event_id}` | prd.md §30's measures |
| — | `GET /v1/runs`, `GET /v1/runs/compare` | |
| — | `DELETE /v1/runs/{run_id}/inferred-artifacts` | |
| — | `GET /v1/runs/{run_id}/ontology`, `GET /v1/runs/{run_id}/rule-pack` | **Principle 4** |
| — | `POST /v1/jobs`, `GET /v1/jobs`, `GET /v1/jobs/{execution_id}` | |
| — | `GET /healthz` | Unauthenticated |

Naming follows `CONVENTIONS.md` §5: lowercase, hyphenated, plural nouns; `snake_case` JSON
fields.

---

## 4. The response envelope

Every body is an `ApiResponse`. Fields:

| Field | Meaning |
|---|---|
| `scope` | `RUN_SCOPED` or `CATALOG` — see below |
| `run_id` | The run this body describes. `null` only under `CATALOG` |
| `envelope` | The nine `OutputEnvelope` fields. Present on every `RUN_SCOPED` body |
| `provenance` | `{weakest, present[]}` — the five classes, never flattened |
| `standing` | `STATED` or `UNPROMOTED_DIAGNOSTIC` — which graph was walked |
| `standing_notice` | **Required** when `standing` is `UNPROMOTED_DIAGNOSTIC` |
| `stage_status` | `COMPLETE`, `PARTIAL` or `NOT_RUNNABLE` |
| `stage_detail` | **Required** when `stage_status` is not `COMPLETE` |
| `timing` | The measurement and the prd.md §55 budget it was measured against |
| `generated_at` | When the body was produced |
| `evidence` | Citations resolving back to evidence records |
| `confidence` | A `ConfidenceView`, or `null`. **Never a bare float** |
| `data` | The payload |

### Why `CATALOG` exists

An `OutputEnvelope` describes **one run**. A listing spans many, and a job that refused
before its packs resolved has none yet (migration 0017's `run_id` is nullable for exactly
that reason). The alternative was to synthesize an envelope of empty strings, which would be
**unverifiable while looking verified** — worse than omitting one. So the scope is declared,
the validator requires the envelope under `RUN_SCOPED` and refuses it under `CATALOG`, and
the catalog routes are a closed, tested set: `GET /v1/runs`, `GET /v1/jobs`,
`GET /v1/jobs/{execution_id}` and `GET /v1/datasets/{dataset_id}/validation` — the last
because **a dataset is not a run**: it is a pack plus a mapping plus a pinned file, where a
run is those *plus* a rule pack, an engine version and a seed (ADR-0013).

### How this is enforced

`tests/law/test_api_returns_no_body_without_envelope.py` — **blocking** — walks the live
route table *and* the AST of every file in `api/routes/`, parametrized per source file, and
both checks are observed to **reject** a planted violation before being trusted to accept a
real route (DEF-0001's lesson).

---

## 5. Authentication and the permission matrix

**Authentication.** `Authorization: Bearer <token>`, where the token is
`<payload-b64url>.<signature-b64url>` signed with HMAC-SHA256 under `CAUSALOG_API_SECRET`
(ADR-0082). The payload is `actor | role | issued_at_epoch | expires_at_epoch`.

There is **no key rotation and no revocation**: a leaked token is valid until it expires and
the only remedy is rotating the secret, which invalidates every token at once. This is
adequate for a single-service V1 and is not adequate for a real user base; the
`Authenticator` port is the seam an identity provider replaces.

Every 401 returns the same body whatever was wrong — missing, malformed, badly signed or
expired — so an unauthenticated caller learns nothing about which guess was closest.

**Roles** are exactly prd.md §10's five user types, under domain-neutral names:

| prd.md §10 user type | Role |
|---|---|
| Operations Manager | `OPERATIONS_MANAGER` |
| Supply Chain Analyst | `HISTORICAL_ANALYST` |
| Executive Leadership | `EXECUTIVE` |
| Data Scientist | `DATA_SCIENTIST` |
| Process Improvement Team | `PROCESS_IMPROVEMENT` |

**The matrix** (rendered from `causalog.api.security.authorization.PERMISSIONS`, not
retyped):

| Capability | Operations Manager | Historical Analyst | Executive | Data Scientist | Process Improvement |
|---|---|---|---|---|---|
| `READ_OBSERVED` | **yes** | **yes** | **yes** | **yes** | **yes** |
| `READ_INFERRED` | **yes** | **yes** | **yes** | **yes** | **yes** |
| `READ_DIAGNOSTIC` | no | **yes** | no | **yes** | no |
| `READ_EVIDENCE` | **yes** | **yes** | no | **yes** | **yes** |
| `READ_RULES` | **yes** | **yes** | no | **yes** | **yes** |
| `READ_RECOMMENDATIONS` | **yes** | **yes** | **yes** | **yes** | **yes** |
| `SIMULATE` | no | no | no | **yes** | **yes** |
| `MUTATE_DATASET` | no | no | no | **yes** | no |
| `EXECUTE_PIPELINE` | no | no | no | **yes** | **yes** |
| `DELETE_INFERRED` | no | no | no | **yes** | no |

Two decisions worth stating:

- **`EXECUTIVE` is withheld `READ_DIAGNOSTIC` deliberately.** That capability reaches the
  `UNPROMOTED_DIAGNOSTIC` standing — output the engine explicitly disowns (ADR-0059).
  OQ-026 records that its structural defences do not survive a screenshot, and an executive
  summary is where a disowned figure quoted as a finding does the most damage.
- **prd.md names no administrator.** `MUTATE_DATASET`, `EXECUTE_PIPELINE` and
  `DELETE_INFERRED` need a holder, and the assignment above is a **proposed default
  awaiting a product owner's ruling** (OQ-033), pinned by a test so a change is deliberate.

**Rate limits** are per caller per capability class: 30/60s for `SIMULATE`, 10/60s for
`EXECUTE_PIPELINE` and `DELETE_INFERRED`, 30/60s for `MUTATE_DATASET`, 300/60s otherwise.
The limiter **fails open** — a limiter outage must not become a total outage — which is
precisely why authorization is not built on it. Limiting happens *after* authorization, so
an unauthorized caller cannot consume an authorized caller's budget.

---

## 6. Errors

Typed, actionable, and never leaking internals. Every body is
`{error_code, message, remediation, correlation_id, retry_after_seconds?}`.

| `error_code` | Status | When |
|---|---|---|
| `ContractViolationError` | 422 | The request violates an interface contract |
| `OntologyMappingError` | 422 | A value has no concept in the active ontology |
| `DataQualityError` | 422 | A stated quality requirement was not met |
| `RuleConflictError` | 409 | The rule pack contradicts itself |
| `ProjectionStaleError` | 409 | The projection version requested is not the one served |
| `RunNotAvailableError` | 404 | That run is not materialized in this process |
| `LawViolationError` | 500 | The engine refused rather than violate its own invariant |
| `UNAUTHENTICATED` | 401 | No valid credential |
| `FORBIDDEN` | 403 | The role lacks the capability |
| `IDEMPOTENCY_KEY_REUSED` | 409 | A key was reused with a different body |
| `RATE_LIMITED` | 429 | The caller's budget is exhausted |
| `InternalError` | 500 | Anything unexpected |

The mapping is **total over the closed `CausaLogError` taxonomy**: a new error class with
no entry raises at resolution rather than defaulting to 500, so an undeclared failure mode
is found by the test that enumerates the taxonomy rather than by the first caller to hit it.

**`CAUSALOG_ENV=production`** (the default when unset) **replaces** the engine's message
with a fixed public sentence per taxonomy member — replaced, not filtered, because deciding
sentence by sentence what is safe to reveal is a judgement that will eventually be made
wrong. Outside production the engine's own message is returned, because `CONVENTIONS.md` §7
writes those to name the offending identifier and the contract violated.

`correlation_id` is on every error and every response header (`X-Correlation-Id`). It is the
only link between a production body and the log line that explains it.

---

## 7. Endpoints, with example payloads

Every example below is elided with `…` where a value is long. `envelope`, `provenance`,
`standing`, `stage_status`, `timing` and `generated_at` are present on every body and are
shown once, in full, in the first example only.

### `GET /healthz` — unauthenticated

```json
{"status": "ok", "engine_version": "0.1.0", "api_schema_version": "1.0.0"}
```

### `POST /v1/jobs` → `202` — start a pipeline execution

Capability `EXECUTE_PIPELINE`. Honours `Idempotency-Key`: a repeated key returns the
**original** execution rather than starting a second one, enforced by a UNIQUE index rather
than by a read-then-write check that would race two concurrent retries.

Request: `{"dataset_id": "dataco", "rows": 150, "seed": 0}`

```json
{
  "scope": "CATALOG",
  "run_id": null,
  "envelope": null,
  "data": {
    "execution_id": "exec:29bda011849e4f7f…",
    "run_id": null,
    "dataset_id": "dataco",
    "status": "PENDING",
    "requested_by": "dana",
    "stages": [
      {"stage_id": "packs", "status": "PENDING", "requires": []},
      {"stage_id": "relationships", "status": "NOT_RUNNABLE", "requires": ["states"],
       "detail": "Module 7 (Relationship Resolver) is not-started. It would supply the structural Relationship values module 9's structural-path generator walks; …"}
    ],
    "runnable_stage_count": 12,
    "completed_stage_count": 0,
    "not_runnable_stage_count": 3
  }
}
```

`run_id` is `null` until the `run_identity` stage resolves one. That is a **meaningful
null**: a run is identified by its inputs (ADR-0013), and minting a placeholder would create
an identifier that addresses nothing.

### `GET /v1/jobs/{execution_id}` — poll

Reports per-stage status and **measured** per-stage timing. `progress` is over *runnable*
stages: a `NOT_RUNNABLE` stage is excluded from the denominator, or a job that can never
exceed 12/15 because three modules are unbuilt would report permanent failure to progress.

An execution ends `SUCCEEDED`, `PARTIAL` or `FAILED`. **`PARTIAL` is not a synonym for
`FAILED`**: a refusing stage blocks only its dependents and every independent stage still
runs, so reporting nine-of-twelve completed stages as failed would discard work that is on
disk and valid. `FAILED` is reserved for an execution where nothing succeeded.

### `GET /v1/runs/{run_id}/events` — paginated, canonical sequence

Capability `READ_OBSERVED`. Paged on `(t_earliest, t_latest, event_id)` —
`CONVENTIONS.md` §11's canonical sort key, not an invented one — so a cursor is stable
across requests and across processes.

```json
{
  "scope": "RUN_SCOPED",
  "run_id": "run:5245e54a6474fe38",
  "envelope": {
    "run_id": "run:5245e54a6474fe38",
    "ontology_version": "1.0.0",
    "ontology_hash": "ont:dbf28f5e460ce54f",
    "dataset_version": "dataco@994b3c8d24049cc4+mapa85a911e567f73c2",
    "rule_pack_version": "1.7.0",
    "engine_version": "0.1.0",
    "graph_projection_version": "unset",
    "seed": 0,
    "execution_id": "exec:29bda011849e4f7f…"
  },
  "provenance": {"weakest": "INFERRED", "present": ["INFERRED"]},
  "standing": "STATED",
  "standing_notice": null,
  "stage_status": "COMPLETE",
  "stage_detail": null,
  "timing": {"operation": "events", "elapsed_seconds": 0.0005,
             "budget_name": null, "budget_seconds": null,
             "budget_enforced": null, "within_budget": null},
  "generated_at": "2026-09-20T13:45:01+00:00",
  "evidence": [],
  "confidence": null,
  "data": {
    "items": [
      {
        "event_id": "evt:024c9502e33a92ed",
        "event_type": "SHIPMENT_DISPATCHED",
        "occurred_at": {"t_earliest": "2017-01-02T11:00:00+00:00",
                        "t_latest": "2017-01-02T11:59:59+00:00",
                        "precision": "MINUTE", "provenance_class": "OBSERVED",
                        "source": "RECORDED"},
        "provenance_class": "OBSERVED",
        "confidence": {
          "scalar": 0.75, "aggregation": "gated_weighted_mean_v1",
          "provenance_class": "INFERRED",
          "components": [
            {"component_name": "rule_support", "value": 1.0,
             "provenance_class": "ASSUMED", "evidence_record_ids": ["evd:0000000000000003"]},
            {"component_name": "temporal_support", "value": 0.5,
             "provenance_class": "OBSERVED", "evidence_record_ids": ["evd:0000000000000003"]}
          ]
        },
        "is_actionable": false,
        "evidence_record_ids": ["evd:0000000000000003"]
      }
    ],
    "next_cursor": "evt:024c9502e33a92ed",
    "has_more": true,
    "total_known": null,
    "sequenced_by": "(t_earliest, t_latest, event_id)"
  }
}
```

`occurred_at` is an **interval**, never a point. ADR-0021 makes time an interval because a
day-granular source does not know an instant, and emitting `t_earliest` alone would hand a
client a precision the data does not have.

`total_known: null` means **not counted**, never zero.

### `GET /v1/runs/{run_id}/graph` — subgraph extraction

Capability `READ_INFERRED`. Query: `seed_event_id`, `depth` (0–10), `limit`, `standing`.

On the reference dataset this is usually **empty, and says why**:

```json
{
  "data": {
    "standing": "STATED",
    "seed_event_id": null,
    "depth": 2,
    "nodes": [],
    "edges": [],
    "truncated": false,
    "rejected_claim_count": 3814,
    "empty_because": "The causal graph is empty: 3,814 claim(s) were proposed and every one was refused promotion. This is a statement about what the engine ASSERTS, not about what the data contains — each refusal is recorded in the rejection ledger with its reason, and on a day-granular source most are refused for TEMPORAL reasons rather than for weak evidence. Re-ask under the UNPROMOTED_DIAGNOSTIC standing to see the scored-but-unasserted structure, reading its disowning notice first."
  }
}
```

**An empty `edges` list without that sentence reads as "this event causes nothing", which is
not what an unpromoted graph means.** Three emptinesses are distinguished: claims were made
and all refused; nothing was ever proposed; the seed is isolated.

Each edge carries `temporal_verdict` and `temporally_unverifiable` as **separate** fields.
On the committed slice 79.3% of claims are stopped by the temporal verdict rather than by
any threshold, so an edge payload omitting the verdict would leave a client unable to tell a
weak claim from an untimeable one.

### `GET /v1/runs/{run_id}/root-causes/{outcome_event_id}`

Capability `READ_INFERRED` (plus `READ_DIAGNOSTIC` for the diagnostic standing). prd.md §55
budget: **3 s, enforced**.

**ADR-0008's four answers are four fields and are never merged.** `earliest` answers "where
did this start?"; `highest_consequence` answers "what is the biggest?"; `most_actionable`
answers "what can anybody change?"; `recommended_groups` answers "what should we change?".
**A client that presents any one of them as *the* root cause is a defect.** There is no
root-cause score anywhere on this type: a single number would have to weight a quantity
against a position in a chain, and any figure produced would be a judgement disguised as
arithmetic.

```json
{
  "standing": "UNPROMOTED_DIAGNOSTIC",
  "standing_notice": "DISOWNED. This was walked over the scored graph BEFORE promotion. The engine does not assert it, nothing here is INFERRED, and a figure quoted from it without this notice is being quoted as something it is not (ADR-0059, OQ-026).",
  "data": {
    "outcome_event_id": "evt:01e903a64c12b18b",
    "actionability_notice": "Actionability is ontology-declared and is not validated against any ground truth (R-15).",
    "earliest": {"event_id": "evt:cb230392436d007d", "chain_scalar": 0.4,
                 "chain_composition": "weakest_link_v1", "confidence": {"…": "…"}},
    "highest_consequence": null,
    "most_actionable": {"event_id": "evt:be49828d5e246138", "…": "…"},
    "recommended_groups": [
      {"tied": true, "plateau_value": 0.4,
       "plateau_notice": "These candidates compose to exactly the same value. The engine did not sequence them and this set is UNSEQUENCED: the sequence of `members` carries no ranking. …",
       "members": [{"event_id": "evt:…"}, {"event_id": "evt:…"}]}
    ],
    "trade_offs": [{"first_view": "EARLIEST", "second_view": "MOST_ACTIONABLE", "detail": "…"}],
    "views_agree": false,
    "empty_because": null
  }
}
```

**`recommended_groups` is a list of groups, not of causes** (OQ-027, ADR-0087). When `tied`
is true the set is **unsequenced**: the order of `members` carries no ranking, and the tie
is deliberately *not* broken on earliness, which would reintroduce ADR-0008's forbidden
blend by the back door.

### `POST /v1/runs/{run_id}/counterfactuals` — **`draft body`**

Capability `SIMULATE`. prd.md §55 budget: **5 s, enforced**.

Request:

```json
{"interventions": [{"payload": {"kind": "SHIFT_TIMING", "event_id": "evt:…", "shift_seconds": -3600},
                    "rationale": "Test whether dispatching an hour earlier prevents the delay."}],
 "standing": "STATED"}
```

`rationale` is required and non-empty: an intervention with no stated reason is one nobody
can review, and prd.md Principle 5 requires assumptions to be explicit. Interventions are
applied as a **set**, never summed from separate calls — two acts on one chain overlap, and
adding single-act results would double-count it (ADR-0077).

The response carries `provenance: SIMULATED`, module 13's fixed "this is a plausibility
simulation, not a prediction" notice, and simulated events typed as `SimulatedEventView` —
which has **no `occurred_at`**, so a client cannot deserialize one into an `EventView` and
no interface can render a simulation as an observation (OQ-031, prd.md §37).

### `GET /v1/runs/{run_id}/propagation/{seed_event_id}` — **`draft body`**

Consequence is attributed to the node **set**, never to the routes: a consequence reachable
four ways is one consequence (ADR-0061).

### `GET /v1/runs/{run_id}/ontology` and `GET /v1/runs/{run_id}/rule-pack`

Capability `READ_RULES`. **This is prd.md Principle 4 made reachable**: "the user must be
able to inspect every inferred relationship", and a relationship inferred by a rule is not
inspectable while the rule is invisible. Both are served from the same run the conclusion
came from, so a user reading a conclusion and a user reading the rule behind it cannot be
looking at two different packs.

`rule-pack` carries `event_types_without_a_rule`. `docs/architecture.md` §7 risk 2 is
explicit that recall is bounded by rule coverage; publishing the rules without publishing
what they fail to cover would satisfy Principle 4's letter and invert its purpose.

### `GET /v1/runs/{run_id}/recommendations`

Capability `READ_RECOMMENDATIONS`. prd.md §55 budget: **5 s, enforced**.

**prd.md Principle 5 is enforced by the type.** "Every recommendation must identify:
expected benefit, confidence, supporting evidence, assumptions." All four are **required
fields** on `RecommendationView` — `evidence_item_ids` and `assumptions` carry
`min_length=1`, and `confidence` is a `ConfidenceView` which itself cannot exist without
components. An unsupported recommendation is *unconstructable*, which is stronger than
filtering one out later: a filter is a step somebody can forget.

There is no single "score". `desirability` is carried, but it names the
`core.scalarization` function that produced it and the weights it was produced under, so a
ranking can never be read under a weighting that did not make it. `pareto_optimal` sits
beside it as a stronger, weighting-independent statement.

**The withheld set is published beside the ranked one**, with a tally by reason:

```json
{
  "data": {
    "standing": "STATED",
    "recommendations": [],
    "withheld_by_reason": [["BENEFIT_NOT_MEASURABLE", 180]],
    "empty_because": "Nothing is recommended: 180 candidate act(s) were considered and every one was withheld. By reason: BENEFIT_NOT_MEASURABLE (180). This is a statement about what the engine will STAND BEHIND, not about whether anything could be done — each withholding names the test it failed and what it was checked against. prd.md Principle 5 requires a benefit, a confidence, evidence AND assumptions; a candidate missing any one of them is withheld rather than published without it."
  }
}
```

That is the real output on the reference slice. An empty `recommendations` list on its own
would say "we found nothing"; the true statement is "we found 180 candidates and every one
failed a named test", and only the withheld set carries it.

Each `assumption` carries `falsified_by`, because an assumption nobody can test is not an
assumption.

### `GET /v1/runs/{run_id}/reports/{process_instance_id}`

Capability `READ_INFERRED`. **Always `NOT_RUNNABLE` today** — module 15 (the Explanation
Generator) is `not-started`. It returns 200 with a full envelope and a `stage_detail`
naming the module, and points at `/root-causes`, `/propagation` and `/recommendations`,
which already carry the same findings without the prose.

The route exists rather than being omitted because an absent route is indistinguishable
from one that ran and found nothing to say — and because a client can bind to the contract
now and receive prose when the module lands, with no version change.

### `GET /v1/datasets/{dataset_id}/validation` — `CATALOG` scope

Capability `READ_OBSERVED`. Two measurements, reported separately and **never merged into
one verdict**:

- **Mapping coverage** (module 2, via `inspect_mapping`, which assesses *without* refusing)
  answers *is this dataset described?* — bound columns, binding count, and every finding an
  author should see.
- **Data quality** (module 1's committed report) answers *is this dataset usable?*

A dataset whose every column binds can still be unusable, and one with mapping gaps can
still measure clean over what it does bind. `quality_report_available` is a **third state**,
not a quiet false: a report that was never produced and a report that found nothing are
different, and only one of them is a reason to proceed.

### `GET /v1/runs`, `GET /v1/runs/compare` — `CATALOG` scope

`compare` names the **inputs that differ**. Two runs differing in one `RunKey` field isolate
that field's effect (ADR-0013); a comparison that did not say which had changed would invite
the first reading regardless.

### `DELETE /v1/runs/{run_id}/inferred-artifacts`

Capability `DELETE_INFERRED`. **Deletes inference only.** Observed facts are
dataset-scoped and inferred artifacts are run-scoped, so a run identifier cannot reach a
fact even in principle — the same asymmetry that makes "inference never overwrites
observation" structural is what makes this operation safe to expose. Audited with
before/after counts.

---

## 8. Performance

prd.md §55's budgets are declared as data in `causalog.orchestration.timing` and every
response reports its measurement against its budget.

| Operation | Budget | Status |
|---|---|---|
| Root cause query | < 3 s | **enforced** — measured through HTTP in `tests/integration/test_api_budgets.py` |
| Counterfactual query | < 5 s | **enforced** |
| Recommendation generation | < 5 s | **enforced** |
| Dataset loading | < 30 s | **measured, not enforced** |
| Graph generation | < 60 s | **measured, not enforced** |

**The two unenforced budgets are unenforced honestly.** prd.md §55 does not say whether
"dataset loading" counts the 180,519 source rows or the ~3.8M events they materialize — a
factor of 21 — and the measured import is ~105 s. That is OQ-018/OQ-019, a product owner's
question. Graph generation has no full producer, since modules 7 and 8 are not built.
Asserting either would be choosing the reading that passes, which is a ruling disguised as a
measurement. `make bench` prints both and keeps saying they are unresolved.

`within_budget: null` in a `timing` block means **no budget is declared for this
operation** — a third state, not a quiet `true`. "This was fast enough" and "nobody said how
fast this should be" are different claims.

A query exceeding its budget is logged at `WARNING` with the overrun (the slow-query log). It
never changes a response body: the answer is correct and arrived late.

**Caching.** Redis holds recomputable query results only, keyed by `run_id` plus a content
address of the query and its arguments, TTL'd. ADR-0001 and `docs/architecture.md` §3.2
point 5 are binding: **flushing the cache changes latency and never an answer.**
Invalidation is explicit and has exactly three triggers — a pipeline execution starts
against a run, a run's inferred artifacts are deleted, the projection is rebuilt.

---

## 9. Known limits

Stated here rather than discovered:

1. **A run must be materialized in this process.** There is no full rehydration path from
   storage, because modules 7 and 8 are not built and OQ-020 records that extraction output
   is discarded each run. Restarting the API loses the ability to answer *graph* queries
   about a run until it is executed again; the **facts** are not lost. A query for an
   unmaterialized run is a 404 naming it, never an empty success.
2. **Resumption does not carry artifacts across a restart.** A resumed execution replays the
   stages that produced the inputs its remaining stages need (ADR-0083).
3. **No key rotation, no revocation, no refresh** on tokens (ADR-0082).
4. **Rate limits are global per capability class**, not per role.
5. **`empty_because` is prose**, so a client cannot branch on *why* a result is empty without
   parsing English or falling back to `rejected_claim_count` (OQ-035).
6. **`draft body` endpoints may change without an `api_schema_version` bump.** The owning
   module's schema version moves instead.
7. **`/reports` returns no prose** until module 15 exists. It returns its envelope and
   says so.
8. **Dataset validation reads the committed quality report from disk**, so it reflects the
   last `make import` rather than the file as it stands now.
9. **Stage wiring exists twice** — here and in `scripts/build_causal_graph.py` (OQ-034).

---

## 10. Document obligations

| Obligation | Status |
|---|---|
| `docs/openapi.json` cannot drift from the code | satisfied — `scripts/export_openapi.py --check` in `make laws` and CI, self-tested first |
| No route returns a body without its envelope | satisfied — blocking law test over the route table AND the AST, both observed to reject |
| No response carries a confidence without components | satisfied — `min_length=1` on the type, plus a recursive walk of real bodies at every depth |
| Every role × every route is asserted against the matrix | satisfied — `tests/api/test_permission_matrix.py` |
| Every mutating action and every inference read is audited | satisfied — and a *refused* read is asserted NOT to produce an access record |
| Production responses leak no internals | satisfied — and the leak detector is observed to reject a planted leak |
| The permission matrix here matches the code | satisfied — rendered from `PERMISSIONS`, not retyped |
| The `CATALOG` scope stays a closed set | satisfied — enumerated by a test |
