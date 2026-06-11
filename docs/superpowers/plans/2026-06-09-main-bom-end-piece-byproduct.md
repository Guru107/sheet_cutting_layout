# Main BOM End-Piece Byproduct Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Main BOMs generated during MR Release include reusable end pieces as BOM scrap/byproduct rows and reject layouts whose generated BOM rows do not reconcile to the raw material sheet weight.

**Architecture:** Add a small shared end-piece Item service that owns deterministic end-piece Item codes and generated Item creation. Keep `bom_service` responsible for pure BOM row construction, with an injectable resolver so tests can derive codes without creating Items while release can create/link Items before persisting BOMs. Keep `release_service` responsible for Frappe persistence and `validators` responsible for save-time/release-time consistency checks.

**Tech Stack:** Frappe/ERPNext app, Python service modules, bench-native `unittest`/pytest-adapter tests via `bench --site development.localhost run-tests`.

---

## File Structure

- Add `sheet_cutting_layout/services/end_piece_item_service.py`
  - Owns `format_code_number()`, `derive_end_piece_item_code()`, and `ensure_end_piece_item()`.
  - Creates generated end-piece Items with `stock_uom = "Kg"`, reciprocal UOM rows, raw-material valuation/item group, and finished-item HSN.
  - Does not import `bom_service` or `validators`; this prevents a circular import.
- Modify `sheet_cutting_layout/services/validators.py`
  - Imports `derive_end_piece_item_code()` and `format_code_number()` from the shared service.
  - Adds main BOM weight-balance validation using `bom_service.expected_main_bom_weight_balance()`.
- Modify `sheet_cutting_layout/services/bom_service.py`
  - Adds reusable end-piece byproduct rows to `BomDocument.scrap_items`.
  - Adds an injectable `EndPieceItemCodeResolver`.
  - Adds a pure expected-weight-balance helper used by validators and tests.
- Modify `sheet_cutting_layout/services/release_service.py`
  - Passes a resolver that calls `ensure_end_piece_item()` and links `row.end_piece_item_code` before BOM insert.
- Modify `sheet_cutting_layout/services/end_piece_bom_service.py`
  - Reuses `ensure_end_piece_item()` instead of owning duplicate Item creation logic.
- Modify `sheet_cutting_layout/tests/test_bom_service.py`
  - Adds behavior tests for reusable end-piece byproduct rows and main BOM mass balance.
- Modify `sheet_cutting_layout/tests/test_release_service.py`
  - Adds release-path behavior tests for Item ensure/linking and BOM scrap row persistence.
- Modify `sheet_cutting_layout/tests/test_end_piece_bom_service.py`
  - Updates fakes to patch the shared Item service and preserves existing generated Item behavior.

No migration or backfill is required.

---

### Task 1: Add Failing Main BOM Behavior Tests

**Files:**
- Modify: `sheet_cutting_layout/tests/test_bom_service.py`

- [ ] **Step 1: Extend the BOM service test fixtures**

Replace the `EndPiece` dataclass in `sheet_cutting_layout/tests/test_bom_service.py` with:

```python
@dataclass
class EndPiece:
	weight_kg: float
	qty_per_sheet: float = 1
	disposition: str = "Reuse"
	scrap_item: str | None = None
	end_piece_item_code: str | None = None
	used_for_finished_part: str | None = "FG002SHR"
	width_mm: float | None = 1250
	length_mm: float | None = 179
```

Add `sheet_thickness_mm` to the `Layout` dataclass:

```python
@dataclass
class Layout:
	raw_material_item: str = "RAW-SHEET"
	process_scrap_item: str = "PROCESS-SCRAP"
	weight_per_sheet_kg: float = 50
	no_of_strips: int = 11
	finished_part_code: str = "FINISHED-SHR"
	net_weight_per_part_kg: float = 12.5
	gross_weight_per_part_kg: float = 12.5
	scrap_weight_per_part_kg: float = 0
	parts_per_sheet: int = 4
	sheet_thickness_mm: float | None = 1.6
	end_pieces: list[EndPiece] = field(default_factory=list)
```

- [ ] **Step 2: Replace the old reuse expectation with a byproduct expectation**

Replace `test_reuse_end_pieces_do_not_create_shearing_bom_scrap_rows()` with:

```python
def test_reuse_end_pieces_create_main_bom_byproduct_rows() -> None:
	bom_service = import_bom_service()

	bom = bom_service.build_bom_from_layout_row(
		Layout(
			sheet_thickness_mm=1.6,
			end_pieces=[
				EndPiece(weight_kg=2.81388, used_for_finished_part="FG002SHR"),
			],
		),
		FinishedPart(parts_per_sheet=77),
	)

	assert [(row.item_code, row.qty, row.uom, row.row_type) for row in bom.scrap_items] == [
		("FG002SHR-EP-1.6x1250x179", 2.81388, "Kg", "end_piece_byproduct"),
	]
```

