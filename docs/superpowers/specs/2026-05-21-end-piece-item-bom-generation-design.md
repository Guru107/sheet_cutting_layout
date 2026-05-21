# End Piece Item and BOM Generation Design

Date: 2026-05-21  
Status: Ready for user review  
Scope: Sheet Cutting Layout end-piece reuse flow after MR Release

## 1. Problem and Goal

Reusable end pieces are currently entered as fixed Item links. That is not the right model because
the end-piece Item should be derived from the raw material and end-piece dimensions, then reused if
the same Item already exists.

Goals:

1. Stop asking users to select an end-piece Item manually.
2. Suggest a deterministic end-piece Item code from raw material item code, thickness, width, and
   length.
3. Let users edit the suggested end-piece Item code before creating end-piece BOMs.
4. Keep MR Release focused on releasing the layout and creating the shearing BOM.
5. Add a separate `Generate End Piece BOMs` action for reusable end pieces.
6. Track whether end-piece BOMs are not required, pending, or generated.
7. Add a preview action so users can inspect what Items and BOMs will be created before creating
   ERPNext master data.

## 2. Chosen Approach

Use a separate post-release action: `Generate End Piece BOMs`.

MR Release will continue to create the ERPNext shearing BOM for the sheet cutting layout. If the
layout has reusable end pieces without generated BOM links, the layout will show that end-piece BOM
generation is pending. Users can preview and then generate those Items and BOMs as a deliberate
follow-up step.

Trade-off: this allows MR Release to complete even when reuse BOMs have not yet been created, but it
also means a Released layout can be temporarily incomplete. The pending status and preview action
make that state visible and manageable.

## 3. Alternatives Considered

### Option A: Create End-Piece Items and BOMs During MR Release

Pros:

1. One workflow action creates all related records.
2. Released layouts are complete immediately.

Cons:

1. MR Release does more work and has more failure points.
2. Users cannot inspect or adjust generated end-piece Item codes before master data is created.

### Option B: Create End-Piece Items During Save

Pros:

1. Users can see generated Item links before release.
2. Later release/generation steps become simpler.

Cons:

1. Draft saves create ERPNext master data before approval.
2. Cleanup is harder when draft layouts are abandoned or edited.

### Option C: Separate Generate End Piece BOMs Action (Selected)

Pros:

1. Release remains simpler and focused on shearing BOM creation.
2. Users can preview generated records before creation.
3. End-piece Item code can stay editable until generation.

Cons:

1. Adds a post-release operational step.
2. Requires a clear parent status so pending BOM generation is not missed.

## 4. Data Model

### 4.1 `Layout End Piece`

Remove:

1. `end_piece_item`

Keep:

1. `width_mm`
2. `length_mm`
3. `weight_kg`
4. `qty_per_sheet`
5. `disposition`
6. `used_for_finished_part`

Add:

1. `end_piece_item_code` (Data)
   - Auto-suggested from raw material and dimensions.
   - Editable until an end-piece Item or BOM has been generated for the row.
2. `generated_end_piece_item` (Link Item, read-only)
   - Set when the Item exists or is created during generation.
3. `bom_quantity` (Float)
   - User-entered BOM quantity for `used_for_finished_part`.
   - Required when `disposition = Reuse`.
4. `bom_scrap_quantity_kg` (Float)
   - User-entered scrap output quantity for the generated reuse BOM.
   - Required when `disposition = Reuse`.
   - `0` is valid when the reuse BOM has no scrap output.
5. `generated_end_piece_bom` (Link BOM, read-only)
   - Set after the reuse BOM is created or was already linked on the row.
6. `scrap_item` (Link Item)
   - Required when `disposition = Scrap`.
   - Used in the shearing BOM scrap table for the end-piece scrap output.

### 4.2 `Sheet Cutting Layout`

Add:

1. `end_piece_bom_status` (Select, read-only)
   - `Not Required`
   - `Pending`
   - `Generated`

