# Phase 1 — LH/RH Symmetric Parts Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
**Goal:** Let a single Sheet Cutting Layout marked LH/RH emit two structurally identical Shearing BOMs (one per symmetric item code), both linked to the same layout, mirrored in `finished_parts`, and retired together on cancel.
**Architecture:** Three new parent fields on Sheet Cutting Layout (`is_lh_rh`, `orientation`, `twin_finished_part`) and an `orientation` column on the `Layout Finished Part` mirror drive a twin expansion inside the existing `release_service._generate_boms` loop: `_parent_finished_part_rows` returns `[primary]` or `[primary, twin]`, the twin inheriting the primary's weights/parts and differing only in item code + orientation. The reference-row sync writes both items with their orientation and generated BOM; the existing `_layout_bom_names` + native `on_cancel` cascade (Phase 0) already retire both BOMs.
**Tech Stack:** Frappe v15 / ERPNext v15.101, Python, openpyxl, Cypress
---

## Dependencies

This plan **lands after Phase 0** and assumes Phase 0 has merged. Specifically it depends on:

- **Phase 0 multi-BOM fix:** `release_service._generate_boms` no longer blindly overwrites `layout.generated_bom` on every loop iteration — it sets the parent `generated_bom` to the **primary** part's BOM only, and the per-item BOMs are tracked through the `finished_parts` mirror. Phase 1 leans on this so the twin BOM does not clobber the primary on the parent field.
- **Phase 0 `Layout Finished Part.generated_bom` column:** the `generated_bom` (Link → BOM) field is already added to the `Layout Finished Part` doctype (it was a latent mismatch — `_layout_bom_names` reads `row.generated_bom` but the doctype had no such field). Phase 1 **adds the `orientation` column only**; it must not re-add `generated_bom`. If, when you start, `generated_bom` is somehow still missing from `layout_finished_part.json`, STOP and confirm Phase 0 merged before proceeding.
- **Phase 0 native release spine:** release is driven by native `on_submit` (the `Released` workflow state has `doc_status = 1`), retirement by native `on_cancel` with `ignore_linked_doctypes = ["BOM"]`. The `apply_workflow` override, `before_workflow_action`, `validate()`-driven release, and `frappe.flags.selected_workflow_action` plumbing are **removed**. The integration tests in this plan therefore drive release via `frappe.model.workflow.apply_workflow(layout, "MR Release")` (or `layout.submit()` once at `Approved by Purchase`), **not** by calling `layout.validate()` with a patched `_get_selected_workflow_action`.

> **Verification gate before Task 1:** run `python -c "import json; d=json.load(open('sheet_cutting_layout/sheet_cutting_layout/doctype/layout_finished_part/layout_finished_part.json')); print('generated_bom' in d['field_order'])"` from the repo root. It must print `True`. If it prints `False`, Phase 0 has not landed — do not start.

## File structure

| File | Responsibility | Change |
|---|---|---|
| `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json` | Parent doctype schema | **Modify** — add `is_lh_rh`, `orientation`, `twin_finished_part` fields + `field_order` entries |
| `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_finished_part/layout_finished_part.json` | Mirror child doctype schema | **Modify** — add `orientation` Select column |
| `sheet_cutting_layout/services/bom_service.py` | Pure BOM/parts math + `ParentFinishedPartRow` | **Modify** — add `orientation` to `ParentFinishedPartRow`; add `twin_finished_part_row()` helper |
| `sheet_cutting_layout/services/release_service.py` | Release orchestration (BOM generation + mirror sync) | **Modify** — `_parent_finished_part_rows` twin expansion; `_sync_finished_part_reference_rows` writes `orientation` + `generated_bom`; mirror dataclass gains fields |
| `sheet_cutting_layout/services/validators.py` | Document validation | **Modify** — add `_validate_lh_rh_fields`; call it from `validate_sheet_cutting_layout` |
| `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js` | Client form behavior | **Modify** — toggle/clear LH/RH fields; default orientation |
| `sheet_cutting_layout/services/tests/test_lh_rh_expansion.py` | Unit tests for pure twin expansion + part-number join | **Create** |
| `sheet_cutting_layout/services/tests/test_lh_rh_validation.py` | Unit tests for LH/RH validation | **Create** |
| `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_lh_rh_release.py` | Integration tests (real DB, two linked BOMs, mirror, cancel) | **Create** |
| `cypress/integration/sheet_cutting_layout_lh_rh.js` | E2E spec (check box, pick twin + orientation, release, assert mirror) | **Create** |

> **Service test location:** this plan places frappe-free unit tests under `sheet_cutting_layout/services/tests/`. If that package does not exist yet, Task 3 creates it (with `__init__.py`). The bench runner discovers any `test_*.py` under the app, so module dotted paths are e.g. `sheet_cutting_layout.services.tests.test_lh_rh_expansion`.

> **All test commands run from `/Users/gurudattkulkarni/Workspace/bench15`.** Lint commands run from the repo root `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`.

> **Line numbers are post-Phase-0 — locate by symbol, not by absolute line.** Every `lines N-M`
> reference in the Files blocks and task bodies below is given against the tree **after Phase 0 has
> merged to `develop`**. The frappe-less TEST-mode cleanup is **already done** — it landed via the
> develop merge (commit `2e964da`): `tests/unittest_adapter.py` is deleted, `tests/base.py` is now a
> bench-native dual-probe (`IntegrationTestCase`/`FrappeTestCase`) exposing
> `SheetCuttingLayoutTestCase`, and the shared factories live in `sheet_cutting_layout/tests/factories.py`
> (`make_layout`, `make_release_ready_layout`, `register_test_doc`, `ensure_item`, `ensure_project`,
> `ensure_item_group`). New test files in this plan therefore use a bare `import frappe` and no
> `@skipUnless` guard. What Phase 0 **still** removes (and is genuinely pending): the production-side
> `try: import frappe` / `_FrappeCompat` import shims (validators.py, overrides/bom.py,
> end_piece_item_service.py, end_piece_bom_service.py, release_service.py, controller), the
> `apply_workflow` override + validate()-driven release, and the migration patches; and it adds the
> `generated_bom` column to `Layout Finished Part` — all of which shift line numbers. The executor MUST
> find each edit point by **symbol name** (e.g. `ParentFinishedPartRow`, `_parent_finished_part_rows`,
> `_validate_parent_finished_part_fields`), treating the line numbers only as a hint. Before starting
> Task 1, **confirm Phase 0 is merged to `develop`**: the current `develop` is *pre*-Phase-0 for the
> production shims and schema (verified — `layout_finished_part.json` has no `generated_bom` field, the
> production frappe-less shims are still present, the workflow's `Superseded` state is still
> `doc_status: 1` with an unreachable `Cancel` state at `doc_status: 2`). The Verification gate under
> **Dependencies** is the hard stop for this.

---

## Task group A: Pure-domain twin expansion (frappe-free)

### Task 1: Add `orientation` to `ParentFinishedPartRow` and a `twin_finished_part_row` builder

**Files:**
- Create: `sheet_cutting_layout/services/tests/__init__.py` (empty package marker)
- Create: `sheet_cutting_layout/services/tests/test_lh_rh_expansion.py`
- Modify: `sheet_cutting_layout/services/bom_service.py` (dataclass `ParentFinishedPartRow` at lines 71-77; helper `parent_finished_part_row` at lines 230-239)

- [ ] Create the test package marker file `sheet_cutting_layout/services/tests/__init__.py` with a single line of content:
```python
# Test package for frappe-free service unit tests.
```

