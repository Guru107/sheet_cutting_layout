# Phase 2 — IATF Excel Export Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
**Goal:** Produce the approved `FRM/PRD/15` IATF audit workbook (`.xlsx`) from a single Sheet Cutting Layout, downloadable from the form, with the cell map fully covered by a frappe-free pure function.
**Architecture:** A frappe-free `services/export_service.py` holds a pure `build_cell_map(layout: dict) -> {cell: value}` function codifying spec §10.3, plus a `render_workbook_bytes(layout, template_path)` function that opens the shipped `FRM/PRD/15` template with `openpyxl`, applies the cell map, and returns `.xlsx` bytes. A thin whitelisted controller method `download_sheet_cutting_layout(name)` extracts a plain-dict view of the persisted document, does a read-permission check, calls the service, and streams the file through Frappe's native `frappe.response` download path. A "Download Layout (Excel)" form button calls it.
**Tech Stack:** Frappe v15 / ERPNext v15.101, Python, openpyxl, Cypress
---

## Dependencies

- **Phase 0 (cleanup + native lifecycle) must land first.** This plan assumes `services/geometry.py` exists for steel-weight math, that `_parent_finished_part_rows` is the multi-BOM source of truth, and that release/cancel run from native `on_submit`/`on_cancel`. Phase 2 does **not** touch the lifecycle; it only reads released-layout fields.
- **Phase 1 (LH/RH symmetric parts) must land first.** This plan reads the Phase-1 parent fields `is_lh_rh` (Check), `orientation` (Select `LH`/`RH`), and `twin_finished_part` (Link Item) to render the joined part-number cell (`N5`) and the LH&RH part-name label (`G5`). If a worker executes Phase 2 on a branch where those three fields do not yet exist on the `Sheet Cutting Layout` doctype, Task 6's integration test will fail at document insert; land Phase 1 first.
- **Single-page export only.** Spec §10.5 (multi-sheet recursion: one workbook page per linked `child_layout`) is **Phase 4** and is explicitly out of scope here. This plan renders exactly one worksheet from one layout's own fields and its `end_pieces` rows; it never follows `child_layout`.
- **Open input (audit gate):** The blank `FRM/PRD/15` template shipped in Task 2 is a *minimally-correct* workbook built programmatically so the rest of the phase is testable end-to-end. It is **not** the audit-approved page. Before Phase 2 is considered closed, the user must confirm the curated audit-approved blank `FRM/PRD/15` page is in place at `sheet_cutting_layout/templates/iatf/sheet_cutting_layout.xlsx`. The cell map in Task 1 is the contract the curated template must satisfy; swapping the template file does not change any code.

## File structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `sheet_cutting_layout/services/export_service.py` | Create | Frappe-free core: `build_cell_map(layout_dict) -> dict[str, value]` (spec §10.3) + `render_workbook_bytes(layout_dict, template_path) -> bytes` (openpyxl apply). |
| `sheet_cutting_layout/templates/iatf/__init__.py` | Create | Package marker so the template dir ships with the app. |
| `sheet_cutting_layout/templates/iatf/sheet_cutting_layout.xlsx` | Create | Shipped blank `FRM/PRD/15` template (minimally-correct; audit-approved confirmation is the §Dependencies open input). |
| `sheet_cutting_layout/templates/iatf/build_blank_template.py` | Create | One-shot, committed generator that produced the shipped `.xlsx`; lets a reviewer/auditor regenerate or diff the blank. |
| `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py` | Modify | Add whitelisted `download_sheet_cutting_layout(name)` entry point: read-perm check, build dict view, call service, set `frappe.response` download fields. |
| `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js` | Modify | Add "Download Layout (Excel)" form button that opens the download URL. |
| `sheet_cutting_layout/tests/test_export_service.py` | Create | Unit tests for `build_cell_map` (incl. joined part numbers, LH/RH labels, missing-data guards) and `render_workbook_bytes`. |
| `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout_export.py` | Create | Integration test: persist a layout → call the entry point → reopen produced workbook → assert key cells. |
| `cypress/integration/sheet_cutting_layout_export.js` | Create | E2E: form button triggers a non-empty `.xlsx` download. |

All test modules subclass `sheet_cutting_layout.tests.base.SheetCuttingLayoutTestCase` (which resolves `FrappeTestCase` via the v16/v15 probe in `tests/base.py` — `frappe.tests.IntegrationTestCase` first, falling back to `frappe.tests.utils.FrappeTestCase`). Run **every** Python command from `/Users/gurudattkulkarni/Workspace/bench15`.

### Cell map contract (spec §10.3, codified here)

`build_cell_map` receives a plain dict (built from the document by the controller — see Task 3) with these keys and returns `{ "A1": value, ... }`. Worksheet target is the first/active sheet.

| Cell | Source key(s) | Value |
|---|---|---|
| `B1` | `company` | company name |
| `G5` | `part_name` | **human** part-name label (NOT an item code) — the controller resolves it from `Item.item_name` of `finished_part_code` (see Task 6 `_export_layout_dict`); LH/RH → `"<base> LH & RH"` (e.g. `"Brkt bumper top LH & RH"`, see Task 1) |
| `N5` | `part_numbers` (list) | joined part numbers, `"_"`-joined (e.g. `0102AAG06400_6410N`) |
| `B6` | `project` | project code (document name of the Project) |
| `C6` | `project_name` | project display name |
| `K8` | `sheet_thickness_mm` | sheet thickness |
| `K9` / `L9` / `M9` | `sheet_thickness_mm` / `sheet_width_mm` / `sheet_length_mm` | sheet T / W / L |
| `K10` | `weight_of_strip_kg` | strip weight |
| `K11` / `L11` / `M11` | `strip_thickness_mm` / `strip_width_mm` / `strip_length_mm` | strip T / W / L |
| `K12` | `parts_per_strip` | parts/strip |
| `K13` | `no_of_strips` | no. of strips |
| `K14` | `parts_per_sheet` | parts/sheet |
| `K15` / `K16` / `K17` | `gross_weight_per_part_kg` / `net_weight_per_part_kg` / `scrap_weight_per_part_kg` | gross / net / scrap per part |
| `O7:U7` (header is in template) | — | not written |
| `O8` `P8` `Q8` `R8` `S8` `T8` `U8` | main BOM row | joined part numbers (same as `N5`), gross wt/part, net (f.g.) wt/part, scrap wt/part, parts/sheet (nos), total wt = gross×nos, raw-material weight |
| `O9..U11` | up to 3 end-piece rows | one row per `end_pieces` entry: end-piece item code (or size label), gross, net, scrap, nos, total, weight |
| row 38 | — | signature row left blank (decision: physical signatures) |

