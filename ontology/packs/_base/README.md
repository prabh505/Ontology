# `ontology/packs/_base`

**Single responsibility:** declare what is true of *every* domain, so that no domain
overlay has to restate it and no domain's assumptions can leak into the next one.

Today that is exactly two things: the ordinal **cost** vocabulary that intervention ranking
reads (`CONTEXT.md` OQ-013) and the ordinal **severity** vocabulary that root-cause ranking
reads alongside impact (ADR-0008). Both carry an explicit `rank`, so a ranker compares two
members without reading their names.

Nothing else belongs here. A `_base` that declared an entity type, an event type, or a
process would make every future domain inherit one domain's shape — which is the failure the
hospital pack exists to detect.

The leading underscore marks a pack that is not a domain. Domain packs never carry one.

**Overlay semantics (ADR-0027):** an overlay entry **replaces** the base entry with the same
identifier, wholesale. A base entry is withdrawn only through an explicit `removes:` block,
and a withdrawal that removes nothing is a load error. There is no field-level merge: a deep
merge would produce an effective declaration that exists in no file, assembled from two, and
an author reading either one would see something other than what the engine loads.
