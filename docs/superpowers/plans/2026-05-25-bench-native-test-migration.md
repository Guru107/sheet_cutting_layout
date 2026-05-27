# Bench-Native Test Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the Sheet Cutting Layout test suite from pytest execution/style to Frappe bench-native `unittest` tests while keeping Hypothesis coverage and cleaning up test data.

**Architecture:** Replace the pytest bridge with directly discoverable `FrappeTestCase` classes. Add a small test-support layer for deterministic factories, cleanup registration, and shared assertions, then migrate modules in batches from low-risk isolated tests to database-backed Frappe/ERPNext integration tests.

**Tech Stack:** Frappe/ERPNext 15, `frappe.tests.utils.FrappeTestCase`, Python `unittest`, `unittest.mock`, Hypothesis, bench test runner.

---

## Reference Documents

- Spec: `docs/superpowers/specs/2026-05-25-bench-native-test-migration-design.md`
- Frappe test base: `/Users/gurudattkulkarni/Workspace/bench15/apps/frappe/frappe/tests/utils.py`
- Frappe runner: `/Users/gurudattkulkarni/Workspace/bench15/apps/frappe/frappe/test_runner.py`

## File Structure

Create:

- `sheet_cutting_layout/tests/base.py`
  - Shared `SheetCuttingLayoutTestCase(FrappeTestCase)`.
  - Registers cleanup fallback for focused module runs.
  - Provides assertion helpers such as `assertFloatAlmostEqual`.

- `sheet_cutting_layout/tests/factories.py`
  - Deterministic factory helpers for Items, Projects, BOMs, and Sheet Cutting Layout records.
  - Central cleanup registry.
  - `atexit` cleanup registration.
  - Conservative prefix sweep for stale test records.

Modify:

- `sheet_cutting_layout/tests/test_cypress_config.py`
- `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`
- `sheet_cutting_layout/tests/test_bom_service.py`
- `sheet_cutting_layout/tests/test_property_layout_invariants.py`
- `sheet_cutting_layout/tests/test_validators.py`
- `sheet_cutting_layout/tests/test_bom_overrides.py`
- `sheet_cutting_layout/tests/test_end_piece_bom_service.py`
- `sheet_cutting_layout/tests/test_release_service.py`
- `sheet_cutting_layout/tests/test_model_workflow_state_machine.py`
- `sheet_cutting_layout/services/release_service.py`
- `README.md`
- `pyproject.toml`

Delete:

- `sheet_cutting_layout/tests/bench_pytest_bridge.py`
- `sheet_cutting_layout/tests/test_bench_pytest_bridge.py`

Do not edit historical docs under `docs/superpowers/specs/*` or `docs/superpowers/plans/*` just because they mention pytest.

## Conversion Patterns

Use these replacements consistently:

```python
# pytest.raises(...)
with self.assertRaisesRegex(frappe.ValidationError, "message"):
    doc.save()

# pytest.approx(...)
self.assertAlmostEqual(actual, expected, places=6)

# pytest.mark.parametrize(...)
for value in values:
    with self.subTest(value=value):
        self.assertIsNotNone(value)

# monkeypatch.setattr(...)
with patch.object(module, "name", replacement):
    self.assertIs(module.name, replacement)

# pytest.fail(...)
self.fail("message")
```

For Hypothesis property tests:

```python
from frappe.tests.utils import FrappeTestCase
from hypothesis import given, settings


class TestBomInvariants(FrappeTestCase):
    @given(layout_case_strategy())
    @settings(max_examples=40, derandomize=True)
    def test_bom_invariants_hold_for_random_valid_layouts(self, layout_case):
        self.assertGreater(layout_case.layout.weight_per_sheet_kg, 0)
```

For Hypothesis state tests:

```python
from frappe.tests.utils import FrappeTestCase
from hypothesis.stateful import run_state_machine_as_test


class TestWorkflowStateMachine(FrappeTestCase):
    def test_state_machine_never_reaches_released_without_purchase_and_mr(self):
        run_state_machine_as_test(WorkflowStateMachine)
```

## Task 1: Add Bench-Native Test Support

**Files:**

