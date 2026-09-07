# Root Cause Analysis — the unpromoted diagnostic view

> **BOUNDED RUN.** Built from the first 150 rows of the clean layer, not from
> all 180,519. Neither module 9 nor module 10 is a streaming module -- the base
> rates measure across process instances and the fusion needs the whole candidate
> graph in hand -- and the full expansion does not fit in memory as models on an 8 GB
> machine (`tests/integration/test_full_expansion_budget.py`). **Every number below
> measures this slice, not the dataset.** Re-run with `--rows 0` to remove the bound.

- standing: `UNPROMOTED_DIAGNOSTIC`
- `run_id`: `run:f5e7ab410fa9eeb4`
- links available in this view: 9,492

> **THIS IS NOT THE ENGINE'S VIEW. Every link below was considered and NOT asserted -- it did not clear the band its pack declares, or its precedence could not be established, or too little was measured on it to say. The traversal is real, the arithmetic is real, and the conclusion is disowned. It is published so that a reader can see what the machinery does and can check it, and so that the reason the stated view is empty is visible as a property of the inputs rather than as an absence of output. Nothing here may be cited as a cause, and nothing here is an input to simulation or to recommendation.**

## Case 1

- outcome: `evt:015bd166df4b2162`
- declared delay on this instance: **4.000000**
- standing: `UNPROMOTED_DIAGNOSTIC`
- candidates considered: 500

### The four views

| view | event | type | actionable |
|---|---|---|---|
| `EARLIEST_EVENT` | `evt:20bb40aac7262476` | `ITEM_PACKED` | yes |
| `HIGHEST_CONSEQUENCE_EVENT` | `evt:ca4b613ed2c63379` | `SHIPMENT_DELAYED` | yes |
| `MOST_ACTIONABLE_EVENT` | `evt:ced405405ab0617e` | `ORDER_CANCELED` | yes |
| `RECOMMENDED_ROOT_CAUSE` | *none* | -- | -- |

**Trade-off — `EARLIEST_EVENT` vs `HIGHEST_CONSEQUENCE_EVENT`.** `evt:20bb40aac7262476` against `evt:ca4b613ed2c63379`.

**Trade-off — `EARLIEST_EVENT` vs `MOST_ACTIONABLE_EVENT`.** `evt:20bb40aac7262476` against `evt:ced405405ab0617e`.

**Trade-off — `HIGHEST_CONSEQUENCE_EVENT` vs `MOST_ACTIONABLE_EVENT`.** `evt:ca4b613ed2c63379` against `evt:ced405405ab0617e`.

### Propagation from the recommended cause

- depth **5**, breadth **487** (never averaged)
- consequences reached: 1223
- affected entities: 500
- combined magnitude: **0.571429** DAYS under `MAXIMUM`, resting on 235 of 1223 consequence(s)

### Ranked causes

| cause | type | actionable | earliness | prevents | chain | links | recurs |
|---|---|---|---:|---|---:|---:|---:|
| `evt:035729f316c8b0dd` | `SHIPMENT_IN_TRANSIT` | no | 8 | 4.000000 DAYS | 0.250000 | 1 | 304 |
| `evt:076746e26240751e` | `SHIPMENT_DELAYED` | yes | 8 | 4.000000 DAYS | 0.250000 | 1 | 644 |
| `evt:08ff1f631be0ee08` | `SHIPMENT_IN_TRANSIT` | no | 8 | 4.000000 DAYS | 0.250000 | 1 | 304 |
| `evt:21c68090b5f8a1aa` | `SHIPMENT_DELAYED` | yes | 8 | 4.000000 DAYS | 0.250000 | 1 | 644 |
| `evt:27363da3dbeedd43` | `SHIPMENT_DELAYED` | yes | 8 | 4.000000 DAYS | 0.250000 | 1 | 644 |
| `evt:2a39f5e48c33502b` | `SHIPMENT_DELAYED` | yes | 8 | 4.000000 DAYS | 0.250000 | 1 | 644 |
| `evt:356448453b80591e` | `SHIPMENT_DELAYED` | yes | 8 | 4.000000 DAYS | 0.250000 | 1 | 644 |
| `evt:007d411e04707d0d` | `SHIPMENT_IN_TRANSIT` | no | 7 | 4.000000 DAYS | 0.250000 | 2 | 304 |

**500 of 500 chain(s) carry a partial-data flag.** PARTIAL DATA: 1 event(s) on this chain were never placed in time by the source; 1 event(s) carry an instant that was computed rather than recorded. The chain is ranked and this flag travels with it into every explanation built on it. A precedence resting on a computed instant is a precedence resting on the arithmetic that produced it.

