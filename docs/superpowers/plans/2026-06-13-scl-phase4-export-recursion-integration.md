# Phase 4 — Export ↔ Recursion Integration Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teach the IATF exporter to render a recursive cutting layout as a multi-sheet Excel workbook — one worksheet for the parent layout plus one worksheet per descendant `child_layout`, reusing the single-page cell-map — and prove the full arc (LH/RH + child layout → release → multi-sheet download → supersede → cascade retire) end to end.

**Architecture:** A frappe-free `walk_layout_tree(layout, fetch_child)` traversal in `services/export_service.py` expands a parent layout into an ordered list of layout documents by following each end piece's `child_layout` link depth-first; the controller turns each into a `(title, layout_dict)` page (title = the layout document `name`, dict = Phase 2's `_export_layout_dict`), and `build_multi_sheet_workbook` writes one openpyxl worksheet per page into a single workbook by calling the existing single-page `build_cell_map` cell-map once per page. The whitelisted `download_sheet_cutting_layout(name)` entry point on the SCL controller resolves child layouts through `frappe.get_doc` and streams the multi-sheet `.xlsx` through the same Phase 2 `frappe.response` (`type="binary"`) download path. (Phase 2's real export symbols are dict-based — `build_cell_map` / `render_workbook_bytes` / `default_template_path` / `_export_layout_dict` — not a `LayoutView` dataclass; Task 1 reconciles this against the real file before any code is written.)

**Tech Stack:** Frappe v15 / ERPNext v15.101, Python, openpyxl, Cypress

---

## Dependencies

This is the **final integration phase**. It merges **last**, after both of these have landed on `feature/scl-iatf-export-lhrh-recursion`:

- **Phase 0** — cleanup + framework-native lifecycle. Establishes:
  - `services/geometry.py` (frappe-free steel-weight + parts math).
  - The native lifecycle spine on the SCL controller: release from `on_submit`, retirement + cascade from `on_cancel`, framework-gated delete from `on_trash`, and the class attribute `ignore_linked_doctypes = ["BOM"]`. The `apply_workflow` override + `before_workflow_action` + `frappe.flags.selected_workflow_action` plumbing is **removed**.
  - `Layout Finished Part.generated_bom` (Link → BOM) column.
- **Phase 2 (export)** — produces, and this plan **extends**:
  - `services/export_service.py` with the frappe-free single-page core. Phase 2's export model is **dict-based** (verified against the Phase 2 plan; re-confirm the exact names by reading the file before Task 1 and note any drift in your task notes):
    - `build_cell_map(layout_dict) -> dict[str, value]` — codifies the §10.3 cell map (e.g. `B1`=company, `G5`=part name, `N5`=joined part numbers, `K14`=parts/sheet) from a plain layout dict. There is **no** `LayoutView` dataclass and **no** `populate_layout_sheet`.
    - `render_workbook_bytes(layout_dict, template_path) -> bytes` — opens the `FRM/PRD/15` template, applies `build_cell_map`, and returns single-sheet `.xlsx` bytes.
    - `default_template_path()` (and module constant `TEMPLATE_PATH`) — resolves `sheet_cutting_layout/templates/iatf/sheet_cutting_layout.xlsx`. There is **no** `load_template_workbook`.
  - The whitelisted entry point `download_sheet_cutting_layout(name)` on the SCL controller (streams via `frappe.response["type"]="binary"`, **not** `provide_binary_file`) + its module-level `_export_layout_dict(doc)` dict extractor + the "Download Layout (Excel)" form button.
- **Phase 3 (recursion)** — produces, and this plan **consumes**:
  - `Layout End Piece.child_layout` (Link → Sheet Cutting Layout; `depends_on: disposition == "Reuse"`).
  - The no-cycle guard on `child_layout` (a layout cannot be its own ancestor), which guarantees the traversal in this plan terminates.
  - The `on_cancel` cross-layout cascade that cancels downstream `child_layout` layouts depth-first and deactivates their BOMs.

> **Before writing any code:** open `sheet_cutting_layout/services/export_service.py` and `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py` as they exist post-Phase-2/Phase-3 and confirm the symbol names above. The tasks below are written against the **contract names**; reconcile any differences in your first task and keep the rest of the plan consistent.

## File structure

| File | Create / Modify | Responsibility |
|---|---|---|
| `sheet_cutting_layout/services/export_service.py` | Modify | Add frappe-free `walk_layout_tree(layout, fetch_child)` (depth-first layout-document expansion), `unique_sheet_title(base, used)` (stable/unique openpyxl-safe titles ≤31 chars), and `build_multi_sheet_workbook(pages)` (one worksheet per `(title, layout_dict)` page via the existing `build_cell_map`). Keep the single-page core untouched. |
| `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py` | Modify | Update the whitelisted `download_sheet_cutting_layout(name)` entry point to walk `child_layout` links via `frappe.get_doc`, build `(layout.name, _export_layout_dict(layout))` pages, build the multi-sheet workbook, and stream it through the existing Phase 2 `frappe.response` (`type="binary"`) path. |
| `sheet_cutting_layout/tests/test_export_service_recursion.py` | Create | Unit tests for `walk_layout_tree`, `unique_sheet_title`, and `build_multi_sheet_workbook` (frappe-free domain logic, run under `FrappeTestCase` via the bench runner). |
| `sheet_cutting_layout/tests/test_download_sheet_cutting_layout_recursion.py` | Create | Integration test: a persisted 2-level recursive + LH/RH layout → `download_sheet_cutting_layout` → multi-sheet workbook with correct per-sheet cell values. |
| `cypress/integration/sheet_cutting_layout_export_recursion.js` | Create | E2E: LH/RH + child layout → release → download multi-sheet `.xlsx` → supersede parent → assert cascade retirement. |

---

## Task group A: Frappe-free multi-sheet domain logic

### Task 1: Reconcile contract names + add `walk_layout_tree` traversal

**Files:**
- Read first: `sheet_cutting_layout/services/export_service.py` (entire file, as produced by Phase 2) and `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json` (confirm `child_layout` exists, fieldtype `Link`, options `Sheet Cutting Layout`).
- Modify: `sheet_cutting_layout/services/export_service.py` (append new frappe-free functions after the existing single-page core; do not edit existing functions).
- Test: `sheet_cutting_layout/tests/test_export_service_recursion.py` (Create).

`walk_layout_tree` is pure: it takes a layout-like object exposing `name` and `end_pieces` (each end-piece row exposing `disposition` and `child_layout`), plus a `fetch_child(name) -> layout` callable, and returns the parent layout followed by every descendant child layout in depth-first order. It does **not** import frappe. The `fetch_child` callable is injected by the controller (which uses `frappe.get_doc`); tests inject a dict-backed fake. A `visited` set keyed on `name` makes the walk defensive even though Phase 3's cycle guard already forbids cycles.

- [ ] **Reconcile the Phase 2 export contract before writing any code.** Read `sheet_cutting_layout/services/export_service.py` in full and `_export_layout_dict` in `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`, and record in your task notes the **exact** symbol names and the **exact** per-page field list Phase 2 produces. The Phase 2 plan ships a **dict-based** export model, not a `LayoutView` dataclass; verify against the real file and write down which of these you find:
  - The per-page export model: Phase 2 builds a plain **`dict`** (returned by `_export_layout_dict(doc)`), not a `LayoutView` object. Record its exact keys: `company`, `part_name` (mapped from `finished_part_code`), `part_numbers` (list), `is_lh_rh`, `orientation`, `project`, `project_name`, `sheet_thickness_mm`, `sheet_width_mm`, `sheet_length_mm`, `weight_of_strip_kg`, `strip_thickness_mm`, `strip_width_mm`, `strip_length_mm`, `parts_per_strip`, `no_of_strips`, `parts_per_sheet`, `gross_weight_per_part_kg`, `net_weight_per_part_kg`, `scrap_weight_per_part_kg`, `raw_material_weight_kg`, `end_pieces` (list of dicts). Confirm this list against the real file and correct any drift.
  - **The layout-identifier / sheet-title source.** The page dict has **no** `sheet_title` and **no** `layout_name` field. The human-meaningful per-page title comes from the **layout document's `name`** (used by Phase 2's `download_sheet_cutting_layout` as `f"{doc.name}.xlsx"`); the part-name cell is `dict["part_name"]` (which Phase 2 maps from `finished_part_code`). Record that the **per-page worksheet title base is the layout doc `name`** (`L1`, `SCL-…`), not a field on the export dict — Tasks 3/5 use this.
  - The cell-applying functions: `build_cell_map(layout_dict) -> dict[str, value]` (the §10.3 cell map; `B1`=company, `G5`=part name, `N5`=joined part numbers, `K14`=parts/sheet) and `render_workbook_bytes(layout_dict, template_path) -> bytes`.
  - The template loader: `default_template_path()` (and module constant `TEMPLATE_PATH`); Phase 2 has **no** `load_template_workbook`, `LayoutView`, `layout_view_from_doc`, `populate_layout_sheet`, or `build_layout_workbook`/`render_workbook`.

  Write down the real-name → contract-name mapping in your task notes and **substitute the real Phase 2 names in every code block in Tasks 3, 4, and 5 below** (those blocks are written against the `LayoutView`/`populate_layout_sheet` contract names; replace them with the dict + `build_cell_map`/`render_workbook_bytes` symbols you recorded here). `walk_layout_tree` itself (this task) is unaffected — it operates on the layout **document** objects, not on the export dict, so it needs no rename.