- Create: `sheet_cutting_layout/tests/base.py`
- Create: `sheet_cutting_layout/tests/factories.py`
- Test with: `sheet_cutting_layout/tests/test_cypress_config.py`

- [ ] **Step 1: Create the shared test base**

Create `sheet_cutting_layout/tests/base.py`:

```python
from __future__ import annotations

from frappe.tests.utils import FrappeTestCase

from sheet_cutting_layout.tests.factories import cleanup_test_records


class SheetCuttingLayoutTestCase(FrappeTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.addClassCleanup(cleanup_test_records)

    def assertFloatAlmostEqual(self, actual: float, expected: float, places: int = 6) -> None:
        self.assertAlmostEqual(float(actual), float(expected), places=places)
```

- [ ] **Step 2: Create the cleanup registry skeleton**

Create `sheet_cutting_layout/tests/factories.py` with:

```python
from __future__ import annotations

import atexit
from collections import defaultdict
from contextlib import suppress

import frappe

TEST_PREFIX = "SCL-TEST-"
ITEM_CODE_PREFIX = "SCLTEST"
_created_docs: dict[str, set[str]] = defaultdict(set)
_cleanup_registered = False


def register_test_doc(doctype: str, name: str | None) -> None:
    if name:
        _created_docs[doctype].add(name)


def _ensure_connection() -> bool:
    site = getattr(frappe.local, "site", None)
    if not site:
        return False
    if not getattr(frappe.local, "db", None):
        frappe.connect(site=site)
    return True


def cleanup_test_records() -> None:
    if not _ensure_connection():
        return
    for doctype in cleanup_order():
        for name in sorted(_created_docs.get(doctype, set()), reverse=True):
            delete_if_exists(doctype, name)
        for name in get_prefixed_records(doctype):
            delete_if_exists(doctype, name)
    frappe.db.commit()


def cleanup_order() -> list[str]:
    return [
        "BOM",
        "Sheet Cutting Layout",
        "Project",
        "Item",
        "Item Group",
        "UOM",
    ]


def delete_if_exists(doctype: str, name: str) -> None:
    if doctype == "Item" and not name.startswith(ITEM_CODE_PREFIX):
        return
    if doctype in {"Project", "Item Group", "UOM"} and not name.startswith(TEST_PREFIX):
        return
    if frappe.db.exists(doctype, name):
        try:
            frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
        except Exception as exc:
            print(f"Skipped cleanup for {doctype} {name}: {exc}")


def get_prefixed_records(doctype: str) -> list[str]:
    if not frappe.db.table_exists(doctype):
        return []
    prefix = ITEM_CODE_PREFIX if doctype == "Item" else TEST_PREFIX
    return frappe.get_all(doctype, filters={"name": ["like", f"{prefix}%"]}, pluck="name")


def register_cleanup() -> None:
    global _cleanup_registered
    if not _cleanup_registered:
        atexit.register(cleanup_test_records)
        _cleanup_registered = True


register_cleanup()
```

Do not add domain factories in this step. Task 3 adds them after the import and cleanup skeleton is
verified.

- [ ] **Step 3: Verify support files import in bench**

Run from `/Users/gurudattkulkarni/Workspace/bench16`:

```bash
source .venv/bin/activate
bench --site frappe16.localhost execute sheet_cutting_layout.tests.factories.cleanup_order
```

Expected: command exits successfully and prints the cleanup order.

- [ ] **Step 4: Commit foundation**

```bash
git add sheet_cutting_layout/tests/base.py sheet_cutting_layout/tests/factories.py
git commit -m "test: add bench native test support"
```

## Task 2: Convert Low-Risk Source and Config Tests

**Files:**

- Modify: `sheet_cutting_layout/tests/test_cypress_config.py`
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`

- [ ] **Step 1: Convert `test_cypress_config.py` to a class**

Replace function-level pytest style with:

```python
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


class TestCypressConfig(SheetCuttingLayoutTestCase):
    def test_cypress_defaults_target_local_bench_and_administrator_password(self):
        config_text = CYPRESS_CONFIG.read_text(encoding="utf-8")
        self.assertIn("localhost", config_text)

    def test_cypress_seed_items_include_hsn_code_for_india_compliance(self):
        seed_text = CYPRESS_SEED.read_text(encoding="utf-8")
        self.assertIn("gst_hsn_code", seed_text)
