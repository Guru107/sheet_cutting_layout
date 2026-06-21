# End Piece Reuse Strip Consumption Design

## Context

Layout End Piece currently stores `width_mm`, `length_mm`, and derived `weight_kg` as the total
end-piece size and weight. Consumption tracking uses the full end-piece weight for every end-piece
row. That is wrong for reuse rows when only a smaller strip is cut from the end piece.

## Goal

Track the strip actually consumed from a reusable end piece without changing the meaning of the
existing end-piece dimensions and total weight.

## Data Model

Add these fields to `Layout End Piece`:

- `strip_width_mm` Float, shown for `Reuse`
- `strip_length_mm` Float, shown for `Reuse`
- `strip_weight_kg` Float, read-only, shown for `Reuse`

Keep existing fields unchanged:

- `width_mm` and `length_mm` remain the total end-piece dimensions.
- `weight_kg` remains the total end-piece weight.
- Layout `sheet_thickness_mm` remains the shared thickness source.

## Calculation Rules

For reuse rows:

1. If `strip_width_mm` is blank, default it from `width_mm`.
2. If `strip_length_mm` is blank, default it from `length_mm`.
3. Validate `strip_width_mm > 0` and `strip_length_mm > 0`.
4. Validate `strip_width_mm <= width_mm` and `strip_length_mm <= length_mm`.
5. Derive `strip_weight_kg` from layout thickness, strip width, and strip length.
6. Derive reuse `gross_weight_per_part_kg` from `strip_weight_kg / bom_quantity`.
7. Derive reuse `scrap_weight_per_part_kg` from gross minus net.
8. Derive reuse `bom_scrap_quantity_kg` from scrap weight times BOM quantity.

For scrap rows:

1. Do not require or use strip fields.
2. Continue using full `weight_kg` as the scrap quantity.

## Consumption Tracking

Main layout consumption should use:

- parent finished-part gross consumption as today
- `strip_weight_kg` for reuse end pieces
- `weight_kg` for scrap end pieces

This preserves the current `leftover_weight_kg` gate. If a reuse strip is smaller than the total end
piece, the unconsumed weight remains in `leftover_weight_kg` until another end-piece row accounts for
that leftover strip.

## BOM Behavior

Generated main BOMs should keep existing behavior for scrap rows and use full `weight_kg`.

Reuse end-piece BOM generation should use:

- raw-material quantity: `strip_weight_kg`
- scrap quantity: derived `bom_scrap_quantity_kg`

The total end-piece `weight_kg` remains available for item naming, dimensions, and audit context.

## Excel Export

The end-piece detail block should populate `Strip Size` cells from the reuse strip fields:

- Endpiece 1: K25 = thickness, L25 = `strip_width_mm`, M25 = `strip_length_mm`
- Subsequent end-piece blocks use the same existing block mapping.

End-piece size/detail cells continue to use `width_mm` and `length_mm`.

## Error Handling

Validation must block save/submit when a reuse row has:

- missing strip dimensions after defaulting
- strip width greater than end-piece width
- strip length greater than end-piece length
- non-positive strip weight
- positive derived BOM scrap with no `scrap_item`

## Testing

Add focused Frappe tests for:

1. Reuse strip fields default from end-piece dimensions.
2. Reuse strip dimensions cannot exceed end-piece dimensions.
3. Reuse gross, scrap, and BOM scrap derive from `strip_weight_kg`.
4. Consumption tracking uses `strip_weight_kg` for reuse and `weight_kg` for scrap.
5. Layout submission remains blocked until leftover consumption balances to zero.
6. Excel `Strip Size` cells use strip dimensions.
7. Generated reuse end-piece BOM uses `strip_weight_kg` as raw-material quantity.

## Trade-Offs

This adds one stored derived field, `strip_weight_kg`, instead of reusing `weight_kg`. The extra field
is worth it because it keeps total end-piece weight and consumed strip weight explicit. We are not
adding a separate leftover-row generator; users already model leftover material by adding another
end-piece row, and the existing `leftover_weight_kg` gate enforces that accounting.
