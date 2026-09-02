"""The Run: the unit of reproducibility (ADR-0013).

A Run is the tuple of every input that can change engine output, condensed into one
content-addressed identifier. Identical tuple implies identical `run_id` implies
byte-identical artifacts.

`run_id` is NOT the per-execution identifier. That is `execution_id`: random, present in
logs and API correlation, and excluded from every determinism comparison.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from causalog.core.identifiers import (
    IdentifierPrefix,
    canonical_instant,
    canonical_payload,
    canonical_text,
    digest,
)

__all__ = ["OutputEnvelope", "Run", "RunKey"]


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

    def address(self) -> str:
        """Return the content-addressed `run_id` for this key (ADR-0013).

        Payload recipe: `dataset_version | ontology_hash | rule_pack_version |
        engine_version | seed`.

        `seed` participates even though V1 is fully deterministic and the seed is
        therefore ceremonial (ADR-0003). It is required anyway so that introducing a
        stochastic component later cannot silently escape the fingerprint -- a run that
        started sampling would otherwise reuse the identifier of the run that did not.
        """
        return digest(
            IdentifierPrefix.RUN,
            canonical_payload(
                canonical_text(self.dataset_version),
                canonical_text(self.ontology_hash),
                canonical_text(self.rule_pack_version),
                canonical_text(self.engine_version),
                canonical_text(str(self.seed)),
            ),
        )


class Run(BaseModel):
    """One reproducibility unit: its key, its identifier, and when it was started.

    Every inferred artifact carries this run's `run_id` (ADR-0013). Observed facts do not:
    they are dataset-scoped, and that asymmetry is what makes "inference never overwrites
    observation" structural rather than procedural.

    `created_at` is **passed in**, obtained from the `Clock` port by whoever assembles the
    run. Reading the wall clock inside a reasoning module is a determinism defect
    (`CONVENTIONS.md` §11), and this field is deliberately excluded from the `run_id`
    payload -- two runs over identical inputs are the same run, whatever hour they started.

    Invariants:
      * `run_id == key.address()`.
      * `created_at` is timezone-aware UTC.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    key: RunKey
    created_at: datetime

    @model_validator(mode="after")
    def _check_invariants(self) -> Run:
        """Enforce the documented invariants at construction."""
        canonical_instant(self.created_at)
        expected = self.key.address()
        if self.run_id != expected:
            raise ValueError(
                f"Run.run_id {self.run_id!r} does not match its key, which addresses to "
                f"{expected!r}. A run identifier that disagrees with its own inputs makes "
                "every artifact scoped to it unverifiable (ADR-0013)."
            )
        return self


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