```

Keep the existing module's actual source assertions. The snippet above shows the class shape only;
do not introduce new path constants unless the current module already has equivalent constants.

- [ ] **Step 2: Run the converted config module through bench**

Run from `/Users/gurudattkulkarni/Workspace/bench16`:

```bash
source .venv/bin/activate
bench --site frappe16.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_cypress_config
```

Expected: 2 tests pass.

- [ ] **Step 3: Convert the DocType source-contract module**

Wrap tests in `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py` inside classes such as:

```python
class TestSheetCuttingLayoutMetadata(SheetCuttingLayoutTestCase):
    def test_sheet_cutting_layout_doctypes_define_normalized_model(self):
        self.assertEqual(sheet_layout_json["doctype"], "DocType")


class TestSheetCuttingLayoutClientScript(SheetCuttingLayoutTestCase):
    def test_client_has_no_sheet_layout_canvas_dependency(self):
        self.assertNotIn("SheetLayoutCanvas", client_script)
```

Use direct `self.assertIn`, `self.assertNotIn`, `self.assertEqual`, and `self.assertTrue` calls.
Move the current assertions into appropriately named methods; the snippet names are illustrative and
should not replace existing assertion coverage. Keep source-contract tests that inspect JSON and JS
files. Do not add browser tests in this migration.

- [ ] **Step 4: Run the DocType test module**

Run:

```bash
bench --site frappe16.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout
```

Expected: converted tests pass.

- [ ] **Step 5: Commit low-risk conversion**

```bash
git add sheet_cutting_layout/tests/test_cypress_config.py sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py
git commit -m "test: convert source contract tests to frappe unittest"
```

## Task 3: Add Real-Record Factories

**Files:**

- Modify: `sheet_cutting_layout/tests/factories.py`
- Test with: `sheet_cutting_layout/tests/test_validators.py`

- [ ] **Step 1: Add item and project factories**

Extend `factories.py` with helpers:

```python
def ensure_uom(name: str = "Kg") -> str:
    if not frappe.db.exists("UOM", name):
        doc = frappe.get_doc({"doctype": "UOM", "uom_name": name, "name": name})
        doc.insert(ignore_permissions=True)
        register_test_doc("UOM", doc.name)
    return name


def ensure_item_group(name: str = f"{TEST_PREFIX}Item Group") -> str:
    if not frappe.db.exists("Item Group", name):
        doc = frappe.get_doc(
            {
                "doctype": "Item Group",
                "item_group_name": name,
                "parent_item_group": "All Item Groups",
                "is_group": 0,
            }
        )
        doc.insert(ignore_permissions=True)
        register_test_doc("Item Group", doc.name)
    return name


def ensure_item(item_code: str, *, item_name: str | None = None, item_group: str | None = None) -> str:
    ensure_uom("Kg")
    item_group = item_group or ensure_item_group()
    if not frappe.db.exists("Item", item_code):
        doc = frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": item_code,
                "item_name": item_name or item_code,
                "item_group": item_group,
                "stock_uom": "Kg",
                "is_stock_item": 1,
            }
        )
        doc.insert(ignore_permissions=True)
        register_test_doc("Item", doc.name)
    return item_code


def ensure_project(name: str = f"{TEST_PREFIX}PROJECT") -> str:
    if not frappe.db.exists("Project", name):
        doc = frappe.get_doc({"doctype": "Project", "project_name": name, "name": name})
        doc.insert(ignore_permissions=True)
        register_test_doc("Project", doc.name)
    return name
