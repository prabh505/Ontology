# `rule_engine/` (data)

**Single responsibility:** hold rule packs as versioned **data** — never as source code
(prd.md §46).

The evaluator lives at `backend/src/causalog/rule_engine/`. That package holds code and is
explicitly **not** exempt from the LAW-DOMAIN lint (`CONVENTIONS.md` §6). This directory is
exempt, because domain vocabulary is exactly what a rule pack is made of.

```
dataco/             the rule pack for the DataCo ontology instance
```

Rules:
- A pack declares a `rule_pack_version`; it participates in the `run_id` (ADR-0013), so
  editing a rule changes the Run and therefore the artifacts.
- A pack that contradicts itself raises `RuleConflictError` **at load time**. A conflict is
  a load error, never a runtime coin-flip (`CONVENTIONS.md` §7).
- Every rule carries an identifier, because every inferred edge records which rules fired
  (`CONVENTIONS.md` §8, LAW-EVIDENCE).
