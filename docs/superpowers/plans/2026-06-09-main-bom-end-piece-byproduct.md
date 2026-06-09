# Main BOM End-Piece Byproduct Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox
> (`- [ ]`) syntax for tracking.

**Goal:** Main BOMs generated during MR Release include reusable end pieces as byproduct rows in
the BOM scrap table and validate against the input raw material sheet weight.

**Architecture:** Extract generated end-piece Item creation from
`sheet_cutting_layout/services/end_piece_bom_service.py` into a small shared service so both main
BOM release and end-piece BOM generation can use the same deterministic Item behavior without a
circular import. Extend `bom_service` so reusable end-piece rows become `BomItemRow` scrap rows
using the generated end-piece Item. Keep process scrap and scrap-disposition behavior unchanged.

**Tech Stack:** Frappe/ERPNext app, Python service modules, bench-native unittest tests via
`bench --site ... run-tests`.

---

## File Structure

- Add `sheet_cutting_layout/services/end_piece_item_service.py`
  - Responsibility: derive, create, and return generated end-piece Item codes.
  - Move shared helpers from `end_piece_bom_service.py` here.
  - Keep generated Item defaults unchanged: `stock_uom = "Kg"`, HSN from finished item, valuation
    and item group from raw material, reciprocal UOM rows.
- Modify `sheet_cutting_layout/services/end_piece_bom_service.py`
  - Responsibility: generate end-piece BOMs.
  - Replace local Item creation helpers with calls to `ensure_end_piece_item()`.
- Modify `sheet_cutting_layout/services/bom_service.py`
  - Responsibility: build expected main BOM rows.
  - Add reusable end-piece byproduct rows to `scrap_items`.
  - Add a mass-balance helper for main BOM expectations.
- Modify `sheet_cutting_layout/services/release_service.py`
  - Responsibility: persist generated main BOMs during MR Release.
  - Ensure reusable end-piece Item links are persisted before BOM insert.
- Modify `sheet_cutting_layout/tests/test_bom_service.py`
  - Responsibility: unit-level expected BOM row and mass-balance behavior.
- Modify `sheet_cutting_layout/tests/test_release_service.py`
  - Responsibility: release-level behavior with generated main BOMs and row link persistence.
- Modify `sheet_cutting_layout/tests/test_end_piece_bom_service.py`
  - Responsibility: confirm end-piece BOM generation reuses the shared Item service behavior.

No migration or backfill files are needed.

---

### Task 1: Add Failing Main BOM Behavior Tests

**Files:**
- Modify: `sheet_cutting_layout/tests/test_bom_service.py`
- Modify: `sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Update the `EndPiece` fixtures to include reuse fields**

Add fields needed by deterministic item-code derivation:

```python
@dataclass
class EndPiece:
	weight_kg: float
	qty_per_sheet: float = 1
	disposition: str = "Reuse"
	scrap_item: str | None = None
	used_for_finished_part: str | None = "FG002SHR"
	end_piece_item_code: str | None = None
	width_mm: float | None = 1250
	length_mm: float | None = 179
```

Add `sheet_thickness_mm` to layout fixtures where needed.

- [ ] **Step 2: Replace the old reuse expectation**

Rename `test_reuse_end_pieces_do_not_create_shearing_bom_scrap_rows()` to a behavior test that
expects reusable end pieces in the main BOM scrap table.

Expected assertions:

```python
bom = bom_service.build_bom_from_layout_row(
	Layout(sheet_thickness_mm=1.6, end_pieces=[EndPiece(weight_kg=2.81388)]),
	FinishedPart(parts_per_sheet=77),
)