```

When a helper creates records whose naming is controlled by ERPNext, such as `BOM`, register the
actual `doc.name` immediately after insert or submit. Do not rely on the reserved prefix for those
records.

Adjust fields if bench reports mandatory field differences. Keep helper names deterministic.

- [ ] **Step 2: Add Sheet Cutting Layout factory**

Add:

```python
def make_sheet_cutting_layout(name: str = f"{TEST_PREFIX}SCL-001", **overrides):
    raw_material = ensure_item(f"{ITEM_CODE_PREFIX}RM001")
    process_scrap = ensure_item(f"{ITEM_CODE_PREFIX}SCRAP")
    finished_part = ensure_item(f"{ITEM_CODE_PREFIX}FG001SHR")
    project = ensure_project()

    data = {
        "doctype": "Sheet Cutting Layout",
        "layout_code": name,
        "project": project,
        "raw_material_item": raw_material,
        "process_scrap_item": process_scrap,
        "sheet_thickness_mm": 1.6,
        "sheet_width_mm": 1250,
        "sheet_length_mm": 2500,
        "strip_thickness_mm": 1.6,
        "strip_width_mm": 1250,
        "strip_length_mm": 211,
        "parts_per_strip": 7,
        "no_of_strips": 11,
        "finished_parts": [
            {
                "finished_part_item": finished_part,
                "net_weight_per_part_kg": 0.289,
            }
        ],
        "end_pieces": [
            {
                "disposition": "Scrap",
                "scrap_item": process_scrap,
                "width_mm": 1250,
                "length_mm": 179,
                "qty_per_sheet": 1,
            }
        ],
    }
    data.update(overrides)
    doc = frappe.get_doc(data)
    doc.insert(ignore_permissions=True)
    register_test_doc("Sheet Cutting Layout", doc.name)
    return doc
```

Expected refinement: if naming series blocks explicit names, rely on `layout_code` plus generated `doc.name`, then register `doc.name`.

- [ ] **Step 3: Add a small direct factory smoke test**

In `test_validators.py`, after converting the file in Task 4, include one smoke test:

```python
class TestFactories(SheetCuttingLayoutTestCase):
    def test_layout_factory_creates_valid_document(self):
        doc = make_sheet_cutting_layout(f"{TEST_PREFIX}FACTORY-SMOKE")
        self.assertEqual(doc.doctype, "Sheet Cutting Layout")
        self.assertGreater(doc.weight_per_sheet_kg, 0)
```

- [ ] **Step 4: Run a focused module once Task 4 conversion starts**

Do not run before `test_validators.py` is converted. This task is complete when factories import cleanly and are used by converted tests.

- [ ] **Step 5: Commit factories**

```bash
git add sheet_cutting_layout/tests/factories.py
git commit -m "test: add frappe document factories"
```

## Task 4: Convert Validator Tests to FrappeTestCase

**Files:**

- Modify: `sheet_cutting_layout/tests/test_validators.py`
- Modify as needed: `sheet_cutting_layout/tests/factories.py`

- [ ] **Step 1: Convert imports and class structure**

Remove `pytest`. Add:

```python
from unittest.mock import patch

import frappe

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase
from sheet_cutting_layout.tests.factories import ITEM_CODE_PREFIX, TEST_PREFIX, ensure_item, make_sheet_cutting_layout
```

Group tests into:

```python
class TestSheetCuttingLayoutValidation(SheetCuttingLayoutTestCase):
    def test_finished_part_item_must_end_with_shr_and_be_alnum(self):
        invalid_item = ensure_item(f"{ITEM_CODE_PREFIX}INVALID")
        with self.assertRaisesRegex(frappe.ValidationError, "end with SHR"):
            make_sheet_cutting_layout(
                f"{TEST_PREFIX}BAD-FG",
                finished_parts=[{"finished_part_item": invalid_item, "net_weight_per_part_kg": 0.289}],
            )


class TestSheetCuttingLayoutControllerMethods(SheetCuttingLayoutTestCase):
    def test_controller_preview_end_piece_boms_delegates(self):
        doc = make_sheet_cutting_layout(f"{TEST_PREFIX}CTRL-PREVIEW")
        self.assertEqual(doc.doctype, "Sheet Cutting Layout")
```

- [ ] **Step 2: Convert direct validation error tests**

For rules such as invalid finished part item, negative weights, missing scrap item, and consumption mismatch, prefer:

```python
invalid_item = ensure_item(f"{ITEM_CODE_PREFIX}INVALID")
with self.assertRaisesRegex(frappe.ValidationError, "exact message fragment"):
    make_sheet_cutting_layout(
        f"{TEST_PREFIX}INVALID-FINISHED-PART",
        finished_parts=[{"finished_part_item": invalid_item, "net_weight_per_part_kg": 0.289}],
    )