- [ ] Write the failing unit test file `sheet_cutting_layout/services/tests/test_lh_rh_expansion.py`:
```python
from __future__ import annotations

from types import SimpleNamespace

from sheet_cutting_layout.services.bom_service import (
	ParentFinishedPartRow,
	parent_finished_part_row,
	twin_finished_part_row,
)
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


def _layout(**overrides: object) -> SimpleNamespace:
	defaults = dict(
		finished_part_code="0102AAG06400SHR",
		parts_per_sheet=4,
		gross_weight_per_part_kg=3.5,
		scrap_weight_per_part_kg=0.5,
		is_lh_rh=0,
		orientation=None,
		twin_finished_part=None,
	)
	defaults.update(overrides)
	return SimpleNamespace(**defaults)


class TestTwinFinishedPartRow(SheetCuttingLayoutTestCase):
	def test_parent_row_defaults_orientation_to_none(self) -> None:
		row = parent_finished_part_row(_layout())
		self.assertEqual(row.finished_part_item, "0102AAG06400SHR")
		self.assertIsNone(row.orientation)

	def test_parent_row_carries_layout_orientation_when_lh_rh(self) -> None:
		row = parent_finished_part_row(
			_layout(is_lh_rh=1, orientation="LH", twin_finished_part="0102AAG06410SHR")
		)
		self.assertEqual(row.orientation, "LH")

	def test_twin_row_inherits_weights_and_parts_with_opposite_orientation(self) -> None:
		layout = _layout(is_lh_rh=1, orientation="LH", twin_finished_part="0102AAG06410SHR")
		primary = parent_finished_part_row(layout)
		twin = twin_finished_part_row(layout)

		self.assertEqual(twin.finished_part_item, "0102AAG06410SHR")
		self.assertEqual(twin.parts_per_sheet, primary.parts_per_sheet)
		self.assertEqual(twin.gross_weight_per_part_kg, primary.gross_weight_per_part_kg)
		self.assertEqual(twin.scrap_weight_per_part_kg, primary.scrap_weight_per_part_kg)
		self.assertEqual(twin.orientation, "RH")

	def test_twin_row_orientation_is_lh_when_primary_is_rh(self) -> None:
		layout = _layout(is_lh_rh=1, orientation="RH", twin_finished_part="0102AAG06410SHR")
		self.assertEqual(twin_finished_part_row(layout).orientation, "LH")

	def test_twin_row_requires_twin_finished_part(self) -> None:
		layout = _layout(is_lh_rh=1, orientation="LH", twin_finished_part="")
		with self.assertRaises(ValueError):
			twin_finished_part_row(layout)

	def test_parent_finished_part_row_returns_expected_dataclass(self) -> None:
		self.assertIsInstance(parent_finished_part_row(_layout()), ParentFinishedPartRow)
```

- [ ] Run the test and see it FAIL. From `/Users/gurudattkulkarni/Workspace/bench15`:
```
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.services.tests.test_lh_rh_expansion
```
Expected failure: `ImportError: cannot import name 'twin_finished_part_row' from 'sheet_cutting_layout.services.bom_service'` (and `orientation` attribute errors).

- [ ] Add `orientation` to the `ParentFinishedPartRow` dataclass. In `sheet_cutting_layout/services/bom_service.py`, replace the dataclass at lines 71-77:
```python
@dataclass
class ParentFinishedPartRow:
	finished_part_item: str
	parts_per_sheet: int
	gross_weight_per_part_kg: float
	scrap_weight_per_part_kg: float
	orientation: str | None = None
```

- [ ] Update `parent_finished_part_row` to carry the layout orientation when LH/RH is set. In `sheet_cutting_layout/services/bom_service.py`, replace the function body at lines 230-239:
```python
def parent_finished_part_row(layout_doc: LayoutDocument) -> ParentFinishedPartRow:
	finished_part_item = str(getattr(layout_doc, "finished_part_code", "") or "").strip()
	if not finished_part_item:
		raise ValueError("finished_part_code is required to create generated BOM")
	return ParentFinishedPartRow(
		finished_part_item=finished_part_item,
		parts_per_sheet=int(getattr(layout_doc, "parts_per_sheet", 0) or 0),
		gross_weight_per_part_kg=float(getattr(layout_doc, "gross_weight_per_part_kg", 0) or 0),
		scrap_weight_per_part_kg=float(getattr(layout_doc, "scrap_weight_per_part_kg", 0) or 0),
		orientation=_parent_orientation(layout_doc),
	)


def _parent_orientation(layout_doc: LayoutDocument) -> str | None:
	if not getattr(layout_doc, "is_lh_rh", None):
		return None
	orientation = str(getattr(layout_doc, "orientation", "") or "").strip()
	return orientation or None


def twin_finished_part_row(layout_doc: LayoutDocument) -> ParentFinishedPartRow:
	primary = parent_finished_part_row(layout_doc)
	twin_item = str(getattr(layout_doc, "twin_finished_part", "") or "").strip()
	if not twin_item:
		raise ValueError("twin_finished_part is required to create the LH/RH twin BOM")
	return ParentFinishedPartRow(
		finished_part_item=twin_item,
		parts_per_sheet=primary.parts_per_sheet,
		gross_weight_per_part_kg=primary.gross_weight_per_part_kg,
		scrap_weight_per_part_kg=primary.scrap_weight_per_part_kg,
		orientation=_opposite_orientation(primary.orientation),
	)


def _opposite_orientation(orientation: str | None) -> str | None:
	normalized = str(orientation or "").strip().upper()
	if normalized == "LH":
		return "RH"
	if normalized == "RH":
		return "LH"
	return None
```

- [ ] Extend the `LayoutDocument` Protocol so the new attributes are documented. In `sheet_cutting_layout/services/bom_service.py`, replace the `LayoutDocument` Protocol at lines 28-38:
```python
class LayoutDocument(Protocol):
	raw_material_item: str
	process_scrap_item: str
	weight_per_sheet_kg: float
	no_of_strips: int
	finished_part_code: str | None
	parts_per_sheet: int
	gross_weight_per_part_kg: float
	scrap_weight_per_part_kg: float
	sheet_thickness_mm: float | None
	is_lh_rh: int | None
	orientation: str | None
	twin_finished_part: str | None
	end_pieces: Sequence[EndPieceRow]
```

- [ ] Run the test and see it PASS:
```
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.services.tests.test_lh_rh_expansion
```
Expected: all 6 tests pass.

- [ ] Run lint gates from the repo root `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
```
python -m ruff check . && python -m ruff format --check .
```
Expected: no errors. (If `ruff format --check` flags the new files, run `python -m ruff format .` and re-run.)

- [ ] Commit:
```
git add sheet_cutting_layout/services/bom_service.py sheet_cutting_layout/services/tests/__init__.py sheet_cutting_layout/services/tests/test_lh_rh_expansion.py
git commit -m "feat: add LH/RH twin finished-part row builder

ParentFinishedPartRow now carries orientation; twin_finished_part_row
inherits the primary part's weights/parts with the opposite orientation.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Add the joined part-number + LH/RH label helpers

> **SUPERSEDED (decision 2026-06-16).** The short-form `joined_part_number_label` /
> `_common_prefix_length` helpers below were **not** built. The export part-number cell uses the
> **full item codes joined with `/`** (e.g. `0102AAG06400SHR/0102AAG06410SHR`), not the common-prefix
> short form (`0102AAG06400_6410N`). Only the `lh_rh_part_name_suffix` ("LH & RH") portion shipped.
> Kept below for historical context; see spec §8.4.

These pure helpers are consumed by the Phase 2 exporter (§8.4) but are defined and tested now so the labeling contract is fixed in Phase 1.

**Files:**
- Modify: `sheet_cutting_layout/services/bom_service.py` (append new module-level functions after `twin_finished_part_row`)
- Modify: `sheet_cutting_layout/services/tests/test_lh_rh_expansion.py` (append a test class)

- [ ] Append the failing test class to `sheet_cutting_layout/services/tests/test_lh_rh_expansion.py`:
```python
from sheet_cutting_layout.services.bom_service import (  # noqa: E402
	joined_part_number_label,
	lh_rh_part_name_suffix,
)


class TestLhRhLabels(SheetCuttingLayoutTestCase):
	def test_joined_part_number_uses_underscore_short_form(self) -> None:
		self.assertEqual(
			joined_part_number_label("0102AAG06400N", "0102AAG06410N"),
			"0102AAG06400_6410N",
		)

	def test_joined_part_number_falls_back_to_full_join_without_common_prefix(self) -> None:
		self.assertEqual(
			joined_part_number_label("ABC123", "XYZ789"),
			"ABC123_XYZ789",
		)

	def test_joined_part_number_with_single_code_returns_that_code(self) -> None:
		self.assertEqual(joined_part_number_label("ABC123", ""), "ABC123")
		self.assertEqual(joined_part_number_label("", "XYZ789"), "XYZ789")

	def test_part_name_suffix_when_lh_rh(self) -> None:
		self.assertEqual(lh_rh_part_name_suffix(is_lh_rh=True), "LH & RH")

	def test_part_name_suffix_when_not_lh_rh(self) -> None:
		self.assertEqual(lh_rh_part_name_suffix(is_lh_rh=False), "")
```

- [ ] Run and see it FAIL:
```
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.services.tests.test_lh_rh_expansion
```
Expected failure: `ImportError: cannot import name 'joined_part_number_label' from 'sheet_cutting_layout.services.bom_service'`.

