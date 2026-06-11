# Sheet Cutting Layout BOM Reference and Versioning Design

## Summary

This design moves finished-part entry to parent-level Strip Layout fields and turns the
`finished_parts` child table into a hidden-until-generated, read-only BOM reference surface.
The Sheet Cutting Layout remains the only place where users can change shearing design inputs.
The generated ERPNext BOM becomes locked against manual edits, is continuously audited against
the layout on every save after generation, and follows layout-driven revisioning and supersede
behavior.

## Goals

1. Keep one finished-part input model per Sheet Cutting Layout.
1. Move editable finished-part data to parent fields in the Strip Layout section:
   - `finished_part_code`
   - `net_weight_per_part_kg`
   - derived `gross_weight_per_part_kg`
   - derived `scrap_weight_per_part_kg`
1. Keep `parts_per_sheet` derived from `parts_per_strip * no_of_strips`.
1. Keep sheet-consumption validation owned by the layout.
1. Keep exactly one main shearing BOM link on the layout via `generated_bom`.
1. Show `finished_parts` only after `generated_bom` exists and make it a read-only BOM-backed
   reference table.
1. Ensure any BOM derived from a Sheet Cutting Layout is not manually editable.
1. Audit the generated BOM against the layout on every save after BOM creation.
1. Keep old BOM versions unchanged when a new layout version is released.
1. Allow users to manually supersede a released Sheet Cutting Layout; superseding deactivates
   that layout's BOM.

## Non-Goals

1. No compatibility fallback for old `finished_parts` input behavior.
1. No dual-write model where child rows remain the authoritative design input.
1. No direct BOM editing workflow for shearing BOMs.
1. No automatic superseding of older released layouts when a new layout version is released.
1. No requirement that only one released layout per finished part or raw material exists at a
   time.

## Current Problems

1. The layout still treats `finished_parts` as the primary finished-part input surface even
   though the business model now expects only one finished part per layout.
1. The BOM link and BOM-derived display state are split across child-row logic instead of a
   single parent-level source of truth.
1. Generated shearing BOMs can drift from the layout after release unless users manually notice
   the mismatch.
1. Current revisioning expectations are not yet aligned with the rule that only the layout can
   drive a new BOM version.

## Approved Decisions

1. Keep only one editable finished-part model on the parent layout.
1. Store the main shearing BOM link on the parent as `generated_bom`.
1. Keep `finished_parts` as a persisted UI projection only; server-side business logic must not
   treat it as authoritative input.
1. Hide `finished_parts` until the main BOM exists.
1. Populate `finished_parts` from the generated BOM and show:
   - `Finished Part Code`
   - `BOM Quantity`
   - `Scrap Weight`
   - `Raw Material Weight`
1. Keep `gross_weight_per_part_kg` derived as:
   - `weight_of_strip_kg / parts_per_strip`
1. Keep `scrap_weight_per_part_kg` derived as:
   - `gross_weight_per_part_kg - net_weight_per_part_kg`
1. Keep total scrap in the BOM reference view inclusive of:
   - process scrap
   - scrap end-piece weight
1. Any BOM linked to a Sheet Cutting Layout is system-derived and not manually editable.
1. Save-time BOM audit compares all derived BOM fields, not only totals.
1. `New Version` creates a duplicated layout revision, clears approval history, and requires the
   full approval flow again.
1. Releasing a new layout revision creates a new BOM version without modifying older BOMs.
1. `Supersede` is the explicit action that deactivates the BOM linked to that layout.

## Data Model Changes

## `Sheet Cutting Layout` DocType

1. Add or keep the finished-part inputs on the parent doctype:
   - `finished_part_code` (`Link` to `Item`)
   - `net_weight_per_part_kg`
   - `gross_weight_per_part_kg` (read-only)
   - `scrap_weight_per_part_kg` (read-only)
1. Add or keep parent-level `generated_bom` (`Link` to `BOM`) as the single main shearing BOM
   reference.
1. Keep `parts_per_sheet`, `consumed_weight_kg`, `leftover_weight_kg`, and `consumption_status`
   on the parent layout.

## `Layout Finished Part` Child Table