- [ ] Write the failing test file `sheet_cutting_layout/tests/test_export_service_recursion.py`:

```python
from __future__ import annotations

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase
from sheet_cutting_layout.services.export_service import walk_layout_tree


class _FakeEndPiece:
    def __init__(self, disposition="Scrap", child_layout=None):
        self.disposition = disposition
        self.child_layout = child_layout


class _FakeLayout:
    def __init__(self, name, end_pieces=None):
        self.name = name
        self.end_pieces = end_pieces or []


class WalkLayoutTreeTest(SheetCuttingLayoutTestCase):
    def _registry(self, *layouts):
        registry = {layout.name: layout for layout in layouts}
        return lambda name: registry[name]

    def test_layout_without_children_yields_only_parent(self):
        parent = _FakeLayout(
            "L1",
            end_pieces=[
                _FakeEndPiece(disposition="Scrap"),
                _FakeEndPiece(disposition="Reuse", child_layout=None),
            ],
        )
        pages = list(walk_layout_tree(parent, self._registry(parent)))
        self.assertEqual([page.name for page in pages], ["L1"])

    def test_single_child_layout_appended_after_parent(self):
        child = _FakeLayout("L2")
        parent = _FakeLayout(
            "L1",
            end_pieces=[_FakeEndPiece(disposition="Reuse", child_layout="L2")],
        )
        pages = list(walk_layout_tree(parent, self._registry(parent, child)))
        self.assertEqual([page.name for page in pages], ["L1", "L2"])

    def test_two_level_recursion_is_depth_first(self):
        grandchild = _FakeLayout("L3")
        child = _FakeLayout(
            "L2",
            end_pieces=[_FakeEndPiece(disposition="Reuse", child_layout="L3")],
        )
        parent = _FakeLayout(
            "L1",
            end_pieces=[_FakeEndPiece(disposition="Reuse", child_layout="L2")],
        )
        pages = list(
            walk_layout_tree(parent, self._registry(parent, child, grandchild))
        )
        self.assertEqual([page.name for page in pages], ["L1", "L2", "L3"])

    def test_two_children_preserve_end_piece_order(self):
        child_a = _FakeLayout("L2A")
        child_b = _FakeLayout("L2B")
        parent = _FakeLayout(
            "L1",
            end_pieces=[
                _FakeEndPiece(disposition="Reuse", child_layout="L2A"),
                _FakeEndPiece(disposition="Reuse", child_layout="L2B"),
            ],
        )
        pages = list(
            walk_layout_tree(parent, self._registry(parent, child_a, child_b))
        )
        self.assertEqual([page.name for page in pages], ["L1", "L2A", "L2B"])

    def test_visited_guard_breaks_a_cycle(self):
        parent = _FakeLayout("L1")
        child = _FakeLayout(
            "L2",
            end_pieces=[_FakeEndPiece(disposition="Reuse", child_layout="L1")],
        )
        parent.end_pieces = [_FakeEndPiece(disposition="Reuse", child_layout="L2")]
        pages = list(walk_layout_tree(parent, self._registry(parent, child)))
        self.assertEqual([page.name for page in pages], ["L1", "L2"])
```

