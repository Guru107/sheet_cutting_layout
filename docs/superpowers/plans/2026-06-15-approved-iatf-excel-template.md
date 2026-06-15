# Approved IATF Excel Template Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Sheet Cutting Layout Excel download use the approved `Shearing Template.xlsx` visual format and populate it as a static snapshot from system data.

**Architecture:** Keep the existing exporter boundary. Replace the placeholder workbook with the approved one, update `build_cell_map()` to write approved-template cells, enrich `_export_layout_dict()` with the few missing system values, and keep multi-sheet export by cloning the approved source sheet per layout.

**Tech Stack:** Frappe/ERPNext app, openpyxl 3.1.5 from bench envs, bench-native Frappe tests, pre-commit.

---

## File Structure

- Modify: `sheet_cutting_layout/templates/iatf/sheet_cutting_layout.xlsx`
  - Replace the placeholder workbook with `/root/.codex/attachments/444747d8-5866-4879-823c-af0ed4cbbae8/Shearing Template.xlsx`.
- Delete: `sheet_cutting_layout/templates/iatf/build_blank_template.py`
  - The generator recreates the wrong template and should not exist.
- Modify: `sheet_cutting_layout/services/export_service.py`
  - Keep `build_cell_map()` as the single cell-coordinate map.
  - Keep `build_multi_sheet_workbook()` as the workbook builder.
  - Copy approved page setup when cloning template worksheets.
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`
  - Add `layout_code`, raw material item name, and `weight_per_sheet_kg` to the existing export dict.
  - Add `used_for_finished_part` to end-piece dicts.
- Modify: `sheet_cutting_layout/tests/test_export_service.py`
  - Add approved-template shape tests.
  - Update cell-map/workbook expectations to approved-template values.
- Modify: `sheet_cutting_layout/tests/test_export_service_recursion.py`
  - Verify cloned sheets preserve approved template anchors.
- Modify: `sheet_cutting_layout/tests/test_sheet_cutting_layout_export.py`
  - Verify the controller download uses system values for `layout_code`, raw material item name, and prefixed labels.
- Modify: `sheet_cutting_layout/tests/test_download_sheet_cutting_layout_recursion.py`
  - Update recursive workbook cell expectations to prefixed part-number cells.

---

### Task 1: Replace Placeholder Template

**Files:**
- Modify: `sheet_cutting_layout/templates/iatf/sheet_cutting_layout.xlsx`
- Delete: `sheet_cutting_layout/templates/iatf/build_blank_template.py`
- Modify: `sheet_cutting_layout/tests/test_export_service.py`

- [ ] **Step 1: Add failing approved-template shape tests**

Append this class to `sheet_cutting_layout/tests/test_export_service.py` after `_base_layout()`:

```python
class TestApprovedIatfTemplate(SheetCuttingLayoutTestCase):
	def test_committed_template_matches_approved_visual_anchors(self) -> None:
		from openpyxl import load_workbook

		from sheet_cutting_layout.services.export_service import default_template_path

		workbook = load_workbook(default_template_path())
		self.assertEqual(len(workbook.worksheets), 1)
		worksheet = workbook.active

		self.assertEqual(worksheet.page_setup.orientation, "landscape")
		self.assertEqual(str(worksheet.page_setup.paperSize), "9")
		self.assertIn("A1:A4", {str(item) for item in worksheet.merged_cells.ranges})
		self.assertIn("E1:P4", {str(item) for item in worksheet.merged_cells.ranges})
		self.assertIn("G5:M5", {str(item) for item in worksheet.merged_cells.ranges})
		self.assertIn("N5:Q5", {str(item) for item in worksheet.merged_cells.ranges})
		self.assertIn("R38:U40", {str(item) for item in worksheet.merged_cells.ranges})
		self.assertEqual(worksheet["Q1"].value, "DOC. NO.:  FRM/PRD/15")
		self.assertEqual(worksheet["O7"].value, "BOM")
		self.assertEqual(worksheet["Q7"].value, "Gross Wt")
		self.assertEqual(worksheet["R7"].value, "F.g Wt")
		self.assertEqual(worksheet["S7"].value, "Scrap Wt")
		self.assertEqual(worksheet["R38"].value, "Released By    \nManagement Rep")