## Case 2

- outcome: `evt:0a8cc6602ef4cf45`
- declared delay on this instance: **4.000000**
- standing: `UNPROMOTED_DIAGNOSTIC`
- candidates considered: 500

### The four views

| view | event | type | actionable |
|---|---|---|---|
| `EARLIEST_EVENT` | `evt:0ce4e764d342ab4d` | `PAYMENT_REQUESTED` | no |
| `HIGHEST_CONSEQUENCE_EVENT` | `evt:3742ef3d5682bb69` | `ITEM_PACKED` | yes |
| `MOST_ACTIONABLE_EVENT` | `evt:d4f280e953222884` | `PAYMENT_APPROVED` | yes |
| `RECOMMENDED_ROOT_CAUSE` | *none* | -- | -- |

**Trade-off — `EARLIEST_EVENT` vs `HIGHEST_CONSEQUENCE_EVENT`.** `evt:0ce4e764d342ab4d` against `evt:3742ef3d5682bb69`.

**Trade-off — `EARLIEST_EVENT` vs `MOST_ACTIONABLE_EVENT`.** `evt:0ce4e764d342ab4d` against `evt:d4f280e953222884`.

**Trade-off — `HIGHEST_CONSEQUENCE_EVENT` vs `MOST_ACTIONABLE_EVENT`.** `evt:3742ef3d5682bb69` against `evt:d4f280e953222884`.

### Propagation from the recommended cause

- depth **6**, breadth **150** (never averaged)
- consequences reached: 216
- affected entities: 500
- combined magnitude: **0.500000** DAYS under `MAXIMUM`, resting on 64 of 216 consequence(s)

### Ranked causes

| cause | type | actionable | earliness | prevents | chain | links | recurs |
|---|---|---|---:|---|---:|---:|---:|
| `evt:0334d401b2de1c02` | `SHIPMENT_IN_TRANSIT` | no | 9 | 4.000000 DAYS | 0.250000 | 1 | 304 |
| `evt:0d3a3931613475a9` | `SHIPMENT_DELAYED` | yes | 9 | 4.000000 DAYS | 0.250000 | 1 | 644 |
| `evt:15b78339372376f3` | `SHIPMENT_IN_TRANSIT` | no | 9 | 4.000000 DAYS | 0.250000 | 1 | 304 |
| `evt:1f97bf389cd639b9` | `SHIPMENT_DELAYED` | yes | 9 | 4.000000 DAYS | 0.250000 | 1 | 644 |
| `evt:25132823dd208b04` | `SHIPMENT_DELAYED` | yes | 9 | 4.000000 DAYS | 0.250000 | 1 | 644 |
| `evt:2ec4eeb658130510` | `SHIPMENT_DELAYED` | yes | 9 | 4.000000 DAYS | 0.250000 | 1 | 644 |
| `evt:523c664a6f3f29a5` | `SHIPMENT_DELAYED` | yes | 9 | 4.000000 DAYS | 0.250000 | 1 | 644 |
| `evt:0392cc05df7c7b20` | `SHIPMENT_DISPATCHED` | yes | 8 | 4.000000 DAYS | 0.250000 | 2 | 161 |

**500 of 500 chain(s) carry a partial-data flag.** PARTIAL DATA: 1 event(s) on this chain were never placed in time by the source; 1 event(s) carry an instant that was computed rather than recorded. The chain is ranked and this flag travels with it into every explanation built on it. A precedence resting on a computed instant is a precedence resting on the arithmetic that produced it.

## Case 3

- outcome: `evt:3c35f1c1b640806c`
- declared delay on this instance: **4.000000**
- standing: `UNPROMOTED_DIAGNOSTIC`
- candidates considered: 500

### The four views

| view | event | type | actionable |
|---|---|---|---|
| `EARLIEST_EVENT` | `evt:0ce4e764d342ab4d` | `PAYMENT_REQUESTED` | no |
| `HIGHEST_CONSEQUENCE_EVENT` | `evt:00d2da6a83269c76` | `PAYMENT_APPROVED` | yes |
| `MOST_ACTIONABLE_EVENT` | `evt:00d2da6a83269c76` | `PAYMENT_APPROVED` | yes |
| `RECOMMENDED_ROOT_CAUSE` | *none* | -- | -- |

**Trade-off — `EARLIEST_EVENT` vs `HIGHEST_CONSEQUENCE_EVENT`.** `evt:0ce4e764d342ab4d` against `evt:00d2da6a83269c76`.