- [ ] Run it from `/Users/gurudattkulkarni/Workspace/bench15` and see it FAIL:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service_recursion`
  Expected failure: `ImportError: cannot import name 'walk_layout_tree' from 'sheet_cutting_layout.services.export_service'`.
- [ ] Add the minimal implementation. Append to `sheet_cutting_layout/services/export_service.py`:

```python
def walk_layout_tree(layout, fetch_child):
    """Yield the layout then each descendant child layout, depth-first.

    Frappe-free. ``layout`` exposes ``name`` and ``end_pieces`` (rows with
    ``disposition`` and ``child_layout``). ``fetch_child(name)`` resolves a
    child layout by name; the controller injects ``frappe.get_doc`` and tests
    inject a dict lookup. A ``visited`` set keyed on ``name`` makes the walk
    terminate even if an unexpected cycle slips past the Phase 3 guard.
    """
    visited: set[str] = set()
    yield from _walk_layout_tree(layout, fetch_child, visited)


def _walk_layout_tree(layout, fetch_child, visited):
    name = str(getattr(layout, "name", "") or "").strip()
    if name in visited:
        return
    visited.add(name)
    yield layout

    for row in getattr(layout, "end_pieces", []) or []:
        if str(getattr(row, "disposition", "") or "").strip() != "Reuse":
            continue
        child_name = str(getattr(row, "child_layout", "") or "").strip()
        if not child_name or child_name in visited:
            continue
        child = fetch_child(child_name)
        yield from _walk_layout_tree(child, fetch_child, visited)
```

- [ ] Run the test again and see it PASS:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service_recursion`
- [ ] Run the lint/format gates from the app dir `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `python -m ruff check .` and `python -m ruff format --check .`
- [ ] Commit:
  `git add sheet_cutting_layout/services/export_service.py sheet_cutting_layout/tests/test_export_service_recursion.py && git commit -m "$(printf 'feat: add frappe-free walk_layout_tree for recursive export\n\nDepth-first expansion of a parent layout plus every descendant\nchild_layout into an ordered page list, with a visited guard.\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"`

---

### Task 2: Stable, unique, openpyxl-safe worksheet titles

**Files:**
- Modify: `sheet_cutting_layout/services/export_service.py` (append `unique_sheet_title`).
- Test: `sheet_cutting_layout/tests/test_export_service_recursion.py` (add a test class).

openpyxl 3.1.5 (verified in bench15) rejects worksheet titles containing any of `\ * ? : / [ ]` and warns/breaks past **31 characters** (`openpyxl/workbook/child.py:74,90,98`, `INVALID_TITLE_REGEX = re.compile(r'[\\*?:/\[\]]')`). Layout names like `SCL-0102AAG06400/6410N-R1` can exceed 31 chars and contain `/`, so the base must be sanitized and truncated, then de-duplicated within the workbook with a numeric suffix while staying ≤31. `unique_sheet_title` is pure: it takes the desired base string and the set of titles already used, and returns a safe unique title; the caller records the returned title in the used-set.

- [ ] Add the failing test class to `sheet_cutting_layout/tests/test_export_service_recursion.py`:

```python
from sheet_cutting_layout.services.export_service import unique_sheet_title


class UniqueSheetTitleTest(SheetCuttingLayoutTestCase):
    def test_plain_title_passes_through(self):
        self.assertEqual(unique_sheet_title("L1", set()), "L1")

    def test_invalid_characters_are_replaced_with_underscore(self):
        title = unique_sheet_title("SCL/0102:AAG[06400]", set())
        for forbidden in "\\/*?:[]":
            self.assertNotIn(forbidden, title)

    def test_title_is_truncated_to_31_characters(self):
        title = unique_sheet_title("A" * 50, set())
        self.assertLessEqual(len(title), 31)
        self.assertEqual(title, "A" * 31)

    def test_duplicate_titles_get_a_numeric_suffix(self):
        used = {"L1"}
        title = unique_sheet_title("L1", used)
        self.assertEqual(title, "L1 (2)")

    def test_suffix_keeps_title_within_31_characters(self):
        used = {"A" * 31}
        title = unique_sheet_title("A" * 31, used)
        self.assertLessEqual(len(title), 31)
        self.assertNotEqual(title, "A" * 31)
        self.assertTrue(title.endswith("(2)"))

    def test_empty_base_falls_back_to_sheet(self):
        self.assertEqual(unique_sheet_title("", set()), "Sheet")
```

- [ ] Run it and see it FAIL:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service_recursion`
  Expected failure: `ImportError: cannot import name 'unique_sheet_title' from 'sheet_cutting_layout.services.export_service'`.
- [ ] Add the minimal implementation. Append to `sheet_cutting_layout/services/export_service.py`:

```python
import re

_INVALID_SHEET_TITLE_CHARS = re.compile(r"[\\*?:/\[\]]")
_MAX_SHEET_TITLE_LENGTH = 31


def unique_sheet_title(base, used):
    """Return an openpyxl-safe (<=31 chars, no ``\\ * ? : / [ ]``) title that
    is unique within ``used``. ``used`` is read-only here; the caller adds the
    returned title to its own set.
    """
    title = _INVALID_SHEET_TITLE_CHARS.sub("_", str(base or "").strip())
    title = title[:_MAX_SHEET_TITLE_LENGTH] or "Sheet"
    if title not in used:
        return title

    for index in range(2, 10000):
        suffix = f" ({index})"
        trimmed = title[: _MAX_SHEET_TITLE_LENGTH - len(suffix)]
        candidate = f"{trimmed}{suffix}"
        if candidate not in used:
            return candidate
    raise ValueError(f"Could not build a unique sheet title from {base!r}")
```

- [ ] Run the test again and see it PASS:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service_recursion`
- [ ] Run lint/format from `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `python -m ruff check .` and `python -m ruff format --check .`
- [ ] Commit:
  `git add sheet_cutting_layout/services/export_service.py sheet_cutting_layout/tests/test_export_service_recursion.py && git commit -m "$(printf 'feat: add unique_sheet_title for multi-sheet export\n\nSanitize invalid openpyxl title chars, cap at 31 chars, and\nde-duplicate within a workbook with a numeric suffix.\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"`

---

### Task 3: `build_multi_sheet_workbook` — one worksheet per page

