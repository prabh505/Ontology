# `ontology/`

**Single responsibility:** hold domain vocabulary as **data**, so that no reasoning package
ever names the thing it is reasoning about (LAW-DOMAIN, ADR-0002).

Everything here is data. The code that loads and validates it is
`backend/src/causalog/ontology_runtime/`, and that code is **not** exempt from the
LAW-DOMAIN lint.

```
_schema/            the JSON Schema every ontology instance validates against
dataco/             the DataCo instance: prd.md §21's event vocabulary lives HERE,
                    not in the engine — it is one instance, not the engine's ontology
```

Each instance directory supplies the six extension seams (`docs/architecture.md` §5):
`ontology.yaml`, `mapping.yaml`, `cost.yaml`, `labels.yaml`, plus a rule pack under
`rule_engine/<domain>/`.

**Forbidden:** no executable code, no reasoning, no defaults. An unmapped column or value
is a hard error at mapping time with the value named — never a fall-through to a catch-all
concept (`CONVENTIONS.md` §7). A "sensible default" here manufactures causality out of a
gap in the data.
