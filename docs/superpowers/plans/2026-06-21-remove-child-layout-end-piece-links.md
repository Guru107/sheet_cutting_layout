# Remove Child Layout End-Piece Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the `child_layout` cross-layout end-piece feature and leave Sheet Cutting Layout release/export behavior local to the current layout.

**Architecture:** `Layout End Piece` no longer links to another Sheet Cutting Layout. Validators, release, and export use only the current document's local end-piece rows. Existing local Reuse/Scrap, strip-weight, generated Item, and Used-for-Part BOM behavior stays intact.

**Tech Stack:** Frappe/ERPNext DocType JSON, Python services, Frappe controller methods, bench-native `unittest`, pre-commit with Ruff/Prettier/ESLint.

---

## File Structure

- Modify `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`: remove the `child_layout` field and field order entry.
- Modify `sheet_cutting_layout/services/validators.py`: remove child-layout traversal, validation, and cycle checks.
- Modify `sheet_cutting_layout/services/end_piece_bom_service.py`: stop excluding Reuse rows that used to have `child_layout`.
- Modify `sheet_cutting_layout/services/release_service.py`: remove descendant collection/cancellation helpers and imports.
- Modify `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`: remove descendant cancellation and recursive download behavior.
- Modify `sheet_cutting_layout/services/export_service.py`: remove `walk_layout_tree()` and its private traversal helper.
- Modify tests under `sheet_cutting_layout/tests/`: remove recursive child-layout test modules or rewrite the one schema test to assert absence.
- Verify with full app tests and pre-commit.

---

### Task 1: Remove `child_layout` Schema And Validator Behavior

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`
- Modify: `sheet_cutting_layout/services/validators.py`
- Modify: `sheet_cutting_layout/tests/test_recursive_end_piece.py`
- Modify: `sheet_cutting_layout/tests/test_validators.py`

- [ ] **Step 1: Replace child-layout schema test with absence assertion**

Replace `sheet_cutting_layout/tests/test_recursive_end_piece.py` with:

```python
from __future__ import annotations

import frappe

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


class TestLayoutEndPieceSchema(SheetCuttingLayoutTestCase):
	def test_child_layout_field_is_removed_from_layout_end_piece(self) -> None:
		meta = frappe.get_meta("Layout End Piece")
		self.assertIsNone(meta.get_field("child_layout"))
```

- [ ] **Step 2: Run the schema test and verify it fails before schema removal**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_recursive_end_piece
```

Expected: FAIL because `meta.get_field("child_layout")` still returns a field.

- [ ] **Step 3: Remove `child_layout` from the DocType JSON**

Edit `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`:

- Remove `"child_layout",` from `field_order`.
- Remove this field object:

```json
  {
   "depends_on": "eval:doc.disposition==\"Reuse\"",
   "fieldname": "child_layout",
   "fieldtype": "Link",
   "label": "Child Layout",
   "no_copy": 1,
   "options": "Sheet Cutting Layout"
  },
```

- [ ] **Step 4: Remove child-layout validation code**

Edit `sheet_cutting_layout/services/validators.py`:

- Remove `Callable` from `from collections.abc import Callable, Sequence`.
- Remove `child_layout: str | None` from `EndPieceRow`.
- Delete `CascadeCycleError`.
- Delete `collect_descendant_layouts()`.
- Remove `_validate_child_layouts(layout, end_pieces)` from `validate_sheet_cutting_layout()`.
- Delete these functions completely:

```python
def _validate_child_layouts(
	layout: SheetCuttingLayoutDocument,
	end_pieces: Sequence[EndPieceRow],
) -> None:

def _validate_child_raw_material(
	layout: SheetCuttingLayoutDocument,
	end_piece: EndPieceRow,
	child_layout: str,
) -> None:

def _validate_no_child_layout_cycle(layout_name: str, child_layout: str) -> None:

def _child_layout_links_from_db(layout_name: str) -> list[str]:
```

- In `apply_end_piece_bom_status()`, remove the child-layout exclusion. The pending check becomes:

```python
pending = any(
	_is_reuse_end_piece(end_piece)
	and _is_missing(getattr(end_piece, "generated_end_piece_bom", None))
	for end_piece in end_pieces
)
```

- [ ] **Step 5: Remove obsolete validator tests**

Edit `sheet_cutting_layout/tests/test_validators.py`:

- Remove `child_layout: str | None = None` from the `EndPiece` dataclass.
- Delete `test_child_layout_raw_material_guard_uses_finished_part_code`.
- Delete `test_child_layout_raw_material_guard_uses_lh_rh_pair_code`.
- Rename `test_apply_end_piece_bom_status_ignores_child_layout_reuse_rows` to `test_apply_end_piece_bom_status_marks_reuse_rows_pending`.
- Replace that test body with:

