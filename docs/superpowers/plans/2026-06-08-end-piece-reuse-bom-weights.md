# End Piece Reuse BOM Weights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reuse end-piece net/gross/scrap weight fields and generate reuse end-piece BOMs from the same raw/net/scrap calculation structure used by main BOMs.

**Architecture:** Keep row-level formulas in `validators.py` as the server source of truth, mirror them in `sheet_cutting_layout.js` for immediate feedback, and move shared BOM weight-row construction into `bom_service.py`. End-piece BOM generation keeps its existing item-creation and persistence flow, but reads shared computed BOM rows and row-level scrap item.

**Tech Stack:** Frappe DocType JSON, Frappe client script, Python services, bench-native unittest suite.

---

## File Structure

- Modify `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`
  - Add reuse weight fields.
  - Make `bom_scrap_quantity_kg` read-only.
  - Show `scrap_item` for both `Reuse` and `Scrap`.
- Modify `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`
  - Mirror server formulas for immediate row feedback.
  - Clear stale fields when disposition changes.
- Modify `sheet_cutting_layout/services/validators.py`
  - Add server-side reuse end-piece formula derivation.
  - Add validation for net weight and row-level scrap item.
- Modify `sheet_cutting_layout/services/bom_service.py`
  - Add shared `build_weight_split_bom_rows()` helper.
  - Update main BOM creation to use the shared helper.
- Modify `sheet_cutting_layout/services/end_piece_bom_service.py`
  - Use derived row fields and row-level `scrap_item`.
  - Use shared BOM row construction.
- Modify tests:
  - `sheet_cutting_layout/tests/test_validators.py`
  - `sheet_cutting_layout/tests/test_bom_service.py`
  - `sheet_cutting_layout/tests/test_end_piece_bom_service.py`
  - `sheet_cutting_layout/tests/test_release_service.py`
- Run bench commands from bench roots:
  - `/root/workspace/bench15`
  - `/root/workspace/bench16`

---

### Task 1: DocType Metadata And Client Formulas

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`
- Test: `sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Write failing metadata test**

Add this test near the existing DocType JSON contract tests in `sheet_cutting_layout/tests/test_release_service.py`:

```python
def test_reuse_end_piece_weight_fields_are_configured() -> None:
	end_piece_path = (
		Path(__file__).resolve().parents[1]
		/ "sheet_cutting_layout"
		/ "doctype"
		/ "layout_end_piece"
		/ "layout_end_piece.json"
	)
	doctype = json.loads(end_piece_path.read_text(encoding="utf-8"))
	fields = {row["fieldname"]: row for row in doctype["fields"] if "fieldname" in row}

	assert "net_weight_per_part_kg" in doctype["field_order"]
	assert "gross_weight_per_part_kg" in doctype["field_order"]
	assert "scrap_weight_per_part_kg" in doctype["field_order"]
	assert doctype["field_order"].index("net_weight_per_part_kg") > doctype["field_order"].index(
		"bom_quantity"
	)
	assert fields["net_weight_per_part_kg"]["depends_on"] == 'eval:doc.disposition=="Reuse"'
	assert fields["gross_weight_per_part_kg"]["read_only"] == 1
	assert fields["scrap_weight_per_part_kg"]["read_only"] == 1
	assert fields["bom_scrap_quantity_kg"]["read_only"] == 1
	assert fields["scrap_item"]["depends_on"] == 'eval:["Reuse","Scrap"].includes(doc.disposition)'
```

- [ ] **Step 2: Run test to verify it fails**

