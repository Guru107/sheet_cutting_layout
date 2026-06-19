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

## Phase 2

- Decision: Ship the generated minimal FRM/PRD/15 workbook template for implementation verification.
  Options: stop until the curated audit-approved workbook is provided; generate a minimal testable workbook; hard-code workbook bytes in tests.
  Chosen: generate and commit the minimal workbook, because the cell-map contract remains testable and the curated template can replace the file later without code changes if coordinates match.
  Trade-off: this does not certify the workbook artwork as audit-approved; it verifies the export contract now and keeps the template swap isolated to one file when the approved workbook is supplied.

## Phase 3

- Decision: Keep `retire_layout` as the existing Phase 0 retirement helper name instead of renaming it to `retire_layout_boms`.
  Options: rename the helper to match the plan text; keep the current helper name; add an alias.
  Chosen: keep the current helper name, because the behavior already matches the contract and a rename would add churn.
- Decision: Let recursive Sheet Cutting Layout links bypass native backlink blocking during cancel.
  Options: clear child links before cancel; set instance-level `ignore_linked_doctypes`; make the link non-submitted-only.
  Chosen: set instance-level `ignore_linked_doctypes` for `BOM` and `Sheet Cutting Layout` during cancel, because it preserves the child links while allowing the designed leaves-first cascade.
- Decision: Cover the descendant BOM cancel-block fallback with a deterministic `LinkExistsError` test double instead of a full Manufacture Stock Entry fixture.
  Options: create submitted manufacture stock entries; patch the descendant BOM cancel call to raise the native link error; leave the fallback covered only by unit tests.
  Chosen: patch the cancel call, because the Phase 3 contract is the fallback from cancel to deactivation and the full stock-entry setup would couple this test to inventory fixture details.
  Trade-off: this verifies the native-block fallback path, not the ERPNext stock-entry document setup.

## Phase 4

- Decision: Keep the Phase 2 dict-based export model and add multi-sheet composition around it.
  Options: introduce a new layout view object; add sheet-title fields to the export dict; keep `_export_layout_dict` plus `build_cell_map`.
  Chosen: keep the dict model, because it is already covered and the recursive export only needs ordered `(layout.name, layout_dict)` pages.
  Trade-off: worksheet titles are passed beside the dict rather than embedded in it.
- Decision: Clone the FRM/PRD/15 template worksheet once per exported layout page.
  Options: render only the first sheet from the template and use blank sheets for children; clone the template sheet; hand-build worksheet formatting.
  Chosen: clone the template sheet, because every recursive page should preserve the same audit layout without duplicating formatting rules in code.
  Trade-off: opening/cloning the template per page is simpler and safer for expected shallow layout trees, but not optimized for very large recursive trees.
- Decision: Keep Cypress download validation binary-level and cover workbook sheet contents in Python integration tests.
  Options: parse `.xlsx` inside Cypress; assert non-empty binary XLSX in Cypress and inspect workbook cells in Python; skip E2E download coverage.
  Chosen: assert the XLSX response in Cypress and validate sheet count/cells with openpyxl in Python, because the bench UI suite already validates the full Desk workflow while Python is the reliable place to inspect workbook internals.