```

Use direct service calls only for pure helpers where document setup makes the test less clear.
For invalid Link-field business rules, create the linked Item first if needed so Frappe link
validation does not fail before the app's custom validation runs.

- [ ] **Step 3: Convert parameterized cases to `subTest`**

Example:

```python
for qty_per_sheet in [0, -1]:
    with self.subTest(qty_per_sheet=qty_per_sheet):
        with self.assertRaisesRegex(frappe.ValidationError, "End piece quantity"):
            make_sheet_cutting_layout(
                f"{TEST_PREFIX}BAD-END-QTY-{abs(qty_per_sheet)}",
                end_pieces=[
                    {
                        "disposition": "Scrap",
                        "scrap_item": ensure_item(f"{ITEM_CODE_PREFIX}SCRAP"),
                        "width_mm": 1250,
                        "length_mm": 179,
                        "qty_per_sheet": qty_per_sheet,
                    }
                ],
            )
```

- [ ] **Step 4: Convert monkeypatch controller tests to `patch`**

Example:

```python
with patch.object(sheet_cutting_layout, "preview_end_piece_boms", fake_preview):
    result = doc.preview_end_piece_boms()
```

Keep these isolated because they verify controller delegation and permission seams.

- [ ] **Step 5: Run validators through bench**

Run from bench16:

```bash
bench --site frappe16.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
```

Expected: all converted validator tests pass. If failures reveal missing mandatory fields, update factories rather than hardcoding setup in individual tests.

- [ ] **Step 6: Commit validators conversion**

```bash
git add sheet_cutting_layout/tests/test_validators.py sheet_cutting_layout/tests/factories.py
git commit -m "test: convert layout validators to frappe tests"
```

## Task 5: Convert Pure BOM and Property Tests

**Files:**

- Modify: `sheet_cutting_layout/tests/test_bom_service.py`
- Modify: `sheet_cutting_layout/tests/test_property_layout_invariants.py`

- [ ] **Step 1: Convert `test_bom_service.py`**

Wrap pure service tests in:

```python
class TestBomService(SheetCuttingLayoutTestCase):
    def test_generated_bom_uses_parts_per_sheet_quantity_and_sheet_weight_raw_qty(self):
        bom = generate_bom_for_finished_part(layout, finished_part)
        self.assertAlmostEqual(bom.items[0].qty, layout.weight_per_sheet_kg, places=6)
```

Replace:

- `pytest.approx` with `self.assertAlmostEqual`
- `pytest.raises` with `self.assertRaisesRegex`
- `pytest.mark.parametrize` with `subTest`
- `pytest.fail` with `self.fail`

Keep these mostly isolated because `generate_bom_for_finished_part` is data-shaping logic.

- [ ] **Step 2: Run BOM service module**

```bash
bench --site frappe16.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_service
```

Expected: module passes.

- [ ] **Step 3: Convert property tests**

In `test_property_layout_invariants.py`, remove `pytest`, keep Hypothesis imports, and wrap the property in:

```python
class TestBomPropertyInvariants(SheetCuttingLayoutTestCase):
    @given(layout_case_strategy())
    @settings(max_examples=40, derandomize=True)
    def test_bom_invariants_hold_for_random_valid_layouts(self, layout_case):
        bom = generate_bom_for_finished_part(layout_case.layout, layout_case.finished_part)
        self.assertAlmostEqual(
            _sum_bom_qty(bom.items, "raw_material"),
            layout_case.layout.weight_per_sheet_kg,
            places=6,
        )