Run from `/root/workspace/bench15`:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service --case TestReleaseService
```

Expected: FAIL because `net_weight_per_part_kg`, `gross_weight_per_part_kg`, and `scrap_weight_per_part_kg` do not exist on `Layout End Piece`.

- [ ] **Step 3: Update DocType JSON**

In `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`, update `field_order` to:

```json
[
 "end_piece_item_code",
 "width_mm",
 "length_mm",
 "weight_kg",
 "qty_per_sheet",
 "disposition",
 "scrap_item",
 "used_for_finished_part",
 "bom_quantity",
 "net_weight_per_part_kg",
 "gross_weight_per_part_kg",
 "scrap_weight_per_part_kg",
 "bom_scrap_quantity_kg"
]
```

Change `scrap_item` to:

```json
{
 "depends_on": "eval:[\"Reuse\",\"Scrap\"].includes(doc.disposition)",
 "fieldname": "scrap_item",
 "fieldtype": "Link",
 "label": "Scrap Item",
 "options": "Item"
}
```

Add these fields between `bom_quantity` and `bom_scrap_quantity_kg`:

```json
{
 "depends_on": "eval:doc.disposition==\"Reuse\"",
 "fieldname": "net_weight_per_part_kg",
 "fieldtype": "Float",
 "label": "Net Weight Per Part Kg"
},
{
 "depends_on": "eval:doc.disposition==\"Reuse\"",
 "fieldname": "gross_weight_per_part_kg",
 "fieldtype": "Float",
 "label": "Gross Weight Per Part Kg",
 "read_only": 1
},
{
 "depends_on": "eval:doc.disposition==\"Reuse\"",
 "fieldname": "scrap_weight_per_part_kg",
 "fieldtype": "Float",
 "label": "Scrap Weight Per Part Kg",
 "read_only": 1
}
```

Change `bom_scrap_quantity_kg` to:

```json
{
 "depends_on": "eval:doc.disposition==\"Reuse\"",
 "fieldname": "bom_scrap_quantity_kg",
 "fieldtype": "Float",
 "label": "BOM Scrap Quantity Kg",
 "read_only": 1
}
```

- [ ] **Step 4: Add client-side reuse row formulas**

In `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`, add these helpers after `calculateEndPieceWeight(frm, row)`:

```javascript
	function calculateEndPieceGrossWeightPerPart(row) {
		const weight = Number(row.weight_kg);
		const bomQuantity = Number(row.bom_quantity);
		if (!(weight >= 0 && bomQuantity > 0)) {
			return null;
		}

		return Number((weight / bomQuantity).toFixed(getCalculationPrecision()));
	}

	function calculateEndPieceScrapWeightPerPart(row) {
		const grossWeight = Number(row.gross_weight_per_part_kg);
		const netWeight = Number(row.net_weight_per_part_kg);
		if (!(grossWeight >= 0) || !Number.isFinite(netWeight)) {
			return null;
		}

		return Number((grossWeight - netWeight).toFixed(getCalculationPrecision()));
	}

	function calculateEndPieceBomScrapQuantity(row) {
		const scrapWeight = Number(row.scrap_weight_per_part_kg);
		const bomQuantity = Number(row.bom_quantity);
		if (!(scrapWeight >= 0 && bomQuantity > 0)) {
			return null;
		}

		return Number((scrapWeight * bomQuantity).toFixed(getCalculationPrecision()));
	}
```

Add this helper after `updateEndPieceWeights(frm)`:

```javascript
	function updateEndPieceReuseWeights(frm) {
		const updates = (frm.doc.end_pieces || []).flatMap((row) => {
			if (row.disposition !== "Reuse") {
				return [];
			}

			const rowUpdates = [];
			const grossWeight = calculateEndPieceGrossWeightPerPart(row);
			if (grossWeight !== null && row.gross_weight_per_part_kg !== grossWeight) {
				rowUpdates.push(
					frappe.model.set_value(
						row.doctype,
						row.name,
						"gross_weight_per_part_kg",
						grossWeight
					)
				);
			}

			const scrapWeight = calculateEndPieceScrapWeightPerPart({
				...row,
				gross_weight_per_part_kg:
					grossWeight === null ? row.gross_weight_per_part_kg : grossWeight,
			});
			if (scrapWeight !== null && row.scrap_weight_per_part_kg !== scrapWeight) {
				rowUpdates.push(
					frappe.model.set_value(
						row.doctype,
						row.name,
						"scrap_weight_per_part_kg",
						scrapWeight
					)
				);
			}

			const bomScrapQuantity = calculateEndPieceBomScrapQuantity({
				...row,
				scrap_weight_per_part_kg:
					scrapWeight === null ? row.scrap_weight_per_part_kg : scrapWeight,
			});
			if (bomScrapQuantity !== null && row.bom_scrap_quantity_kg !== bomScrapQuantity) {
				rowUpdates.push(
					frappe.model.set_value(
						row.doctype,
						row.name,
						"bom_scrap_quantity_kg",
						bomScrapQuantity
					)
				);
			}
			return rowUpdates;
		});

		return Promise.all(updates);
	}
