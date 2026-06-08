# App-Created Item UOM and Valuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generated app-created Items get reciprocal `Kg`/`Nos` UOM rows and generated end-piece Items copy per-Kg valuation from their raw material Item.

**Architecture:** Keep the change local to `sheet_cutting_layout/services/end_piece_bom_service.py`, the only production path that creates Items in this app today. Add a small helper that appends reciprocal UOM rows from `stock_uom` and `weight_kg`, then use it from `_ensure_end_piece_item()`. Extend the existing bench-native service tests so they verify behavior through `generate_end_piece_boms()`.

**Tech Stack:** Frappe/ERPNext app, Python service module, bench-native unittest tests via `bench --site ... run-tests`.

---

## File Structure

- Modify `sheet_cutting_layout/services/end_piece_bom_service.py`
  - Responsibility: generate end-piece Items and BOMs.
  - Add `_append_app_created_item_uoms(item, *, stock_uom, weight_kg)` near `_ensure_end_piece_item()`.
  - Add valuation-rate copy in `_ensure_end_piece_item()`.
- Modify `sheet_cutting_layout/tests/test_end_piece_bom_service.py`
  - Responsibility: behavior coverage for generated end-piece Item and BOM creation.
  - Extend fake DB valuation lookups.
  - Update generated Item tests to assert reciprocal UOMs and RM valuation rate.

No migration or backfill files are needed.

---

### Task 1: Add Failing Behavior Tests for UOMs and Valuation

**Files:**
- Modify: `sheet_cutting_layout/tests/test_end_piece_bom_service.py`

- [ ] **Step 1: Extend `FakeDB` to expose raw material valuation rates**

In `FakeDB.__init__`, add `raw_item_valuation_rates` as an input and store it:

```python
class FakeDB:
	def __init__(
		self,
		*,
		existing_items: set[str] | None = None,
		raw_item_groups: dict[str, str] | None = None,
		item_hsn_codes: dict[str, str] | None = None,
		raw_item_valuation_rates: dict[str, float] | None = None,
	) -> None:
		self.existing_items = set(existing_items or set())
		self.raw_item_groups = raw_item_groups or {"RAW-001": "Raw Material"}
		self.item_hsn_codes = item_hsn_codes or {}
		self.raw_item_valuation_rates = raw_item_valuation_rates or {}
```

In `FakeDB.get_value()`, return valuation rates for Item lookups:

```python
	def get_value(self, doctype: str, name: str, fieldname: str) -> object:
		if doctype == "Item" and fieldname == "item_group":
			return self.raw_item_groups.get(name)
		if doctype == "Item" and fieldname == "gst_hsn_code":
			return self.item_hsn_codes.get(name)
		if doctype == "Item" and fieldname == "valuation_rate":
			return self.raw_item_valuation_rates.get(name)
		return None
```

- [ ] **Step 2: Thread valuation rates through `FakeFrappe` and `_install_fakes()`**

Update `FakeFrappe.__init__`:

```python
class FakeFrappe:
	def __init__(
		self,
		*,
		existing_items: set[str] | None = None,
		raw_item_groups: dict[str, str] | None = None,
		item_hsn_codes: dict[str, str] | None = None,
		raw_item_valuation_rates: dict[str, float] | None = None,
	) -> None:
		self.db = FakeDB(
			existing_items=existing_items,
			raw_item_groups=raw_item_groups,
			item_hsn_codes=item_hsn_codes,
			raw_item_valuation_rates=raw_item_valuation_rates,
		)
		self.created_docs: list[FakeDoc] = []
		self.defaults = SimpleNamespace(get_user_default=lambda _key: "")
		self.ValidationError = ValueError
		self._ = lambda message: message
```

Update `TestEndPieceBomService._install_fakes()`:

```python
	def _install_fakes(
		self,
		*,
		existing_items: set[str] | None = None,
		raw_item_groups: dict[str, str] | None = None,
		item_hsn_codes: dict[str, str] | None = None,
		raw_item_valuation_rates: dict[str, float] | None = None,
	) -> FakeFrappe:
		fake_frappe = FakeFrappe(
			existing_items=existing_items,
			raw_item_groups=raw_item_groups,
			item_hsn_codes=item_hsn_codes,
			raw_item_valuation_rates=raw_item_valuation_rates,
		)
```

- [ ] **Step 3: Update the generated end-piece Item test**

Rename `test_generation_creates_missing_item_with_kg_stock_uom` to:

```python
def test_generation_creates_missing_item_with_kg_stock_uom_alternate_nos_and_rm_valuation(self) -> None:
```

Set up the fake DB with RM valuation:

```python
fake_frappe = self._install_fakes(
	raw_item_groups={"RAW-001": "Sheet Steel"},
	item_hsn_codes={"FG01SHR": "7208"},
	raw_item_valuation_rates={"RAW-001": 82.75},
)
```

Replace the final generated Item assertions with:

```python
self.assertEqual(item.item_group, "Sheet Steel")
self.assertEqual(item.gst_hsn_code, "7208")
self.assertEqual(item.valuation_rate, 82.75)
self.assertEqual(item.stock_uom, "Kg")
self.assertEqual(item.is_stock_item, 1)
self.assertEqual(item.disabled, 0)
self.assertEqual(
	item.uoms,
	[
		{"uom": "Kg", "conversion_factor": 1},
		{"uom": "Nos", "conversion_factor": 0.4},
	],
)
```

This uses the default `EndPiece.weight_kg = 2.5`, so `Nos` conversion factor is `1 / 2.5 = 0.4`.

- [ ] **Step 4: Run focused test to verify it fails**