assert [(row.item_code, row.qty, row.uom, row.row_type) for row in bom.scrap_items] == [
	("FG002SHR-EP-1.6x1250x179", 2.81388, "Kg", "end_piece_byproduct"),
]
```

If process scrap is also present, assert the process scrap row remains first and the byproduct row
is appended after it.

- [ ] **Step 3: Add a mass-balance expectation test**

Use the `002-R2` numbers:

```python
layout = Layout(
	raw_material_item="RM001",
	process_scrap_item="MSScrap",
	weight_per_sheet_kg=39.3,
	parts_per_sheet=77,
	net_weight_per_part_kg=0.289,
	gross_weight_per_part_kg=0.473846,
	scrap_weight_per_part_kg=0.184846,
	sheet_thickness_mm=1.6,
	end_pieces=[EndPiece(weight_kg=2.81388)],
)
```

Assert the expected BOM rows reconcile to `39.3` within the same decimal tolerance used elsewhere
in tests.

- [ ] **Step 4: Add a release-level behavior test**

In `test_release_service.py`, add a test that releases a layout with:

- raw material valuation rate available through fakes or a monkeypatched shared Item service,
- one reusable end piece,
- positive process scrap.

Assert:

- release creates or reuses the generated end-piece Item code,
- `layout.end_pieces[0].end_piece_item_code == "FG002SHR-EP-1.6x1250x179"`,
- generated main BOM scrap rows include process scrap and the generated end-piece Item,
- `layout.finished_parts[0].scrap_weight_kg` equals process scrap plus byproduct weight,
- raw material weight remains the sheet weight.

- [ ] **Step 5: Run focused tests and confirm they fail for the expected reason**

From `/root/workspace/bench15`:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
```

Expected: tests fail because reusable end pieces are still skipped in main BOM scrap rows.

Do not commit the red tests separately.

---

### Task 2: Extract Shared End-Piece Item Creation

**Files:**
- Add: `sheet_cutting_layout/services/end_piece_item_service.py`
- Modify: `sheet_cutting_layout/services/end_piece_bom_service.py`
- Modify: `sheet_cutting_layout/tests/test_end_piece_bom_service.py`

- [ ] **Step 1: Move Item creation helpers into the new shared service**

Move these behaviors out of `end_piece_bom_service.py`:

- deterministic item-code derivation,
- item-code length validation,
- generated Item description,
- Item existence check,
- Item creation with `Kg` stock UOM,
- reciprocal UOM rows,
- raw-material item group and valuation copy,
- finished-item HSN copy,
- insert error handling and logging.

Expose:

```python
def derive_end_piece_item_code(layout: LayoutDocument, row: EndPieceRow) -> str:
	...

def ensure_end_piece_item(layout: LayoutDocument, row: EndPieceRow) -> str:
	...
```

Keep error messages row-specific. `derive_end_piece_item_code()` must be pure and must not create
Item records; `ensure_end_piece_item()` may create records and should be used only from real Frappe
release/end-piece BOM flows.

- [ ] **Step 2: Update end-piece BOM generation to call the shared service**

Replace `_ensure_end_piece_item(layout, row)` with `ensure_end_piece_item(layout, row)`.

Remove duplicated private helpers from `end_piece_bom_service.py` after moving them. Keep BOM-only
helpers such as `_create_end_piece_bom()`, `_company_for_layout()`, and `_persist_generated_links()`
in `end_piece_bom_service.py`.

- [ ] **Step 3: Preserve existing end-piece BOM tests**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
```

Expected after implementation: existing generated Item behavior still passes, including HSN,
valuation, and reciprocal UOM rows.

---

### Task 3: Add Reusable End Pieces to Main BOM Scrap Rows

**Files:**
- Modify: `sheet_cutting_layout/services/bom_service.py`
- Modify: `sheet_cutting_layout/services/release_service.py`

- [ ] **Step 1: Extend the `BomItemRowType` literal**

Add `end_piece_byproduct`:

```python
BomItemRowType = Literal[
	"raw_material",
	"process_scrap",
	"end_piece_scrap",
	"end_piece_byproduct",
]
```

- [ ] **Step 2: Add reusable end-piece detection**

Add a helper next to `_is_scrap_end_piece()`:

```python
def _is_reuse_end_piece(end_piece: EndPieceRow) -> bool:
	return str(getattr(end_piece, "disposition", "") or "").strip().lower() == "reuse"
