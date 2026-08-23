"""CausaLog — a domain-agnostic causal intelligence engine.

The reasoning core computes over Event, Entity, State, Transition, and Relationship.
All domain vocabulary lives in the replaceable ontology layer (LAW-DOMAIN).
"""

__all__ = ["ENGINE_VERSION"]

#: Participates in the ``run_id`` fingerprint (ADR-0013). Bump on any change that can
#: alter engine output for identical inputs.
ENGINE_VERSION = "0.1.0"
