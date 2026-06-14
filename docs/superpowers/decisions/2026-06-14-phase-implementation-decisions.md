# Phase Implementation Decisions

## Phase 1

- Decision: Batch the plan's small TDD tasks into phase-level commits instead of one commit per checkbox.
  Options: one commit per checkbox; one commit per task group; one commit per phase.
  Chosen: phase-level commits, because the repo already has strong tests and smaller history noise is easier to review.
- Decision: Keep LH/RH validation minimal.
  Options: infer orientation from item names; require explicit orientation and twin item; add a new pairing doctype.
  Chosen: require explicit orientation and twin item, because it matches the plan without adding model surface.
- Decision: Defer joined part-number and label formatting until the export phase.
  Options: add BOM-service helpers in Phase 1; add export-local helpers in Phase 2; add stored display fields.
  Chosen: add the formatting only where Phase 2 consumes it, because Phase 1 does not need new public helper surface.
