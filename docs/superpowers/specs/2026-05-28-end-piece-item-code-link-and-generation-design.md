# End Piece Item Code Link and Generation Design

## Summary

This design changes end-piece item handling to a single generated `Item` link field with no preview state.  
The field is shown only after generation and is not user-editable. Item creation remains in the explicit
`Generate End Piece BOMs` action flow.

## Goals

1. Keep exactly one end-piece item field in `Layout End Piece`: `end_piece_item_code`.
1. Store `end_piece_item_code` as `Link` to `Item`.
1. Do not show any generated code preview before generation.
1. Generate/reuse end-piece items only from `Generate End Piece BOMs`.
1. Derive code from `used_for_finished_part` and dimensions.
1. Add reuse validation for `used_for_finished_part` suffix: `SHR` / `BLK` / `DR`.
1. Populate BOM scrap row `rate` using valuation rate only when rate is not already set by ERPNext.

## Non-Goals

1. No compatibility fallback for old behavior (development app assumption).
1. No automatic item creation on save/validate.
1. No manual editing of end-piece item code in UI.

## Current Problems

1. End-piece item code behavior is split between a suggestion path and generated link path.
1. UI allows early code visibility/editability patterns that conflict with strict post-generation linking.
1. Costing rate fallback for scrap rows is not consistently guaranteed when ERPNext does not auto-populate.

## Approved Decisions

1. Use only `end_piece_item_code` for end-piece item linking.
1. Change `end_piece_item_code` field type to `Link` (`Item`), read-only.
1. Keep `end_piece_item_code` hidden until populated.
1. Remove `generated_end_piece_item` from doctype and code paths.
1. Build code from `used_for_finished_part`, not from finished-part parent row:
   - `<used_for_finished_part>-EP-<thickness>x<width>x<length>`
1. If computed item exists, reuse as-is.
1. If missing, create item with:
   - `item_code` = computed code
   - `item_name` = computed code
   - `description` includes raw material item and end-piece dimensions
   - `stock_uom` = `Nos`
   - Alternate UOM `Kg` with conversion factor = `1 / end_piece.weight_kg`
1. Add validation for reuse rows: `used_for_finished_part` must end with `SHR`, `BLK`, or `DR`.
1. Add scrap row `rate` in both flows when not already available:
   - finished-part BOM creation path
   - Generate End Piece BOMs path

## Data Model Changes

## `Layout End Piece` DocType

1. Change `end_piece_item_code`:
   - from: `Data`
   - to: `Link`
   - options: `Item`
   - `read_only = 1`
   - hidden when empty (via dependency/property handling)
1. Remove `generated_end_piece_item` field.
1. Keep `generated_end_piece_bom` as existing generated record link.
1. Align `disposition` options to only supported states:
   - `Reuse`
   - `Scrap`

## Behavior Changes

## UI/Client

1. Remove item-code suggestion behavior and preview dependencies.
1. Do not set `end_piece_item_code` during edit-time calculations.
1. Only display `end_piece_item_code` when non-empty.
1. Preserve existing calculation and disposition cleanup behavior for non-item fields.

## Server Validation

1. For reuse rows, validate:
   - `used_for_finished_part` is present.
   - suffix must match one of `SHR`, `BLK`, `DR`.
1. Keep existing reuse/scrap field integrity guards.
1. Keep existing generated-record lock semantics adapted to single-field model.

## Item Generation (`Generate End Piece BOMs`)

1. Compute item code from `used_for_finished_part` + dimensions.
1. Reuse existing item when present.
1. If missing, create Item:
   - derive `item_group` from `raw_material_item` (existing behavior baseline)
   - set UOM model (`Nos` stock UOM, `Kg` alternate UOM with conversion)
   - set description from `raw_material_item` and dimensions.
1. Persist generated code to `end_piece_item_code`.

## BOM Scrap Rate Fallback

1. When adding scrap rows, keep ERPNext default rate behavior first.
1. If `rate` is not set by ERPNext, fetch valuation rate for scrap item and set `rate`.
1. Apply this to:
   - Finished-part BOM creation path.
   - End-piece BOM creation path.

## Rate Source and Rules

1. Use valuation rate lookup for the relevant scrap item.
1. Do not overwrite existing populated `rate`.
1. Fail with clear error when a required scrap item is missing but a scrap row with quantity/rate needs to be created.

## Error Handling

1. Reuse-row suffix violation:
   - Throw explicit validation error listing allowed suffixes.
1. Missing or zero `end_piece.weight_kg` for conversion factor:
   - Throw explicit error before item creation.
1. Failed item creation due to missing required master data (e.g., item group):
   - Raise actionable error with row index context.

## Test Plan (Frappe/bench-native)

1. DocType contract tests:
   - `end_piece_item_code` is `Link(Item)` and read-only.
   - `generated_end_piece_item` is absent.
   - `disposition` options exclude `Hold`.
1. Validator tests:
   - reuse suffix valid for `SHR` / `BLK` / `DR`.
   - invalid suffix rejected with expected message.
1. End-piece generation service tests:
   - computed code uses `used_for_finished_part`.
   - item creation sets `Nos` stock UOM and `Kg` alternate conversion (`1 / weight_kg`).
   - existing item reuse path does not mutate item metadata.
1. BOM service/release tests:
   - scrap row `rate` is filled from valuation fallback when missing.
   - existing auto-populated `rate` is preserved.
1. Client/source assertions:
   - remove suggestion hooks and preview-only code tied to pre-generation item code.

## Rollout and Risk

1. Risk: direct schema change can invalidate local test fixtures and stale rows.
   - Mitigation: update all fixtures/tests in this repo together.
1. Risk: valuation lookups add DB calls during generation.
   - Mitigation: bounded per generated row; acceptable for current scale.
1. No migration/backward-compat layer by explicit product decision.

## Implementation Units

1. DocType metadata unit (`layout_end_piece.json`)
2. Client behavior unit (`sheet_cutting_layout.js`)
3. Validation unit (`services/validators.py`)
4. End-piece BOM generation unit (`services/end_piece_bom_service.py`)
5. Finished-part BOM/release unit (`services/bom_service.py` and/or `services/release_service.py`)
6. Bench-native test units (doctype + validators + service modules)

Each unit has a clear boundary and can be implemented/tested independently while sharing existing APIs.
