# Structural Pattern Report

For the reader who wants the shape of the run rather than one incident (prd.md §10, Executive Leadership).

- standing: `UNPROMOTED_DIAGNOSTIC`
- `run_id`: `run:f5e7ab410fa9eeb4`
- `report_schema_version`: `1.0.0`
- links examined: 9492
- distinct type-level shapes examined: 161

> **THIS IS NOT THE ENGINE'S VIEW. Every link below was considered and NOT asserted -- it did not clear the band its pack declares, or its precedence could not be established, or too little was measured on it to say. The traversal is real, the arithmetic is real, and the conclusion is disowned. It is published so that a reader can see what the machinery does and can check it, and so that the reason the stated view is empty is visible as a property of the inputs rather than as an absence of output. Nothing here may be cited as a cause, and nothing here is an input to simulation or to recommendation.**

## What this report does not contain

**An empty list below is not a finding that there are no patterns.** It may mean the pack declared no threshold, in which case nothing was looked for; or that the threshold was not reached, in which case something was. Every empty section carries a sentence saying which.

Motifs are enumerated to length **2** at this version, against a declared `motif_maximum_length` of 4. Longer shapes were not searched for, so their absence here is not evidence of their absence in the run.

Everything below is measured over the **event-type projection**, never over event instances. A claim about instances is unique by construction, so a recurrence counter running at that level could only ever return one. The cost of that choice is stated rather than hidden: a shape reported here may be carried by a single instance repeating, which is why every row carries the number of process instances it spans beside its raw count.

## Recurring motifs

| cause type | effect type | claims | instances spanned | support floor |
|---|---|---:|---:|---:|
| `SHIPMENT_IN_TRANSIT` | `SHIPMENT_DISPATCHED` | 793 | 137 | 3 |
| `SHIPMENT_DISPATCHED` | `SHIPMENT_IN_TRANSIT` | 730 | 137 | 3 |
| `SHIPMENT_DELAYED` | `SHIPMENT_DELIVERED` | 644 | 138 | 3 |
| `SHIPMENT_DELAYED` | `SHIPMENT_IN_TRANSIT` | 604 | 135 | 3 |
| `SHIPMENT_IN_TRANSIT` | `ORDER_PLACED` | 502 | 142 | 3 |
| `SHIPMENT_DELAYED` | `ORDER_PLACED` | 448 | 142 | 3 |
| `SHIPMENT_IN_TRANSIT` | `SHIPMENT_DELAYED` | 444 | 101 | 3 |
| `SHIPMENT_IN_TRANSIT` | `SHIPMENT_IN_TRANSIT` | 379 | 134 | 3 |
| `SHIPMENT_IN_TRANSIT` | `SHIPMENT_DELIVERED` | 304 | 135 | 3 |
| `SHIPMENT_DELAYED` | `SHIPMENT_DISPATCHED` | 204 | 78 | 3 |
| `ORDER_PLACED` | `ORDER_PLACED` | 182 | 113 | 3 |
| `SHIPMENT_DISPATCHED` | `SHIPMENT_DELAYED` | 175 | 96 | 3 |
| `ORDER_PLACED` | `SHIPMENT_DELIVERED` | 172 | 100 | 3 |
| `ITEM_PACKED` | `ITEM_PICKED` | 163 | 0 | 3 |
| `ITEM_PICKED` | `ITEM_PACKED` | 163 | 0 | 3 |
| `SHIPMENT_DISPATCHED` | `ITEM_PACKED` | 163 | 137 | 3 |
| `SHIPMENT_DISPATCHED` | `ITEM_PICKED` | 163 | 137 | 3 |
| `ITEM_PACKED` | `SHIPMENT_DISPATCHED` | 161 | 137 | 3 |
| `SHIPMENT_DISPATCHED` | `SHIPMENT_DELIVERED` | 161 | 137 | 3 |
| `SHIPMENT_DELAYED` | `SHIPMENT_DELAYED` | 136 | 71 | 3 |
| `ORDER_PLACED` | `PAYMENT_REQUESTED` | 112 | 104 | 3 |
| `SHIPMENT_DELIVERED` | `PAYMENT_REQUESTED` | 110 | 104 | 3 |
| `SHIPMENT_DISPATCHED` | `PAYMENT_REQUESTED` | 110 | 104 | 3 |
| `SHIPMENT_IN_TRANSIT` | `PAYMENT_REQUESTED` | 102 | 102 | 3 |
| `SHIPMENT_DISPATCHED` | `SHIPMENT_DISPATCHED` | 92 | 79 | 3 |
| `SHIPMENT_DELIVERED` | `ORDER_PLACED` | 82 | 74 | 3 |
| `SHIPMENT_DELAYED` | `PAYMENT_REQUESTED` | 74 | 74 | 3 |
| `SHIPMENT_DELIVERED` | `SHIPMENT_DELIVERED` | 70 | 68 | 3 |
| `ORDER_PLACED` | `SHIPMENT_IN_TRANSIT` | 57 | 54 | 3 |
| `INVENTORY_RESERVED` | `ITEM_PACKED` | 48 | 48 | 3 |
| ... | 109 further row(s) in the JSON artifact | | | |

## Chronic bottlenecks

In-degree and out-degree are separate columns and are never summed. A type consequence collects at and a type consequence originates from are different structures needing different responses.

| type | caused by (types) | causes (types) | claims touching | floor |
|---|---:|---:|---:|---:|
| `ORDER_PLACED` | 13 | 16 | 2033 | 5 |
| `SHIPMENT_DELAYED` | 11 | 16 | 3076 | 5 |
| `SHIPMENT_DELIVERED` | 13 | 15 | 1963 | 5 |
| `SHIPMENT_DISPATCHED` | 13 | 14 | 3068 | 5 |
| `PAYMENT_REQUESTED` | 13 | 13 | 907 | 5 |
| `SHIPMENT_IN_TRANSIT` | 12 | 13 | 4517 | 5 |
| `INVENTORY_RESERVED` | 11 | 11 | 704 | 5 |
| `PAYMENT_REVIEW_OPENED` | 10 | 9 | 105 | 5 |
| `ORDER_CLOSED` | 9 | 8 | 80 | 5 |
| `ORDER_COMPLETED` | 9 | 9 | 320 | 5 |
| `PAYMENT_APPROVED` | 9 | 9 | 501 | 5 |
| `ORDER_HELD` | 8 | 7 | 93 | 5 |
| `PAYMENT_FAILED` | 8 | 4 | 90 | 5 |
| `ITEM_PACKED` | 5 | 5 | 808 | 5 |
| `ITEM_PICKED` | 5 | 5 | 671 | 5 |
| `ORDER_CANCELED` | 5 | 3 | 23 | 5 |