- [ ] Append the implementation to `sheet_cutting_layout/services/bom_service.py` (after `_opposite_orientation`):
```python
def joined_part_number_label(primary_part_number: str, twin_part_number: str) -> str:
	"""Render the Excel's paired part-number cell, e.g. 0102AAG06400_6410N.

	The twin is collapsed to its trailing segment that diverges from the
	primary's common prefix; when there is no shared prefix both codes are
	joined in full. A single code is returned unchanged.
	"""
	primary = str(primary_part_number or "").strip()
	twin = str(twin_part_number or "").strip()
	if not primary:
		return twin
	if not twin:
		return primary

	common = _common_prefix_length(primary, twin)
	twin_suffix = twin[common:] if common else twin
	if not twin_suffix:
		twin_suffix = twin
	return f"{primary}_{twin_suffix}"


def _common_prefix_length(left: str, right: str) -> int:
	length = 0
	for left_char, right_char in zip(left, right, strict=False):
		if left_char != right_char:
			break
		length += 1
	return length


def lh_rh_part_name_suffix(*, is_lh_rh: bool) -> str:
	return "LH & RH" if is_lh_rh else ""
```

- [ ] Run and see it PASS:
```
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.services.tests.test_lh_rh_expansion
```
Expected: all tests (Task 1 + Task 2 classes) pass.

- [ ] Lint from repo root, then commit:
```
python -m ruff check . && python -m ruff format --check .
git add sheet_cutting_layout/services/bom_service.py sheet_cutting_layout/services/tests/test_lh_rh_expansion.py
git commit -m "feat: add joined part-number and LH/RH label helpers

Pure helpers for the paired part-number cell (0102AAG06400_6410N) and
the 'LH & RH' part-name suffix the exporter renders.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task group B: Release-service twin expansion + mirror sync

### Task 3: Expand `_parent_finished_part_rows` to `[primary, twin]` when LH/RH

**Files:**
- Create: `sheet_cutting_layout/services/tests/test_lh_rh_release.py`
- Modify: `sheet_cutting_layout/services/release_service.py` (`_parent_finished_part_rows` at lines 432-435; import block at lines 8-14)

- [ ] Write the failing unit test `sheet_cutting_layout/services/tests/test_lh_rh_release.py`:
```python
from __future__ import annotations

from types import SimpleNamespace

from sheet_cutting_layout.services.release_service import _parent_finished_part_rows
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


def _layout(**overrides: object) -> SimpleNamespace:
	defaults = dict(
		finished_part_code="0102AAG06400SHR",
		parts_per_sheet=4,
		gross_weight_per_part_kg=3.5,
		scrap_weight_per_part_kg=0.5,
		is_lh_rh=0,
		orientation=None,
		twin_finished_part=None,
	)
	defaults.update(overrides)
	return SimpleNamespace(**defaults)


class TestParentFinishedPartRows(SheetCuttingLayoutTestCase):
	def test_non_lh_rh_layout_returns_single_primary_row(self) -> None:
		rows = _parent_finished_part_rows(_layout())
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].finished_part_item, "0102AAG06400SHR")
		self.assertIsNone(rows[0].orientation)

	def test_lh_rh_layout_returns_primary_then_twin(self) -> None:
		rows = _parent_finished_part_rows(
			_layout(is_lh_rh=1, orientation="LH", twin_finished_part="0102AAG06410SHR")
		)
		self.assertEqual([row.finished_part_item for row in rows], ["0102AAG06400SHR", "0102AAG06410SHR"])
		self.assertEqual([row.orientation for row in rows], ["LH", "RH"])

	def test_twin_row_inherits_primary_weights(self) -> None:
		rows = _parent_finished_part_rows(
			_layout(is_lh_rh=1, orientation="RH", twin_finished_part="0102AAG06410SHR")
		)
		primary, twin = rows
		self.assertEqual(twin.parts_per_sheet, primary.parts_per_sheet)
		self.assertEqual(twin.gross_weight_per_part_kg, primary.gross_weight_per_part_kg)
		self.assertEqual(twin.scrap_weight_per_part_kg, primary.scrap_weight_per_part_kg)
		self.assertEqual([primary.orientation, twin.orientation], ["RH", "LH"])

	def test_blank_finished_part_code_returns_empty(self) -> None:
		self.assertEqual(_parent_finished_part_rows(_layout(finished_part_code="")), [])
```

- [ ] Run and see it FAIL:
```
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.services.tests.test_lh_rh_release
```
Expected failure: `test_lh_rh_layout_returns_primary_then_twin` fails with `AssertionError` (only one row returned — the primary).

- [ ] Add `twin_finished_part_row` to the release-service import block. In `sheet_cutting_layout/services/release_service.py`, replace the import at lines 8-14:
```python
from sheet_cutting_layout.services.bom_service import (
	BomDocument,
	ParentFinishedPartRow,
	build_bom_from_layout_row,
	parent_finished_part_row,
	resolve_scrap_item_rate,
	twin_finished_part_row,
)
```

- [ ] Replace `_parent_finished_part_rows` at lines 432-435:
```python
def _parent_finished_part_rows(layout: ReleaseLayoutDocument) -> list[ParentFinishedPartRow]:
	if not str(getattr(layout, "finished_part_code", "") or "").strip():
		return []
	rows = [parent_finished_part_row(layout)]  # type: ignore[arg-type]
	if getattr(layout, "is_lh_rh", None):
		rows.append(twin_finished_part_row(layout))  # type: ignore[arg-type]
	return rows
```

- [ ] Run and see it PASS:
```
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.services.tests.test_lh_rh_release
```
Expected: all 4 tests pass.

- [ ] Lint from repo root, then commit:
```
python -m ruff check . && python -m ruff format --check .
git add sheet_cutting_layout/services/release_service.py sheet_cutting_layout/services/tests/test_lh_rh_release.py
git commit -m "feat: expand release finished-part rows to LH/RH twin

_parent_finished_part_rows returns [primary, twin] when is_lh_rh, so the
existing _generate_boms loop emits one Shearing BOM per item code.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Mirror `orientation` + `generated_bom` into `finished_parts` reference rows

The mirror sync (`_sync_finished_part_reference_rows`, release_service.py:438-456) currently writes
`finished_part_item`, `bom_quantity`, `scrap_weight_kg`, `raw_material_weight_kg`. It must also write the
per-row `orientation` (from the expanded `ParentFinishedPartRow`) and `generated_bom` (the BOM produced
for **that** row, paired positionally with `generated_boms`).

**Files:**
- Modify: `sheet_cutting_layout/services/release_service.py` (`FinishedPartReferenceRow` dataclass at lines 88-94; `_sync_finished_part_reference_rows` at lines 438-456; `FinishedPartRow` Protocol at lines 40-46)
- Modify: `sheet_cutting_layout/services/tests/test_lh_rh_release.py` (append a test class)

- [ ] Append the failing test class to `sheet_cutting_layout/services/tests/test_lh_rh_release.py`:
```python
from dataclasses import dataclass, field  # noqa: E402

from sheet_cutting_layout.services.bom_service import BomDocument, BomItemRow  # noqa: E402
from sheet_cutting_layout.services.release_service import (  # noqa: E402
	_sync_finished_part_reference_rows,
)


@dataclass
class _MirrorLayout:
	finished_parts: list[object] = field(default_factory=list)

	def set(self, fieldname: str, value: object) -> None:
		setattr(self, fieldname, value)


def _bom(name: str, raw_qty: float, scrap_qty: float) -> BomDocument:
	return BomDocument(
		item="X",
		name=name,
		items=[BomItemRow(item_code="RM", qty=raw_qty, row_type="raw_material")],
		scrap_items=[BomItemRow(item_code="SC", qty=scrap_qty, row_type="process_scrap")],
	)


class TestSyncFinishedPartReferenceRows(SheetCuttingLayoutTestCase):
	def test_mirror_rows_carry_orientation_and_generated_bom(self) -> None:
		layout = _MirrorLayout()
		rows = _parent_finished_part_rows(
			_layout(is_lh_rh=1, orientation="LH", twin_finished_part="0102AAG06410SHR")
		)
		boms = [_bom("BOM-PRIMARY", 14.0, 2.0), _bom("BOM-TWIN", 14.0, 2.0)]

		_sync_finished_part_reference_rows(layout, boms, rows)

		mirror = layout.finished_parts
		self.assertEqual([row["finished_part_item"] for row in mirror], ["0102AAG06400SHR", "0102AAG06410SHR"])
		self.assertEqual([row["orientation"] for row in mirror], ["LH", "RH"])
		self.assertEqual([row["generated_bom"] for row in mirror], ["BOM-PRIMARY", "BOM-TWIN"])
		self.assertEqual([row["bom_quantity"] for row in mirror], [4, 4])
		self.assertEqual([row["raw_material_weight_kg"] for row in mirror], [14.0, 14.0])
		self.assertEqual([row["scrap_weight_kg"] for row in mirror], [2.0, 2.0])

	def test_single_part_mirror_has_none_orientation(self) -> None:
		layout = _MirrorLayout()
		rows = _parent_finished_part_rows(_layout())
		boms = [_bom("BOM-ONLY", 14.0, 2.0)]

		_sync_finished_part_reference_rows(layout, boms, rows)

		self.assertEqual(len(layout.finished_parts), 1)
		self.assertIsNone(layout.finished_parts[0]["orientation"])
		self.assertEqual(layout.finished_parts[0]["generated_bom"], "BOM-ONLY")
```