Status rules:

1. `Not Required`: no end-piece rows with `disposition = Reuse`.
2. `Pending`: at least one reusable end-piece row lacks `generated_end_piece_bom`.
3. `Generated`: all reusable end-piece rows have `generated_end_piece_bom`.

## 5. Item Code Rules

Default generated end-piece Item code:

```text
<raw_material_item>-EP-<thickness>x<width>x<length>
```

Example:

```text
RM001-EP-1.6x1250x179
```

Rules:

1. The grade/source prefix comes directly from `raw_material_item` item code.
2. Thickness comes from the parent sheet thickness.
3. Width and length come from the end-piece row.
4. If the Item code already exists, reuse the existing Item.
5. If the Item code does not exist, create a new ERPNext Item.
6. If the user edits `end_piece_item_code`, generation uses the edited value exactly.
7. After `generated_end_piece_item` or `generated_end_piece_bom` is set, lock
   `end_piece_item_code`.
8. Numeric segments use the displayed document values without trailing `.0` for whole numbers.
   Example: `1.6x1250x179`, not `1.600000x1250.0x179.0`.

Trade-off: a deterministic code keeps item reuse simple and avoids duplicate Items for the same raw
material/dimensions. It relies on users choosing a meaningful override when they need a different
code for business reasons.

## 6. Weight Rules

End-piece `weight_kg` is stored as weight per sheet, not per part.

Calculation:

```text
single_end_piece_weight_kg = thickness_mm * width_mm * length_mm * steel_density / 1_000_000
weight_kg = single_end_piece_weight_kg * qty_per_sheet
```

`steel_density` is the existing app constant `STEEL_DENSITY_G_PER_CM3 = 7.86`, in g/cm3.

The same stored `weight_kg` is used:

1. In sheet consumption tracking.
2. As the raw material quantity in the generated reuse BOM.
3. As the scrap quantity basis only when users explicitly enter `bom_scrap_quantity_kg`.

## 7. Preview Action

Add `Preview End Piece Items`.

Availability:

1. Raw material item is set.
2. Sheet thickness is set.
3. At least one end-piece row has `disposition = Reuse`.

The preview must not create or update records.

Preview output per reusable row:

1. End-piece row number.
2. Current `end_piece_item_code`.
3. Suggested Item code.
4. Item status: `Exists` or `Will be created`.
5. `used_for_finished_part`.
6. `bom_quantity`.
7. Raw material quantity in kg (`weight_kg`).
8. `bom_scrap_quantity_kg`.
9. BOM status: `Already linked` or `Will be created`.

Preview does not search for reusable unlinked BOMs. The generated BOM is considered complete only
when the end-piece row has `generated_end_piece_bom`.

Trade-off: preview adds a small server method and dialog, but it prevents surprise Item/BOM creation.

## 8. Generate End Piece BOMs Action

Add `Generate End Piece BOMs`.

Availability:

1. Layout is Released.
2. At least one reusable end-piece row is pending.

For each pending reusable row:

1. Validate required fields:
   - `end_piece_item_code`
   - `used_for_finished_part`
   - `bom_quantity`
   - `bom_scrap_quantity_kg`
   - `weight_kg`
2. Reuse existing Item if `end_piece_item_code` exists.
3. Otherwise create the Item using `end_piece_item_code`.
4. Create ERPNext native BOM for `used_for_finished_part`.
5. Set BOM quantity to user-entered `bom_quantity`.
6. Add raw material row:
   - Item: generated end-piece Item
   - Qty: `weight_kg`
   - UOM: `Kg`
7. Add scrap row when `bom_scrap_quantity_kg > 0`:
   - Item: process scrap item from the parent layout
   - Qty: `bom_scrap_quantity_kg`
   - UOM: `Kg`
8. Link the generated Item and BOM back to the end-piece row.
9. Recalculate parent `end_piece_bom_status`.