```

Use `self.assertAlmostEqual(actual, expected, places=6)` for approximate checks.

- [ ] **Step 4: Run property module**

```bash
bench --site frappe16.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_property_layout_invariants
```

Expected: property tests pass and runtime remains acceptable.

- [ ] **Step 5: Commit BOM/property conversion**

```bash
git add sheet_cutting_layout/tests/test_bom_service.py sheet_cutting_layout/tests/test_property_layout_invariants.py
git commit -m "test: convert bom service and property tests"
```

## Task 6: Convert End-Piece BOM Integration Tests

**Files:**

- Modify: `sheet_cutting_layout/tests/test_end_piece_bom_service.py`
- Modify as needed: `sheet_cutting_layout/tests/factories.py`

- [ ] **Step 1: Replace fake-heavy setup with real records for happy paths**

Use factories for:

- raw material Item
- process scrap Item
- finished part Item
- reusable end-piece Item
- released Sheet Cutting Layout document

Add `make_released_layout_with_reuse_end_piece(name: str)` to `factories.py`. It should create a
valid layout with a reusable end-piece row, move the document to a released state using the app's
supported workflow/release helpers where practical, register the document, and return it.

Expected real-record test examples:

```python
class TestEndPieceBomService(SheetCuttingLayoutTestCase):
    def test_preview_creates_no_records(self):
        layout = make_released_layout_with_reuse_end_piece(f"{TEST_PREFIX}EP-PREVIEW")
        before_items = frappe.db.count("Item", {"name": ["like", f"{ITEM_CODE_PREFIX}%"]})
        result = preview_end_piece_boms(layout.name)
        after_items = frappe.db.count("Item", {"name": ["like", f"{ITEM_CODE_PREFIX}%"]})
        self.assertEqual(before_items, after_items)
        self.assertEqual(result["rows"][0]["item_status"], "Will be created")
```

- [ ] **Step 2: Keep isolated tests only for impractical branches**

Branches such as injected fake Frappe failures may use `patch.object(service, "frappe", fake)` if they cannot be expressed through real records. Use `unittest.mock.patch`, not pytest monkeypatch.

- [ ] **Step 3: Convert parameterized validation errors to `subTest`**

Use one test method with `cases = [...]`, and assert `ValueError` with `self.assertRaisesRegex`.

- [ ] **Step 4: Run module**

```bash
bench --site frappe16.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
```

Expected: module passes and generated Items/BOMs are registered for cleanup.

- [ ] **Step 5: Commit conversion**

```bash
git add sheet_cutting_layout/tests/test_end_piece_bom_service.py sheet_cutting_layout/tests/factories.py
git commit -m "test: convert end piece bom tests to frappe integration"
```

## Task 7: Convert Release, Workflow, and BOM Override Tests

**Files:**

- Modify: `sheet_cutting_layout/tests/test_release_service.py`
- Modify: `sheet_cutting_layout/tests/test_bom_overrides.py`
- Modify: `sheet_cutting_layout/services/release_service.py`
- Modify as needed: `sheet_cutting_layout/tests/factories.py`

- [ ] **Step 1: Remove pytest-specific production runtime detection**

In `sheet_cutting_layout/services/release_service.py`, remove:

```python
def _is_test_runtime() -> bool:
    return "pytest" in sys.modules
```

Replace call sites with explicit dependency injection or direct failures. For tests that need fallback behavior, pass `release_context_provider`, `layouts`, `boms`, or `bom_document_factory` explicitly.

- [ ] **Step 2: Convert BOM override tests to real ERPNext BOM documents**

Use `frappe.get_doc` with required BOM fields and test Items from factories:

```python
bom = frappe.get_doc(
    {
        "doctype": "BOM",
        "item": finished_part_item,
        "quantity": 1,
        "custom_operation": "Shearing",
        "items": [{"item_code": raw_material_item, "qty": 1, "uom": "Kg"}],
    }
)
```

If the bench site requires additional ERPNext mandatory fields, such as `company`, set them from the
site defaults or an explicit test company helper in `factories.py`.

Verify:

- manual shearing BOM without layout link is blocked
- generated shearing BOM with layout link is allowed
- non-shearing BOM is unaffected
- copied shearing BOM without copied layout link is blocked

Use `self.assertRaisesRegex(frappe.ValidationError, "Create a Sheet Cutting Layout")`.

- [ ] **Step 3: Run BOM override module**

```bash
bench --site frappe16.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_overrides
```

Expected: module passes.

- [ ] **Step 4: Convert release service tests**

Split into classes:

```python
class TestReleaseServiceIntegration(SheetCuttingLayoutTestCase):
    def test_mr_release_records_mr_approval_snapshot(self):
        layout = make_approved_layout_ready_for_release(f"{TEST_PREFIX}MR-SNAPSHOT")
        apply_sheet_cutting_layout_workflow(layout.as_json(), "MR Release")
        layout.reload()
        self.assertIn("MR Approval", [row.step_name for row in layout.approval_snapshot])