- [ ] Run and see it FAIL:
```
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.services.tests.test_lh_rh_release
```
Expected failure: `KeyError: 'orientation'` (the mirror dict lacks the `orientation` and `generated_bom` keys).

- [ ] Extend the `FinishedPartRow` Protocol so `orientation` is documented. In `sheet_cutting_layout/services/release_service.py`, replace lines 40-46:
```python
class FinishedPartRow(Protocol):
	finished_part_item: str
	parts_per_sheet: int
	gross_weight_per_part_kg: float
	scrap_weight_per_part_kg: float
	generated_bom: str | None
	orientation: str | None
```

- [ ] Extend the `FinishedPartReferenceRow` dataclass at lines 88-94:
```python
@dataclass
class FinishedPartReferenceRow:
	finished_part_item: str
	bom_quantity: float | None
	scrap_weight_kg: float | None
	raw_material_weight_kg: float | None
	orientation: str | None = None
	generated_bom: str | None = None
```

- [ ] Replace `_sync_finished_part_reference_rows` at lines 438-456:
```python
def _sync_finished_part_reference_rows(
	layout: ReleaseLayoutDocument,
	generated_boms: Sequence[BomDocument],
	finished_parts: Sequence[FinishedPartRow],
) -> None:
	references = [
		{
			"finished_part_item": finished_part.finished_part_item,
			"orientation": getattr(finished_part, "orientation", None),
			"generated_bom": getattr(bom, "name", None) or None,
			"bom_quantity": _finished_part_bom_quantity(finished_part),
			"scrap_weight_kg": _sum_bom_qty(bom.scrap_items),
			"raw_material_weight_kg": _sum_bom_qty(bom.items),
		}
		for finished_part, bom in zip(finished_parts, generated_boms, strict=False)
	]
	set_child_table = getattr(layout, "set", None)
	if callable(set_child_table):
		set_child_table("finished_parts", references)
		return
	layout.finished_parts = [FinishedPartReferenceRow(**row) for row in references]
```

- [ ] Run and see it PASS:
```
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.services.tests.test_lh_rh_release
```
Expected: all tests in this module pass.

- [ ] Lint from repo root, then commit:
```
python -m ruff check . && python -m ruff format --check .
git add sheet_cutting_layout/services/release_service.py sheet_cutting_layout/services/tests/test_lh_rh_release.py
git commit -m "feat: mirror orientation and per-row BOM into finished_parts

_sync_finished_part_reference_rows writes each expanded part's
orientation and its own generated BOM, pairing rows positionally.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task group C: Schema — doctype fields

### Task 5: Add `is_lh_rh`, `orientation`, `twin_finished_part` to Sheet Cutting Layout

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json` (`field_order` at lines 10-52; `fields` array — insert the three field defs near `finished_part_code` at lines 249-255)
- Create: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_lh_rh_release.py` (schema-presence integration test)

> Doctype JSON changes take effect after `bench --site development.localhost migrate`. The bench test runner reloads doctype JSON from disk during `setUpClass` model sync, but to be safe run `migrate` after editing the JSON and before running the integration test.

- [ ] Write the failing schema-presence integration test `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_lh_rh_release.py`:
```python
from __future__ import annotations

import frappe

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


class TestLhRhSchema(SheetCuttingLayoutTestCase):
	def test_layout_has_lh_rh_fields(self) -> None:
		meta = frappe.get_meta("Sheet Cutting Layout")
		self.assertTrue(meta.has_field("is_lh_rh"))
		self.assertTrue(meta.has_field("orientation"))
		self.assertTrue(meta.has_field("twin_finished_part"))

	def test_orientation_options_are_lh_and_rh(self) -> None:
		field = frappe.get_meta("Sheet Cutting Layout").get_field("orientation")
		self.assertEqual(field.fieldtype, "Select")
		self.assertEqual([line for line in (field.options or "").split("\n") if line], ["LH", "RH"])

	def test_twin_finished_part_links_to_item(self) -> None:
		field = frappe.get_meta("Sheet Cutting Layout").get_field("twin_finished_part")
		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "Item")

	def test_lh_rh_fields_depend_on_is_lh_rh(self) -> None:
		meta = frappe.get_meta("Sheet Cutting Layout")
		self.assertIn("is_lh_rh", meta.get_field("orientation").depends_on or "")
		self.assertIn("is_lh_rh", meta.get_field("twin_finished_part").depends_on or "")
```

- [ ] Run and see it FAIL. From `/Users/gurudattkulkarni/Workspace/bench15`:
```
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_lh_rh_release
```
Expected failure: `AssertionError: False is not true` from `test_layout_has_lh_rh_fields` (fields absent).

- [ ] Add the three field names to `field_order` in `sheet_cutting_layout.json`. Replace the line `"finished_part_code",` (line 42) with:
```
  "finished_part_code",
  "is_lh_rh",
  "orientation",
  "twin_finished_part",
```

- [ ] Add the three field definitions to the `fields` array. In `sheet_cutting_layout.json`, locate the `finished_part_code` field object (lines 249-255) and insert the following three objects immediately after its closing `},` (i.e. before the `net_weight_per_part_kg` field object at line 256):
```json
  {
   "default": "0",
   "fieldname": "is_lh_rh",
   "fieldtype": "Check",
   "label": "Symmetric LH/RH Part?"
  },
  {
   "depends_on": "eval:doc.is_lh_rh",
   "fieldname": "orientation",
   "fieldtype": "Select",
   "label": "Orientation",
   "mandatory_depends_on": "eval:doc.is_lh_rh",
   "options": "LH\nRH"
  },
  {
   "depends_on": "eval:doc.is_lh_rh",
   "fieldname": "twin_finished_part",
   "fieldtype": "Link",
   "label": "Twin Finished Part",
   "mandatory_depends_on": "eval:doc.is_lh_rh",
   "options": "Item"
  },
```

- [ ] Apply the schema. From `/Users/gurudattkulkarni/Workspace/bench15`:
```
bench --site development.localhost migrate
```
Expected: migrate completes without error.

- [ ] Run the test and see it PASS:
```
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_lh_rh_release
```
Expected: all 4 schema tests pass.

- [ ] Commit:
```
git add sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_lh_rh_release.py
git commit -m "feat: add is_lh_rh, orientation, twin_finished_part fields

LH/RH parent fields on Sheet Cutting Layout; orientation and twin are
mandatory and visible only when is_lh_rh is checked.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Add `orientation` column to `Layout Finished Part`

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_finished_part/layout_finished_part.json` (`field_order` at lines 8-13; `fields` array)
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_lh_rh_release.py` (append a schema test method)

- [ ] Append a failing schema test method to the `TestLhRhSchema` class in `test_lh_rh_release.py`:
```python
	def test_finished_part_mirror_has_orientation_and_generated_bom(self) -> None:
		meta = frappe.get_meta("Layout Finished Part")
		self.assertTrue(meta.has_field("orientation"))
		self.assertTrue(meta.has_field("generated_bom"))
		orientation = meta.get_field("orientation")
		self.assertEqual(orientation.fieldtype, "Select")
		self.assertEqual(
			[line for line in (orientation.options or "").split("\n") if line], ["LH", "RH"]
		)
```

- [ ] Run and see it FAIL:
```
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_lh_rh_release
```
Expected failure: `AssertionError: False is not true` from the new method (`orientation` absent on the mirror). `generated_bom` must already be present from Phase 0 — if that assertion fails, Phase 0 has not landed (see Dependencies gate).

