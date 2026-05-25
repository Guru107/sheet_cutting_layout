# End Piece BOM Generation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a post-release end-piece Item preview and BOM generation flow for reusable sheet cutting end pieces.

**Architecture:** Keep MR Release responsible for the shearing BOM only. Move end-piece reuse Item/BOM preview and generation into a focused service, expose it through whitelisted controller methods, and keep form scripting limited to UI calculation, preview dialog, and button wiring.

**Tech Stack:** Frappe/ERPNext 15 DocTypes, Python service modules, ERPNext BOM and Item documents, Frappe form JavaScript, pytest unit tests, bench tests.

---

## File Structure

Modify:

- `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`
  Owns child-row schema. Remove manual `end_piece_item`; add editable/generated Item and reuse BOM fields.

- `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json`
  Owns parent schema. Add read-only `end_piece_bom_status` near consumption/workflow status.

- `sheet_cutting_layout/services/validators.py`
  Owns layout calculations and validation. Update end-piece weight semantics, generated item code suggestion, conditional required fields, and parent end-piece BOM status calculation.

- `sheet_cutting_layout/services/bom_service.py`
  Owns pure shearing BOM construction. Update end-piece BOM mapping so scrap end pieces use row-level `scrap_item`, reusable end pieces do not become scrap rows, and end-piece weight is treated as per-sheet weight.

- `sheet_cutting_layout/services/release_service.py`
  Owns MR Release orchestration. Ensure release recalculates `end_piece_bom_status` but does not generate end-piece Items or reuse BOMs.

- `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`
  Owns DocType controller and whitelisted methods. Add preview and generation endpoints.

- `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`
  Owns form UX. Auto-suggest editable end-piece item codes, update per-sheet weights, show preview/generation buttons, and call server methods.

- `sheet_cutting_layout/services/canvas_payload.py` and `sheet_cutting_layout/public/js/sheet_layout_canvas.js`
  Own canvas payload/render semantics. Remove dependence on `end_piece_item`, carry `end_piece_item_code`, and treat `weight_kg` as per-sheet weight.

- Tests:
  - `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`
  - `sheet_cutting_layout/tests/test_validators.py`
  - `sheet_cutting_layout/tests/test_bom_service.py`
  - `sheet_cutting_layout/tests/test_release_service.py`
  - `sheet_cutting_layout/tests/test_property_layout_invariants.py`

Create:

- `sheet_cutting_layout/services/end_piece_bom_service.py`
  Pure-ish service for generated Item code suggestions, preview rows, Item creation/reuse, ERPNext BOM creation, and status calculation.

- `sheet_cutting_layout/tests/test_end_piece_bom_service.py`
  Unit tests for preview/generation behavior with fake Frappe.

---

## Chunk 1: Schema, Calculation, Validation, and Shearing BOM Semantics

### Task 1: Update DocType Schema Tests First

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`
- Later modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`
- Later modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json`

- [ ] **Step 1: Write the failing schema test updates**

In `test_sheet_cutting_layout_doctypes_define_normalized_model`, add `end_piece_bom_status` to the parent subset and assert its options/read-only state:

```python
assert {
    # existing fields...
    "end_piece_bom_status",
}.issubset(parent_fields)
assert parent_fields["end_piece_bom_status"]["fieldtype"] == "Select"
assert parent_fields["end_piece_bom_status"].get("read_only") == 1
assert parent_fields["end_piece_bom_status"].get("options") == "Not Required\nPending\nGenerated"
```

Replace the `Layout End Piece` expected fields set with:

```python
{
    "end_piece_item_code",
    "generated_end_piece_item",
    "width_mm",
    "length_mm",
    "weight_kg",
    "qty_per_sheet",
    "disposition",
    "scrap_item",
    "used_for_finished_part",
    "bom_quantity",
    "bom_scrap_quantity_kg",
    "generated_end_piece_bom",
}
```

Add these field assertions:

```python
assert "end_piece_item" not in end_piece_fields
assert end_piece_fields["end_piece_item_code"]["fieldtype"] == "Data"
assert end_piece_fields["end_piece_item_code"].get("in_list_view") == 1
assert end_piece_fields["generated_end_piece_item"]["fieldtype"] == "Link"
assert end_piece_fields["generated_end_piece_item"]["options"] == "Item"
assert end_piece_fields["generated_end_piece_item"].get("read_only") == 1
assert end_piece_fields["scrap_item"]["fieldtype"] == "Link"
assert end_piece_fields["scrap_item"]["options"] == "Item"
assert end_piece_fields["bom_quantity"]["fieldtype"] == "Float"
assert end_piece_fields["bom_scrap_quantity_kg"]["fieldtype"] == "Float"
assert end_piece_fields["generated_end_piece_bom"]["fieldtype"] == "Link"
assert end_piece_fields["generated_end_piece_bom"]["options"] == "BOM"
assert end_piece_fields["generated_end_piece_bom"].get("read_only") == 1
```

- [ ] **Step 2: Run schema test to verify it fails**

Run:

```bash
pytest -q sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py::test_sheet_cutting_layout_doctypes_define_normalized_model
```

Expected: FAIL because `end_piece_bom_status` and new end-piece fields do not exist and `end_piece_item` still exists.

- [ ] **Step 3: Update DocType JSON minimally**

In `layout_end_piece.json`:

- Remove `end_piece_item` from `field_order` and `fields`.
- Add fields in this order:

```json
"field_order": [
  "end_piece_item_code",
  "generated_end_piece_item",
  "width_mm",
  "length_mm",
  "weight_kg",
  "qty_per_sheet",
  "disposition",
  "scrap_item",
  "used_for_finished_part",
  "bom_quantity",
  "bom_scrap_quantity_kg",
  "generated_end_piece_bom"
]
```

Add field objects:

```json
{
  "fieldname": "end_piece_item_code",
  "fieldtype": "Data",
  "in_list_view": 1,
  "label": "End Piece Item Code"
},
{
  "fieldname": "generated_end_piece_item",
  "fieldtype": "Link",
  "label": "Generated End Piece Item",
  "options": "Item",
  "read_only": 1
},
{
  "fieldname": "scrap_item",
  "fieldtype": "Link",
  "label": "Scrap Item",
  "options": "Item"
},
{
  "fieldname": "bom_quantity",
  "fieldtype": "Float",
  "label": "BOM Quantity"
},
{
  "fieldname": "bom_scrap_quantity_kg",
  "fieldtype": "Float",
  "label": "BOM Scrap Quantity Kg"
},
{
  "fieldname": "generated_end_piece_bom",
  "fieldtype": "Link",
  "label": "Generated End Piece BOM",
  "options": "BOM",
  "read_only": 1
}
```

In `sheet_cutting_layout.json`:

- Add `"end_piece_bom_status"` after `"consumption_status"` in `field_order`.
- Add field:

```json
{
  "fieldname": "end_piece_bom_status",
  "fieldtype": "Select",
  "label": "End Piece BOM Status",
  "options": "Not Required\nPending\nGenerated",
  "read_only": 1
}
```

- [ ] **Step 4: Run schema test to verify it passes**

Run:

```bash
pytest -q sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py::test_sheet_cutting_layout_doctypes_define_normalized_model
```

Expected: PASS.

- [ ] **Step 5: Commit schema changes**

Run:

```bash
git add sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py
git commit -m "feat: add end piece bom tracking fields"
```

### Task 2: Update Validator Tests for Per-Sheet End-Piece Weight and Conditional Fields

**Files:**
- Modify: `sheet_cutting_layout/tests/test_validators.py`
- Later modify: `sheet_cutting_layout/services/validators.py`

- [ ] **Step 1: Update test dataclasses**

Replace the `EndPiece` dataclass with:

```python
@dataclass
class EndPiece:
    end_piece_item_code: str | None = "RM001-EP-1x1000x100"
    weight_kg: float | None = None
    qty_per_sheet: float | None = 1
    width_mm: float | None = 1000
    length_mm: float | None = 100
    disposition: str | None = "Reuse"
    used_for_finished_part: str | None = "FG01SHR"
    bom_quantity: float | None = 1
    bom_scrap_quantity_kg: float | None = 0
    generated_end_piece_item: str | None = None
    generated_end_piece_bom: str | None = None
    scrap_item: str | None = "ENDSCRAP001"

    def __post_init__(self) -> None:
        if self.weight_kg is not None and self.width_mm is None and self.length_mm is None:
            self.width_mm = 1000
            self.length_mm = self.weight_kg * 1_000_000 / (7.86 * self.width_mm)