The action is idempotent at the row-link level: rows with `generated_end_piece_bom` are skipped.
It does not search for or reuse unlinked BOMs because matching by item, generated end-piece raw
material, quantities, and scrap rows can be ambiguous.

### 8.1 Generated Item Fields

When the generated end-piece Item does not exist, create it with:

1. `item_code`: `end_piece_item_code`
2. `item_name`: `end_piece_item_code`
3. `item_group`: copied from `raw_material_item`
4. `stock_uom`: `Kg`
5. `is_stock_item`: `1`
6. disabled: `0`

Do not copy valuation rate, opening stock, default warehouses, taxes, or supplier data from the raw
material Item. Those remain ERPNext master-data concerns outside this action.

Trade-off: copying only the item group keeps generated Items classified consistently with the raw
material while avoiding accidental duplication of commercial or inventory defaults.

## 9. Shearing BOM Behavior

The shearing BOM remains generated during MR Release.

For end pieces:

1. `Scrap` disposition adds a shearing BOM scrap row using the row-level `scrap_item`.
   - Qty: end-piece `weight_kg`
   - UOM: `Kg`
2. `Reuse` disposition does not create a shearing BOM scrap row for the reusable end piece.
3. Reusable end-piece consumption is accounted through the separate generated end-piece Item and BOM.

Trade-off: this keeps the shearing BOM tied to cutting the sheet into strips, while the reuse BOM
models how the generated end-piece Item is later consumed.

## 10. Validation and Error Handling

Server-side validation:

1. Do not require `end_piece_item`.
2. Require dimensions and quantity for every end-piece row.
3. For `Reuse`, require:
   - `used_for_finished_part`
   - `end_piece_item_code`
   - positive `bom_quantity`
   - non-negative `bom_scrap_quantity_kg`
4. If any reuse row has `bom_scrap_quantity_kg > 0`, require parent `process_scrap_item`.
5. For `Scrap`, require `scrap_item`.
6. Prevent editing `end_piece_item_code` after generated links exist.
7. Do not allow `Generate End Piece BOMs` before release.
8. Throw clear row-specific validation errors for missing reuse data.

Client-side behavior:

1. Auto-suggest `end_piece_item_code` when raw material, thickness, width, or length changes.
2. Keep the field editable before generation.
3. Show preview and generation buttons only when relevant.
4. Refresh generated links and parent status after generation.

## 11. Testing

Unit tests:

1. End-piece weight calculation multiplies by `qty_per_sheet`.
2. Sheet consumption uses end-piece `weight_kg` directly.
3. Validation no longer requires `end_piece_item`.
4. Reuse rows require `used_for_finished_part`, `end_piece_item_code`, `bom_quantity`, and
   `bom_scrap_quantity_kg`.
5. Reuse rows with positive `bom_scrap_quantity_kg` require parent `process_scrap_item`.
6. Scrap rows require `scrap_item`.
7. Generated Item code is deterministic and based on raw material item code.
8. Preview reports existing versus missing Items without creating records.
9. Preview reports BOM state as linked or will-create without searching for unlinked BOMs.
10. Generation reuses an existing end-piece Item.
11. Generation creates a missing end-piece Item with raw-material item group and `Kg` stock UOM.
12. Generation creates a BOM with user-entered BOM quantity, raw material qty equal to end-piece
   `weight_kg`, and scrap qty equal to user-entered scrap quantity.
13. Generation skips rows that already have `generated_end_piece_bom`.
14. Shearing BOM uses row-level `scrap_item` for scrap-disposition end pieces.

Frappe/bench tests:

1. DocType schema contains the new fields and removed field.
2. Released layout with reusable end pieces shows `Pending`.
3. Running `Generate End Piece BOMs` updates child generated links and parent status to `Generated`.

## 12. Rollout Notes

This app is under development, so no compatibility fallback is needed. Existing local metadata and
test fixtures can be migrated directly through DocType JSON changes and `bench migrate`.