```

- [ ] **Step 2: Run the template-shape test to verify it fails**

Run from bench15:

```bash
cd /root/workspace/bench15
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service
```

Expected: fail in `test_committed_template_matches_approved_visual_anchors` because the current template has no approved merged ranges and no approved labels.

- [ ] **Step 3: Replace the workbook and delete the generator**

Run from the app repo:

```bash
cd /root/workspace/sheet_cutting_layout
cp "/root/.codex/attachments/444747d8-5866-4879-823c-af0ed4cbbae8/Shearing Template.xlsx" \
  sheet_cutting_layout/templates/iatf/sheet_cutting_layout.xlsx
rm sheet_cutting_layout/templates/iatf/build_blank_template.py
```

- [ ] **Step 4: Run the template-shape test to verify it passes**

Run:

```bash
cd /root/workspace/bench15
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service
```

Expected: `test_committed_template_matches_approved_visual_anchors` passes. Other export tests may still fail until later tasks update the cell map.

- [ ] **Step 5: Commit**

```bash
cd /root/workspace/sheet_cutting_layout
git add sheet_cutting_layout/templates/iatf/sheet_cutting_layout.xlsx \
  sheet_cutting_layout/templates/iatf/build_blank_template.py \
  sheet_cutting_layout/tests/test_export_service.py
git commit -m "feat: use approved IATF shearing template"
```

---

### Task 2: Update Cell Map For Snapshot Values

**Files:**
- Modify: `sheet_cutting_layout/services/export_service.py`
- Modify: `sheet_cutting_layout/tests/test_export_service.py`

- [ ] **Step 1: Update `_base_layout()` test fixture**

In `sheet_cutting_layout/tests/test_export_service.py`, update `_base_layout()` so it includes the missing snapshot keys:

```python
def _base_layout() -> dict[str, object]:
	return {
		"company": "Acme Press Parts",
		"layout_code": "SCL-EXPORT-LAYOUT-001",
		"part_name": "Brkt bumper top",
		"part_numbers": ["0102AAG06400SHR"],
		"is_lh_rh": False,
		"project": "PRJ-0001",
		"project_name": "Bumper Program",
		"raw_material_item_name": "HSLA-340",
		"sheet_thickness_mm": 2.0,
		"sheet_width_mm": 1000.0,
		"sheet_length_mm": 2000.0,
		"weight_per_sheet_kg": 31.44,
		"weight_of_strip_kg": 15.72,
		"strip_thickness_mm": 2.0,
		"strip_width_mm": 1000.0,
		"strip_length_mm": 1000.0,
		"parts_per_strip": 1,
		"no_of_strips": 2,
		"parts_per_sheet": 2,
		"gross_weight_per_part_kg": 15.72,
		"net_weight_per_part_kg": 15.52,
		"scrap_weight_per_part_kg": 0.2,
		"raw_material_weight_kg": 31.44,
		"end_pieces": [],
	}
```

- [ ] **Step 2: Update header and strip cell-map expectations**

Replace `TestBuildCellMapHeaderAndStrip.test_header_strip_and_per_part_cells` with:

```python
def test_header_strip_and_per_part_cells(self) -> None:
	from sheet_cutting_layout.services.export_service import build_cell_map

	cells = build_cell_map(_base_layout())

	self.assertEqual(cells["B1"], "Acme Press Parts")
	self.assertEqual(cells["A5"], "Sheet Cutting Layout No:- SCL-EXPORT-LAYOUT-001")
	self.assertEqual(cells["G5"], "Part Name:-Brkt bumper top")
	self.assertEqual(cells["N5"], "Part Number:-0102AAG06400SHR")
	self.assertEqual(cells["B6"], "PRJ-0001")
	self.assertEqual(cells["C6"], "Bumper Program")
	self.assertEqual(cells["J7"], "HSLA-340")
	self.assertEqual(cells["K8"], 2.0)
	self.assertEqual(cells["K9"], 2.0)
	self.assertEqual(cells["L9"], 1000.0)
	self.assertEqual(cells["M9"], 2000.0)
	self.assertEqual(cells["T6"], 31.44)
	self.assertEqual(cells["K10"], 15.72)
	self.assertEqual(cells["K11"], 2.0)
	self.assertEqual(cells["L11"], 1000.0)
	self.assertEqual(cells["M11"], 1000.0)
	self.assertEqual(cells["K12"], 1)
	self.assertEqual(cells["K13"], 2)
	self.assertEqual(cells["K14"], 2)
	self.assertEqual(cells["K15"], 15.72)
	self.assertEqual(cells["K16"], 15.52)
	self.assertEqual(cells["K17"], 0.2)
	self.assertEqual(cells["O8"], "0102AAG06400SHR")
	self.assertEqual(cells["Q8"], 15.72)
	self.assertEqual(cells["R8"], 15.52)
	self.assertEqual(cells["S8"], 0.2)
	self.assertEqual(cells["T8"], 2)
	self.assertAlmostEqual(float(cells["U8"]), 31.44, places=6)
