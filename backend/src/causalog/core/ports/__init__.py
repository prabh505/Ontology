"""Abstract capabilities the reasoning layers require from the outside world.

A port is declared here; an adapter implementing it lives in `causalog.persistence` and is
wired only by `causalog.orchestration` (ADR-0014).
"""