- [ ] Add `orientation` to `field_order` in `layout_finished_part.json`. Replace the `field_order` block (lines 8-13):
```json
 "field_order": [
  "finished_part_item",
  "orientation",
  "generated_bom",
  "bom_quantity",
  "scrap_weight_kg",
  "raw_material_weight_kg"
 ],
```
> Note: this assumes Phase 0 already added `generated_bom` to both `field_order` and `fields`. Keep the existing `generated_bom` ordering Phase 0 chose if it differs — only ensure `orientation` is present in `field_order`. Do not remove or duplicate `generated_bom`.

- [ ] Add the `orientation` field definition to the `fields` array in `layout_finished_part.json`, immediately after the `finished_part_item` field object (which ends at line 22 in the pre-Phase-0 file):
```json
  {
   "fieldname": "orientation",
   "fieldtype": "Select",
   "in_list_view": 1,
   "label": "Orientation",
   "options": "LH\nRH",
   "read_only": 1
  },
```

- [ ] Apply the schema:
```
bench --site development.localhost migrate
```
Expected: migrate completes without error.

- [ ] Run and see it PASS:
```
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_lh_rh_release
```
Expected: all 5 schema tests pass.

- [ ] Commit:
```
git add sheet_cutting_layout/sheet_cutting_layout/doctype/layout_finished_part/layout_finished_part.json sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_lh_rh_release.py
git commit -m "feat: add orientation column to Layout Finished Part mirror

The read-only mirror now records each produced item's orientation
alongside the generated_bom column carried over from Phase 0.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task group D: Validation

### Task 7: Validate LH/RH twin and orientation

When `is_lh_rh` is set: `orientation` and `twin_finished_part` are required; the twin code must be
alphanumeric and end with `SHR` (reusing the existing `validate_finished_part_code` rule), distinct from
the primary `finished_part_code`, and distinct from the `raw_material_item`. The pure validation logic is
exercised through `FrappeTestCase` via the bench runner (the frappe-less `_FrappeCompat` shim in
`validators.py` is removed by Phase 0, so `frappe.throw`/`frappe.ValidationError` is the real Frappe one).

**Files:**
- Modify: `sheet_cutting_layout/services/validators.py` (`validate_sheet_cutting_layout` at lines 91-115; `SheetCuttingLayoutDocument` Protocol at lines 51-75; append a new `_validate_lh_rh_fields` function)
- Create: `sheet_cutting_layout/services/tests/test_lh_rh_validation.py`

- [ ] Write the failing unit test `sheet_cutting_layout/services/tests/test_lh_rh_validation.py`:
```python
from __future__ import annotations

from types import SimpleNamespace

import frappe

from sheet_cutting_layout.services.validators import _validate_lh_rh_fields
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


def _layout(**overrides: object) -> SimpleNamespace:
	defaults = dict(
		finished_part_code="0102AAG06400SHR",
		raw_material_item="SCLTESTRM001",
		is_lh_rh=1,
		orientation="LH",
		twin_finished_part="0102AAG06410SHR",
	)
	defaults.update(overrides)
	return SimpleNamespace(**defaults)


class TestValidateLhRhFields(SheetCuttingLayoutTestCase):
	def test_valid_lh_rh_layout_passes(self) -> None:
		_validate_lh_rh_fields(_layout())  # no raise

	def test_non_lh_rh_layout_skips_validation(self) -> None:
		_validate_lh_rh_fields(
			_layout(is_lh_rh=0, orientation=None, twin_finished_part=None)
		)  # no raise

	def test_missing_orientation_raises(self) -> None:
		with self.assertRaisesRegex(frappe.ValidationError, "Orientation is required"):
			_validate_lh_rh_fields(_layout(orientation=None))

	def test_missing_twin_raises(self) -> None:
		with self.assertRaisesRegex(frappe.ValidationError, "Twin finished part is required"):
			_validate_lh_rh_fields(_layout(twin_finished_part=""))

	def test_twin_must_end_with_shr(self) -> None:
		with self.assertRaisesRegex(frappe.ValidationError, "must end with SHR"):
			_validate_lh_rh_fields(_layout(twin_finished_part="0102AAG06410BLK"))

	def test_twin_must_be_alphanumeric(self) -> None:
		with self.assertRaisesRegex(frappe.ValidationError, "alphanumeric"):
			_validate_lh_rh_fields(_layout(twin_finished_part="0102-AAG-SHR"))

	def test_twin_distinct_from_primary(self) -> None:
		with self.assertRaisesRegex(frappe.ValidationError, "must differ from the primary"):
			_validate_lh_rh_fields(_layout(twin_finished_part="0102AAG06400SHR"))

	def test_twin_distinct_from_raw_material(self) -> None:
		with self.assertRaisesRegex(frappe.ValidationError, "cannot be the raw material"):
			_validate_lh_rh_fields(
				_layout(raw_material_item="0102AAG06410SHR", twin_finished_part="0102AAG06410SHR")
			)
```

> **The `assertRaisesRegex` fragments are load-bearing substrings of the throw messages.** Each regex
> argument above (`"Orientation is required"`, `"Twin finished part is required"`, `"must end with SHR"`,
> `"alphanumeric"`, `"must differ from the primary"`, `"cannot be the raw material"`) is a literal
> substring of the corresponding `frappe.throw(_(...))` message in the `_validate_lh_rh_fields`
> implementation defined later in this task. These tests couple to the message wording on purpose. If you
> reword any throw message (e.g. for clarity or i18n), you MUST update the matching fragment here, or the
> test will fail spuriously. Do not loosen the regexes to `.` or `""` to dodge this — that defeats the
> assertion that the *correct* error path fired.

- [ ] Run and see it FAIL:
```
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.services.tests.test_lh_rh_validation
```
Expected failure: `ImportError: cannot import name '_validate_lh_rh_fields' from 'sheet_cutting_layout.services.validators'`.

- [ ] Extend the `SheetCuttingLayoutDocument` Protocol so the new attributes are documented. In `sheet_cutting_layout/services/validators.py`, add these three lines to the Protocol (after `finished_part_code` at line 52):
```python
	is_lh_rh: int | None
	orientation: str | None
	twin_finished_part: str | None
```

- [ ] Append the `_validate_lh_rh_fields` implementation to `sheet_cutting_layout/services/validators.py` (place it after `_validate_parent_finished_part_fields`, before `_validate_end_piece_required_fields` at line 294):
```python
def _validate_lh_rh_fields(layout: SheetCuttingLayoutDocument) -> None:
	if not getattr(layout, "is_lh_rh", None):
		return

	orientation = str(getattr(layout, "orientation", "") or "").strip()
	if orientation not in {"LH", "RH"}:
		frappe.throw(_("Orientation is required and must be LH or RH for symmetric parts"))

	twin = str(getattr(layout, "twin_finished_part", "") or "").strip()
	if not twin:
		frappe.throw(_("Twin finished part is required for symmetric LH/RH parts"))

	if not ALNUM_RE.fullmatch(twin):
		frappe.throw(_("Twin finished part item code must be alphanumeric only"))
	if not twin.endswith("SHR"):
		frappe.throw(_("Twin finished part item code must end with SHR"))

	primary = getattr(layout, "finished_part_code", None)
	if _same_item_code(twin, primary):
		frappe.throw(_("Twin finished part must differ from the primary finished part"))

	raw_material_item = getattr(layout, "raw_material_item", None)
	if _same_item_code(twin, raw_material_item):
		frappe.throw(_("Twin finished part cannot be the raw material item"))
```

- [ ] Run and see it PASS:
```
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.services.tests.test_lh_rh_validation
```
Expected: all 8 tests pass.

- [ ] Lint from repo root, then commit:
```
python -m ruff check . && python -m ruff format --check .
git add sheet_cutting_layout/services/validators.py sheet_cutting_layout/services/tests/test_lh_rh_validation.py
git commit -m "feat: validate LH/RH twin and orientation fields

Require orientation + twin when is_lh_rh; twin must be alphanumeric,
end SHR, and differ from the primary part and the raw material.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Wire `_validate_lh_rh_fields` into the validation pipeline

**Files:**
- Modify: `sheet_cutting_layout/services/validators.py` (`validate_sheet_cutting_layout` at lines 91-115)
- Modify: `sheet_cutting_layout/services/tests/test_lh_rh_validation.py` (append a test class)