```

- [ ] **Step 3: Update LH/RH label expectations**

In `TestBuildCellMapLhRhLabels`, update assertions:

```python
self.assertEqual(cells["G5"], "Part Name:-Brkt bumper top LH & RH")
self.assertEqual(cells["N5"], "Part Number:-0102AAG06400SHR_0102AAG06410SHR")
self.assertEqual(cells["O8"], "0102AAG06400SHR_0102AAG06410SHR")
```

In `test_single_part_number_is_not_joined`, update:

```python
self.assertEqual(cells["N5"], "Part Number:-0102AAG06400SHR")
self.assertEqual(cells["G5"], "Part Name:-Brkt bumper top")
```

In `test_blank_part_numbers_are_dropped_from_join`, update:

```python
self.assertEqual(cells["N5"], "Part Number:-0102AAG06400SHR")
```

- [ ] **Step 4: Update end-piece tests for approved-template columns**

Replace `test_end_piece_rows_populate_bom_table` with:

```python
def test_end_piece_rows_populate_bom_table(self) -> None:
	from sheet_cutting_layout.services.export_service import build_cell_map

	layout = _base_layout()
	layout["end_pieces"] = [
		{
			"end_piece_item_code": "EP-0102AAG06400-1",
			"used_for_finished_part": "0102AAG06400SHR",
			"width_mm": 200.0,
			"length_mm": 300.0,
			"weight_kg": 0.94,
			"gross_weight_per_part_kg": 0.47,
			"net_weight_per_part_kg": 0.4,
			"scrap_weight_per_part_kg": 0.07,
			"bom_quantity": 2,
		}
	]

	cells = build_cell_map(layout)

	self.assertEqual(cells["O9"], "EP-0102AAG06400-1")
	self.assertEqual(cells["Q9"], 0.47)
	self.assertEqual(cells["R9"], 0.4)
	self.assertEqual(cells["S9"], 0.07)
	self.assertEqual(cells["T9"], 2)
	self.assertAlmostEqual(float(cells["U9"]), 0.94, places=6)
	self.assertEqual(cells["K18"], 2.0)
	self.assertEqual(cells["L18"], 200.0)
	self.assertEqual(cells["M18"], 300.0)
	self.assertEqual(cells["J23"], "0102AAG06400SHR")
	self.assertEqual(cells["K24"], 2.0)
	self.assertEqual(cells["L24"], 200.0)
	self.assertEqual(cells["M24"], 300.0)
	self.assertEqual(cells["K25"], 2)
	self.assertEqual(cells["K26"], 0.47)
	self.assertEqual(cells["K27"], 0.4)
	self.assertEqual(cells["K28"], 0.07)
```

Update `test_only_first_three_end_pieces_render` so it proves the BOM table uses two end pieces and detail
blocks use three:

```python
layout["end_pieces"] = [
	{
		"end_piece_item_code": f"EP-{index}",
		"width_mm": 100 + index,
		"length_mm": 200 + index,
		"bom_quantity": index + 1,
	}
	for index in range(5)
]
cells = build_cell_map(layout)

