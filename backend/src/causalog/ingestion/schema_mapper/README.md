# `causalog.ingestion.schema_mapper`

**Layer rank:** `L2` · **Module 2** · Status `built-unverified`

## Single responsibility

Bind dataset columns and values to ontology concepts (module 2).

The mapping itself is **data**, at `ontology/packs/<domain>/mapping.yaml` (extension seam 3).
This package holds the schema that data is validated against, the loader, the coverage
assessment, and the auto-suggester.

## Public surface

- `SchemaMappingSpec` — the DSL (ADR-0036), `draft`. Eight namespaces; a closed `Transform`
  registry; no expression strings, for the reason ADR-0026 gave about the ontology DSL.
- `load_mapping(path, pack, header=…)` — validates and **refuses**: an unconfirmed proposal,
  or any coverage `ERROR`.
- `assess_coverage(mapping, pack, header=…)` — what is unmapped, and what that breaks.
- `suggest_mapping(profile, pack)` / `render_proposal_yaml(…)` — a proposal, never a mapping.
- `mapping_hash(mapping)` — `map:<sha256(canonical)[:16]>`, the ADR-0028 recipe.

## The three refusals

1. **A proposal never loads.** `status: PROPOSED_UNCONFIRMED` is a hard error, not a warning.
   A human removes it in a commit. That is the whole confirmation mechanism, and it is a
   refusal because a warning is a thing that gets read once.
2. **No value is ever defaulted.** `unmapped_value_policy` exists and admits exactly one
   value, `ERROR`. It is a field rather than an assumption so that a future proposal to
   default an unmapped value has to change a declared contract in a diff somebody reads
   (risk R-07).
3. **No column goes unlisted.** Every header column is bound or is justified under
   `dropped_columns`. "We did not map it" and "we did not notice it" are otherwise
   indistinguishable, and only one of them is a decision.

## What it does NOT guarantee

**That a binding is correct.** The suggester's precision is unmeasured — there is no
labelled ground truth for column-to-concept mappings anywhere in this repository — and a
mapping that loads cleanly can still be semantically wrong, producing silently wrong
causality rather than an error. That is risk R-16 arriving through the mapping, and it is
why the proposal cannot load. The suggester's match figure is called `score`, not
`confidence`: LAW-EVIDENCE reserves that word for a decomposable vector.

## Forbidden dependencies

`extraction` and above; may never default an unmapped value; may never import
`causalog.persistence.*` (F4). **In LAW-DOMAIN scope since ADR-0037.**

See `docs/architecture.md` §1 for the layer map and §5 for the extension seams.
