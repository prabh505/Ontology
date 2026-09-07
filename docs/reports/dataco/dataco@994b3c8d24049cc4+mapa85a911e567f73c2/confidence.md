# Confidence Report

> **BOUNDED RUN.** Built from the first 60 rows of the clean layer, not from
> all 180,519. Neither module 9 nor module 10 is a streaming module -- the base
> rates measure across process instances and the fusion needs the whole candidate
> graph in hand -- and the full expansion does not fit in memory as models on an 8 GB
> machine (`tests/integration/test_full_expansion_budget.py`). **Every number below
> measures this slice, not the dataset.** Re-run with `--rows 0` to remove the bound.

- `report_schema_version`: `1.1.0`
- `confidence_schema_version`: `2.0.0` (eight components)
- `run_id`: `run:f5e7ab410fa9eeb4`
- aggregation strategy: `gated_weighted_mean_v1`
- candidate edges read: 7330
- claims scored (one per source, target, kind): 4113

## What is not calibrated

**THESE SCORES ARE NOT CALIBRATED.** Calibration means that claims scored 0.8 turn out to be right about eighty per cent of the time, and measuring it requires labelled causal ground truth: a set of pairs where someone independently established what actually caused what. This repository holds none. The reference dataset carries no causal annotation, and no fixture set of known causes exists, so no reliability curve can be drawn and no error rate can be quoted.

What the numbers below ARE is internally consistent: every component is computed from stated inputs by a named function, the aggregation is monotone and gated, and the whole vector is reproducible from the artifact. That is a real property and it is a much weaker one than calibration. Two scores ranking correctly relative to each other says nothing about either being right.

The component weights are a stated editorial judgement, not a measurement. Nothing fitted them, because there was nothing to fit them against. They are written down in one place (`causalog.core.aggregation.V2_ADDEND_WEIGHTS`) precisely so that disagreement has somewhere to point.

## Components that could not be measured

These were emitted at zero and marked missing rather than being omitted. An omitted component would renormalize away and every edge would score as though the measurement had been made and found irrelevant. Missing costs score, and the cost is stated here.

| component | missing on | share | needs |
|---|---:|---:|---|
| `graph_connectivity` | 4113 / 4113 | 1.000000 | at least one Relationship in the fact set. The relationship graph is module 7's output and module 8's projection, and neither exists yet (CONTEXT.md section 3) -- so this component is MISSING on every edge today rather than scored zero or silently omitted, and every edge is scored lower for it. |
| `rule_support` | 3158 / 4113 | 0.767809 | at least one EvidenceKind.RULE item on the fused claim. A claim no rule proposed has no rule support to measure -- which is not the same as a claim the pack argues against, and is scored as missing rather than as zero. |
| `historical_support` | 1373 / 4113 | 0.333820 | confidence_scoring.lift_reference and confidence_scoring.small_sample_prior_count, plus a contingency table for this event-type pair -- which requires the pair to have been observed in sequence in at least one process instance, and the effect type to occur at all so a baseline rate exists. |
| `statistical_support` | 1373 / 4113 | 0.333820 | confidence_scoring.lift_reference and confidence_scoring.small_sample_prior_count, plus a contingency table with a non-zero baseline rate for this event-type pair. Without a baseline there is no independence to measure a departure from. |

## Was this run told which instants the source computed?

Audited. **1 declared derivation check(s) were confirmed**, and 6 claim(s) had `temporal_support` capped as a result.

A capped claim is not a rejected one. Its precedence holds; what it lacks is any evidence that the precedence was OBSERVED. The cap is the value the rule pack declares, and each affected edge names the check that fired.

## Components that distinguish nothing

A component holding one value on every edge carries a weight and separates no two claims. This is the same defect module 9's report calls a saturated generator, one layer on.

- **`graph_connectivity`** MISSING on all 4113 edge(s), so it holds 0.000000 everywhere. Its weight is being applied to an absence: every edge is scored lower for a measurement nobody made. That is the honest treatment, and it is also a standing argument for building what would supply it.

## Outcome: scored, versus not enough measured