Missing / `None` numeric inputs render as empty string `""` (never the string `"None"`); see the missing-data-guard tests.

---

## Task group A: Pure cell-map service (frappe-free)

### Task 1: `build_cell_map` — header, strip, and per-part cells

**Files:**
- Create: `sheet_cutting_layout/services/export_service.py` (new file, lines 1–end)
- Test: `sheet_cutting_layout/tests/test_export_service.py` (new file)

Steps:

- [ ] Write the failing test. Create `sheet_cutting_layout/tests/test_export_service.py` with this exact content:

```python
from __future__ import annotations

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


def _base_layout() -> dict:
	return {
		"company": "Acme Press Parts",
		# part_name is the HUMAN label (Item.item_name), never the item code;
		# the controller (Task 6) resolves it from finished_part_code's Item.
		"part_name": "Brkt bumper top",
		"part_numbers": ["0102AAG06400SHR"],
		"is_lh_rh": False,
		"project": "PRJ-0001",
		"project_name": "Bumper Program",
		"sheet_thickness_mm": 2.0,
		"sheet_width_mm": 1000.0,
		"sheet_length_mm": 2000.0,
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


class TestBuildCellMapHeaderAndStrip(SheetCuttingLayoutTestCase):
	def test_header_strip_and_per_part_cells(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		cells = build_cell_map(_base_layout())

		self.assertEqual(cells["B1"], "Acme Press Parts")
		self.assertEqual(cells["G5"], "Brkt bumper top")
		self.assertEqual(cells["N5"], "0102AAG06400SHR")
		self.assertEqual(cells["B6"], "PRJ-0001")
		self.assertEqual(cells["C6"], "Bumper Program")
		self.assertEqual(cells["K8"], 2.0)
		self.assertEqual(cells["K9"], 2.0)
		self.assertEqual(cells["L9"], 1000.0)
		self.assertEqual(cells["M9"], 2000.0)
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
		# Right-side main BOM row O8:U8 (U8 = raw-material weight).
		self.assertEqual(cells["O8"], "0102AAG06400SHR")
		self.assertEqual(cells["P8"], 15.72)
		self.assertEqual(cells["Q8"], 15.52)
		self.assertEqual(cells["R8"], 0.2)
		self.assertEqual(cells["S8"], 2)
		self.assertAlmostEqual(float(cells["T8"]), 31.44, places=6)
		self.assertEqual(cells["U8"], 31.44)
```

- [ ] Run it and see it FAIL. Command (from `/Users/gurudattkulkarni/Workspace/bench15`):
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service`
  Expected failure: `ModuleNotFoundError: No module named 'sheet_cutting_layout.services.export_service'` (the import inside the test fails).

- [ ] Minimal implementation. Create `sheet_cutting_layout/services/export_service.py` with this exact content:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence


def _num(value: object) -> object:
	"""Render a numeric layout value, or empty string when missing/blank."""
	if value is None or value == "":
		return ""
	return value


def _text(value: object) -> str:
	if value is None:
		return ""
	return str(value)


def _part_name_label(layout: Mapping[str, object]) -> str:
	base = _text(layout.get("part_name")).strip()
	if not base:
		return ""
	if layout.get("is_lh_rh"):
		return f"{base} LH & RH"
	return base


def _joined_part_numbers(layout: Mapping[str, object]) -> str:
	part_numbers = layout.get("part_numbers") or []
	cleaned = [str(part).strip() for part in part_numbers if str(part or "").strip()]
	return "_".join(cleaned)


def build_cell_map(layout: Mapping[str, object]) -> dict[str, object]:
	"""Map a Sheet Cutting Layout dict to FRM/PRD/15 worksheet cells (spec §10.3)."""
	cells: dict[str, object] = {
		"B1": _text(layout.get("company")),
		"G5": _part_name_label(layout),
		"N5": _joined_part_numbers(layout),
		"B6": _text(layout.get("project")),
		"C6": _text(layout.get("project_name")),
		"K8": _num(layout.get("sheet_thickness_mm")),
		"K9": _num(layout.get("sheet_thickness_mm")),
		"L9": _num(layout.get("sheet_width_mm")),
		"M9": _num(layout.get("sheet_length_mm")),
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
	return cells


def _bom_table_cells(layout: Mapping[str, object]) -> dict[str, object]:
	"""Right-side BOM table: main row O8:U8, end-piece rows O9:U11 (spec §10.3)."""
	cells: dict[str, object] = {}
	gross = layout.get("gross_weight_per_part_kg")
	nos = layout.get("parts_per_sheet")
	cells["O8"] = _joined_part_numbers(layout)
	cells["P8"] = _num(gross)
	cells["Q8"] = _num(layout.get("net_weight_per_part_kg"))
	cells["R8"] = _num(layout.get("scrap_weight_per_part_kg"))
	cells["S8"] = _num(nos)
	cells["T8"] = _num(_product(gross, nos))
	cells["U8"] = _num(layout.get("raw_material_weight_kg"))

	end_pieces: Sequence[Mapping[str, object]] = layout.get("end_pieces") or []
	for offset, end_piece in enumerate(end_pieces):
		row = 9 + offset
		if row > 11:
			break
		ep_gross = end_piece.get("gross_weight_per_part_kg")
		ep_nos = end_piece.get("bom_quantity")
		cells[f"O{row}"] = _end_piece_label(end_piece)
		cells[f"P{row}"] = _num(ep_gross)
		cells[f"Q{row}"] = _num(end_piece.get("net_weight_per_part_kg"))
		cells[f"R{row}"] = _num(end_piece.get("scrap_weight_per_part_kg"))
		cells[f"S{row}"] = _num(ep_nos)
		cells[f"T{row}"] = _num(_product(ep_gross, ep_nos))
		cells[f"U{row}"] = _num(end_piece.get("weight_kg"))
	return cells


def _end_piece_label(end_piece: Mapping[str, object]) -> str:
	item_code = _text(end_piece.get("end_piece_item_code")).strip()
	if item_code:
		return item_code
	width = end_piece.get("width_mm")
	length = end_piece.get("length_mm")
	if width and length:
		return f"{width} x {length}"
	return ""


def _product(left: object, right: object) -> object:
	if left in (None, "") or right in (None, ""):
		return ""
	try:
		return float(left) * float(right)
	except (TypeError, ValueError):
		return ""
```