- [ ] **Step 3: Add a test that process scrap and reuse byproduct rows both appear**

Add this test near `test_process_scrap_row_is_included_when_scrap_weight_is_positive()`:

```python
def test_process_scrap_and_reuse_end_piece_byproduct_rows_are_both_included() -> None:
	bom_service = import_bom_service()

	bom = bom_service.build_bom_from_layout_row(
		Layout(
			process_scrap_item="MSScrap",
			sheet_thickness_mm=1.6,
			end_pieces=[EndPiece(weight_kg=2.81388, used_for_finished_part="FG002SHR")],
		),
		FinishedPart(parts_per_sheet=77, scrap_weight_per_part_kg=0.184846),
	)

	assert [(row.item_code, row.qty, row.row_type) for row in bom.scrap_items] == [
		("MSScrap", 14.233142, "process_scrap"),
		("FG002SHR-EP-1.6x1250x179", 2.81388, "end_piece_byproduct"),
	]
```

- [ ] **Step 4: Update expected consumption coverage for `002-R2`**

In `TestBomService.test_main_bom_expected_consumption_helper_matches_parent_fields`, add one reuse
end-piece row to the layout:

```python
end_pieces=[
	EndPiece(
		weight_kg=2.81388,
		used_for_finished_part="FG002SHR",
		width_mm=1250,
		length_mm=179,
	)
],
```

Then replace the scrap-row assertion with:

```python
self.assertEqual(
	[(row.item_code, row.qty, row.row_type) for row in expected.scrap_rows],
	[
		("PROCESS-SCRAP", 14.233142, "process_scrap"),
		("FG002SHR-EP-1.6x1250x179", 2.81388, "end_piece_byproduct"),
	],
)
self.assertAlmostEqual(expected.total_scrap_qty, 17.047022, places=6)
```

- [ ] **Step 5: Add an expected balance helper test**

Add this test to `TestBomService`:

```python
def test_expected_main_bom_weight_balance_includes_reuse_end_piece_byproducts(self) -> None:
	bom_service = import_bom_service()
	layout = Layout(
		raw_material_item="RM001",
		process_scrap_item="MSScrap",
		finished_part_code="FG01SHR",
		net_weight_per_part_kg=0.289,
		parts_per_sheet=77,
		no_of_strips=11,
		weight_per_sheet_kg=39.3,
		gross_weight_per_part_kg=0.473846,
		scrap_weight_per_part_kg=0.184846,
		sheet_thickness_mm=1.6,
		end_pieces=[
			EndPiece(
				weight_kg=2.81388,
				used_for_finished_part="FG002SHR",
				width_mm=1250,
				length_mm=179,
			)
		],
	)

	balance = bom_service.expected_main_bom_weight_balance(layout)

	self.assertAlmostEqual(balance.raw_material_weight_kg, 39.3, places=6)
	self.assertAlmostEqual(balance.finished_part_weight_kg, 22.253, places=6)
	self.assertAlmostEqual(balance.scrap_and_byproduct_weight_kg, 17.047022, places=6)
	self.assertAlmostEqual(balance.difference_kg, -0.000022, places=6)
```

- [ ] **Step 6: Run the focused tests and confirm the failure**

Run from `/root/workspace/bench15`:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_service
```

Expected failure before implementation:

```text
AssertionError: Lists differ
```

The failure should show that reuse end pieces are not present as `end_piece_byproduct` rows yet.

---

### Task 2: Extract Shared End-Piece Item Service

**Files:**
- Create: `sheet_cutting_layout/services/end_piece_item_service.py`
- Modify: `sheet_cutting_layout/services/end_piece_bom_service.py`
- Modify: `sheet_cutting_layout/services/validators.py`
- Modify: `sheet_cutting_layout/tests/test_end_piece_bom_service.py`

- [ ] **Step 1: Create the shared service file**

Create `sheet_cutting_layout/services/end_piece_item_service.py` with:

```python
from __future__ import annotations

from typing import Protocol

import frappe

_ = frappe._


class EndPieceRow(Protocol):
	idx: int
	end_piece_item_code: str | None
	width_mm: float | None
	length_mm: float | None
	weight_kg: float | None
	used_for_finished_part: str | None


class LayoutDocument(Protocol):
	raw_material_item: str | None
	sheet_thickness_mm: float | None


def format_code_number(value: float | int | str) -> str:
	return f"{float(value):.6f}".rstrip("0").rstrip(".")