```

Update `updateSheetWeightAndDerivedFields(frm)` and `updateEndPieceWeightsAndConsumption(frm)` so `updateEndPieceReuseWeights(frm)` runs after `updateEndPieceWeights(frm)` and before consumption tracking:

```javascript
	function updateSheetWeightAndDerivedFields(frm) {
		return updateSheetWeight(frm)
			.then(() => updateEndPieceWeights(frm))
			.then(() => updateEndPieceReuseWeights(frm))
			.then(() => updateConsumptionTracking(frm));
	}

	function updateEndPieceWeightsAndConsumption(frm) {
		return updateEndPieceWeights(frm)
			.then(() => updateEndPieceReuseWeights(frm))
			.then(() => updateConsumptionTracking(frm));
	}
```

Update `clearStaleEndPieceDispositionFields(cdt, cdn)`:

```javascript
		if (row.disposition === "Reuse") {
			return Promise.all(updates);
		}
```

and for `row.disposition === "Scrap"`, also clear:

```javascript
		if (hasValue(row.net_weight_per_part_kg)) {
			updates.push(frappe.model.set_value(cdt, cdn, "net_weight_per_part_kg", null));
		}
		if (hasValue(row.gross_weight_per_part_kg)) {
			updates.push(frappe.model.set_value(cdt, cdn, "gross_weight_per_part_kg", null));
		}
		if (hasValue(row.scrap_weight_per_part_kg)) {
			updates.push(frappe.model.set_value(cdt, cdn, "scrap_weight_per_part_kg", null));
		}
```

Add child field handlers:

```javascript
		bom_quantity: updateEndPieceWeightsAndConsumption,
		net_weight_per_part_kg: updateEndPieceWeightsAndConsumption,
```

- [ ] **Step 5: Run metadata test to verify it passes**

Run from `/root/workspace/bench15`:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service --case TestReleaseService
```

Expected: PASS.

- [ ] **Step 6: Commit metadata and client feedback**

```bash
git add sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js sheet_cutting_layout/tests/test_release_service.py
git commit -m "feat: add reuse end piece weight fields"
```

---

### Task 2: Server-Side Reuse Formulas And Validation

**Files:**
- Modify: `sheet_cutting_layout/services/validators.py`
- Test: `sheet_cutting_layout/tests/test_validators.py`

- [ ] **Step 1: Extend validator test dataclass**

In `sheet_cutting_layout/tests/test_validators.py`, extend `EndPiece`:

```python
@dataclass
class EndPiece:
	end_piece_item_code: str | None = None
	weight_kg: float | None = 2.5545
	qty_per_sheet: float | None = 1
	width_mm: float | None = 1250
	length_mm: float | None = 260
	disposition: str | None = "Reuse"
	used_for_finished_part: str | None = "FG01SHR"
	bom_quantity: float | None = 1
	net_weight_per_part_kg: float | None = 2.0
	gross_weight_per_part_kg: float | None = None
	scrap_weight_per_part_kg: float | None = None
	bom_scrap_quantity_kg: float | None = 0
	scrap_item: str | None = ""
```

- [ ] **Step 2: Write failing formula and validation tests**

Add these tests to `TestValidators`:

```python
	def test_reuse_end_piece_derives_weight_split_and_bom_scrap(self) -> None:
		end_piece = EndPiece(
			weight_kg=12.0,
			bom_quantity=3,
			net_weight_per_part_kg=3.25,
			scrap_item="EP-SCRAP",
		)
		layout = self._balanced_layout(
			finished_part=FinishedPart("AB12SHR", 2, 11.004, 0),
			end_piece=end_piece,
		)

		self.validators.apply_end_piece_reuse_weight_formulas(layout, layout.end_pieces)

		self.assertEqual(end_piece.gross_weight_per_part_kg, 4.0)
		self.assertEqual(end_piece.scrap_weight_per_part_kg, 0.75)
		self.assertEqual(end_piece.bom_scrap_quantity_kg, 2.25)

	def test_reuse_end_piece_requires_net_weight(self) -> None:
		layout = self._balanced_layout(end_piece=EndPiece(net_weight_per_part_kg=None))

		with self.assertRaisesRegex(ValidationError, "Net weight per part is required"):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_reuse_end_piece_rejects_net_weight_above_gross_weight(self) -> None:
		layout = self._balanced_layout(
			end_piece=EndPiece(
				weight_kg=10.0,
				bom_quantity=5,
				net_weight_per_part_kg=2.01,
			)
		)

		with self.assertRaisesRegex(ValidationError, "Scrap weight per part cannot be negative"):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_reuse_end_piece_requires_row_scrap_item_for_positive_derived_scrap(self) -> None:
		layout = self._balanced_layout(
			end_piece=EndPiece(
				weight_kg=12.0,
				bom_quantity=3,
				net_weight_per_part_kg=3.25,
				scrap_item="",
			)
		)

		with self.assertRaisesRegex(ValidationError, "Scrap item is required for reuse end pieces"):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_reuse_end_piece_rejects_scrap_item_matching_used_for_finished_part(self) -> None:
		layout = self._balanced_layout(
			end_piece=EndPiece(
				weight_kg=12.0,
				bom_quantity=3,
				net_weight_per_part_kg=3.25,
				scrap_item="FG01SHR",
			)
		)

		with self.assertRaisesRegex(ValidationError, "Scrap item cannot be the used-for finished part"):
			self.validators.validate_sheet_cutting_layout(layout)
```