self.assertEqual(cells["O9"], "EP-0")
self.assertEqual(cells["O10"], "EP-1")
self.assertNotIn("O11", cells)
self.assertEqual(cells["L18"], 100)
self.assertEqual(cells["S12"], 101)
self.assertEqual(cells["S22"], 102)
self.assertNotIn("EP-3", {str(value) for value in cells.values()})
```

- [ ] **Step 5: Add a workbook test for static snapshot values**

Append to `TestRenderWorkbookBytes`:

```python
def test_formula_cells_are_overwritten_with_system_snapshot_values(self) -> None:
	import io

	from openpyxl import load_workbook

	from sheet_cutting_layout.services.export_service import (
		default_template_path,
		render_workbook_bytes,
	)

	content = render_workbook_bytes(_base_layout(), default_template_path())
	worksheet = load_workbook(io.BytesIO(content), data_only=False).active

	self.assertEqual(worksheet["T6"].value, 31.44)
	self.assertEqual(worksheet["K10"].value, 15.72)
	self.assertEqual(worksheet["K14"].value, 2)
	self.assertEqual(worksheet["K15"].value, 15.72)
	self.assertEqual(worksheet["K17"].value, 0.2)
	self.assertFalse(str(worksheet["T6"].value).startswith("="))
	self.assertFalse(str(worksheet["K10"].value).startswith("="))
```

- [ ] **Step 6: Run tests to verify they fail**

Run:

```bash
cd /root/workspace/bench15
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service
```

Expected: failures show missing/prefixed cells such as `A5`, `J7`, `T6`, `Q8`, and formula overwrite assertions.

- [ ] **Step 7: Update `build_cell_map()` and helpers**

In `sheet_cutting_layout/services/export_service.py`, replace `build_cell_map()`, `_bom_table_cells()`, `_part_name_label()`, `_joined_part_numbers()`, and add `_end_piece_detail_cells()`:

```python
def build_cell_map(layout: Mapping[str, object]) -> dict[str, object]:
	"""Map a Sheet Cutting Layout dict to the approved FRM/PRD/15 worksheet cells."""
	cells: dict[str, object] = {
		"B1": _text(layout.get("company")),
		"A5": f"Sheet Cutting Layout No:- {_text(layout.get('layout_code')).strip()}".rstrip(),
		"G5": _part_name_label(layout),
		"N5": f"Part Number:-{_joined_part_numbers(layout)}",
		"B6": _text(layout.get("project")),
		"C6": _text(layout.get("project_name")),
		"J7": _text(layout.get("raw_material_item_name")),
		"K8": _num(layout.get("sheet_thickness_mm")),
		"K9": _num(layout.get("sheet_thickness_mm")),
		"L9": _num(layout.get("sheet_width_mm")),
		"M9": _num(layout.get("sheet_length_mm")),
		"T6": _num(layout.get("weight_per_sheet_kg")),
		"K10": _num(layout.get("weight_of_strip_kg")),
		"K11": _num(layout.get("strip_thickness_mm")),
		"L11": _num(layout.get("strip_width_mm")),
		"M11": _num(layout.get("strip_length_mm")),
		"K12": _num(layout.get("parts_per_strip")),
		"K13": _num(layout.get("no_of_strips")),
		"K14": _num(layout.get("parts_per_sheet")),
		"K15": _num(layout.get("gross_weight_per_part_kg")),
		"K16": _num(layout.get("net_weight_per_part_kg")),
		"K17": _num(layout.get("scrap_weight_per_part_kg")),
	}
	cells.update(_bom_table_cells(layout))
	cells.update(_end_piece_detail_cells(layout))
	return cells
```

Use this `_bom_table_cells()`:

```python
def _bom_table_cells(layout: Mapping[str, object]) -> dict[str, object]:
	cells: dict[str, object] = {}
	gross = layout.get("gross_weight_per_part_kg")
	nos = layout.get("parts_per_sheet")
	cells["O8"] = _joined_part_numbers(layout)
	cells["Q8"] = _num(gross)
	cells["R8"] = _num(layout.get("net_weight_per_part_kg"))
	cells["S8"] = _num(layout.get("scrap_weight_per_part_kg"))
	cells["T8"] = _num(nos)
	cells["U8"] = _num(_product(gross, nos))

	end_pieces: Sequence[Mapping[str, object]] = layout.get("end_pieces") or []
	for offset, end_piece in enumerate(end_pieces[:2]):
		row = 9 + offset
		ep_gross = end_piece.get("gross_weight_per_part_kg")
		ep_nos = end_piece.get("bom_quantity")
		cells[f"O{row}"] = _end_piece_label(end_piece)
		cells[f"Q{row}"] = _num(ep_gross)
		cells[f"R{row}"] = _num(end_piece.get("net_weight_per_part_kg"))
		cells[f"S{row}"] = _num(end_piece.get("scrap_weight_per_part_kg"))
		cells[f"T{row}"] = _num(ep_nos)
		cells[f"U{row}"] = _num(_product(ep_gross, ep_nos))
	return cells