class TestReleaseServiceInjectedSeams(SheetCuttingLayoutTestCase):
    def test_release_uses_injected_bom_document_factory(self):
        result = release_layout(layout, bom_document_factory=fake_factory)
        self.assertEqual(result.status, "Released")


class TestReleasePatches(SheetCuttingLayoutTestCase):
    def test_patch_backfills_missing_mr_approval_snapshots(self):
        patch_execute()
        self.assertTrue(frappe.db.exists("Sheet Cutting Layout", layout.name))
```

The snippets show expected assertion shape. Prefer real layout release paths:

- create layout with factories
- apply workflow wrapper where practical
- verify generated ERPNext BOM exists
- verify MR approval snapshot exists
- verify superseded layout state changes
- verify generated BOM links are persisted

Keep injection tests only for explicit seam behavior such as custom validators, custom factories, or missing runtime branches.

- [ ] **Step 5: Convert patch tests to real records where compact**

Patch tests should create the minimum real records and call the patch function. Use prefix names and registry cleanup.

- [ ] **Step 6: Run release service module**

```bash
bench --site frappe16.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
```

Expected: module passes without pytest and without `_is_test_runtime`.

- [ ] **Step 7: Commit release/BOM conversion**

```bash
git add sheet_cutting_layout/tests/test_release_service.py sheet_cutting_layout/tests/test_bom_overrides.py sheet_cutting_layout/services/release_service.py sheet_cutting_layout/tests/factories.py
git commit -m "test: convert release and bom override tests"
```

## Task 8: Convert Hypothesis Workflow State Tests

**Files:**

- Modify: `sheet_cutting_layout/tests/test_model_workflow_state_machine.py`

- [ ] **Step 1: Convert pytest raises to unittest**

Replace module-level pytest usage with `self.assertRaisesRegex`.

- [ ] **Step 2: Keep pure state model isolated**

The state machine is a model-level invariant test. Do not force it through DB records unless the current assertions depend on actual Frappe metadata. Wrap it in a bench-discoverable class:

```python
from hypothesis.stateful import run_state_machine_as_test


class TestWorkflowStateMachine(SheetCuttingLayoutTestCase):
    def test_state_machine_never_reaches_released_without_purchase_and_mr(self):
        run_state_machine_as_test(LayoutWorkflowStateMachine)
