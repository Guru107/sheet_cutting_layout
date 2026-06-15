# Approved IATF Excel Template Export

## Goal

The Sheet Cutting Layout Excel download must match the approved IATF shearing template format exactly.
The attached `Shearing Template.xlsx` is the production visual template. The current generated placeholder
template is not acceptable for audit use.

## Decisions

- Use `Shearing Template.xlsx` as the single canonical workbook template at
  `sheet_cutting_layout/templates/iatf/sheet_cutting_layout.xlsx`.
- Keep the current recursive export model: one worksheet per exported layout, with parent first and child
  layouts after it.
- Clone the approved template sheet for each exported layout.
- Treat the export as a system snapshot. The app writes system values into the workbook, including cells
  that currently contain formulas in the sample template.
- Support the first three end pieces only. Additional end pieces are excluded from this export for now.
- Leave the signature block as template labels only.
- Remove the placeholder template generator because it can recreate the wrong visual format.

## Template Contract

The committed template must preserve the approved sheet's visual structure:

- one source worksheet
- the approved workbook's saved print/page setup
- merged-cell layout from the approved template
- row heights, column widths, borders, alignment, and signature-label blocks
- fixed labels such as `DOC. NO.: FRM/PRD/15`, `BOM`, `Gross Wt`, `F.g Wt`, `Scrap Wt`, and
  signature labels in rows 38-40

The workbook may contain example values while stored in the repository, but export code must overwrite all
mapped data cells for each generated layout.

## Data Mapping

The exporter builds a plain layout snapshot from the Sheet Cutting Layout document and related Item/Project
records, then writes it onto the cloned template sheet.

Required mappings:

- `A5`: `Sheet Cutting Layout No:- <layout_code>`
- `G5`: `Part Name:-<finished part item_name>`, using the existing LH/RH label behavior
- `N5`: `Part Number:-<finished_part_code>` or joined LH/RH part numbers
- `B6`: project code
- `C6`: project name
- `J7`: raw material `Item.item_name`
- `K8`: sheet thickness
- `K9`, `L9`, `M9`: sheet thickness, width, length
- `K10`: weight of strip
- `K11`, `L11`, `M11`: strip thickness, width, length
- `K12`: parts per strip
- `K13`: number of strips
- `K14`: parts per sheet
- `K15`: gross weight per part
- `K16`: net weight per part
- `K17`: scrap weight per part
- `O8:U10`: BOM snapshot rows for the finished part and up to two end-piece rows, using system quantities
  and weights
- End-piece detail blocks: fill only the first three end pieces supported by the template

Formula cells in the source template are not trusted as calculations during export. The exported workbook
must contain the current system values.

## Architecture

Keep the current boundary:

- `download_sheet_cutting_layout(name)` permission-checks the parent and child layouts, builds ordered
  layout pages, saves the workbook to `frappe.response`, and returns the binary download.
- `build_multi_sheet_workbook(pages)` opens the approved template, clones its worksheet per page, applies
  values, and returns an openpyxl workbook.
- `build_cell_map(layout)` remains the central value map, updated to the approved-template coordinates.

No new abstraction is needed. The existing dict snapshot is enough.

## Error Handling

- If the template file is missing or unreadable, the download should fail normally with the underlying
  exception so the bench logs show the real cause.
- If more than three end pieces exist, export only the first three. Do not fail the download.
- Missing optional values should produce blank cells.
- Required values already enforced by Sheet Cutting Layout validation should not get a second export-only
  validation layer.

## Tests

Add focused tests only:

- Template-shape test: load the committed `.xlsx` and assert the key visual anchors, including one sheet,
  page setup, representative merged ranges, and signature labels.
- Cell-map test: assert the approved-template cells receive system snapshot values, including `layout_code`
  in `A5` and raw material item name in `J7`.
- Workbook test: render a workbook and assert formula cells are overwritten with static system values.
- Existing download and recursive workbook tests should keep passing with updated approved-template
  expectations.

Final verification before implementation completion must run the relevant export tests and the app tests in
both bench15 and bench16.

## Out Of Scope

- PDF export
- visual diff tooling
- automatic support for more than three end pieces
- populating approval/signature names and dates
- creating an in-code openpyxl layout builder