**Files:**
- Read first: re-confirm the Phase 2 export symbols you recorded in Task 1 — the page is a plain `dict` (from `_export_layout_dict`), the cell map is `build_cell_map(layout_dict)`, and the template loader is `default_template_path()`. (Phase 2 has no `LayoutView`/`populate_layout_sheet`/`load_template_workbook` — see Task 1's reconciliation step.)
- Modify: `sheet_cutting_layout/services/export_service.py` (append `build_multi_sheet_workbook`).
- Test: `sheet_cutting_layout/tests/test_export_service_recursion.py` (add a test class).

`build_multi_sheet_workbook` is frappe-free: it takes an ordered list of `(title, layout_dict)` page tuples (already expanded by the controller via `walk_layout_tree` + `_export_layout_dict`, with `title` set to each layout document's `name`), opens the `FRM/PRD/15` template **once per page** via `default_template_path()` to get a fresh templated worksheet, titles each worksheet with `unique_sheet_title`, fills it via the existing `build_cell_map` cell map, and returns a single `openpyxl.Workbook` whose worksheets appear in page order. The first page reuses the workbook the template loader returns; subsequent pages copy the template's single worksheet into that same workbook so every sheet keeps the curated `FRM/PRD/15` layout.

The per-page worksheet title base is the **layout document `name`** (the identifier recorded in Task 1), passed in as the tuple's `title` element — the export dict itself carries no `sheet_title`/`layout_name` field, so the controller supplies it. Each page's `part_name` cell (`G5`) still comes from `build_cell_map(layout_dict)`.

- [ ] Add the failing test class to `sheet_cutting_layout/tests/test_export_service_recursion.py`:

```python
from sheet_cutting_layout.services.export_service import build_multi_sheet_workbook


class BuildMultiSheetWorkbookTest(SheetCuttingLayoutTestCase):
    def _page(self, name, part_name="Bracket", part_numbers=None):
        # A page is a (title, layout_dict) tuple. ``title`` is the layout
        # document name (the recorded identifier); the dict uses the real
        # Phase 2 build_cell_map keys. Only the keys the assertions below read
        # are populated; build_cell_map renders missing numerics as "".
        layout_dict = {
            "company": "Test Co",
            "part_name": part_name,
            "part_numbers": part_numbers or ["P-001"],
            "is_lh_rh": False,
            "project": "PRJ",
            "project_name": "Project",
            "parts_per_sheet": 2,
            "end_pieces": [],
        }
        return (name, layout_dict)

    def test_single_page_workbook_has_one_sheet(self):
        workbook = build_multi_sheet_workbook([self._page("L1")])
        self.assertEqual(workbook.sheetnames, ["L1"])

    def test_one_worksheet_per_page_in_order(self):
        pages = [self._page("L1"), self._page("L2"), self._page("L3")]
        workbook = build_multi_sheet_workbook(pages)
        self.assertEqual(workbook.sheetnames, ["L1", "L2", "L3"])

    def test_duplicate_page_titles_are_made_unique(self):
        pages = [self._page("DUP"), self._page("DUP")]
        workbook = build_multi_sheet_workbook(pages)
        self.assertEqual(workbook.sheetnames, ["DUP", "DUP (2)"])

    def test_each_sheet_carries_its_own_part_name(self):
        pages = [
            self._page("L1", part_name="Parent Bracket"),
            self._page("L2", part_name="End Piece Bracket"),
        ]
        workbook = build_multi_sheet_workbook(pages)
        # G5 is the part-name cell in the codified map (spec §10.3).
        self.assertEqual(workbook["L1"]["G5"].value, "Parent Bracket")
        self.assertEqual(workbook["L2"]["G5"].value, "End Piece Bracket")

    def test_empty_page_list_raises(self):
        with self.assertRaises(ValueError):
            build_multi_sheet_workbook([])
```

- [ ] Run it and see it FAIL:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service_recursion`
  Expected failure: `ImportError: cannot import name 'build_multi_sheet_workbook' from 'sheet_cutting_layout.services.export_service'`.
- [ ] Add the minimal implementation. Append to `sheet_cutting_layout/services/export_service.py`. Use the **real Phase 2 dict contract you recorded in Task 1**: pages are `(title, layout_dict)` tuples (the `title` is the layout document `name` — the recorded identifier, since the export dict has no `sheet_title`/`layout_name` field), the template is opened via `default_template_path()` + `openpyxl.load_workbook`, and each worksheet's cells are filled by `build_cell_map(layout_dict)` (the §10.3 cell map, exactly as `render_workbook_bytes` does it):

```python
from copy import copy as _copy

from openpyxl import load_workbook


def build_multi_sheet_workbook(pages):
    """Build one ``openpyxl.Workbook`` with one worksheet per page.

    ``pages`` is an ordered list of ``(title, layout_dict)`` tuples (parent
    first, then each descendant child layout, as produced by the controller
    from ``walk_layout_tree`` + ``_export_layout_dict``). ``title`` is the
    layout document ``name`` (the recorded page identifier). Each worksheet
    uses the curated FRM/PRD/15 template and is filled by the existing
    single-page cell map ``build_cell_map``.
    """
    pages = list(pages)
    if not pages:
        raise ValueError("Cannot build a workbook without at least one layout page")

    used_titles: set[str] = set()
    workbook = None

    for index, (page_title, layout_dict) in enumerate(pages):
        template = load_workbook(default_template_path())
        source_ws = template.active
        base = str(page_title or "")
        title = unique_sheet_title(base, used_titles)
        used_titles.add(title)

        if index == 0:
            workbook = template
            worksheet = source_ws
            worksheet.title = title
        else:
            worksheet = _clone_template_worksheet(workbook, source_ws, title)

        for coordinate, value in build_cell_map(layout_dict).items():
            worksheet[coordinate] = value if value != "" else None

    return workbook


def _clone_template_worksheet(workbook, source_ws, title):
    """Copy the curated template worksheet (values + cell styles) into
    ``workbook`` under ``title`` and return the new worksheet."""
    worksheet = workbook.create_sheet(title=title)
    for row in source_ws.iter_rows():
        for cell in row:
            target = worksheet.cell(row=cell.row, column=cell.column, value=cell.value)
            if cell.has_style:
                target.font = _copy(cell.font)
                target.border = _copy(cell.border)
                target.fill = _copy(cell.fill)
                target.number_format = _copy(cell.number_format)
                target.protection = _copy(cell.protection)
                target.alignment = _copy(cell.alignment)
    for merged_range in list(source_ws.merged_cells.ranges):
        worksheet.merge_cells(str(merged_range))
    for column_letter, dimension in source_ws.column_dimensions.items():
        worksheet.column_dimensions[column_letter].width = dimension.width
    for row_index, dimension in source_ws.row_dimensions.items():
        worksheet.row_dimensions[row_index].height = dimension.height
    return worksheet
```

- [ ] Run the test again and see it PASS:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service_recursion`
- [ ] Run lint/format from `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `python -m ruff check .` and `python -m ruff format --check .`
- [ ] Commit:
  `git add sheet_cutting_layout/services/export_service.py sheet_cutting_layout/tests/test_export_service_recursion.py && git commit -m "$(printf 'feat: build multi-sheet IATF workbook from layout pages\n\nOne curated FRM/PRD/15 worksheet per parent + child layout, titled\nuniquely and populated via the single-page cell-map.\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"`

---

## Task group B: Frappe entry-point integration

### Task 4: Walk `child_layout` links in `download_sheet_cutting_layout`

**Files:**
- Read first: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py` — confirm the Phase 2 `download_sheet_cutting_layout(name)` body (whitelist decorator, permission check, single-page `render_workbook_bytes` build, and the `frappe.response["filename"]/["filecontent"]/["type"]="binary"` streaming) and the `_export_layout_dict(doc)` helper it calls.
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py` — replace the single-page workbook build inside `download_sheet_cutting_layout` with the multi-sheet walk.
- Test: `sheet_cutting_layout/tests/test_download_sheet_cutting_layout_recursion.py` (Create).

The entry point loads the parent layout, walks its `child_layout` tree with `frappe.get_doc` as `fetch_child`, converts each layout doc to a `(doc.name, _export_layout_dict(doc))` page tuple (reusing the Phase 2 dict extractor), builds the multi-sheet workbook with `build_multi_sheet_workbook`, serializes it to bytes with `workbook.save(BytesIO())`, and streams it through the **same Phase 2 `frappe.response` download pattern** (`frappe.response["filename"] = f"{doc.name}.xlsx"`, `["filecontent"] = bytes`, `["type"] = "binary"`). Permission stays read-checked via `doc.check_permission("read")` (matching the Phase 2 pattern).

> Note: `fetch_child` is `frappe.get_doc("Sheet Cutting Layout", child_name)`, which returns a **full layout document** — its `.end_pieces` attribute is the materialized child-table rows (doc objects), so `getattr(row, "child_layout", "")` and `getattr(row, "disposition", "")` inside `walk_layout_tree` read real values without any extra fetch.

This integration test persists a real 2-level recursive layout. To stay self-contained, it builds items, a project, the parent layout (with an end piece whose `child_layout` points at a persisted child layout that has its own end piece), and asserts the returned workbook has two worksheets (parent + one child) with the right per-sheet header cell. It does **not** require release — the export reads the layout tree directly, independent of BOM generation.

- [ ] Write the failing test file `sheet_cutting_layout/tests/test_download_sheet_cutting_layout_recursion.py`:

```python
from __future__ import annotations

from io import BytesIO

import frappe
from openpyxl import load_workbook

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase
from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.sheet_cutting_layout import (
    download_sheet_cutting_layout,
)


class DownloadRecursiveLayoutTest(SheetCuttingLayoutTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.suffix = frappe.generate_hash(length=6)
        cls.project = cls._make_project()
        cls.raw_material = cls._make_item("RM")
        cls.scrap_item = cls._make_item("SCRAP")
        cls.parent_part = cls._make_item("PARENTSHR")
        cls.end_piece_item = cls._make_item("ENDPIECESHR")
        cls.child_part = cls._make_item("CHILDSHR")
        cls.child = cls._make_child_layout()
        cls.parent = cls._make_parent_layout()

    @classmethod
    def _make_project(cls):
        name = f"SCLP{cls.suffix}"
        if not frappe.db.exists("Project", name):
            frappe.get_doc({"doctype": "Project", "project_name": name, "name": name}).insert()
        return name

    @classmethod
    def _make_item(cls, kind):
        code = f"SCL{kind}{cls.suffix}"
        if not frappe.db.exists("Item", code):
            frappe.get_doc(
                {
                    "doctype": "Item",
                    "item_code": code,
                    "item_name": code,
                    "item_group": "All Item Groups",
                    "stock_uom": "Kg",
                    "is_stock_item": 1,
                }
            ).insert()
        return code

    @classmethod
    def _strip_fields(cls):
        return {
            "sheet_thickness_mm": 2,
            "sheet_width_mm": 1000,
            "sheet_length_mm": 2000,
            "weight_per_sheet_kg": 31.44,
            "strip_thickness_mm": 2,
            "strip_width_mm": 1000,
            "strip_length_mm": 1000,
            "weight_of_strip_kg": 15.72,
            "parts_per_strip": 1,
            "no_of_strips": 2,
            "parts_per_sheet": 2,
        }

    @classmethod
    def _make_child_layout(cls):
        doc = frappe.get_doc(
            {
                "doctype": "Sheet Cutting Layout",
                "layout_code": f"SCLCHILD{cls.suffix}",
                "project": cls.project,
                "revision_no": 1,
                "is_active": 0,
                "status": "Draft",
                "raw_material_item": cls.end_piece_item,
                "process_scrap_item": cls.scrap_item,
                "finished_part_code": cls.child_part,
                "net_weight_per_part_kg": 7.0,
                "gross_weight_per_part_kg": 7.5,
                "scrap_weight_per_part_kg": 0.5,
                "end_pieces": [
                    {
                        "doctype": "Layout End Piece",
                        "width_mm": 200,
                        "length_mm": 300,
                        "weight_kg": 0.94,
                        "disposition": "Scrap",
                        "scrap_item": cls.scrap_item,
                    }
                ],
                **cls._strip_fields(),
            }
        )
        doc.insert()
        return doc.name

    @classmethod
    def _make_parent_layout(cls):
        doc = frappe.get_doc(
            {
                "doctype": "Sheet Cutting Layout",
                "layout_code": f"SCLPARENT{cls.suffix}",
                "project": cls.project,
                "revision_no": 1,
                "is_active": 0,
                "status": "Draft",
                "raw_material_item": cls.raw_material,
                "process_scrap_item": cls.scrap_item,
                "finished_part_code": cls.parent_part,
                "net_weight_per_part_kg": 15.52,
                "gross_weight_per_part_kg": 15.72,
                "scrap_weight_per_part_kg": 0.2,
                "end_pieces": [
                    {
                        "doctype": "Layout End Piece",
                        "end_piece_item_code": cls.end_piece_item,
                        "width_mm": 400,
                        "length_mm": 500,
                        "weight_kg": 3.14,
                        "disposition": "Reuse",
                        "used_for_finished_part": cls.child_part,
                        "bom_quantity": 2,
                        "child_layout": cls.child,
                    }
                ],
                **cls._strip_fields(),
            }
        )
        doc.insert()
        return doc.name

    def _download_workbook(self):
        frappe.response.clear()
        download_sheet_cutting_layout(self.parent)
        content = frappe.response["filecontent"]
        return load_workbook(BytesIO(content))

    def test_download_returns_xlsx_response(self):
        frappe.response.clear()
        download_sheet_cutting_layout(self.parent)
        self.assertEqual(frappe.response["type"], "binary")
        self.assertTrue(frappe.response["filename"].endswith(".xlsx"))

    def test_workbook_has_one_sheet_per_layout_in_tree(self):
        workbook = self._download_workbook()
        self.assertEqual(len(workbook.sheetnames), 2)

    def test_parent_and_child_sheets_carry_distinct_part_numbers(self):
        workbook = self._download_workbook()
        # N5 holds the joined part number(s) in the codified map (spec §10.3).
        part_numbers = {workbook[name]["N5"].value for name in workbook.sheetnames}
        self.assertIn(self.parent_part, part_numbers)
        self.assertIn(self.child_part, part_numbers)
```

- [ ] Run it from `/Users/gurudattkulkarni/Workspace/bench15` and see it FAIL:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_download_sheet_cutting_layout_recursion`
  Expected failure: the Phase 2 single-page entry point produces a workbook with **one** sheet, so `test_workbook_has_one_sheet_per_layout_in_tree` fails with `AssertionError: 1 != 2` and `test_parent_and_child_sheets_carry_distinct_part_numbers` fails because the child part number is absent.
- [ ] Replace the single-page build in `download_sheet_cutting_layout`. Read the existing Phase 2 function, keep its whitelist decorator + permission check, and swap the single-page `render_workbook_bytes(...)` call for the multi-sheet walk, **keeping the same Phase 2 `frappe.response` streaming** (so the existing `frappe.response`-based tests still pass). Reuse the Phase 2 module-level `_export_layout_dict` helper that already lives in this file. The resulting function body:

```python
@whitelist()
def download_sheet_cutting_layout(name: str) -> None:
    if not frappe:
        raise RuntimeError("Frappe is required to export Sheet Cutting Layout")

    from io import BytesIO

    from sheet_cutting_layout.services.export_service import (
        build_multi_sheet_workbook,
        walk_layout_tree,
    )

    doc = frappe.get_doc("Sheet Cutting Layout", name)
    check_permission = getattr(doc, "check_permission", None)
    if callable(check_permission):
        check_permission("read")

    def fetch_child(child_name: str) -> object:
        return frappe.get_doc("Sheet Cutting Layout", child_name)

    pages = [
        (layout.name, _export_layout_dict(layout))
        for layout in walk_layout_tree(doc, fetch_child)
    ]
    workbook = build_multi_sheet_workbook(pages)

    stream = BytesIO()
    workbook.save(stream)
    frappe.response["filename"] = f"{doc.name}.xlsx"
    frappe.response["filecontent"] = stream.getvalue()
    frappe.response["type"] = "binary"
```

- [ ] Run the test again and see it PASS:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_download_sheet_cutting_layout_recursion`
- [ ] Re-run the Phase 2 single-page download test to confirm no regression (find it by listing the tests dir; the file is the Phase 2 download test, e.g. `test_download_sheet_cutting_layout`):
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_download_sheet_cutting_layout`
  Expected: still green (a childless layout produces a single-sheet workbook).
- [ ] Run lint/format from `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `python -m ruff check .` and `python -m ruff format --check .`
- [ ] Commit:
  `git add sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py sheet_cutting_layout/tests/test_download_sheet_cutting_layout_recursion.py && git commit -m "$(printf 'feat: export recursive layout tree as multi-sheet workbook\n\ndownload_sheet_cutting_layout now walks child_layout links and emits\none FRM/PRD/15 worksheet per parent and descendant layout.\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"`

---

### Task 5: Integration — release a 2-level recursive + LH/RH layout and export it

**Files:**
- Modify: `sheet_cutting_layout/tests/test_download_sheet_cutting_layout_recursion.py` — add a release-then-export class.
- Test path: same file.

This proves the full data path across §8 (LH/RH), §9 (recursion), and §10 (export): a released parent that is both LH/RH **and** has a child layout exports a multi-sheet workbook whose parent sheet shows the **joined** LH_RH part number and whose child sheet shows the child part. The release goes through the native `on_submit` spine (Phase 0): set the workflow `status` to `Released` and call `doc.submit()`. The twin (`twin_finished_part`) makes the parent's joined part-number cell carry both codes (spec §8.4 / §10.3 cell `N5`).

- [ ] Add this class to `sheet_cutting_layout/tests/test_download_sheet_cutting_layout_recursion.py`:

```python
class DownloadReleasedRecursiveLhRhTest(SheetCuttingLayoutTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.suffix = frappe.generate_hash(length=6)
        cls.project = DownloadRecursiveLayoutTest._make_project.__func__(cls)
        cls.raw_material = DownloadRecursiveLayoutTest._make_item.__func__(cls, "RM")
        cls.scrap_item = DownloadRecursiveLayoutTest._make_item.__func__(cls, "SCRAP")
        cls.parent_part = DownloadRecursiveLayoutTest._make_item.__func__(cls, "PARENTSHR")
        cls.twin_part = DownloadRecursiveLayoutTest._make_item.__func__(cls, "PARENTTWINSHR")
        cls.end_piece_item = DownloadRecursiveLayoutTest._make_item.__func__(cls, "ENDPIECESHR")
        cls.child_part = DownloadRecursiveLayoutTest._make_item.__func__(cls, "CHILDSHR")
        cls.child = DownloadRecursiveLayoutTest._make_child_layout.__func__(cls)
        cls.parent = cls._make_lhrh_parent_layout()
        cls._release(cls.child)
        cls._release(cls.parent)

    @classmethod
    def _make_lhrh_parent_layout(cls):
        doc = frappe.get_doc(
            {
                "doctype": "Sheet Cutting Layout",
                "layout_code": f"SCLLHRH{cls.suffix}",
                "project": cls.project,
                "revision_no": 1,
                "is_active": 0,
                "status": "Draft",
                "raw_material_item": cls.raw_material,
                "process_scrap_item": cls.scrap_item,
                "finished_part_code": cls.parent_part,
                "is_lh_rh": 1,
                "orientation": "LH",
                "twin_finished_part": cls.twin_part,
                "net_weight_per_part_kg": 15.52,
                "gross_weight_per_part_kg": 15.72,
                "scrap_weight_per_part_kg": 0.2,
                "end_pieces": [
                    {
                        "doctype": "Layout End Piece",
                        "end_piece_item_code": cls.end_piece_item,
                        "width_mm": 400,
                        "length_mm": 500,
                        "weight_kg": 3.14,
                        "disposition": "Reuse",
                        "used_for_finished_part": cls.child_part,
                        "bom_quantity": 2,
                        "child_layout": cls.child,
                    }
                ],
                **DownloadRecursiveLayoutTest._strip_fields.__func__(cls),
            }
        )
        doc.insert()
        return doc.name

    @classmethod
    def _release(cls, name):
        doc = frappe.get_doc("Sheet Cutting Layout", name)
        doc.status = "Released"
        doc.submit()

    def test_released_parent_sheet_shows_joined_lh_rh_part_number(self):
        frappe.response.clear()
        download_sheet_cutting_layout(self.parent)
        workbook = load_workbook(BytesIO(frappe.response["filecontent"]))
        joined = workbook[workbook.sheetnames[0]]["N5"].value
        self.assertIn(self.parent_part, joined)
        self.assertIn(self.twin_part, joined)

    def test_released_workbook_has_parent_and_child_sheets(self):
        frappe.response.clear()
        download_sheet_cutting_layout(self.parent)
        workbook = load_workbook(BytesIO(frappe.response["filecontent"]))
        self.assertEqual(len(workbook.sheetnames), 2)
        part_numbers = {workbook[name]["N5"].value for name in workbook.sheetnames}
        self.assertTrue(any(self.child_part in (value or "") for value in part_numbers))
```

- [ ] Run it and see it PASS (the multi-sheet machinery from Tasks 1-4 already satisfies it; this test pins the cross-phase contract):
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_download_sheet_cutting_layout_recursion`
  If `test_released_parent_sheet_shows_joined_lh_rh_part_number` fails, the bug is in Phase 2's joined-part-number rendering for `is_lh_rh` — the twin is appended to `part_numbers` by `_export_layout_dict` (controller) and `"_"`-joined by `_joined_part_numbers` inside `build_cell_map` (`N5`); fix it there (the join is `"_"`-joined per spec §8.4), re-run, then continue.
- [ ] Run the full app suite to confirm no cross-module regression:
  `bench --site development.localhost run-tests --app sheet_cutting_layout`
- [ ] Run lint/format from `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `python -m ruff check .` and `python -m ruff format --check .`
- [ ] Commit:
  `git add sheet_cutting_layout/tests/test_download_sheet_cutting_layout_recursion.py && git commit -m "$(printf 'test: integration export of released LH/RH + recursive layout\n\nReleased parent that is both LH/RH and has a child layout exports a\ntwo-sheet workbook with joined part numbers and the child page.\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"`

---

## Task group C: End-to-end arc

### Task 6: E2E — LH/RH + child layout → release → download → supersede → cascade retire

**Files:**
- Create: `cypress/integration/sheet_cutting_layout_export_recursion.js`.
- Test path: same file.

This single spec exercises the whole arc through the Desk UI + API, matching the style of the existing `cypress/integration/sheet_cutting_layout_release.js` (login, `cy.call("frappe.client.insert", …)`, `runWorkflowAction`, API polling). It: seeds items + project; inserts a released-via-workflow child layout and an LH/RH parent layout whose Reuse end piece links the child; drives both through the workflow to `Released`; downloads the parent's `.xlsx` via the whitelisted method and asserts a non-empty body; then supersedes the parent (the `Supersede` workflow action) and asserts the parent and the child layout both reach a retired state and their BOMs are deactivated.

The download endpoint returns a binary attachment; in Cypress we hit it with `cy.request` and assert a non-empty body and the spreadsheet content-type. Supersede ≡ Cancel (spec §4.2): after Phase 0 sets the `Superseded` workflow state to `doc_status: 2`, the UI **`Supersede`** action (transition `Released --Supersede--> Superseded`, the only action that drives docstatus 2 — verified in `fixtures/workflow.json`; there is no "Cancel" action) calls native `apply_workflow`, which runs `doc.cancel()` (verified: `apps/frappe/frappe/model/workflow.py:143-144`, the `is_submitted() and new_docstatus.is_cancelled()` branch); `on_cancel` then cascades to the child layout and deactivates the BOMs.

- [ ] Reconcile the retirement action before writing the spec: read `sheet_cutting_layout/fixtures/workflow.json` and confirm the transition whose `next_state` resolves to a `doc_status: 2` state is `"Supersede"` (`Released --Supersede--> Superseded`, with `Superseded` set to `doc_status: 2` by Phase 0). Confirm there is **no** `"Cancel"` action/transition. The E2E `runWorkflowAction(...)` call below must use `"Supersede"` — never `"Cancel"`. If the action label differs from `"Supersede"`, substitute the real label in the spec and note it in your task notes.
- [ ] Write the failing E2E spec `cypress/integration/sheet_cutting_layout_export_recursion.js`:

```javascript
describe("Sheet Cutting Layout export + recursion arc", () => {
	const suffix = Date.now();
	const project = `SCLEXPPROJ${suffix}`;
	const rawMaterialItem = `SCLEXPRM${suffix}`;
	const scrapItem = `SCLEXPSCRAP${suffix}`;
	const endPieceItem = `SCLEXPEP${suffix}`;
	const parentPart = `EXPPARENT${suffix}SHR`;
	const twinPart = `EXPTWIN${suffix}SHR`;
	const childPart = `EXPCHILD${suffix}SHR`;
	const childLayout = `SCLEXPCHILD${suffix}`;
	const parentLayout = `SCLEXPPARENT${suffix}`;
	let projectName;

	const stripFields = {
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
	};

	function runWorkflowAction(action, expectedStatus) {
		cy.contains(".actions-btn-group button, button", "Actions").click();
		cy.contains(".dropdown-menu a, .dropdown-menu button", action).click();
		cy.get("body").then(($body) => {
			if ($body.find(".modal:visible").length) {
				cy.get(".modal:visible").within(() => {
					cy.contains("button", "Yes").click();
				});
			}
		});
		cy.get(".modal:visible").should("not.exist");
		cy.get(".freeze:visible").should("not.exist");
		if (expectedStatus) {
			cy.contains('[data-fieldname="status"]', expectedStatus);
		}
	}

	function releaseLayout(layoutCode) {
		cy.visit(`/app/sheet-cutting-layout/${layoutCode}`);
		cy.contains('[data-fieldname="status"]', "Draft");
		runWorkflowAction("Submit for Check", "Submitted for Check");
		runWorkflowAction("Project Manager Approves", "PM Approved");
		runWorkflowAction("Purchase Approves", "Approved by Purchase");
		runWorkflowAction("MR Release", "Released");
	}

	function bomsForLayout(layoutCode) {
		return cy
			.request(
				"GET",
				`/api/method/frappe.client.get_list?doctype=BOM&filters=${encodeURIComponent(
					JSON.stringify([["sheet_cutting_layout", "=", layoutCode]])
				)}&fields=${encodeURIComponent(JSON.stringify(["name", "is_active", "docstatus"]))}`
			)
			.then(({ body }) => body.message);
	}

	before(() => {
		cy.login();
		cy.ensureHsnCode("720890");
		cy.call("frappe.client.insert", {
			doc: { doctype: "Project", name: project, project_name: project },
		}).then(({ message }) => {
			projectName = message.name;
		});
		[rawMaterialItem, scrapItem, endPieceItem, parentPart, twinPart, childPart].forEach(
			(itemCode) => {
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
			}
		);
		cy.call("frappe.client.insert", {
			doc: {
				doctype: "Sheet Cutting Layout",
				layout_code: childLayout,
				project,
				revision_no: 1,
				is_active: 0,
				status: "Draft",
				raw_material_item: endPieceItem,
				process_scrap_item: scrapItem,
				finished_part_code: childPart,
				net_weight_per_part_kg: 7.0,
				gross_weight_per_part_kg: 7.5,
				scrap_weight_per_part_kg: 0.5,
				end_pieces: [
					{
						doctype: "Layout End Piece",
						width_mm: 200,
						length_mm: 300,
						weight_kg: 0.94,
						disposition: "Scrap",
						scrap_item: scrapItem,
					},
				],
				...stripFields,
			},
		});
		cy.call("frappe.client.insert", {
			doc: {
				doctype: "Sheet Cutting Layout",
				layout_code: parentLayout,
				project,
				revision_no: 1,
				is_active: 0,
				status: "Draft",
				raw_material_item: rawMaterialItem,
				process_scrap_item: scrapItem,
				finished_part_code: parentPart,
				is_lh_rh: 1,
				orientation: "LH",
				twin_finished_part: twinPart,
				net_weight_per_part_kg: 15.52,
				gross_weight_per_part_kg: 15.72,
				scrap_weight_per_part_kg: 0.2,
				end_pieces: [
					{
						doctype: "Layout End Piece",
						end_piece_item_code: endPieceItem,
						width_mm: 400,
						length_mm: 500,
						weight_kg: 3.14,
						disposition: "Reuse",
						used_for_finished_part: childPart,
						bom_quantity: 2,
						child_layout: childLayout,
					},
				],
				...stripFields,
			},
		});
	});

	beforeEach(() => {
		cy.login();
	});

	it("releases, downloads a multi-sheet workbook, supersedes, and cascades retirement", () => {
		releaseLayout(childLayout);
		releaseLayout(parentLayout);

		// Download the multi-sheet Excel and assert a non-empty xlsx body.
		cy.request({
			method: "GET",
			url: `/api/method/sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.sheet_cutting_layout.download_sheet_cutting_layout?name=${parentLayout}`,
			encoding: "binary",
		}).then((response) => {
			expect(response.status).to.equal(200);
			expect(response.headers["content-type"]).to.match(/spreadsheet|octet-stream/);
			expect(response.body.length).to.be.greaterThan(1000);
		});

		// Supersede the parent (drives docstatus 2 -> doc.cancel());
		// on_cancel cascades to the child layout.
		cy.visit(`/app/sheet-cutting-layout/${parentLayout}`);
		runWorkflowAction("Supersede");
		cy.get(".freeze:visible").should("not.exist");

		// Parent and child layouts both reach docstatus=2 (cancelled).
		cy.request(
			"GET",
			`/api/method/frappe.client.get?doctype=Sheet%20Cutting%20Layout&name=${parentLayout}`
		).then(({ body }) => {
			expect(body.message.docstatus).to.equal(2);
		});
		cy.request(
			"GET",
			`/api/method/frappe.client.get?doctype=Sheet%20Cutting%20Layout&name=${childLayout}`
		).then(({ body }) => {
			expect(body.message.docstatus).to.equal(2);
		});

		// Every BOM the parent and child created is deactivated.
		bomsForLayout(parentLayout).then((boms) => {
			expect(boms.length).to.be.greaterThan(0);
			boms.forEach((bom) => expect(Boolean(bom.is_active)).to.equal(false));
		});
		bomsForLayout(childLayout).then((boms) => {
			expect(boms.length).to.be.greaterThan(0);
			boms.forEach((bom) => expect(Boolean(bom.is_active)).to.equal(false));
		});
	});
});
```

- [ ] Run it from `/Users/gurudattkulkarni/Workspace/bench15` and see it run end to end (it should PASS once Tasks 1-5 are merged; if it fails at download, the entry point is not wired; if it fails at the cascade assertions, the Phase 3 `on_cancel` cascade is not reaching the child — debug there, not in this spec):
  `bench --site development.localhost run-ui-tests sheet_cutting_layout --headless --spec cypress/integration/sheet_cutting_layout_export_recursion.js`
- [ ] If `--spec` is not honored by the bench wrapper on this version, run the whole UI suite and confirm the new spec is green:
  `bench --site development.localhost run-ui-tests sheet_cutting_layout --headless`
- [ ] Run lint/format from `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `python -m ruff check .` and `python -m ruff format --check .`
- [ ] Commit:
  `git add cypress/integration/sheet_cutting_layout_export_recursion.js && git commit -m "$(printf 'test: e2e export + recursion arc with cascade retirement\n\nLH/RH + child layout release, multi-sheet download, supersede, and\ncascading BOM deactivation through the Desk UI.\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"`

---

### Task 7: Full green gate before integration merge

**Files:** none (verification only).

- [ ] Run the full Python suite from `/Users/gurudattkulkarni/Workspace/bench15` and confirm green:
  `bench --site development.localhost run-tests --app sheet_cutting_layout`
- [ ] Run the full UI suite from `/Users/gurudattkulkarni/Workspace/bench15` and confirm green:
  `bench --site development.localhost run-ui-tests sheet_cutting_layout --headless`
- [ ] Run both lint gates from `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout` and confirm clean:
  `python -m ruff check .` and `python -m ruff format --check .`
- [ ] Confirm coverage is above 96% (dev-philosophy gate). If the bench runner is configured with coverage, run:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --coverage`
  and verify the reported total ≥ 96%. The new frappe-free functions (`walk_layout_tree`, `unique_sheet_title`, `build_multi_sheet_workbook`, `_clone_template_worksheet`, `_walk_layout_tree`) are each covered by Task 1-3 unit tests and the Task 4-5 integration tests; if any branch is uncovered, add a unit test to `test_export_service_recursion.py` for it before merging.
- [ ] This is the final integration PR for `feature/scl-iatf-export-lhrh-recursion`. Open the PR to `develop` with the superpowers:finishing-a-development-branch skill, summarizing the export ↔ recursion wiring and citing the three green test layers.