```

Add `end_piece_bom_status: str = ""` to `Layout`.

- [ ] **Step 2: Write failing validator tests**

Add:

```python
def test_generated_end_piece_item_code_is_suggested_from_raw_material_and_dimensions(
    validators: types.ModuleType,
) -> None:
    assert (
        validators.suggest_end_piece_item_code(
            raw_material_item="RM001",
            thickness_mm=1.6,
            width_mm=1250,
            length_mm=179,
        )
        == "RM001-EP-1.6x1250x179"
    )


def test_end_piece_weight_is_per_sheet_and_multiplies_quantity(validators: types.ModuleType) -> None:
    layout = Layout(
        finished_parts=[FinishedPart("AB12SHR", 77, gross_weight_per_part_kg=0, net_weight_per_part_kg=0.289)],
        end_pieces=[EndPiece(weight_kg=999, qty_per_sheet=2, width_mm=1250, length_mm=179)],
        sheet_thickness_mm=1.6,
    )

    validators.apply_end_piece_weight_formulas(layout, layout.end_pieces)

    assert layout.end_pieces[0].weight_kg == 5.62776


def test_consumption_tracking_uses_end_piece_weight_directly(validators: types.ModuleType) -> None:
    consumed = validators.calculate_consumed_weight_kg(
        [FinishedPart("AB12SHR", 2, 10, 0)],
        [EndPiece(weight_kg=4, qty_per_sheet=3)],
    )

    assert consumed == 24


def test_end_piece_rows_do_not_require_manual_end_piece_item(validators: types.ModuleType) -> None:
    layout = Layout(
        finished_parts=[FinishedPart("AB12SHR", 2, 10, 0)],
        end_pieces=[EndPiece(end_piece_item_code="RM001-EP-1x1000x100", weight_kg=4.5625)],
    )

    validators.validate_sheet_cutting_layout(layout)


def test_reuse_end_piece_requires_reuse_bom_fields(validators: types.ModuleType) -> None:
    base = {
        "disposition": "Reuse",
        "weight_kg": 4.5625,
        "qty_per_sheet": 1,
    }

    with pytest.raises(ValidationError, match="Used for finished part"):
        validators.validate_sheet_cutting_layout(
            Layout(
                finished_parts=[FinishedPart("AB12SHR", 2, 10, 0)],
                end_pieces=[EndPiece(**base, used_for_finished_part="")],
            )
        )

    with pytest.raises(ValidationError, match="End piece item code"):
        validators.validate_sheet_cutting_layout(
            Layout(
                finished_parts=[FinishedPart("AB12SHR", 2, 10, 0)],
                end_pieces=[EndPiece(**base, end_piece_item_code="")],
            )
        )

    with pytest.raises(ValidationError, match="BOM quantity"):
        validators.validate_sheet_cutting_layout(
            Layout(
                finished_parts=[FinishedPart("AB12SHR", 2, 10, 0)],
                end_pieces=[EndPiece(**base, bom_quantity=0)],
            )
        )

    with pytest.raises(ValidationError, match="BOM scrap quantity"):
        validators.validate_sheet_cutting_layout(
            Layout(
                finished_parts=[FinishedPart("AB12SHR", 2, 10, 0)],
                end_pieces=[EndPiece(**base, bom_scrap_quantity_kg=-0.01)],
            )
        )


def test_positive_reuse_bom_scrap_requires_parent_process_scrap_item(validators: types.ModuleType) -> None:
    with pytest.raises(ValidationError, match="Process scrap item"):
        validators.validate_sheet_cutting_layout(
            Layout(
                finished_parts=[FinishedPart("AB12SHR", 2, 10, 0)],
                end_pieces=[EndPiece(weight_kg=4.5625, bom_scrap_quantity_kg=0.1)],
                process_scrap_item="",
            )
        )


def test_scrap_end_piece_requires_scrap_item(validators: types.ModuleType) -> None:
    with pytest.raises(ValidationError, match="Scrap item"):
        validators.validate_sheet_cutting_layout(
            Layout(
                finished_parts=[FinishedPart("AB12SHR", 2, 10, 0)],
                end_pieces=[
                    EndPiece(
                        disposition="Scrap",
                        scrap_item="",
                        used_for_finished_part=None,
                        bom_quantity=None,
                        bom_scrap_quantity_kg=None,
                        weight_kg=4.5625,
                    )
                ],
            )
        )


def test_end_piece_bom_status_is_calculated(validators: types.ModuleType) -> None:
    no_reuse = Layout(end_pieces=[])
    validators.apply_end_piece_bom_status(no_reuse)
    assert no_reuse.end_piece_bom_status == "Not Required"

    pending = Layout(end_pieces=[EndPiece(generated_end_piece_bom=None)])
    validators.apply_end_piece_bom_status(pending)
    assert pending.end_piece_bom_status == "Pending"

    generated = Layout(end_pieces=[EndPiece(generated_end_piece_bom="BOM-001")])
    validators.apply_end_piece_bom_status(generated)
    assert generated.end_piece_bom_status == "Generated"


def test_generated_end_piece_item_code_cannot_change_after_links_exist(
    validators: types.ModuleType,
) -> None:
    class ExistingEndPiece(EndPiece):
        def has_value_changed(self, fieldname: str) -> bool:
            return fieldname == "end_piece_item_code"

    with pytest.raises(ValidationError, match="End piece item code cannot be changed"):
        validators.validate_sheet_cutting_layout(
            Layout(
                finished_parts=[FinishedPart("AB12SHR", 2, 10, 0)],
                end_pieces=[
                    ExistingEndPiece(
                        weight_kg=4.5625,
                        generated_end_piece_item="RM001-EP-1x1000x100",
                    )
                ],
            )
        )

    with pytest.raises(ValidationError, match="End piece item code cannot be changed"):
        validators.validate_sheet_cutting_layout(
            Layout(
                finished_parts=[FinishedPart("AB12SHR", 2, 10, 0)],
                end_pieces=[
                    ExistingEndPiece(
                        weight_kg=4.5625,
                        generated_end_piece_bom="BOM-001",
                    )
                ],
            )
        )
```

- [ ] **Step 3: Run validator tests to verify failures**

Run:

```bash
pytest -q sheet_cutting_layout/tests/test_validators.py
```

Expected: FAIL on missing `suggest_end_piece_item_code`, old end-piece item validation, old quantity multiplication, and missing status logic.

- [ ] **Step 4: Implement validator changes**

In `validators.py`:

- Update `EndPieceRow` protocol:

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
    bom_scrap_quantity_kg: float | None
    generated_end_piece_item: str | None
    generated_end_piece_bom: str | None
    scrap_item: str | None
```

- Add `raw_material_item` and `end_piece_bom_status` to `SheetCuttingLayoutDocument`.
- Add helpers:

```python
def suggest_end_piece_item_code(
    *,
    raw_material_item: str | None,
    thickness_mm: float | None,
    width_mm: float | None,
    length_mm: float | None,
) -> str | None:
    if _is_missing(raw_material_item) or thickness_mm is None or width_mm is None or length_mm is None:
        return None
    if thickness_mm <= 0 or width_mm <= 0 or length_mm <= 0:
        return None
    return (
        f"{str(raw_material_item).strip()}-EP-"
        f"{_format_code_number(thickness_mm)}x{_format_code_number(width_mm)}x{_format_code_number(length_mm)}"
    )


def _format_code_number(value: float | int) -> str:
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.6f}".rstrip("0").rstrip(".")


def apply_end_piece_item_code_suggestions(
    layout: SheetCuttingLayoutDocument,
    end_pieces: Sequence[EndPieceRow],
) -> None:
    for end_piece in end_pieces:
        if not _is_reuse_end_piece(end_piece):
            continue
        if not _is_missing(getattr(end_piece, "end_piece_item_code", None)):
            continue
        suggested = suggest_end_piece_item_code(
            raw_material_item=getattr(layout, "raw_material_item", None),
            thickness_mm=getattr(layout, "sheet_thickness_mm", None),
            width_mm=getattr(end_piece, "width_mm", None),
            length_mm=getattr(end_piece, "length_mm", None),
        )
        if suggested:
            end_piece.end_piece_item_code = suggested
```

- In `validate_sheet_cutting_layout`, call `apply_end_piece_item_code_suggestions` after `apply_end_piece_weight_formulas`, and call `apply_end_piece_bom_status` before complete consumption validation.
- Change `apply_end_piece_weight_formulas`:

```python
qty_per_sheet = getattr(end_piece, "qty_per_sheet", None)
if weight is not None and qty_per_sheet is not None and qty_per_sheet > 0:
    end_piece.weight_kg = _flt(weight * qty_per_sheet)
```

- Change `calculate_consumed_weight_kg` end-piece sum:

```python
end_piece_weight = sum(
    end_piece.weight_kg
    for end_piece in end_pieces
    if end_piece.weight_kg is not None
)
```

- Replace `_validate_end_piece_required_fields` with:

```python
def _validate_end_piece_required_fields(end_piece: EndPieceRow) -> None:
    if end_piece.width_mm is None:
        frappe.throw(_("End piece width is required"))
    if end_piece.length_mm is None:
        frappe.throw(_("End piece length is required"))
    if end_piece.weight_kg is None:
        frappe.throw(_("End piece weight is required"))
    if end_piece.qty_per_sheet is None:
        frappe.throw(_("End piece quantity is required"))

    if _is_reuse_end_piece(end_piece):
        if _is_missing(getattr(end_piece, "used_for_finished_part", None)):
            frappe.throw(_("Used for finished part is required for reusable end pieces"))
        if _is_missing(getattr(end_piece, "end_piece_item_code", None)):
            frappe.throw(_("End piece item code is required for reusable end pieces"))
        if getattr(end_piece, "bom_quantity", None) is None or end_piece.bom_quantity <= 0:
            frappe.throw(_("BOM quantity must be greater than zero for reusable end pieces"))
        if getattr(end_piece, "bom_scrap_quantity_kg", None) is None:
            frappe.throw(_("BOM scrap quantity is required for reusable end pieces"))
        if end_piece.bom_scrap_quantity_kg < 0:
            frappe.throw(_("BOM scrap quantity must be non-negative"))

    if _is_scrap_end_piece(end_piece) and _is_missing(getattr(end_piece, "scrap_item", None)):
        frappe.throw(_("Scrap item is required for scrap end pieces"))
```

- Add:

```python
def _is_reuse_end_piece(end_piece: EndPieceRow) -> bool:
    return str(getattr(end_piece, "disposition", "") or "").strip().lower() == "reuse"


def _is_scrap_end_piece(end_piece: EndPieceRow) -> bool:
    return str(getattr(end_piece, "disposition", "") or "").strip().lower() == "scrap"


def _requires_process_scrap_item_for_reuse_bom(end_pieces: Sequence[EndPieceRow]) -> bool:
    return any(
        _is_reuse_end_piece(end_piece)
        and getattr(end_piece, "bom_scrap_quantity_kg", None) is not None
        and end_piece.bom_scrap_quantity_kg > 0
        for end_piece in end_pieces
    )


def apply_end_piece_bom_status(layout: SheetCuttingLayoutDocument) -> None:
    end_pieces = list(getattr(layout, "end_pieces", []) or [])
    reusable = [end_piece for end_piece in end_pieces if _is_reuse_end_piece(end_piece)]
    if not reusable:
        layout.end_piece_bom_status = "Not Required"
    elif all(not _is_missing(getattr(end_piece, "generated_end_piece_bom", None)) for end_piece in reusable):
        layout.end_piece_bom_status = "Generated"
    else:
        layout.end_piece_bom_status = "Pending"
```

- Change `_validate_end_piece_distribution` to divide `weight_kg` directly by `parts_per_sheet`, not `weight_kg * qty_per_sheet`.
- Add parent process scrap validation:

```python
if _requires_process_scrap_item_for_reuse_bom(end_pieces) and _is_missing(getattr(layout, "process_scrap_item", None)):
    frappe.throw(_("Process scrap item is required when reuse BOM scrap quantity is positive"))
```

- Add generated-link immutability validation:

```python
def _validate_generated_end_piece_item_code_is_locked(end_piece: EndPieceRow) -> None:
    has_value_changed = getattr(end_piece, "has_value_changed", None)
    if not callable(has_value_changed) or not has_value_changed("end_piece_item_code"):
        return
    if not _is_missing(getattr(end_piece, "generated_end_piece_item", None)) or not _is_missing(
        getattr(end_piece, "generated_end_piece_bom", None)
    ):
        frappe.throw(_("End piece item code cannot be changed after generated Item or BOM exists"))
```

Call `_validate_generated_end_piece_item_code_is_locked(end_piece)` inside the end-piece validation loop before `_validate_end_piece_required_fields(end_piece)`.

- [ ] **Step 5: Run validator tests to verify pass**

Run:

```bash
pytest -q sheet_cutting_layout/tests/test_validators.py
```

Expected: PASS.

### Task 3: Update Shearing BOM Tests and Service

**Files:**
- Modify: `sheet_cutting_layout/tests/test_bom_service.py`
- Modify: `sheet_cutting_layout/tests/test_release_service.py`
- Modify: `sheet_cutting_layout/tests/test_property_layout_invariants.py`
- Modify: `sheet_cutting_layout/services/bom_service.py`

- [ ] **Step 1: Update `test_bom_service.py` dataclasses**

Change `EndPiece`:

```python
@dataclass
class EndPiece:
    weight_kg: float
    qty_per_sheet: float = 1
    disposition: str = "Reuse"
    scrap_item: str | None = None
```

Add `no_of_strips: int = 11` to `Layout`.

- [ ] **Step 2: Replace old end-piece BOM tests**

Replace `test_generated_bom_uses_parts_per_sheet_quantity_and_sheet_weight_raw_qty` expectation:

```python
assert bom.quantity == 11
```

Replace reusable end-piece scrap test with:

```python
def test_reusable_end_pieces_do_not_create_shearing_scrap_rows() -> None:
    bom_service = import_bom_service()

    bom = bom_service.build_bom_from_layout_row(
        Layout(end_pieces=[EndPiece(weight_kg=3, qty_per_sheet=2, disposition="Reuse")]),
        FinishedPart(parts_per_sheet=6),
    )

    assert bom.scrap_items == []
```

Replace scrap end-piece test with:

```python
def test_scrap_endpiece_uses_row_level_scrap_item_and_per_sheet_weight() -> None:
    bom_service = import_bom_service()

    bom = bom_service.build_bom_from_layout_row(
        Layout(
            end_pieces=[
                EndPiece(weight_kg=8, qty_per_sheet=2, disposition="Scrap", scrap_item="END-SCRAP")
            ]
        ),
        FinishedPart(parts_per_sheet=4, scrap_weight_per_part_kg=1),
    )

    assert [(row.item_code, row.qty, row.row_type) for row in bom.scrap_items] == [
        ("PROCESS-SCRAP", 4, "process_scrap"),
        ("END-SCRAP", 8, "end_piece_scrap"),
    ]
```

Remove or update old `end_piece_per_part_kg` tests if the helper is no longer used. The new model
treats `weight_kg` as per-sheet end-piece weight.

- [ ] **Step 3: Run BOM tests to verify failures**

Run:

```bash
pytest -q sheet_cutting_layout/tests/test_bom_service.py
```

Expected: FAIL because service still uses `parts_per_sheet`, old `end_piece_item`, and multiplies by `qty_per_sheet`.

- [ ] **Step 4: Update `bom_service.py`**

Change protocols:

```python
class EndPieceRow(Protocol):
    weight_kg: float
    qty_per_sheet: float
    disposition: str | None
    scrap_item: str | None


class LayoutDocument(Protocol):
    raw_material_item: str
    process_scrap_item: str
    weight_per_sheet_kg: float
    no_of_strips: int
    end_pieces: Sequence[EndPieceRow]
```

In `build_bom_from_layout_row`:

```python
bom.quantity = int(getattr(layout_doc, "no_of_strips", 0) or finished_part_row.parts_per_sheet)
```

Keep process scrap as:

```python
process_scrap_weight = finished_part_row.scrap_weight_per_part_kg * finished_part_row.parts_per_sheet
```

For end pieces:

```python
for end_piece in layout_doc.end_pieces:
    if not _is_scrap_end_piece(end_piece):
        continue
    bom.scrap_items.append(
        BomItemRow(
            item_code=end_piece.scrap_item,
            qty=end_piece.weight_kg,
            row_type="end_piece_scrap",
        )
    )
```

Update `_sheet_weight_kg` fallback:

```python
end_piece_weight = sum(end_piece.weight_kg for end_piece in layout_doc.end_pieces)
```

Remove `end_piece_per_part_kg` if nothing uses it after this change. If a caller still needs a
distribution helper, update it to accept per-sheet `end_piece_weight_kg` and divide directly by
`parts_per_sheet` without `qty_per_sheet`.

- [ ] **Step 5: Update release/property tests for new shearing semantics**

In `test_release_service.py`:

- Update `EndPiece` dataclass to include `scrap_item: str | None = None` and remove required `end_piece_item`.
- In `test_release_generates_bom_for_one_sheet_in_kg_with_scrap_outputs`, use:

```python
end_pieces=[EndPiece(weight_kg=10.0, qty_per_sheet=2, disposition="Scrap", scrap_item="ENDSCRAP001")]
```

Expect:

```python
assert bom.quantity == 11
assert [(row.item_code, row.qty, row.row_type) for row in bom.scrap_items] == [
    ("PROCESSSCRAP001", 20.0, "process_scrap"),
    ("ENDSCRAP001", 10.0, "end_piece_scrap"),
]
```

In `test_property_layout_invariants.py`, make only the BOM/shearing semantic updates needed for this chunk:

- Update the `EndPiece` dataclass to keep any existing payload fields unchanged for now, but add `scrap_item: str | None = None`.
- Update `end_pieces_strategy()` to generate `scrap_item` for scrap rows.
- Change total end-piece weight expectations from `sum(end_piece.weight_kg * end_piece.qty_per_sheet ...)` to `sum(end_piece.weight_kg ...)`.
- In the property test that compares BOM scrap rows, set:

```python
expected_end_piece_scrap_qty = sum(
    end_piece.weight_kg
    for end_piece in layout_case.layout.end_pieces
    if end_piece.disposition == "Scrap"
)
```

- Assert reusable end pieces do not contribute to `end_piece_scrap`:

```python
assert _sum_bom_qty(bom.scrap_items, "end_piece_scrap") == pytest.approx(
    expected_end_piece_scrap_qty
)
```

- Update any expected BOM quantity from `parts_per_sheet` to `no_of_strips`.
- Leave payload key changes from `end_piece_item` to `end_piece_item_code` for Task 8, where the payload builders are changed in the same chunk.

- [ ] **Step 6: Run impacted service tests**

Run:

```bash
pytest -q sheet_cutting_layout/tests/test_bom_service.py sheet_cutting_layout/tests/test_release_service.py sheet_cutting_layout/tests/test_property_layout_invariants.py
```

Expected: PASS without changing canvas payload keys yet.

- [ ] **Step 7: Commit chunk 1**

Run:

```bash
git add sheet_cutting_layout/services/validators.py sheet_cutting_layout/services/bom_service.py sheet_cutting_layout/tests/test_validators.py sheet_cutting_layout/tests/test_bom_service.py sheet_cutting_layout/tests/test_release_service.py sheet_cutting_layout/tests/test_property_layout_invariants.py
git commit -m "feat: update end piece validation and shearing bom mapping"
```

---

## Chunk 2: End-Piece Preview and Generation Service

### Task 4: Add End-Piece BOM Service Unit Tests

**Files:**
- Create: `sheet_cutting_layout/tests/test_end_piece_bom_service.py`
- Create later: `sheet_cutting_layout/services/end_piece_bom_service.py`

- [ ] **Step 1: Write service tests with fake Frappe**

Create `test_end_piece_bom_service.py` with:

```python
from __future__ import annotations

import importlib
import types
from dataclasses import dataclass, field

import pytest


@dataclass
class EndPiece:
    end_piece_item_code: str = "RM001-EP-1.6x1250x179"
    generated_end_piece_item: str | None = None
    generated_end_piece_bom: str | None = None
    disposition: str = "Reuse"
    used_for_finished_part: str = "FG01SHR"
    bom_quantity: float = 11
    bom_scrap_quantity_kg: float = 0.25
    weight_kg: float = 2.814
    width_mm: float = 1250
    length_mm: float = 179


@dataclass
class Layout:
    name: str = "SCL-001"
    status: str = "Released"
    raw_material_item: str = "RM001"
    process_scrap_item: str = "MSScrap"
    sheet_thickness_mm: float = 1.6
    end_piece_bom_status: str = "Pending"
    end_pieces: list[EndPiece] = field(default_factory=lambda: [EndPiece()])

    def save(self, **kwargs: object) -> None:
        assert kwargs == {"ignore_permissions": True}


class FakeDoc:
    def __init__(self, doctype: str, name: str | None = None) -> None:
        self.doctype = doctype
        self.name = name or ""
        self.items: list[dict[str, object]] = []
        self.scrap_items: list[dict[str, object]] = []

    def append(self, table: str, row: dict[str, object]) -> None:
        getattr(self, table).append(row)

    def insert(self, **kwargs: object) -> "FakeDoc":
        self.insert_kwargs = kwargs
        if self.doctype == "Item" and not self.name:
            self.name = self.item_code
            self._frappe.items[self.item_code] = {
                "item_group": self.item_group,
                "stock_uom": self.stock_uom,
            }
        if self.doctype == "BOM" and not self.name:
            self.name = f"BOM-{len([doc for doc in self._frappe.inserted if doc.doctype == 'BOM']) + 1}"
        if not self.name:
            self.name = f"{self.doctype}-{len(self._frappe.inserted) + 1}"
        self._frappe.inserted.append(self)
        return self


class FakeFrappe:
    def __init__(self) -> None:
        self.items = {
            "RM001": {"item_group": "Raw Material", "stock_uom": "Kg"},
        }
        self.boms: dict[str, FakeDoc] = {}
        self.inserted: list[FakeDoc] = []

    def db_exists(self, doctype: str, name: str) -> bool:
        if doctype == "Item":
            return name in self.items
        if doctype == "BOM":
            return name in self.boms
        return False

    def get_value(self, doctype: str, name: str, fieldname: str) -> object:
        assert doctype == "Item"
        return self.items[name][fieldname]

    def new_doc(self, doctype: str) -> FakeDoc:
        doc = FakeDoc(doctype)
        doc._frappe = self
        return doc

    def throw(self, message: str) -> None:
        raise ValueError(message)


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    module = importlib.import_module("sheet_cutting_layout.services.end_piece_bom_service")
    fake = FakeFrappe()
    monkeypatch.setattr(module, "frappe", fake)
    return module
```