```

- [ ] **Step 3: Add an end-piece item-code resolver for main BOM rows**

Use `getattr(row, "end_piece_item_code", None)` when already linked. If missing, derive the item
code through the shared service's pure `derive_end_piece_item_code()` helper, or call
`ensure_end_piece_item()` when running in the Frappe release path.

Keep pure `bom_service` tests deterministic by allowing an injected resolver:

```python
EndPieceItemCodeResolver = Callable[[LayoutDocument, EndPieceRow], str]
```

Extend `build_bom_from_layout_row()` with an optional keyword-only resolver. Default to the shared
deterministic resolver for in-memory expected rows, and let `release_service` pass the ensuring
resolver during real release.

- [ ] **Step 4: Append reusable end-piece byproduct rows**

After process scrap and scrap-disposition rows, append:

```python
BomItemRow(
	item_code=end_piece_item_code,
	qty=end_piece.weight_kg,
	row_type="end_piece_byproduct",
)
```

Skip zero or negative weights only if existing validation already rejects them before release. Do
not silently drop invalid reuse rows in release.

- [ ] **Step 5: Persist generated links during release**

When release calls `build_bom_from_layout_row()`, pass a resolver that calls
`ensure_end_piece_item(layout, row)`, sets `row.end_piece_item_code`, and returns the item code.

For submitted layouts, use the existing `db_set` pattern if the in-memory mutation is not enough
to persist child-row links safely. For draft/pre-submit release, normal document save should carry
the row mutation.

---

### Task 4: Add Main BOM Mass-Balance Validation

**Files:**
- Modify: `sheet_cutting_layout/services/bom_service.py`
- Modify: `sheet_cutting_layout/services/validators.py` if save-time audit needs a distinct error.
- Modify: `sheet_cutting_layout/tests/test_bom_service.py`
- Modify: `sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Add a small balance helper**

Add a pure helper to `bom_service.py`:

```python
def expected_main_bom_weight_balance_kg(layout_doc: LayoutDocument) -> float:
	...
```

Calculate:

```text
raw_material_qty - (
	finished_part_quantity * finished_part_net_weight_per_part_kg
	+ total_scrap_qty
)
```

Use `finished_part_row.gross_weight_per_part_kg - finished_part_row.scrap_weight_per_part_kg` as
the net weight when a row-specific net field is not available.

Because `total_scrap_qty` now includes process scrap, scrap-disposition end pieces, and reusable
end-piece byproducts, a balanced BOM should return approximately zero.

- [ ] **Step 2: Validate during expected BOM creation or release validation**

Run the balance check from the release validation path after formulas have been applied. If the
absolute difference exceeds the existing precision/tolerance used by this module, raise a Frappe
validation error that includes:

- raw material weight,
- finished part net weight total,
- total scrap/byproduct weight,
- difference.

- [ ] **Step 3: Keep generated BOM audit aligned**

`expected_bom_consumption_from_layout()` already flows through `build_bom_from_layout()`. Once
byproduct rows are part of that builder, save-time generated BOM audit should expect the same rows.
Add a test that a generated BOM missing the reusable end-piece byproduct row is rejected.

---

### Task 5: Verify and Commit

**Files:**
- All modified implementation and test files.

- [ ] **Step 1: Run focused tests**

From `/root/workspace/bench15`:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
```

- [ ] **Step 2: Run the app suite if the focused tests pass**

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --skip-test-records
```

If site fixtures block the app suite before the target tests run, capture the exact traceback and
use the focused tests as the verified signal.

- [ ] **Step 3: Inspect the diff**

```bash
git diff --check
git diff --stat
git status --short
```

- [ ] **Step 4: Commit implementation**

Use one focused commit:

```bash
git add sheet_cutting_layout/services sheet_cutting_layout/tests
git commit -m "fix: include end pieces in main bom byproducts"
```
