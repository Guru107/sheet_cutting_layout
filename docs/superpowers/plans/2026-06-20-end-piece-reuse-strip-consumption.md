# End Piece Reuse Strip Consumption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track consumed strip weight separately from total end-piece weight for reuse rows, and make layout consumption, BOMs, and Excel export use that strip basis.

**Architecture:** Keep `weight_kg` as total end-piece weight. Add reuse-only strip dimensions plus derived `strip_weight_kg`; route all reuse consumption through a small helper so validators and BOM code agree. Scrap rows continue using full `weight_kg`.

**Tech Stack:** Frappe DocType JSON, Python services, Frappe test runner, existing Excel export service.

---

## File Map

- Modify `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`: add strip fields to the child table.
- Modify `sheet_cutting_layout/services/validators.py`: default/validate strip dimensions, derive `strip_weight_kg`, and use consumed weight by disposition.
- Modify `sheet_cutting_layout/services/bom_service.py`: use strip weight for reuse byproduct quantities in generated main BOMs.
- Modify `sheet_cutting_layout/services/end_piece_bom_service.py`: use strip weight as raw-material quantity for generated reuse BOMs.
- Modify `sheet_cutting_layout/services/export_service.py`: write strip dimensions into the end-piece detail Strip Size cells.
- Modify tests in `sheet_cutting_layout/tests/test_validators.py`, `sheet_cutting_layout/tests/test_release_service.py`, `sheet_cutting_layout/tests/test_end_piece_bom_service.py`, and `sheet_cutting_layout/tests/test_export_service.py`.

---

### Task 1: Add Layout End Piece Strip Fields

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`
- Test: `sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Write the failing metadata test**

Add this assertion block to the existing DocType metadata tests in `sheet_cutting_layout/tests/test_release_service.py`:

```python
def test_layout_end_piece_has_reuse_strip_fields(self) -> None:
	doctype_path = (
		Path(__file__).resolve().parents[1]
		/ "sheet_cutting_layout"
		/ "doctype"
		/ "layout_end_piece"
		/ "layout_end_piece.json"
	)
	doctype = json.loads(doctype_path.read_text(encoding="utf-8"))
	fields = {field["fieldname"]: field for field in doctype["fields"]}

	assert doctype["field_order"].index("strip_width_mm") > doctype["field_order"].index("length_mm")
	assert doctype["field_order"].index("strip_weight_kg") < doctype["field_order"].index("weight_kg")
	assert fields["strip_width_mm"]["fieldtype"] == "Float"
	assert fields["strip_width_mm"]["depends_on"] == 'eval:doc.disposition=="Reuse"'
	assert fields["strip_length_mm"]["fieldtype"] == "Float"
	assert fields["strip_length_mm"]["depends_on"] == 'eval:doc.disposition=="Reuse"'
	assert fields["strip_weight_kg"]["fieldtype"] == "Float"
	assert fields["strip_weight_kg"]["read_only"] == 1
	assert fields["strip_weight_kg"]["depends_on"] == 'eval:doc.disposition=="Reuse"'
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
```

Expected: FAIL with missing `strip_width_mm`.

- [ ] **Step 3: Add fields to DocType JSON**

Update `field_order` so the block is:

```json
  "width_mm",
  "length_mm",
  "strip_width_mm",
  "strip_length_mm",
  "strip_weight_kg",
  "weight_kg",
```

Add these field objects before `weight_kg`:

```json
  {
   "depends_on": "eval:doc.disposition==\"Reuse\"",
   "fieldname": "strip_width_mm",
   "fieldtype": "Float",
   "label": "Strip Width Mm"
  },
  {
   "depends_on": "eval:doc.disposition==\"Reuse\"",
   "fieldname": "strip_length_mm",
   "fieldtype": "Float",
   "label": "Strip Length Mm"
  },
  {
   "depends_on": "eval:doc.disposition==\"Reuse\"",
   "fieldname": "strip_weight_kg",
   "fieldtype": "Float",
   "label": "Strip Weight Kg",
   "read_only": 1
  },
```

- [ ] **Step 4: Run test to verify it passes**