Add tests:

```python
def test_preview_reports_existing_item_and_linked_bom(service: types.ModuleType) -> None:
    fake = service.frappe
    fake.items["RM001-EP-1.6x1250x179"] = {"item_group": "Raw Material", "stock_uom": "Kg"}
    layout = Layout(end_pieces=[EndPiece(generated_end_piece_bom="BOM-LINKED")])

    rows = service.preview_end_piece_boms(layout)

    assert rows == [
        {
            "idx": 1,
            "end_piece_item_code": "RM001-EP-1.6x1250x179",
            "suggested_item_code": "RM001-EP-1.6x1250x179",
            "item_status": "Exists",
            "used_for_finished_part": "FG01SHR",
            "bom_quantity": 11,
            "raw_material_qty_kg": 2.814,
            "bom_scrap_quantity_kg": 0.25,
            "bom_status": "Already linked",
            "generated_end_piece_bom": "BOM-LINKED",
        }
    ]


def test_preview_does_not_create_records(service: types.ModuleType) -> None:
    service.preview_end_piece_boms(Layout())

    assert service.frappe.inserted == []


def test_preview_reports_missing_item_as_will_be_created(service: types.ModuleType) -> None:
    rows = service.preview_end_piece_boms(Layout())

    assert rows[0]["item_status"] == "Will be created"


def test_generate_reuses_existing_item_and_creates_bom(service: types.ModuleType) -> None:
    fake = service.frappe
    fake.items["RM001-EP-1.6x1250x179"] = {"item_group": "Raw Material", "stock_uom": "Kg"}
    layout = Layout()

    result = service.generate_end_piece_boms(layout)

    bom = fake.inserted[0]
    assert result["generated"] == ["BOM-1"]
    assert layout.end_pieces[0].generated_end_piece_item == "RM001-EP-1.6x1250x179"
    assert layout.end_pieces[0].generated_end_piece_bom == "BOM-1"
    assert layout.end_piece_bom_status == "Generated"
    assert bom.doctype == "BOM"
    assert bom.item == "FG01SHR"
    assert bom.quantity == 11
    assert bom.items == [{"item_code": "RM001-EP-1.6x1250x179", "qty": 2.814, "uom": "Kg"}]
    assert bom.scrap_items == [{"item_code": "MSScrap", "qty": 0.25, "stock_qty": 0.25, "uom": "Kg"}]


def test_generate_creates_missing_item_from_raw_material_group(service: types.ModuleType) -> None:
    layout = Layout()

    service.generate_end_piece_boms(layout)

    item = service.frappe.inserted[0]
    assert item.doctype == "Item"
    assert item.item_code == "RM001-EP-1.6x1250x179"
    assert item.item_name == "RM001-EP-1.6x1250x179"
    assert item.item_group == "Raw Material"
    assert item.stock_uom == "Kg"
    assert item.is_stock_item == 1
    assert item.disabled == 0
    assert layout.end_pieces[0].generated_end_piece_item == "RM001-EP-1.6x1250x179"
    bom = service.frappe.inserted[1]
    assert bom.items == [{"item_code": "RM001-EP-1.6x1250x179", "qty": 2.814, "uom": "Kg"}]


def test_generate_with_zero_scrap_quantity_creates_no_scrap_row(service: types.ModuleType) -> None:
    layout = Layout(end_pieces=[EndPiece(bom_scrap_quantity_kg=0)])

    service.generate_end_piece_boms(layout)

    bom = service.frappe.inserted[1]
    assert bom.scrap_items == []


def test_generate_requires_process_scrap_item_when_scrap_quantity_is_positive(
    service: types.ModuleType,
) -> None:
    layout = Layout(process_scrap_item="", end_pieces=[EndPiece(bom_scrap_quantity_kg=0.25)])

    with pytest.raises(ValueError, match="Row 1.*Process scrap item"):
        service.generate_end_piece_boms(layout)


def test_generate_validation_errors_include_row_number(service: types.ModuleType) -> None:
    layout = Layout(
        end_pieces=[
            EndPiece(generated_end_piece_bom="BOM-OLD"),
            EndPiece(end_piece_item_code="", bom_scrap_quantity_kg=0),
        ]
    )

    with pytest.raises(ValueError, match="Row 2.*End piece item code"):
        service.generate_end_piece_boms(layout)


def test_generate_skips_linked_rows_and_generates_pending_rows(service: types.ModuleType) -> None:
    layout = Layout(
        end_pieces=[
            EndPiece(generated_end_piece_bom="BOM-OLD"),
            EndPiece(end_piece_item_code="RM001-EP-1.6x1250x180", length_mm=180, bom_scrap_quantity_kg=0),
        ]
    )

    result = service.generate_end_piece_boms(layout)

    assert result["generated"] == ["BOM-1"]
    assert layout.end_pieces[0].generated_end_piece_bom == "BOM-OLD"
    assert layout.end_pieces[1].generated_end_piece_bom == "BOM-1"


def test_generate_skips_already_linked_rows(service: types.ModuleType) -> None:
    layout = Layout(end_pieces=[EndPiece(generated_end_piece_bom="BOM-OLD")])

    result = service.generate_end_piece_boms(layout)

    assert result["generated"] == []
    assert service.frappe.inserted == []


def test_generate_requires_released_layout(service: types.ModuleType) -> None:
    with pytest.raises(ValueError, match="Released"):
        service.generate_end_piece_boms(Layout(status="Draft"))
```

- [ ] **Step 2: Run tests to verify import failure**

Run:

```bash
pytest -q sheet_cutting_layout/tests/test_end_piece_bom_service.py
```

Expected: FAIL with `ModuleNotFoundError` for `end_piece_bom_service`.

### Task 5: Implement End-Piece BOM Service

**Files:**
- Create: `sheet_cutting_layout/services/end_piece_bom_service.py`
- Modify: `sheet_cutting_layout/tests/test_end_piece_bom_service.py` only if fake behavior needs harmless alignment with Frappe APIs.

- [ ] **Step 1: Create service module**

Create `end_piece_bom_service.py`:

```python
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, TypedDict

from sheet_cutting_layout.services.validators import (
    apply_end_piece_bom_status,
    suggest_end_piece_item_code,
)

try:
    import frappe
except ImportError:
    frappe = None

_ = getattr(frappe, "_", lambda message: message)


class EndPieceRow(Protocol):
    end_piece_item_code: str | None
    generated_end_piece_item: str | None
    generated_end_piece_bom: str | None
    disposition: str | None
    used_for_finished_part: str | None
    bom_quantity: float | None
    bom_scrap_quantity_kg: float | None
    weight_kg: float | None
    width_mm: float | None
    length_mm: float | None


class LayoutDocument(Protocol):
    name: str
    status: str
    raw_material_item: str
    process_scrap_item: str | None
    sheet_thickness_mm: float | None
    end_piece_bom_status: str | None
    end_pieces: Sequence[EndPieceRow]

    def save(self, **kwargs: object) -> None: ...


class PreviewRow(TypedDict):
    idx: int
    end_piece_item_code: str
    suggested_item_code: str | None
    item_status: str
    used_for_finished_part: str | None
    bom_quantity: float | None
    raw_material_qty_kg: float | None
    bom_scrap_quantity_kg: float | None
    bom_status: str
    generated_end_piece_bom: str | None


def preview_end_piece_boms(layout: LayoutDocument) -> list[PreviewRow]:
    return [_preview_row(layout, row, idx) for idx, row in _pending_or_linked_reuse_rows(layout)]


def generate_end_piece_boms(layout: LayoutDocument) -> dict[str, list[str]]:
    _validate_released(layout)
    generated: list[str] = []
    for idx, row in _pending_or_linked_reuse_rows(layout):
        if row.generated_end_piece_bom:
            continue
        _validate_generation_row(layout, row, idx)
        item_code = _ensure_end_piece_item(layout, row)
        bom_name = _create_reuse_bom(layout, row, item_code)
        row.generated_end_piece_item = item_code
        row.generated_end_piece_bom = bom_name
        generated.append(bom_name)

    apply_end_piece_bom_status(layout)
    if hasattr(layout, "save"):
        layout.save(ignore_permissions=True)
    return {"generated": generated}
```

Add helpers in the same file:

```python
def _pending_or_linked_reuse_rows(layout: LayoutDocument) -> list[tuple[int, EndPieceRow]]:
    return [
        (idx, row)
        for idx, row in enumerate(getattr(layout, "end_pieces", []) or [], start=1)
        if _is_reuse(row)
    ]


def _preview_row(layout: LayoutDocument, row: EndPieceRow, idx: int) -> PreviewRow:
    item_code = row.end_piece_item_code or ""
    suggested = suggest_end_piece_item_code(
        raw_material_item=getattr(layout, "raw_material_item", None),
        thickness_mm=getattr(layout, "sheet_thickness_mm", None),
        width_mm=getattr(row, "width_mm", None),
        length_mm=getattr(row, "length_mm", None),
    )
    return {
        "idx": idx,
        "end_piece_item_code": item_code,
        "suggested_item_code": suggested,
        "item_status": "Exists" if item_code and _item_exists(item_code) else "Will be created",
        "used_for_finished_part": row.used_for_finished_part,
        "bom_quantity": row.bom_quantity,
        "raw_material_qty_kg": row.weight_kg,
        "bom_scrap_quantity_kg": row.bom_scrap_quantity_kg,
        "bom_status": "Already linked" if row.generated_end_piece_bom else "Will be created",
        "generated_end_piece_bom": row.generated_end_piece_bom,
    }


def _ensure_end_piece_item(layout: LayoutDocument, row: EndPieceRow) -> str:
    item_code = str(row.end_piece_item_code or "").strip()
    if _item_exists(item_code):
        return item_code

    raw_item_group = frappe.get_value("Item", layout.raw_material_item, "item_group")
    item = frappe.new_doc("Item")
    item.item_code = item_code
    item.item_name = item_code
    item.item_group = raw_item_group
    item.stock_uom = "Kg"
    item.is_stock_item = 1
    item.disabled = 0
    item.insert(ignore_permissions=True)
    return item_code


def _create_reuse_bom(layout: LayoutDocument, row: EndPieceRow, item_code: str) -> str:
    bom = frappe.new_doc("BOM")
    bom.item = row.used_for_finished_part
    bom.quantity = row.bom_quantity
    bom.uom = "Kg"
    bom.custom_operation = "Shearing"
    bom.sheet_cutting_layout = getattr(layout, "name", None)
    bom.append("items", {"item_code": item_code, "qty": row.weight_kg, "uom": "Kg"})
    scrap_qty = float(row.bom_scrap_quantity_kg or 0)
    if scrap_qty > 0:
        bom.append(
            "scrap_items",
            {
                "item_code": layout.process_scrap_item,
                "qty": scrap_qty,
                "stock_qty": scrap_qty,
                "uom": "Kg",
            },
        )
    bom.insert(ignore_permissions=True)
    return bom.name


def _validate_generation_row(layout: LayoutDocument, row: EndPieceRow, idx: int) -> None:
    if _is_missing(row.end_piece_item_code):
        _throw_row(idx, "End piece item code is required")
    if _is_missing(row.used_for_finished_part):
        _throw_row(idx, "Used for finished part is required")
    if row.bom_quantity is None or row.bom_quantity <= 0:
        _throw_row(idx, "BOM quantity must be greater than zero")
    if row.bom_scrap_quantity_kg is None or row.bom_scrap_quantity_kg < 0:
        _throw_row(idx, "BOM scrap quantity must be non-negative")
    if row.weight_kg is None or row.weight_kg <= 0:
        _throw_row(idx, "End piece weight must be greater than zero")
    if row.bom_scrap_quantity_kg > 0 and _is_missing(layout.process_scrap_item):
        _throw_row(idx, "Process scrap item is required when reuse BOM scrap quantity is positive")


def _validate_released(layout: LayoutDocument) -> None:
    if getattr(layout, "status", None) != "Released":
        _throw("End Piece BOMs can only be generated for Released layouts")


def _item_exists(item_code: str) -> bool:
    return bool(item_code and frappe.db_exists("Item", item_code))


def _is_reuse(row: EndPieceRow) -> bool:
    return str(getattr(row, "disposition", "") or "").strip().lower() == "reuse"


def _is_missing(value: object) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _throw(message: str) -> None:
    if frappe:
        frappe.throw(_(message))
    raise ValueError(message)


def _throw_row(idx: int, message: str) -> None:
    _throw(f"Row {idx}: {message}")
```

- [ ] **Step 2: Run service tests**

Run:

```bash
pytest -q sheet_cutting_layout/tests/test_end_piece_bom_service.py
```

Expected: PASS.

- [ ] **Step 3: Commit service tests and implementation**

Run:

```bash
git add sheet_cutting_layout/services/end_piece_bom_service.py sheet_cutting_layout/tests/test_end_piece_bom_service.py
git commit -m "feat: add end piece bom generation service"
```

---

## Chunk 3: Controller Methods, Client UI, Canvas Payload, and Full Verification

### Task 6: Add Controller Method Tests and Whitelisted Methods

**Files:**
- Modify: `sheet_cutting_layout/tests/test_validators.py` or `sheet_cutting_layout/tests/test_release_service.py` for controller delegation tests
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`
- Modify later: `sheet_cutting_layout/tests/bench_pytest_bridge.py`

- [ ] **Step 1: Add controller delegation tests**

In `test_validators.py`, after `test_controller_validate_delegates_to_service`, add:

```python
def test_controller_preview_end_piece_boms_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import sheet_cutting_layout

    calls: list[str] = []

    class FakeFrappe:
        @staticmethod
        def get_doc(doctype: str, name: str) -> object:
            calls.append(f"{doctype}:{name}")
            return object()

    monkeypatch.setattr(sheet_cutting_layout, "frappe", FakeFrappe)
    monkeypatch.setattr(sheet_cutting_layout, "preview_end_piece_boms", lambda doc: [{"idx": 1}])

    assert sheet_cutting_layout.preview_sheet_cutting_layout_end_piece_boms("SCL-001") == [{"idx": 1}]
    assert calls == ["Sheet Cutting Layout:SCL-001"]