- [ ] Append the failing test class to `sheet_cutting_layout/services/tests/test_lh_rh_validation.py`:
```python
from unittest.mock import patch  # noqa: E402

from sheet_cutting_layout.services import validators  # noqa: E402


class TestValidationPipelineCallsLhRh(SheetCuttingLayoutTestCase):
	def test_validate_sheet_cutting_layout_invokes_lh_rh_validator(self) -> None:
		layout = _layout()
		with patch.object(validators, "_validate_lh_rh_fields") as lh_rh_validator:
			try:
				validators.validate_sheet_cutting_layout(layout)
			except Exception:
				# Other validators may fail on this minimal SimpleNamespace; we only
				# assert the LH/RH validator was reached before any such failure if it
				# runs early, otherwise patch isolates it. Re-raise only if not called.
				if not lh_rh_validator.called:
					raise
		lh_rh_validator.assert_called_once_with(layout)
```

- [ ] Run and see it FAIL:
```
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.services.tests.test_lh_rh_validation
```
Expected failure: `AssertionError: Expected '_validate_lh_rh_fields' to have been called once. Called 0 times.` (validator not yet wired in).

- [ ] Wire the call into `validate_sheet_cutting_layout`. In `sheet_cutting_layout/services/validators.py`, add the call immediately after `_validate_parent_finished_part_fields(layout)` (currently line 101):
```python
	_validate_parent_finished_part_fields(layout)
	_validate_lh_rh_fields(layout)
```

- [ ] Run and see it PASS:
```
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.services.tests.test_lh_rh_validation
```
Expected: all tests pass (the new class plus the Task 7 class).

- [ ] Lint from repo root, then commit:
```
python -m ruff check . && python -m ruff format --check .
git add sheet_cutting_layout/services/validators.py sheet_cutting_layout/services/tests/test_lh_rh_validation.py
git commit -m "feat: invoke LH/RH validator from validate_sheet_cutting_layout

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task group E: Client form behavior

### Task 9: Toggle and clear LH/RH fields, default orientation in client JS

The doctype JSON's `depends_on`/`mandatory_depends_on` already handle visibility and required state in the
form. The client JS adds: clearing `orientation` and `twin_finished_part` when `is_lh_rh` is unchecked
(so stale values do not persist), and a default `orientation` of `LH` when the box is first checked.

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js` (add an `is_lh_rh` handler to the second `frappe.ui.form.on("Sheet Cutting Layout", {...})` block at lines 437-447)

> **Automated gate for this JS:** client JS has no Python unit test, but the `syncLhRhFields` behavior is
> **not** left ungated — Task 11's Cypress spec exercises it directly. Specifically, after checking the
> `is_lh_rh` box the E2E asserts `orientation` auto-defaults to `LH` (the "default orientation when first
> checked" branch), and after un-checking it asserts `orientation`/`twin_finished_part` are cleared (the
> "clear stale values" branch). So both branches of `syncLhRhFields` are covered end-to-end. Keep the
> change here minimal and deterministic; the E2E in Task 11 is its gate.

- [ ] Add a top-level helper function near the other update helpers in `sheet_cutting_layout.js`. Insert this function immediately before `function addEndPieceBomButtons(frm) {` (line 369):
```javascript
	function syncLhRhFields(frm) {
		if (!frm.doc.is_lh_rh) {
			const updates = [];
			if (frm.doc.orientation) {
				updates.push(frm.set_value("orientation", null));
			}
			if (frm.doc.twin_finished_part) {
				updates.push(frm.set_value("twin_finished_part", null));
			}
			return Promise.all(updates);
		}
		if (!frm.doc.orientation) {
			return frm.set_value("orientation", "LH");
		}
		return Promise.resolve();
	}
```

- [ ] Register the `is_lh_rh` field handler. In the second `frappe.ui.form.on("Sheet Cutting Layout", {...})` block (lines 437-447), add the handler after `net_weight_per_part_kg: updateParentWeightsAndConsumption,` (line 446):
```javascript
		net_weight_per_part_kg: updateParentWeightsAndConsumption,
		is_lh_rh: syncLhRhFields,
```

- [ ] Lint the JS (Prettier is configured via pre-commit; verify formatting). From the repo root run the project's JS check via pre-commit if available, otherwise rely on the E2E gate. Run:
```
pre-commit run prettier --files sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js
```
Expected: `Passed` (or it reformats; re-stage if so). If `pre-commit` is not installed, skip and confirm visually that indentation uses tabs to match the surrounding file.

- [ ] Commit:
```
git add sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js
git commit -m "feat: clear LH/RH twin fields on uncheck and default orientation

Client toggles orientation/twin_finished_part: clears them when LH/RH is
unchecked, defaults orientation to LH when first checked.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task group F: Integration — two linked BOMs, mirror, cancel cascade

### Task 10: Integration test — LH/RH release produces two linked BOMs + mirror, cancel retires both

This exercises the full bench stack: a persisted LH/RH layout released natively (`apply_workflow` →
`on_submit`), producing two Shearing BOMs both linked to the same layout via `BOM.sheet_cutting_layout`,
the `finished_parts` mirror showing both items with orientation + BOM, and a native cancel retiring both
(`_layout_bom_names` gathers both → both end deactivated, `is_active = 0`).

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_lh_rh_release.py` (append an integration test class; add the helper imports at the top of the file)

> The integration helpers reuse the same dependency-seeding pattern as `make_layout`
> (`sheet_cutting_layout/tests/factories.py:183`) and its `ensure_item` / `ensure_project` /
> `ensure_item_group` helpers. This test file defines a local `_make_lh_rh_layout` to keep the
> LH/RH-specific seeding (twin Item + `is_lh_rh`/`orientation`/`twin_finished_part`) self-contained,
> while reusing the shared `register_test_doc` factory for cleanup registration.