1. Keep the child table as a presentation layer only.
1. Remove it from all authoritative calculation, validation, release, and versioning logic.
1. Make the table hidden until `generated_bom` is populated.
1. Make the table read-only once shown.
1. Reduce the effective columns to BOM-reference fields only:
   - `finished_part_item`
   - `bom_quantity`
   - `scrap_weight_kg`
   - `raw_material_weight_kg`
1. Do not allow user-driven row creation, editing, or deletion as part of normal workflow.

## Source-of-Truth Contract

1. Layout design input source:
   - parent strip-layout fields
   - end-piece rows
1. Released manufacturing source:
   - the `generated_bom` document
1. UI reference projection:
   - `finished_parts` child rows rebuilt or synchronized from the BOM
1. Server-side validations and release logic must never read the child table as the source of
   finished-part design input after this change.

## Formula and Calculation Rules

1. `weight_per_sheet_kg` remains derived from sheet dimensions, thickness, and steel density.
1. `weight_of_strip_kg` remains derived from strip dimensions, thickness, and steel density.
1. `gross_weight_per_part_kg = weight_of_strip_kg / parts_per_strip`
1. `parts_per_sheet = parts_per_strip * no_of_strips`
1. `scrap_weight_per_part_kg = gross_weight_per_part_kg - net_weight_per_part_kg`
1. Layout consumption remains:
   - total strip consumption
   - plus end-piece weights
   - balanced against one sheet weight with the existing tolerance rules

## Main BOM Generation Behavior

1. MR Release creates the main shearing BOM only from layout parent fields and end-piece rows.
1. BOM item code is `finished_part_code`.
1. For shearing BOMs (`SHR`), BOM quantity is `no_of_strips`.
1. Raw material row:
   - item code = `raw_material_item`
   - qty = full `weight_per_sheet_kg`
   - UOM = `Kg`
1. Scrap rows:
   - process scrap derived from `scrap_weight_per_part_kg * parts_per_sheet`
   - scrap end-piece rows derived from end pieces with `Disposition = Scrap`
1. `generated_bom` is written back to the layout after successful creation.
1. `finished_parts` is then synchronized from the generated BOM for display.

## BOM Reference Table Behavior

1. Before BOM generation:
   - `finished_parts` stays hidden.
1. After BOM generation:
   - `finished_parts` becomes visible and read-only.
1. Each displayed row is BOM-backed, not user-entered.
1. Displayed values:
   - `Finished Part Code`: BOM item
   - `BOM Quantity`: BOM quantity
   - `Scrap Weight`: total scrap weight from BOM scrap rows
   - `Raw Material Weight`: total weight from BOM raw material rows
1. The child table may be rebuilt or synchronized on load/save so the displayed data stays aligned
   with the linked BOM.

## Revision and Versioning Behavior

1. `New Version` on a released layout creates a duplicated new Sheet Cutting Layout revision.
1. The new revision carries forward:
   - parent finished-part inputs
   - sheet and strip dimensions
   - end-piece definitions
   - other ordinary layout design fields
1. The new revision does not carry forward:
   - `approval_snapshot`
   - `generated_bom`
   - BOM-backed `finished_parts` reference rows
   - an active released-state workflow outcome
1. The new revision starts the approval flow again from draft.
1. When the new revision reaches MR Release:
   - a new shearing BOM is created
   - the previous BOM remains unchanged
1. This layout-driven revision behavior is the supported equivalent of ERPNext BOM “New Version”
   for shearing BOMs.

## Supersede Behavior

1. Users may manually supersede any released Sheet Cutting Layout.
1. Supersede does not rewrite or version the BOM.
1. Supersede deactivates the main BOM linked in `generated_bom`.
1. Older released layouts and BOMs remain available until a user explicitly supersedes them.

## Edit Locking Rules

1. Any BOM linked to `sheet_cutting_layout` is treated as layout-derived.
1. Manual edits to a layout-derived BOM must fail with an explicit user-facing error directing the
   user to create a new Sheet Cutting Layout version instead.
1. The lock applies to:
   - header quantity changes
   - raw material row changes
   - scrap row changes
   - item changes
   - other derived manufacturing fields owned by the layout
1. App-controlled writes remain allowed for:
   - initial BOM creation at MR Release
   - explicit BOM deactivation on layout supersede
   - system-managed synchronization needed for the BOM reference view
