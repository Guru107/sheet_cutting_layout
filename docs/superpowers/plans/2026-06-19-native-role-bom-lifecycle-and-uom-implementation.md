# Native Role, BOM Lifecycle, and Generated UOM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the custom workflow role with ERPNext native `Projects Manager`, remove the custom BOM app-control flag in favor of native link ownership plus explicit cancel sequencing, ensure every app-created Item carries the required alternate UOM using ERPNext-native conversion semantics, and make strip thickness read-only/mirrored from material thickness.

**Architecture:** Keep the change narrow. Update workflow/fixture role references first, then remove the BOM app-control path while preserving explicit layout-driven BOM cancellation order, then normalize app-created Item UOM rows through one shared helper, and finally lock strip thickness at the UI/validation edge. Every task stays bench-testable on its own.

**Tech Stack:** Frappe v15 / ERPNext (DocType JSON, workflow fixtures, Python services), bench-native tests, `pre-commit`.

**Spec:** `docs/superpowers/specs/2026-06-19-native-project-role-bom-lifecycle-and-uom-design.md`

**Test commands (bench-native):**
- Workflow + controller coverage: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_sheet_cutting_layout_controller`
- Release/BOM lifecycle: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service`
- End-piece BOM flow: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service`
- Validators/UOM behavior: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators`
- Export/recursive smoke where relevant: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_download_sheet_cutting_layout_recursion`
- Final repo check: `pre-commit run --all-files`

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `sheet_cutting_layout/fixtures/workflow.json` | Replace custom Project Manager role with native `Projects Manager` | **Modify** (Task 1) |
| `sheet_cutting_layout/services/workflow.py` | Keep workflow constants aligned if tests/helpers assert role-driven behavior | **Modify if needed** (Task 1) |
| `sheet_cutting_layout/tests/test_sheet_cutting_layout_controller.py` | Workflow/permission fixture coverage | **Modify** (Task 1) |
| `sheet_cutting_layout/overrides/bom.py` | Remove app-control flag logic; keep only native-field-based restrictions if still needed | **Modify** (Task 2) |
| `sheet_cutting_layout/services/release_service.py` | Cancel generated BOMs through normal flow without app-control flag | **Modify** (Task 2) |
| `sheet_cutting_layout/services/end_piece_bom_service.py` | Stop marking generated BOMs app-controlled | **Modify** (Task 2) |
| `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py` | Keep cancel/trash order native-link-safe | **Modify** (Task 2) |
| `sheet_cutting_layout/tests/test_release_service.py` | Derived BOM cancel/deactivate coverage | **Modify** (Task 2) |
| `sheet_cutting_layout/tests/test_end_piece_bom_service.py` | Generated end-piece BOM lifecycle coverage | **Modify** (Task 2) |
| `sheet_cutting_layout/services/end_piece_item_service.py` | Shared app-created Item alternate UOM enforcement for the only current app-created Item path | **Modify** (Task 3) |
| `sheet_cutting_layout/tests/test_end_piece_bom_service.py` | End-piece Item alternate UOM coverage | **Modify** (Task 3) |
| `sheet_cutting_layout/tests/test_validators.py` | Conversion factor semantics assertions where cheapest | **Modify** (Task 3) |
| `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json` | Make `strip_thickness_mm` read-only | **Modify** (Task 4) |
| `sheet_cutting_layout/services/validators.py` | Mirror strip thickness from sheet thickness before formulas | **Modify** (Task 4) |
| `sheet_cutting_layout/tests/test_validators.py` | Strip-thickness mirror/read-only behavior coverage | **Modify** (Task 4) |

---

## Task 1: Replace the custom workflow role with ERPNext native `Projects Manager`

**Files:**
- Modify: `sheet_cutting_layout/fixtures/workflow.json`
- Modify: `sheet_cutting_layout/tests/test_sheet_cutting_layout_controller.py`
- Test: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_sheet_cutting_layout_controller`

- [ ] **Step 1: Find the current role references**

Run:

```bash
rg -n "Project Manager|Projects Manager" sheet_cutting_layout
```

Expected: exact workflow/fixture/test locations that still reference the custom role.

- [ ] **Step 2: Write the failing test/update the existing expectation**

