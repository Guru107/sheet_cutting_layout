# Main BOM Quantity Uses Parts Per Sheet

## Summary

This change updates the main finished-part BOM created from `Sheet Cutting Layout` so its BOM
quantity comes from `parts_per_sheet`, not `no_of_strips`. The change applies only to the main BOM
created for parent `finished_part_code` during `MR Release`. End-piece BOM quantity remains
user-controlled through row-level `bom_quantity`.

The end-piece child field `qty_per_sheet` is no longer part of the active business model. Each
end-piece row already represents exactly one end piece per sheet, so the field is not required for
generation, validation, or consumption logic. Existing layouts that still rely on `qty_per_sheet`
to encode multiplicity must be corrected before save or release by splitting that row into one row
per end piece.

Because the app is under development, this is a hard cutover. Existing local released BOMs created
under the strip-count rule must be corrected locally so they match `parts_per_sheet`.

This spec supersedes the earlier main-BOM quantity rule in the June 2 BOM/versioning design and
the June 3 submitted-derived-BOM lifecycle design wherever those documents still imply main BOM
quantity equals `no_of_strips`. Those earlier specs remain in force for everything else.

## Goals

1. Make the main finished-part BOM quantity equal `parts_per_sheet`.
2. Keep end-piece BOM quantity sourced from row-level `bom_quantity`.
3. Remove `qty_per_sheet` from active end-piece validation and logic.
4. Keep save-time BOM drift audit aligned with the new quantity rule.
5. Clean up local released BOMs that were generated with `no_of_strips`.

## Non-Goals

1. No compatibility logic for older released BOMs created with strip-count quantity.
2. No change to row-level end-piece BOM quantity behavior.
3. No change to raw-material quantity, process scrap quantity, or scrap end-piece row generation.
4. No broader rework of the shearing workflow or release lifecycle.

## Current Behavior

Current live behavior on `bench15 / development.localhost` confirms the mismatch:

- Layout `001`
  - `no_of_strips = 11`
  - `parts_per_sheet = 77`
  - `generated_bom = BOM-FG01SHR-001`
  - layout reference row `finished_parts[0].bom_quantity = 11`
- BOM `BOM-FG01SHR-001`
  - `item = FG01SHR`
  - `quantity = 11`

That behavior matches the current code path in `sheet_cutting_layout/services/bom_service.py`,
where main BOM quantity is derived from `no_of_strips`.

## Approved Decisions

1. Main BOM quantity will use `parts_per_sheet`.
2. This change applies only to the parent finished-part BOM created during `MR Release`.
3. End-piece BOM quantity continues to use row-level `bom_quantity`.
4. `qty_per_sheet` is not required because every end-piece row represents one end piece per sheet.
5. Existing local released BOMs and linked layout reference rows should be regenerated or corrected
   locally after the code change.

## Business Rules

## Main BOM

For the parent finished-part BOM:

- `item = finished_part_code`
- `quantity = parts_per_sheet`
- raw material quantity remains the full sheet weight in Kg
- process scrap remains `scrap_weight_per_part_kg * parts_per_sheet`
- scrap end-piece rows continue to come from end pieces marked `Scrap`

## End-Piece Rows

Each end-piece row represents:

- one end piece per sheet
- one row-level `weight_kg`
- one disposition (`Reuse` or `Scrap`)

If a layout has multiple identical end pieces per sheet, they must be represented as separate rows.
This cutover does not support one row standing in for multiple end pieces through `qty_per_sheet`.

Therefore:

- `qty_per_sheet` is not required input
- end-piece generation and validation should not depend on it
- any remaining local values in that field are ignored as dead data unless the field is removed in a
  later cleanup

Weight semantics are explicit after this cutover:

- `weight_kg` is the total end-piece weight for that row, per sheet
- no server or client path should derive end-piece weight through `single_weight * qty_per_sheet`
- stale payloads or rows that still carry `qty_per_sheet` must not affect weight, scrap, or
  consumption calculations

## End-Piece BOMs

End-piece BOM behavior stays unchanged:

- quantity comes from row-level `bom_quantity`
- scrap quantity comes from row-level `bom_scrap_quantity_kg`

## Implementation Boundaries

## BOM Quantity Logic

Update `sheet_cutting_layout/services/bom_service.py` so the main BOM quantity helper returns
`parts_per_sheet` for the parent BOM instead of `no_of_strips`.

This must also update:

- any helper that computes expected BOM consumption from the layout
- any read-only finished-part reference-row projection that mirrors BOM quantity back to the layout

## Validation and Audit

Update save-time audit logic in `sheet_cutting_layout/services/validators.py` so:

- expected BOM quantity = `parts_per_sheet`
- released BOMs created under the new rule pass audit
- BOMs that still carry `no_of_strips` quantity fail until locally corrected

## End-Piece Simplification