- [ ] Run tests and see PASS. Command:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service`
  Expected: `test_header_strip_and_per_part_cells` passes (1 test OK).

- [ ] Run lint gates. From the app dir `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `python -m ruff check sheet_cutting_layout/services/export_service.py sheet_cutting_layout/tests/test_export_service.py` then
  `python -m ruff format --check sheet_cutting_layout/services/export_service.py sheet_cutting_layout/tests/test_export_service.py`
  Expected: both report no issues. If format check fails, run `python -m ruff format sheet_cutting_layout/services/export_service.py sheet_cutting_layout/tests/test_export_service.py` and re-run.

- [ ] Commit. From the repo root:
  `git add sheet_cutting_layout/services/export_service.py sheet_cutting_layout/tests/test_export_service.py && git commit -m "$(cat <<'EOF'
feat: add frappe-free build_cell_map for IATF export header and strip

Codifies spec §10.3 header, strip, per-part, and BOM-table cells for the
FRM/PRD/15 export as a pure layout-dict -> {cell: value} function.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"`

### Task 2: `build_cell_map` — joined LH/RH part numbers and labels (tests-only contract)

**Files:**
- Modify: `sheet_cutting_layout/tests/test_export_service.py` (append a test class)
- (No implementation change expected — `_joined_part_numbers` and `_part_name_label` from Task 1 already cover this; the test pins the LH/RH contract.)

Steps:

- [ ] Write the failing test. Append this class to `sheet_cutting_layout/tests/test_export_service.py` (after `TestBuildCellMapHeaderAndStrip`):

```python
class TestBuildCellMapLhRhLabels(SheetCuttingLayoutTestCase):
	def test_lh_rh_part_name_and_joined_numbers(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		layout = _base_layout()
		layout.update(
			{
				"part_name": "Brkt bumper top",
				"is_lh_rh": True,
				"orientation": "LH",
				"part_numbers": ["0102AAG06400SHR", "0102AAG06410SHR"],
			}
		)

		cells = build_cell_map(layout)

		self.assertEqual(cells["G5"], "Brkt bumper top LH & RH")
		self.assertEqual(cells["N5"], "0102AAG06400SHR_0102AAG06410SHR")
		self.assertEqual(cells["O8"], "0102AAG06400SHR_0102AAG06410SHR")

	def test_single_part_number_is_not_joined(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		layout = _base_layout()
		layout["part_numbers"] = ["0102AAG06400SHR"]

		cells = build_cell_map(layout)

		self.assertEqual(cells["N5"], "0102AAG06400SHR")
		self.assertEqual(cells["G5"], "Brkt bumper top")

	def test_blank_part_numbers_are_dropped_from_join(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		layout = _base_layout()
		layout["part_numbers"] = ["0102AAG06400SHR", "", None, "  "]

		cells = build_cell_map(layout)

		self.assertEqual(cells["N5"], "0102AAG06400SHR")
```

- [ ] Run it and confirm result. Command:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service`
  Expected: the three new tests **PASS** immediately (Task 1's code already satisfies them). This task is a characterization/contract test — if any fail, that is a real regression in Task 1's join/label logic and must be fixed before continuing.

- [ ] Run lint gates. From `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `python -m ruff check sheet_cutting_layout/tests/test_export_service.py && python -m ruff format --check sheet_cutting_layout/tests/test_export_service.py`
  Expected: no issues (run `python -m ruff format ...` if the format check fails).

- [ ] Commit. From the repo root:
  `git add sheet_cutting_layout/tests/test_export_service.py && git commit -m "$(cat <<'EOF'
test: pin LH/RH joined part-number and label rendering for export

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"`

### Task 3: `build_cell_map` — end-piece rows and missing-data guards

**Files:**
- Modify: `sheet_cutting_layout/tests/test_export_service.py` (append a test class)
- (No implementation change expected — `_bom_table_cells` and `_num` from Task 1 cover this; the test pins the contract and the empty-string guard.)

Steps:

- [ ] Write the failing test. Append this class to `sheet_cutting_layout/tests/test_export_service.py`:

```python
class TestBuildCellMapEndPiecesAndGuards(SheetCuttingLayoutTestCase):
	def test_end_piece_rows_populate_bom_table(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		layout = _base_layout()
		layout["end_pieces"] = [
			{
				"end_piece_item_code": "EP-0102AAG06400-1",
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
		self.assertEqual(cells["P9"], 0.47)
		self.assertEqual(cells["Q9"], 0.4)
		self.assertEqual(cells["R9"], 0.07)
		self.assertEqual(cells["S9"], 2)
		self.assertAlmostEqual(float(cells["T9"]), 0.94, places=6)
		self.assertEqual(cells["U9"], 0.94)

	def test_end_piece_without_item_code_uses_size_label(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		layout = _base_layout()
		layout["end_pieces"] = [
			{"width_mm": 200.0, "length_mm": 300.0, "weight_kg": 0.94}
		]

		cells = build_cell_map(layout)

		self.assertEqual(cells["O9"], "200.0 x 300.0")

	def test_only_first_three_end_pieces_render(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		layout = _base_layout()
		layout["end_pieces"] = [
			{"end_piece_item_code": f"EP-{index}"} for index in range(5)
		]

		cells = build_cell_map(layout)

		self.assertEqual(cells["O9"], "EP-0")
		self.assertEqual(cells["O10"], "EP-1")
		self.assertEqual(cells["O11"], "EP-2")
		self.assertNotIn("O12", cells)

	def test_missing_numeric_inputs_render_as_empty_string(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		layout = _base_layout()
		layout.update(
			{
				"sheet_thickness_mm": None,
				"weight_of_strip_kg": None,
				"gross_weight_per_part_kg": None,
				"net_weight_per_part_kg": "",
				"parts_per_sheet": None,
				"raw_material_weight_kg": None,
			}
		)

		cells = build_cell_map(layout)

		self.assertEqual(cells["K8"], "")
		self.assertEqual(cells["K9"], "")
		self.assertEqual(cells["K10"], "")
		self.assertEqual(cells["K15"], "")
		self.assertEqual(cells["K16"], "")
		self.assertEqual(cells["T8"], "")
		self.assertEqual(cells["U8"], "")
		# Never the literal string "None".
		for value in cells.values():
			self.assertNotEqual(value, "None")
```