In `sheet_cutting_layout/tests/test_sheet_cutting_layout_controller.py`, change the workflow-role expectation to the native role name. If there is no direct role assertion yet, add one in the workflow-access test area:

```python
		self.assertIn("Projects Manager", role_names)
		self.assertNotIn("Project Manager", role_names)
```

- [ ] **Step 3: Run the targeted test and verify it fails**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_sheet_cutting_layout_controller
```

Expected: FAIL because fixtures/workflow still reference the old role name.

- [ ] **Step 4: Update the workflow/fixture role name**

Replace app-owned role references from the custom value to the native value:

```json
"role": "Projects Manager"
```

Do this only in files owned by this app; do not add compatibility aliases.

- [ ] **Step 5: Re-run the targeted test and verify it passes**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_sheet_cutting_layout_controller
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add sheet_cutting_layout/fixtures/workflow.json sheet_cutting_layout/tests/test_sheet_cutting_layout_controller.py
git commit -m "refactor: use native Projects Manager role"
```

---

## Task 2: Remove the BOM app-control flag and keep cancel/delete working through native links

**Files:**
- Modify: `sheet_cutting_layout/overrides/bom.py`
- Modify: `sheet_cutting_layout/services/release_service.py`
- Modify: `sheet_cutting_layout/services/end_piece_bom_service.py`
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`
- Modify: `sheet_cutting_layout/tests/test_release_service.py`
- Modify: `sheet_cutting_layout/tests/test_end_piece_bom_service.py`

- [ ] **Step 1: Write the failing lifecycle tests**

Add one release-service test that proves layout retirement/cancel no longer depends on the flag and instead cancels linked BOMs in order:

```python
	def test_retire_layout_cancels_linked_boms_without_app_control_flag(self) -> None:
		first = SimpleNamespace(name="BOM-1", cancel=Mock(), docstatus=1)
		second = SimpleNamespace(name="BOM-2", cancel=Mock(), docstatus=1)
		with patch("frappe.get_doc", side_effect=[first, second]):
			retire_layout(SimpleNamespace(generated_bom="BOM-1", twin_generated_bom="BOM-2", end_pieces=[]))
		first.cancel.assert_called_once_with()
		second.cancel.assert_called_once_with()
```

Add one BOM-override test that proves a manually-cancelled linked generated BOM is blocked from the BOM side using only native fields:

```python
	def test_validate_shearing_bom_source_blocks_manual_cancel_for_linked_layout_bom(self) -> None:
		doc = SimpleNamespace(custom_operation="Shearing", sheet_cutting_layout="SCL-001")
		with self.assertRaisesRegex(Exception, "Sheet Cutting Layout"):
			validate_shearing_bom_source(doc, "before_cancel")
```

- [ ] **Step 2: Run the lifecycle modules and verify failure**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
```

Expected: FAIL because current code still expects `mark_bom_app_controlled()` and the old override path.

- [ ] **Step 3: Remove the app-control flag from BOM override code**

In `sheet_cutting_layout/overrides/bom.py`, delete the custom flag constant and helper:

```python
APP_CONTROLLED_BOM_UPDATE_FLAG = "sheet_cutting_layout_allow_bom_update"

def _is_app_controlled_bom_update(doc: object) -> bool:
	...

def mark_bom_app_controlled(doc: object) -> None:
	...
```

Keep `validate_shearing_bom_source()` field-based only:

```python
def validate_shearing_bom_source(doc: object, method: str | None = None) -> None:
	if getattr(doc, "custom_operation", None) != "Shearing":
		return
	layout_name = str(getattr(doc, "sheet_cutting_layout", "") or "").strip()
	if not layout_name:
		return
	if method == "before_cancel":
		frappe.throw(
			_("This Shearing BOM is generated from a Sheet Cutting Layout. Use the Sheet Cutting Layout workflow instead of cancelling or amending this BOM.")
		)
	if method == "before_insert":
		frappe.throw(_("Create a Sheet Cutting Layout to generate a Shearing BOM."))
```

- [ ] **Step 4: Remove flag writes from generation/save paths**

Delete calls like:

```python
mark_bom_app_controlled(bom_doc)
```

from:

```python
sheet_cutting_layout/services/release_service.py
sheet_cutting_layout/services/end_piece_bom_service.py
```