```

Use this detail helper:

```python
def _end_piece_detail_cells(layout: Mapping[str, object]) -> dict[str, object]:
	cells: dict[str, object] = {
		"K18": "",
		"L18": "",
		"M18": "",
		"J23": "",
		"K24": "",
		"L24": "",
		"M24": "",
		"K25": "",
		"K26": "",
		"K27": "",
		"K28": "",
		"R12": "",
		"S12": "",
		"T12": "",
		"Q13": "",
		"R14": "",
		"S14": "",
		"T14": "",
		"R15": "",
		"R16": "",
		"R17": "",
		"R18": "",
		"R22": "",
		"S22": "",
		"T22": "",
		"Q23": "",
		"R24": "",
		"S24": "",
		"T24": "",
		"R25": "",
		"R26": "",
		"R27": "",
		"R28": "",
	}
	end_pieces: Sequence[Mapping[str, object]] = layout.get("end_pieces") or []
	blocks = [
		{
			"size": ("K18", "L18", "M18"),
			"used_for": "J23",
			"strip": ("K24", "L24", "M24"),
			"parts": "K25",
			"gross": "K26",
			"net": "K27",
			"scrap": "K28",
		},
		{
			"size": ("R12", "S12", "T12"),
			"used_for": "Q13",
			"strip": ("R14", "S14", "T14"),
			"parts": "R15",
			"gross": "R16",
			"net": "R17",
			"scrap": "R18",
		},
		{
			"size": ("R22", "S22", "T22"),
			"used_for": "Q23",
			"strip": ("R24", "S24", "T24"),
			"parts": "R25",
			"gross": "R26",
			"net": "R27",
			"scrap": "R28",
		},
	]
	for end_piece, block in zip(end_pieces, blocks, strict=False):
		thickness_cell, width_cell, length_cell = block["size"]
		strip_thickness_cell, strip_width_cell, strip_length_cell = block["strip"]
		thickness = _num(layout.get("sheet_thickness_mm"))
		width = _num(end_piece.get("width_mm"))
		length = _num(end_piece.get("length_mm"))
		cells[thickness_cell] = thickness
		cells[width_cell] = width
		cells[length_cell] = length
		cells[block["used_for"]] = _text(end_piece.get("used_for_finished_part"))
		cells[strip_thickness_cell] = thickness
		cells[strip_width_cell] = width
		cells[strip_length_cell] = length
		cells[block["parts"]] = _num(end_piece.get("bom_quantity"))
		cells[block["gross"]] = _num(end_piece.get("gross_weight_per_part_kg"))
		cells[block["net"]] = _num(end_piece.get("net_weight_per_part_kg"))
		cells[block["scrap"]] = _num(end_piece.get("scrap_weight_per_part_kg"))
	return cells
```

Use this `_part_name_label()`:

```python
def _part_name_label(layout: Mapping[str, object]) -> str:
	base = _text(layout.get("part_name")).strip()
	if not base:
		return "Part Name:"
	if layout.get("is_lh_rh"):
		return f"Part Name:-{base} LH & RH"
	return f"Part Name:-{base}"
```

- [ ] **Step 8: Run tests to verify they pass**

Run:

```bash
cd /root/workspace/bench15
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service
```

Expected: all `test_export_service` tests pass.

- [ ] **Step 9: Commit**

```bash
cd /root/workspace/sheet_cutting_layout
git add sheet_cutting_layout/services/export_service.py sheet_cutting_layout/tests/test_export_service.py
git commit -m "feat: map approved IATF template snapshot cells"
```

---

### Task 3: Enrich Controller Export Snapshot

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`
- Modify: `sheet_cutting_layout/tests/test_sheet_cutting_layout_export.py`

- [ ] **Step 1: Update integration fixture and expectations**

In `sheet_cutting_layout/tests/test_sheet_cutting_layout_export.py`, change the raw-material item creation in `_build_layout()`:

```python
raw_material = _ensure_item(f"SCLRM{suffix}", item_name=f"Raw Material {suffix}")
```

Then update `test_download_produces_workbook_with_expected_cells` assertions after loading the worksheet:

```python
self.assertTrue(str(worksheet["A5"].value).startswith("Sheet Cutting Layout No:- SCL-EXPORT-LAYOUT-"))
self.assertIn("Raw Material", str(worksheet["J7"].value))
self.assertEqual(worksheet["K9"].value, 2.0)
self.assertEqual(worksheet["L9"].value, 1000.0)
self.assertEqual(worksheet["M9"].value, 2000.0)
self.assertEqual(worksheet["T6"].value, 31.44)
self.assertEqual(worksheet["K14"].value, 2)
self.assertEqual(worksheet["K15"].value, 15.72)
self.assertEqual(worksheet["K16"].value, 15.52)
self.assertIn("SCL Export", str(worksheet["C6"].value))
self.assertIn("SCLPART", str(worksheet["N5"].value))
self.assertTrue(str(worksheet["N5"].value).startswith("Part Number:-"))
self.assertEqual(worksheet["G5"].value, "Part Name:-Brkt bumper top")
self.assertNotEqual(worksheet["G5"].value, worksheet["N5"].value)
self.assertEqual(worksheet["U8"].value, 31.44)
```

Update `test_download_uses_persisted_lh_rh_pairing`:

```python
self.assertEqual(worksheet["G5"].value, "Part Name:-Brkt bumper top LH & RH")
self.assertTrue(str(worksheet["N5"].value).startswith("Part Number:-SCLPART"))
self.assertIn("_SCLTWIN", str(worksheet["N5"].value))
self.assertTrue(str(worksheet["N5"].value).endswith("SHR"))
```

- [ ] **Step 2: Run integration test to verify it fails**

Run:

```bash
cd /root/workspace/bench15
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_sheet_cutting_layout_export
```

Expected: fail because `_export_layout_dict()` does not yet provide `layout_code`, `raw_material_item_name`, or `weight_per_sheet_kg`.

- [ ] **Step 3: Update `_export_layout_dict()`**

In `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`, add raw material item name before `return`:

```python
	raw_material_item = getattr(doc, "raw_material_item", None)
	raw_material_item_name = ""
	if raw_material_item:
		raw_material_item_name = frappe.get_cached_value("Item", raw_material_item, "item_name") or raw_material_item
```

Add these keys to the returned dict:

```python
			"layout_code": getattr(doc, "layout_code", None),
			"raw_material_item_name": raw_material_item_name,
			"weight_per_sheet_kg": getattr(doc, "weight_per_sheet_kg", None),
```

Update `_export_end_piece_dict()` to include `used_for_finished_part`:

```python
def _export_end_piece_dict(row: object) -> dict[str, object]:
	return {
		"end_piece_item_code": getattr(row, "end_piece_item_code", None),
		"used_for_finished_part": getattr(row, "used_for_finished_part", None),
		"width_mm": getattr(row, "width_mm", None),
		"length_mm": getattr(row, "length_mm", None),
		"weight_kg": getattr(row, "weight_kg", None),
		"gross_weight_per_part_kg": getattr(row, "gross_weight_per_part_kg", None),
		"net_weight_per_part_kg": getattr(row, "net_weight_per_part_kg", None),
		"scrap_weight_per_part_kg": getattr(row, "scrap_weight_per_part_kg", None),
		"bom_quantity": getattr(row, "bom_quantity", None),
	}
```

- [ ] **Step 4: Run integration test to verify it passes**

Run:

```bash
cd /root/workspace/bench15
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_sheet_cutting_layout_export
```

Expected: all `test_sheet_cutting_layout_export` tests pass.

- [ ] **Step 5: Commit**

```bash
cd /root/workspace/sheet_cutting_layout
git add sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py \
  sheet_cutting_layout/tests/test_sheet_cutting_layout_export.py
git commit -m "feat: export approved IATF workbook from system snapshot"
```

---

### Task 4: Preserve Approved Template When Cloning Sheets