- [ ] **Step 3: Run tests to verify they fail**

Run from `/root/workspace/bench15`:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators --case TestValidators
```

Expected: FAIL because `apply_end_piece_reuse_weight_formulas` does not exist and validation does not require reuse net weight.

- [ ] **Step 4: Implement server formulas**

In `sheet_cutting_layout/services/validators.py`, extend `EndPieceRow`:

```python
class EndPieceRow(Protocol):
	end_piece_item_code: str | None
	width_mm: float | None
	length_mm: float | None
	weight_kg: float | None
	qty_per_sheet: float | None
	disposition: str | None
	used_for_finished_part: str | None
	bom_quantity: float | None
	net_weight_per_part_kg: float | None
	gross_weight_per_part_kg: float | None
	scrap_weight_per_part_kg: float | None
	bom_scrap_quantity_kg: float | None
	scrap_item: str | None
```

Add this function after `apply_end_piece_weight_formulas()`:

```python
def apply_end_piece_reuse_weight_formulas(
	layout: SheetCuttingLayoutDocument,
	end_pieces: Sequence[EndPieceRow],
) -> None:
	_ = layout
	for end_piece in end_pieces:
		if not _is_reuse_end_piece(end_piece):
			continue
		weight = getattr(end_piece, "weight_kg", None)
		bom_quantity = getattr(end_piece, "bom_quantity", None)
		net_weight = getattr(end_piece, "net_weight_per_part_kg", None)
		if weight is None or bom_quantity is None or bom_quantity <= 0:
			continue
		gross_weight = _flt(_flt(weight) / _flt(bom_quantity))
		end_piece.gross_weight_per_part_kg = gross_weight
		if net_weight is None:
			continue
		scrap_weight = _flt(gross_weight - _flt(net_weight))
		end_piece.scrap_weight_per_part_kg = scrap_weight
		if scrap_weight >= 0:
			end_piece.bom_scrap_quantity_kg = _flt(scrap_weight * _flt(bom_quantity))
```

In `validate_sheet_cutting_layout()`, call it immediately after `apply_end_piece_weight_formulas(layout, end_pieces)`:

```python
	apply_end_piece_weight_formulas(layout, end_pieces)
	apply_end_piece_reuse_weight_formulas(layout, end_pieces)
```

- [ ] **Step 5: Implement validation rules**

Change the loop in `validate_sheet_cutting_layout()` from:

```python
	for end_piece in end_pieces:
		_validate_end_piece_item_code_is_locked(end_piece)
		_validate_end_piece_required_fields(end_piece)
```

to:

```python
	for end_piece in end_pieces:
		_validate_end_piece_item_code_is_locked(end_piece)
		_validate_end_piece_required_fields(layout, end_piece)