- [ ] Run it and confirm result. Command:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service`
  Expected: all four new tests **PASS** (Task 1's `_bom_table_cells`/`_num` already satisfy them). If any fail it signals a real gap in Task 1 to fix now.

- [ ] Run lint gates. From `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `python -m ruff check sheet_cutting_layout/tests/test_export_service.py && python -m ruff format --check sheet_cutting_layout/tests/test_export_service.py`
  Expected: no issues.

- [ ] Commit. From the repo root:
  `git add sheet_cutting_layout/tests/test_export_service.py && git commit -m "$(cat <<'EOF'
test: cover end-piece BOM rows and missing-data guards for export

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"`

---

## Task group B: Template asset + workbook rendering

### Task 4: Ship a blank `FRM/PRD/15` template and its generator

> **AUDIT OPEN INPUT — read before doing this task.** The workbook produced here is a *minimally-correct* blank so the export is testable; it is **not** the audit-approved page. The committed generator (`build_blank_template.py`) makes the blank reproducible and diff-able by a reviewer. Phase 2 does not close until the user confirms the curated audit-approved blank `FRM/PRD/15` is in place at the same path. Replacing the file requires **no** code change — the cell map (Task 1) is the contract.

**Files:**
- Create: `sheet_cutting_layout/templates/iatf/__init__.py` (empty package marker)
- Create: `sheet_cutting_layout/templates/iatf/build_blank_template.py` (committed generator)
- Create: `sheet_cutting_layout/templates/iatf/sheet_cutting_layout.xlsx` (generated artifact)

Steps:

- [ ] Create the package marker. Create `sheet_cutting_layout/templates/iatf/__init__.py` as an **empty** file (zero bytes).

- [ ] Create the generator. Create `sheet_cutting_layout/templates/iatf/build_blank_template.py` with this exact content:

```python
"""Generate the shipped blank FRM/PRD/15 IATF export template.

This produces a *minimally-correct* blank workbook so the exporter is
testable end-to-end. It is NOT the audit-approved page; see the Phase 2
plan's "AUDIT OPEN INPUT" note. Run with the bench env python:

    /Users/gurudattkulkarni/Workspace/bench15/env/bin/python \
        sheet_cutting_layout/templates/iatf/build_blank_template.py
"""

from __future__ import annotations

import os

from openpyxl import Workbook

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "sheet_cutting_layout.xlsx")

# Static labels the exporter never overwrites. Keys are cell coordinates.
STATIC_LABELS = {
	"A1": "Company:",
	"A2": "Doc No:",
	"B2": "FRM/PRD/15",
	"A5": "Part Name:",
	"M5": "Part Number:",
	"A6": "Project:",
	"A8": "Sheet Thickness (mm):",
	"A9": "Sheet T/W/L (mm):",
	"A10": "Strip Weight (kg):",
	"A11": "Strip T/W/L (mm):",
	"A12": "Parts / Strip:",
	"A13": "No. of Strips:",
	"A14": "Parts / Sheet:",
	"A15": "Gross Wt / Part (kg):",
	"A16": "Net Wt / Part (kg):",
	"A17": "Scrap Wt / Part (kg):",
	"O7": "Item",
	"P7": "Gross",
	"Q7": "F.G.",
	"R7": "Scrap",
	"S7": "Nos",
	"T7": "Total Wt",
	"U7": "RM Wt",
	"A38": "Prepared By (Engg/Prod):",
	"G38": "Checked by Production Manager:",
	"M38": "BOM Updated by Purchase:",
	"R38": "Released by Management Rep:",
}


def build_blank_template() -> None:
	workbook = Workbook()
	worksheet = workbook.active
	worksheet.title = "FRM-PRD-15"
	for coordinate, label in STATIC_LABELS.items():
		worksheet[coordinate] = label
	workbook.save(TEMPLATE_PATH)


if __name__ == "__main__":
	build_blank_template()
	print(f"Wrote {TEMPLATE_PATH}")
```

- [ ] Generate the workbook artifact. Command (from `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`):
  `/Users/gurudattkulkarni/Workspace/bench15/env/bin/python sheet_cutting_layout/templates/iatf/build_blank_template.py`
  Expected output: `Wrote /Users/gurudattkulkarni/Workspace/sheet_cutting_layout/sheet_cutting_layout/templates/iatf/sheet_cutting_layout.xlsx`.

- [ ] Verify the artifact is a valid, non-empty workbook. Command (from `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`):
  `/Users/gurudattkulkarni/Workspace/bench15/env/bin/python -c "from openpyxl import load_workbook; wb = load_workbook('sheet_cutting_layout/templates/iatf/sheet_cutting_layout.xlsx'); ws = wb.active; print(ws.title, ws['B2'].value, ws['O7'].value)"`
  Expected output: `FRM-PRD-15 FRM/PRD/15 Item`.