def derive_end_piece_item_code(layout: LayoutDocument, row: EndPieceRow) -> str:
	try:
		item_code = _derive_end_piece_item_code(
			used_for_finished_part=getattr(row, "used_for_finished_part", None),
			thickness_mm=getattr(layout, "sheet_thickness_mm", None),
			width_mm=getattr(row, "width_mm", None),
			length_mm=getattr(row, "length_mm", None),
		)
	except ValueError as error:
		_throw(_("Row {0}: {1}").format(getattr(row, "idx", 0), str(error)))

	max_item_code_length = 140
	if len(item_code) > max_item_code_length:
		_throw(
			_("Row {0}: Generated end piece item code for '{1}' exceeds {2} characters").format(
				getattr(row, "idx", 0),
				_clean(getattr(row, "used_for_finished_part", None)),
				max_item_code_length,
			)
		)
	return item_code


def ensure_end_piece_item(layout: LayoutDocument, row: EndPieceRow) -> str:
	item_code = derive_end_piece_item_code(layout, row)
	if _item_exists(item_code):
		return item_code

	weight_kg = getattr(row, "weight_kg", None)
	if weight_kg is None or weight_kg <= 0:
		_throw(_("Row {0}: End piece weight must be greater than zero").format(getattr(row, "idx", 0)))

	item = frappe.new_doc("Item")
	item.item_code = item_code
	item.item_name = item_code
	item.description = _build_item_description(layout, row)
	item.item_group = _get_value("Item", getattr(layout, "raw_material_item", None), "item_group")
	item.valuation_rate = _get_value("Item", getattr(layout, "raw_material_item", None), "valuation_rate")
	item.gst_hsn_code = _get_value(
		"Item", _clean(getattr(row, "used_for_finished_part", None)), "gst_hsn_code"
	)
	item.stock_uom = "Kg"
	item.is_stock_item = 1
	item.disabled = 0
	_append_app_created_item_uoms(item, stock_uom=item.stock_uom, weight_kg=weight_kg)
	insert_error_types = _item_insert_exception_types()
	if insert_error_types:
		try:
			item.insert(ignore_permissions=True)
		except insert_error_types as error:
			_log_item_insert_error(item_code=item_code, row=row, error=error)
			_throw(
				_("Row {0}: Failed to create end piece item '{1}': {2}").format(
					getattr(row, "idx", 0),
					item_code,
					str(error),
				)
			)
	else:
		item.insert(ignore_permissions=True)
	return item_code


def _derive_end_piece_item_code(
	*,
	used_for_finished_part: str | None,
	thickness_mm: float | None,
	width_mm: float | None,
	length_mm: float | None,
) -> str:
	finished_part = _clean(used_for_finished_part)
	if finished_part is None:
		raise ValueError("Used for finished part is required")
	if thickness_mm is None or thickness_mm <= 0:
		raise ValueError("Sheet thickness is required to derive end piece item code")
	if width_mm is None or width_mm <= 0:
		raise ValueError("End piece width must be greater than zero")
	if length_mm is None or length_mm <= 0:
		raise ValueError("End piece length must be greater than zero")
	return (
		f"{finished_part}-EP-"
		f"{format_code_number(thickness_mm)}x"
		f"{format_code_number(width_mm)}x"
		f"{format_code_number(length_mm)}"
	)


def _append_app_created_item_uoms(item: object, *, stock_uom: str, weight_kg: float) -> None:
	if stock_uom == "Kg":
		item.append("uoms", {"uom": "Kg", "conversion_factor": 1})
		item.append("uoms", {"uom": "Nos", "conversion_factor": weight_kg})
		return
	if stock_uom == "Nos":
		item.append("uoms", {"uom": "Nos", "conversion_factor": 1})
		item.append("uoms", {"uom": "Kg", "conversion_factor": 1 / weight_kg})
		return
	_throw(_("Unsupported stock UOM for app-created Item: {0}").format(stock_uom))


def _build_item_description(layout: LayoutDocument, row: EndPieceRow) -> str:
	raw_material_item = _clean(getattr(layout, "raw_material_item", None)) or "Unknown raw material"
	thickness_mm = format_code_number(getattr(layout, "sheet_thickness_mm", 0))
	width_mm = format_code_number(getattr(row, "width_mm", 0))
	length_mm = format_code_number(getattr(row, "length_mm", 0))
	return f"Derived from {raw_material_item}; End Piece {thickness_mm}x{width_mm}x{length_mm} mm"


def _item_exists(item_code: str) -> bool:
	db = getattr(frappe, "db", None)
	exists = getattr(db, "exists", None)
	if callable(exists):
		return bool(exists("Item", item_code))
	db_exists = getattr(frappe, "db_exists", None)
	if callable(db_exists):
		return bool(db_exists("Item", item_code))
	return False


