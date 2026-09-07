# Counterfactual Report

> **BOUNDED RUN.** Built from the first 150 rows of the clean layer, not from
> all 180,519. Neither module 9 nor module 10 is a streaming module -- the base
> rates measure across process instances and the fusion needs the whole candidate
> graph in hand -- and the full expansion does not fit in memory as models on an 8 GB
> machine (`tests/integration/test_full_expansion_budget.py`). **Every number below
> measures this slice, not the dataset.** Re-run with `--rows 0` to remove the bound.

> **THE QUESTION AS ASKED COULD NOT BE POSED, AND A DIFFERENT ONE WAS ANSWERED.** no process instance in this slice places a INVENTORY_RESERVED more than 30 minute(s) after its own start. 0 placed occurrence(s) of that type were examined. There is therefore nothing for this question to move, which is a finding about the slice and not a failure of the query. What follows asks about `SHIPMENT_DISPATCHED` instead, which this source does place in time. That is a SUBSTITUTION and not the question prd.md §11 asked: it moves a different step, so nothing below is an answer about `INVENTORY_RESERVED`. `evt:3cd104d531e3b363` (SHIPMENT_DISPATCHED) occurred 8585.0 minute(s) after the start of its process instance; the question asks what the graph says had it occurred within 30.

### Why: which occurrences this source places in time

`INVENTORY_RESERVED` is the step the question names. A type with **0 placed** is one this source emits without ever saying when it happened, so a question about its timing has no referent — thirteen of DataCo's declared types are in that position (R-21).

| type | placed | never placed | median min. after instance start | max |
|---|---:|---:|---:|---:|
| `FRAUD_SUSPECTED` | 0 | 2 | 0.0 | 0.0 |
| `INVENTORY_RESERVED` **←** | 0 | 48 | 0.0 | 0.0 |
| `INVENTORY_SHORTFALL_DETECTED` | 0 | 3 | 0.0 | 0.0 |
| `ORDER_CANCELED` | 0 | 5 | 0.0 | 0.0 |
| `ORDER_CLOSED` | 0 | 6 | 0.0 | 0.0 |
| `ORDER_COMPLETED` | 0 | 25 | 0.0 | 0.0 |
| `ORDER_HELD` | 0 | 7 | 0.0 | 0.0 |
| `ORDER_PLACED` | 150 | 0 | 0.0 | 369.0 |
| `PAYMENT_APPROVED` | 0 | 48 | 0.0 | 0.0 |
| `PAYMENT_FAILED` | 0 | 7 | 0.0 | 0.0 |
| `PAYMENT_REQUESTED` | 0 | 104 | 0.0 | 0.0 |
| `PAYMENT_REVIEW_OPENED` | 0 | 9 | 0.0 | 0.0 |
| `SHIPMENT_DELAYED` | 0 | 95 | 0.0 | 0.0 |
| `SHIPMENT_DELIVERED` | 145 | 0 | 10571.0 | 17225.0 |
| `SHIPMENT_DISPATCHED` | 145 | 0 | 4811.0 | 8585.0 |
| `SHIPMENT_IN_TRANSIT` | 0 | 135 | 0.0 | 0.0 |


- standing: `STATED`
> SIMULATED. This is a hypothetical about the PAST, not a forecast of the future and not a measurement of anything. It is what the stated graph implies under the stated change, propagated along links that were derived from rules, temporal structure and frequency rather than identified as causal effects. No counterfactual was observed and no confounder was adjusted for, so the figure has no identification argument behind it. It may never be written back into history, and it may never be read as a prediction.

- `report_schema_version`: `1.0.0`
- `run_id`: `run:da138c47fdf780fe`
- base world: `cgr:7c033575bc89165a`
- simulated world: `sim:3ffa24c6f1660a18`
- changes proposed: 1; admitted: 1

## What this report does not contain

> NOTHING BELOW IS CALIBRATED. A support envelope says a change stays inside the range this run witnessed; it does not say the answer is right. Calibration would mean outcomes stated at a given belief are right that often, and measuring it needs labelled causal ground truth -- pairs where somebody independently established what actually caused what. This dataset carries none, so no reliability curve can be drawn and no error rate can be quoted. A decomposed, envelope-checked, sensitivity-swept figure is MORE persuasive than a bare one and is not more accurate, and that is the specific way this artifact could do harm.

It contains no prediction. Every statement below is about a world that did NOT happen, phrased in the past conditional, and none of it forecasts anything.

It contains no causal effect estimate. The links this change travelled were derived from rules, temporal structure and frequency rather than identified as causal effects (prd.md §16, OQ-007).

Every declared policy ran.

## What was refused, and against what

