# `backend/tests`

**Single responsibility:** hold every automated check that gates a module, organized by the
test taxonomy in `CONVENTIONS.md` §14.

| Directory | Asserts |
|---|---|
| `unit/` | one module's behavior in isolation; mirrors `src/causalog/` one-to-one |
| `law/` | the Five Inviolable Laws are not violated — a failure here is `CRITICAL` |
| `determinism/` | two runs with the same seed and ontology hash are byte-identical |
| `integration/` | adjacent modules interoperate across a registered interface |
| `pipeline/` | an end-to-end run on a fixture dataset yields a well-formed graph |
| `graph/` | edge direction, temporal admissibility, cycle detection, depth arithmetic |
| `ontology/` | every column maps or hard-fails; an ontology swap changes output with no code change |
| `counterfactual/` | a null intervention reproduces the base world; no writeback to history |
| `api/` | response schema, provenance fields, output envelope |
| `fixtures/` | synthetic domain-neutral fixtures; `fixtures/dataco/` is the ONLY place LAW-DOMAIN vocabulary may appear |

**Forbidden:** no test may assert that a causal conclusion is *correct* — this dataset has
no causal ground truth (`CONVENTIONS.md` §14). Tests assert structural properties only.