**Trade-off — `EARLIEST_EVENT` vs `MOST_ACTIONABLE_EVENT`.** `evt:0ce4e764d342ab4d` against `evt:00d2da6a83269c76`.

### Propagation from the recommended cause

- depth **3**, breadth **4** (never averaged)
- consequences reached: 8
- affected entities: 500
- combined magnitude: none — no consequence carried an evaluable magnitude; each one's reason is on its node.

### Ranked causes

| cause | type | actionable | earliness | prevents | chain | links | recurs |
|---|---|---|---:|---|---:|---:|---:|
| `evt:0334d401b2de1c02` | `SHIPMENT_IN_TRANSIT` | no | 9 | 4.000000 DAYS | 0.250000 | 1 | 304 |
| `evt:0d3a3931613475a9` | `SHIPMENT_DELAYED` | yes | 9 | 4.000000 DAYS | 0.250000 | 1 | 644 |
| `evt:15b78339372376f3` | `SHIPMENT_IN_TRANSIT` | no | 9 | 4.000000 DAYS | 0.250000 | 1 | 304 |
| `evt:1f97bf389cd639b9` | `SHIPMENT_DELAYED` | yes | 9 | 4.000000 DAYS | 0.250000 | 1 | 644 |
| `evt:25132823dd208b04` | `SHIPMENT_DELAYED` | yes | 9 | 4.000000 DAYS | 0.250000 | 1 | 644 |
| `evt:2ec4eeb658130510` | `SHIPMENT_DELAYED` | yes | 9 | 4.000000 DAYS | 0.250000 | 1 | 644 |
| `evt:523c664a6f3f29a5` | `SHIPMENT_DELAYED` | yes | 9 | 4.000000 DAYS | 0.250000 | 1 | 644 |
| `evt:0392cc05df7c7b20` | `SHIPMENT_DISPATCHED` | yes | 8 | 4.000000 DAYS | 0.250000 | 2 | 161 |

**500 of 500 chain(s) carry a partial-data flag.** PARTIAL DATA: 1 event(s) on this chain were never placed in time by the source; 1 event(s) carry an instant that was computed rather than recorded. The chain is ranked and this flag travels with it into every explanation built on it. A precedence resting on a computed instant is a precedence resting on the arithmetic that produced it.

## Case 4

- outcome: `evt:3f48319b818320c1`
- declared delay on this instance: **4.000000**
- standing: `UNPROMOTED_DIAGNOSTIC`
- candidates considered: 500

### The four views

| view | event | type | actionable |
|---|---|---|---|
| `EARLIEST_EVENT` | `evt:0ce4e764d342ab4d` | `PAYMENT_REQUESTED` | no |
| `HIGHEST_CONSEQUENCE_EVENT` | `evt:22cff3c05253a2ed` | `PAYMENT_REQUESTED` | no |
| `MOST_ACTIONABLE_EVENT` | `evt:d4f280e953222884` | `PAYMENT_APPROVED` | yes |
| `RECOMMENDED_ROOT_CAUSE` | *none* | -- | -- |

**Trade-off — `EARLIEST_EVENT` vs `HIGHEST_CONSEQUENCE_EVENT`.** `evt:0ce4e764d342ab4d` against `evt:22cff3c05253a2ed`.

**Trade-off — `EARLIEST_EVENT` vs `MOST_ACTIONABLE_EVENT`.** `evt:0ce4e764d342ab4d` against `evt:d4f280e953222884`.

**Trade-off — `HIGHEST_CONSEQUENCE_EVENT` vs `MOST_ACTIONABLE_EVENT`.** `evt:22cff3c05253a2ed` against `evt:d4f280e953222884`.

### Propagation from the recommended cause

- depth **2**, breadth **4** (never averaged)
- consequences reached: 5
- affected entities: 500
- combined magnitude: none — no consequence carried an evaluable magnitude; each one's reason is on its node.

### Ranked causes

