# Recommendation Report

> **BOUNDED RUN.** Built from the first 150 rows of the clean layer, not from
> all 180,519. Neither module 9 nor module 10 is a streaming module -- the base
> rates measure across process instances and the fusion needs the whole candidate
> graph in hand -- and the full expansion does not fit in memory as models on an 8 GB
> machine (`tests/integration/test_full_expansion_budget.py`). **Every number below
> measures this slice, not the dataset.** Re-run with `--rows 0` to remove the bound.

> **The question (prd.md §51, Workspace 6).** Which acts should an operator be shown first, to protect SHIPMENT_DELAYED, ORDER_CANCELED?


`recommendation_report_schema_version` 1.0.0 · `run_id` run:f38e8e4dccbb8415 · standing **UNPROMOTED_DIAGNOSTIC**

> EVERY COST AND EVERY OPERATIONAL RISK BELOW IS AN ASSUMPTION, NOT A MEASUREMENT. They are read from the ontology pack, where their provenance is pinned to ASSUMED because no observation in any dataset establishes what an act costs an organisation or what taking it risks. Nothing in this system can validate either declaration, and a mis-declared one silently changes the sequence below with no symptom (R-15, R-25). Benefit figures are SIMULATED: they describe a world that did not happen, re-evaluated over links derived from rules, temporal structure and frequency rather than identified as causal effects. This report ranks acts; it does not establish that any of them would work.
>
> NOTHING BELOW IS CALIBRATED. A support envelope says a change stays inside the range this run witnessed; it does not say the answer is right. Calibration would mean outcomes stated at a given belief are right that often, and measuring it needs labelled causal ground truth -- pairs where somebody independently established what actually caused what. This dataset carries none, so no reliability curve can be drawn and no error rate can be quoted. A decomposed, envelope-checked, sensitivity-swept figure is MORE persuasive than a bare one and is not more accurate, and that is the specific way this artifact could do harm.
>
> THIS IS NOT THE ENGINE'S VIEW. Every link below was considered and NOT asserted -- it did not clear the band its pack declares, or its precedence could not be established, or too little was measured on it to say. The traversal is real, the arithmetic is real, and the conclusion is disowned. It is published so that a reader can see what the machinery does and can check it, and so that the reason the stated view is empty is visible as a property of the inputs rather than as an absence of output. Nothing here may be cited as a cause, and nothing here is an input to simulation or to recommendation.

## 1. What this run did

- Nodes proposed by the four generators: **1130**
- Refused at the actionability gate: **471**
- Published as recommendations: **0**
- Withheld with a reason: **202**

## 3. Ranked recommendations

**None.** This is a finding, not an empty section. Every candidate either failed the actionability gate or was withheld; sections 1 and 4 say which.

## 4. Withheld, and why

| Node(s) | Reason | Checked against | Belief |
|---|---|---|---|
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED, SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED, SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| ITEM_PACKED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| ITEM_PACKED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| ITEM_PICKED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| INVENTORY_RESERVED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| INVENTORY_RESERVED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| PAYMENT_APPROVED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| ITEM_PICKED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| ITEM_PACKED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| ITEM_PICKED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| PAYMENT_APPROVED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| ITEM_PACKED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| ITEM_PACKED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| ITEM_PICKED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| ITEM_PICKED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| ITEM_PICKED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| ITEM_PACKED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| ITEM_PACKED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| PAYMENT_APPROVED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| PAYMENT_APPROVED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| PAYMENT_APPROVED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| ITEM_PICKED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| ITEM_PICKED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| INVENTORY_RESERVED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| ITEM_PACKED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| INVENTORY_RESERVED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| ITEM_PICKED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| ITEM_PACKED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| PAYMENT_APPROVED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| ITEM_PICKED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| INVENTORY_RESERVED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| INVENTORY_RESERVED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| ITEM_PICKED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DELAYED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| SHIPMENT_DISPATCHED | BELOW_CONFIDENCE_FLOOR | rule pack recommendation.minimum_belief_to_publish=0.5 | 0.03 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| INVENTORY_SHORTFALL_DETECTED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| PAYMENT_APPROVED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| PAYMENT_APPROVED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| INVENTORY_RESERVED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| FRAUD_SUSPECTED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| PAYMENT_APPROVED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| PAYMENT_APPROVED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| INVENTORY_RESERVED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| PAYMENT_APPROVED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| INVENTORY_RESERVED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| INVENTORY_RESERVED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| SHIPMENT_DELAYED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| INVENTORY_RESERVED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| PAYMENT_APPROVED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| INVENTORY_RESERVED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| INVENTORY_RESERVED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| PAYMENT_APPROVED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| PAYMENT_APPROVED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| PAYMENT_APPROVED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PACKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| INVENTORY_RESERVED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| INVENTORY_RESERVED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |
| ITEM_PICKED | BENEFIT_NOT_MEASURABLE | counterfactual_engine.simulate | 0.0 |

## 5. What this report is a property of

Every figure above is a property of the run named in the envelope: this dataset slice, this ontology pack, this rule pack, this seed. A benefit range is bounded by the perturbations the pack declares, not by a confidence interval. A cost and a risk are declarations. Nothing here is calibrated and no procedure in this repository could calibrate it, because the dataset carries no causal ground truth.