```python
def test_apply_end_piece_bom_status_marks_reuse_rows_pending(self) -> None:
	layout = Layout()
	end_pieces = [
		EndPiece(
			disposition="Reuse",
			end_piece_item_code="FG01SHR-EP-1x1250x260",
			generated_end_piece_bom=None,
		)
	]

	self.validators.apply_end_piece_bom_status(layout, end_pieces)

	self.assertEqual(layout.end_piece_bom_status, "Pending")
```

- [ ] **Step 6: Run focused validator/schema tests**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_recursive_end_piece --module sheet_cutting_layout.tests.test_validators
```

Expected: PASS for the modules that execute. If bench only runs the last `--module`, run both commands separately:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_recursive_end_piece
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
```

- [ ] **Step 7: Commit Task 1**

```bash
git add sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json sheet_cutting_layout/services/validators.py sheet_cutting_layout/tests/test_recursive_end_piece.py sheet_cutting_layout/tests/test_validators.py
git commit -m "fix: remove child layout validation"
```

---

### Task 2: Make End-Piece BOM And Release Local-Only

**Files:**
- Modify: `sheet_cutting_layout/services/end_piece_bom_service.py`
- Modify: `sheet_cutting_layout/services/release_service.py`
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`
- Delete: `sheet_cutting_layout/tests/test_recursive_end_piece_release.py`
- Modify: `sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Write the failing local Reuse end-piece BOM test**

In `sheet_cutting_layout/tests/test_end_piece_bom_service.py`, add:

```python
def test_generation_includes_every_reuse_end_piece_row(self) -> None:
	existing_code = "FG01SHR-EP-2x100x200"
	fake_frappe = self._install_fakes(existing_items={existing_code})
	layout = Layout(end_pieces=[EndPiece()])

	result = self.service.generate_end_piece_boms(layout)

	self.assertEqual(result["boms"], [self._created_doc(fake_frappe, "BOM").name])
	self.assertEqual(layout.end_pieces[0].generated_end_piece_bom, result["boms"][0])
```

This test documents the retained behavior: a local Reuse end-piece row generates its Used-for-Part BOM.

- [ ] **Step 2: Remove child-layout filtering from end-piece BOM service**

Edit `sheet_cutting_layout/services/end_piece_bom_service.py`:

- Remove `child_layout: str | None` from `EndPieceRow`.
- Replace `_pending_rows()` with:

```python
def _pending_rows(layout: LayoutDocument) -> list[EndPieceRow]:
	return [
		row
		for row in getattr(layout, "end_pieces", []) or []
		if _is_reuse(row)
		and (_is_missing(getattr(row, "end_piece_item_code", None)) or _is_missing(getattr(row, "generated_end_piece_bom", None)))
	]
```

- Delete `_row_has_child_layout()`.

- [ ] **Step 3: Remove descendant release/cancel helpers**

Edit `sheet_cutting_layout/services/release_service.py`:

- Change the validators import to:

```python
from sheet_cutting_layout.services.validators import validate_sheet_cutting_layout
```

- Remove `child_layout: str | None` from the local `EndPieceRow` protocol.
- Delete `collect_descendant_layout_names()`.
- Delete `cancel_descendant_layouts()`.
- Delete `_child_layout_links()`.
- Keep `_append_unique_clean()` because `_layout_bom_names()` still uses it for generated BOM links.

- [ ] **Step 4: Remove descendant cancellation from the DocType controller**

Edit `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`:

- Remove `cancel_descendant_layouts` from the `release_service` import list.
- Change `before_cancel()` to:

```python
def before_cancel(self) -> None:
	self.ignore_linked_doctypes = ["BOM", "Sheet Cutting Layout"]
```

- Delete this line from `on_trash()`:

```python
cancel_descendant_layouts(self)
```

- [ ] **Step 5: Delete recursive release tests and one descendant unit test**

Delete `sheet_cutting_layout/tests/test_recursive_end_piece_release.py`.

In `sheet_cutting_layout/tests/test_release_service.py`, delete the entire method named `test_cancel_descendant_layouts_preserves_existing_ignore_linked_doctypes`.

- [ ] **Step 6: Run focused release and end-piece BOM tests**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
```

Expected: both pass.

- [ ] **Step 7: Commit Task 2**

```bash
git add sheet_cutting_layout/services/end_piece_bom_service.py sheet_cutting_layout/services/release_service.py sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py sheet_cutting_layout/tests/test_end_piece_bom_service.py sheet_cutting_layout/tests/test_release_service.py
git rm sheet_cutting_layout/tests/test_recursive_end_piece_release.py
git commit -m "fix: remove recursive end piece release"
```

---

### Task 3: Make Export And Download Local-Only

**Files:**
- Modify: `sheet_cutting_layout/services/export_service.py`
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`
- Delete: `sheet_cutting_layout/tests/test_export_service_recursion.py`
- Delete: `sheet_cutting_layout/tests/test_download_sheet_cutting_layout_recursion.py`
- Modify: `sheet_cutting_layout/tests/test_sheet_cutting_layout_controller.py`