```

Change `_validate_end_piece_required_fields()` signature and reuse block:

```python
def _validate_end_piece_required_fields(
	layout: SheetCuttingLayoutDocument,
	end_piece: EndPieceRow,
) -> None:
	if end_piece.width_mm is None:
		frappe.throw(_("End piece width is required"))
	if end_piece.length_mm is None:
		frappe.throw(_("End piece length is required"))
	if end_piece.weight_kg is None:
		frappe.throw(_("End piece weight is required"))
	_validate_end_piece_disposition(end_piece)
	_validate_non_reuse_end_piece_fields_are_empty(end_piece)
	_validate_non_scrap_end_piece_fields_are_empty(end_piece)
	if _is_reuse_end_piece(end_piece):
		if _is_missing(getattr(end_piece, "used_for_finished_part", None)):
			frappe.throw(_("Used for finished part is required for reuse end pieces"))
		_validate_reuse_suffix(end_piece)
		if getattr(end_piece, "bom_quantity", None) is None or end_piece.bom_quantity <= 0:
			frappe.throw(_("BOM quantity must be greater than zero for reuse end pieces"))
		_validate_reuse_weight_split(layout, end_piece)
	if _is_scrap_end_piece(end_piece) and _is_missing(getattr(end_piece, "scrap_item", None)):
		frappe.throw(_("Scrap item is required for scrap end pieces"))
```

Add this helper near `_validate_reuse_suffix()`:

```python
def _validate_reuse_weight_split(
	layout: SheetCuttingLayoutDocument,
	end_piece: EndPieceRow,
) -> None:
	net_weight = getattr(end_piece, "net_weight_per_part_kg", None)
	if net_weight is None:
		frappe.throw(_("Net weight per part is required for reuse end pieces"))
	if net_weight < 0:
		frappe.throw(_("Net weight per part must be non-negative for reuse end pieces"))
	gross_weight = _flt(getattr(end_piece, "gross_weight_per_part_kg", 0))
	if gross_weight <= 0:
		frappe.throw(_("Gross weight per part must be greater than zero for reuse end pieces"))
	scrap_weight = _flt(getattr(end_piece, "scrap_weight_per_part_kg", 0))
	if scrap_weight < 0:
		frappe.throw(_("Scrap weight per part cannot be negative for reuse end pieces"))
	bom_scrap_quantity = _flt(getattr(end_piece, "bom_scrap_quantity_kg", 0))
	if bom_scrap_quantity < 0:
		frappe.throw(_("BOM scrap quantity must be non-negative for reuse end pieces"))
	if bom_scrap_quantity > 0:
		scrap_item = getattr(end_piece, "scrap_item", None)
		if _is_missing(scrap_item):
			frappe.throw(_("Scrap item is required for reuse end pieces when BOM scrap quantity is positive"))
		if _same_item_code(scrap_item, getattr(end_piece, "used_for_finished_part", None)):
			frappe.throw(_("Scrap item cannot be the used-for finished part"))
		_validate_scrap_item_is_not_generated_end_piece_item(layout, end_piece, scrap_item)
```

Add this helper after `_validate_reuse_weight_split()`:

```python
def _validate_scrap_item_is_not_generated_end_piece_item(
	layout: SheetCuttingLayoutDocument,
	end_piece: EndPieceRow,
	scrap_item: str | None,
) -> None:
	if _is_missing(scrap_item):
		return
	try:
		generated_item_code = derive_end_piece_item_code(
			used_for_finished_part=getattr(end_piece, "used_for_finished_part", None),
			thickness_mm=getattr(layout, "sheet_thickness_mm", None),
			width_mm=getattr(end_piece, "width_mm", None),
			length_mm=getattr(end_piece, "length_mm", None),
		)
	except ValueError:
		return
	if _same_item_code(scrap_item, generated_item_code):
		frappe.throw(_("Scrap item cannot be the generated end-piece item"))
```

Update `_validate_non_reuse_end_piece_fields_are_empty()` so non-reuse rows reject the new reuse-only fields:

```python
	if _has_non_zero_value(getattr(end_piece, "net_weight_per_part_kg", None)):
		frappe.throw(_("Net weight per part is only allowed for reuse end pieces"))
	if _has_non_zero_value(getattr(end_piece, "gross_weight_per_part_kg", None)):
		frappe.throw(_("Gross weight per part is only allowed for reuse end pieces"))
	if _has_non_zero_value(getattr(end_piece, "scrap_weight_per_part_kg", None)):
		frappe.throw(_("Scrap weight per part is only allowed for reuse end pieces"))
```

Remove `_requires_process_scrap_item_for_reuse_bom()` from `validate_sheet_cutting_layout()` because reuse scrap now uses row-level `scrap_item`.

- [ ] **Step 6: Run validator tests to verify they pass**

Run from `/root/workspace/bench15`:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators --case TestValidators
```

Expected: PASS.

- [ ] **Step 7: Commit server formulas and validation**