Run from `/root/workspace/bench15`:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service --case TestEndPieceBomService
```

Expected: `FAILED` because the generated Item has no `valuation_rate` and only one UOM row: `{"uom": "Kg", "conversion_factor": 1}`.

- [ ] **Step 5: Commit the failing test**

Do not commit the red test by itself. Keep it staged locally for Task 2.

---

### Task 2: Implement Reciprocal UOM Rows and RM Valuation Copy

**Files:**
- Modify: `sheet_cutting_layout/services/end_piece_bom_service.py`
- Test: `sheet_cutting_layout/tests/test_end_piece_bom_service.py`

- [ ] **Step 1: Add a local helper for app-created Item UOM rows**

Add this helper after `_ensure_end_piece_item()`:

```python
def _append_app_created_item_uoms(item: object, *, stock_uom: str, weight_kg: float) -> None:
	if stock_uom == "Kg":
		item.append("uoms", {"uom": "Kg", "conversion_factor": 1})
		item.append("uoms", {"uom": "Nos", "conversion_factor": 1 / weight_kg})
		return
	if stock_uom == "Nos":
		item.append("uoms", {"uom": "Nos", "conversion_factor": 1})
		item.append("uoms", {"uom": "Kg", "conversion_factor": weight_kg})
		return
	_throw(_("Unsupported stock UOM for app-created Item: {0}").format(stock_uom))
```

Rationale: this keeps reciprocal UOM behavior explicit for app-created Items. Today the service uses `Kg`; the `Nos` branch is included because the approved behavior covers app-created Items in both directions.

- [ ] **Step 2: Copy raw material valuation rate during generated Item creation**

In `_ensure_end_piece_item()`, after setting `item_group`, add:

```python
	item.valuation_rate = _get_value("Item", getattr(layout, "raw_material_item", None), "valuation_rate")
```

The surrounding block should read:

```python
	item.item_code = item_code
	item.item_name = item_code
	item.description = _build_item_description(layout, row)
	item.item_group = _get_value("Item", getattr(layout, "raw_material_item", None), "item_group")
	item.valuation_rate = _get_value("Item", getattr(layout, "raw_material_item", None), "valuation_rate")
	item.gst_hsn_code = _get_value(
		"Item", _clean(getattr(row, "used_for_finished_part", None)), "gst_hsn_code"
	)
```

- [ ] **Step 3: Use the helper instead of appending only the base UOM**

Replace:

```python
	item.stock_uom = "Kg"
	item.is_stock_item = 1
	item.disabled = 0
	item.append("uoms", {"uom": "Kg", "conversion_factor": 1})
```

with:

```python
	item.stock_uom = "Kg"
	item.is_stock_item = 1
	item.disabled = 0
	_append_app_created_item_uoms(item, stock_uom=item.stock_uom, weight_kg=weight_kg)
```

- [ ] **Step 4: Run focused test to verify it passes**

Run from `/root/workspace/bench15`:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service --case TestEndPieceBomService
```

Expected: `Ran 15 tests ... OK` or higher if new tests are added in the same class.

- [ ] **Step 5: Commit**

```bash
git add sheet_cutting_layout/services/end_piece_bom_service.py sheet_cutting_layout/tests/test_end_piece_bom_service.py
git commit -m "fix: set app-created item uoms and valuation"
```

---

### Task 3: Full Verification and PR Update

**Files:**
- No code files expected.
- Update PR #7 body after push if this branch is still attached to PR #7.

- [ ] **Step 1: Run full bench15 app tests**

Run from `/root/workspace/bench15`:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout
```

Expected: all tests pass.

- [ ] **Step 2: Run full bench16 app tests**

Run from `/root/workspace/bench16`:

```bash
bench --site frappe16.localhost run-tests --app sheet_cutting_layout
```

Expected: all tests pass.

- [ ] **Step 3: Run pre-commit**

Run from `/root/workspace/sheet_cutting_layout`:

```bash
PYTHONPATH=/tmp/precommit-runner PRE_COMMIT_HOME=/tmp/precommit-cache npm_config_cache=/tmp/npm-cache python -m pre_commit run --all-files
```

Expected: all hooks pass. If a formatter modifies files, rerun the same command and amend or create a follow-up commit for formatting.

- [ ] **Step 4: Run final diff checks**

Run from `/root/workspace/sheet_cutting_layout`:

```bash
git diff --check
git status --short --branch
```

Expected: no whitespace errors. Status should show the branch ahead only by intentional commits and no unstaged changes.

- [ ] **Step 5: Push branch**

Run from `/root/workspace/sheet_cutting_layout`:

```bash
git push origin codex/end-piece-item-code-design-spec
```

Expected: push succeeds.

- [ ] **Step 6: Update PR body**

If PR #7 still exists for this branch, update its summary to mention:

```text
- Adds reciprocal Kg/Nos alternate UOM rows and copies raw material per-Kg valuation rate for generated app-created end-piece Items.
```

Use the GitHub connector or `gh pr edit` if available.

---

## Self-Review

Spec coverage:

- Reciprocal UOM rows for app-created `Kg` Items: Task 1 test and Task 2 helper.
- Reciprocal UOM rows for app-created `Nos` Items: Task 2 helper includes the branch; no production `Nos` app-created Item path exists today.
- No backfill or unrelated Item mutation: plan has no migration and only touches `_ensure_end_piece_item()`.
- End-piece Item valuation from raw material: Task 1 test and Task 2 valuation copy.
- BOM row stays in `Kg`: existing tests remain, and Task 3 full suite verifies no regression.

Red-flag scan: no incomplete or vague steps remain.

Type consistency: helper uses existing `item.append()` behavior and existing `_throw`, `_`, `_get_value`, and `weight_kg` values already present in `end_piece_bom_service.py`.