Also delete any save-path flag-setting in `_save_bom_records()`.

- [ ] **Step 5: Keep explicit BOM cancel sequencing on layout cancel**

In the layout/release lifecycle, gather BOMs linked by `sheet_cutting_layout` and cancel them before the layout cancel continues. The implementation should stay boring:

```python
def retire_layout(layout: object) -> None:
	for bom_name in _layout_bom_names(layout):
		bom_doc = frappe.get_doc("BOM", bom_name)
		if _is_cancelled_document(bom_doc):
			continue
		bom_doc.cancel()
```

If the current code has fallback deactivation for link-exists cases, keep only the minimum that is still required after native sequencing is applied.

- [ ] **Step 6: Re-run the lifecycle modules and verify they pass**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add sheet_cutting_layout/overrides/bom.py sheet_cutting_layout/services/release_service.py sheet_cutting_layout/services/end_piece_bom_service.py sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py sheet_cutting_layout/tests/test_release_service.py sheet_cutting_layout/tests/test_end_piece_bom_service.py
git commit -m "refactor: use native links for generated bom lifecycle"
```

---

## Task 3: Normalize alternate UOM rows for every app-created Item

**Files:**
- Modify: `sheet_cutting_layout/services/end_piece_item_service.py`
- Modify: `sheet_cutting_layout/tests/test_end_piece_bom_service.py`
- Modify: `sheet_cutting_layout/tests/test_validators.py` if it is the cheapest place to assert ERPNext conversion semantics

- [ ] **Step 1: Verify ERPNext conversion-factor direction and confirm current app-created Item scope**

Run:

```bash
rg -n "conversion_factor" /root/workspace/bench15/apps/erpnext /root/workspace/bench15/apps/frappe | sed -n '1,80p'
rg -n 'new_doc\("Item"\)|insert\(ignore_permissions=True\)' sheet_cutting_layout/services sheet_cutting_layout/sheet_cutting_layout -g '*.py'
```

Expected:

1. concrete ERPNext usage showing how alternate UOM rows are interpreted relative to stock UOM
1. repo proof that `sheet_cutting_layout/services/end_piece_item_service.py` is the only current app-created Item path

- [ ] **Step 2: Write the failing tests**

In `sheet_cutting_layout/tests/test_end_piece_bom_service.py`, add explicit assertions for the end-piece path using ERPNext-native semantics:

```python
		self.assertIn(("Kg", 1.0), uom_rows)
		self.assertIn(("Nos", expected_nos_factor), uom_rows)