```bash
git add sheet_cutting_layout/services/validators.py sheet_cutting_layout/tests/test_validators.py
git commit -m "feat: derive reuse end piece weight split"
```

---

### Task 3: Shared Main BOM Weight Row Builder

**Files:**
- Modify: `sheet_cutting_layout/services/bom_service.py`
- Test: `sheet_cutting_layout/tests/test_bom_service.py`

- [ ] **Step 1: Write failing shared-helper test**

Add this test to `sheet_cutting_layout/tests/test_bom_service.py`:

```python
def test_weight_split_helper_matches_main_bom_raw_and_scrap_rows() -> None:
	from sheet_cutting_layout.services.bom_service import build_weight_split_bom_rows

	rows = build_weight_split_bom_rows(
		raw_material_item="RAW-001",
		gross_weight_per_part_kg=4.0,
		scrap_weight_per_part_kg=0.75,
		quantity=3,
		scrap_item="EP-SCRAP",
		scrap_row_type="process_scrap",
	)

	assert [(row.item_code, row.qty, row.row_type) for row in rows.items] == [
		("RAW-001", 12.0, "raw_material")
	]
	assert [(row.item_code, row.qty, row.row_type) for row in rows.scrap_items] == [
		("EP-SCRAP", 2.25, "process_scrap")
	]
```

- [ ] **Step 2: Run test to verify it fails**

Run from `/root/workspace/bench15`:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_service --case TestBomService
```

Expected: FAIL because `build_weight_split_bom_rows` does not exist.

- [ ] **Step 3: Add shared helper**

In `sheet_cutting_layout/services/bom_service.py`, add this dataclass after `BomItemRow`:

```python
@dataclass
class BomWeightRows:
	items: list[BomItemRow] = field(default_factory=list)
	scrap_items: list[BomItemRow] = field(default_factory=list)
```

Add this function before `build_bom_from_layout_row()`:

```python
def build_weight_split_bom_rows(
	*,
	raw_material_item: str,
	gross_weight_per_part_kg: float,
	scrap_weight_per_part_kg: float,
	quantity: float,
	scrap_item: str | None,
	scrap_row_type: BomItemRowType,
) -> BomWeightRows:
	rows = BomWeightRows(
		items=[
			BomItemRow(
				item_code=raw_material_item,
				qty=gross_weight_per_part_kg * quantity,
				row_type="raw_material",
			)
		]
	)
	scrap_qty = scrap_weight_per_part_kg * quantity
	if scrap_qty > 0:
		if not scrap_item:
			raise ValueError("Scrap item is required when scrap quantity is positive")
		rows.scrap_items.append(
			BomItemRow(
				item_code=scrap_item,
				qty=scrap_qty,
				row_type=scrap_row_type,
			)
		)
	return rows
```

- [ ] **Step 4: Update main BOM builder to use helper**

Replace the raw-material and process-scrap block in `build_bom_from_layout_row()` with:

```python
	weight_rows = build_weight_split_bom_rows(
		raw_material_item=layout_doc.raw_material_item,
		gross_weight_per_part_kg=finished_part_row.gross_weight_per_part_kg,
		scrap_weight_per_part_kg=finished_part_row.scrap_weight_per_part_kg,
		quantity=finished_part_row.parts_per_sheet,
		scrap_item=layout_doc.process_scrap_item,
		scrap_row_type="process_scrap",
	)
	bom.items.extend(weight_rows.items)
	bom.scrap_items.extend(weight_rows.scrap_items)
```

Keep the existing scrap-disposition end-piece loop unchanged.

- [ ] **Step 5: Run BOM service tests**

Run from `/root/workspace/bench15`:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_service --case TestBomService
```

Expected: PASS, including existing main BOM invariant tests.

- [ ] **Step 6: Commit shared helper**

```bash
git add sheet_cutting_layout/services/bom_service.py sheet_cutting_layout/tests/test_bom_service.py
git commit -m "refactor: share bom weight split rows"
```

---

### Task 4: End-Piece BOM Generation Uses Derived Rows

**Files:**
- Modify: `sheet_cutting_layout/services/end_piece_bom_service.py`
- Test: `sheet_cutting_layout/tests/test_end_piece_bom_service.py`

- [ ] **Step 1: Extend end-piece BOM test dataclass**

In `sheet_cutting_layout/tests/test_end_piece_bom_service.py`, extend `EndPiece`:

```python
@dataclass
class EndPiece:
	idx: int = 1
	disposition: str = "Reuse"
	end_piece_item_code: str | None = None
	width_mm: float | None = 100
	length_mm: float | None = 200
	weight_kg: float | None = 2.5
	used_for_finished_part: str | None = "FG01SHR"
	bom_quantity: float | None = 1
	net_weight_per_part_kg: float | None = 2.5
	gross_weight_per_part_kg: float | None = 2.5
	scrap_weight_per_part_kg: float | None = 0
	bom_scrap_quantity_kg: float | None = 0
	scrap_item: str | None = None
	db_set_calls: list[tuple[object, object, dict[str, object]]] = field(default_factory=list)
```

- [ ] **Step 2: Update existing positive-scrap tests to use row scrap item**

Where tests currently rely on `layout.process_scrap_item` for reuse BOM scrap, set row values like:

```python
EndPiece(
	weight_kg=12.0,
	bom_quantity=3,
	net_weight_per_part_kg=3.25,
	gross_weight_per_part_kg=4.0,
	scrap_weight_per_part_kg=0.75,
	bom_scrap_quantity_kg=2.25,
	scrap_item="EP-SCRAP",
)
```

Assert the generated BOM scrap row uses `"EP-SCRAP"`.

- [ ] **Step 3: Write failing row-level scrap item test**

Add this test to `TestEndPieceBomService`:

```python
	def test_generation_uses_row_scrap_item_for_reuse_bom_scrap(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		fake_frappe = self._install_fakes(existing_items={existing_code})
		layout = Layout(
			process_scrap_item=None,
			end_pieces=[
				EndPiece(
					weight_kg=12.0,
					bom_quantity=3,
					net_weight_per_part_kg=3.25,
					gross_weight_per_part_kg=4.0,
					scrap_weight_per_part_kg=0.75,
					bom_scrap_quantity_kg=2.25,
					scrap_item="EP-SCRAP",
				)
			],
		)

		with patch.object(self.service, "resolve_scrap_item_rate", return_value=33.5) as resolve_rate:
			result = self.service.generate_end_piece_boms(layout)

		self.assertEqual(result["items"], [existing_code])
		bom = fake_frappe.created_docs[0]
		self.assertEqual(bom.quantity, 3)
		self.assertEqual(bom.items, [{"item_code": existing_code, "qty": 12.0, "uom": "Kg"}])
		self.assertEqual(
			bom.scrap_items,
			[
				{
					"item_code": "EP-SCRAP",
					"qty": 2.25,
					"stock_qty": 2.25,
					"uom": "Kg",
					"rate": 33.5,
				}
			],
		)
		resolve_rate.assert_called_once_with(item_code="EP-SCRAP", company="Test Company")
```

- [ ] **Step 4: Run tests to verify failure**

Run from `/root/workspace/bench15`:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service --case TestEndPieceBomService
```

Expected: FAIL because `_create_end_piece_bom()` still reads `layout.process_scrap_item`.

- [ ] **Step 5: Update end-piece BOM service**

In `sheet_cutting_layout/services/end_piece_bom_service.py`, import the shared helper:

```python
from sheet_cutting_layout.services.bom_service import (
	build_weight_split_bom_rows,
	resolve_scrap_item_rate,
)
```

Update `EndPieceRow` protocol:

```python
class EndPieceRow(Protocol):
	idx: int
	disposition: str
	end_piece_item_code: str | None
	width_mm: float | None
	length_mm: float | None
	weight_kg: float | None
	used_for_finished_part: str | None
	bom_quantity: float | None
	net_weight_per_part_kg: float | None
	gross_weight_per_part_kg: float | None
	scrap_weight_per_part_kg: float | None
	bom_scrap_quantity_kg: float | None
	scrap_item: str | None