- [ ] **Step 1: Add or confirm one local download/export test**

Keep `sheet_cutting_layout/tests/test_sheet_cutting_layout_export.py` as the local workbook coverage. Confirm it still calls `download_sheet_cutting_layout()` and checks a single workbook for the selected layout.

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_sheet_cutting_layout_export
```

Expected before implementation: current tests pass or fail only for unrelated setup. Do not change behavior based on this step; it is a baseline.

- [ ] **Step 2: Remove recursive walk from export service**

Edit `sheet_cutting_layout/services/export_service.py`:

- Remove `Callable` from the imports if it is only used by `walk_layout_tree()`.
- Delete `walk_layout_tree()`.
- Delete `_walk_layout_tree()`.
- Keep `build_multi_sheet_workbook()` if existing callers/tests still use it for one page.

- [ ] **Step 3: Simplify `download_sheet_cutting_layout()`**

Edit `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`:

- Remove `walk_layout_tree` from the export service import.
- Replace the body after the selected layout read permission check with:

```python
pages = [(doc.name, _export_layout_dict(doc))]
workbook = build_multi_sheet_workbook(pages)
stream = BytesIO()
workbook.save(stream)
frappe.response["filename"] = f"{doc.name}.xlsx"
frappe.response["filecontent"] = stream.getvalue()
frappe.response["type"] = "binary"
```

- Delete the nested `fetch_child()` function.

- [ ] **Step 4: Remove recursive export tests**

Delete:

```bash
git rm sheet_cutting_layout/tests/test_export_service_recursion.py
git rm sheet_cutting_layout/tests/test_download_sheet_cutting_layout_recursion.py
```

In `sheet_cutting_layout/tests/test_sheet_cutting_layout_controller.py`, delete the entire methods named `test_download_checks_child_layout_read_permission_before_export` and `test_download_denies_real_user_without_child_layout_read_access`.

- [ ] **Step 5: Run focused export/controller tests**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_sheet_cutting_layout_export
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_sheet_cutting_layout_controller
```

Expected: all pass.

- [ ] **Step 6: Commit Task 3**

```bash
git add sheet_cutting_layout/services/export_service.py sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py sheet_cutting_layout/tests/test_sheet_cutting_layout_controller.py
git rm sheet_cutting_layout/tests/test_export_service_recursion.py sheet_cutting_layout/tests/test_download_sheet_cutting_layout_recursion.py
git commit -m "fix: remove recursive layout export"
```

---

### Task 4: Remove Remaining References And Verify

**Files:**
- Check: all changed source/test files
- Modify: any file still referencing live `child_layout` behavior

- [ ] **Step 1: Search for remaining live references**

Run:

```bash
rg -n "child_layout|collect_descendant_layouts|CascadeCycleError|cancel_descendant_layouts|collect_descendant_layout_names|walk_layout_tree" sheet_cutting_layout
```

Expected: no matches in live source/tests. Historical docs under `docs/superpowers/` are allowed to keep old references.

- [ ] **Step 2: If matches remain, remove them**

Use these rules:

- Source code match: remove the code path.
- Test match: delete or rewrite the test so it covers local-only behavior.
- DocType JSON match: remove it.
- Historical docs match outside `sheet_cutting_layout/`: leave it alone.

- [ ] **Step 3: Run migration for DocType JSON change**

Run:

```bash
bench --site development.localhost migrate
```

Expected: migration completes successfully and updates the DocType metadata.

- [ ] **Step 4: Run full app tests**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout
```

Expected: PASS.

- [ ] **Step 5: Run pre-commit**

Run:

```bash
pre-commit run --all-files
```

Expected: PASS. If hooks modify files, rerun focused tests for any modified Python/JS paths and rerun `pre-commit run --all-files`.

- [ ] **Step 6: Commit final cleanup if needed**

If Step 1 or hooks changed additional files:

```bash
git add .
git commit -m "chore: clean child layout references"
```

Skip this commit if there are no remaining changes after Tasks 1-3.

---

## Final Verification

Run:

```bash
git status --short
bench --site development.localhost run-tests --app sheet_cutting_layout
pre-commit run --all-files
rg -n "child_layout|collect_descendant_layouts|CascadeCycleError|cancel_descendant_layouts|collect_descendant_layout_names|walk_layout_tree" sheet_cutting_layout
```

Expected:

- `git status --short` shows only intended committed changes before final push/PR update.
- Full app tests pass.
- Pre-commit passes.
- `rg` returns no live source/test matches.