def _get_value(doctype: str, name: str | None, fieldname: str) -> object:
	db = getattr(frappe, "db", None)
	get_value = getattr(db, "get_value", None)
	if callable(get_value):
		return get_value(doctype, name, fieldname)
	get_value = getattr(frappe, "get_value", None)
	if callable(get_value):
		return get_value(doctype, name, fieldname)
	return None


def _item_insert_exception_types() -> tuple[type[Exception], ...]:
	exception_types: list[type[Exception]] = []
	for attr in ("ValidationError", "DuplicateEntryError"):
		error_type = getattr(frappe, attr, None)
		if isinstance(error_type, type) and issubclass(error_type, Exception):
			exception_types.append(error_type)
	return tuple(dict.fromkeys(exception_types))


def _log_item_insert_error(*, item_code: str, row: EndPieceRow, error: Exception) -> None:
	log_error = getattr(frappe, "log_error", None)
	if not callable(log_error):
		return
	get_traceback = getattr(frappe, "get_traceback", None)
	traceback = get_traceback() if callable(get_traceback) else str(error)
	log_error(
		message=traceback,
		title=f"Row {getattr(row, 'idx', 0)}: Failed to create end piece item '{item_code}'",
	)


def _clean(value: object) -> str | None:
	if value is None:
		return None
	if isinstance(value, str):
		value = value.strip()
		return value or None
	return str(value)


def _throw(message: str) -> None:
	frappe.throw(message)
```

- [ ] **Step 2: Update validators to import shared item-code helpers**

In `sheet_cutting_layout/services/validators.py`, replace the import block:

```python
from sheet_cutting_layout.services.bom_service import BomItemRow, expected_bom_consumption_from_layout
```

with:

```python
from sheet_cutting_layout.services.bom_service import (
	BomItemRow,
	expected_bom_consumption_from_layout,
	expected_main_bom_weight_balance,
)
from sheet_cutting_layout.services.end_piece_item_service import (
	derive_end_piece_item_code,
	format_code_number,
)
```

Remove the local `derive_end_piece_item_code()` and `format_code_number()` definitions from
`validators.py` after the imports are in place.

- [ ] **Step 3: Update end-piece BOM service imports**

In `sheet_cutting_layout/services/end_piece_bom_service.py`, add:

```python
from sheet_cutting_layout.services.end_piece_item_service import ensure_end_piece_item
```

In `generate_end_piece_boms()`, replace:

```python
item_code = _ensure_end_piece_item(layout, row)
```

with:

```python
item_code = ensure_end_piece_item(layout, row)
```

Remove these private helpers from `end_piece_bom_service.py`:

```text
_ensure_end_piece_item
_append_app_created_item_uoms
_derived_item_code
_build_item_description
_item_exists
_get_value
_item_insert_exception_types
_log_item_insert_error
```

Keep `_clean()` in `end_piece_bom_service.py` because BOM generation still uses it.

- [ ] **Step 4: Patch shared-service fakes in end-piece BOM tests**

In `TestEndPieceBomService.setUp()`, add:

```python
self.item_service = importlib.import_module("sheet_cutting_layout.services.end_piece_item_service")
```

In `_install_fakes()`, after creating `fake_frappe`, replace the patch block with:

```python
self.frappe_patch = patch.object(self.service, "frappe", fake_frappe)
self.translation_patch = patch.object(self.service, "_", lambda message: message)
self.item_frappe_patch = patch.object(self.item_service, "frappe", fake_frappe)
self.item_translation_patch = patch.object(self.item_service, "_", lambda message: message)
self.frappe_patch.start()
self.translation_patch.start()
self.item_frappe_patch.start()
self.item_translation_patch.start()
self.addCleanup(self.frappe_patch.stop)
self.addCleanup(self.translation_patch.stop)
self.addCleanup(self.item_frappe_patch.stop)
self.addCleanup(self.item_translation_patch.stop)
```

- [ ] **Step 5: Run end-piece BOM tests**

Run from `/root/workspace/bench15`:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
```

Expected after this task:

```text
OK
```

- [ ] **Step 6: Commit the shared service extraction**

Run from `/root/workspace/sheet_cutting_layout`:

```bash
git add sheet_cutting_layout/services/end_piece_item_service.py sheet_cutting_layout/services/end_piece_bom_service.py sheet_cutting_layout/services/validators.py sheet_cutting_layout/tests/test_end_piece_bom_service.py
git commit -m "refactor: share end-piece item creation"
```

---

### Task 3: Implement Reusable End-Piece Byproduct Rows

