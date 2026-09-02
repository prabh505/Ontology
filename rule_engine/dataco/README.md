# `rule_engine/dataco/` — the DataCo rule pack

**This directory is DATA.** prd.md §46: "Never hardcode logistics logic into source code."
It and `ontology/packs/dataco/` are the only two places in this repository where logistics
vocabulary may live. The evaluator that reads this file
(`backend/src/causalog/rule_engine/`) contains none of it, and
`scripts/check_domain_independence.py` fails the build if it ever does.

```
rules.yaml    24 rules, 23 enabled. rule_pack_version 1.0.0.
```

## This directory was meant to stay empty until module 9, and no longer is

The README this replaces said so plainly:

> Authored with module 9 (Candidate Cause Generator), which is the first module that
> consumes rules. Empty until then, by intent — an unratified rule would fire against a
> graph nobody has validated.

That intent is recorded here rather than quietly overwritten, because **the concern behind
it is still live and is not resolved by this pack existing.** Modules 7, 8 and 9 are
`not-started` (`CONTEXT.md` §3). There is no temporal property graph, no candidate cause
generator, and **no run has ever evaluated these rules against real DataCo facts.** Every
rule here has been checked against the ontology's declared vocabulary and exercised against
synthetic fixtures; none has been observed to fire against the dataset.

What changed is the balance of costs. Leaving the seam unbuilt kept `rule_pack_version`
`unset`, which blocked every `run_id` and left the ontology loader reporting rule coverage
as a check that could not run — a state `docs/ontology.md` §6 had been carrying since the
ontology layer shipped. Building it now means the coverage question has an answer and the
`RunKey` is complete; it does **not** mean the rules are right. The weights in particular
are judgements, several rules are labelled `ASSUMPTION`, and the first real run should be
expected to move them.

Read this pack as a set of declared, inspectable, testable hypotheses. It is not a validated
model, and nothing in this repository claims it is.

## What a rule declares, and why each field is required

Every rule carries `id`, `description`, `rationale`, `author`, `base_strength`,
`knowledge_provenance`, `evidence_basis`, and `enabled`. None is decorative:

- **`rationale`** — a rule nobody justified is a rule nobody can argue with.
- **`knowledge_provenance`** — `DOMAIN_EXPERTISE`, `DATASET_OBSERVATION`, or `ASSUMPTION`.
  This is **not** `ProvenanceClass` (ADR-0045): it says where a *policy* came from, not how
  a *fact* came to be known, and the two are never combined.
- **`evidence_basis`** — the content behind the class. An `ASSUMPTION` with an empty basis
  is refused at load: an assumption nobody wrote down cannot be shown to a user, and the
  premise of this system is that a user sees what it is assuming.
- **`enabled`** — a disabled rule keeps its identifier, so a past run that cites it stays
  legible. A disabled rule must state `disabled_reason`.

## The composition of this pack, stated plainly

| Knowledge provenance | Rules |
|---|---|
| `DOMAIN_EXPERTISE` | 15 |
| `DATASET_OBSERVATION` | 4 |
| `ASSUMPTION` | 5 |

**Five of twenty-four rules are assumptions, and one more is disabled as unreachable.** That
ratio is a finding about this dataset, not a shortcoming to be tidied away — it is the same
finding the ontology pack reports when it declares one `OBSERVED` event type and nineteen
`DERIVED` ones. Every assumption is visible to users.

The four `DATASET_OBSERVATION` rules deserve a caveat this README would be dishonest to
omit: they rest on statements the *ontology pack* makes about the dataset (its declared
process variants, its enumerated status values, its own comment that late delivery is "the
single most common departure"), not on counts this repository has performed. **No pipeline
has run end to end** (`CONTEXT.md` OQ-014), so no rule here rests on a measured frequency.
When one does, these weights should move and the class should be re-earned.

## What prd.md §25's chain cannot reach, and why nothing was invented

§25 prints:

```
Inventory Shortage -> Warehouse Delay -> Truck Missed -> Late Delivery
                   -> Customer Complaint -> Refund
```

The first four segments are expressible and are authored here. The last two are not:

| §25 segment | Why it is absent |
|---|---|
| Customer Complaint | The ontology declares no such event type, because DataCo carries "no complaint, contact, or service column of any kind" (`ontology/packs/dataco/README.md`). |
| Refund | The ontology declares no refund concept at all. The dataset has profit and benefit columns, which are outcomes, not occurrences. |

Declaring them would manufacture occurrences the source never recorded — the failure
LAW-PROVENANCE and ADR-0029 exist to prevent. **The chain terminates where the ontology
terminates**, and `docs/reports/dataco/rule-coverage.md` names the gap rather than leaving
it to be noticed.

## Coverage, and the blind spots

13 of the 20 declared event types have a rule explaining them (65%). One more —
`ORDER_RELEASED` — is declared but unwitnessable: the schema mapping carries no emission
rule for it, so its rule is present and **disabled**, with the reason recorded on the rule.

The six remaining blind spots are:

```
FRAUD_SUSPECTED   INVENTORY_SHORTFALL_DETECTED   ORDER_PLACED
PAYMENT_FAILED    PAYMENT_REQUESTED              PAYMENT_REVIEW_OPENED
```

**These are not omissions to be filled in.** Every one of them is a *root* in this dataset:
nothing DataCo records explains why stock ran short, why a settlement failed, or why a review
was opened. `ORDER_PLACED` is the process origin and has no antecedent by construction. A
rule claiming to explain any of them would be inventing a mechanism the source does not
witness. What they mean in practice is that a root-cause query terminating at one of these
will say "this is where the evidence stops", which is the correct answer.

## Why the temporal windows are wide

DataCo is one row per line with day-granularity dates. Nineteen of twenty event types are
`DERIVED`, and most carry `occurred_at: UNKNOWN` in the mapping, meaning an unbounded
interval. A narrow window would not be more rigorous — it would be a claim about instants
the source never recorded. Each firing carries its own LAW-TIME verdict, and a pair the data
cannot separate is reported `UNDETERMINED` rather than admitted or dropped (ADR-0007). If
`UNDETERMINED` dominates a run, that is a finding about the dataset and never something to
tune away by loosening the test (`CONTEXT.md` R-14).

## Checking this pack

```
python scripts/check_rule_pack.py --self-test     # prove the checks reject
python scripts/check_rule_pack.py --dataset dataco
```

or `make rules DATASET=dataco`. Both run in CI.

Editing any rule changes `rule_pack_hash`, and `rule_pack_version` participates in `run_id`
(ADR-0013) — so an edit here creates a new Run, and prior runs are not comparable to
subsequent ones.