Run the same `test_release_service` command.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json sheet_cutting_layout/tests/test_release_service.py
git commit -m "feat: add reuse strip fields"
```

---

### Task 2: Derive Reuse Strip Weight and Consumption

**Files:**
- Modify: `sheet_cutting_layout/services/validators.py`
- Test: `sheet_cutting_layout/tests/test_validators.py`

- [ ] **Step 1: Write failing validator tests**

Add tests that build simple namespace rows and call existing validator functions:

```python
def test_reuse_strip_fields_default_and_drive_weight(self) -> None:
	layout = SimpleNamespace(sheet_thickness_mm=2.0)
	row = SimpleNamespace(
		disposition="Reuse",
		width_mm=200.0,
		length_mm=300.0,
		strip_width_mm=None,
		strip_length_mm=None,
		strip_weight_kg=None,
	)

	validators.apply_end_piece_strip_weight_formulas(layout, [row])

	assert row.strip_width_mm == 200.0
	assert row.strip_length_mm == 300.0
	assert row.strip_weight_kg == 0.9432


def test_reuse_strip_dimensions_cannot_exceed_end_piece_dimensions(self) -> None:
	layout = SimpleNamespace(sheet_thickness_mm=2.0)
	row = SimpleNamespace(
		disposition="Reuse",
		width_mm=200.0,
		length_mm=300.0,
		strip_width_mm=201.0,
		strip_length_mm=300.0,
		strip_weight_kg=None,
	)

	with self.assertRaises(frappe.ValidationError):
		validators.apply_end_piece_strip_weight_formulas(layout, [row])


def test_consumed_weight_uses_strip_for_reuse_and_total_weight_for_scrap(self) -> None:
	layout = SimpleNamespace(
		finished_part_code="FG01SHR",
		gross_weight_per_part_kg=1.0,
		parts_per_sheet=2,
	)
	rows = [
		SimpleNamespace(disposition="Reuse", weight_kg=10.0, strip_weight_kg=6.0),
		SimpleNamespace(disposition="Scrap", weight_kg=4.0, strip_weight_kg=1.0),
	]

	assert validators.calculate_consumed_weight_kg(layout, rows) == 12.0
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
```

Expected: FAIL because `apply_end_piece_strip_weight_formulas` does not exist.

- [ ] **Step 3: Implement minimal validator changes**

In `validators.EndPieceRow`, add:

```python
	strip_width_mm: float | None
	strip_length_mm: float | None
	strip_weight_kg: float | None
```

Call the new formula before reuse weight formulas:

```python
	apply_end_piece_weight_formulas(layout, end_pieces)
	apply_end_piece_strip_weight_formulas(layout, end_pieces)
	apply_end_piece_reuse_weight_formulas(end_pieces)
```

Add these helpers:

```python
def apply_end_piece_strip_weight_formulas(
	layout: SheetCuttingLayoutDocument,
	end_pieces: Sequence[EndPieceRow],
) -> None:
	for end_piece in end_pieces:
		if not _is_reuse_end_piece(end_piece):
			continue
		if getattr(end_piece, "strip_width_mm", None) is None:
			end_piece.strip_width_mm = getattr(end_piece, "width_mm", None)
		if getattr(end_piece, "strip_length_mm", None) is None:
			end_piece.strip_length_mm = getattr(end_piece, "length_mm", None)
		_validate_reuse_strip_dimensions(end_piece)
		weight = calculate_sheet_weight_kg(
			thickness_mm=getattr(layout, "sheet_thickness_mm", None),
			width_mm=getattr(end_piece, "strip_width_mm", None),
			length_mm=getattr(end_piece, "strip_length_mm", None),
		)
		if weight is not None:
			end_piece.strip_weight_kg = _flt(weight)