def test_controller_generate_end_piece_boms_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import sheet_cutting_layout

    calls: list[str] = []

    class FakeFrappe:
        @staticmethod
        def get_doc(doctype: str, name: str) -> object:
            calls.append(f"{doctype}:{name}")
            return object()

    monkeypatch.setattr(sheet_cutting_layout, "frappe", FakeFrappe)
    monkeypatch.setattr(sheet_cutting_layout, "generate_end_piece_boms", lambda doc: {"generated": ["BOM-1"]})

    assert sheet_cutting_layout.generate_sheet_cutting_layout_end_piece_boms("SCL-001") == {
        "generated": ["BOM-1"]
    }
    assert calls == ["Sheet Cutting Layout:SCL-001"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest -q sheet_cutting_layout/tests/test_validators.py::test_controller_preview_end_piece_boms_delegates sheet_cutting_layout/tests/test_validators.py::test_controller_generate_end_piece_boms_delegates
```

Expected: FAIL because controller functions do not exist.

- [ ] **Step 3: Add controller imports and methods**

In `sheet_cutting_layout.py`, add imports:

```python
from sheet_cutting_layout.services.end_piece_bom_service import (
    generate_end_piece_boms,
    preview_end_piece_boms,
)
```

Add whitelisted methods near `create_sheet_cutting_layout_revision`:

```python
@whitelist()
def preview_sheet_cutting_layout_end_piece_boms(name: str) -> list[dict[str, object]]:
    if not frappe:
        raise RuntimeError("Frappe is required to preview End Piece BOMs")
    doc = frappe.get_doc("Sheet Cutting Layout", name)
    return preview_end_piece_boms(doc)


@whitelist()
def generate_sheet_cutting_layout_end_piece_boms(name: str) -> dict[str, list[str]]:
    if not frappe:
        raise RuntimeError("Frappe is required to generate End Piece BOMs")
    doc = frappe.get_doc("Sheet Cutting Layout", name)
    return generate_end_piece_boms(doc)
```

- [ ] **Step 4: Run controller tests**

Run:

```bash
pytest -q sheet_cutting_layout/tests/test_validators.py::test_controller_preview_end_piece_boms_delegates sheet_cutting_layout/tests/test_validators.py::test_controller_generate_end_piece_boms_delegates
```

Expected: PASS.

### Task 7: Update Client Script Tests and Form UX

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`

- [ ] **Step 1: Add JS source assertions**

In the client script test section, add assertions:

```python
assert "preview_sheet_cutting_layout_end_piece_boms" in client_script
assert "generate_sheet_cutting_layout_end_piece_boms" in client_script
assert "Preview End Piece Items" in client_script
assert "Generate End Piece BOMs" in client_script
assert "end_piece_item_code" in client_script
assert "suggested_item_code" in client_script
assert "Current Item Code" in client_script
assert "Suggested Item Code" in client_script
assert "generated_end_piece_bom" in client_script
assert "hasRequiredEndPiecePreviewInputs" in client_script
assert "raw_material_item: updateEndPieceItemCodesAndRedraw" in client_script
assert "numberOrZero(row.weight_kg)" in client_script
assert "numberOrZero(row.weight_kg) * numberOrZero(row.qty_per_sheet)" not in client_script
```

- [ ] **Step 2: Run JS/source tests to verify failure**

Run:

```bash
pytest -q sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py
```

Expected: FAIL because script does not include new buttons and still multiplies end-piece weight by quantity.

- [ ] **Step 3: Update client script**

In `sheet_cutting_layout.js`:

- Change `calculateEndPieceWeight`:

```javascript
function calculateEndPieceWeight(frm, row) {
    const singleWeight = calculateWeight(frm.doc.sheet_thickness_mm, row.width_mm, row.length_mm);
    if (singleWeight === null) {
        return null;
    }
    return Number((singleWeight * numberOrZero(row.qty_per_sheet || 1)).toFixed(getCalculationPrecision()));
}
```

- Add code helpers:

```javascript
function formatCodeNumber(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) {
        return "";
    }
    if (Number.isInteger(number)) {
        return String(number);
    }
    return number.toFixed(6).replace(/0+$/, "").replace(/\.$/, "");
}

function suggestEndPieceItemCode(frm, row) {
    if (!frm.doc.raw_material_item || !frm.doc.sheet_thickness_mm || !row.width_mm || !row.length_mm) {
        return null;
    }
    return `${frm.doc.raw_material_item}-EP-${formatCodeNumber(frm.doc.sheet_thickness_mm)}x${formatCodeNumber(row.width_mm)}x${formatCodeNumber(row.length_mm)}`;
}

function updateEndPieceItemCodes(frm) {
    const updates = (frm.doc.end_pieces || []).flatMap((row) => {
        if (row.disposition !== "Reuse" || row.generated_end_piece_item || row.generated_end_piece_bom) {
            return [];
        }
        if (row.end_piece_item_code) {
            return [];
        }
        const suggested = suggestEndPieceItemCode(frm, row);
        if (!suggested) {
            return [];
        }
        return [frappe.model.set_value(row.doctype, row.name, "end_piece_item_code", suggested)];
    });
    return Promise.all(updates);
}

function updateEndPieceItemCodesAndRedraw(frm) {
    updateEndPieceItemCodes(frm).then(() => {
        scheduleSheetLayoutRedraw(frm);
    });
}
```

This intentionally fills blank `end_piece_item_code` values only. It must not overwrite a user-edited
code unless the user clears the field first.

- Change consumption end-piece reducer to:

```javascript
endPieces.reduce((total, row) => total + numberOrZero(row.weight_kg), 0)
```

- Add refresh buttons:

```javascript
function addEndPieceBomButtons(frm) {
    const hasReusableEndPieces = (frm.doc.end_pieces || []).some((row) => row.disposition === "Reuse");
    if (!hasReusableEndPieces || frm.is_new() || !hasRequiredEndPiecePreviewInputs(frm)) {
        return;
    }
    frm.add_custom_button(__("Preview End Piece Items"), () => previewEndPieceItems(frm));
    if (frm.doc.status === "Released" && frm.doc.end_piece_bom_status === "Pending") {
        frm.add_custom_button(__("Generate End Piece BOMs"), () => generateEndPieceBoms(frm));
    }
}

function hasRequiredEndPiecePreviewInputs(frm) {
    return Boolean(frm.doc.raw_material_item && frm.doc.sheet_thickness_mm);
}

function previewEndPieceItems(frm) {
    frappe.call({
        method: "sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.sheet_cutting_layout.preview_sheet_cutting_layout_end_piece_boms",
        args: { name: frm.doc.name },
        callback: (r) => {
            showEndPiecePreviewDialog(r.message || []);
        },
    });
}

function generateEndPieceBoms(frm) {
    frappe.call({
        method: "sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.sheet_cutting_layout.generate_sheet_cutting_layout_end_piece_boms",
        args: { name: frm.doc.name },
        freeze: true,
        freeze_message: __("Generating End Piece BOMs"),
        callback: () => frm.reload_doc(),
    });
}

function showEndPiecePreviewDialog(rows) {
    const fields = [
        {
            fieldname: "preview",
            fieldtype: "HTML",
            options: buildEndPiecePreviewHtml(rows),
        },
    ];
    const dialog = new frappe.ui.Dialog({
        title: __("Preview End Piece Items"),
        fields,
        primary_action_label: __("Close"),
        primary_action() {
            dialog.hide();
        },
    });
    dialog.show();
}

function buildEndPiecePreviewHtml(rows) {
    if (!rows.length) {
        return `<p>${__("No reusable end pieces found.")}</p>`;
    }
    const body = rows
        .map(
            (row) => `<tr>
                <td>${frappe.utils.escape_html(String(row.idx || ""))}</td>
                <td>${frappe.utils.escape_html(row.end_piece_item_code || "")}</td>
                <td>${frappe.utils.escape_html(row.suggested_item_code || "")}</td>
                <td>${frappe.utils.escape_html(row.item_status || "")}</td>
                <td>${frappe.utils.escape_html(row.used_for_finished_part || "")}</td>
                <td>${frappe.utils.escape_html(String(row.bom_quantity ?? ""))}</td>
                <td>${frappe.utils.escape_html(String(row.raw_material_qty_kg ?? ""))}</td>
                <td>${frappe.utils.escape_html(String(row.bom_scrap_quantity_kg ?? ""))}</td>
                <td>${frappe.utils.escape_html(row.bom_status || "")}</td>
            </tr>`
        )
        .join("");
    return `<table class="table table-bordered">
        <thead><tr>
            <th>${__("Row")}</th>
            <th>${__("Current Item Code")}</th>
            <th>${__("Suggested Item Code")}</th>
            <th>${__("Item Status")}</th>
            <th>${__("Used For")}</th>
            <th>${__("BOM Qty")}</th>
            <th>${__("Raw Qty Kg")}</th>
            <th>${__("Scrap Qty Kg")}</th>
            <th>${__("BOM Status")}</th>
        </tr></thead>
        <tbody>${body}</tbody>
    </table>`;
}
```

- In `refresh`, call `addEndPieceBomButtons(frm)`.
- In update chains after sheet/end-piece dimension changes, call `updateEndPieceItemCodes(frm)`.
- Add a parent handler for raw material changes:

```javascript
raw_material_item: updateEndPieceItemCodesAndRedraw,
```

- In `Layout End Piece` handlers:

```javascript
end_piece_item_code: scheduleParentRedraw,
scrap_item: scheduleParentRedraw,
bom_quantity: scheduleParentRedraw,
bom_scrap_quantity_kg: scheduleParentRedraw,
generated_end_piece_item: scheduleParentRedraw,
generated_end_piece_bom: scheduleParentRedraw,
```

- Remove `end_piece_item` handler.

- [ ] **Step 4: Run JS/source tests**

Run:

```bash
pytest -q sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py
```

Expected: PASS.

### Task 8: Update Canvas Payload Tests and Payload Code

**Files:**
- Modify: `sheet_cutting_layout/tests/test_property_layout_invariants.py`
- Modify: `sheet_cutting_layout/services/canvas_payload.py`
- Modify: `sheet_cutting_layout/public/js/sheet_layout_canvas.js`

- [ ] **Step 1: Update payload tests**

Replace expected `end_piece_item` payload keys with `end_piece_item_code`, and change end-piece totals to use `weight_kg` directly.

Example expected zone:

```python
{
    "end_piece_item_code": "RM001-EP-1.6x1250x179",
    "weight_kg": 2.814,
    "qty_per_sheet": 1,
    "disposition": "Reuse",
    "used_for_finished_part": "FG01SHR",
    "x_mm": 0.0,
    "y_mm": 2321,
    "width_mm": 1250.0,
    "length_mm": 179,
}
```

- [ ] **Step 2: Run payload tests to verify failure**

Run:

```bash
pytest -q sheet_cutting_layout/tests/test_property_layout_invariants.py
```

Expected: FAIL due to old payload key and old quantity multiplication.

- [ ] **Step 3: Update Python and browser canvas payload builders**

In `canvas_payload.py`:

- Protocol field becomes `end_piece_item_code`.
- Zone dict uses:

```python
"end_piece_item_code": _optional_str(getattr(end_piece, "end_piece_item_code", None)),
```

- Summary total:

```python
if weight is not None and weight >= 0:
    total_end_piece_weight += weight
```

In `public/js/sheet_layout_canvas.js`:

- Replace `end_piece_item` with `end_piece_item_code`.
- Change summary calculation to add `weight` directly, not `weight * qty`.

- [ ] **Step 4: Run payload tests**

Run:

```bash
pytest -q sheet_cutting_layout/tests/test_property_layout_invariants.py
```

Expected: PASS.

### Task 9: Run Full Verification and Bench Migration/Test

**Files:**
- All modified files from previous chunks.
- Modify: `sheet_cutting_layout/tests/bench_pytest_bridge.py`

- [ ] **Step 1: Add new pytest module to bench bridge**

Open `sheet_cutting_layout/tests/bench_pytest_bridge.py` and add
`sheet_cutting_layout.tests.test_end_piece_bom_service` to the module list used by the bridge.

Run:

```bash
pytest -q sheet_cutting_layout/tests/bench_pytest_bridge.py
```

Expected: PASS, or if this file is only bench-collected, confirm the module import list includes the new test module.

- [ ] **Step 2: Run focused pytest suite**

Run:

```bash
pytest -q sheet_cutting_layout/tests/test_validators.py sheet_cutting_layout/tests/test_bom_service.py sheet_cutting_layout/tests/test_end_piece_bom_service.py sheet_cutting_layout/tests/test_release_service.py sheet_cutting_layout/tests/test_property_layout_invariants.py sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py
```

Expected: PASS.

- [ ] **Step 3: Run pre-commit on changed files**

Run:

```bash
pre-commit run --files sheet_cutting_layout/services/validators.py sheet_cutting_layout/services/bom_service.py sheet_cutting_layout/services/end_piece_bom_service.py sheet_cutting_layout/services/canvas_payload.py sheet_cutting_layout/public/js/sheet_layout_canvas.js sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json sheet_cutting_layout/tests/test_validators.py sheet_cutting_layout/tests/test_bom_service.py sheet_cutting_layout/tests/test_end_piece_bom_service.py sheet_cutting_layout/tests/test_release_service.py sheet_cutting_layout/tests/test_property_layout_invariants.py sheet_cutting_layout/tests/bench_pytest_bridge.py sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py
```

Expected: PASS. If hooks reformat files, rerun the focused pytest suite.

- [ ] **Step 4: Run bench migrate on bench16**

Run from `/Users/gurudattkulkarni/Workspace/bench16`:

```bash
source .venv/bin/activate
bench --site development.localhost migrate
```

Expected: migration succeeds and DocType metadata imports without stale `end_piece_item` errors.

- [ ] **Step 5: Run bench app tests**

Run from `/Users/gurudattkulkarni/Workspace/bench16`:

```bash
source .venv/bin/activate
bench --site development.localhost run-tests --app sheet_cutting_layout
```

Expected: PASS with bench test summary.

- [ ] **Step 6: Manual browser verification on localhost:8002**

Use Administrator / `admin` for bench16 if login is needed.

Verify:

1. Open `http://localhost:8002/app/sheet-cutting-layout`.
2. Open or create a layout with one `Reuse` end piece.
3. Confirm `End Piece Item` is gone.
4. Confirm `End Piece Item Code` auto-suggests `RM001-EP-1.6x1250x179` style values and remains editable before generation.
5. Confirm `Preview End Piece Items` opens a read-only table and does not create Item/BOM records.
6. Confirm `Generate End Piece BOMs` appears only when layout status is `Released` and `end_piece_bom_status` is `Pending`.
7. Run generation and confirm child row links `generated_end_piece_item` and `generated_end_piece_bom` are set.
8. Confirm parent `end_piece_bom_status` becomes `Generated`.

- [ ] **Step 7: Commit final UI/controller/payload changes**

Run:

```bash
git add sheet_cutting_layout/services/canvas_payload.py sheet_cutting_layout/public/js/sheet_layout_canvas.js sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py sheet_cutting_layout/tests/test_property_layout_invariants.py sheet_cutting_layout/tests/test_validators.py sheet_cutting_layout/tests/bench_pytest_bridge.py
git commit -m "feat: add end piece bom preview and generation actions"
```

- [ ] **Step 8: Final status check**

Run:

```bash
git status -sb
```

Expected: clean except known generated/local artifacts such as `outputs/`.