```

Add one repair-on-touch test:

```python
	def test_existing_generated_item_repairs_missing_alternate_uom(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		fake_frappe = self._install_fakes(
			existing_items={existing_code},
			raw_item_valuation_rates={"RAW-001": 82.75, existing_code: 82.75},
		)
		existing_item = FakeDoc("Item")
		existing_item.name = existing_code
		existing_item.stock_uom = "Kg"
		existing_item.uoms = [{"uom": "Kg", "conversion_factor": 1}]
		with patch.object(fake_frappe, "get_doc", return_value=existing_item):
			self.item_service.ensure_end_piece_item(Layout(), EndPiece())
		self.assertIn({"uom": "Nos", "conversion_factor": 2.5}, existing_item.uoms)
		self.assertEqual(existing_item.save_calls, [{"ignore_permissions": True}])
```

- [ ] **Step 3: Run the targeted module and verify failure**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
```

Expected: FAIL because the current helper only covers end-piece insert and does not yet repair missing alternate rows using ERPNext-native semantics.

- [ ] **Step 4: Add one shared helper and use it from every app-created Item path**

In `sheet_cutting_layout/services/end_piece_item_service.py`, add the smallest helper:

```python
def _ensure_app_created_item_uoms(item: object, *, stock_uom: str, alternate_uom: str, factor: float) -> None:
	if factor <= 0:
		_throw(_("Alternate UOM conversion factor must be greater than zero"))
	# keep one stock row at factor 1
	# add or repair exactly one alternate row
```

Use the ERPNext-native conversion direction discovered in Step 1. Do not invent a new interpretation. Because Step 1 proves `end_piece_item_service.py` is the only current Item-creation path owned by this app, wire the helper there now and keep it reusable for future app-created finished Items without adding speculative code paths.

For end-piece creation, call it with:

```python
_ensure_app_created_item_uoms(
	item,
	stock_uom="Kg",
	alternate_uom="Nos",
	factor=weight_kg_factor,
)
```

- [ ] **Step 5: Re-run the targeted tests and verify they pass**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add sheet_cutting_layout/services/end_piece_item_service.py sheet_cutting_layout/tests/test_end_piece_bom_service.py sheet_cutting_layout/tests/test_validators.py
git commit -m "feat: normalize alternate uoms for generated items"
```

---

## Task 4: Make strip thickness read-only and mirror it from material thickness

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json`
- Modify: `sheet_cutting_layout/services/validators.py`
- Modify: `sheet_cutting_layout/tests/test_validators.py`

- [ ] **Step 1: Write the failing tests**

Add one metadata test:

```python
	def test_strip_thickness_field_is_read_only(self) -> None:
		field = frappe.get_meta("Sheet Cutting Layout").get_field("strip_thickness_mm")
		self.assertEqual(field.read_only, 1)
```

Add one behavior test in `sheet_cutting_layout/tests/test_validators.py`:

```python
	def test_validation_mirrors_strip_thickness_from_sheet_thickness(self) -> None:
		layout = Layout(sheet_thickness_mm=2, strip_thickness_mm=99)
		self.validators.validate_sheet_cutting_layout(layout)
		self.assertEqual(layout.strip_thickness_mm, 2)
```

- [ ] **Step 2: Run the validator module and verify failure**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
```

Expected: FAIL because the field is editable and the validator path does not yet force the mirror.

- [ ] **Step 3: Make the field read-only in the doctype**

In `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json`, update the existing field definition:

```json
"fieldname": "strip_thickness_mm",
"read_only": 1
```

- [ ] **Step 4: Mirror the value in validation before strip formulas run**

In `sheet_cutting_layout/services/validators.py`, near the top of `validate_sheet_cutting_layout()`, add the minimal mirror:

```python
	if getattr(layout, "sheet_thickness_mm", None) is not None:
		layout.strip_thickness_mm = getattr(layout, "sheet_thickness_mm", None)
```

Place it before `apply_strip_weight_formula(layout)`.

- [ ] **Step 5: Re-run the validator module and verify it passes**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json sheet_cutting_layout/services/validators.py sheet_cutting_layout/tests/test_validators.py
git commit -m "feat: lock strip thickness to material thickness"
```

---

## Task 5: Final verification and cleanup

**Files:**
- Modify: any touched files from Tasks 1-4 only if verification exposes regressions

- [ ] **Step 1: Run the focused regression set**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_sheet_cutting_layout_controller
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_download_sheet_cutting_layout_recursion
```

Expected: all modules PASS.

- [ ] **Step 2: Run formatting/lint hooks**

Run:

```bash
pre-commit run --all-files
```

Expected: PASS. If `ruff-format` changes files, stage them and re-run once.

- [ ] **Step 3: Review the final diff**

Run:

```bash
git diff --stat develop...HEAD
git status --short
```

Expected: only intended files changed, no stray edits.

- [ ] **Step 4: Final commit if verification tooling reformats files**

```bash
git add <formatted-files>
git commit -m "style: apply final formatting"
```

## Self-review against spec

Spec coverage:

1. Native `Projects Manager` role replacement is covered in Task 1.
1. Removal of `APP_CONTROLLED_BOM_UPDATE_FLAG` and native-link-driven BOM lifecycle is covered in Task 2.
1. Alternate UOM rows for all app-created Items using ERPNext-native conversion semantics is covered in Task 3.
1. Strip-thickness read-only/mirror behavior is covered in Task 4.
1. Focused verification and repo hygiene are covered in Task 5.

Placeholder scan:

1. No `TBD`, `TODO`, or implicit “handle later” steps remain.

Type consistency:

1. The plan uses the existing names `sheet_cutting_layout`, `generated_bom`, `generated_end_piece_bom`, `strip_thickness_mm`, and `sheet_thickness_mm` consistently.
1. The UOM helper is defined once and reused; no alternate helper names are introduced later in the plan.