def _validate_reuse_strip_dimensions(end_piece: EndPieceRow) -> None:
	if getattr(end_piece, "strip_width_mm", None) is None:
		frappe.throw(_("Strip width is required for reuse end pieces"))
	if getattr(end_piece, "strip_length_mm", None) is None:
		frappe.throw(_("Strip length is required for reuse end pieces"))
	if _flt(getattr(end_piece, "strip_width_mm", 0)) <= 0:
		frappe.throw(_("Strip width must be greater than zero for reuse end pieces"))
	if _flt(getattr(end_piece, "strip_length_mm", 0)) <= 0:
		frappe.throw(_("Strip length must be greater than zero for reuse end pieces"))
	if _flt(getattr(end_piece, "strip_width_mm", 0)) > _flt(getattr(end_piece, "width_mm", 0)):
		frappe.throw(_("Strip width cannot be greater than end piece width"))
	if _flt(getattr(end_piece, "strip_length_mm", 0)) > _flt(getattr(end_piece, "length_mm", 0)):
		frappe.throw(_("Strip length cannot be greater than end piece length"))


def _end_piece_consumed_weight_kg(end_piece: EndPieceRow) -> float:
	if _is_reuse_end_piece(end_piece):
		return _flt(getattr(end_piece, "strip_weight_kg", 0))
	return _flt(getattr(end_piece, "weight_kg", 0))
```

Change reuse gross calculation:

```python
		weight = getattr(end_piece, "strip_weight_kg", None)
```

Change `calculate_consumed_weight_kg`:

```python
	end_piece_weight = sum(_end_piece_consumed_weight_kg(end_piece) for end_piece in end_pieces)
```

Change `_validate_end_piece_distribution`:

```python
	end_piece_weight_per_part = sum(
		_end_piece_consumed_weight_kg(end_piece) / parts_per_sheet for end_piece in end_pieces
	)
```

- [ ] **Step 4: Run test to verify it passes**

Run the same `test_validators` command.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sheet_cutting_layout/services/validators.py sheet_cutting_layout/tests/test_validators.py
git commit -m "feat: derive reuse strip consumption"
```

---

### Task 3: Use Strip Weight in BOM Services

**Files:**
- Modify: `sheet_cutting_layout/services/bom_service.py`
- Modify: `sheet_cutting_layout/services/end_piece_bom_service.py`
- Test: `sheet_cutting_layout/tests/test_release_service.py`
- Test: `sheet_cutting_layout/tests/test_end_piece_bom_service.py`

- [ ] **Step 1: Write failing BOM tests**

Add a main BOM assertion near existing end-piece byproduct tests:

```python
def test_reuse_end_piece_byproduct_uses_strip_weight(self) -> None:
	from sheet_cutting_layout.services.bom_service import build_bom_from_layout_row, parent_finished_part_row

	layout = SimpleNamespace(
		raw_material_item="RM-001",
		process_scrap_item="SCRAP-001",
		weight_per_sheet_kg=10.0,
		no_of_strips=1,
		finished_part_code="FG01SHR",
		is_lh_rh=0,
		orientation=None,
		twin_finished_part=None,
		parts_per_sheet=1,
		gross_weight_per_part_kg=2.0,
		scrap_weight_per_part_kg=0.0,
		sheet_thickness_mm=2.0,
		end_pieces=[
			SimpleNamespace(
				disposition="Reuse",
				weight_kg=5.0,
				strip_weight_kg=3.0,
				end_piece_item_code="EP-001",
				used_for_finished_part="FG02SHR",
				width_mm=200.0,
				length_mm=300.0,
			)
		],
	)

	bom = build_bom_from_layout_row(layout, parent_finished_part_row(layout))

	assert bom.scrap_items[-1].qty == 3.0
```

Add an end-piece BOM generation test near existing raw-material quantity tests:

```python
def test_generated_end_piece_bom_uses_strip_weight_as_raw_material_qty(self) -> None:
	existing_code = "FG01SHR-EP-2x100x200"
	fake_frappe = self._install_fakes(existing_items={existing_code})
	layout = Layout(end_pieces=[EndPiece(strip_weight_kg=1.75, weight_kg=2.5)])

	result = self.service.generate_end_piece_boms(layout)
	bom = self._created_doc(fake_frappe, "BOM")

	assert result["boms"]
	assert bom.items[0]["qty"] == 1.75
```

Also add this field to the `EndPiece` dataclass in `test_end_piece_bom_service.py`:

```python
	strip_weight_kg: float | None = 2.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
```

Expected: FAIL because both services still use `weight_kg`.