No proposed change was refused.

## Validity

**Verdict: `NOT_ASSESSABLE`**

> Support could NOT BE JUDGED for this hypothetical, which is a different finding from its leaving the data behind. Nothing comparable was witnessed, so there is no range to place the change against — an absence of measurement, not a measurement of nothing. A figure is withheld for that reason and not because the change was found unsupported.

| quantity | witnessed | over | asked for | beyond | verdict |
|---|---|---|---|---|---|
| gap in seconds after evt:3cd104d531e3b363 | nothing comparable | 0 | -513300.0 | None | `NOT_ASSESSABLE` |

### Belief along the chain

the change travelled no stated link, so there is no chain of belief to compose. This is an absence and not a belief of zero.

### Sensitivity

| assumption | multiplier | outcome | stable? |
|---|---|---|---|
| apportioned_share | 0.5 | none | **not runnable** — nothing was perturbed |

### Assumptions this answer rests on

**graph_is_the_world** -- Every route by which the changed occurrence reaches its consequences is in the stated graph. A route the graph omits carries none of this change.

- why it is needed: Propagation is graph surgery. It can only travel links that exist, so recall bounds the answer and nothing in the system can report what was missed (R-13).
- falsified by: Any consequence a reader knows of that the graph does not reach.

**no_unobserved_confounder** -- No unobserved common cause explains the links this change travelled. If one does, the change moves nothing in the world and this figure is an artifact of the graph's shape.

- why it is needed: The links here were derived from rules, temporal structure and frequency rather than identified as causal effects (prd.md §16, OQ-007). Nothing in V1 adjusts for a confounder, and module 9's flags LOCATE observed common causes without resolving any of them.
- falsified by: A domain expert naming a factor outside the ontology that produces both ends of any link in the chain.

**the_rest_of_the_world_is_held_still** -- Nothing outside the stated change behaves differently. Every occurrence the change does not reach happens exactly as it did.

- why it is needed: A simulated world is the historical world with a surgery applied. There is no forward process model here and prd.md §6 excludes one.
- falsified by: Any adaptive response to the change -- anything that would have been done differently once the changed occurrence happened differently.

**weights_are_apportionments** -- The share attributed to each cause of a consequence is a reasonable split of that consequence among the causes the engine happens to hold for it.

- why it is needed: Every reduced magnitude is that share applied to a measured total. ATTRIBUTION_NOT_MEASUREMENT_NOTICE states the limit: two weights are comparable to each other and neither is a quantity of anything in the world.
- falsified by: A measurement of what each cause actually contributed, which would make the apportionment unnecessary rather than wrong.

## The diff: the world that happened against the one that did not

- occurrences reached: 1; changed: 1; reached and unchanged: 0
- the graph says 0 would not have happened, and 0 would still have happened and been smaller

**Those two counts are never added.** A consequence that would have been smaller is not a consequence that would have been prevented, and merging them is the single most common counterfactual error.

| occurrence | kinds | was | would have been | note |
|---|---|---|---|---|
| `evt:3cd104d531e3b363` (SHIPMENT_DISPATCHED) | `RETIMED` | not measurable | **NOT_ASSESSABLE** | evt:3cd104d531e3b363 happens at a different instant in this hypothetical. |

> PROPAGATION WEIGHT IS AN ATTRIBUTION ESTIMATE, NOT A MEASUREMENT. It apportions a magnitude the ontology declares how to compute across the causes this engine happens to hold for that effect. Nothing identifies a causal effect: no counterfactual was observed, no confounder was adjusted for, and a cause the engine never proposed receives no share -- so the shares sum to one over the modelled causes and not over the real ones. Two weights are comparable to each other. Neither is a quantity of anything in the world.

## Where the sweep stopped

The sweep ran to completion within the declared bounds.

## What this run did not check

- **Whether the answer is right.** No labelled causal ground truth exists for this dataset, so no counterfactual here can be scored against what actually would have happened. prd.md §57 names 'counterfactual plausibility' as a metric and defines it nowhere; nothing in this repository can compute it (OQ-030).
- **Whether a condition that should have stopped holding did.** A qualified link's condition was re-checked by asking whether its recorded expression NAMES anything this change touched. That test is conservative: it stops a link it cannot prove should keep transmitting, so consequences are under-claimed rather than over-claimed. It cannot see a condition that should have stopped holding and names nothing that changed.
- **Whether the ontology's changeability declarations are true.** A `mutable: true` on an attribute no operator could really have set is a declaration that loads cleanly and is wrong, and nothing here can detect it (R-16).
- **Anything at dataset scale.** Every figure above is a property of the slice this run walked, not of the dataset (OQ-023).