- [ ] Append the integration test class to `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_lh_rh_release.py`. First add these imports at the very top of the file (after the existing `from __future__ import annotations`):
```python
from sheet_cutting_layout.tests.factories import register_test_doc
```
Then append:
```python
def _ensure_item(item_code: str, *, item_group: str, stock_uom: str) -> str:
	if frappe.db.exists("Item", item_code):
		return item_code
	doc = {
		"doctype": "Item",
		"item_code": item_code,
		"item_name": item_code,
		"item_group": item_group,
		"stock_uom": stock_uom,
		"is_stock_item": 1,
		"valuation_rate": 1,
	}
	if frappe.get_meta("Item", cached=True).has_field("gst_hsn_code") and frappe.db.exists(
		"DocType", "GST HSN Code"
	):
		if not frappe.db.exists("GST HSN Code", "720810"):
			frappe.get_doc({"doctype": "GST HSN Code", "hsn_code": "720810"}).insert(
				ignore_permissions=True
			)
		doc["gst_hsn_code"] = "720810"
	inserted = frappe.get_doc(doc).insert(ignore_permissions=True)
	register_test_doc("Item", inserted.name)
	return inserted.name


def _ensure_dependencies() -> tuple[str, str]:
	if not frappe.db.exists("Item Group", "SCL-TEST-ITEM-GROUP"):
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": "SCL-TEST-ITEM-GROUP",
				"parent_item_group": "All Item Groups",
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
	project_name = frappe.db.exists("Project", {"project_name": "SCL-TEST-PROJECT"})
	if not project_name:
		project_name = (
			frappe.get_doc({"doctype": "Project", "project_name": "SCL-TEST-PROJECT"})
			.insert(ignore_permissions=True)
			.name
		)
	return "SCL-TEST-ITEM-GROUP", str(project_name)


def _make_lh_rh_layout() -> object:
	suffix = frappe.generate_hash(length=6).upper()
	item_group, project = _ensure_dependencies()
	raw_material_item = _ensure_item("SCLTESTRM001", item_group=item_group, stock_uom="Kg")
	primary = f"SCLTESTLH{suffix}SHR"
	twin = f"SCLTESTRH{suffix}SHR"
	_ensure_item(primary, item_group=item_group, stock_uom="Nos")
	_ensure_item(twin, item_group=item_group, stock_uom="Nos")
	layout = frappe.get_doc(
		{
			"doctype": "Sheet Cutting Layout",
			"layout_code": f"SCL-TEST-LHRH-{suffix}",
			"project": project,
			"raw_material_item": raw_material_item,
			"process_scrap_item": raw_material_item,
			"sheet_thickness_mm": 1,
			"sheet_width_mm": 1250,
			"sheet_length_mm": 2500,
			"strip_thickness_mm": 1,
			"strip_width_mm": 1250,
			"strip_length_mm": 2500,
			"parts_per_strip": 1,
			"no_of_strips": 1,
			"status": "Draft",
			"finished_part_code": primary,
			"is_lh_rh": 1,
			"orientation": "LH",
			"twin_finished_part": twin,
			"net_weight_per_part_kg": 0,
			"finished_parts": [],
			"end_pieces": [],
		}
	)
	layout.insert(ignore_permissions=True)
	register_test_doc("Sheet Cutting Layout", layout.name)
	# Balance the sheet: net == gross so consumption validates and scrap is zero.
	layout.reload()
	layout.net_weight_per_part_kg = layout.gross_weight_per_part_kg
	layout.save(ignore_permissions=True)
	return layout


def _release(layout: object) -> object:
	"""Drive native release: advance to Approved by Purchase, then MR Release."""
	from frappe.model.workflow import apply_workflow

	layout.db_set("status", "Approved by Purchase", update_modified=False)
	layout.reload()
	apply_workflow(layout, "MR Release")
	layout.reload()
	return layout


class TestLhRhRelease(SheetCuttingLayoutTestCase):
	def test_lh_rh_release_creates_two_boms_both_linked_to_layout(self) -> None:
		layout = _release(_make_lh_rh_layout())

		self.assertEqual(layout.status, "Released")
		bom_names = frappe.get_all(
			"BOM", filters={"sheet_cutting_layout": layout.name}, pluck="name"
		)
		self.assertEqual(len(bom_names), 2)
		for bom_name in bom_names:
			register_test_doc("BOM", bom_name)
			bom = frappe.get_doc("BOM", bom_name)
			self.assertEqual(bom.sheet_cutting_layout, layout.name)
			self.assertEqual(bom.custom_operation, "Shearing")
			self.assertEqual(int(bom.is_active), 1)

		bom_items = sorted(frappe.get_value("BOM", name, "item") for name in bom_names)
		self.assertEqual(bom_items, sorted([layout.finished_part_code, layout.twin_finished_part]))

	def test_lh_rh_mirror_shows_both_items_with_orientation_and_bom(self) -> None:
		layout = _release(_make_lh_rh_layout())

		mirror = sorted(layout.finished_parts, key=lambda row: row.orientation)
		self.assertEqual(len(mirror), 2)
		orientations = [row.orientation for row in mirror]
		self.assertEqual(orientations, ["LH", "RH"])
		items = {row.orientation: row.finished_part_item for row in mirror}
		self.assertEqual(items["LH"], layout.finished_part_code)
		self.assertEqual(items["RH"], layout.twin_finished_part)
		for row in mirror:
			self.assertTrue(row.generated_bom)
			register_test_doc("BOM", row.generated_bom)
			self.assertEqual(
				frappe.get_value("BOM", row.generated_bom, "sheet_cutting_layout"), layout.name
			)

	def test_two_generated_boms_are_structurally_identical(self) -> None:
		layout = _release(_make_lh_rh_layout())
		bom_names = frappe.get_all(
			"BOM", filters={"sheet_cutting_layout": layout.name}, pluck="name"
		)
		for bom_name in bom_names:
			register_test_doc("BOM", bom_name)
		boms = [frappe.get_doc("BOM", name) for name in bom_names]

		def signature(bom: object) -> tuple:
			items = sorted((row.item_code, row.qty) for row in bom.items)
			scrap = sorted((row.item_code, row.stock_qty) for row in bom.scrap_items)
			return (bom.quantity, tuple(items), tuple(scrap))

		self.assertEqual(signature(boms[0]), signature(boms[1]))

	def test_cancel_retires_both_boms(self) -> None:
		layout = _release(_make_lh_rh_layout())
		bom_names = frappe.get_all(
			"BOM", filters={"sheet_cutting_layout": layout.name}, pluck="name"
		)
		for bom_name in bom_names:
			register_test_doc("BOM", bom_name)
		self.assertEqual(len(bom_names), 2)

		layout.cancel()

		for bom_name in bom_names:
			self.assertEqual(int(frappe.get_value("BOM", bom_name, "is_active")), 0)
```

> **This task adds no new production code** — it is the integration gate proving Tasks 1-8 compose
> end-to-end. Because the production behavior already landed in Tasks 3/4, the tests would pass on the
> first run, which is *not* a valid "see it FAIL" observation. So the red step below is **mandatory and
> explicit**: you deterministically revert the Task 3 twin-expansion edit, observe the genuine failure,
> then restore it. Do not skip it and do not treat "it passed" as the red step.

- [ ] **Mandatory red step — observe a genuine failure by reverting Task 3's twin expansion.** Temporarily
  collapse `_parent_finished_part_rows` back to a single-row (primary-only) return so the LH/RH expansion
  is gone, then run the integration tests and confirm they FAIL. From the repo root
  `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`, stash only the release-service change:
```
git stash push -- sheet_cutting_layout/services/release_service.py
```
  Then from `/Users/gurudattkulkarni/Workspace/bench15` run:
```
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_lh_rh_release
```
  Expected FAIL (deterministic): `test_lh_rh_release_creates_two_boms_both_linked_to_layout` fails with
  `AssertionError: 1 != 2` (only the primary BOM is created — no twin expansion), and
  `test_lh_rh_mirror_shows_both_items_with_orientation_and_bom`, `test_two_generated_boms_are_structurally_identical`,
  and `test_cancel_retires_both_boms` fail for the same single-BOM reason. The schema tests (Tasks 5-6)
  still pass. This is the canonical red observation for Task 10.

- [ ] Restore Task 3's twin expansion:
```
git stash pop
```
  Confirm `_parent_finished_part_rows` again contains the `twin_finished_part_row(layout)` append (Task 3).

- [ ] Run and see it PASS:
```
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_lh_rh_release
```
Expected: the schema tests (Tasks 5-6) and the four new integration tests in `TestLhRhRelease` all PASS, because Tasks 1-8 implement the behavior. If any integration test still FAILS, debug:
  - If only **one** BOM is created → `_parent_finished_part_rows` is not expanding (re-confirm `git stash pop` restored Task 3).
  - If the mirror lacks `orientation`/`generated_bom` → re-check Task 4 and Task 6.
  - If `cancel()` leaves a BOM `is_active = 1` → confirm Phase 0's native `on_cancel` + `ignore_linked_doctypes = ["BOM"]` is in place and `_layout_bom_names` (locate by symbol in `release_service.py`) gathers via the `sheet_cutting_layout` backlink query — both BOMs share that link so both are returned.

- [ ] Confirm PASS:
```
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_lh_rh_release
```
Expected: all schema + integration tests pass.

