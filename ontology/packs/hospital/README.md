# `ontology/packs/hospital`

**Single responsibility:** prove a negative — that the domain-pack DSL is not secretly
shaped like logistics.

This pack has no dataset behind it and is not intended to acquire one. Every attribute is
`ASSUMED`, which is the honest origin when nothing was observed. It exists for two reasons:

1. **A regression test.** `tests/ontology/test_pack_is_not_domain_shaped.py` loads it
   through the identical code path the DataCo pack uses, with zero engine changes. Any
   change to the DSL that quietly assumes a supply chain breaks this file first.
2. **A worked example.** It is the shortest complete pack in the repository and the one to
   read before authoring a new domain (`docs/ontology.md`).

Four entity types (`PATIENT`, `BED`, `CLINICIAN`, `DEPARTMENT`), five event types
(`ADMITTED`, `TRIAGED`, `BED_ASSIGNED`, `TREATED`, `DISCHARGED`), one process, one
measurement. `DISCHARGED` is declared `DERIVED` on purpose, so the derived-event path is
exercised by a pack that is not DataCo.

## What this pack does NOT prove

That swapping the ontology changes the engine's *output*. That needs a pipeline, and the
obligation for `tests/ontology/test_ontology_swap.py` in `docs/architecture.md` §8 remains
open. What is proved today is that the *schema* is domain-neutral: two unrelated domains
load through one code path, share no behavioural vocabulary, and share only the structural
base. `docs/architecture.md` §1.5 states the residual — a reasoning package branching on a
data *value* — and it is still not covered by any lint.