- [ ] Run lint gates on the generator. From `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `python -m ruff check sheet_cutting_layout/templates/iatf/build_blank_template.py && python -m ruff format --check sheet_cutting_layout/templates/iatf/build_blank_template.py`
  Expected: no issues.

- [ ] Confirm `.xlsx` is not git-ignored. Command from the repo root:
  `git check-ignore sheet_cutting_layout/templates/iatf/sheet_cutting_layout.xlsx; echo "exit=$?"`
  Expected: `exit=1` (no output, meaning the file is NOT ignored). If it prints the path with `exit=0`, the file is ignored — add a negation to `.gitignore` (e.g. `!sheet_cutting_layout/templates/iatf/*.xlsx`) and re-check before committing.

- [ ] Commit. From the repo root:
  `git add sheet_cutting_layout/templates/iatf/__init__.py sheet_cutting_layout/templates/iatf/build_blank_template.py sheet_cutting_layout/templates/iatf/sheet_cutting_layout.xlsx && git commit -m "$(cat <<'EOF'
feat: ship blank FRM/PRD/15 IATF export template and generator

Minimally-correct blank workbook plus a committed openpyxl generator so the
template is reproducible and diff-able. Audit-approved curated blank is a
Phase 2 closing gate (open input); swapping the file needs no code change.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"`

### Task 5: `render_workbook_bytes` — apply the cell map to the template

**Files:**
- Modify: `sheet_cutting_layout/services/export_service.py` (append `render_workbook_bytes` + `template_path`, after `build_cell_map`)
- Modify: `sheet_cutting_layout/tests/test_export_service.py` (append a test class)

Steps:

- [ ] Write the failing test. Append this class to `sheet_cutting_layout/tests/test_export_service.py`:

```python
class TestRenderWorkbookBytes(SheetCuttingLayoutTestCase):
	def test_renders_cells_into_template_and_returns_xlsx_bytes(self) -> None:
		import io

		from openpyxl import load_workbook

		from sheet_cutting_layout.services.export_service import (
			default_template_path,
			render_workbook_bytes,
		)

		layout = _base_layout()
		layout.update(
			{
				"is_lh_rh": True,
				"part_numbers": ["0102AAG06400SHR", "0102AAG06410SHR"],
			}
		)

		content = render_workbook_bytes(layout, default_template_path())

		self.assertIsInstance(content, bytes)
		self.assertGreater(len(content), 0)
		# .xlsx is a zip archive — first two bytes are "PK".
		self.assertEqual(content[:2], b"PK")

		workbook = load_workbook(io.BytesIO(content))
		worksheet = workbook.active
		self.assertEqual(worksheet["B1"].value, "Acme Press Parts")
		self.assertEqual(worksheet["G5"].value, "Brkt bumper top LH & RH")
		self.assertEqual(worksheet["N5"].value, "0102AAG06400SHR_0102AAG06410SHR")
		self.assertEqual(worksheet["K14"].value, 2)
		# Static template label is preserved (not overwritten by the cell map).
		self.assertEqual(worksheet["B2"].value, "FRM/PRD/15")

	def test_empty_string_cells_clear_the_target_cell(self) -> None:
		import io

		from openpyxl import load_workbook

		from sheet_cutting_layout.services.export_service import (
			default_template_path,
			render_workbook_bytes,
		)

		layout = _base_layout()
		layout["sheet_thickness_mm"] = None

		content = render_workbook_bytes(layout, default_template_path())
		workbook = load_workbook(io.BytesIO(content))
		worksheet = workbook.active
		self.assertIn(worksheet["K8"].value, (None, ""))
```

- [ ] Run it and see it FAIL. Command:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service`
  Expected failure: `ImportError: cannot import name 'render_workbook_bytes' from 'sheet_cutting_layout.services.export_service'` (and `default_template_path`).

- [ ] Minimal implementation. Append this to the **end** of `sheet_cutting_layout/services/export_service.py`:

```python
def default_template_path() -> str:
	import os

	return os.path.join(
		os.path.dirname(__file__),
		"..",
		"templates",
		"iatf",
		"sheet_cutting_layout.xlsx",
	)


def render_workbook_bytes(layout: Mapping[str, object], template_path: str) -> bytes:
	"""Open the FRM/PRD/15 template, apply the cell map, return .xlsx bytes."""
	import io

	from openpyxl import load_workbook

	workbook = load_workbook(template_path)
	worksheet = workbook.active
	cells = build_cell_map(layout)
	for coordinate, value in cells.items():
		worksheet[coordinate] = value if value != "" else None
	buffer = io.BytesIO()
	workbook.save(buffer)
	return buffer.getvalue()
```

- [ ] Run tests and see PASS. Command:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service`
  Expected: both new tests pass; all earlier `test_export_service` tests still pass.

- [ ] Run lint gates. From `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `python -m ruff check sheet_cutting_layout/services/export_service.py sheet_cutting_layout/tests/test_export_service.py && python -m ruff format --check sheet_cutting_layout/services/export_service.py sheet_cutting_layout/tests/test_export_service.py`
  Expected: no issues.

- [ ] Commit. From the repo root:
  `git add sheet_cutting_layout/services/export_service.py sheet_cutting_layout/tests/test_export_service.py && git commit -m "$(cat <<'EOF'
feat: render FRM/PRD/15 workbook bytes from layout via openpyxl

render_workbook_bytes opens the shipped template, applies build_cell_map,
and returns .xlsx bytes for the native download response.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"`

---

## Task group C: Whitelisted entry point + form button

### Task 6: `download_sheet_cutting_layout(name)` controller method

The controller builds the plain-dict view the service expects, does a read-permission check, and sets the native download fields on `frappe.response` (the same pattern ERPNext's chart-of-accounts importer uses: `frappe/utils/response.py::as_raw` / `as_binary`, and `erpnext/.../chart_of_accounts_importer.py:304-306`). Verified field shape: set `frappe.response["filename"]`, `frappe.response["filecontent"]` (bytes), `frappe.response["type"] = "binary"`.

The dict view maps the document's stored fields to the cell-map keys, including the Phase-1 LH/RH twin into `part_numbers`, the human `part_name` resolved from the finished part's `Item.item_name` (G5 is a label, never the item code), the Project's display name, and the BOM raw-material weight stored on the primary `finished_parts` reference row (populated only after release; blank on a Draft layout — see Task 6 test note on U8).

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py` — add `download_sheet_cutting_layout` + a private dict-builder, appended after the last top-level function `generate_sheet_cutting_layout_end_piece_boms` (anchor by symbol; absolute line numbers shift once Phase 0 rewrites this controller).
- Test: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout_export.py` (new file — integration).

Steps:

- [ ] Write the failing integration test. Create `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout_export.py` with this exact content:

```python
from __future__ import annotations

import io

import frappe
from openpyxl import load_workbook

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase
from sheet_cutting_layout.tests.factories import ITEM_CODE_PREFIX, TEST_PREFIX, register_test_doc


def _ensure_item(item_code: str, item_name: str | None = None) -> str:
	if not frappe.db.exists("Item", item_code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": item_name or item_code,
				"item_group": "All Item Groups",
				"stock_uom": "Kg",
				"is_stock_item": 1,
			}
		).insert(ignore_permissions=True)
	register_test_doc("Item", item_code)
	return item_code


def _ensure_project() -> str:
	project_code = f"{TEST_PREFIX}EXPORT"
	if not frappe.db.exists("Project", project_code):
		frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": "Export Program",
				"name": project_code,
			}
		).insert(ignore_permissions=True)
	register_test_doc("Project", project_code)
	return project_code


class TestSheetCuttingLayoutExport(SheetCuttingLayoutTestCase):
	def _build_layout(self) -> str:
		project = _ensure_project()
		raw_material = _ensure_item(f"{ITEM_CODE_PREFIX}RM01")
		scrap = _ensure_item(f"{ITEM_CODE_PREFIX}SCRAP01")
		# Distinct HUMAN item_name so the G5 assertion proves _export_layout_dict
		# resolves Item.item_name and never leaks the raw item code into G5.
		finished = _ensure_item(
			f"{ITEM_CODE_PREFIX}PART01SHR", item_name="Brkt bumper top"
		)
		layout_code = f"{TEST_PREFIX}LAYOUT-EXPORT"
		register_test_doc("Sheet Cutting Layout", layout_code)
		doc = frappe.get_doc(
			{
				"doctype": "Sheet Cutting Layout",
				"layout_code": layout_code,
				"project": project,
				"revision_no": 1,
				"status": "Draft",
				"raw_material_item": raw_material,
				"process_scrap_item": scrap,
				"sheet_thickness_mm": 2.0,
				"sheet_width_mm": 1000.0,
				"sheet_length_mm": 2000.0,
				"weight_per_sheet_kg": 31.44,
				"strip_thickness_mm": 2.0,
				"strip_width_mm": 1000.0,
				"strip_length_mm": 1000.0,
				"weight_of_strip_kg": 15.72,
				"parts_per_strip": 1,
				"no_of_strips": 2,
				"parts_per_sheet": 2,
				"finished_part_code": finished,
				"net_weight_per_part_kg": 15.52,
				"gross_weight_per_part_kg": 15.72,
				"scrap_weight_per_part_kg": 0.2,
				# No end_pieces rows here on purpose: a valid end-piece row must be
				# a fully-specified Reuse/Scrap row (validators.py
				# _validate_end_piece_disposition + the reuse weight-split /
				# sheet-consumption checks), which would make this single-layout
				# export fixture brittle. The end-piece BOM-table rows O9:U11 are
				# covered exhaustively by the unit tests in test_export_service.py
				# (TestBuildCellMapEndPiecesAndGuards) — see the U8/end-piece note
				# on the assertions below.
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def test_download_produces_workbook_with_expected_cells(self) -> None:
		from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.sheet_cutting_layout import (  # noqa: E501
			download_sheet_cutting_layout,
		)

		layout_name = self._build_layout()
		frappe.response.clear()

		download_sheet_cutting_layout(layout_name)

		self.assertEqual(frappe.response["type"], "binary")
		self.assertTrue(str(frappe.response["filename"]).endswith(".xlsx"))
		content = frappe.response["filecontent"]
		self.assertIsInstance(content, bytes)
		self.assertEqual(content[:2], b"PK")

		worksheet = load_workbook(io.BytesIO(content)).active
		self.assertEqual(worksheet["K9"].value, 2.0)
		self.assertEqual(worksheet["L9"].value, 1000.0)
		self.assertEqual(worksheet["M9"].value, 2000.0)
		self.assertEqual(worksheet["K14"].value, 2)
		self.assertEqual(worksheet["K15"].value, 15.72)
		self.assertEqual(worksheet["K16"].value, 15.52)
		self.assertEqual(worksheet["B6"].value, f"{TEST_PREFIX}EXPORT")
		self.assertEqual(worksheet["C6"].value, "Export Program")
		self.assertIn(f"{ITEM_CODE_PREFIX}PART01SHR", str(worksheet["N5"].value))
		# G5 is the HUMAN label resolved from Item.item_name, NOT the item code.
		self.assertEqual(worksheet["G5"].value, "Brkt bumper top")
		self.assertNotEqual(worksheet["G5"].value, f"{ITEM_CODE_PREFIX}PART01SHR")
		# NOTE — U8 and the end-piece BOM-table rows (O9:U11) are UNIT-covered
		# only, by design:
		#   * U8 (raw_material_weight_kg) comes from the post-release
		#     `finished_parts` mirror (_sync_finished_part_reference_rows fills it
		#     on release). This Draft layout has an empty mirror, so U8 is blank
		#     here. The U8-populated path is asserted by the unit test
		#     TestBuildCellMapHeaderAndStrip.test_header_strip_and_per_part_cells
		#     (cells["U8"] == 31.44) in tests/test_export_service.py.
		#   * End-piece rows require fully-specified Reuse/Scrap rows that pass
		#     validators.py; rather than carry that brittle fixture here, the
		#     O9:U11 rendering is asserted by
		#     TestBuildCellMapEndPiecesAndGuards in tests/test_export_service.py.
		# Driving a full release to populate both would depend on the
		# Phase-0/Phase-1 lifecycle and is out of scope for this single-layout
		# export test.
		self.assertIn(worksheet["U8"].value, (None, ""))
```

- [ ] Run it and see it FAIL. Command:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout_export`
  Expected failure: `ImportError: cannot import name 'download_sheet_cutting_layout' from '...sheet_cutting_layout'`.

- [ ] Minimal implementation. In `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`, add this import to the top-of-file service-import block (immediately after the existing `from sheet_cutting_layout.services.workflow import record_approval_snapshot` line — the last entry in that block):

```python
from sheet_cutting_layout.services.export_service import (
	default_template_path,
	render_workbook_bytes,
)
```

  Then append these two functions to the **end** of the file (after `generate_sheet_cutting_layout_end_piece_boms`, which is the last top-level function in the module):

```python
@whitelist()
def download_sheet_cutting_layout(name: str) -> None:
	if not frappe:
		raise RuntimeError("Frappe is required to export Sheet Cutting Layout")

	doc = frappe.get_doc("Sheet Cutting Layout", name)
	check_permission = getattr(doc, "check_permission", None)
	if callable(check_permission):
		check_permission("read")

	content = render_workbook_bytes(_export_layout_dict(doc), default_template_path())
	frappe.response["filename"] = f"{doc.name}.xlsx"
	frappe.response["filecontent"] = content
	frappe.response["type"] = "binary"


def _export_layout_dict(doc: object) -> dict[str, object]:
	finished_part_code = getattr(doc, "finished_part_code", None)
	part_numbers = [code for code in [finished_part_code] if code]
	if getattr(doc, "is_lh_rh", None) and getattr(doc, "twin_finished_part", None):
		part_numbers.append(doc.twin_finished_part)

	# G5 is a HUMAN part-name label, not an item code: resolve the finished
	# part's Item.item_name. The cell map's _part_name_label adds the LH&RH
	# suffix on top of this base label. Fall back to the code only if the
	# Item has no item_name (never leave G5 = raw item code silently).
	part_name = ""
	if frappe and finished_part_code:
		part_name = (
			frappe.get_cached_value("Item", finished_part_code, "item_name")
			or finished_part_code
		)
	elif finished_part_code:
		part_name = finished_part_code

	project = getattr(doc, "project", None)
	project_name = ""
	if frappe and project:
		project_name = frappe.db.get_value("Project", project, "project_name") or ""

	company = ""
	if frappe:
		import erpnext

		company = erpnext.get_default_company() or ""

	raw_material_weight_kg = None
	for row in getattr(doc, "finished_parts", None) or []:
		raw_material_weight_kg = getattr(row, "raw_material_weight_kg", None)
		break

	return {
		"company": company,
		"part_name": part_name,
		"part_numbers": part_numbers,
		"is_lh_rh": bool(getattr(doc, "is_lh_rh", False)),
		"orientation": getattr(doc, "orientation", None),
		"project": project,
		"project_name": project_name,
		"sheet_thickness_mm": getattr(doc, "sheet_thickness_mm", None),
		"sheet_width_mm": getattr(doc, "sheet_width_mm", None),
		"sheet_length_mm": getattr(doc, "sheet_length_mm", None),
		"weight_of_strip_kg": getattr(doc, "weight_of_strip_kg", None),
		"strip_thickness_mm": getattr(doc, "strip_thickness_mm", None),
		"strip_width_mm": getattr(doc, "strip_width_mm", None),
		"strip_length_mm": getattr(doc, "strip_length_mm", None),
		"parts_per_strip": getattr(doc, "parts_per_strip", None),
		"no_of_strips": getattr(doc, "no_of_strips", None),
		"parts_per_sheet": getattr(doc, "parts_per_sheet", None),
		"gross_weight_per_part_kg": getattr(doc, "gross_weight_per_part_kg", None),
		"net_weight_per_part_kg": getattr(doc, "net_weight_per_part_kg", None),
		"scrap_weight_per_part_kg": getattr(doc, "scrap_weight_per_part_kg", None),
		"raw_material_weight_kg": raw_material_weight_kg,
		"end_pieces": [
			{
				"end_piece_item_code": getattr(row, "end_piece_item_code", None),
				"width_mm": getattr(row, "width_mm", None),
				"length_mm": getattr(row, "length_mm", None),
				"weight_kg": getattr(row, "weight_kg", None),
				"gross_weight_per_part_kg": getattr(row, "gross_weight_per_part_kg", None),
				"net_weight_per_part_kg": getattr(row, "net_weight_per_part_kg", None),
				"scrap_weight_per_part_kg": getattr(row, "scrap_weight_per_part_kg", None),
				"bom_quantity": getattr(row, "bom_quantity", None),
			}
			for row in getattr(doc, "end_pieces", None) or []
		],
	}
```

  > Note: the doctype has **no** dedicated part-name field, so `part_name` is the **human** `Item.item_name` of `finished_part_code`, resolved here via `frappe.get_cached_value("Item", finished_part_code, "item_name")` (G5 must read like spec §2's `"Brkt bumper top LH&RH"`, never the raw item code). The cell map's `_part_name_label` (Task 1) layers the LH&RH suffix on top of this base label. If the Item has no `item_name` we fall back to the code rather than emit a blank cell. If Phase 1 names its fields differently than `is_lh_rh`/`orientation`/`twin_finished_part`, update only the three `getattr(doc, ...)` calls here — they are the single coupling point to Phase 1.

- [ ] Run tests and see PASS. Command:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout_export`
  Expected: `test_download_produces_workbook_with_expected_cells` passes (1 test OK).

- [ ] Run lint gates. From `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `python -m ruff check sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout_export.py && python -m ruff format --check sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout_export.py`
  Expected: no issues.

- [ ] Commit. From the repo root:
  `git add sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout_export.py && git commit -m "$(cat <<'EOF'
feat: add download_sheet_cutting_layout whitelisted IATF export endpoint

Read-permission-checked entry point builds a plain-dict view (incl. LH/RH
twin part numbers) and streams the FRM/PRD/15 .xlsx via frappe.response.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"`

### Task 7: "Download Layout (Excel)" form button

The button opens the whitelisted method's URL with the document name as a query arg, which triggers the native binary download. Mirrors the existing button wiring in `sheet_cutting_layout.js` (`refresh` handler, `frm.add_custom_button`).

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js` — add a helper and call it from `refresh` (refresh handler is at lines 398–414; helpers are defined above `frappe.ui.form.on`).

Steps:

- [ ] Add the button helper. In `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`, insert this function immediately before `function ignoreBomInGenericCancelAll(frm) {` (currently line 391):

```javascript
	function addDownloadLayoutButton(frm) {
		if (frm.is_new()) {
			return;
		}
		frm.add_custom_button(__("Download Layout (Excel)"), () => {
			const method =
				"sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout." +
				"sheet_cutting_layout.download_sheet_cutting_layout";
			const url = `/api/method/${method}?name=${encodeURIComponent(frm.doc.name)}`;
			window.open(url, "_blank");
		});
	}

```

- [ ] Call it from `refresh`. In the same file, inside the `refresh(frm)` handler, add the call right after `addEndPieceBomButtons(frm);` (currently line 400). Change:

```javascript
		refresh(frm) {
			ignoreBomInGenericCancelAll(frm);
			addEndPieceBomButtons(frm);
```

  to:

```javascript
		refresh(frm) {
			ignoreBomInGenericCancelAll(frm);
			addEndPieceBomButtons(frm);
			addDownloadLayoutButton(frm);
```

- [ ] Run lint/format gates on the JS. From `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `npx prettier --check sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`
  Expected: `All matched files use Prettier code style!`. If it reports a style issue, run `npx prettier --write sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js` and re-check.

- [ ] Build assets so the button loads in the running site (the doctype JS is bundled by Frappe). Command from `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench build --app sheet_cutting_layout`
  Expected: build completes without error (this makes the new button available to the Task 8 E2E run).

- [ ] Commit. From the repo root:
  `git add sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js && git commit -m "$(cat <<'EOF'
feat: add Download Layout (Excel) form button for IATF export

Opens the whitelisted download_sheet_cutting_layout endpoint to stream the
FRM/PRD/15 workbook for the current layout.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"`

---

## Task group D: End-to-end

### Task 8: Cypress E2E — button downloads a non-empty `.xlsx`

The spec triggers the same download URL the button opens and asserts the response is a non-empty `.xlsx` (zip magic bytes `PK`). It reuses the existing custom commands (`cy.login`, `cy.call`, `cy.ensureHsnCode`) from `cypress/support/e2e.js`, and the layout-insert shape from `cypress/integration/sheet_cutting_layout_release.js`.

**Files:**
- Create: `cypress/integration/sheet_cutting_layout_export.js` (new spec)

Steps:

- [ ] Write the E2E spec. Create `cypress/integration/sheet_cutting_layout_export.js` with this exact content:

```javascript
describe("Sheet Cutting Layout IATF export", () => {
	const suffix = Date.now();
	const layoutCode = `SCLEXP${suffix}`;
	const project = `SCLEXPPROJ${suffix}`;
	const rawMaterialItem = `SCLEXPRM${suffix}`;
	const processScrapItem = `SCLEXPSCRAP${suffix}`;
	const finishedPartItem = `EXPPART001${suffix}SHR`;
	let projectName;

	const downloadMethod =
		"sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout." +
		"sheet_cutting_layout.download_sheet_cutting_layout";

	before(() => {
		cy.login();
		cy.ensureHsnCode("720890");
		cy.call("frappe.client.insert", {
			doc: { doctype: "Project", name: project, project_name: project },
		}).then(({ message }) => {
			projectName = message.name;
		});
		[rawMaterialItem, processScrapItem, finishedPartItem].forEach((itemCode) => {
			cy.call("frappe.client.insert", {
				doc: {
					doctype: "Item",
					item_code: itemCode,
					item_name: itemCode,
					item_group: "All Item Groups",
					stock_uom: "Kg",
					is_stock_item: 1,
					gst_hsn_code: "720890",
				},
			});
		});
	});

	beforeEach(() => {
		cy.login();
	});

	it("downloads a non-empty .xlsx via the export endpoint", { retries: 0 }, () => {
		cy.call("frappe.client.insert", {
			doc: {
				doctype: "Sheet Cutting Layout",
				layout_code: layoutCode,
				project: projectName,
				revision_no: 1,
				is_active: 0,
				status: "Draft",
				raw_material_item: rawMaterialItem,
				process_scrap_item: processScrapItem,
				sheet_thickness_mm: 2,
				sheet_width_mm: 1000,
				sheet_length_mm: 2000,
				weight_per_sheet_kg: 31.44,
				strip_thickness_mm: 2,
				strip_width_mm: 1000,
				strip_length_mm: 1000,
				weight_of_strip_kg: 15.72,
				parts_per_strip: 1,
				no_of_strips: 2,
				parts_per_sheet: 2,
				finished_part_code: finishedPartItem,
				net_weight_per_part_kg: 15.52,
				gross_weight_per_part_kg: 15.72,
				scrap_weight_per_part_kg: 0.2,
			},
		});

		cy.visit(`/app/sheet-cutting-layout/${layoutCode}`);
		cy.contains('[data-fieldname="status"]', "Draft");
		cy.contains("button", "Download Layout (Excel)").should("exist");

		cy.request({
			method: "GET",
			url: `/api/method/${downloadMethod}?name=${encodeURIComponent(layoutCode)}`,
			encoding: "binary",
		}).then((response) => {
			expect(response.status).to.equal(200);
			expect(response.headers["content-disposition"]).to.contain(".xlsx");
			expect(response.body.length).to.be.greaterThan(0);
			// .xlsx is a zip archive — first two bytes are "PK".
			expect(response.body.slice(0, 2)).to.equal("PK");
		});
	});
});
```

- [ ] Run the E2E spec. Command from `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-ui-tests sheet_cutting_layout --headless --spec cypress/integration/sheet_cutting_layout_export.js`
  Expected: the `downloads a non-empty .xlsx via the export endpoint` test passes (1 passing). If the bench runner does not accept `--spec`, run `bench --site development.localhost run-ui-tests sheet_cutting_layout --headless` and confirm the export spec is green among the suite.

- [ ] Run lint/format gates on the spec. From `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `npx prettier --check cypress/integration/sheet_cutting_layout_export.js`
  Expected: `All matched files use Prettier code style!` (run `npx prettier --write ...` then re-check if needed).

- [ ] Commit. From the repo root:
  `git add cypress/integration/sheet_cutting_layout_export.js && git commit -m "$(cat <<'EOF'
test: e2e download button yields a non-empty FRM/PRD/15 .xlsx

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"`

---

## Final verification (run before declaring Phase 2 done)

- [ ] Full Python suite green. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-tests --app sheet_cutting_layout`
  Expected: all tests pass, including `test_export_service` and `test_sheet_cutting_layout_export`.

- [ ] Lint + format gates clean across the app. From `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `python -m ruff check . && python -m ruff format --check .`
  Expected: no issues.

- [ ] **Audit gate (open input — escalate to user, do NOT self-resolve):** Confirm with the user that the curated, audit-approved blank `FRM/PRD/15` page is in place at `sheet_cutting_layout/templates/iatf/sheet_cutting_layout.xlsx`. The cell-map contract (Task 1 + the cell-map table above) is fixed; if the curated template lays out fields at different coordinates than the table above, update **only** the cell coordinates in `build_cell_map` (and the corresponding test expectations) — no other code changes. Phase 2 is not closed until this confirmation is recorded.

- [ ] **Phase 4 boundary check:** Confirm the exporter never reads `end_pieces[].child_layout` and renders exactly one worksheet. Multi-sheet recursion (spec §10.5) is deferred to the Phase 3↔export integration PR and must not be added here.