**Files:**
- Modify: `sheet_cutting_layout/services/export_service.py`
- Modify: `sheet_cutting_layout/tests/test_export_service_recursion.py`
- Modify: `sheet_cutting_layout/tests/test_download_sheet_cutting_layout_recursion.py`

- [ ] **Step 1: Add clone-format assertions**

Append this test to `TestBuildMultiSheetWorkbook` in `sheet_cutting_layout/tests/test_export_service_recursion.py`:

```python
def test_each_cloned_sheet_keeps_approved_template_format(self) -> None:
	from sheet_cutting_layout.services.export_service import build_multi_sheet_workbook

	workbook = build_multi_sheet_workbook([_base_page("L1"), _base_page("L2")])

	for sheet_name in ("L1", "L2"):
		worksheet = workbook[sheet_name]
		merged = {str(item) for item in worksheet.merged_cells.ranges}
		self.assertIn("G5:M5", merged)
		self.assertIn("N5:Q5", merged)
		self.assertIn("R38:U40", merged)
		self.assertEqual(worksheet.page_setup.orientation, "landscape")
		self.assertEqual(worksheet["R38"].value, "Released By    \nManagement Rep")
```

- [ ] **Step 2: Update recursive download part-number expectations**

In `sheet_cutting_layout/tests/test_download_sheet_cutting_layout_recursion.py`, update part-number collection:

```python
part_numbers = {str(workbook[name]["N5"].value or "").replace("Part Number:-", "") for name in workbook.sheetnames}
```

Use that replacement in all tests that compare `N5` values to item codes.

- [ ] **Step 3: Run recursion tests to verify clone assertion fails if page setup is not copied**

Run:

```bash
cd /root/workspace/bench15
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service_recursion
```

Expected: the new clone-format test fails on the second sheet if page setup is not copied.

- [ ] **Step 4: Update `_clone_template_worksheet()`**

In `sheet_cutting_layout/services/export_service.py`, add page setup copies after creating `worksheet`:

```python
	worksheet.sheet_format = _copy(source_worksheet.sheet_format)
	worksheet.page_margins = _copy(source_worksheet.page_margins)
	worksheet.page_setup = _copy(source_worksheet.page_setup)
	worksheet.print_options = _copy(source_worksheet.print_options)
	worksheet.sheet_properties = _copy(source_worksheet.sheet_properties)
```

Keep existing style, merged range, column width, and row height copies.

- [ ] **Step 5: Run recursion tests to verify they pass**

Run:

```bash
cd /root/workspace/bench15
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service_recursion
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_download_sheet_cutting_layout_recursion
```

Expected: both modules pass.

- [ ] **Step 6: Commit**

```bash
cd /root/workspace/sheet_cutting_layout
git add sheet_cutting_layout/services/export_service.py \
  sheet_cutting_layout/tests/test_export_service_recursion.py \
  sheet_cutting_layout/tests/test_download_sheet_cutting_layout_recursion.py
git commit -m "fix: preserve approved IATF format in recursive export"
```

---

### Task 5: Final Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run export-focused tests in bench15**

```bash
cd /root/workspace/bench15
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service_recursion
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_sheet_cutting_layout_export
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_download_sheet_cutting_layout_recursion
```

Expected: all pass.

- [ ] **Step 2: Run export-focused tests in bench16**

```bash
cd /root/workspace/bench16
bench --site frappe16.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service
bench --site frappe16.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service_recursion
bench --site frappe16.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_sheet_cutting_layout_export
bench --site frappe16.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_download_sheet_cutting_layout_recursion
```

Expected: all pass.

- [ ] **Step 3: Run app tests in bench15 and bench16**

```bash
cd /root/workspace/bench15
bench --site development.localhost run-tests --app sheet_cutting_layout

cd /root/workspace/bench16
bench --site frappe16.localhost run-tests --app sheet_cutting_layout
```

Expected: all pass.

- [ ] **Step 4: Run pre-commit on all files**

```bash
cd /root/workspace/sheet_cutting_layout
pre-commit run --all-files
```

Expected: all hooks pass.

- [ ] **Step 5: Commit any final test-only adjustments**

Only run this if Step 1-4 produced necessary test expectation fixes:

```bash
cd /root/workspace/sheet_cutting_layout
git add sheet_cutting_layout/tests
git commit -m "test: update IATF export verification"
```

If there are no final changes, skip this commit.
