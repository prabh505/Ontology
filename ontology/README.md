# `ontology/`

**Single responsibility:** hold domain vocabulary as **data**, so that no reasoning package
ever names the thing it is reasoning about (LAW-DOMAIN, ADR-0002).

Everything here is data. The code that loads and validates it is
`backend/src/causalog/ontology_runtime/`, and that code is **not** exempt from the
LAW-DOMAIN lint — as of ADR-0026 it is explicitly in the lint's scope, because the one
package built to keep the domain out was the one package not being checked for it.

```
_schema/            the JSON Schema every pack validates against -- GENERATED from
                    causalog.ontology_runtime.dsl, never hand-edited
packs/_base/        the structural base every domain pack extends: ordinal cost and
                    severity vocabularies, and nothing domain-specific
packs/dataco/       the DataCo instance. prd.md §21's event vocabulary lives HERE, not in
                    the engine -- it is one instance, not the engine's ontology
packs/hospital/     an unrelated domain with no dataset behind it, carried as proof that
                    the DSL is not secretly logistics-shaped (ADR-0026)
```

Packs moved from `ontology/<domain>/` to `ontology/packs/<domain>/` in ADR-0027, so that
`_schema/` and `_base/` are not siblings of real domains.

Each domain directory supplies the ontology seam (`docs/architecture.md` §5). The other
seams — `mapping.yaml`, `cost.yaml`, `labels.yaml`, and a rule pack under
`rule_engine/<domain>/` — land with the modules that own them and are **not** folded into
the pack: collapsing six seams into one would make a pack author responsible for four
different contracts at once.

**Forbidden:** no executable code, no reasoning, no defaults. There is no expression string,
no callable reference, and no plugin hook anywhere in the schema; a metric that cannot be
written as a declarative operator tree needs a new operator and an ADR, never an escape
hatch. An unmapped column or value is a hard error at mapping time with the value named —
never a fall-through to a catch-all concept (`CONVENTIONS.md` §7). A "sensible default" here
manufactures causality out of a gap in the data.

To add a domain, follow the numbered checklist in `docs/ontology.md`.