1. ERPNext-native BOM revision/version actions for layout-derived BOMs must also be blocked and
   redirected to Sheet Cutting Layout `New Version`.

## Audit and Validation Rules

1. On every layout save, recompute all layout-derived fields first.
1. If `generated_bom` is empty, run only layout validation.
1. If `generated_bom` exists, run layout validation and a full BOM audit.

## Audit Contract for the Main BOM

1. Header checks:
   - BOM item equals `finished_part_code`
   - BOM quantity equals expected layout-derived quantity (`no_of_strips` for `SHR`)
   - `custom_operation == "Shearing"`
   - `sheet_cutting_layout == layout.name`
1. Raw material checks:
   - raw material item matches `raw_material_item`
   - raw material total qty matches `weight_per_sheet_kg`
   - UOM is `Kg`
1. Scrap checks:
   - process scrap matches `scrap_weight_per_part_kg * parts_per_sheet`
   - scrap end-piece rows match layout scrap end pieces
   - total BOM scrap equals the expected layout-derived total scrap
1. Consumption check:
   - BOM-accounted material must match one-sheet layout consumption
   - drift in any derived field fails the save

## Audit Failure Behavior

1. Save must fail when a generated BOM drifts from the layout.
1. Error messages must identify the category of drift, for example:
   - BOM quantity mismatch
   - finished part mismatch
   - raw material weight mismatch
   - scrap row mismatch
   - total consumption mismatch
1. Do not silently resync the BOM from save-time validation. Save-time audit is for drift
   detection, not hidden BOM rewriting.

## Error Handling

1. Missing `finished_part_code` fails validation.
1. Missing or non-positive `parts_per_strip` fails gross-weight derivation.
1. Negative derived `scrap_weight_per_part_kg` fails validation.
1. Missing `raw_material_item` fails release and BOM audit.
1. Missing `process_scrap_item` fails when positive process scrap must be represented.
1. Missing or invalid `generated_bom` link on a released layout fails audit.
1. Attempted manual edit of a layout-derived BOM fails with a user-facing instruction to use
   Sheet Cutting Layout `New Version`.

## Testing Strategy (Bench/Frappe Native Only)

1. Use only bench/Frappe native `unittest` style tests through:
   - `bench --site <site-name> run-tests --app sheet_cutting_layout`
1. Do not use pytest-based tests or source-string existence assertions for this feature.

## Required Behavioral Tests

1. Parent formula tests:
   - `gross_weight_per_part_kg` derives from `weight_of_strip_kg / parts_per_strip`
   - `scrap_weight_per_part_kg` derives from gross minus net
   - `parts_per_sheet` derives from `parts_per_strip * no_of_strips`
1. Consumption tests:
   - layout balances total sheet consumption with the configured tolerance
1. Release tests:
   - MR Release creates the shearing BOM from parent fields
   - `generated_bom` is populated on the layout
   - `finished_parts` reference rows reflect the generated BOM
1. Audit tests:
   - save passes when BOM matches layout
   - save fails when any derived BOM field drifts
   - save fails when total consumption drifts
1. BOM lock tests:
   - direct edits to layout-derived BOMs fail
   - app-controlled supersede deactivation remains allowed
1. Revision tests:
   - `New Version` copies layout design fields
   - `New Version` clears approval snapshot
   - releasing a new layout revision creates a new BOM while leaving the old BOM unchanged
1. Supersede tests:
   - superseding a released layout deactivates its linked BOM

## Implementation Units

1. Parent doctype schema and field layout
1. Child reference-table schema and visibility rules
1. Parent-driven validator formulas
1. Main BOM generation service
1. Layout revisioning service
1. BOM override and edit-lock enforcement
1. Save-time BOM audit service
1. Bench-native integration tests

## Trade-Offs

1. Keeping `finished_parts` as a persisted UI table, even though it is no longer authoritative,
   adds synchronization work. The trade-off is acceptable because it preserves a familiar Frappe
   table UI while keeping the true source of truth explicit.
1. Continuous audit on every save is stricter than release-only validation and may block saves
   sooner. The trade-off is intentional because BOM drift must be surfaced immediately.
1. Allowing multiple released layouts and BOMs to coexist gives flexibility for different raw
   materials, but “current” is no longer implied by most recent release alone. Users must use
   explicit supersede when they want a BOM deactivated.
