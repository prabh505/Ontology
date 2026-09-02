# `causalog.persistence.memory`

**Layer rank:** none — a driven adapter, like the rest of `persistence`.

## Single responsibility

Implement the `core/ports` capabilities in memory, so the unit suite runs with no services.

## Why fakes rather than mocks

A mock asserts that a call happened. A fake behaves. Every property worth asserting about
this layer is behavioural — canonical sequencing, the dataset/run scoping asymmetry, the
append-only refusal, bi-temporal supersession — and a mock exhibits none of them. A suite
built on mocks passes against a repository that returns rows in insertion order, which is
the exact defect `CONVENTIONS.md` §11 exists to prevent.

## How drift is prevented

`tests/unit/persistence/test_repository_contract.py` is parameterized over **this adapter
and the PostgreSQL one**. A behaviour the two do not share fails in one of them. Without
that, a fake is a second implementation free to be wrong in a comfortable direction.

**Forbidden:** no I/O, no persistence across a process, no shortcut around a law the real
adapter enforces. A fake that accepted an unevidenced observed fact would make the law
tests pass for the wrong reason.