Two counts, never summed. `INSUFFICIENT_EVIDENCE` is **not** a low score: it is the absence of a measurement, and showing it as a weak claim would present a gap as a finding (`docs/contracts.md` §3's distinction, carried into scoring).

- **`SCORED`**: 3205
- **`INSUFFICIENT_EVIDENCE`**: 908 (0.220763 of claims)
- **promoted to `INFERRED` by this module**: 0

**Promotion is no longer this module's decision (ADR-0054).** It moved to `causal_engine.causal_graph_builder`, which owns an explicit per-edge-kind selection policy declared in the rule pack's `graph_construction` namespace. The count above is structurally zero from that commit forward and is NOT a finding about the data; the Graph Quality Report is where promotion is counted, with the reason every rejected claim was rejected. `confidence_scoring.promotion_band` is deprecated and the loader warns about it.

### How many components were actually measured

The distribution the outcome floor is set against. A floor at or below this histogram's minimum can never fire, and an `INSUFFICIENT_EVIDENCE` count of zero under such a floor says nothing about the data -- it says the threshold does not exist.

| components measured (of 8) | edges |
|---:|---:|
| 4 | 908 |
| 5 | 465 |
| 6 | 2250 |
| 7 | 490 |

Declared floor: **5**.

INSUFFICIENT EVIDENCE. Fewer components could be measured than this pack requires before it calls an edge scored. The scalar below is arithmetic over a vector that is mostly absence, and it is NOT a finding that the claim is weak -- it is a statement that not enough was measured to have a finding. Read the component breakdown: the components marked missing say what was never looked at.

## Which gate bound the score

`temporal_support` and `contradiction_freedom` are ceilings, not addends: they cap the score rather than being outvoted by it (ADR-0052). This table says how often each was the binding constraint. A dominant temporal share is a finding about the source's granularity, not about the claims (`CONTEXT.md` R-14).

| binding gate | edges | share |
|---|---:|---:|
| `contradiction_freedom` | 28 | 0.006808 |
| none (the weighted mean stood) | 2358 | 0.573304 |
| `temporal_support` | 1727 | 0.419888 |

## Confidence distribution

- edges: 4113
- minimum: 0.030000 · median: 0.214988 · mean: 0.171071 · maximum: 0.400000

| scalar (up to) | edges |
|---:|---:|
| 0.100000 | 1396 |
| 0.200000 | 424 |
| 0.300000 | 2127 |
| 0.400000 | 166 |
| 0.500000 | 0 |
| 0.600000 | 0 |
| 0.700000 | 0 |
| 0.800000 | 0 |
| 0.900000 | 0 |
| 1.000000 | 0 |

## Bands

Thresholds and wording are declared in the rule pack, not in engine or UI code (ADR-0053). A boundary in a component is a policy no reviewer can find and two screens can silently disagree about.

### `STRONG` — scalar at or above 0.700000

0 edge(s).

> Strong evidence. Several independent lines of support agree, the ordering of the two events is established, and nothing on record contradicts the claim. Still not proof of causation: this engine measures support, and no part of it identifies a causal effect.

### `SUGGESTIVE` — scalar at or above 0.450000

0 edge(s).

> Suggestive. There is real support here, but at least one leg is weak -- commonly the ordering, which on this dataset is frequently unresolvable. Worth investigating; not worth acting on alone.

### `WEAK` — scalar at or above 0.000000

3205 edge(s).

> Weak -- inspect before acting. Either the support is thin, the ordering could not be established, or something on record argues against the claim. The breakdown beside this label says which; read it before using this edge for anything.


## Per-component distribution

| component | missing | min | median | mean | max |
|---|---:|---:|---:|---:|---:|
| `contradiction_freedom` | 0 | 0.095238 | 0.454545 | 0.467039 | 1.000000 |
| `evidence_count` | 0 | 0.250000 | 0.250000 | 0.379735 | 0.769231 |
| `evidence_diversity` | 0 | 0.000000 | 0.000000 | 0.195539 | 1.000000 |
| `graph_connectivity` | 4113 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| `historical_support` | 1373 | 0.000000 | 0.236458 | 0.287948 | 0.714747 |
| `rule_support` | 3158 | 0.000000 | 0.000000 | 0.176144 | 0.810000 |
| `statistical_support` | 1373 | 0.000000 | 0.115302 | 0.223301 | 0.693361 |
| `temporal_support` | 0 | 0.000000 | 0.000000 | 0.039123 | 0.998625 |

## The 10 highest-scoring edges, in full

Every component of every edge below, with the arithmetic that produced it. This is what prd.md §49 asks for: never a single unexplained number.

> **THIS IS NOT A RANKING OF THE TOP 10.** 110 edges share the maximum scalar of 0.400000, which is more than this section prints. They are tied because a **gate** put them there: a ceiling maps every edge above it onto one value, so the claims below are a canonical slice of a tie, not the best-supported claims in the graph. Read them as examples of what sits at the ceiling. Anything that looks like a ranking between them is the sort key, not the evidence.

### 1. `evt:01118fd81bdb6ef1` → `evt:d30426e039dc42d6`

- `causal_edge_id`: `edg:46ff1624967c73f1`
- edge kind: `DIRECT`
- **confidence: 0.400000** via `gated_weighted_mean_v1`
- band: WEAK
- outcome: `SCORED` (7 of 8 components measured)
- provenance: `STATISTICAL` · temporal verdict: `UNDETERMINED` · temporally unverifiable: false
- weighted mean of the addends before gating: 0.603136; binding gate: temporal_support

> Weak -- inspect before acting. Either the support is thin, the ordering could not be established, or something on record argues against the claim. The breakdown beside this label says which; read it before using this edge for anything.

**`contradiction_freedom` = 0.769231**

This claim has counter-evidence against it, so its score is capped. Higher is better here: 1.0 means nothing argues against the claim, and this edge scores 0.769. What was found: reverse pair (the opposite direction was independently proposed).

- constraint prohibition: `no`
- rule conflicts touching this pair: `0`
- reverse pair also proposed: `yes`
- confounding flags on this edge: `0`
- total contradiction weight: `0.300000`
- half-at: `1.000000`
- ⚠ READ THE DIRECTION. This component is inverted relative to its name in the brief: it scores FREEDOM from contradiction, so a HIGH value means LITTLE counter-evidence. It is named this way so that every component rises with support and the aggregation stays monotone (ADR-0052).
- ⚠ A confounding flag is not counter-evidence. It marks a structure that could explain the association without this edge being real. Nothing at V1 resolves it, and the ABSENCE of a flag is not evidence of no confounding -- an unobserved common cause leaves no shape in a graph built from observed events (CONTEXT.md R-05).
- ⚠ Absence of contradiction is not support. A claim nothing argues against still needs evidence FOR it, which the other seven components supply.

**`evidence_count` = 0.727273**

8 distinct justification(s) support this pair. The scale is saturating: this pack is half convinced at 3, and each further justification adds less than the one before it.

- distinct evidence items: `8`
- generators reaching this pair: `5`
- declared saturation k: `3`
- ⚠ This counts justifications; it does not ask whether they are independent. Ten items of one kind score the same here as ten items of ten kinds. The evidence_diversity component is what separates them, and it is weighted higher than this one.
- ⚠ Evidence items are deduplicated by content address, so two generators minting a byte-identical justification contribute one item, not two.

**`evidence_diversity` = 1.000000**

Support for this pair comes from 5 distinct kind(s) of evidence, produced by 5 independent generator(s): HISTORICAL_FREQUENCY, RULE, SHARED_ENTITY, STATISTICAL_ASSOCIATION, TEMPORAL_PROXIMITY via historical_frequency, rule_based, shared_entity, statistical_association, temporal_proximity. Independent lines of reasoning reaching one conclusion count for more than one line repeated, which is why this is weighted above raw evidence count.

- distinct evidence kinds: `5`
- reachable kinds this run: `5`
- kind spread: `1.000000`
- distinct generators: `5`
- reachable generators this run: `5`
- generator spread: `1.000000`
- total evidence items: `8`
- ⚠ Independence here means different reasoning, not statistical independence. Two generators can rest on the same underlying coincidence in the data -- the shared-entity and shared-identifier generators are the obvious pair -- and nothing here detects that.
- ⚠ Normalized against what THIS run could reach, not against the full vocabulary. A run with generators that could not run has a smaller denominator, so diversity scores are not comparable across runs with different generator availability.

**`graph_connectivity` = 0.000000** *(MISSING)*

Not scored: graph_connectivity could not be computed for this edge, so it contributes nothing. This is an absence of measurement, not a measurement of absence -- the edge is scored lower for it, and the gap is reported rather than hidden.

- *needs*: at least one Relationship in the fact set. The relationship graph is module 7's output and module 8's projection, and neither exists yet (CONTEXT.md section 3) -- so this component is MISSING on every edge today rather than scored zero or silently omitted, and every edge is scored lower for it.

**`historical_support` = 0.570272**

Across 310 process instances, 110 contained ITEM_PACKED and 106 of those went on to contain SHIPMENT_DISPATCHED. That is a rate of 0.964 against a baseline rate of 0.723 for SHIPMENT_DISPATCHED overall -- a lift of 1.334. The score is that lift on a declared scale, then discounted because 106 instances is a sample of that size.

- process instances (denominator): `310`
- instances with cause type: `110`
- instances with effect type: `224`
- instances with the sequenced pair: `106`
- cause only: `4`
- effect only: `118`
- neither: `82`
- conditional rate: `0.963636`
- baseline rate: `0.722581`
- lift: `1.333604`
- declared lift_reference: `3.000000`
- lift on the declared scale: `0.262044`
- declared small_sample_prior_count: `20`
- small-sample discount: `0.841270`
- blend: `sample-weighted: discount^(2/3) * lift^(1/3)`
- module 9 recurrence items on this edge: `2`
- ⚠ A lift of 1.0 is independence and scores zero. A pattern that appears in every instance is not evidence for anything, however large its count -- which is why the count alone is never the score.
- ⚠ Recurrence is not causation and carries no direction: this ratio is identical in both directions. The direction of this edge comes only from the temporal gate.
- ⚠ Computed over the pinned dataset version, and over whatever slice of it this run read. A different slice is a different number.

**`rule_support` = 0.690000**

1 authored rule justification(s) in the active pack support this pair. Their declared strengths are combined so that independent rules corroborate rather than average: two rules reaching the same conclusion by different reasoning say more than either alone.

- rule justifications: `1`
- authored strength [evi:6f95bc5e76261f52]: `0.690000`
- combined (noisy-OR): `0.690000`
- ⚠ A rule is a stated belief about the domain, not an observation of it. Strong rule support means the pack's authors expected this; it does not mean it happened.
- ⚠ Rules that a constraint suppressed, and conflicts the rule engine reported, are NOT subtracted here. They lower this edge through the contradiction_freedom component, so that weak support and contradicted support stay distinguishable.

**`statistical_support` = 0.386570**

Measure: lift over an instance-level 2x2 contingency table; no hypothesis test is performed. ITEM_PACKED and SHIPMENT_DISPATCHED co-occur, in that sequence, at 1.334 times the rate independence would predict, measured over 310 process instances of which 106 exhibit the pair. The score is that effect size on a declared scale, discounted for the size of the sample it was measured on.

- measure: `lift over an instance-level 2x2 contingency table; no hypothesis test is performed`
- sample size (process instances): `310`
- both: `106`
- cause only: `4`
- effect only: `118`
- neither: `82`
- effect size (lift): `1.333604`
- declared lift_reference: `3.000000`
- effect size on the declared scale: `0.262044`
- declared small_sample_prior_count: `20`
- sample-size discount: `0.841270`
- blend: `effect-weighted: discount^(1/3) * lift^(2/3)`
- p-value: `not computed; no null hypothesis is tested`
- ⚠ Lift measures co-occurrence against independence within one dataset version. It establishes NO causation, NO direction (lift is symmetric; this candidate's direction comes only from the LAW-TIME gate), NO freedom from confounding, and NO statistical significance -- no null is tested and no sampling distribution is assumed.
- ⚠ Confounding structures are present in this candidate graph and are REPORTED, not resolved. Nothing in V1 distinguishes a direct association from one explained by a third event, and the absence of a flag is not evidence of no confounding (CONTEXT.md R-05).

**`temporal_support` = 0.150000**

Both events were placed in time, but not precisely enough to say which came first. This scores the low value this rule pack declares for an unresolvable precedence, and CAPS the whole edge.

- temporal verdict: `UNDETERMINED`
- declared undetermined_temporal_support: `0.150000`
- ⚠ The events were placed; precedence was not resolved. That is more than an absent timestamp and much less than an established precedence.
- ⚠ A dominant UNDETERMINED share is a finding about the source's granularity (CONTEXT.md R-14). It is never resolved by loosening the test or by raising this number.
- ⚠ This edge can never be promoted to INFERRED (ADR-0007).

### 2. `evt:0928603480659239` → `evt:0ac91b7e7f7a6f0b`

- `causal_edge_id`: `edg:d6de2c11be8fd402`
- edge kind: `DIRECT`
- **confidence: 0.400000** via `gated_weighted_mean_v1`
- band: WEAK
- outcome: `SCORED` (7 of 8 components measured)
- provenance: `STATISTICAL` · temporal verdict: `UNDETERMINED` · temporally unverifiable: false
- weighted mean of the addends before gating: 0.521008; binding gate: temporal_support

> Weak -- inspect before acting. Either the support is thin, the ordering could not be established, or something on record argues against the claim. The breakdown beside this label says which; read it before using this edge for anything.

**`contradiction_freedom` = 0.303030**

This claim has counter-evidence against it, so its score is capped. Higher is better here: 1.0 means nothing argues against the claim, and this edge scores 0.303. What was found: reverse pair (the opposite direction was independently proposed); confounding flags (20).

- constraint prohibition: `no`
- rule conflicts touching this pair: `0`
- reverse pair also proposed: `yes`
- confounding flags on this edge: `20`
- total contradiction weight: `2.300000`
- half-at: `1.000000`
- ⚠ READ THE DIRECTION. This component is inverted relative to its name in the brief: it scores FREEDOM from contradiction, so a HIGH value means LITTLE counter-evidence. It is named this way so that every component rises with support and the aggregation stays monotone (ADR-0052).
- ⚠ A confounding flag is not counter-evidence. It marks a structure that could explain the association without this edge being real. Nothing at V1 resolves it, and the ABSENCE of a flag is not evidence of no confounding -- an unobserved common cause leaves no shape in a graph built from observed events (CONTEXT.md R-05).
- ⚠ Absence of contradiction is not support. A claim nothing argues against still needs evidence FOR it, which the other seven components supply.

**`evidence_count` = 0.727273**

8 distinct justification(s) support this pair. The scale is saturating: this pack is half convinced at 3, and each further justification adds less than the one before it.

- distinct evidence items: `8`
- generators reaching this pair: `5`
- declared saturation k: `3`
- ⚠ This counts justifications; it does not ask whether they are independent. Ten items of one kind score the same here as ten items of ten kinds. The evidence_diversity component is what separates them, and it is weighted higher than this one.
- ⚠ Evidence items are deduplicated by content address, so two generators minting a byte-identical justification contribute one item, not two.

**`evidence_diversity` = 1.000000**

Support for this pair comes from 5 distinct kind(s) of evidence, produced by 5 independent generator(s): HISTORICAL_FREQUENCY, RULE, SHARED_ENTITY, STATISTICAL_ASSOCIATION, TEMPORAL_PROXIMITY via historical_frequency, rule_based, shared_entity, statistical_association, temporal_proximity. Independent lines of reasoning reaching one conclusion count for more than one line repeated, which is why this is weighted above raw evidence count.

- distinct evidence kinds: `5`
- reachable kinds this run: `5`
- kind spread: `1.000000`
- distinct generators: `5`
- reachable generators this run: `5`
- generator spread: `1.000000`
- total evidence items: `8`
- ⚠ Independence here means different reasoning, not statistical independence. Two generators can rest on the same underlying coincidence in the data -- the shared-entity and shared-identifier generators are the obvious pair -- and nothing here detects that.
- ⚠ Normalized against what THIS run could reach, not against the full vocabulary. A run with generators that could not run has a smaller denominator, so diversity scores are not comparable across runs with different generator availability.

**`graph_connectivity` = 0.000000** *(MISSING)*

Not scored: graph_connectivity could not be computed for this edge, so it contributes nothing. This is an absence of measurement, not a measurement of absence -- the edge is scored lower for it, and the gap is reported rather than hidden.

- *needs*: at least one Relationship in the fact set. The relationship graph is module 7's output and module 8's projection, and neither exists yet (CONTEXT.md section 3) -- so this component is MISSING on every edge today rather than scored zero or silently omitted, and every edge is scored lower for it.

**`historical_support` = 0.312815**

Across 310 process instances, 110 contained ITEM_PICKED and 42 of those went on to contain ITEM_PACKED. That is a rate of 0.382 against a baseline rate of 0.355 for ITEM_PACKED overall -- a lift of 1.076. The score is that lift on a declared scale, then discounted because 42 instances is a sample of that size.

- process instances (denominator): `310`
- instances with cause type: `110`
- instances with effect type: `110`
- instances with the sequenced pair: `42`
- cause only: `68`
- effect only: `68`
- neither: `132`
- conditional rate: `0.381818`
- baseline rate: `0.354839`
- lift: `1.076033`
- declared lift_reference: `3.000000`
- lift on the declared scale: `0.066703`
- declared small_sample_prior_count: `20`
- small-sample discount: `0.677419`
- blend: `sample-weighted: discount^(2/3) * lift^(1/3)`
- module 9 recurrence items on this edge: `2`
- ⚠ A lift of 1.0 is independence and scores zero. A pattern that appears in every instance is not evidence for anything, however large its count -- which is why the count alone is never the score.
- ⚠ Recurrence is not causation and carries no direction: this ratio is identical in both directions. The direction of this edge comes only from the temporal gate.
- ⚠ Computed over the pinned dataset version, and over whatever slice of it this run read. A different slice is a different number.

**`rule_support` = 0.700000**

1 authored rule justification(s) in the active pack support this pair. Their declared strengths are combined so that independent rules corroborate rather than average: two rules reaching the same conclusion by different reasoning say more than either alone.

- rule justifications: `1`
- authored strength [evi:cdca355a3f8db6b4]: `0.700000`
- combined (noisy-OR): `0.700000`
- ⚠ A rule is a stated belief about the domain, not an observation of it. Strong rule support means the pack's authors expected this; it does not mean it happened.
- ⚠ Rules that a constraint suppressed, and conflicts the rule engine reported, are NOT subtracted here. They lower this edge through the contradiction_freedom component, so that weak support and contradicted support stay distinguishable.

**`statistical_support` = 0.144450**

Measure: lift over an instance-level 2x2 contingency table; no hypothesis test is performed. ITEM_PICKED and ITEM_PACKED co-occur, in that sequence, at 1.076 times the rate independence would predict, measured over 310 process instances of which 42 exhibit the pair. The score is that effect size on a declared scale, discounted for the size of the sample it was measured on.

- measure: `lift over an instance-level 2x2 contingency table; no hypothesis test is performed`
- sample size (process instances): `310`
- both: `42`
- cause only: `68`
- effect only: `68`
- neither: `132`
- effect size (lift): `1.076033`
- declared lift_reference: `3.000000`
- effect size on the declared scale: `0.066703`
- declared small_sample_prior_count: `20`
- sample-size discount: `0.677419`
- blend: `effect-weighted: discount^(1/3) * lift^(2/3)`
- p-value: `not computed; no null hypothesis is tested`
- ⚠ Lift measures co-occurrence against independence within one dataset version. It establishes NO causation, NO direction (lift is symmetric; this candidate's direction comes only from the LAW-TIME gate), NO freedom from confounding, and NO statistical significance -- no null is tested and no sampling distribution is assumed.
- ⚠ Confounding structures are present in this candidate graph and are REPORTED, not resolved. Nothing in V1 distinguishes a direct association from one explained by a third event, and the absence of a flag is not evidence of no confounding (CONTEXT.md R-05).

**`temporal_support` = 0.150000**

Both events were placed in time, but not precisely enough to say which came first. This scores the low value this rule pack declares for an unresolvable precedence, and CAPS the whole edge.

- temporal verdict: `UNDETERMINED`
- declared undetermined_temporal_support: `0.150000`
- ⚠ The events were placed; precedence was not resolved. That is more than an absent timestamp and much less than an established precedence.
- ⚠ A dominant UNDETERMINED share is a finding about the source's granularity (CONTEXT.md R-14). It is never resolved by loosening the test or by raising this number.
- ⚠ This edge can never be promoted to INFERRED (ADR-0007).

### 3. `evt:093b307df27c3628` → `evt:dfec96772c34336b`

- `causal_edge_id`: `edg:cb1cfe649384e09e`
- edge kind: `DIRECT`
- **confidence: 0.400000** via `gated_weighted_mean_v1`
- band: WEAK
- outcome: `SCORED` (7 of 8 components measured)
- provenance: `STATISTICAL` · temporal verdict: `UNDETERMINED` · temporally unverifiable: false
- weighted mean of the addends before gating: 0.603136; binding gate: temporal_support

> Weak -- inspect before acting. Either the support is thin, the ordering could not be established, or something on record argues against the claim. The breakdown beside this label says which; read it before using this edge for anything.

**`contradiction_freedom` = 0.769231**

This claim has counter-evidence against it, so its score is capped. Higher is better here: 1.0 means nothing argues against the claim, and this edge scores 0.769. What was found: reverse pair (the opposite direction was independently proposed).

- constraint prohibition: `no`
- rule conflicts touching this pair: `0`
- reverse pair also proposed: `yes`
- confounding flags on this edge: `0`
- total contradiction weight: `0.300000`
- half-at: `1.000000`
- ⚠ READ THE DIRECTION. This component is inverted relative to its name in the brief: it scores FREEDOM from contradiction, so a HIGH value means LITTLE counter-evidence. It is named this way so that every component rises with support and the aggregation stays monotone (ADR-0052).
- ⚠ A confounding flag is not counter-evidence. It marks a structure that could explain the association without this edge being real. Nothing at V1 resolves it, and the ABSENCE of a flag is not evidence of no confounding -- an unobserved common cause leaves no shape in a graph built from observed events (CONTEXT.md R-05).
- ⚠ Absence of contradiction is not support. A claim nothing argues against still needs evidence FOR it, which the other seven components supply.

**`evidence_count` = 0.727273**

8 distinct justification(s) support this pair. The scale is saturating: this pack is half convinced at 3, and each further justification adds less than the one before it.

- distinct evidence items: `8`
- generators reaching this pair: `5`
- declared saturation k: `3`
- ⚠ This counts justifications; it does not ask whether they are independent. Ten items of one kind score the same here as ten items of ten kinds. The evidence_diversity component is what separates them, and it is weighted higher than this one.
- ⚠ Evidence items are deduplicated by content address, so two generators minting a byte-identical justification contribute one item, not two.

**`evidence_diversity` = 1.000000**

Support for this pair comes from 5 distinct kind(s) of evidence, produced by 5 independent generator(s): HISTORICAL_FREQUENCY, RULE, SHARED_ENTITY, STATISTICAL_ASSOCIATION, TEMPORAL_PROXIMITY via historical_frequency, rule_based, shared_entity, statistical_association, temporal_proximity. Independent lines of reasoning reaching one conclusion count for more than one line repeated, which is why this is weighted above raw evidence count.

- distinct evidence kinds: `5`
- reachable kinds this run: `5`
- kind spread: `1.000000`
- distinct generators: `5`
- reachable generators this run: `5`
- generator spread: `1.000000`
- total evidence items: `8`
- ⚠ Independence here means different reasoning, not statistical independence. Two generators can rest on the same underlying coincidence in the data -- the shared-entity and shared-identifier generators are the obvious pair -- and nothing here detects that.
- ⚠ Normalized against what THIS run could reach, not against the full vocabulary. A run with generators that could not run has a smaller denominator, so diversity scores are not comparable across runs with different generator availability.

**`graph_connectivity` = 0.000000** *(MISSING)*

Not scored: graph_connectivity could not be computed for this edge, so it contributes nothing. This is an absence of measurement, not a measurement of absence -- the edge is scored lower for it, and the gap is reported rather than hidden.

- *needs*: at least one Relationship in the fact set. The relationship graph is module 7's output and module 8's projection, and neither exists yet (CONTEXT.md section 3) -- so this component is MISSING on every edge today rather than scored zero or silently omitted, and every edge is scored lower for it.

**`historical_support` = 0.570272**

Across 310 process instances, 110 contained ITEM_PACKED and 106 of those went on to contain SHIPMENT_DISPATCHED. That is a rate of 0.964 against a baseline rate of 0.723 for SHIPMENT_DISPATCHED overall -- a lift of 1.334. The score is that lift on a declared scale, then discounted because 106 instances is a sample of that size.

- process instances (denominator): `310`
- instances with cause type: `110`
- instances with effect type: `224`
- instances with the sequenced pair: `106`
- cause only: `4`
- effect only: `118`
- neither: `82`
- conditional rate: `0.963636`
- baseline rate: `0.722581`
- lift: `1.333604`
- declared lift_reference: `3.000000`
- lift on the declared scale: `0.262044`
- declared small_sample_prior_count: `20`
- small-sample discount: `0.841270`
- blend: `sample-weighted: discount^(2/3) * lift^(1/3)`
- module 9 recurrence items on this edge: `2`
- ⚠ A lift of 1.0 is independence and scores zero. A pattern that appears in every instance is not evidence for anything, however large its count -- which is why the count alone is never the score.
- ⚠ Recurrence is not causation and carries no direction: this ratio is identical in both directions. The direction of this edge comes only from the temporal gate.
- ⚠ Computed over the pinned dataset version, and over whatever slice of it this run read. A different slice is a different number.

**`rule_support` = 0.690000**

1 authored rule justification(s) in the active pack support this pair. Their declared strengths are combined so that independent rules corroborate rather than average: two rules reaching the same conclusion by different reasoning say more than either alone.

- rule justifications: `1`
- authored strength [evi:ff1212875a716c11]: `0.690000`
- combined (noisy-OR): `0.690000`
- ⚠ A rule is a stated belief about the domain, not an observation of it. Strong rule support means the pack's authors expected this; it does not mean it happened.
- ⚠ Rules that a constraint suppressed, and conflicts the rule engine reported, are NOT subtracted here. They lower this edge through the contradiction_freedom component, so that weak support and contradicted support stay distinguishable.

**`statistical_support` = 0.386570**

Measure: lift over an instance-level 2x2 contingency table; no hypothesis test is performed. ITEM_PACKED and SHIPMENT_DISPATCHED co-occur, in that sequence, at 1.334 times the rate independence would predict, measured over 310 process instances of which 106 exhibit the pair. The score is that effect size on a declared scale, discounted for the size of the sample it was measured on.

- measure: `lift over an instance-level 2x2 contingency table; no hypothesis test is performed`
- sample size (process instances): `310`
- both: `106`
- cause only: `4`
- effect only: `118`
- neither: `82`
- effect size (lift): `1.333604`
- declared lift_reference: `3.000000`
- effect size on the declared scale: `0.262044`
- declared small_sample_prior_count: `20`
- sample-size discount: `0.841270`
- blend: `effect-weighted: discount^(1/3) * lift^(2/3)`
- p-value: `not computed; no null hypothesis is tested`
- ⚠ Lift measures co-occurrence against independence within one dataset version. It establishes NO causation, NO direction (lift is symmetric; this candidate's direction comes only from the LAW-TIME gate), NO freedom from confounding, and NO statistical significance -- no null is tested and no sampling distribution is assumed.
- ⚠ Confounding structures are present in this candidate graph and are REPORTED, not resolved. Nothing in V1 distinguishes a direct association from one explained by a third event, and the absence of a flag is not evidence of no confounding (CONTEXT.md R-05).

**`temporal_support` = 0.150000**

Both events were placed in time, but not precisely enough to say which came first. This scores the low value this rule pack declares for an unresolvable precedence, and CAPS the whole edge.

- temporal verdict: `UNDETERMINED`
- declared undetermined_temporal_support: `0.150000`
- ⚠ The events were placed; precedence was not resolved. That is more than an absent timestamp and much less than an established precedence.
- ⚠ A dominant UNDETERMINED share is a finding about the source's granularity (CONTEXT.md R-14). It is never resolved by loosening the test or by raising this number.
- ⚠ This edge can never be promoted to INFERRED (ADR-0007).

### 4. `evt:0ac91b7e7f7a6f0b` → `evt:a09944ec38d250f1`

- `causal_edge_id`: `edg:01276d69adea9566`
- edge kind: `DIRECT`
- **confidence: 0.400000** via `gated_weighted_mean_v1`
- band: WEAK
- outcome: `SCORED` (7 of 8 components measured)
- provenance: `STATISTICAL` · temporal verdict: `UNDETERMINED` · temporally unverifiable: false
- weighted mean of the addends before gating: 0.603136; binding gate: temporal_support

> Weak -- inspect before acting. Either the support is thin, the ordering could not be established, or something on record argues against the claim. The breakdown beside this label says which; read it before using this edge for anything.

**`contradiction_freedom` = 0.434783**

This claim has counter-evidence against it, so its score is capped. Higher is better here: 1.0 means nothing argues against the claim, and this edge scores 0.435. What was found: reverse pair (the opposite direction was independently proposed); confounding flags (10).

- constraint prohibition: `no`
- rule conflicts touching this pair: `0`
- reverse pair also proposed: `yes`
- confounding flags on this edge: `10`
- total contradiction weight: `1.300000`
- half-at: `1.000000`
- ⚠ READ THE DIRECTION. This component is inverted relative to its name in the brief: it scores FREEDOM from contradiction, so a HIGH value means LITTLE counter-evidence. It is named this way so that every component rises with support and the aggregation stays monotone (ADR-0052).
- ⚠ A confounding flag is not counter-evidence. It marks a structure that could explain the association without this edge being real. Nothing at V1 resolves it, and the ABSENCE of a flag is not evidence of no confounding -- an unobserved common cause leaves no shape in a graph built from observed events (CONTEXT.md R-05).
- ⚠ Absence of contradiction is not support. A claim nothing argues against still needs evidence FOR it, which the other seven components supply.

**`evidence_count` = 0.727273**

8 distinct justification(s) support this pair. The scale is saturating: this pack is half convinced at 3, and each further justification adds less than the one before it.

- distinct evidence items: `8`
- generators reaching this pair: `5`
- declared saturation k: `3`
- ⚠ This counts justifications; it does not ask whether they are independent. Ten items of one kind score the same here as ten items of ten kinds. The evidence_diversity component is what separates them, and it is weighted higher than this one.
- ⚠ Evidence items are deduplicated by content address, so two generators minting a byte-identical justification contribute one item, not two.

**`evidence_diversity` = 1.000000**

Support for this pair comes from 5 distinct kind(s) of evidence, produced by 5 independent generator(s): HISTORICAL_FREQUENCY, RULE, SHARED_ENTITY, STATISTICAL_ASSOCIATION, TEMPORAL_PROXIMITY via historical_frequency, rule_based, shared_entity, statistical_association, temporal_proximity. Independent lines of reasoning reaching one conclusion count for more than one line repeated, which is why this is weighted above raw evidence count.

- distinct evidence kinds: `5`
- reachable kinds this run: `5`
- kind spread: `1.000000`
- distinct generators: `5`
- reachable generators this run: `5`
- generator spread: `1.000000`
- total evidence items: `8`
- ⚠ Independence here means different reasoning, not statistical independence. Two generators can rest on the same underlying coincidence in the data -- the shared-entity and shared-identifier generators are the obvious pair -- and nothing here detects that.
- ⚠ Normalized against what THIS run could reach, not against the full vocabulary. A run with generators that could not run has a smaller denominator, so diversity scores are not comparable across runs with different generator availability.

**`graph_connectivity` = 0.000000** *(MISSING)*

Not scored: graph_connectivity could not be computed for this edge, so it contributes nothing. This is an absence of measurement, not a measurement of absence -- the edge is scored lower for it, and the gap is reported rather than hidden.

- *needs*: at least one Relationship in the fact set. The relationship graph is module 7's output and module 8's projection, and neither exists yet (CONTEXT.md section 3) -- so this component is MISSING on every edge today rather than scored zero or silently omitted, and every edge is scored lower for it.

**`historical_support` = 0.570272**

Across 310 process instances, 110 contained ITEM_PACKED and 106 of those went on to contain SHIPMENT_DISPATCHED. That is a rate of 0.964 against a baseline rate of 0.723 for SHIPMENT_DISPATCHED overall -- a lift of 1.334. The score is that lift on a declared scale, then discounted because 106 instances is a sample of that size.

- process instances (denominator): `310`
- instances with cause type: `110`
- instances with effect type: `224`
- instances with the sequenced pair: `106`
- cause only: `4`
- effect only: `118`
- neither: `82`
- conditional rate: `0.963636`
- baseline rate: `0.722581`
- lift: `1.333604`
- declared lift_reference: `3.000000`
- lift on the declared scale: `0.262044`
- declared small_sample_prior_count: `20`
- small-sample discount: `0.841270`
- blend: `sample-weighted: discount^(2/3) * lift^(1/3)`
- module 9 recurrence items on this edge: `2`
- ⚠ A lift of 1.0 is independence and scores zero. A pattern that appears in every instance is not evidence for anything, however large its count -- which is why the count alone is never the score.
- ⚠ Recurrence is not causation and carries no direction: this ratio is identical in both directions. The direction of this edge comes only from the temporal gate.
- ⚠ Computed over the pinned dataset version, and over whatever slice of it this run read. A different slice is a different number.

**`rule_support` = 0.690000**

1 authored rule justification(s) in the active pack support this pair. Their declared strengths are combined so that independent rules corroborate rather than average: two rules reaching the same conclusion by different reasoning say more than either alone.

- rule justifications: `1`
- authored strength [evi:0234c670e54dbcc2]: `0.690000`
- combined (noisy-OR): `0.690000`
- ⚠ A rule is a stated belief about the domain, not an observation of it. Strong rule support means the pack's authors expected this; it does not mean it happened.
- ⚠ Rules that a constraint suppressed, and conflicts the rule engine reported, are NOT subtracted here. They lower this edge through the contradiction_freedom component, so that weak support and contradicted support stay distinguishable.

**`statistical_support` = 0.386570**

Measure: lift over an instance-level 2x2 contingency table; no hypothesis test is performed. ITEM_PACKED and SHIPMENT_DISPATCHED co-occur, in that sequence, at 1.334 times the rate independence would predict, measured over 310 process instances of which 106 exhibit the pair. The score is that effect size on a declared scale, discounted for the size of the sample it was measured on.

- measure: `lift over an instance-level 2x2 contingency table; no hypothesis test is performed`
- sample size (process instances): `310`
- both: `106`
- cause only: `4`
- effect only: `118`
- neither: `82`
- effect size (lift): `1.333604`
- declared lift_reference: `3.000000`
- effect size on the declared scale: `0.262044`
- declared small_sample_prior_count: `20`
- sample-size discount: `0.841270`
- blend: `effect-weighted: discount^(1/3) * lift^(2/3)`
- p-value: `not computed; no null hypothesis is tested`
- ⚠ Lift measures co-occurrence against independence within one dataset version. It establishes NO causation, NO direction (lift is symmetric; this candidate's direction comes only from the LAW-TIME gate), NO freedom from confounding, and NO statistical significance -- no null is tested and no sampling distribution is assumed.
- ⚠ Confounding structures are present in this candidate graph and are REPORTED, not resolved. Nothing in V1 distinguishes a direct association from one explained by a third event, and the absence of a flag is not evidence of no confounding (CONTEXT.md R-05).

**`temporal_support` = 0.150000**

Both events were placed in time, but not precisely enough to say which came first. This scores the low value this rule pack declares for an unresolvable precedence, and CAPS the whole edge.

- temporal verdict: `UNDETERMINED`
- declared undetermined_temporal_support: `0.150000`
- ⚠ The events were placed; precedence was not resolved. That is more than an absent timestamp and much less than an established precedence.
- ⚠ A dominant UNDETERMINED share is a finding about the source's granularity (CONTEXT.md R-14). It is never resolved by loosening the test or by raising this number.
- ⚠ This edge can never be promoted to INFERRED (ADR-0007).

### 5. `evt:0c97bbb43e40c038` → `evt:468f392847b3e6c9`

- `causal_edge_id`: `edg:195c576f313238af`
- edge kind: `DIRECT`
- **confidence: 0.400000** via `gated_weighted_mean_v1`
- band: WEAK
- outcome: `SCORED` (7 of 8 components measured)
- provenance: `STATISTICAL` · temporal verdict: `UNDETERMINED` · temporally unverifiable: false
- weighted mean of the addends before gating: 0.521008; binding gate: temporal_support

> Weak -- inspect before acting. Either the support is thin, the ordering could not be established, or something on record argues against the claim. The breakdown beside this label says which; read it before using this edge for anything.

**`contradiction_freedom` = 0.434783**

This claim has counter-evidence against it, so its score is capped. Higher is better here: 1.0 means nothing argues against the claim, and this edge scores 0.435. What was found: reverse pair (the opposite direction was independently proposed); confounding flags (10).

- constraint prohibition: `no`
- rule conflicts touching this pair: `0`
- reverse pair also proposed: `yes`
- confounding flags on this edge: `10`
- total contradiction weight: `1.300000`
- half-at: `1.000000`
- ⚠ READ THE DIRECTION. This component is inverted relative to its name in the brief: it scores FREEDOM from contradiction, so a HIGH value means LITTLE counter-evidence. It is named this way so that every component rises with support and the aggregation stays monotone (ADR-0052).
- ⚠ A confounding flag is not counter-evidence. It marks a structure that could explain the association without this edge being real. Nothing at V1 resolves it, and the ABSENCE of a flag is not evidence of no confounding -- an unobserved common cause leaves no shape in a graph built from observed events (CONTEXT.md R-05).
- ⚠ Absence of contradiction is not support. A claim nothing argues against still needs evidence FOR it, which the other seven components supply.

**`evidence_count` = 0.727273**

8 distinct justification(s) support this pair. The scale is saturating: this pack is half convinced at 3, and each further justification adds less than the one before it.

- distinct evidence items: `8`
- generators reaching this pair: `5`
- declared saturation k: `3`
- ⚠ This counts justifications; it does not ask whether they are independent. Ten items of one kind score the same here as ten items of ten kinds. The evidence_diversity component is what separates them, and it is weighted higher than this one.
- ⚠ Evidence items are deduplicated by content address, so two generators minting a byte-identical justification contribute one item, not two.

**`evidence_diversity` = 1.000000**

Support for this pair comes from 5 distinct kind(s) of evidence, produced by 5 independent generator(s): HISTORICAL_FREQUENCY, RULE, SHARED_ENTITY, STATISTICAL_ASSOCIATION, TEMPORAL_PROXIMITY via historical_frequency, rule_based, shared_entity, statistical_association, temporal_proximity. Independent lines of reasoning reaching one conclusion count for more than one line repeated, which is why this is weighted above raw evidence count.

- distinct evidence kinds: `5`
- reachable kinds this run: `5`
- kind spread: `1.000000`
- distinct generators: `5`
- reachable generators this run: `5`
- generator spread: `1.000000`
- total evidence items: `8`
- ⚠ Independence here means different reasoning, not statistical independence. Two generators can rest on the same underlying coincidence in the data -- the shared-entity and shared-identifier generators are the obvious pair -- and nothing here detects that.
- ⚠ Normalized against what THIS run could reach, not against the full vocabulary. A run with generators that could not run has a smaller denominator, so diversity scores are not comparable across runs with different generator availability.

**`graph_connectivity` = 0.000000** *(MISSING)*

Not scored: graph_connectivity could not be computed for this edge, so it contributes nothing. This is an absence of measurement, not a measurement of absence -- the edge is scored lower for it, and the gap is reported rather than hidden.

- *needs*: at least one Relationship in the fact set. The relationship graph is module 7's output and module 8's projection, and neither exists yet (CONTEXT.md section 3) -- so this component is MISSING on every edge today rather than scored zero or silently omitted, and every edge is scored lower for it.

**`historical_support` = 0.312815**

Across 310 process instances, 110 contained ITEM_PICKED and 42 of those went on to contain ITEM_PACKED. That is a rate of 0.382 against a baseline rate of 0.355 for ITEM_PACKED overall -- a lift of 1.076. The score is that lift on a declared scale, then discounted because 42 instances is a sample of that size.

- process instances (denominator): `310`
- instances with cause type: `110`
- instances with effect type: `110`
- instances with the sequenced pair: `42`
- cause only: `68`
- effect only: `68`
- neither: `132`
- conditional rate: `0.381818`
- baseline rate: `0.354839`
- lift: `1.076033`
- declared lift_reference: `3.000000`
- lift on the declared scale: `0.066703`
- declared small_sample_prior_count: `20`
- small-sample discount: `0.677419`
- blend: `sample-weighted: discount^(2/3) * lift^(1/3)`
- module 9 recurrence items on this edge: `2`
- ⚠ A lift of 1.0 is independence and scores zero. A pattern that appears in every instance is not evidence for anything, however large its count -- which is why the count alone is never the score.
- ⚠ Recurrence is not causation and carries no direction: this ratio is identical in both directions. The direction of this edge comes only from the temporal gate.
- ⚠ Computed over the pinned dataset version, and over whatever slice of it this run read. A different slice is a different number.

**`rule_support` = 0.700000**

1 authored rule justification(s) in the active pack support this pair. Their declared strengths are combined so that independent rules corroborate rather than average: two rules reaching the same conclusion by different reasoning say more than either alone.

- rule justifications: `1`
- authored strength [evi:5a9125ebf6bc0700]: `0.700000`
- combined (noisy-OR): `0.700000`
- ⚠ A rule is a stated belief about the domain, not an observation of it. Strong rule support means the pack's authors expected this; it does not mean it happened.
- ⚠ Rules that a constraint suppressed, and conflicts the rule engine reported, are NOT subtracted here. They lower this edge through the contradiction_freedom component, so that weak support and contradicted support stay distinguishable.

**`statistical_support` = 0.144450**

Measure: lift over an instance-level 2x2 contingency table; no hypothesis test is performed. ITEM_PICKED and ITEM_PACKED co-occur, in that sequence, at 1.076 times the rate independence would predict, measured over 310 process instances of which 42 exhibit the pair. The score is that effect size on a declared scale, discounted for the size of the sample it was measured on.

- measure: `lift over an instance-level 2x2 contingency table; no hypothesis test is performed`
- sample size (process instances): `310`
- both: `42`
- cause only: `68`
- effect only: `68`
- neither: `132`
- effect size (lift): `1.076033`
- declared lift_reference: `3.000000`
- effect size on the declared scale: `0.066703`
- declared small_sample_prior_count: `20`
- sample-size discount: `0.677419`
- blend: `effect-weighted: discount^(1/3) * lift^(2/3)`
- p-value: `not computed; no null hypothesis is tested`
- ⚠ Lift measures co-occurrence against independence within one dataset version. It establishes NO causation, NO direction (lift is symmetric; this candidate's direction comes only from the LAW-TIME gate), NO freedom from confounding, and NO statistical significance -- no null is tested and no sampling distribution is assumed.
- ⚠ Confounding structures are present in this candidate graph and are REPORTED, not resolved. Nothing in V1 distinguishes a direct association from one explained by a third event, and the absence of a flag is not evidence of no confounding (CONTEXT.md R-05).

**`temporal_support` = 0.150000**

Both events were placed in time, but not precisely enough to say which came first. This scores the low value this rule pack declares for an unresolvable precedence, and CAPS the whole edge.

- temporal verdict: `UNDETERMINED`
- declared undetermined_temporal_support: `0.150000`
- ⚠ The events were placed; precedence was not resolved. That is more than an absent timestamp and much less than an established precedence.
- ⚠ A dominant UNDETERMINED share is a finding about the source's granularity (CONTEXT.md R-14). It is never resolved by loosening the test or by raising this number.
- ⚠ This edge can never be promoted to INFERRED (ADR-0007).

### 6. `evt:0f5cf881318dcdae` → `evt:2ac908421695bd68`

- `causal_edge_id`: `edg:8ad384c276df5e29`
- edge kind: `DIRECT`
- **confidence: 0.400000** via `gated_weighted_mean_v1`
- band: WEAK
- outcome: `SCORED` (7 of 8 components measured)
- provenance: `STATISTICAL` · temporal verdict: `UNDETERMINED` · temporally unverifiable: false
- weighted mean of the addends before gating: 0.603136; binding gate: temporal_support

> Weak -- inspect before acting. Either the support is thin, the ordering could not be established, or something on record argues against the claim. The breakdown beside this label says which; read it before using this edge for anything.

**`contradiction_freedom` = 0.434783**

This claim has counter-evidence against it, so its score is capped. Higher is better here: 1.0 means nothing argues against the claim, and this edge scores 0.435. What was found: reverse pair (the opposite direction was independently proposed); confounding flags (10).

- constraint prohibition: `no`
- rule conflicts touching this pair: `0`
- reverse pair also proposed: `yes`
- confounding flags on this edge: `10`
- total contradiction weight: `1.300000`
- half-at: `1.000000`
- ⚠ READ THE DIRECTION. This component is inverted relative to its name in the brief: it scores FREEDOM from contradiction, so a HIGH value means LITTLE counter-evidence. It is named this way so that every component rises with support and the aggregation stays monotone (ADR-0052).
- ⚠ A confounding flag is not counter-evidence. It marks a structure that could explain the association without this edge being real. Nothing at V1 resolves it, and the ABSENCE of a flag is not evidence of no confounding -- an unobserved common cause leaves no shape in a graph built from observed events (CONTEXT.md R-05).
- ⚠ Absence of contradiction is not support. A claim nothing argues against still needs evidence FOR it, which the other seven components supply.

**`evidence_count` = 0.727273**

8 distinct justification(s) support this pair. The scale is saturating: this pack is half convinced at 3, and each further justification adds less than the one before it.

- distinct evidence items: `8`
- generators reaching this pair: `5`
- declared saturation k: `3`
- ⚠ This counts justifications; it does not ask whether they are independent. Ten items of one kind score the same here as ten items of ten kinds. The evidence_diversity component is what separates them, and it is weighted higher than this one.
- ⚠ Evidence items are deduplicated by content address, so two generators minting a byte-identical justification contribute one item, not two.

**`evidence_diversity` = 1.000000**

Support for this pair comes from 5 distinct kind(s) of evidence, produced by 5 independent generator(s): HISTORICAL_FREQUENCY, RULE, SHARED_ENTITY, STATISTICAL_ASSOCIATION, TEMPORAL_PROXIMITY via historical_frequency, rule_based, shared_entity, statistical_association, temporal_proximity. Independent lines of reasoning reaching one conclusion count for more than one line repeated, which is why this is weighted above raw evidence count.

- distinct evidence kinds: `5`
- reachable kinds this run: `5`
- kind spread: `1.000000`
- distinct generators: `5`
- reachable generators this run: `5`
- generator spread: `1.000000`
- total evidence items: `8`
- ⚠ Independence here means different reasoning, not statistical independence. Two generators can rest on the same underlying coincidence in the data -- the shared-entity and shared-identifier generators are the obvious pair -- and nothing here detects that.
- ⚠ Normalized against what THIS run could reach, not against the full vocabulary. A run with generators that could not run has a smaller denominator, so diversity scores are not comparable across runs with different generator availability.

**`graph_connectivity` = 0.000000** *(MISSING)*

Not scored: graph_connectivity could not be computed for this edge, so it contributes nothing. This is an absence of measurement, not a measurement of absence -- the edge is scored lower for it, and the gap is reported rather than hidden.

- *needs*: at least one Relationship in the fact set. The relationship graph is module 7's output and module 8's projection, and neither exists yet (CONTEXT.md section 3) -- so this component is MISSING on every edge today rather than scored zero or silently omitted, and every edge is scored lower for it.

**`historical_support` = 0.570272**

Across 310 process instances, 110 contained ITEM_PACKED and 106 of those went on to contain SHIPMENT_DISPATCHED. That is a rate of 0.964 against a baseline rate of 0.723 for SHIPMENT_DISPATCHED overall -- a lift of 1.334. The score is that lift on a declared scale, then discounted because 106 instances is a sample of that size.

- process instances (denominator): `310`
- instances with cause type: `110`
- instances with effect type: `224`
- instances with the sequenced pair: `106`
- cause only: `4`
- effect only: `118`
- neither: `82`
- conditional rate: `0.963636`
- baseline rate: `0.722581`
- lift: `1.333604`
- declared lift_reference: `3.000000`
- lift on the declared scale: `0.262044`
- declared small_sample_prior_count: `20`
- small-sample discount: `0.841270`
- blend: `sample-weighted: discount^(2/3) * lift^(1/3)`
- module 9 recurrence items on this edge: `2`
- ⚠ A lift of 1.0 is independence and scores zero. A pattern that appears in every instance is not evidence for anything, however large its count -- which is why the count alone is never the score.
- ⚠ Recurrence is not causation and carries no direction: this ratio is identical in both directions. The direction of this edge comes only from the temporal gate.
- ⚠ Computed over the pinned dataset version, and over whatever slice of it this run read. A different slice is a different number.

**`rule_support` = 0.690000**

1 authored rule justification(s) in the active pack support this pair. Their declared strengths are combined so that independent rules corroborate rather than average: two rules reaching the same conclusion by different reasoning say more than either alone.

- rule justifications: `1`
- authored strength [evi:2b38b66838ae9128]: `0.690000`
- combined (noisy-OR): `0.690000`
- ⚠ A rule is a stated belief about the domain, not an observation of it. Strong rule support means the pack's authors expected this; it does not mean it happened.
- ⚠ Rules that a constraint suppressed, and conflicts the rule engine reported, are NOT subtracted here. They lower this edge through the contradiction_freedom component, so that weak support and contradicted support stay distinguishable.

**`statistical_support` = 0.386570**

Measure: lift over an instance-level 2x2 contingency table; no hypothesis test is performed. ITEM_PACKED and SHIPMENT_DISPATCHED co-occur, in that sequence, at 1.334 times the rate independence would predict, measured over 310 process instances of which 106 exhibit the pair. The score is that effect size on a declared scale, discounted for the size of the sample it was measured on.

- measure: `lift over an instance-level 2x2 contingency table; no hypothesis test is performed`
- sample size (process instances): `310`
- both: `106`
- cause only: `4`
- effect only: `118`
- neither: `82`
- effect size (lift): `1.333604`
- declared lift_reference: `3.000000`
- effect size on the declared scale: `0.262044`
- declared small_sample_prior_count: `20`
- sample-size discount: `0.841270`
- blend: `effect-weighted: discount^(1/3) * lift^(2/3)`
- p-value: `not computed; no null hypothesis is tested`
- ⚠ Lift measures co-occurrence against independence within one dataset version. It establishes NO causation, NO direction (lift is symmetric; this candidate's direction comes only from the LAW-TIME gate), NO freedom from confounding, and NO statistical significance -- no null is tested and no sampling distribution is assumed.
- ⚠ Confounding structures are present in this candidate graph and are REPORTED, not resolved. Nothing in V1 distinguishes a direct association from one explained by a third event, and the absence of a flag is not evidence of no confounding (CONTEXT.md R-05).

**`temporal_support` = 0.150000**

Both events were placed in time, but not precisely enough to say which came first. This scores the low value this rule pack declares for an unresolvable precedence, and CAPS the whole edge.

- temporal verdict: `UNDETERMINED`
- declared undetermined_temporal_support: `0.150000`
- ⚠ The events were placed; precedence was not resolved. That is more than an absent timestamp and much less than an established precedence.
- ⚠ A dominant UNDETERMINED share is a finding about the source's granularity (CONTEXT.md R-14). It is never resolved by loosening the test or by raising this number.
- ⚠ This edge can never be promoted to INFERRED (ADR-0007).

### 7. `evt:0fb82f123f075782` → `evt:0f5cf881318dcdae`

- `causal_edge_id`: `edg:48c8b740671bdf53`
- edge kind: `DIRECT`
- **confidence: 0.400000** via `gated_weighted_mean_v1`
- band: WEAK
- outcome: `SCORED` (7 of 8 components measured)
- provenance: `ASSUMED` · temporal verdict: `UNDETERMINED` · temporally unverifiable: false
- weighted mean of the addends before gating: 0.422307; binding gate: temporal_support

> Weak -- inspect before acting. Either the support is thin, the ordering could not be established, or something on record argues against the claim. The breakdown beside this label says which; read it before using this edge for anything.

**`contradiction_freedom` = 0.526316**

This claim has counter-evidence against it, so its score is capped. Higher is better here: 1.0 means nothing argues against the claim, and this edge scores 0.526. What was found: reverse pair (the opposite direction was independently proposed); confounding flags (6).

- constraint prohibition: `no`
- rule conflicts touching this pair: `0`
- reverse pair also proposed: `yes`
- confounding flags on this edge: `6`
- total contradiction weight: `0.900000`
- half-at: `1.000000`
- ⚠ READ THE DIRECTION. This component is inverted relative to its name in the brief: it scores FREEDOM from contradiction, so a HIGH value means LITTLE counter-evidence. It is named this way so that every component rises with support and the aggregation stays monotone (ADR-0052).
- ⚠ A confounding flag is not counter-evidence. It marks a structure that could explain the association without this edge being real. Nothing at V1 resolves it, and the ABSENCE of a flag is not evidence of no confounding -- an unobserved common cause leaves no shape in a graph built from observed events (CONTEXT.md R-05).
- ⚠ Absence of contradiction is not support. A claim nothing argues against still needs evidence FOR it, which the other seven components supply.

**`evidence_count` = 0.571429**

4 distinct justification(s) support this pair. The scale is saturating: this pack is half convinced at 3, and each further justification adds less than the one before it.

- distinct evidence items: `4`
- generators reaching this pair: `3`
- declared saturation k: `3`
- ⚠ This counts justifications; it does not ask whether they are independent. Ten items of one kind score the same here as ten items of ten kinds. The evidence_diversity component is what separates them, and it is weighted higher than this one.
- ⚠ Evidence items are deduplicated by content address, so two generators minting a byte-identical justification contribute one item, not two.

**`evidence_diversity` = 0.500000**

Support for this pair comes from 3 distinct kind(s) of evidence, produced by 3 independent generator(s): RULE, SHARED_ENTITY, TEMPORAL_PROXIMITY via rule_based, shared_entity, temporal_proximity. Independent lines of reasoning reaching one conclusion count for more than one line repeated, which is why this is weighted above raw evidence count.

- distinct evidence kinds: `3`
- reachable kinds this run: `5`
- kind spread: `0.500000`
- distinct generators: `3`
- reachable generators this run: `5`
- generator spread: `0.500000`
- total evidence items: `4`
- ⚠ Independence here means different reasoning, not statistical independence. Two generators can rest on the same underlying coincidence in the data -- the shared-entity and shared-identifier generators are the obvious pair -- and nothing here detects that.
- ⚠ Normalized against what THIS run could reach, not against the full vocabulary. A run with generators that could not run has a smaller denominator, so diversity scores are not comparable across runs with different generator availability.

**`graph_connectivity` = 0.000000** *(MISSING)*

Not scored: graph_connectivity could not be computed for this edge, so it contributes nothing. This is an absence of measurement, not a measurement of absence -- the edge is scored lower for it, and the gap is reported rather than hidden.

- *needs*: at least one Relationship in the fact set. The relationship graph is module 7's output and module 8's projection, and neither exists yet (CONTEXT.md section 3) -- so this component is MISSING on every edge today rather than scored zero or silently omitted, and every edge is scored lower for it.

**`historical_support` = 0.312815**

Across 310 process instances, 110 contained ITEM_PICKED and 42 of those went on to contain ITEM_PACKED. That is a rate of 0.382 against a baseline rate of 0.355 for ITEM_PACKED overall -- a lift of 1.076. The score is that lift on a declared scale, then discounted because 42 instances is a sample of that size.

- process instances (denominator): `310`
- instances with cause type: `110`
- instances with effect type: `110`
- instances with the sequenced pair: `42`
- cause only: `68`
- effect only: `68`
- neither: `132`
- conditional rate: `0.381818`
- baseline rate: `0.354839`
- lift: `1.076033`
- declared lift_reference: `3.000000`
- lift on the declared scale: `0.066703`
- declared small_sample_prior_count: `20`
- small-sample discount: `0.677419`
- blend: `sample-weighted: discount^(2/3) * lift^(1/3)`
- module 9 recurrence items on this edge: `0`
- ⚠ A lift of 1.0 is independence and scores zero. A pattern that appears in every instance is not evidence for anything, however large its count -- which is why the count alone is never the score.
- ⚠ Recurrence is not causation and carries no direction: this ratio is identical in both directions. The direction of this edge comes only from the temporal gate.
- ⚠ Computed over the pinned dataset version, and over whatever slice of it this run read. A different slice is a different number.

**`rule_support` = 0.700000**

1 authored rule justification(s) in the active pack support this pair. Their declared strengths are combined so that independent rules corroborate rather than average: two rules reaching the same conclusion by different reasoning say more than either alone.

- rule justifications: `1`
- authored strength [evi:0f0c6ef86447dcad]: `0.700000`
- combined (noisy-OR): `0.700000`
- ⚠ A rule is a stated belief about the domain, not an observation of it. Strong rule support means the pack's authors expected this; it does not mean it happened.
- ⚠ Rules that a constraint suppressed, and conflicts the rule engine reported, are NOT subtracted here. They lower this edge through the contradiction_freedom component, so that weak support and contradicted support stay distinguishable.

**`statistical_support` = 0.144450**

Measure: lift over an instance-level 2x2 contingency table; no hypothesis test is performed. ITEM_PICKED and ITEM_PACKED co-occur, in that sequence, at 1.076 times the rate independence would predict, measured over 310 process instances of which 42 exhibit the pair. The score is that effect size on a declared scale, discounted for the size of the sample it was measured on.

- measure: `lift over an instance-level 2x2 contingency table; no hypothesis test is performed`
- sample size (process instances): `310`
- both: `42`
- cause only: `68`
- effect only: `68`
- neither: `132`
- effect size (lift): `1.076033`
- declared lift_reference: `3.000000`
- effect size on the declared scale: `0.066703`
- declared small_sample_prior_count: `20`
- sample-size discount: `0.677419`
- blend: `effect-weighted: discount^(1/3) * lift^(2/3)`
- p-value: `not computed; no null hypothesis is tested`
- ⚠ Lift measures co-occurrence against independence within one dataset version. It establishes NO causation, NO direction (lift is symmetric; this candidate's direction comes only from the LAW-TIME gate), NO freedom from confounding, and NO statistical significance -- no null is tested and no sampling distribution is assumed.
- ⚠ Confounding structures are present in this candidate graph and are REPORTED, not resolved. Nothing in V1 distinguishes a direct association from one explained by a third event, and the absence of a flag is not evidence of no confounding (CONTEXT.md R-05).

**`temporal_support` = 0.150000**

Both events were placed in time, but not precisely enough to say which came first. This scores the low value this rule pack declares for an unresolvable precedence, and CAPS the whole edge.

- temporal verdict: `UNDETERMINED`
- declared undetermined_temporal_support: `0.150000`
- ⚠ The events were placed; precedence was not resolved. That is more than an absent timestamp and much less than an established precedence.
- ⚠ A dominant UNDETERMINED share is a finding about the source's granularity (CONTEXT.md R-14). It is never resolved by loosening the test or by raising this number.
- ⚠ This edge can never be promoted to INFERRED (ADR-0007).

### 8. `evt:12283598c28a1bf7` → `evt:3ad74bb885018ae5`

- `causal_edge_id`: `edg:d8b3acaf065a16c6`
- edge kind: `DIRECT`
- **confidence: 0.400000** via `gated_weighted_mean_v1`
- band: WEAK
- outcome: `SCORED` (7 of 8 components measured)
- provenance: `STATISTICAL` · temporal verdict: `UNDETERMINED` · temporally unverifiable: false
- weighted mean of the addends before gating: 0.521008; binding gate: temporal_support

> Weak -- inspect before acting. Either the support is thin, the ordering could not be established, or something on record argues against the claim. The breakdown beside this label says which; read it before using this edge for anything.

**`contradiction_freedom` = 0.303030**

This claim has counter-evidence against it, so its score is capped. Higher is better here: 1.0 means nothing argues against the claim, and this edge scores 0.303. What was found: reverse pair (the opposite direction was independently proposed); confounding flags (20).

- constraint prohibition: `no`
- rule conflicts touching this pair: `0`
- reverse pair also proposed: `yes`
- confounding flags on this edge: `20`
- total contradiction weight: `2.300000`
- half-at: `1.000000`
- ⚠ READ THE DIRECTION. This component is inverted relative to its name in the brief: it scores FREEDOM from contradiction, so a HIGH value means LITTLE counter-evidence. It is named this way so that every component rises with support and the aggregation stays monotone (ADR-0052).
- ⚠ A confounding flag is not counter-evidence. It marks a structure that could explain the association without this edge being real. Nothing at V1 resolves it, and the ABSENCE of a flag is not evidence of no confounding -- an unobserved common cause leaves no shape in a graph built from observed events (CONTEXT.md R-05).
- ⚠ Absence of contradiction is not support. A claim nothing argues against still needs evidence FOR it, which the other seven components supply.

**`evidence_count` = 0.727273**

8 distinct justification(s) support this pair. The scale is saturating: this pack is half convinced at 3, and each further justification adds less than the one before it.

- distinct evidence items: `8`
- generators reaching this pair: `5`
- declared saturation k: `3`
- ⚠ This counts justifications; it does not ask whether they are independent. Ten items of one kind score the same here as ten items of ten kinds. The evidence_diversity component is what separates them, and it is weighted higher than this one.
- ⚠ Evidence items are deduplicated by content address, so two generators minting a byte-identical justification contribute one item, not two.

**`evidence_diversity` = 1.000000**

Support for this pair comes from 5 distinct kind(s) of evidence, produced by 5 independent generator(s): HISTORICAL_FREQUENCY, RULE, SHARED_ENTITY, STATISTICAL_ASSOCIATION, TEMPORAL_PROXIMITY via historical_frequency, rule_based, shared_entity, statistical_association, temporal_proximity. Independent lines of reasoning reaching one conclusion count for more than one line repeated, which is why this is weighted above raw evidence count.

- distinct evidence kinds: `5`
- reachable kinds this run: `5`
- kind spread: `1.000000`
- distinct generators: `5`
- reachable generators this run: `5`
- generator spread: `1.000000`
- total evidence items: `8`
- ⚠ Independence here means different reasoning, not statistical independence. Two generators can rest on the same underlying coincidence in the data -- the shared-entity and shared-identifier generators are the obvious pair -- and nothing here detects that.
- ⚠ Normalized against what THIS run could reach, not against the full vocabulary. A run with generators that could not run has a smaller denominator, so diversity scores are not comparable across runs with different generator availability.

**`graph_connectivity` = 0.000000** *(MISSING)*

Not scored: graph_connectivity could not be computed for this edge, so it contributes nothing. This is an absence of measurement, not a measurement of absence -- the edge is scored lower for it, and the gap is reported rather than hidden.

- *needs*: at least one Relationship in the fact set. The relationship graph is module 7's output and module 8's projection, and neither exists yet (CONTEXT.md section 3) -- so this component is MISSING on every edge today rather than scored zero or silently omitted, and every edge is scored lower for it.

**`historical_support` = 0.312815**

Across 310 process instances, 110 contained ITEM_PICKED and 42 of those went on to contain ITEM_PACKED. That is a rate of 0.382 against a baseline rate of 0.355 for ITEM_PACKED overall -- a lift of 1.076. The score is that lift on a declared scale, then discounted because 42 instances is a sample of that size.

- process instances (denominator): `310`
- instances with cause type: `110`
- instances with effect type: `110`
- instances with the sequenced pair: `42`
- cause only: `68`
- effect only: `68`
- neither: `132`
- conditional rate: `0.381818`
- baseline rate: `0.354839`
- lift: `1.076033`
- declared lift_reference: `3.000000`
- lift on the declared scale: `0.066703`
- declared small_sample_prior_count: `20`
- small-sample discount: `0.677419`
- blend: `sample-weighted: discount^(2/3) * lift^(1/3)`
- module 9 recurrence items on this edge: `2`
- ⚠ A lift of 1.0 is independence and scores zero. A pattern that appears in every instance is not evidence for anything, however large its count -- which is why the count alone is never the score.
- ⚠ Recurrence is not causation and carries no direction: this ratio is identical in both directions. The direction of this edge comes only from the temporal gate.
- ⚠ Computed over the pinned dataset version, and over whatever slice of it this run read. A different slice is a different number.

**`rule_support` = 0.700000**

1 authored rule justification(s) in the active pack support this pair. Their declared strengths are combined so that independent rules corroborate rather than average: two rules reaching the same conclusion by different reasoning say more than either alone.

- rule justifications: `1`
- authored strength [evi:f1e40ef15cc32359]: `0.700000`
- combined (noisy-OR): `0.700000`
- ⚠ A rule is a stated belief about the domain, not an observation of it. Strong rule support means the pack's authors expected this; it does not mean it happened.
- ⚠ Rules that a constraint suppressed, and conflicts the rule engine reported, are NOT subtracted here. They lower this edge through the contradiction_freedom component, so that weak support and contradicted support stay distinguishable.

**`statistical_support` = 0.144450**

Measure: lift over an instance-level 2x2 contingency table; no hypothesis test is performed. ITEM_PICKED and ITEM_PACKED co-occur, in that sequence, at 1.076 times the rate independence would predict, measured over 310 process instances of which 42 exhibit the pair. The score is that effect size on a declared scale, discounted for the size of the sample it was measured on.

- measure: `lift over an instance-level 2x2 contingency table; no hypothesis test is performed`
- sample size (process instances): `310`
- both: `42`
- cause only: `68`
- effect only: `68`
- neither: `132`
- effect size (lift): `1.076033`
- declared lift_reference: `3.000000`
- effect size on the declared scale: `0.066703`
- declared small_sample_prior_count: `20`
- sample-size discount: `0.677419`
- blend: `effect-weighted: discount^(1/3) * lift^(2/3)`
- p-value: `not computed; no null hypothesis is tested`
- ⚠ Lift measures co-occurrence against independence within one dataset version. It establishes NO causation, NO direction (lift is symmetric; this candidate's direction comes only from the LAW-TIME gate), NO freedom from confounding, and NO statistical significance -- no null is tested and no sampling distribution is assumed.
- ⚠ Confounding structures are present in this candidate graph and are REPORTED, not resolved. Nothing in V1 distinguishes a direct association from one explained by a third event, and the absence of a flag is not evidence of no confounding (CONTEXT.md R-05).

**`temporal_support` = 0.150000**

Both events were placed in time, but not precisely enough to say which came first. This scores the low value this rule pack declares for an unresolvable precedence, and CAPS the whole edge.

- temporal verdict: `UNDETERMINED`
- declared undetermined_temporal_support: `0.150000`
- ⚠ The events were placed; precedence was not resolved. That is more than an absent timestamp and much less than an established precedence.
- ⚠ A dominant UNDETERMINED share is a finding about the source's granularity (CONTEXT.md R-14). It is never resolved by loosening the test or by raising this number.
- ⚠ This edge can never be promoted to INFERRED (ADR-0007).

### 9. `evt:152904c36530d8bf` → `evt:da1979c82d057cf9`

- `causal_edge_id`: `edg:9e0e1d4de1512f7f`
- edge kind: `DIRECT`
- **confidence: 0.400000** via `gated_weighted_mean_v1`
- band: WEAK
- outcome: `SCORED` (7 of 8 components measured)
- provenance: `STATISTICAL` · temporal verdict: `UNDETERMINED` · temporally unverifiable: false
- weighted mean of the addends before gating: 0.521008; binding gate: temporal_support

> Weak -- inspect before acting. Either the support is thin, the ordering could not be established, or something on record argues against the claim. The breakdown beside this label says which; read it before using this edge for anything.

**`contradiction_freedom` = 0.434783**

This claim has counter-evidence against it, so its score is capped. Higher is better here: 1.0 means nothing argues against the claim, and this edge scores 0.435. What was found: reverse pair (the opposite direction was independently proposed); confounding flags (10).

- constraint prohibition: `no`
- rule conflicts touching this pair: `0`
- reverse pair also proposed: `yes`
- confounding flags on this edge: `10`
- total contradiction weight: `1.300000`
- half-at: `1.000000`
- ⚠ READ THE DIRECTION. This component is inverted relative to its name in the brief: it scores FREEDOM from contradiction, so a HIGH value means LITTLE counter-evidence. It is named this way so that every component rises with support and the aggregation stays monotone (ADR-0052).
- ⚠ A confounding flag is not counter-evidence. It marks a structure that could explain the association without this edge being real. Nothing at V1 resolves it, and the ABSENCE of a flag is not evidence of no confounding -- an unobserved common cause leaves no shape in a graph built from observed events (CONTEXT.md R-05).
- ⚠ Absence of contradiction is not support. A claim nothing argues against still needs evidence FOR it, which the other seven components supply.

**`evidence_count` = 0.727273**

8 distinct justification(s) support this pair. The scale is saturating: this pack is half convinced at 3, and each further justification adds less than the one before it.

- distinct evidence items: `8`
- generators reaching this pair: `5`
- declared saturation k: `3`
- ⚠ This counts justifications; it does not ask whether they are independent. Ten items of one kind score the same here as ten items of ten kinds. The evidence_diversity component is what separates them, and it is weighted higher than this one.
- ⚠ Evidence items are deduplicated by content address, so two generators minting a byte-identical justification contribute one item, not two.

**`evidence_diversity` = 1.000000**

Support for this pair comes from 5 distinct kind(s) of evidence, produced by 5 independent generator(s): HISTORICAL_FREQUENCY, RULE, SHARED_ENTITY, STATISTICAL_ASSOCIATION, TEMPORAL_PROXIMITY via historical_frequency, rule_based, shared_entity, statistical_association, temporal_proximity. Independent lines of reasoning reaching one conclusion count for more than one line repeated, which is why this is weighted above raw evidence count.

- distinct evidence kinds: `5`
- reachable kinds this run: `5`
- kind spread: `1.000000`
- distinct generators: `5`
- reachable generators this run: `5`
- generator spread: `1.000000`
- total evidence items: `8`
- ⚠ Independence here means different reasoning, not statistical independence. Two generators can rest on the same underlying coincidence in the data -- the shared-entity and shared-identifier generators are the obvious pair -- and nothing here detects that.
- ⚠ Normalized against what THIS run could reach, not against the full vocabulary. A run with generators that could not run has a smaller denominator, so diversity scores are not comparable across runs with different generator availability.

**`graph_connectivity` = 0.000000** *(MISSING)*

Not scored: graph_connectivity could not be computed for this edge, so it contributes nothing. This is an absence of measurement, not a measurement of absence -- the edge is scored lower for it, and the gap is reported rather than hidden.

- *needs*: at least one Relationship in the fact set. The relationship graph is module 7's output and module 8's projection, and neither exists yet (CONTEXT.md section 3) -- so this component is MISSING on every edge today rather than scored zero or silently omitted, and every edge is scored lower for it.

**`historical_support` = 0.312815**

Across 310 process instances, 110 contained ITEM_PICKED and 42 of those went on to contain ITEM_PACKED. That is a rate of 0.382 against a baseline rate of 0.355 for ITEM_PACKED overall -- a lift of 1.076. The score is that lift on a declared scale, then discounted because 42 instances is a sample of that size.

- process instances (denominator): `310`
- instances with cause type: `110`
- instances with effect type: `110`
- instances with the sequenced pair: `42`
- cause only: `68`
- effect only: `68`
- neither: `132`
- conditional rate: `0.381818`
- baseline rate: `0.354839`
- lift: `1.076033`
- declared lift_reference: `3.000000`
- lift on the declared scale: `0.066703`
- declared small_sample_prior_count: `20`
- small-sample discount: `0.677419`
- blend: `sample-weighted: discount^(2/3) * lift^(1/3)`
- module 9 recurrence items on this edge: `2`
- ⚠ A lift of 1.0 is independence and scores zero. A pattern that appears in every instance is not evidence for anything, however large its count -- which is why the count alone is never the score.
- ⚠ Recurrence is not causation and carries no direction: this ratio is identical in both directions. The direction of this edge comes only from the temporal gate.
- ⚠ Computed over the pinned dataset version, and over whatever slice of it this run read. A different slice is a different number.

**`rule_support` = 0.700000**

1 authored rule justification(s) in the active pack support this pair. Their declared strengths are combined so that independent rules corroborate rather than average: two rules reaching the same conclusion by different reasoning say more than either alone.

- rule justifications: `1`
- authored strength [evi:ff6a74b8dda351a3]: `0.700000`
- combined (noisy-OR): `0.700000`
- ⚠ A rule is a stated belief about the domain, not an observation of it. Strong rule support means the pack's authors expected this; it does not mean it happened.
- ⚠ Rules that a constraint suppressed, and conflicts the rule engine reported, are NOT subtracted here. They lower this edge through the contradiction_freedom component, so that weak support and contradicted support stay distinguishable.

**`statistical_support` = 0.144450**

Measure: lift over an instance-level 2x2 contingency table; no hypothesis test is performed. ITEM_PICKED and ITEM_PACKED co-occur, in that sequence, at 1.076 times the rate independence would predict, measured over 310 process instances of which 42 exhibit the pair. The score is that effect size on a declared scale, discounted for the size of the sample it was measured on.

- measure: `lift over an instance-level 2x2 contingency table; no hypothesis test is performed`
- sample size (process instances): `310`
- both: `42`
- cause only: `68`
- effect only: `68`
- neither: `132`
- effect size (lift): `1.076033`
- declared lift_reference: `3.000000`
- effect size on the declared scale: `0.066703`
- declared small_sample_prior_count: `20`
- sample-size discount: `0.677419`
- blend: `effect-weighted: discount^(1/3) * lift^(2/3)`
- p-value: `not computed; no null hypothesis is tested`
- ⚠ Lift measures co-occurrence against independence within one dataset version. It establishes NO causation, NO direction (lift is symmetric; this candidate's direction comes only from the LAW-TIME gate), NO freedom from confounding, and NO statistical significance -- no null is tested and no sampling distribution is assumed.
- ⚠ Confounding structures are present in this candidate graph and are REPORTED, not resolved. Nothing in V1 distinguishes a direct association from one explained by a third event, and the absence of a flag is not evidence of no confounding (CONTEXT.md R-05).

**`temporal_support` = 0.150000**

Both events were placed in time, but not precisely enough to say which came first. This scores the low value this rule pack declares for an unresolvable precedence, and CAPS the whole edge.

- temporal verdict: `UNDETERMINED`
- declared undetermined_temporal_support: `0.150000`
- ⚠ The events were placed; precedence was not resolved. That is more than an absent timestamp and much less than an established precedence.
- ⚠ A dominant UNDETERMINED share is a finding about the source's granularity (CONTEXT.md R-14). It is never resolved by loosening the test or by raising this number.
- ⚠ This edge can never be promoted to INFERRED (ADR-0007).

### 10. `evt:1c0dcb783c7c3a63` → `evt:0c7d749ef7153e5b`

- `causal_edge_id`: `edg:f45243811ed2d2fa`
- edge kind: `DIRECT`
- **confidence: 0.400000** via `gated_weighted_mean_v1`
- band: WEAK
- outcome: `SCORED` (7 of 8 components measured)
- provenance: `STATISTICAL` · temporal verdict: `UNDETERMINED` · temporally unverifiable: false
- weighted mean of the addends before gating: 0.510863; binding gate: temporal_support

> Weak -- inspect before acting. Either the support is thin, the ordering could not be established, or something on record argues against the claim. The breakdown beside this label says which; read it before using this edge for anything.

**`contradiction_freedom` = 0.769231**

This claim has counter-evidence against it, so its score is capped. Higher is better here: 1.0 means nothing argues against the claim, and this edge scores 0.769. What was found: reverse pair (the opposite direction was independently proposed).

- constraint prohibition: `no`
- rule conflicts touching this pair: `0`
- reverse pair also proposed: `yes`
- confounding flags on this edge: `0`
- total contradiction weight: `0.300000`
- half-at: `1.000000`
- ⚠ READ THE DIRECTION. This component is inverted relative to its name in the brief: it scores FREEDOM from contradiction, so a HIGH value means LITTLE counter-evidence. It is named this way so that every component rises with support and the aggregation stays monotone (ADR-0052).
- ⚠ A confounding flag is not counter-evidence. It marks a structure that could explain the association without this edge being real. Nothing at V1 resolves it, and the ABSENCE of a flag is not evidence of no confounding -- an unobserved common cause leaves no shape in a graph built from observed events (CONTEXT.md R-05).
- ⚠ Absence of contradiction is not support. A claim nothing argues against still needs evidence FOR it, which the other seven components supply.

**`evidence_count` = 0.625000**

5 distinct justification(s) support this pair. The scale is saturating: this pack is half convinced at 3, and each further justification adds less than the one before it.

- distinct evidence items: `5`
- generators reaching this pair: `3`
- declared saturation k: `3`
- ⚠ This counts justifications; it does not ask whether they are independent. Ten items of one kind score the same here as ten items of ten kinds. The evidence_diversity component is what separates them, and it is weighted higher than this one.
- ⚠ Evidence items are deduplicated by content address, so two generators minting a byte-identical justification contribute one item, not two.

**`evidence_diversity` = 0.500000**

Support for this pair comes from 3 distinct kind(s) of evidence, produced by 3 independent generator(s): RULE, STATISTICAL_ASSOCIATION, TEMPORAL_PROXIMITY via rule_based, statistical_association, temporal_proximity. Independent lines of reasoning reaching one conclusion count for more than one line repeated, which is why this is weighted above raw evidence count.

- distinct evidence kinds: `3`
- reachable kinds this run: `5`
- kind spread: `0.500000`
- distinct generators: `3`
- reachable generators this run: `5`
- generator spread: `0.500000`
- total evidence items: `5`
- ⚠ Independence here means different reasoning, not statistical independence. Two generators can rest on the same underlying coincidence in the data -- the shared-entity and shared-identifier generators are the obvious pair -- and nothing here detects that.
- ⚠ Normalized against what THIS run could reach, not against the full vocabulary. A run with generators that could not run has a smaller denominator, so diversity scores are not comparable across runs with different generator availability.

**`graph_connectivity` = 0.000000** *(MISSING)*

Not scored: graph_connectivity could not be computed for this edge, so it contributes nothing. This is an absence of measurement, not a measurement of absence -- the edge is scored lower for it, and the gap is reported rather than hidden.

- *needs*: at least one Relationship in the fact set. The relationship graph is module 7's output and module 8's projection, and neither exists yet (CONTEXT.md section 3) -- so this component is MISSING on every edge today rather than scored zero or silently omitted, and every edge is scored lower for it.

**`historical_support` = 0.570272**

Across 310 process instances, 110 contained ITEM_PACKED and 106 of those went on to contain SHIPMENT_DISPATCHED. That is a rate of 0.964 against a baseline rate of 0.723 for SHIPMENT_DISPATCHED overall -- a lift of 1.334. The score is that lift on a declared scale, then discounted because 106 instances is a sample of that size.

- process instances (denominator): `310`
- instances with cause type: `110`
- instances with effect type: `224`
- instances with the sequenced pair: `106`
- cause only: `4`
- effect only: `118`
- neither: `82`
- conditional rate: `0.963636`
- baseline rate: `0.722581`
- lift: `1.333604`
- declared lift_reference: `3.000000`
- lift on the declared scale: `0.262044`
- declared small_sample_prior_count: `20`
- small-sample discount: `0.841270`
- blend: `sample-weighted: discount^(2/3) * lift^(1/3)`
- module 9 recurrence items on this edge: `0`
- ⚠ A lift of 1.0 is independence and scores zero. A pattern that appears in every instance is not evidence for anything, however large its count -- which is why the count alone is never the score.
- ⚠ Recurrence is not causation and carries no direction: this ratio is identical in both directions. The direction of this edge comes only from the temporal gate.
- ⚠ Computed over the pinned dataset version, and over whatever slice of it this run read. A different slice is a different number.

**`rule_support` = 0.690000**

1 authored rule justification(s) in the active pack support this pair. Their declared strengths are combined so that independent rules corroborate rather than average: two rules reaching the same conclusion by different reasoning say more than either alone.

- rule justifications: `1`
- authored strength [evi:46913d57fb94f2f2]: `0.690000`
- combined (noisy-OR): `0.690000`
- ⚠ A rule is a stated belief about the domain, not an observation of it. Strong rule support means the pack's authors expected this; it does not mean it happened.
- ⚠ Rules that a constraint suppressed, and conflicts the rule engine reported, are NOT subtracted here. They lower this edge through the contradiction_freedom component, so that weak support and contradicted support stay distinguishable.

**`statistical_support` = 0.386570**

Measure: lift over an instance-level 2x2 contingency table; no hypothesis test is performed. ITEM_PACKED and SHIPMENT_DISPATCHED co-occur, in that sequence, at 1.334 times the rate independence would predict, measured over 310 process instances of which 106 exhibit the pair. The score is that effect size on a declared scale, discounted for the size of the sample it was measured on.

- measure: `lift over an instance-level 2x2 contingency table; no hypothesis test is performed`
- sample size (process instances): `310`
- both: `106`
- cause only: `4`
- effect only: `118`
- neither: `82`
- effect size (lift): `1.333604`
- declared lift_reference: `3.000000`
- effect size on the declared scale: `0.262044`
- declared small_sample_prior_count: `20`
- sample-size discount: `0.841270`
- blend: `effect-weighted: discount^(1/3) * lift^(2/3)`
- p-value: `not computed; no null hypothesis is tested`
- ⚠ Lift measures co-occurrence against independence within one dataset version. It establishes NO causation, NO direction (lift is symmetric; this candidate's direction comes only from the LAW-TIME gate), NO freedom from confounding, and NO statistical significance -- no null is tested and no sampling distribution is assumed.
- ⚠ Confounding structures are present in this candidate graph and are REPORTED, not resolved. Nothing in V1 distinguishes a direct association from one explained by a third event, and the absence of a flag is not evidence of no confounding (CONTEXT.md R-05).

**`temporal_support` = 0.150000**

Both events were placed in time, but not precisely enough to say which came first. This scores the low value this rule pack declares for an unresolvable precedence, and CAPS the whole edge.

- temporal verdict: `UNDETERMINED`
- declared undetermined_temporal_support: `0.150000`
- ⚠ The events were placed; precedence was not resolved. That is more than an absent timestamp and much less than an established precedence.
- ⚠ A dominant UNDETERMINED share is a finding about the source's granularity (CONTEXT.md R-14). It is never resolved by loosening the test or by raising this number.
- ⚠ This edge can never be promoted to INFERRED (ADR-0007).


## Payload divergence

None. No two candidates of one kind over one pair disagreed about their payload parameters.