```

Replace `_create_end_piece_bom()` raw/scrap row logic with:

```python
	weight_rows = build_weight_split_bom_rows(
		raw_material_item=item_code,
		gross_weight_per_part_kg=float(getattr(row, "gross_weight_per_part_kg", 0) or 0),
		scrap_weight_per_part_kg=float(getattr(row, "scrap_weight_per_part_kg", 0) or 0),
		quantity=float(getattr(row, "bom_quantity", 0) or 0),
		scrap_item=_clean(getattr(row, "scrap_item", None)),
		scrap_row_type="process_scrap",
	)
	for item_row in weight_rows.items:
		bom.append("items", {"item_code": item_row.item_code, "qty": item_row.qty, "uom": item_row.uom})

	for scrap_row in weight_rows.scrap_items:
		try:
			rate = resolve_scrap_item_rate(item_code=scrap_row.item_code, company=bom.company)
		except ValueError as error:
			_throw(_("Row {0}: {1}").format(getattr(row, "idx", 0), str(error)))
		bom.append(
			"scrap_items",
			{
				"item_code": scrap_row.item_code,
				"qty": scrap_row.qty,
				"stock_qty": scrap_row.qty,
				"uom": scrap_row.uom,
				"rate": rate,
			},
		)
```

Update `_validate_pending_row()` so positive `bom_scrap_quantity_kg` requires row `scrap_item`:

```python
	if row.bom_scrap_quantity_kg > 0 and _is_missing(getattr(row, "scrap_item", None)):
		_throw(_("Row {0}: Scrap item is required when BOM scrap quantity is positive").format(row_idx))
```

- [ ] **Step 6: Run end-piece BOM service tests**

Run from `/root/workspace/bench15`:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service --case TestEndPieceBomService
```

Expected: PASS.

- [ ] **Step 7: Commit end-piece BOM generation**

```bash
git add sheet_cutting_layout/services/end_piece_bom_service.py sheet_cutting_layout/tests/test_end_piece_bom_service.py
git commit -m "feat: use row scrap item for end piece boms"
```

---

### Task 5: Migration And Full Verification

**Files:**
- Verify all files changed by Tasks 1-4.

- [ ] **Step 1: Run app tests on bench15**

Run from `/root/workspace/bench15`:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout
```

Expected: all tests pass.

- [ ] **Step 2: Run app tests on bench16**

Run from `/root/workspace/bench16`:

```bash
bench --site frappe16.localhost run-tests --app sheet_cutting_layout
```

Expected: all tests pass.

- [ ] **Step 3: Run DocType migrations**

Run from `/root/workspace/bench15`:

```bash
bench --site development.localhost migrate
```

Run from `/root/workspace/bench16`:

```bash
bench --site frappe16.localhost migrate
```

Expected: both migrations finish without errors.

- [ ] **Step 4: Run pre-commit**

Run from `/root/workspace/sheet_cutting_layout`:

```bash
PYTHONPATH=/tmp/precommit-runner PRE_COMMIT_HOME=/tmp/precommit-cache npm_config_cache=/tmp/npm-cache python -m pre_commit run --all-files
```

Expected: all hooks pass.

- [ ] **Step 5: Check final diff**

Run from `/root/workspace/sheet_cutting_layout`:

```bash
git status --short
git diff --check
git log --oneline -5
```

Expected: no unstaged changes except intentional work before the final commit; `git diff --check` prints nothing.

- [ ] **Step 6: Final commit if verification changed generated metadata**

If migration or formatting changed files after the task commits, commit only those intentional changes:

```bash
git add sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js sheet_cutting_layout/services/validators.py sheet_cutting_layout/services/bom_service.py sheet_cutting_layout/services/end_piece_bom_service.py sheet_cutting_layout/tests/test_validators.py sheet_cutting_layout/tests/test_bom_service.py sheet_cutting_layout/tests/test_end_piece_bom_service.py sheet_cutting_layout/tests/test_release_service.py
git commit -m "chore: finalize reuse end piece bom weights"
```

If `git status --short` is clean, skip this commit.

---

## Self-Review

- Spec coverage:
  - Row fields: Task 1.
  - Read-only `bom_scrap_quantity_kg`: Task 1.
  - Row-level reuse `scrap_item`: Tasks 1, 2, and 4.
  - Server formulas: Task 2.
  - Client feedback: Task 1.
  - Main BOM calculation reuse: Task 3 and Task 4.
  - Bench-native tests: Tasks 1-5.
- Placeholder scan: clear; all test commands use bench-native execution.
- Type consistency:
  - New fields use `net_weight_per_part_kg`, `gross_weight_per_part_kg`, `scrap_weight_per_part_kg`, and `bom_scrap_quantity_kg` consistently across DocType, validators, JS, and tests.
  - Shared helper returns existing `BomItemRow` values so main and end-piece BOM creation share the same weight-row shape.
