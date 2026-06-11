# End Piece Reuse BOM Weight Fields Design

## Goal

Reuse end pieces need the same weight split model as the main sheet cutting BOM. When a reuse
end piece is converted into an end-piece BOM, the user enters the net usable weight per part, and
the system derives gross weight, scrap weight, and BOM scrap quantity from the existing end-piece
weight and BOM quantity.

## Current Behavior

Reuse rows currently capture `used_for_finished_part`, `bom_quantity`, and a manually entered
`bom_scrap_quantity_kg`. End-piece BOM generation consumes the full `weight_kg` as the raw-material
item and uses the layout-level process scrap item when `bom_scrap_quantity_kg` is positive.

That makes the reuse BOM less auditable than the main BOM because users cannot see the per-part
gross/net/scrap split on the end-piece row.

## Proposed Behavior

For `Disposition = Reuse`, add these row fields:

- `net_weight_per_part_kg`: required user input.
- `gross_weight_per_part_kg`: read-only, derived as `weight_kg / bom_quantity`.
- `scrap_weight_per_part_kg`: read-only, derived as `gross_weight_per_part_kg - net_weight_per_part_kg`.
- `scrap_item`: visible for reuse rows; required when derived scrap is positive.

Change existing `bom_scrap_quantity_kg` to read-only for reuse rows and derive it as:

```text
bom_scrap_quantity_kg = scrap_weight_per_part_kg * bom_quantity
```

End-piece BOM generation uses the row-level `scrap_item` for reuse BOM scrap rows. It no longer
uses the layout-level `process_scrap_item` for reuse end-piece BOM scrap.

The end-piece BOM builder reuses the main BOM creation logic where the calculations are the same:
derive raw-material consumption from gross weight, derive finished-good output from net weight, and
derive scrap from the row-level scrap weight. The key difference is the quantity source: main BOM
quantity comes from the layout's `parts_per_sheet`, while reuse end-piece BOM quantity comes from the
user-entered row `bom_quantity`.

## Validation Rules

For reuse rows:

- `used_for_finished_part` remains required.
- `bom_quantity` must be greater than zero.
- `net_weight_per_part_kg` is required and must be non-negative.
- Derived `gross_weight_per_part_kg` must be positive.
- Derived `scrap_weight_per_part_kg` must be non-negative.
- If derived `bom_scrap_quantity_kg` is positive, `scrap_item` is required.
- `scrap_item` must not equal the generated end-piece item code or the used-for finished part.

For scrap-disposition rows, existing scrap behavior remains unchanged.

## Data Flow

1. Server-side validation recalculates end-piece `weight_kg` from dimensions.
2. For reuse rows, validation derives gross, scrap, and BOM scrap quantities.
3. Validation rejects inconsistent weights before release or end-piece BOM generation.
4. Client-side scripts mirror the same formulas for immediate form feedback.
5. End-piece BOM generation reads the already-derived row values and uses row `scrap_item` for BOM
   scrap rows.
6. End-piece BOM generation uses the same calculation structure as main BOM generation, with
   row `bom_quantity` replacing main-layout `parts_per_sheet`.

## Testing

Add bench-native tests for:

- Reuse row derives gross, scrap, and BOM scrap quantity from weight, BOM quantity, and net weight.
- Reuse row rejects missing net weight.
- Reuse row rejects net weight greater than gross weight.
- Reuse row requires row-level scrap item when derived scrap is positive.
- End-piece BOM generation uses row-level scrap item in the BOM scrap row.
- End-piece BOM generation matches the main BOM raw/net/scrap calculation structure while using the
  user-entered row `bom_quantity`.
- Existing scrap-disposition behavior stays unchanged.

## Trade-offs

This removes manual `bom_scrap_quantity_kg` entry for reuse rows. The trade-off is intentional:
derived values prevent inconsistent BOMs and keep reuse end-piece BOMs aligned with the main BOM
calculation model. Users lose override flexibility, but the generated BOM becomes easier to audit
and safer to validate.