Remove `qty_per_sheet` from active server-side requirements and behavior:

- no required validation for the field
- no consumption or BOM logic should multiply through it
- tests should stop treating it as meaningful input

Scope for this change:

- keep the field out of active business logic immediately
- this change does include narrow DocType metadata cleanup for `qty_per_sheet`
- the field should be hidden from normal UI use
- the field must not be editable or required in active form flow
- if the field remains present in payloads temporarily, it is informational dead data and must be
  ignored by server and client calculations
- field removal from DocType metadata can be handled later as a separate cleanup if desired

Enforcement boundaries are explicit:

- DocType metadata: field becomes non-required and hidden from active form flow
- client script: no calculation, validation, or conditional UI behavior may depend on `qty_per_sheet`
- server validation/services: no formula, validation, consumption, or BOM logic may depend on
  `qty_per_sheet`
- pre-release legacy layouts: if any end-piece row has `qty_per_sheet > 1`, save/release must be
  blocked until the user or developer splits that multiplicity into duplicate rows

## Local Cleanup

Affected released records for one-time local cleanup are explicitly:

1. released `Sheet Cutting Layout` records with a non-empty parent `generated_bom`
2. where the linked BOM item matches the layout `finished_part_code`
3. and the linked BOM quantity equals legacy strip-count quantity instead of `parts_per_sheet`

Cleanup steps:

1. inspect affected released layouts and their parent `generated_bom`
2. directly correct the linked parent generated BOM quantity from legacy strip-count quantity to
   `parts_per_sheet`
3. resynchronize linked `finished_parts` projection rows from the corrected BOM data
4. confirm the linked layout reference rows reflect the corrected quantity
5. confirm the updated layout/BOM pair passes the new save-time audit invariant

For the concrete local example:

- layout `001` should keep `parts_per_sheet = 77`
- `BOM-FG01SHR-001` should end up with `quantity = 77`
- layout `finished_parts[0].bom_quantity` should end up as `77`

Allowed remediation path for this under-development app:

- direct local database cleanup is acceptable
- no compatibility code or migration patch is required
- do not rely on rerunning `MR Release` for an already released layout
- do not introduce manual end-user BOM editing as the supported correction path

Supported cleanup mechanism for rollout planning:

- use a developer-run local cleanup step to update the released BOM quantity to `parts_per_sheet`
- then run the same BOM-backed projection synchronization logic used by release flow so
  `finished_parts` rows are rebuilt from the corrected BOM
- this cleanup can be implemented as a one-off developer helper or bench-executed local script; it
  is not an end-user workflow

The cleanup source of truth remains:

- first correct the released BOM quantity and any dependent BOM-backed values
- then resynchronize the layout `finished_parts` reference rows from the corrected BOM
- do not treat `finished_parts` rows as authoritative independent business state

Rollout ordering is explicit:

1. ship the code change
2. immediately run the one-time local cleanup on existing released layouts/BOMs
3. only after cleanup is complete should released layouts be considered safe to save under the new
   audit rule

Ownership:

- the developer performing this rollout owns the local cleanup on bench15 for existing released test
  or development data

## Testing Strategy

Update behavior-focused tests to assert:

1. main BOM quantity = `parts_per_sheet`
2. read-only `finished_parts.bom_quantity` mirrors `parts_per_sheet`
3. save-time audit rejects BOM quantity drift against `parts_per_sheet`
4. end-piece BOM quantity still comes from row-level `bom_quantity`
5. `qty_per_sheet` is not required for end-piece validation
6. stale `qty_per_sheet` values in client/API payloads are ignored by weight and consumption logic
7. a released BOM created with the old strip-count quantity fails the updated audit until local
   cleanup corrects it
8. the corrected local-released shape passes the updated audit once quantity and reference rows
   match `parts_per_sheet`
9. a fresh `MR Release` creates the main BOM with `quantity = parts_per_sheet`

Cleanup verification expectations:

- automated tests should cover old-shape audit failure and corrected-shape audit success using test
  fixtures or direct in-test document setup
- the one-time local bench cleanup itself can remain a manual verification step, but the plan must
  include explicit bench commands or scripted steps for reproducing and checking the corrected state

Remove or update tests that currently assert:

- main BOM quantity equals `no_of_strips`
- read-only finished-part BOM quantity equals `no_of_strips`
- `qty_per_sheet` is required or behaviorally significant

## Trade-Offs

### Chosen

- Hard cutover to `parts_per_sheet` for main BOM quantity
- End-piece model simplification by treating one row as one end piece

### Benefits

- BOM quantity matches finished-part output rather than strip count
- model is simpler and more explicit
- save-time audit and UI reference rows align with the intended business rule

### Costs

- local released BOMs generated under the old rule must be corrected
- tests and any read-only projections tied to the old quantity rule must be updated
