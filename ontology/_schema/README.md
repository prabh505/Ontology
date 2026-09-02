# `ontology/_schema`

**Single responsibility:** publish the JSON Schema every domain pack validates against, so
that tooling outside Python — an editor, a CI linter, another language — can check a pack
without importing the distribution.

```
ontology.schema.json    GENERATED. Do not hand-edit.
```

**The pydantic models in `causalog.ontology_runtime.dsl` are normative** (ADR-0026); this
file is rendered from them by `scripts/export_ontology_schema.py`, and
`scripts/export_ontology_schema.py --check` fails the build when the two disagree. It runs
in `make laws` and in its own CI job.

A hand-authored schema beside a code validator would be two descriptions of one contract,
free to drift. The drift surfaces as a pack one validator accepts and the other rejects,
with nobody able to say which is right — so there is exactly one description, and the other
is generated from it.

To regenerate after changing the models:

```
python scripts/export_ontology_schema.py --write
```