| cause | type | actionable | earliness | prevents | chain | links | recurs |
|---|---|---|---:|---|---:|---:|---:|
| `evt:2842e1fd09928640` | `SHIPMENT_DISPATCHED` | yes | 9 | 4.000000 DAYS | 0.365507 | 1 | 161 |
| `evt:007d411e04707d0d` | `SHIPMENT_IN_TRANSIT` | no | 9 | 4.000000 DAYS | 0.250000 | 1 | 304 |
| `evt:7b40b2645a990f11` | `SHIPMENT_DELAYED` | yes | 9 | 4.000000 DAYS | 0.250000 | 1 | 644 |
| `evt:e2834cc07d85f278` | `SHIPMENT_IN_TRANSIT` | no | 9 | 4.000000 DAYS | 0.250000 | 1 | 304 |
| `evt:e64fb949340e784e` | `SHIPMENT_DELAYED` | yes | 9 | 4.000000 DAYS | 0.250000 | 1 | 644 |
| `evt:0392cc05df7c7b20` | `SHIPMENT_DISPATCHED` | yes | 8 | 4.000000 DAYS | 0.250000 | 2 | 161 |
| `evt:044bb13e02bd02c9` | `SHIPMENT_DISPATCHED` | yes | 8 | 4.000000 DAYS | 0.250000 | 2 | 161 |
| `evt:0abbd2e98bb18c61` | `SHIPMENT_DISPATCHED` | yes | 8 | 4.000000 DAYS | 0.250000 | 2 | 161 |

**500 of 500 chain(s) carry a partial-data flag.** PARTIAL DATA: 2 event(s) carry an instant that was computed rather than recorded. The chain is ranked and this flag travels with it into every explanation built on it. A precedence resting on a computed instant is a precedence resting on the arithmetic that produced it.

## Case 5

- outcome: `evt:67ecbde833a19000`
- declared delay on this instance: **4.000000**
- standing: `UNPROMOTED_DIAGNOSTIC`
- candidates considered: 500

### The four views

| view | event | type | actionable |
|---|---|---|---|
| `EARLIEST_EVENT` | `evt:e6e94350860b1ce5` | `SHIPMENT_IN_TRANSIT` | no |
| `HIGHEST_CONSEQUENCE_EVENT` | `evt:22cff3c05253a2ed` | `PAYMENT_REQUESTED` | no |
| `MOST_ACTIONABLE_EVENT` | `evt:88e68b515fcd7dbc` | `PAYMENT_APPROVED` | yes |
| `RECOMMENDED_ROOT_CAUSE` | *none* | -- | -- |

**Trade-off — `EARLIEST_EVENT` vs `HIGHEST_CONSEQUENCE_EVENT`.** `evt:e6e94350860b1ce5` against `evt:22cff3c05253a2ed`.

**Trade-off — `EARLIEST_EVENT` vs `MOST_ACTIONABLE_EVENT`.** `evt:e6e94350860b1ce5` against `evt:88e68b515fcd7dbc`.

**Trade-off — `HIGHEST_CONSEQUENCE_EVENT` vs `MOST_ACTIONABLE_EVENT`.** `evt:22cff3c05253a2ed` against `evt:88e68b515fcd7dbc`.

### Propagation from the recommended cause

- depth **6**, breadth **591** (never averaged)
- consequences reached: 793
- affected entities: 500
- combined magnitude: **0.571429** DAYS under `MAXIMUM`, resting on 218 of 793 consequence(s)

### Ranked causes

| cause | type | actionable | earliness | prevents | chain | links | recurs |
|---|---|---|---:|---|---:|---:|---:|
| `evt:67b8dbbe6a8d4e15` | `SHIPMENT_DISPATCHED` | yes | 10 | 4.000000 DAYS | 0.261771 | 1 | 161 |
| `evt:79b05cf4643894ac` | `ITEM_PACKED` | yes | 9 | 4.000000 DAYS | 0.261771 | 2 | 24 |
| `evt:d5177e1601f1a5e9` | `ITEM_PACKED` | yes | 9 | 4.000000 DAYS | 0.261771 | 2 | 24 |
| `evt:40ccbb3b2c64a3e0` | `ITEM_PICKED` | yes | 8 | 4.000000 DAYS | 0.261771 | 3 | 30 |
| `evt:f85532b479a293a8` | `ITEM_PICKED` | yes | 8 | 4.000000 DAYS | 0.261771 | 3 | 30 |
| `evt:005ed1068f0114b5` | `SHIPMENT_DELAYED` | yes | 10 | 4.000000 DAYS | 0.250000 | 1 | 644 |
| `evt:1ebc9860caa5bdeb` | `SHIPMENT_DELAYED` | yes | 10 | 4.000000 DAYS | 0.250000 | 1 | 644 |
| `evt:21aada7cf3df1037` | `SHIPMENT_DELAYED` | yes | 10 | 4.000000 DAYS | 0.250000 | 1 | 644 |

**500 of 500 chain(s) carry a partial-data flag.** PARTIAL DATA: 2 event(s) carry an instant that was computed rather than recorded. The chain is ranked and this flag travels with it into every explanation built on it. A precedence resting on a computed instant is a precedence resting on the arithmetic that produced it.
