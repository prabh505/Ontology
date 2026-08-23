# `ontology/_schema`

**Single responsibility:** define the JSON Schema every ontology instance must validate
against, so that a malformed ontology fails at load rather than producing silently wrong
causality.

The validator that applies it is `causalog.ontology_runtime`. The schema itself lands with
module 2 (Schema Mapper); this directory is its reserved location.
