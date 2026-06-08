# App-Created Item UOM and Valuation Design

## Context

The sheet cutting layout app creates derived Items during release and end-piece BOM generation. Generated end-piece Items are now stocked in `Kg` so their BOM rows can consume fractional weights without triggering ERPNext's whole-number validation for `Nos`.

New app-created Items should also carry the reciprocal alternate UOM needed by shop-floor and inventory users:

- Items stocked in `Kg` should also have `Nos`.
- Items stocked in `Nos` should also have `Kg`.

Generated end-piece Items must also inherit valuation from the raw material sheet because the end piece is physically cut from that sheet.

## Scope

This change applies only to Items created by this app going forward.

It does not backfill or mutate existing Items, and it does not change unrelated ERPNext Item master data.

## Behavior

When the app creates an Item with `stock_uom = "Kg"`:

- Add `Kg` with conversion factor `1`.
- Add alternate `Nos` using the specific derived piece weight.
- For generated end-piece Items, the `Nos` conversion factor is `row.weight_kg`.

When the app creates an Item with `stock_uom = "Nos"`:

- Add `Nos` with conversion factor `1`.
- Add alternate `Kg` using the reciprocal of the specific derived piece weight.
- The `Kg` conversion factor is `1 / row.weight_kg`.

Generated end-piece BOM rows continue to consume the generated end-piece Item in `Kg`, with `stock_uom = "Kg"`, `stock_qty = qty`, and `conversion_factor = 1`.

Generated end-piece Items copy these values from their source records:

- `item_group` from `layout.raw_material_item`.
- `valuation_rate` from `layout.raw_material_item`.
- `gst_hsn_code` from `row.used_for_finished_part`.

Because the generated end-piece Item is stocked in `Kg`, copying the raw material valuation rate as-is means the generated Item is valued per Kg. The app does not calculate or store a separate per-piece valuation rate.

## Trade-Offs

Copying raw material valuation rate keeps valuation simple and consistent with the stock UOM. A calculated per-piece cost can still be understood as:

```text
piece_value = raw_material_valuation_rate_per_kg * end_piece_weight_kg
```

The app should not store that piece value as `valuation_rate` while the Item is stocked in `Kg`, because ERPNext would treat it as a per-Kg rate and overvalue inventory.

Adding reciprocal alternate UOM rows only to app-created Items avoids broad master-data edits and removes the need for a migration.

## Testing

Add bench-native behavior tests for generated end-piece Item creation:

- A generated `Kg` end-piece Item includes `Kg` base UOM and alternate `Nos`.
- The alternate `Nos` conversion factor is derived from the row weight.
- The generated Item copies `valuation_rate` from `layout.raw_material_item`.
- Existing BOM row behavior remains in `Kg`, including fractional quantities such as `2.814`.

Avoid cosmetic metadata-only tests.