```

Use deterministic settings on the state machine or runner:

```python
state_settings = settings(max_examples=25, stateful_step_count=20, derandomize=True)
run_state_machine_as_test(LayoutWorkflowStateMachine, settings=state_settings)
```

- [ ] **Step 3: Run state module**

```bash
bench --site frappe16.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_model_workflow_state_machine
```

Expected: module passes and still exercises state/property behavior.

- [ ] **Step 4: Commit state conversion**

```bash
git add sheet_cutting_layout/tests/test_model_workflow_state_machine.py
git commit -m "test: convert workflow state tests to bench"
```

## Task 9: Delete Pytest Bridge and Update Docs/Config

**Files:**

- Delete: `sheet_cutting_layout/tests/bench_pytest_bridge.py`
- Delete: `sheet_cutting_layout/tests/test_bench_pytest_bridge.py`
- Modify: `README.md`
- Modify: `pyproject.toml`

- [ ] **Step 1: Delete bridge files**

Remove both bridge files.

- [ ] **Step 2: Update README primary test command**

Replace `pytest -q` in `README.md` with:

```bash
bench --site <site-name> run-tests --app sheet_cutting_layout
```

Keep any bench migration/install commands already present.

- [ ] **Step 3: Review `pyproject.toml` dependencies**

Keep Hypothesis in `[tool.bench.dev-dependencies]`. Do not add pytest. If pytest is listed anywhere after conversion, remove it unless another non-test tool requires it.

- [ ] **Step 4: Verify no active pytest references remain**

Run:

```bash
rg -n "pytest|SHEET_CUTTING_LAYOUT_PYTEST|bench_pytest|_is_test_runtime" README.md pyproject.toml sheet_cutting_layout -g "*.py" -g "*.md" -g "*.toml"
```

Expected:

- No hits in app tests or production code.
- `hypothesis` may remain in `pyproject.toml`.
- Historical docs under `docs/superpowers/**` are out of scope.

- [ ] **Step 5: Commit cleanup**

```bash
git add README.md pyproject.toml sheet_cutting_layout/tests/bench_pytest_bridge.py sheet_cutting_layout/tests/test_bench_pytest_bridge.py
git commit -m "test: remove pytest bridge"
```

## Task 10: Full Bench Verification and Cleanup Validation

**Files:**

- Modify if needed: `sheet_cutting_layout/tests/factories.py`
- No planned app behavior files.

- [ ] **Step 1: Run full app tests on bench16**

Run from `/Users/gurudattkulkarni/Workspace/bench16`:

```bash
source .venv/bin/activate
bench --site frappe16.localhost run-tests --app sheet_cutting_layout
```

Expected: all tests pass through native Frappe runner. No pytest subprocess collection.

- [ ] **Step 2: Verify bench16 cleanup**

Run:

```bash
bench --site frappe16.localhost execute frappe.get_all --args '["Item"]' --kwargs '{"filters":{"name":["like","SCL-TEST-%"]},"pluck":"name"}'
bench --site frappe16.localhost execute frappe.get_all --args '["Item"]' --kwargs '{"filters":{"name":["like","SCLTEST%"]},"pluck":"name"}'
bench --site frappe16.localhost execute frappe.get_all --args '["Sheet Cutting Layout"]' --kwargs '{"filters":{"name":["like","SCL-TEST-%"]},"pluck":"name"}'
```

Expected: empty lists. If records remain, fix cleanup order or registration and rerun.

- [ ] **Step 3: Run full app tests on bench15**

Run from `/Users/gurudattkulkarni/Workspace/bench15`:

```bash
source .venv/bin/activate
bench --site development.localhost run-tests --app sheet_cutting_layout
```

Expected: all tests pass without `SHEET_CUTTING_LAYOUT_PYTEST_PYTHON`.

- [ ] **Step 4: Verify bench15 cleanup**

Run the same prefix checks on `development.localhost`. Expected: empty lists.

- [ ] **Step 5: Run pre-commit**

Run from app repo:

```bash
pre-commit run --all-files
```

Expected: all hooks pass. If formatting changes occur, rerun the affected bench module and then pre-commit again.

- [ ] **Step 6: Final grep**

Run:

```bash
rg -n "pytest|SHEET_CUTTING_LAYOUT_PYTEST|bench_pytest|_is_test_runtime" README.md pyproject.toml sheet_cutting_layout -g "*.py" -g "*.md" -g "*.toml"
```

Expected: no pytest/bridge/runtime hits. `hypothesis` may remain.

- [ ] **Step 7: Commit final verification fixes**

If Task 10 required any fixes:

```bash
git status -sb
git add sheet_cutting_layout/tests/factories.py
git commit -m "test: stabilize bench native test suite"
```

If files other than `factories.py` changed, add those explicit paths after reviewing `git status -sb`.
If no files changed, do not create an empty commit.

## Task 11: Request Code Review Before Publishing

**Files:**

- No planned changes.

- [ ] **Step 1: Review diff locally**

Run:

```bash
git status -sb
git log --oneline --decorate -8
git diff --stat develop..HEAD
```

Expected: branch contains only the spec/plan and test migration work.

- [ ] **Step 2: Request internal code review**

Use `superpowers:requesting-code-review` with:

- Base: `develop`
- Head: current branch HEAD
- Description: migrated pytest bridge suite to bench-native Frappe tests

Fix Critical and Important findings before publishing.

- [ ] **Step 3: Publish**

Use `github:yeet` after review passes:

```bash
git push -u origin codex/migrate-tests-to-bench
```

Open a draft PR against `develop`.
