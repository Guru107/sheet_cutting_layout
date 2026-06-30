# Allow Alternative Item on Generated Objects Design

## Goal

Any object newly created or touched by Sheet Cutting Layout generation that must allow alternatives will have
`allow_alternative_item = 1`.

## Scope

Apply only during new generation flows. Do not backfill historical Items or BOMs.

Covered objects:

- Generated end-piece `Item` records.
- Generated main release `BOM` records.
- Generated end-piece `BOM` records.
- Raw-material `BOM Item` child rows added by Sheet Cutting Layout.
- Raw-material `Item` masters referenced by a newly generated SCL BOM.

Existing historical SCL records are unchanged unless their RM Item master is touched by a new generation.

## Design

Add one small helper that sets `allow_alternative_item = 1` only when a doc or child row supports that field.
Use it from both generated BOM paths and the generated end-piece Item path.

In `release_service._insert_frappe_bom`, set the flag on the BOM header before insert, on each raw-material
item row dict, and on the referenced RM Item master. In `end_piece_bom_service._create_end_piece_bom`, do the
same for the end-piece BOM header, its raw-material row, and the referenced Item. In
`end_piece_item_service.ensure_end_piece_item`, set the flag on newly created end-piece Items.

Use metadata/attribute checks for v15/v16 compatibility. If a DocType ever lacks the field, skip that target
instead of failing generation.

## Trade-offs

- Mutating RM Item masters is intentional because alternatives are required downstream.
- No migration patch keeps this narrow, but old records keep their old values.
- A tiny shared helper avoids duplicating field-support checks without adding a new abstraction layer.

## Testing

Before adding or changing tests, verify the live v15 and v16 schemas for `Item`, `BOM`, and `BOM Item`:

- Confirm the header field name for `Item` and `BOM`.
- Confirm the child-row field name for `BOM Item`.
- Confirm whether row dictionaries or document metadata expose those fields differently between versions.
- Base the helper and tests on the verified schema, not on assumed field names.

Add focused tests to assert:

- Generated end-piece Items have `allow_alternative_item = 1`.
- Main generated BOM headers and raw-material rows have `allow_alternative_item = 1`.
- End-piece generated BOM headers and raw-material rows have `allow_alternative_item = 1`.
- Referenced RM Item masters are set when generation runs.
- Field-support guards work with existing fake docs, covering v15/v16 style metadata differences.

Run focused release and end-piece BOM tests on bench15 and bench16, then `pre-commit`.
