"""The Run: the unit of reproducibility (ADR-0013).

A Run is the tuple of every input that can change engine output, condensed into one
content-addressed identifier. Identical tuple implies identical `run_id` implies
byte-identical artifacts.

`run_id` is NOT the per-execution identifier. That is `execution_id`: random, present in
logs and API correlation, and excluded from every determinism comparison.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

__all__ = ["OutputEnvelope", "RunKey"]


class RunKey(BaseModel):
    """The five inputs that determine a `run_id`.

    `run_id = "run:" + sha256(dataset_version | ontology_hash | rule_pack_version |
    engine_version | seed)[:16]`, built with `causalog.core.identifiers.digest`.

    Every inferred artifact is scoped to a `run_id`. Observed facts are NOT run-scoped;
    they are dataset-scoped, which is what makes "inference never overwrites observation"
    (LAW-PROVENANCE) structural rather than procedural.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_version: str
    ontology_hash: str
    rule_pack_version: str
    engine_version: str
    seed: int


class OutputEnvelope(BaseModel):
    """Carried by every persisted artifact and every API response body.

    `CONVENTIONS.md` §11: an output without its envelope cannot be verified and is a
    defect. `execution_id` is present for correlation and is excluded from determinism
    diffs by `scripts/check_determinism.py`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    ontology_version: str
    ontology_hash: str
    dataset_version: str
    rule_pack_version: str
    engine_version: str
    graph_projection_version: str
    seed: int
    execution_id: str