- [ ] **Step 3: Update BOM services**

In `bom_service.EndPieceRow`, add:

```python
	strip_weight_kg: float | None
```

Add helper:

```python
def _end_piece_bom_qty_kg(end_piece: EndPieceRow) -> float:
	if _is_reuse_end_piece(end_piece):
		return float(getattr(end_piece, "strip_weight_kg", 0) or 0)
	return float(getattr(end_piece, "weight_kg", 0) or 0)
```

Change reuse byproduct qty:

```python
					qty=_end_piece_bom_qty_kg(end_piece),
```

Change `_sheet_weight_kg` fallback:

```python
	end_piece_weight = sum(_end_piece_bom_qty_kg(end_piece) for end_piece in layout_doc.end_pieces)
```

In `end_piece_bom_service.EndPieceRow`, add:

```python
	strip_weight_kg: float | None
```

Change `_validate_pending_row`:

```python
		if getattr(row, "strip_weight_kg", None) is None or row.strip_weight_kg <= 0:
			_throw(_("Row {0}: Strip weight must be greater than zero").format(row_idx))
```

Change `_create_end_piece_bom`:

```python
		raw_material_qty_kg=float(getattr(row, "strip_weight_kg", 0) or 0),
```

- [ ] **Step 4: Run tests to verify they pass**

Run both test commands from Step 2.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sheet_cutting_layout/services/bom_service.py sheet_cutting_layout/services/end_piece_bom_service.py sheet_cutting_layout/tests/test_release_service.py sheet_cutting_layout/tests/test_end_piece_bom_service.py
git commit -m "feat: use strip weight in bom consumption"
```

---

### Task 4: Export Strip Size from Strip Fields

**Files:**
- Modify: `sheet_cutting_layout/services/export_service.py`
- Test: `sheet_cutting_layout/tests/test_export_service.py`

- [ ] **Step 1: Write failing export test**

Update `test_first_three_end_pieces_render_in_bom_and_detail_blocks` so each reuse row includes strip dimensions:

```python
"strip_width_mm": 100 + index,
"strip_length_mm": 150 + index,
```

Change the first block Strip Size assertions:

```python
self.assertEqual(cells["K25"], 2.0)
self.assertEqual(cells["L25"], 100)
self.assertEqual(cells["M25"], 150)
```

Keep size/detail assertions such as `L18 == 200` and `M18 == 300`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service
```

Expected: FAIL because export still writes `width_mm` and `length_mm` to Strip Size.

- [ ] **Step 3: Update export mapping**

Change `_end_piece_detail_cells`:

```python
		cells[strip_width] = _num(end_piece.get("strip_width_mm") or end_piece.get("width_mm"))
		cells[strip_length] = _num(end_piece.get("strip_length_mm") or end_piece.get("length_mm"))
```

- [ ] **Step 4: Run test to verify it passes**

Run the same `test_export_service` command.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sheet_cutting_layout/services/export_service.py sheet_cutting_layout/tests/test_export_service.py
git commit -m "feat: export reuse strip size"
```

---

### Task 5: Migrate and Run Final Checks

**Files:**
- Verify all changed files from Tasks 1-4.

- [ ] **Step 1: Apply DocType schema to bench15**

Run:

```bash
bench --site development.localhost migrate
```

Expected: migration completes and updates `Layout End Piece`.

- [ ] **Step 2: Run focused test modules**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_export_service
```

Expected: all PASS.

- [ ] **Step 3: Run repository hooks**

Run:

```bash
pre-commit run --all-files
```

Expected: all hooks PASS.

- [ ] **Step 4: Commit any verification-only fixes**

If Step 1-3 required formatting or small test corrections, commit them:

```bash
git add sheet_cutting_layout docs
git commit -m "fix: align strip consumption checks"
```

If no files changed, skip this commit.

---

## Self-Review

- Spec coverage: fields, defaulting, validation, strip weight derivation, consumption tracking, BOM behavior, Excel export, and focused tests are covered.
- Placeholder scan: no open placeholders remain.
- Type consistency: field names are `strip_width_mm`, `strip_length_mm`, and `strip_weight_kg` across DocType, validators, BOM services, export, and tests.