- [ ] Run the full app Python suite to confirm no regressions:
```
bench --site development.localhost run-tests --app sheet_cutting_layout
```
Expected: green. (If Phase 0 removed `test_release_service.py`'s `unittest_adapter` dependency, that suite already runs bench-native; do not re-introduce the adapter.)

- [ ] Lint from repo root, then commit:
```
python -m ruff check . && python -m ruff format --check .
git add sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_lh_rh_release.py
git commit -m "test: integration coverage for LH/RH dual-BOM release and cancel

Releasing an LH/RH layout creates two structurally identical Shearing
BOMs both linked to the layout; the mirror shows both with orientation;
cancel retires both.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task group G: End-to-end

### Task 11: Cypress E2E — check LH/RH, pick twin + orientation, release, assert mirror

This spec is also the automated gate for the Task 9 client JS (`syncLhRhFields`): it asserts that
checking `is_lh_rh` auto-defaults `orientation` to `LH`, and that un-checking it clears
`orientation` + `twin_finished_part`. Both branches of `syncLhRhFields` are therefore exercised here
before the release assertions run.

**Files:**
- Create: `cypress/integration/sheet_cutting_layout_lh_rh.js`

> Model this spec on the existing `cypress/integration/sheet_cutting_layout_release.js`. Read that file
> first to reuse its login/session and layout-creation conventions (selectors, `cy.fill_field`, workflow
> action buttons). The spec below uses Frappe's standard Cypress helpers (`cy.login`,
> `cy.new_form`/`cy.visit`, `cy.fill_field`, `cy.get_field`). Adjust selector helpers to match what the
> existing release spec already established in this repo.

- [ ] Read the existing release spec to reuse conventions:
```
cat cypress/integration/sheet_cutting_layout_release.js
```
(Use the Read tool, not `cat`, when executing.) Note its setup/login pattern and how it seeds Items/Project and advances the workflow to `Released`.

- [ ] Create `cypress/integration/sheet_cutting_layout_lh_rh.js`:
```javascript
context("Sheet Cutting Layout — LH/RH symmetric parts", () => {
	before(() => {
		cy.login();
		// Seed shared masters once via the API so the form only edits the layout.
		cy.call("frappe.client.insert", {
			doc: {
				doctype: "Item Group",
				item_group_name: "SCL-TEST-ITEM-GROUP",
				parent_item_group: "All Item Groups",
				is_group: 0,
			},
		}).then(
			() => {},
			() => {}
		);
	});

	beforeEach(() => {
		cy.login();
	});

	it("releases an LH/RH layout and shows both items in the mirror", () => {
		const suffix = Math.random().toString(36).slice(2, 8).toUpperCase();
		const rawMaterial = "SCLTESTRM001";
		const primary = `SCLTESTLH${suffix}SHR`;
		const twin = `SCLTESTRH${suffix}SHR`;

		const ensureItem = (code, uom) =>
			cy
				.call("frappe.client.insert", {
					doc: {
						doctype: "Item",
						item_code: code,
						item_name: code,
						item_group: "SCL-TEST-ITEM-GROUP",
						stock_uom: uom,
						is_stock_item: 1,
						valuation_rate: 1,
					},
				})
				.then(
					() => {},
					() => {}
				);

		ensureItem(rawMaterial, "Kg");
		ensureItem(primary, "Nos");
		ensureItem(twin, "Nos");
		cy.call("frappe.client.insert", {
			doc: { doctype: "Project", project_name: "SCL-TEST-PROJECT" },
		}).then(
			() => {},
			() => {}
		);

		cy.visit("/app/sheet-cutting-layout/new");
		cy.fill_field("layout_code", `SCL-TEST-LHRH-${suffix}`, "Data");
		cy.fill_field("project", "SCL-TEST-PROJECT", "Link");
		cy.fill_field("raw_material_item", rawMaterial, "Link");
		cy.fill_field("process_scrap_item", rawMaterial, "Link");
		cy.fill_field("sheet_thickness_mm", "1", "Float");
		cy.fill_field("sheet_width_mm", "1250", "Float");
		cy.fill_field("sheet_length_mm", "2500", "Float");
		cy.fill_field("strip_thickness_mm", "1", "Float");
		cy.fill_field("strip_width_mm", "1250", "Float");
		cy.fill_field("strip_length_mm", "2500", "Float");
		cy.fill_field("parts_per_strip", "1", "Int");
		cy.fill_field("no_of_strips", "1", "Int");
		cy.fill_field("finished_part_code", primary, "Link");

		// Check LH/RH and confirm dependent fields appear and the client
		// syncLhRhFields handler defaults orientation to "LH" on first check.
		cy.get_field("is_lh_rh", "Check").check({ force: true });
		cy.get_field("orientation").should("exist");
		// Exercises the syncLhRhFields "default orientation when first checked" branch.
		cy.window()
			.its("cur_frm.doc.orientation", { timeout: 10000 })
			.should("eq", "LH");

		// Exercise the "clear stale values on uncheck" branch: set a twin, uncheck,
		// and assert both dependent fields were cleared by syncLhRhFields.
		cy.fill_field("twin_finished_part", twin, "Link");
		cy.get_field("is_lh_rh", "Check").uncheck({ force: true });
		cy.window().its("cur_frm.doc.orientation").should("not.be.ok");
		cy.window().its("cur_frm.doc.twin_finished_part").should("not.be.ok");

		// Re-check and re-enter the twin for the actual release path; orientation
		// defaults back to LH again.
		cy.get_field("is_lh_rh", "Check").check({ force: true });
		cy.window().its("cur_frm.doc.orientation").should("eq", "LH");
		cy.fill_field("twin_finished_part", twin, "Link");

		// net = gross so the sheet balances; read gross then set net to match.
		cy.get_field("gross_weight_per_part_kg")
			.invoke("val")
			.then((gross) => {
				cy.fill_field("net_weight_per_part_kg", String(gross), "Float");
			});

		cy.findByRole("button", { name: "Save" }).click({ force: true });
		cy.get(".indicator-pill").should("be.visible");

		// Advance through the workflow to Released (button labels per the workflow fixture).
		const advance = (label) => {
			cy.get(".page-actions").findByText("Actions").click({ force: true });
			cy.get(".dropdown-menu").findByText(label).click({ force: true });
			cy.get(".indicator-pill", { timeout: 20000 }).should("be.visible");
		};
		advance("Submit for Check");
		advance("Project Manager Approves");
		advance("Purchase Approves");
		advance("MR Release");

		// Mirror shows both produced items.
		cy.get('[data-fieldname="finished_parts"]').within(() => {
			cy.contains(primary).should("exist");
			cy.contains(twin).should("exist");
			cy.contains("LH").should("exist");
			cy.contains("RH").should("exist");
		});

		// Both BOMs reference the layout.
		cy.location("pathname").then((pathname) => {
			const layoutName = decodeURIComponent(pathname.split("/").pop());
			cy.call("frappe.client.get_list", {
				doctype: "BOM",
				filters: { sheet_cutting_layout: layoutName },
				fields: ["name"],
			}).then((response) => {
				expect(response.message.length).to.equal(2);
			});
		});
	});
});
```

> The workflow action labels (`Submit for Check`, `Project Manager Approves`, `Purchase Approves`,
> `MR Release`) must match the transitions in `sheet_cutting_layout/fixtures/workflow.json`. Open that
> file and confirm the exact action names before running; adjust the `advance(...)` calls if they differ.

- [ ] Run the E2E spec headless. From `/Users/gurudattkulkarni/Workspace/bench15`:
```
bench --site development.localhost run-ui-tests sheet_cutting_layout --headless --spec cypress/integration/sheet_cutting_layout_lh_rh.js
```
Expected: first run may FAIL on a selector/label mismatch — this is the red step. Fix selectors against the real DOM (use the existing release spec's proven selectors), then re-run until the assertions (both items + LH + RH in the mirror, exactly 2 BOMs linked) pass.

- [ ] Confirm PASS (full UI suite, to ensure the new spec coexists):
```
bench --site development.localhost run-ui-tests sheet_cutting_layout --headless
```
Expected: green.

- [ ] Commit:
```
git add cypress/integration/sheet_cutting_layout_lh_rh.js
git commit -m "test: e2e LH/RH release shows both items in the mirror

Cypress spec checks the LH/RH box (asserting syncLhRhFields defaults
orientation to LH and clears the twin fields on uncheck), picks twin +
orientation, releases via the workflow, and asserts both items appear in
finished_parts and two BOMs link to the layout.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] Run the complete Python suite from `/Users/gurudattkulkarni/Workspace/bench15`:
```
bench --site development.localhost run-tests --app sheet_cutting_layout
```
Expected: all green, including the new `test_lh_rh_expansion`, `test_lh_rh_release`, `test_lh_rh_validation`, and the `test_lh_rh_release.py` integration class.

- [ ] Run the complete UI suite:
```
bench --site development.localhost run-ui-tests sheet_cutting_layout --headless
```
Expected: green.

- [ ] Run lint gates from the repo root `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
```
python -m ruff check . && python -m ruff format --check .
```
Expected: clean.

- [ ] Confirm coverage remains above 96% per `docs/development-philosophy.md`. If the bench runner is configured with coverage, run:
```
bench --site development.localhost run-tests --app sheet_cutting_layout --coverage
```
and verify the reported percentage. If any new line is uncovered (e.g. `_opposite_orientation` returning `None`, or `joined_part_number_label` single-code branches), the unit tests in Tasks 1-2 already cover them — confirm.

## Notes for the executor

- **Do not re-implement the cancel/retire path.** Phase 0 already provides native `on_cancel` +
  `ignore_linked_doctypes = ["BOM"]`. Phase 1 relies on `_layout_bom_names` (release_service.py:251-267)
  finding both BOMs through the shared `BOM.sheet_cutting_layout` backlink — which `_insert_frappe_bom`
  (release_service.py:368-429) sets for every generated BOM. Task 10's `test_cancel_retires_both_boms`
  proves it; if it fails, the fault is in Phase 0's cancel wiring, not in Phase 1.
- **The parent `generated_bom` holds the primary only.** Per the Phase-0 fix, after release the parent
  `Sheet Cutting Layout.generated_bom` points at the primary part's BOM; the twin's BOM lives in the
  mirror row. Do not assert the parent field equals the twin BOM.
- **Net == gross in the integration/E2E layouts** keeps the sheet-consumption validator
  (`_validate_complete_sheet_consumption`, validators.py:486-508) balanced with zero process scrap, so the
  release path does not require a valid scrap valuation rate. This mirrors
  `test_mr_release_generates_native_bom_with_test_uom_items` in the existing controller test.
- **Twin Item must exist** before release because the generated BOM's FG item must be a real Item; the
  integration helper seeds it via `_ensure_item`, and the E2E spec seeds it via `frappe.client.insert`.
