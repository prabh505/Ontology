# `causalog.causal_engine`

**Layer rank:** `L6`

## Single responsibility

Produce scored causal structure from the observed temporal graph, and decide which of it the
engine will assert.

## Sub-packages

| Package | §36 module | Owns |
|---|---|---|
| `candidate_cause_generator` | 9 | proposal; the LAW-TIME gate |
| `confidence_scorer` | 10 | scoring; the LAW-EVIDENCE gate; constructs `CausalEdge` |
| `causal_graph_builder` | **none** | promotion, edge typing, propagation weights, feedback loops (prd.md §25, §26, §31; ADR-0054, OQ-025) |
| `root_cause_analyzer` | 11 | ranking |
| `propagation_analyzer` | 12 | spread measurement |

**`ProvenanceClass.INFERRED` is assigned in `causal_graph_builder/policy.py` and nowhere else
in this package** (ADR-0054), asserted structurally by
`tests/law/test_law_time_gates_every_promotion.py`. Promotion is one decision with one home;
a second site would mean two modules deciding what the engine asserts.

## Forbidden dependencies

`counterfactual_engine`, `recommendation_engine`, `explanation_engine`, `orchestration`, `api`.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