**Files:**
- Modify: `sheet_cutting_layout/services/bom_service.py`
- Modify: `sheet_cutting_layout/tests/test_bom_service.py`

- [ ] **Step 1: Update imports, protocols, and row types**

In `sheet_cutting_layout/services/bom_service.py`, add this import:

```python
from sheet_cutting_layout.services.end_piece_item_service import derive_end_piece_item_code
```

Extend `EndPieceRow`:

```python
class EndPieceRow(Protocol):
	weight_kg: float
	qty_per_sheet: float
	disposition: str
	scrap_item: str | None
	end_piece_item_code: str | None
	used_for_finished_part: str | None
	width_mm: float | None
	length_mm: float | None
```

Extend `LayoutDocument`:

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
	end_pieces: Sequence[EndPieceRow]
```

Replace the row type literal with:

```python
BomItemRowType = Literal["raw_material", "process_scrap", "end_piece_scrap", "end_piece_byproduct"]
```

Add this resolver alias near `BomDocumentFactory`:

```python
EndPieceItemCodeResolver = Callable[[LayoutDocument, EndPieceRow], str]
```

- [ ] **Step 2: Add expected balance data**

Add this dataclass after `ExpectedBomConsumption`:

```python
@dataclass
class ExpectedBomWeightBalance:
	raw_material_weight_kg: float
	finished_part_weight_kg: float
	scrap_and_byproduct_weight_kg: float
	difference_kg: float
```

- [ ] **Step 3: Update `build_bom_from_layout_row()`**

Replace the function body with:

```python
def build_bom_from_layout_row(
	layout_doc: LayoutDocument,
	finished_part_row: FinishedPartRow,
	*,
	document_factory: BomDocumentFactory | None = None,
	end_piece_item_code_resolver: EndPieceItemCodeResolver | None = None,
) -> BomDocument:
	bom = _new_bom(finished_part_row.finished_part_item, document_factory)
	bom.quantity = _bom_quantity(layout_doc, finished_part_row)

	weight_rows = build_weight_split_bom_rows(
		raw_material_item=layout_doc.raw_material_item,
		raw_material_qty_kg=_sheet_weight_kg(layout_doc, finished_part_row),
		scrap_qty_kg=finished_part_row.scrap_weight_per_part_kg * finished_part_row.parts_per_sheet,
		scrap_item=layout_doc.process_scrap_item,
		scrap_row_type="process_scrap",
	)
	bom.items.extend(weight_rows.items)
	bom.scrap_items.extend(weight_rows.scrap_items)

	for end_piece in layout_doc.end_pieces:
		if _is_scrap_end_piece(end_piece):
			scrap_item = _required_scrap_item(end_piece)
			bom.scrap_items.append(
				BomItemRow(
					item_code=scrap_item,
					qty=end_piece.weight_kg,
					row_type="end_piece_scrap",
				)
			)
			continue
		if _is_reuse_end_piece(end_piece):
			item_code = _end_piece_byproduct_item_code(
				layout_doc,
				end_piece,
				end_piece_item_code_resolver,
			)
			bom.scrap_items.append(
				BomItemRow(
					item_code=item_code,
					qty=end_piece.weight_kg,
					row_type="end_piece_byproduct",
				)
			)

	return bom
```

- [ ] **Step 4: Update `build_bom_from_layout()`**

Replace the function with:

```python
def build_bom_from_layout(
	layout_doc: LayoutDocument,
	*,
	document_factory: BomDocumentFactory | None = None,
	end_piece_item_code_resolver: EndPieceItemCodeResolver | None = None,
) -> BomDocument:
	return build_bom_from_layout_row(
		layout_doc,
		_parent_finished_part_row(layout_doc),
		document_factory=document_factory,
		end_piece_item_code_resolver=end_piece_item_code_resolver,
	)
```

- [ ] **Step 5: Add byproduct helpers**

Add these helpers near `_is_scrap_end_piece()`:

```python
def _is_reuse_end_piece(end_piece: EndPieceRow) -> bool:
	return str(getattr(end_piece, "disposition", "") or "").strip().lower() == "reuse"


def _end_piece_byproduct_item_code(
	layout_doc: LayoutDocument,
	end_piece: EndPieceRow,
	end_piece_item_code_resolver: EndPieceItemCodeResolver | None,
) -> str:
	existing_item_code = str(getattr(end_piece, "end_piece_item_code", "") or "").strip()
	if existing_item_code:
		return existing_item_code
	if end_piece_item_code_resolver is not None:
		return end_piece_item_code_resolver(layout_doc, end_piece)
	return derive_end_piece_item_code(layout_doc, end_piece)
```

- [ ] **Step 6: Add expected mass-balance helper**

Add this function after `expected_bom_consumption_from_layout()`:

```python
def expected_main_bom_weight_balance(layout_doc: LayoutDocument) -> ExpectedBomWeightBalance:
	finished_part = _parent_finished_part_row(layout_doc)
	bom = build_bom_from_layout_row(layout_doc, finished_part)
	raw_material_weight = sum(row.qty for row in bom.items)
	scrap_and_byproduct_weight = sum(row.qty for row in bom.scrap_items)
	net_weight_per_part = finished_part.gross_weight_per_part_kg - finished_part.scrap_weight_per_part_kg
	finished_part_weight = net_weight_per_part * finished_part.parts_per_sheet
	difference = raw_material_weight - finished_part_weight - scrap_and_byproduct_weight
	return ExpectedBomWeightBalance(
		raw_material_weight_kg=raw_material_weight,
		finished_part_weight_kg=finished_part_weight,
		scrap_and_byproduct_weight_kg=scrap_and_byproduct_weight,
		difference_kg=difference,
	)
```

- [ ] **Step 7: Update invariant test expectations**

In `test_bom_invariants_hold_for_representative_layouts()`, replace the reuse case expected
end-piece scrap quantity from `0` to `3.75`, and sum both byproduct and scrap rows:

```python
end_piece_byproduct_qty = self._sum_bom_qty(bom.scrap_items, "end_piece_byproduct")
total_scrap_qty = process_scrap_qty + end_piece_scrap_qty + end_piece_byproduct_qty
```

Assert byproduct quantity:

```python
self.assertEqual(end_piece_byproduct_qty, expected_end_piece_scrap_qty)
```

- [ ] **Step 8: Run BOM service tests**

Run from `/root/workspace/bench15`:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_service
```

Expected:

```text
OK
```

- [ ] **Step 9: Commit the BOM row implementation**

Run from `/root/workspace/sheet_cutting_layout`:

```bash
git add sheet_cutting_layout/services/bom_service.py sheet_cutting_layout/tests/test_bom_service.py
git commit -m "fix: include reusable end pieces in main bom"
```

---

### Task 4: Wire Release-Time Item Creation

**Files:**
- Modify: `sheet_cutting_layout/services/release_service.py`
- Modify: `sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Import the shared ensure helper**

In `sheet_cutting_layout/services/release_service.py`, add:

```python
from sheet_cutting_layout.services.end_piece_item_service import ensure_end_piece_item
```

- [ ] **Step 2: Pass an ensuring resolver during default BOM creation**

Replace this line in `_default_bom_document_factory()`:

```python
bom = build_bom_from_layout_row(layout, finished_part)  # type: ignore[arg-type]
```

with:

```python
bom = build_bom_from_layout_row(
	layout,
	finished_part,
	end_piece_item_code_resolver=_ensure_and_link_end_piece_item,
)  # type: ignore[arg-type]
```

Add this helper near `_default_bom_document_factory()`:

```python
def _ensure_and_link_end_piece_item(layout: ReleaseLayoutDocument, row: object) -> str:
	item_code = ensure_end_piece_item(layout, row)  # type: ignore[arg-type]
	if hasattr(row, "end_piece_item_code"):
		setattr(row, "end_piece_item_code", item_code)
	return item_code
```

- [ ] **Step 3: Extend the release test `EndPiece` fixture**

In `sheet_cutting_layout/tests/test_release_service.py`, replace the `EndPiece` dataclass with:

```python
@dataclass
class EndPiece:
	weight_kg: float
	qty_per_sheet: float = 1
	disposition: str = "Reuse"
	scrap_item: str | None = None
	end_piece_item_code: str | None = None
	used_for_finished_part: str | None = "FG002SHR"
	width_mm: float | None = 1250
	length_mm: float | None = 179
	idx: int = 1
	bom_quantity: float | None = 1
	net_weight_per_part_kg: float | None = 0
	gross_weight_per_part_kg: float | None = 0
	scrap_weight_per_part_kg: float | None = 0
	bom_scrap_quantity_kg: float | None = 0
```

- [ ] **Step 4: Add a release-level persistence test**

Add this test near `test_frappe_bom_insert_wraps_scrap_rate_resolution_error()`:

```python
def test_default_release_creates_reuse_end_piece_byproduct_row(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import release_service

	created_boms: list[object] = []

	class FrappeBom:
		def __init__(self) -> None:
			self.name = ""
			self.items: list[dict[str, object]] = []
			self.scrap_items: list[dict[str, object]] = []
			self.flags = type("Flags", (), {})()

		def append(self, fieldname: str, row: dict[str, object]) -> None:
			getattr(self, fieldname).append(row)

		def insert(self) -> None:
			self.name = self.name or "BOM-FG01SHR-001"
			created_boms.append(self)

		def submit(self) -> None:
			self.docstatus = 1

	class FrappeStub:
		@staticmethod
		def new_doc(doctype: str) -> FrappeBom:
			assert doctype == "BOM"
			return FrappeBom()

		@staticmethod
		def throw(message: str) -> None:
			raise ValueError(message)

	layout = Layout(
		name="002-R2",
		weight_per_sheet_kg=39.3,
		parts_per_sheet=77,
		finished_part_code="FG01SHR",
		net_weight_per_part_kg=0.289,
		gross_weight_per_part_kg=0.473846,
		scrap_weight_per_part_kg=0.184846,
		finished_parts=[],
		end_pieces=[
			EndPiece(
				weight_kg=2.81388,
				disposition="Reuse",
				used_for_finished_part="FG002SHR",
				width_mm=1250,
				length_mm=179,
			)
		],
	)
	layout.sheet_thickness_mm = 1.6

	def fake_ensure(_layout: object, row: object) -> str:
		item_code = "FG002SHR-EP-1.6x1250x179"
		row.end_piece_item_code = item_code
		return item_code

	monkeypatch.setattr(release_service, "frappe", FrappeStub)
	monkeypatch.setattr(release_service, "ensure_end_piece_item", fake_ensure)
	monkeypatch.setattr(release_service, "resolve_scrap_item_rate", lambda **_kwargs: 62.0)

	result = release_service.release_layout(
		layout,
		validators=[lambda _layout: None],
		release_context=release_service.ReleaseContext(layouts=(), boms=[]),
	)

	assert result.generated_boms[0].name == "BOM-FG01SHR-001"
	assert layout.end_pieces[0].end_piece_item_code == "FG002SHR-EP-1.6x1250x179"
	assert len(created_boms) == 1
	assert created_boms[0].scrap_items == [
		{
			"item_code": "PROCESSSCRAP001",
			"stock_qty": 14.233142,
			"qty": 14.233142,
			"uom": "Kg",
			"rate": 62.0,
		},
		{
			"item_code": "FG002SHR-EP-1.6x1250x179",
			"stock_qty": 2.81388,
			"qty": 2.81388,
			"uom": "Kg",
			"rate": 62.0,
		},
	]
	assert layout.finished_parts[0].scrap_weight_kg == 17.047022
	assert layout.finished_parts[0].raw_material_weight_kg == 39.3
```

- [ ] **Step 5: Run release service tests**

Run from `/root/workspace/bench15`:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
```

Expected:

```text
OK
```

- [ ] **Step 6: Commit release integration**

Run from `/root/workspace/sheet_cutting_layout`:

```bash
git add sheet_cutting_layout/services/release_service.py sheet_cutting_layout/tests/test_release_service.py
git commit -m "fix: create end-piece byproducts during release"
```

---

### Task 5: Validate Main BOM Weight Balance

**Files:**
- Modify: `sheet_cutting_layout/services/validators.py`
- Modify: `sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Add the validator call**

In `validate_sheet_cutting_layout()`, insert this line after `_validate_complete_sheet_consumption(layout, end_pieces)`:

```python
_validate_expected_main_bom_weight_balance(layout)
```

- [ ] **Step 2: Add the balance validator**

Add this function near `_validate_complete_sheet_consumption()`:

```python
def _validate_expected_main_bom_weight_balance(layout: SheetCuttingLayoutDocument) -> None:
	balance = expected_main_bom_weight_balance(layout)  # type: ignore[arg-type]
	difference = _sheet_consumption_flt(balance.difference_kg)
	if abs(difference) <= SHEET_CONSUMPTION_TOLERANCE_KG:
		return
	frappe.throw(
		_(
			"Main BOM weight mismatch: raw material {0} kg, finished parts {1} kg, "
			"scrap/byproduct {2} kg, difference {3} kg"
		).format(
			_format_sheet_consumption_weight(balance.raw_material_weight_kg),
			_format_sheet_consumption_weight(balance.finished_part_weight_kg),
			_format_sheet_consumption_weight(balance.scrap_and_byproduct_weight_kg),
			_format_sheet_consumption_weight(abs(difference)),
		)
	)
```

- [ ] **Step 3: Add a missing byproduct audit test**

Add this test after `test_save_time_audit_rejects_generated_bom_quantity_drift()`:

```python
def test_save_time_audit_rejects_missing_reuse_end_piece_byproduct_row(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import validators

	class FrappeStub:
		ValidationError = ValueError

		@staticmethod
		def get_system_settings(_fieldname: str) -> None:
			return None

		@staticmethod
		def get_doc(doctype: str, name: str) -> object:
			assert (doctype, name) == ("BOM", "BOM-FG01SHR")
			return type(
				"Bom",
				(),
				{
					"item": "FG01SHR",
					"quantity": 77,
					"items": [type("BomItem", (), {"item_code": "RMSHEET001", "qty": 39.3})()],
					"scrap_items": [
						type(
							"ScrapItem",
							(),
							{"item_code": "PROCESSSCRAP001", "stock_qty": 14.233142, "qty": 14.233142},
						)(),
					],
				},
			)()

		@staticmethod
		def throw(message: str) -> None:
			raise ValueError(message)

	layout = type(
		"AuditLayout",
		(),
		{
			"finished_part_code": "FG01SHR",
			"net_weight_per_part_kg": 0.289,
			"generated_bom": "BOM-FG01SHR",
			"end_pieces": [
				type(
					"EndPieceRow",
					(),
					{
						"idx": 1,
						"end_piece_item_code": None,
						"weight_kg": 2.81388,
						"qty_per_sheet": 1,
						"width_mm": 1250,
						"length_mm": 179,
						"disposition": "Reuse",
						"scrap_item": None,
						"used_for_finished_part": "FG002SHR",
						"bom_quantity": 1,
						"net_weight_per_part_kg": 2.81388,
						"gross_weight_per_part_kg": 2.81388,
						"scrap_weight_per_part_kg": 0,
						"bom_scrap_quantity_kg": 0,
					},
				)()
			],
			"raw_material_item": "RMSHEET001",
			"process_scrap_item": "PROCESSSCRAP001",
			"end_piece_bom_status": "",
			"sheet_thickness_mm": 1.6,
			"sheet_width_mm": None,
			"sheet_length_mm": None,
			"weight_per_sheet_kg": 39.3,
			"strip_thickness_mm": None,
			"strip_width_mm": None,
			"strip_length_mm": None,
			"weight_of_strip_kg": None,
			"gross_weight_per_part_kg": 0.473846,
			"scrap_weight_per_part_kg": 0.184846,
			"parts_per_strip": 7,
			"no_of_strips": 11,
			"parts_per_sheet": 77,
			"consumed_weight_kg": None,
			"leftover_weight_kg": None,
			"consumption_status": None,
		},
	)()
	monkeypatch.setattr(validators, "frappe", FrappeStub)
	monkeypatch.setattr(validators, "_", lambda message: message)

	with raises(ValueError, match="BOM scrap item mismatch"):
		validators.validate_sheet_cutting_layout(layout)
```

- [ ] **Step 4: Add an expected-balance mismatch test**

Add this test near the audit tests:

```python
def test_validator_rejects_expected_main_bom_weight_shortfall(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import validators

	class FrappeStub:
		ValidationError = ValueError

		@staticmethod
		def get_system_settings(_fieldname: str) -> None:
			return None

		@staticmethod
		def throw(message: str) -> None:
			raise ValueError(message)

	layout = Layout(
		weight_per_sheet_kg=39.3,
		parts_per_sheet=77,
		finished_part_code="FG01SHR",
		net_weight_per_part_kg=0.289,
		gross_weight_per_part_kg=0.437558,
		scrap_weight_per_part_kg=0.148558,
		finished_parts=[],
		end_pieces=[],
	)
	layout.sheet_thickness_mm = 1.6
	monkeypatch.setattr(validators, "frappe", FrappeStub)
	monkeypatch.setattr(validators, "_", lambda message: message)

	with raises(ValueError, match="Main BOM weight mismatch"):
		validators._validate_expected_main_bom_weight_balance(layout)
```

- [ ] **Step 5: Run release tests**

Run from `/root/workspace/bench15`:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
```

Expected:

```text
OK
```

- [ ] **Step 6: Commit validation**

Run from `/root/workspace/sheet_cutting_layout`:

```bash
git add sheet_cutting_layout/services/validators.py sheet_cutting_layout/tests/test_release_service.py
git commit -m "fix: validate main bom weight balance"
```

---

### Task 6: Verify Full Behavior

**Files:**
- No source files are created in this task.

- [ ] **Step 1: Run focused service tests**

Run from `/root/workspace/bench15`:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
```

Expected:

```text
OK
```

- [ ] **Step 2: Run app suite**

Run from `/root/workspace/bench15`:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --skip-test-records
```

Expected:

```text
OK
```

If site fixtures fail before reaching app tests, record the exact traceback and keep the three
focused module runs as the verified signal.

- [ ] **Step 3: Run diff hygiene checks**

Run from `/root/workspace/sheet_cutting_layout`:

```bash
git diff --check
git status --short
```

Expected:

```text
```

`git diff --check` should print nothing. `git status --short` should print nothing after the task
commits are complete.
