# Phase 0 — Cleanup & Framework Conformance Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
**Goal:** Remove dead code, the frappe-less test shims, and the pytest-emulation layer, then bring the Sheet Cutting Layout app onto the native Frappe/ERPNext lifecycle (`on_submit`/`on_cancel`/`on_trash`, native BOM cancel/deactivate, `ignore_linked_doctypes`) so later phases build on a clean, framework-native foundation.
**Architecture:** Production services and controllers `import frappe` unconditionally; pure-domain math/cell-mapping lives in frappe-free modules but runs under `FrappeTestCase` via the bench runner. The Sheet Cutting Layout controller drives release from `on_submit` and retirement/cascade from `on_cancel`, retiring generated BOMs through native `bom.cancel()` (falling back to native `is_active=0` deactivate on `LinkExistsError`) and relying on `ignore_linked_doctypes = ["BOM"]` instead of hand-rolled backlink/savepoint juggling. The steel-weight geometry is extracted into one shared `services/geometry.py`.
**Tech Stack:** Frappe v15 / ERPNext v15.101, Python, openpyxl, Cypress
---

## Dependencies

- **Lands first.** Phase 0 has no upstream phase dependencies. It is the foundation for Phase 1 (LH/RH), Phase 2 (export), and Phase 3 (recursion).
- Implement the task groups **in order A → B → C → D → E**. Within a group, tasks are ordered; later tasks reference symbols introduced earlier.
  - **Group A (bench-native test migration)** must land first: every later group's tests are written as plain `FrappeTestCase` methods, which requires the production import shims to be gone. (The `unittest_adapter` removal and the suite migration already landed in the develop merge — Group A's remaining work is the production shims plus the test-base/factories cleanup-sweep removal.)
  - **Group D (native lifecycle spine)** depends on **Group C** (`services/geometry.py` exists) only insofar as both touch the controller; keep C before D to avoid merge churn.
- Spec sections implemented: §4 (cross-cutting principles), §6 (dead-code/residue + geometry extraction + multi-BOM fix), §7 (10 conformance themes), §12 (36-finding appendix).

### Branch

All work is on `feature/scl-iatf-export-lhrh-recursion` (already checked out, off `develop`). Do not create sub-branches; commit task-by-task on this branch.

### Test commands (full bench-native — frappe-less test mode is removed)

Run from `/Users/gurudattkulkarni/Workspace/bench15`:

- Single module: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_service`
- Whole app: `bench --site development.localhost run-tests --app sheet_cutting_layout`
- E2E: `bench --site development.localhost run-ui-tests sheet_cutting_layout --headless`

Run lint/format from the app root `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:

- `python -m ruff check .`
- `python -m ruff format --check .`

> **Indentation is TABS.** `pyproject.toml` sets `indent-style = "tab"`, `line-length = 110`. Every code block below uses tabs; preserve them exactly or `ruff format --check` fails.

### Commit style

Conventional commits (`feat:`/`fix:`/`refactor:`/`test:`/`docs:`). End every commit body with:

```
Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

### Pure-refactor vs behaviour-change labels

- **Pure refactor** (characterization tests pin existing output; no behaviour change): Group A (all), Group C (all), Task E-7 (versioning).
- **Behaviour change** (new/changed behaviour, new failing test first): Group B Task B-2 (multi-BOM primary fix), Group D (all), Group E Tasks E-1..E-6.

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `sheet_cutting_layout/services/geometry.py` | Frappe-free steel-weight + parts math (sheet/strip/part weights, `parts_per_sheet`) | **Create** (Group C) |
| `sheet_cutting_layout/services/release_service.py` | Build + insert generated BOMs on release; retire BOMs natively on cancel | **Modify** (A, B, D, E) |
| `sheet_cutting_layout/services/bom_service.py` | Frappe-free BOM row assembly + scrap-rate resolution | **Modify** (A, B, E) |
| `sheet_cutting_layout/services/end_piece_bom_service.py` | Build simple end-piece BOMs for reuse rows | **Modify** (A, B, E) |
| `sheet_cutting_layout/services/end_piece_item_service.py` | Derive + create end-piece Items | **Modify** (A, E) |
| `sheet_cutting_layout/services/validators.py` | Layout validation + derived-field formulas | **Modify** (A, B, C) |
| `sheet_cutting_layout/services/versioning.py` | Layout revision copy logic | **Modify** (E-7) |
| `sheet_cutting_layout/services/workflow.py` | Approval snapshot recording; `APPROVAL_SNAPSHOT_ACTIONS` map | **Modify** (D-1: add `Supersede`) |
| `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py` | SCL controller lifecycle | **Modify** (A, D) |
| `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json` | SCL doctype schema (parent `generated_bom` Link field already present at line 269; add PM/Purchase/MR perms; remove `Cancel` from `status` Select options line 289) | **Modify** (D-5, E-6) |
| `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_finished_part/layout_finished_part.json` | Add `generated_bom` (Link → BOM) + `orientation` columns (field absent today; `release_service` already reads `row.generated_bom`) | **Modify** (B-2) |
| `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json` | Remove dead `qty_per_sheet` field | **Modify** (B-1) |
| `sheet_cutting_layout/fixtures/workflow.json` | Set `Superseded` doc_status 1→2; delete unreachable `Cancel` state | **Modify** (D-5) |
| `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_*/*.py` | Child controllers (drop `try: import` Document stub) | **Modify** (A) |
| `sheet_cutting_layout/hooks.py` | Drop `apply_workflow` override (D-1); remove `Cancel` from Workflow State fixture filter (D-5); scope Custom Field fixture to BOM (E-5) | **Modify** (D-1, D-5, E-5) |
| `sheet_cutting_layout/tests/base.py` | `SheetCuttingLayoutTestCase` extends `FrappeTestCase` (already a 26-line v15/v16 dual-probe after the merge) | **Modify** (A-1) |
| `sheet_cutting_layout/tests/factories.py` | **Retained + trimmed.** Keeps the `make_layout`/`make_release_ready_layout`/`ensure_item`/`ensure_item_group`/`ensure_project`/`ensure_hsn_code`/`insert_if_missing` factories the whole suite imports; only the home-grown cleanup sweep (atexit, `_created_docs`, `cleanup_test_records`, …) is removed in favour of `FrappeTestCase` rollback | **Modify** (A-2) |
| `sheet_cutting_layout/tests/unittest_adapter.py` | pytest emulation — **deleted by the develop merge** | ~~Delete (A-5)~~ **DONE** |
| `sheet_cutting_layout/tests/test_unittest_adapter.py` | tests for the adapter — **deleted by the develop merge** | ~~Delete (A-5)~~ **DONE** |
| `sheet_cutting_layout/tests/test_*.py` | adapter migration already done by the merge; only `register_test_doc` de-registration remains | **Modify** (A-4) |
| `sheet_cutting_layout/patches/*.py` + `patches.txt` | 5 dev-only patches | **Delete** (B-3) |
| `.../doctype/layout_impact_resolution/` | stale residue dir (only `__pycache__`) | **Delete** (B-3) |

---

## Task group A — Bench-native test migration

Resolves findings 11, 15, 16, 18, 31, 34, 36. **Pure refactor** throughout: behaviour is unchanged; we are removing the frappe-less import shims and the hand-rolled cleanup sweep. The bench runner already imports `frappe`, so the `except ImportError` branches are dead under it.

> **Mostly landed in the develop merge.** The merge already deleted `unittest_adapter.py`/`test_unittest_adapter.py`, migrated all four suites to plain `FrappeTestCase` methods, and moved the test factories into `tests/factories.py`. **A-3 and A-5 are therefore no-ops (skip).** The live remaining work is: A-1 (drop `base.py`'s `setUpClass` sweep), A-2 (drop `factories.py`'s home-grown cleanup sweep, keep the factories), A-4 (de-register the no-op `register_test_doc` call sites), and A-6/A-7 (remove the production import shims that survived the merge).

Order matters: A-1 (base) → A-2 (factories) → A-4 (de-register `register_test_doc`) → A-6/A-7 (remove production shims, now that nothing exercises them frappe-less). [A-3, A-5 already done by the merge.]

### Task A-1: base.py drops the class-cleanup sweep (rollback handles teardown)

Pure refactor. **The develop merge already rewrote `base.py`** to the 26-line v15/v16 dual-probe shown below — the old `except ImportError: _FrappeTestCase = TestCase` fallback (finding 36) is **gone**. The *only* remaining change here is removing the `setUpClass` + `cls.addClassCleanup(cleanup_test_records)` block so per-test `FrappeTestCase` rollback handles teardown (this pairs with A-2 dropping the sweep). **Keep** the v15/v16 dual probe, `start_patcher`, and `assertFloatAlmostEqual`.

**Current `base.py` (after the merge — 26 lines):**

```python
from __future__ import annotations

try:
	# Frappe v16's canonical base class; probe it first because v16 still ships
	# frappe.tests.utils.FrappeTestCase as a deprecated shim slated for removal.
	from frappe.tests import IntegrationTestCase as FrappeTestCase
except ImportError:  # Frappe v15 ships FrappeTestCase instead.
	from frappe.tests.utils import FrappeTestCase


class SheetCuttingLayoutTestCase(FrappeTestCase):
	@classmethod
	def setUpClass(cls) -> None:
		super().setUpClass()
		from sheet_cutting_layout.tests.factories import cleanup_test_records

		cls.addClassCleanup(cleanup_test_records)

	def start_patcher(self, patcher: object) -> object:
		"""Start a mock patcher and guarantee teardown, returning what start() returns."""
		started = patcher.start()
		self.addCleanup(patcher.stop)
		return started

	def assertFloatAlmostEqual(self, actual: float | int, expected: float | int, places: int = 6) -> None:
		self.assertAlmostEqual(float(actual), float(expected), places=places)
```

> **Note:** this dual `except ImportError` probe is the v15/v16 base-class selector, **not** a frappe-less shim — keep it. Only the `setUpClass`/`addClassCleanup(cleanup_test_records)` block is removed here.

**Files:**
- Modify: `sheet_cutting_layout/tests/base.py` (remove the `setUpClass` block only; currently lines 12-17)
- Test: `sheet_cutting_layout/tests/test_base.py` (Create)

- [ ] Write the failing test `sheet_cutting_layout/tests/test_base.py`:

```python
from __future__ import annotations

from frappe.tests.utils import FrappeTestCase

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


class TestSheetCuttingLayoutTestCase(FrappeTestCase):
	def test_base_extends_frappe_test_case(self) -> None:
		self.assertTrue(issubclass(SheetCuttingLayoutTestCase, FrappeTestCase))

	def test_base_does_not_register_class_cleanup_sweep(self) -> None:
		# Cleanup is handled by FrappeTestCase per-test rollback, not a custom sweep.
		import inspect

		source = inspect.getsource(SheetCuttingLayoutTestCase)
		self.assertNotIn("cleanup_test_records", source)

	def test_assert_float_almost_equal_helper_is_available(self) -> None:
		case = SheetCuttingLayoutTestCase()
		case.assertFloatAlmostEqual(0.1 + 0.2, 0.3)
```

- [ ] Run it and see it FAIL:
  - Command (from `/Users/gurudattkulkarni/Workspace/bench15`): `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_base`
  - Expected failure: `test_base_does_not_register_class_cleanup_sweep` fails with `AssertionError: 'cleanup_test_records' unexpectedly found in ...` because the current `setUpClass` still calls `cls.addClassCleanup(cleanup_test_records)`. `SheetCuttingLayoutTestCase()` instantiation also fails because the no-arg constructor requires a `methodName` — that is fine; the assertion failure is the expected signal.

- [ ] Minimal implementation — delete only the `setUpClass` block (lines 12-17), keeping the v15/v16 dual probe, `start_patcher`, and `assertFloatAlmostEqual`. The result is:

```python
from __future__ import annotations

try:
	# Frappe v16's canonical base class; probe it first because v16 still ships
	# frappe.tests.utils.FrappeTestCase as a deprecated shim slated for removal.
	from frappe.tests import IntegrationTestCase as FrappeTestCase
except ImportError:  # Frappe v15 ships FrappeTestCase instead.
	from frappe.tests.utils import FrappeTestCase


class SheetCuttingLayoutTestCase(FrappeTestCase):
	def start_patcher(self, patcher: object) -> object:
		"""Start a mock patcher and guarantee teardown, returning what start() returns."""
		started = patcher.start()
		self.addCleanup(patcher.stop)
		return started

	def assertFloatAlmostEqual(self, actual: float | int, expected: float | int, places: int = 6) -> None:
		self.assertAlmostEqual(float(actual), float(expected), places=places)
```

- [ ] Run tests and see PASS: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_base`
- [ ] Run lint: from app root `python -m ruff check sheet_cutting_layout/tests/base.py sheet_cutting_layout/tests/test_base.py && python -m ruff format --check sheet_cutting_layout/tests/base.py sheet_cutting_layout/tests/test_base.py`
- [ ] Commit: `test: extend FrappeTestCase unconditionally in test base`

### Task A-2: factories.py drops the home-grown cleanup sweep (rollback replaces it) — keep all factories

Pure refactor. **Scope: remove ONLY the home-grown cleanup machinery** that `FrappeTestCase` per-test rollback replaces (finding 15). The merge already moved the test factories here, and the whole suite imports them from this module — they **stay**. Concretely, delete:
- the `import atexit` and `from collections import defaultdict` imports;
- the `_created_docs` dict and `_cleanup_registered` flag globals;
- `register_cleanup()` and its module-level call;
- the sweep functions `cleanup_test_records`, `get_prefixed_records`, `get_generated_test_boms`, `delete_if_exists`, `_cancel_submitted_bom`, `cleanup_order`, `_ensure_connection`, and the `TEST_PREFIX`/`ITEM_CODE_PREFIX` constants only where they become unused.

**Keep** every `make_*`/`ensure_*` factory: `make_layout` (line 183), `make_release_ready_layout` (line 222), `ensure_item` (line 166), `ensure_item_group` (line 140), `ensure_project` (line 152), `ensure_hsn_code` (line 160), and `insert_if_missing` (line 124). `register_test_doc` (line 16) becomes a no-op kept only so existing call sites keep compiling — `make_release_ready_layout`/`insert_if_missing` still call it internally, which is fine once it's a no-op; it is de-registered at the external call sites in A-4.

> **Note:** `ITEM_CODE_PREFIX` is still read by `make_release_ready_layout` (`f"{ITEM_CODE_PREFIX}FG…"`), so keep it; only `TEST_PREFIX` and the sweep-only helpers go. Confirm with `grep -n "ITEM_CODE_PREFIX\|TEST_PREFIX" sheet_cutting_layout/tests/factories.py` before deleting either constant.

> **`make_layout` location (pinned, post-merge).** The integration factory `make_layout` now lives in **`sheet_cutting_layout/tests/factories.py` (line 183)** alongside `make_release_ready_layout` (line 222) — the develop merge moved it here out of the doctype test module, and every suite imports it via `from sheet_cutting_layout.tests.factories import make_layout, make_release_ready_layout, register_test_doc`. Bench-gated tests that need it (D-2, D-4, D-5) import it from `tests.factories`; do **not** reach for a `helpers.make_layout`/local definition.

**Files:**
- Modify: `sheet_cutting_layout/tests/factories.py` (remove the cleanup-sweep block — `atexit` import + `_created_docs`/`_cleanup_registered` + `register_cleanup`/`cleanup_test_records`/`get_prefixed_records`/`get_generated_test_boms`/`delete_if_exists`/`_cancel_submitted_bom`/`cleanup_order`/`_ensure_connection`, currently lines 3-4, 12-13, 41-121; keep the factories)
- Test: `sheet_cutting_layout/tests/test_factories.py` (Create)

- [ ] Write the failing test `sheet_cutting_layout/tests/test_factories.py`:

```python
from __future__ import annotations

from frappe.tests.utils import FrappeTestCase

from sheet_cutting_layout.tests import factories


class TestFactories(FrappeTestCase):
	def test_register_test_doc_is_a_noop_under_rollback(self) -> None:
		# Must not raise and must not touch any global registry.
		factories.register_test_doc("Sheet Cutting Layout", "SCL-TEST-NOOP")
		self.assertFalse(hasattr(factories, "_created_docs"))

	def test_no_atexit_cleanup_is_registered(self) -> None:
		import inspect

		source = inspect.getsource(factories)
		self.assertNotIn("atexit", source)
		self.assertNotIn("cleanup_test_records", source)

	def test_factories_are_still_exported(self) -> None:
		# The merge moved the factories here; they must remain importable.
		for name in (
			"make_layout",
			"make_release_ready_layout",
			"ensure_item",
			"insert_if_missing",
		):
			self.assertTrue(hasattr(factories, name))
```

- [ ] Run it and see it FAIL: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_factories`
  - Expected failure: `test_no_atexit_cleanup_is_registered` fails with `AssertionError: 'atexit' unexpectedly found in ...` and `test_register_test_doc_is_a_noop_under_rollback` fails because `factories._created_docs` still exists.

- [ ] Minimal implementation — in `sheet_cutting_layout/tests/factories.py`:
  - Delete the `import atexit` and `from collections import defaultdict` lines.
  - Delete the `_created_docs`/`_cleanup_registered` globals.
  - Delete `cleanup_order`, `_ensure_connection`, `_cancel_submitted_bom`, `delete_if_exists`, `get_prefixed_records`, `get_generated_test_boms`, `cleanup_test_records`, `register_cleanup`, and the bare `register_cleanup()` call.
  - Reduce `register_test_doc` to a no-op:

```python
def register_test_doc(doctype: str, name: str | None) -> None:
	"""No-op kept for call-site compatibility.

	FrappeTestCase rolls back the database after each test, so explicitly
	created docs do not need to be tracked or swept.
	"""
	return None
```

  - **Leave the rest of the module intact**: `insert_if_missing`, `ensure_item_group`, `ensure_project`, `ensure_hsn_code`, `ensure_item`, `make_layout`, `make_release_ready_layout`, and the `ITEM_CODE_PREFIX` constant they rely on.

- [ ] Run tests and see PASS: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_factories`
- [ ] Run lint: `python -m ruff check sheet_cutting_layout/tests/factories.py sheet_cutting_layout/tests/test_factories.py && python -m ruff format --check sheet_cutting_layout/tests/factories.py sheet_cutting_layout/tests/test_factories.py`
- [ ] Commit: `test: drop factories cleanup sweep in favour of FrappeTestCase rollback`

### Task A-3: migrate test_bom_service.py off the pytest-emulation adapter — ALREADY DONE BY THE develop MERGE — skip

**ALREADY DONE BY THE develop MERGE — skip.** The merge deleted `tests/unittest_adapter.py` (and `test_unittest_adapter.py`) and migrated every consumer to plain `FrappeTestCase` methods. `test_bom_service.py` no longer imports `unittest_adapter` or calls `add_pytest_style_tests` — verify with `grep -rn "unittest_adapter\|add_pytest_style_tests" sheet_cutting_layout/tests/test_bom_service.py` (zero hits). Nothing to do.

### Task A-4: de-register `register_test_doc` call sites (adapter migration already done by the merge)

**Adapter migration: ALREADY DONE BY THE develop MERGE — skip.** `test_release_service.py`, `test_model_workflow_state_machine.py`, and `test_validators.py` no longer import `unittest_adapter`/`MonkeyPatch`/`add_pytest_style_tests` (the merge converted them to plain `FrappeTestCase` methods and deleted the adapter). Confirm with `grep -rn "unittest_adapter\|add_pytest_style_tests" sheet_cutting_layout/tests` (zero hits).

**Remaining scope (gated on the corrected A-2):** once `register_test_doc` is a no-op (A-2), de-register its external call sites. After the merge, `register_test_doc` is imported and called from the doctype controller test module — `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py` imports it (in the factory import at lines 11-15) and calls it at lines 154, 171, 198 (paired with `make_layout`/`make_release_ready_layout` at lines 144, 154, 162, 171, 191, 194, 203). Removing those calls is cleaner now that it's a no-op.

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py` (drop the `register_test_doc` import member + its calls)

- [ ] In `test_sheet_cutting_layout.py`, drop `register_test_doc` from the factory import block (lines 11-15) so it reads `from sheet_cutting_layout.tests.factories import make_layout, make_release_ready_layout`, and delete every `register_test_doc(...)` call (lines 154, 171, 198 — no-op under FrappeTestCase rollback).

- [ ] Run the affected module and see PASS:
  - `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout`
  - Expected: identical assertions pass; no `register_test_doc` reference remains.

- [ ] Run lint: `python -m ruff check sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py && python -m ruff format --check sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`
- [ ] Commit: `test: drop no-op register_test_doc call sites`

### Task A-5: delete the pytest-emulation adapter and its test — ALREADY DONE BY THE develop MERGE — skip

**ALREADY DONE BY THE develop MERGE — skip.** Both `sheet_cutting_layout/tests/unittest_adapter.py` and `sheet_cutting_layout/tests/test_unittest_adapter.py` were deleted by the merge, and no module references `unittest_adapter` any more — confirm with `grep -rn "unittest_adapter" sheet_cutting_layout/ --include="*.py"` (zero hits). Nothing to delete or commit.

### Task A-6: remove the frappe-less import shim from the SCL controller and child controllers

Pure refactor. The bench always provides `frappe`; the `try: import frappe / except ImportError` blocks plus the stub `Document` / `whitelist` (controller findings 34) are dead. Replace with unconditional imports. **Important:** the controller is rewritten more deeply in Group D — this task only removes the import shim and the `if not frappe:` guards that depend on it, leaving the workflow logic in place for D to replace. Keep the diff minimal.

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py` (lines 1-25: the import shim)
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.py` (lines 1-12)
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_finished_part/layout_finished_part.py`
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_approval_snapshot/layout_approval_snapshot.py`
- Test: `sheet_cutting_layout/tests/test_controller_imports.py` (Create)

- [ ] Write the failing test `sheet_cutting_layout/tests/test_controller_imports.py`:

```python
from __future__ import annotations

import inspect

from frappe.model.document import Document
from frappe.tests.utils import FrappeTestCase

from sheet_cutting_layout.sheet_cutting_layout.doctype.layout_approval_snapshot import (
	layout_approval_snapshot as snapshot_module,
)
from sheet_cutting_layout.sheet_cutting_layout.doctype.layout_end_piece import (
	layout_end_piece as end_piece_module,
)
from sheet_cutting_layout.sheet_cutting_layout.doctype.layout_finished_part import (
	layout_finished_part as finished_part_module,
)
from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import (
	sheet_cutting_layout as controller,
)


class TestControllerImports(FrappeTestCase):
	def test_child_controllers_use_real_document_base(self) -> None:
		self.assertTrue(issubclass(end_piece_module.LayoutEndPiece, Document))
		self.assertTrue(issubclass(finished_part_module.LayoutFinishedPart, Document))
		self.assertTrue(issubclass(snapshot_module.LayoutApprovalSnapshot, Document))

	def test_controllers_have_no_frappe_import_shim(self) -> None:
		for module in (controller, end_piece_module, finished_part_module, snapshot_module):
			self.assertNotIn("except ImportError", inspect.getsource(module))
```

- [ ] Run it and see it FAIL: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_controller_imports`
  - Expected failure: `test_controllers_have_no_frappe_import_shim` fails with `AssertionError: 'except ImportError' unexpectedly found ...` because all four controllers still wrap their imports in `try/except ImportError`.

- [ ] Minimal implementation — in the three child controllers replace the whole `try: from frappe.model.document import Document / except ImportError: class Document: pass` block with a plain import. For `layout_end_piece.py` the result is:

```python
from __future__ import annotations

from frappe.model.document import Document


class LayoutEndPiece(Document):
	pass
```

  Apply the analogous one-line-import rewrite to `layout_finished_part.py` (`LayoutFinishedPart`) and `layout_approval_snapshot.py` (`LayoutApprovalSnapshot`).

- [ ] In the SCL controller `sheet_cutting_layout.py`, replace lines 1-25 (the `try: import frappe ... except ImportError: ... class Document: pass` block) with:

```python
from __future__ import annotations

from datetime import datetime
from importlib import import_module

import frappe
from frappe.model.document import Document

whitelist = frappe.whitelist

_ = frappe._
```

  Then remove every `if not frappe:` / `if frappe:` guard in the controller body that only existed for the frappe-less path: in `_get_selected_workflow_action`, `_get_session_user`, `_get_now_datetime`, `_workflow_side_effects_are_suppressed`, and the whitelisted entry points `apply_sheet_cutting_layout_workflow`, `create_sheet_cutting_layout_revision`, `generate_sheet_cutting_layout_end_piece_boms`. Replace `if not frappe: raise RuntimeError(...)` early-returns with the body that follows (frappe is always present). Leave the workflow logic itself untouched for Group D.

- [ ] Run tests and see PASS: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_controller_imports`
- [ ] Run the controller integration suite to confirm no regression: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout`
- [ ] Run lint over all five files.
- [ ] Commit: `refactor: drop frappe-less import shims from controllers`

### Task A-7: remove the frappe-less import shims from the services

Pure refactor. `validators.py` (finding 11), `end_piece_item_service.py` (finding 31), `end_piece_bom_service.py`, `overrides/bom.py` (finding 18), `release_service.py`, and `versioning.py`'s inner `try: import frappe` (finding 33 touches this file too — done fully in E-7; here only its import). Replace each `try: import frappe / except ImportError: <_FrappeCompat>` with `import frappe`.

**Files:** (shims survived the develop merge; spans re-confirmed against the merged tree)
- Modify: `sheet_cutting_layout/services/validators.py` (`try`@16 / `except ImportError`@18 / `_FrappeCompat`@23-30)
- Modify: `sheet_cutting_layout/services/end_piece_item_service.py` (`try`@5 / `except ImportError`@7 / `_FrappeCompat`@12-29)
- Modify: `sheet_cutting_layout/services/end_piece_bom_service.py` (`try`@14 / `except ImportError`@16 / `_FrappeCompat`@21-28)
- Modify: `sheet_cutting_layout/services/release_service.py` (`try`@19 / `except ImportError: frappe = None`@21-22)
- Modify: `sheet_cutting_layout/overrides/bom.py` (`try`@3 / `except ImportError`@5 / `_FrappeCompat`@10-17)
- Test: `sheet_cutting_layout/tests/test_service_imports.py` (Create)

- [ ] Write the failing test `sheet_cutting_layout/tests/test_service_imports.py`:

```python
from __future__ import annotations

import inspect

from frappe.tests.utils import FrappeTestCase

from sheet_cutting_layout.overrides import bom as bom_override
from sheet_cutting_layout.services import (
	bom_service,
	end_piece_bom_service,
	end_piece_item_service,
	release_service,
	validators,
)


class TestServiceImports(FrappeTestCase):
	def test_services_have_no_frappe_import_shim(self) -> None:
		for module in (
			validators,
			end_piece_item_service,
			end_piece_bom_service,
			release_service,
			bom_override,
		):
			with self.subTest(module=module.__name__):
				self.assertNotIn("except ImportError", inspect.getsource(module))

	def test_validators_throw_uses_real_frappe(self) -> None:
		import frappe

		with self.assertRaises(frappe.ValidationError):
			validators.validate_finished_part_code("not-alnum-!")

	def test_bom_service_remains_frappe_free_at_import(self) -> None:
		# Pure-domain module: no top-level `import frappe`.
		self.assertNotIn("\nimport frappe", inspect.getsource(bom_service))
```

- [ ] Run it and see it FAIL: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_service_imports`
  - Expected failure: `test_services_have_no_frappe_import_shim` fails — `validators`, `end_piece_item_service`, `end_piece_bom_service`, `release_service`, and `bom_override` all still contain `except ImportError`.

- [ ] In `validators.py` replace lines 16-30 (`try: import frappe / except ImportError: <_FrappeCompat>`) with `import frappe`. Keep line `_ = getattr(frappe, "_", lambda message: message)` as `_ = frappe._`.

- [ ] In `end_piece_item_service.py` replace lines 5-29 (the `_FrappeCompat` shim with `ValidationError`/`DuplicateEntryError`/`log_error`/`get_traceback`) with `import frappe`. Keep `_ = frappe._`.

- [ ] In `end_piece_bom_service.py` replace lines 14-28 (the `_FrappeCompat` shim) with `import frappe`. Keep `_ = frappe._`.

- [ ] In `release_service.py` replace lines 19-22 (and the `_ = getattr(...)` on line 24):

```python
try:
	import frappe
except ImportError:
	frappe = None

_ = getattr(frappe, "_", lambda message: message)
```

  with:

```python
import frappe

_ = frappe._
```

  Then delete every `if not frappe:` / `if frappe is None:` guard and the `getattr(frappe, "db", None) if frappe else None` ternaries throughout the module that only existed to tolerate `frappe = None`. (These are touched again in Group D; here just simplify the now-impossible `None` path. If a guard is load-bearing for a Group-D rewrite, leave it and note it — do not break tests.)

  > Safe minimal version: keep the structure but change `getattr(frappe, "db", None) if frappe else None` → `frappe.db`, and remove `if not frappe: return None` lines, since Group D rewrites the retirement helpers anyway.

- [ ] In `overrides/bom.py` replace lines 3-17 (the `_FrappeCompat` shim) with `import frappe`. Keep `_ = frappe._`.

- [ ] Run tests and see PASS: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_service_imports`
- [ ] Run the full suite to confirm no regression: `bench --site development.localhost run-tests --app sheet_cutting_layout`
- [ ] Run lint over the five modified files.
- [ ] Commit: `refactor: import frappe unconditionally in services`

---

## Task group B — Dead code & residue (§6)

Resolves findings 19-22 (patch drop) and the dead-field cleanup. Task B-1 is a **behaviour-adjacent refactor** (removing an unused field + the legacy multiplicity guard that read it); B-2 is a **behaviour change** (multi-BOM primary fix + new child columns); B-3 is pure deletion.

### Task B-1: remove the dead `qty_per_sheet` field and its EndPieceRow attrs

The `qty_per_sheet` field on `Layout End Piece` is `hidden: 1` and only consumed by `validators._validate_unreleased_legacy_end_piece_multiplicity` / `_has_legacy_qty_per_sheet_multiplicity` (a legacy guard). It is declared on the `EndPieceRow` Protocols in **exactly three** services — `bom_service` (line 19), `release_service` (line 35), and `validators` (line 40) — and is **NOT** declared in `end_piece_bom_service.EndPieceRow` (verified: `grep -n qty_per_sheet sheet_cutting_layout/services` returns hits only in those three plus the two validators-guard helpers). This matches the spec §6 ("the three `EndPieceRow` Protocols in `bom_service`, `release_service`, `validators` — `end_piece_bom_service` does not declare it"). Remove the attr from those three Protocols, the field, and — since dropping the field makes the legacy multiplicity guard unreachable — the guard too (and the test that exercised it).

> **Decision (note in commit):** This drops the "Qty Per Sheet > 1 is legacy data" guard. That guard exists only to block stale pre-split data; per §6 the field is dead and rows are already one-per-instance. Removing it is a deliberate behaviour change scoped to legacy data only.

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json` (remove `qty_per_sheet` from `field_order` lines 8-23 and its field def lines 57-62)
- Modify: `sheet_cutting_layout/services/validators.py` (remove `qty_per_sheet: float | None` from `EndPieceRow` line 40; remove `_validate_unreleased_legacy_end_piece_multiplicity` lines 318-331 + `_has_legacy_qty_per_sheet_multiplicity` lines 333-338 and the call on line 98)
- Modify: `sheet_cutting_layout/services/bom_service.py` (remove `qty_per_sheet: float` from `EndPieceRow` line 19 — it IS declared here and must be removed)
- Modify: `sheet_cutting_layout/services/end_piece_bom_service.py` (`EndPieceRow` Protocol does **not** declare `qty_per_sheet` — nothing to change; this file is left untouched. Confirm with `grep -n qty_per_sheet sheet_cutting_layout/services/end_piece_bom_service.py` returning no hits.)
- Modify: `sheet_cutting_layout/services/release_service.py` (remove `qty_per_sheet: float` from `EndPieceRow` line 35)
- Modify: tests that set `qty_per_sheet` (`test_bom_service.py`, `test_release_service.py`, `test_validators.py`, `test_sheet_cutting_layout.py`) — remove the field from their fake `EndPiece` dataclasses and the legacy-guard test.
- Test: `sheet_cutting_layout/tests/test_validators.py` (modify — drop the legacy-multiplicity test, add a guard-absence assertion)

- [ ] First grep to confirm exact surface: from app root `grep -rn "qty_per_sheet" sheet_cutting_layout/services sheet_cutting_layout/sheet_cutting_layout`. Record every hit.

- [ ] Write the failing test (add to `tests/test_validators.py`, inside the validators test class):

```python
	def test_qty_per_sheet_legacy_guard_is_removed(self) -> None:
		import inspect

		from sheet_cutting_layout.services import bom_service, release_service, validators

		validators_source = inspect.getsource(validators)
		self.assertNotIn("qty_per_sheet", validators_source)
		self.assertNotIn("_validate_unreleased_legacy_end_piece_multiplicity", validators_source)
		# qty_per_sheet is also declared on the EndPieceRow Protocol in bom_service
		# (line 19) and release_service (line 35); both must drop it.
		self.assertNotIn("qty_per_sheet", inspect.getsource(bom_service))
		self.assertNotIn("qty_per_sheet", inspect.getsource(release_service))
```

- [ ] Run it and see it FAIL: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators`
  - Expected failure: `AssertionError: 'qty_per_sheet' unexpectedly found in ...` because `validators.py` (line 40 + guard), `bom_service.py` (line 19), and `release_service.py` (line 31) all still declare the attr.

- [ ] Implement:
  - In `validators.py`: delete the `qty_per_sheet: float | None` line from the `EndPieceRow` Protocol (line 40); delete `_validate_unreleased_legacy_end_piece_multiplicity` (lines 318-331) and `_has_legacy_qty_per_sheet_multiplicity` (lines 333-338); delete the call `_validate_unreleased_legacy_end_piece_multiplicity(layout, end_pieces)` on line 98.
  - In `bom_service.py`: delete `qty_per_sheet: float` from the `EndPieceRow` Protocol (line 19).
  - In `release_service.py`: delete `qty_per_sheet: float` from the `EndPieceRow` Protocol (line 35).
  - Leave `end_piece_bom_service.py` untouched (its `EndPieceRow` never declared `qty_per_sheet`).
  - In `layout_end_piece.json`: remove `"qty_per_sheet"` from `field_order`, and remove the field object (the `{"fieldname": "qty_per_sheet", ...}` block).
  - In the test dataclasses: remove `qty_per_sheet: float = 1` (and any `qty_per_sheet=...` kwargs) from the fake `EndPiece` classes in `test_bom_service.py`, `test_release_service.py`, `test_validators.py`; remove the `"qty_per_sheet": 2` key from the `make_layout` end-piece dict and delete `test_unreleased_layout_with_qty_per_sheet_gt_one_is_blocked_until_rows_are_split` and `test_qty_per_sheet_is_not_required_for_end_piece_validation` / `test_stale_qty_per_sheet_payload_is_ignored_for_weight_and_consumption` in `test_validators.py` (these assert the now-removed guard).

- [ ] Run tests and see PASS: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators` then the bom_service / release_service modules.
- [ ] Run `bench --site development.localhost migrate` from bench root so the dropped column is removed from the live DB schema (dev-only hard-reset policy permits this).
- [ ] Run lint over all modified files.
- [ ] Commit: `refactor: remove dead qty_per_sheet field and legacy guard`

### Task B-2: multi-BOM primary fix + `generated_bom`/`orientation` columns on Layout Finished Part

**Behaviour change.** Today `_generate_boms` calls `_set_frappe_field_if_supported(layout, "generated_bom", bom.name)` on **every** iteration (release_service line 335), so for multiple finished parts `layout.generated_bom` ends up holding the **last** BOM, not the primary. Per §6/§8.2, `layout.generated_bom` must hold the **primary** (first) part's BOM; the rest live in the `finished_parts` mirror rows. Also add the `generated_bom` (Link → BOM) and `orientation` (Select LH/RH) columns to `Layout Finished Part` — `_layout_bom_names` and `_sync_finished_part_reference_rows` already read/write `row.generated_bom`, but the doctype has no such field (latent mismatch, §8.1).

**Files:**
- Modify: `sheet_cutting_layout/services/release_service.py` (`_generate_boms` lines 321-338, with the last-write overwrite at line 335; `_sync_finished_part_reference_rows` lines 448-466)
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_finished_part/layout_finished_part.json` (add two fields)
- Test: `sheet_cutting_layout/tests/test_release_service.py` (add a multi-part method)

- [ ] Write the failing test. Add to `TestReleaseService` in `tests/test_release_service.py` (it already defines `Layout`, `FinishedPart`, and a stubbed `release_layout` path with `bom_document_factory`):

```python
	def test_generated_bom_holds_primary_part_with_multiple_finished_parts(self) -> None:
		layout = Layout()
		layout.finished_part_code = "PART001SHR"
		built: list[str] = []

		def fake_factory(layout_doc, finished_part, index):
			from sheet_cutting_layout.services.bom_service import BomDocument

			name = f"BOM-{index:03d}-{finished_part.finished_part_item}"
			built.append(name)
			return BomDocument(item=finished_part.finished_part_item, name=name)

		# Two structurally-identical parts (groundwork for LH/RH): patch the parent
		# rows resolver to return two rows.
		from sheet_cutting_layout.services import release_service

		def two_rows(_layout):
			from sheet_cutting_layout.services.bom_service import ParentFinishedPartRow

			return [
				ParentFinishedPartRow("PART001SHR", 1, 1.0, 0.0),
				ParentFinishedPartRow("PART001SHR_TWIN", 1, 1.0, 0.0),
			]

		with patch.object(release_service, "_parent_finished_part_rows", two_rows):
			result = release_service.release_layout(
				layout,
				layouts=(),
				boms=[],
				validators=(),
				bom_document_factory=fake_factory,
			)

		self.assertEqual(len(result.generated_boms), 2)
		# Primary == first part's BOM, not the last.
		self.assertEqual(layout.generated_bom, built[0])
```

  (`patch` is imported in the file; if not, add `from unittest.mock import patch`.)

- [ ] Run it and see it FAIL: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service`
  - Expected failure: `AssertionError: 'BOM-002-PART001SHR_TWIN' != 'BOM-001-PART001SHR'` — `layout.generated_bom` currently holds the last (`index=2`) BOM because the loop overwrites it every iteration.

- [ ] Implement — rewrite `_generate_boms` (release_service lines 321-338) so only the **first** part sets `layout.generated_bom`:

```python
def _generate_boms(
	layout: ReleaseLayoutDocument,
	bom_name_factory: Callable[[ReleaseLayoutDocument, FinishedPartRow, int], str] | None,
	bom_document_factory: BomDocumentFactory | None,
) -> list[BomDocument]:
	finished_parts = _parent_finished_part_rows(layout)
	generated_boms: list[BomDocument] = []

	for index, finished_part in enumerate(finished_parts, start=1):
		bom = (
			bom_document_factory(layout, finished_part, index)
			if bom_document_factory is not None
			else _default_bom_document_factory(layout, finished_part, index, bom_name_factory)
		)
		if index == 1:
			_set_frappe_field_if_supported(layout, "generated_bom", bom.name)
		generated_boms.append(bom)

	return generated_boms
```

- [ ] Extend `_sync_finished_part_reference_rows` (release_service lines 448-466) so each mirror row also records its `generated_bom` (and, when present on the parent row, `orientation`). Change the dict comprehension to:

```python
	references = [
		{
			"finished_part_item": finished_part.finished_part_item,
			"bom_quantity": _finished_part_bom_quantity(finished_part),
			"scrap_weight_kg": _sum_bom_qty(bom.scrap_items),
			"raw_material_weight_kg": _sum_bom_qty(bom.items),
			"generated_bom": getattr(bom, "name", None),
			"orientation": getattr(finished_part, "orientation", None),
		}
		for finished_part, bom in zip(finished_parts, generated_boms, strict=False)
	]
```

  (`orientation` is `None` for non-LH/RH parts; the column is added now so Phase 1 can populate it.)

- [ ] Add the two fields to `layout_finished_part.json`. Append `"generated_bom"` and `"orientation"` to `field_order`, and add field objects:

```json
  {
   "fieldname": "generated_bom",
   "fieldtype": "Link",
   "label": "Generated BOM",
   "options": "BOM",
   "read_only": 1
  },
  {
   "fieldname": "orientation",
   "fieldtype": "Select",
   "label": "Orientation",
   "options": "\nLH\nRH",
   "read_only": 1
  }
```

- [ ] Run tests and see PASS: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service`
- [ ] Run `bench --site development.localhost migrate` to add the new columns.
- [ ] Run lint.
- [ ] Commit: `fix: keep primary generated_bom and add Layout Finished Part BOM/orientation columns`

### Task B-3: delete the 5 patches + patches.txt entries + layout_impact_resolution residue

Pure deletion (resolves findings 19-22). Dev-only hard-reset policy (§6) permits dropping migration patches. The `layout_impact_resolution` doctype dir contains only a stale `__pycache__` (verified: no `.py`/`.json`, zero source refs).

**Files:**
- Delete: `sheet_cutting_layout/patches/v1_0_migrate_checked_workflow_state_to_pm_approved.py`
- Delete: `sheet_cutting_layout/patches/v1_0_submit_released_layouts.py`
- Delete: `sheet_cutting_layout/patches/v1_0_submit_superseded_layouts.py`
- Delete: `sheet_cutting_layout/patches/v1_0_backfill_mr_approval_snapshots.py`
- Delete: `sheet_cutting_layout/patches/v1_0_mark_cancelled_layouts_and_unlink_boms.py`
- Modify: `sheet_cutting_layout/patches.txt` (remove the 5 `[post_model_sync]` entries)
- Delete: `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_impact_resolution/` (whole dir)

- [ ] Confirm residue is dead: `grep -rn "layout_impact_resolution\|Layout Impact Resolution" sheet_cutting_layout --include="*.py" --include="*.json" --include="*.txt"`. Expected: no output.
- [ ] `git rm sheet_cutting_layout/patches/v1_0_migrate_checked_workflow_state_to_pm_approved.py sheet_cutting_layout/patches/v1_0_submit_released_layouts.py sheet_cutting_layout/patches/v1_0_submit_superseded_layouts.py sheet_cutting_layout/patches/v1_0_backfill_mr_approval_snapshots.py sheet_cutting_layout/patches/v1_0_mark_cancelled_layouts_and_unlink_boms.py`
- [ ] `rm -rf sheet_cutting_layout/sheet_cutting_layout/doctype/layout_impact_resolution` then `git add -A`.
- [ ] Edit `patches.txt`: under `[post_model_sync]` remove the five `sheet_cutting_layout.patches.v1_0_*` lines, leaving the section header + comment.
- [ ] Run `bench --site development.localhost migrate` from bench root — expect a clean migrate with no missing-patch import error.
- [ ] Run the full suite: `bench --site development.localhost run-tests --app sheet_cutting_layout`
- [ ] Commit: `chore: drop dev-only migration patches and stale doctype residue`

---

## Task group C — Geometry extraction (§6)

**Pure refactor.** Move the steel-weight + parts math into one frappe-free `services/geometry.py` and have `validators.py` (and, later, the controller/exporter) call it. Characterization tests pin current outputs first. The canonical density factor is `× 0.786 / 100000` (equivalently `thickness*width*length*7.86/1_000_000`, as `validators.calculate_sheet_weight_kg` computes today).

### Task C-1: create services/geometry.py with characterized weight + parts math

**Files:**
- Create: `sheet_cutting_layout/services/geometry.py`
- Test: `sheet_cutting_layout/tests/test_geometry.py` (Create)

- [ ] Write the failing characterization test `sheet_cutting_layout/tests/test_geometry.py`:

```python
from __future__ import annotations

from frappe.tests.utils import FrappeTestCase

from sheet_cutting_layout.services import geometry


class TestGeometry(FrappeTestCase):
	def test_sheet_weight_uses_steel_density_factor(self) -> None:
		# 1mm x 1250mm x 2500mm sheet: 1 * 1250 * 2500 * 0.786 / 100000 = 24.5625
		self.assertAlmostEqual(
			geometry.sheet_weight_kg(thickness_mm=1, width_mm=1250, length_mm=2500),
			24.5625,
			places=6,
		)

	def test_sheet_weight_returns_none_for_nonpositive_or_invalid(self) -> None:
		self.assertIsNone(geometry.sheet_weight_kg(thickness_mm=0, width_mm=1250, length_mm=2500))
		self.assertIsNone(geometry.sheet_weight_kg(thickness_mm=1, width_mm=-1, length_mm=2500))
		self.assertIsNone(geometry.sheet_weight_kg(thickness_mm="x", width_mm=1250, length_mm=2500))

	def test_gross_weight_per_part_divides_strip_weight(self) -> None:
		self.assertAlmostEqual(
			geometry.gross_weight_per_part_kg(weight_of_strip_kg=10.0, parts_per_strip=4),
			2.5,
			places=6,
		)

	def test_gross_weight_per_part_guards_zero_parts(self) -> None:
		self.assertIsNone(geometry.gross_weight_per_part_kg(weight_of_strip_kg=10.0, parts_per_strip=0))
		self.assertIsNone(geometry.gross_weight_per_part_kg(weight_of_strip_kg=None, parts_per_strip=4))

	def test_parts_per_sheet_multiplies_strip_count(self) -> None:
		self.assertEqual(geometry.parts_per_sheet(parts_per_strip=7, no_of_strips=11), 77)
		self.assertIsNone(geometry.parts_per_sheet(parts_per_strip=0, no_of_strips=11))
		self.assertIsNone(geometry.parts_per_sheet(parts_per_strip=7, no_of_strips=None))
```

- [ ] Run it and see it FAIL: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_geometry`
  - Expected failure: `ModuleNotFoundError: No module named 'sheet_cutting_layout.services.geometry'`.

- [ ] Minimal implementation — create `sheet_cutting_layout/services/geometry.py` (frappe-free; rounding mirrors `validators._round_value` with a fixed precision so domain logic stays import-clean):

```python
from __future__ import annotations

STEEL_DENSITY_G_PER_CM3 = 7.86
DEFAULT_PRECISION = 6


def _round(value: float, precision: int = DEFAULT_PRECISION) -> float:
	return round(float(value), precision)


def sheet_weight_kg(
	*,
	thickness_mm: float | int | str | None,
	width_mm: float | int | str | None,
	length_mm: float | int | str | None,
	precision: int = DEFAULT_PRECISION,
) -> float | None:
	"""Steel weight of a rectangular sheet/strip/part in kg.

	weight = thickness_mm * width_mm * length_mm * 0.786 / 100000
	       = thickness * width * length * 7.86 / 1_000_000
	"""
	try:
		thickness = float(thickness_mm)
		width = float(width_mm)
		length = float(length_mm)
	except (TypeError, ValueError):
		return None
	if thickness <= 0 or width <= 0 or length <= 0:
		return None
	weight = length * width * thickness * STEEL_DENSITY_G_PER_CM3 / 1_000_000
	return _round(weight, precision)


def gross_weight_per_part_kg(
	*,
	weight_of_strip_kg: float | int | str | None,
	parts_per_strip: int | None,
	precision: int = DEFAULT_PRECISION,
) -> float | None:
	if weight_of_strip_kg is None or parts_per_strip is None:
		return None
	try:
		parts = int(parts_per_strip)
	except (TypeError, ValueError):
		return None
	if parts <= 0:
		return None
	return _round(float(weight_of_strip_kg) / parts, precision)


def parts_per_sheet(*, parts_per_strip: int | None, no_of_strips: int | None) -> int | None:
	if parts_per_strip is None or no_of_strips is None:
		return None
	if parts_per_strip <= 0 or no_of_strips <= 0:
		return None
	return int(parts_per_strip) * int(no_of_strips)
```

- [ ] Run tests and see PASS: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_geometry`
- [ ] Run lint over `geometry.py` and `test_geometry.py`.
- [ ] Commit: `feat: add frappe-free services/geometry.py`

### Task C-2: point validators at services/geometry.py

**Pure refactor.** `validators.py` keeps its public formula functions (`apply_sheet_weight_formula`, `apply_strip_weight_formula`, `apply_parent_gross_weight_per_part_formula`, `apply_parts_per_sheet_formula`, `apply_end_piece_weight_formulas`) but delegates the math to `geometry`. The existing `validators.calculate_sheet_weight_kg`, `calculate_parent_gross_weight_per_part_kg`, and `calculate_parts_per_sheet` become thin shims delegating to `geometry` (keep them so other callers/tests that import them don't break) OR are removed if grep shows no external callers. Verify with grep before deciding.

**Files:**
- Modify: `sheet_cutting_layout/services/validators.py` (import `geometry`; delegate `calculate_sheet_weight_kg` line 220-236, `calculate_parent_gross_weight_per_part_kg` line 178-185, `calculate_parts_per_sheet` line 166-175)
- Test: `sheet_cutting_layout/tests/test_validators.py` (existing characterization coverage; add a delegation assertion)

- [ ] Grep external callers: `grep -rn "calculate_sheet_weight_kg\|calculate_parent_gross_weight_per_part_kg\|calculate_parts_per_sheet" sheet_cutting_layout --include="*.py"`. If only `validators.py` + its tests use them, they can delegate (keep the names).

- [ ] Write the failing test (add to `tests/test_validators.py`):

```python
	def test_validators_sheet_weight_delegates_to_geometry(self) -> None:
		from unittest.mock import patch

		from sheet_cutting_layout.services import validators

		with patch("sheet_cutting_layout.services.validators.geometry.sheet_weight_kg", return_value=99.0) as spy:
			result = validators.calculate_sheet_weight_kg(thickness_mm=1, width_mm=2, length_mm=3)

		self.assertEqual(result, 99.0)
		spy.assert_called_once()
```

- [ ] Run it and see it FAIL: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators`
  - Expected failure: `AttributeError: <module 'sheet_cutting_layout.services.validators'> does not have the attribute 'geometry'` because `validators` does not yet import `geometry`.

- [ ] Implement:
  - Add `from sheet_cutting_layout.services import geometry` to `validators.py` imports.
  - Replace the body of `calculate_sheet_weight_kg` (lines 220-236) with `return geometry.sheet_weight_kg(thickness_mm=thickness_mm, width_mm=width_mm, length_mm=length_mm, precision=_float_precision())`.
  - Replace `calculate_parent_gross_weight_per_part_kg` body with `return geometry.gross_weight_per_part_kg(weight_of_strip_kg=weight_of_strip_kg, parts_per_strip=parts_per_strip, precision=_calculation_precision())`.
  - Replace `calculate_parts_per_sheet` body with `return geometry.parts_per_sheet(parts_per_strip=parts_per_strip, no_of_strips=no_of_strips)`.
  - Keep `STEEL_DENSITY_G_PER_CM3` in validators only if still referenced; otherwise remove it (grep `_steel_density_g_per_cm3` — it is used by `calculate_sheet_weight_kg`; once delegated, `_steel_density_g_per_cm3` and `_system_flt`/`STEEL_DENSITY_G_PER_CM3` may be dead — remove only confirmed-dead helpers).

- [ ] Run tests and see PASS: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators`
- [ ] Run the bom_service + release_service modules to confirm no numeric drift (characterization): `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_service` and `... test_release_service`.
- [ ] Run lint.
- [ ] Commit: `refactor: route validator weight formulas through services/geometry`

---

## Task group D — Native lifecycle spine

Resolves findings 1, 2, 3, 9, 10, 13, 14, 17, 32. **Behaviour change** throughout — this is the §4.2/§4.3 redesign. Sequence: D-1 (drop the override in hooks + controller plumbing, move release to `on_submit`) → D-2 (native BOM insert: set only input fields) → D-3 (native retire via `bom.cancel()`/deactivate on `on_cancel`) → D-4 (`ignore_linked_doctypes` + `on_trash`) → D-5 (the workflow-fixture change that makes `Supersede` drive `doc.cancel()` → `on_cancel`).

> **Why D-5 lands last in the group.** D-1..D-4 wire the `on_submit`/`on_cancel` handlers and verify cancellation via a **direct** native `layout.cancel()` call (which fires `on_cancel` regardless of workflow state). D-5 then makes the **user-facing `Supersede` workflow action** drive that same `doc.cancel()` by flipping the `Superseded` state to `doc_status: 2` and removing the unreachable `Cancel` state — so the whole release→supersede E2E path is native end-to-end. Without D-5 the plan would remove the old `before_cancel`/`deactivate_generated_bom` Supersede handler in D-1 yet leave the `Released --Supersede--> Superseded` transition firing **no** doc event (it stays a docstatus 1→1 `doc.save()`), leaving retirement unwired from the user's perspective.

> **Schema prerequisite (already satisfied by Group B).** The `release_layout` path exercised by D-2/D-4/D-5 writes the `finished_parts` mirror via `_sync_finished_part_reference_rows`, which sets each row's `generated_bom`. The `Layout Finished Part` doctype gains that `generated_bom` (Link → BOM) column in **Task B-2** (Group B runs before Group D in the A→B→C→D→E order), so the field exists by the time these D tests run. Do not re-add it here — confirm with `grep -n generated_bom sheet_cutting_layout/sheet_cutting_layout/doctype/layout_finished_part/layout_finished_part.json` before D-2; if Group B was skipped, run B-2 first.

> **Verified against installed source** (`erpnext/manufacturing/doctype/bom/bom.py` v15.101):
> - `BOM.on_cancel` (line 310): `db_set("is_active", 0)`, `db_set("is_default", 0)`, `validate_bom_links()`, `manage_default_bom()`. So cancelling an unused BOM deactivates it and re-points `Item.default_bom` natively.
> - `BOM.on_update_after_submit` (line 335): `validate_bom_links()` + `manage_default_bom()` — so setting `is_active=0` on a submitted BOM and saving is the native deactivate path.
> - `validate_bom_links` (line 979) only blocks when the BOM is a component of another **active** BOM.
> - `frappe/model/delete_doc.py:273,325,328,366`: `ignore_linked_doctypes` is honoured for `method == "Cancel"`, so listing `"BOM"` lets the layout cancel without unlinking the BOM backlink manually.
> - The Frappe `LinkExistsError` is raised by `check_if_doc_is_linked` when a submitted Work Order / Manufacture Stock Entry links the BOM; that is the signal to fall back to deactivate.

### Task D-1: drop the apply_workflow override and move release to on_submit

The `Released` workflow state has `doc_status = 1` (verified in `fixtures/workflow.json` line 30-34), so native `apply_workflow` (verified `frappe/model/workflow.py:130-144`: draft→submitted runs `doc.submit()`; submitted→cancelled runs `doc.cancel()`) calls `doc.submit()` when transitioning `Approved by Purchase --MR Release--> Released`. **`MR Release` is the only docstatus 0→1 transition in the workflow**, so `on_submit` fires only on release. Release therefore belongs in `on_submit`, not `validate()` reached via `before_workflow_action`/`frappe.flags.selected_workflow_action`. Remove the `override_whitelisted_methods` entry, the `apply_sheet_cutting_layout_workflow` whitelisted method, `before_workflow_action`, `_apply_workflow_action_effects`, `_get_selected_workflow_action`, the suppress-side-effects machinery, and the `frappe.flags` plumbing. Keep `record_approval_snapshot` (§7 theme 7 — IATF trail) but drive it from the doc-event hooks.

> **Post-merge state of release_service (read before editing the controller/release path).**
> - The "always persist the **in-memory** layout, never a re-fetched copy" fix is **ALREADY DONE** by the develop merge: `release_layout` calls `_save_layout_records((layout,))` directly (release_service ~lines 137-141). The old `_release_layout_records` and `_copy_generated_end_piece_item_links` helpers were **removed** in that merge — do **not** add a persist fix or try to edit those helpers; they no longer exist.
> - `_set_frappe_field_if_supported` was split into **three** helpers by the merge: `_field_is_supported(doc, fieldname) -> bool` (~line 600), `_set_frappe_field_if_supported(doc, fieldname, value)` (~line 607), and `_supported_field_values(doc, values) -> dict` (~line 612). Steps below that reference `_set_frappe_field_if_supported` still apply, but column-guarded writes now go through `_supported_field_values`.
> - `SUPPRESS_WORKFLOW_SIDE_EFFECTS_FLAG` (release_service ~line 30) and the `_save_layout_records` early-return that checks it (~lines 540-544) exist only to support the controller's suppress machinery driven from `validate()`. Once **this task (D-1)** removes that machinery, both the flag constant and the early-return guard become **dead** — remove the flag constant + its early-return branch as part of D-1 (and drop the `SUPPRESS_WORKFLOW_SIDE_EFFECTS_FLAG` member from the controller's `release_service` import on line 32).

> **Snapshot semantics (gating fix).** The old `_apply_workflow_action_effects` recorded a snapshot for *every* workflow action that mapped to a step name. Under the native model the in-app snapshot is driven from two doc events: `on_submit` records the **MR Release** snapshot (the only docstatus 0→1 transition reaches it), and `on_cancel` records the **Supersede** snapshot. So the `on_submit` snapshot call is **gated inside the `if status == "Released"` branch** — the label `"MR Release"` only fires on the one path that reaches `on_submit` with `status == "Released"`. (The intermediate draft→draft approval steps — Submit for Check / PM / Purchase — are not in scope for Phase 0; they are recorded by the existing native workflow audit and revisited if needed in a later phase.) **Implemented post-Phase-0 (2026-06-16):** those draft-approval snapshots were subsequently added via the controller's `on_update` → `_record_draft_workflow_snapshot`, persisted as `Layout Approval Snapshot` rows that are idempotent by `step_name` (`approval_snapshot_row` builds the row; `_insert_approval_snapshot_row` writes it). The migration-backfill patch was removed in favour of this live recording.
>
> **`Supersede` must be added to the snapshot action map.** `record_approval_snapshot` returns `False` for any action not in `services/workflow.py::APPROVAL_SNAPSHOT_ACTIONS` (verified: the map has `Submit for Check`, `Project Manager Approves`, `Purchase Approves`, `MR Release`, `Reject` — **no `Supersede`**). So `on_cancel` recording a `"Supersede"` snapshot is a no-op until `"Supersede"` is added to the map. This task adds that entry.

**Files:**
- Modify: `sheet_cutting_layout/hooks.py` (remove `override_whitelisted_methods` lines 36-41; later E-5 scopes the Custom Field fixture)
- Modify: `sheet_cutting_layout/services/workflow.py` (add `Supersede` to `APPROVAL_SNAPSHOT_ACTIONS`, line 24-30)
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py` (replace `validate`/`before_workflow_action`/`before_cancel`/`_apply_workflow_action_effects`/`apply_sheet_cutting_layout_workflow` + helpers)
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py` (rewrite the `before_workflow_action`/`apply_workflow`/`MR Release-via-validate` tests to the `on_submit` model)

- [ ] Add `"Supersede"` to `APPROVAL_SNAPSHOT_ACTIONS` in `services/workflow.py`. Add the module constant alongside the existing action constants (`PROJECT_MANAGER_APPROVAL_ACTION` line 18 … `REJECT_ACTION` line 22):

```python
SUPERSEDE_ACTION = "Supersede"
```

  and add the map entry (so `record_approval_snapshot(doc, action="Supersede", ...)` appends a row):

```python
APPROVAL_SNAPSHOT_ACTIONS: dict[str, str] = {
	SUBMIT_FOR_CHECK_ACTION: "Submit for Check",
	PROJECT_MANAGER_APPROVAL_ACTION: "Project Manager Approval",
	PURCHASE_APPROVAL_ACTION: "Purchase Approval",
	MR_RELEASE_ACTION: "MR Approval",
	REJECT_ACTION: "Rejection",
	SUPERSEDE_ACTION: "Supersession",
}
```

  The `decision` ladder in `record_approval_snapshot` already falls through to `"Approved"` for any action that is neither `Submit for Check` nor `Reject`; `Supersede` therefore records `decision="Approved"`, `step_name="Supersession"`. (No change needed to the ladder.)

- [ ] Write the failing test. Add to `TestSheetCuttingLayoutController` in `test_sheet_cutting_layout.py`:

```python
	def test_validate_only_runs_validator_no_workflow_side_effects(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"

		with patch.object(controller, "validate_sheet_cutting_layout") as validate:
			doc.validate()

		validate.assert_called_once_with(doc)
		self.assertFalse(hasattr(controller, "before_workflow_action"))
		self.assertFalse(hasattr(controller, "apply_sheet_cutting_layout_workflow"))

	def test_on_submit_releases_and_snapshots_when_status_released(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"
		doc.status = "Released"

		with (
			patch.object(controller, "release_layout") as release,
			patch.object(controller, "record_approval_snapshot") as snapshot,
			patch.object(controller, "_get_session_user", return_value="Administrator"),
			patch.object(controller, "_get_now_datetime", return_value="2026-06-13T12:00:00"),
		):
			doc.on_submit()

		release.assert_called_once_with(doc)
		snapshot.assert_called_once_with(
			doc,
			action="MR Release",
			approver="Administrator",
			decision_time="2026-06-13T12:00:00",
		)

	def test_on_submit_does_not_snapshot_or_release_when_not_released(self) -> None:
		# on_submit only ever runs on the MR Release transition (the sole 0->1 path),
		# but guard the label: a non-Released status must not record an MR Release
		# snapshot nor release.
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"
		doc.status = "Approved by Purchase"

		with (
			patch.object(controller, "release_layout") as release,
			patch.object(controller, "record_approval_snapshot") as snapshot,
		):
			doc.on_submit()

		release.assert_not_called()
		snapshot.assert_not_called()

	def test_on_cancel_retires_and_snapshots_supersede(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"

		with (
			patch.object(controller, "retire_layout") as retire,
			patch.object(controller, "record_approval_snapshot") as snapshot,
			patch.object(controller, "_get_session_user", return_value="Administrator"),
			patch.object(controller, "_get_now_datetime", return_value="2026-06-13T12:00:00"),
		):
			doc.on_cancel()

		retire.assert_called_once_with(doc)
		snapshot.assert_called_once_with(
			doc,
			action="Supersede",
			approver="Administrator",
			decision_time="2026-06-13T12:00:00",
		)
```

  Delete the obsolete `test_validate_mr_release_records_snapshot_and_release_once` (merged module line 48) and `test_apply_workflow_sets_selected_action_only_for_sheet_cutting_layout` (line 113) tests (they assert the removed override path). Also replace `test_validate_delegates_to_validator` (merged module line 36) — it patches the now-deleted `controller._get_selected_workflow_action` — with `test_validate_only_runs_validator_no_workflow_side_effects` above (which patches only `validate_sheet_cutting_layout`).

- [ ] Run it and see it FAIL: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout`
  - Expected failure: `AttributeError: 'SheetCuttingLayout' object has no attribute 'on_submit'` (no `on_submit` yet); and `assertFalse(hasattr(controller, "apply_sheet_cutting_layout_workflow"))` fails because that whitelisted function still exists.

- [ ] Implement in the controller. Replace the class body (`before_insert` may stay; rewrite the rest):

```python
class SheetCuttingLayout(Document):
	ignore_linked_doctypes = ["BOM"]

	def before_insert(self) -> None:
		_clear_copied_release_artifacts(self)

	def validate(self) -> None:
		validate_sheet_cutting_layout(self)

	def on_submit(self) -> None:
		# on_submit fires only on the docstatus 0->1 transition, which in this
		# workflow is exactly `Approved by Purchase --MR Release--> Released`.
		# Gate the snapshot label inside the Released branch so "MR Release" only
		# labels the one path that reaches on_submit at status Released.
		if getattr(self, "status", None) == "Released":
			_record_workflow_snapshot(self, action="MR Release")
			release_layout(self)

	def on_cancel(self) -> None:
		# Supersede == cancel (spec 4.2): the docstatus 1->2 transition
		# `Released --Supersede--> Superseded` runs doc.cancel() -> on_cancel.
		_record_workflow_snapshot(self, action="Supersede")
		retire_layout(self)

	def on_trash(self) -> None:
		_clear_rejected_workflow_actions(self)
```

  - Add a small helper `_record_workflow_snapshot(doc, *, action)` that calls `record_approval_snapshot(doc, action=action, approver=_get_session_user(), decision_time=_get_now_datetime())`.
  - Move the existing `on_trash` Workflow-Action cleanup body into `_clear_rejected_workflow_actions(self)` (it already exists as the `on_trash` body lines 58-78 — extract it; keep the `status == "Rejected"` guard).
    > **Refined post-Phase-0 (2026-06-16):** the `status == "Rejected"` guard was dropped — `on_trash` now clears stale `Workflow Action` rows for **any** status — and a sibling `_clear_cancelled_bom_links(self)` was added that nulls the `sheet_cutting_layout` backlink on the layout's **cancelled** (`docstatus=2`) BOMs. Together these clear the app's own residue so Frappe's link validation doesn't block a genuine delete (active/submitted BOM / Work Order / Stock Entry still block natively). See spec §4.3.
  - Delete `before_workflow_action`, `_apply_workflow_action_effects`, `_get_selected_workflow_action`, `_suppress_workflow_side_effects`, `_workflow_side_effects_are_suppressed`, and the whitelisted `apply_sheet_cutting_layout_workflow` function. The old `before_cancel` (which wrote `self.status = "Cancel"` — that state is removed in D-5) is deleted; native `doc.cancel()` sets `docstatus = 2` and `apply_workflow` sets `status = "Superseded"`.
  - `retire_layout` is imported from `release_service` (introduced in D-3); for D-1 add a temporary `retire_layout` import alias to the existing `cancel_generated_bom` so the module imports cleanly, e.g. `from sheet_cutting_layout.services.release_service import cancel_generated_bom as retire_layout` — D-3 replaces it with the real `retire_layout`. (`on_cancel` calls `retire_layout(self)`, which resolves through this alias until D-3.)
  - Drop the now-dead `SUPPRESS_WORKFLOW_SIDE_EFFECTS_FLAG` member from the controller's `release_service` import (merged controller line 32) — it was only referenced by the suppress machinery being deleted. Per the post-merge note above, also delete the `SUPPRESS_WORKFLOW_SIDE_EFFECTS_FLAG` constant and the `_save_layout_records` early-return guard in `release_service.py` (they become dead with the controller suppress machinery gone).

- [ ] In `hooks.py`, delete the `override_whitelisted_methods = { "frappe.model.workflow.apply_workflow": ... }` block (lines 36-41).

- [ ] Run tests and see PASS: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout`
- [ ] Run lint.
- [ ] Commit: `refactor: drive release from on_submit; drop apply_workflow override`

### Task D-2: native BOM insert sets only input fields

**Behaviour change** (finding 32, 7, 23, 24). `_insert_frappe_bom` (release_service lines 368-429) sets `bom_doc.uom = "Kg"` (overwritten by `validate_main_item`), `is_active`/`disabled`/`status` pre-submit, and the scrap `rate` (let BOM compute via `get_rm_rate`). Set only input fields; let the BOM controller compute the rest. Likewise the end-piece BOM in `end_piece_bom_service._create_end_piece_bom` (lines 89-141) sets `bom.uom`, `stock_uom`/`stock_qty`/`conversion_factor` on items (let `update_stock_qty` compute), and `is_active`/`disabled`/`status`.

**Files:**
- Modify: `sheet_cutting_layout/services/release_service.py` (`_insert_frappe_bom` lines 368-429)
- Modify: `sheet_cutting_layout/services/end_piece_bom_service.py` (`_create_end_piece_bom` lines 89-141)
- Modify: `sheet_cutting_layout/services/bom_service.py` (`resolve_scrap_item_rate` / `_insert_frappe_bom` no longer need the rate; keep `resolve_scrap_item_rate` only if still used — see step)
- Test: `sheet_cutting_layout/tests/test_release_service.py` + `test_end_piece_bom_service.py` (integration: assert the BOM is created and `validate()` computes the omitted fields)

- [ ] Write the failing integration test. Add to the bench-gated section of `test_release_service.py` (uses real `frappe`; pattern from `test_sheet_cutting_layout.py::test_mr_release_generates_native_bom_with_test_uom_items`):

```python
	def test_generated_bom_lets_controller_compute_uom_and_status(self) -> None:
		# Build a layout via the controller path and submit it; assert the BOM
		# the app inserted carries the FG item's stock UOM (set by validate_main_item),
		# not a hard-coded "Kg", and is active because submit ran manage_default_bom.
		import frappe

		from sheet_cutting_layout.tests.factories import make_release_ready_layout

		# make_release_ready_layout inserts + registers, sets status "Approved by
		# Purchase" and net == gross, and reloads — i.e. the full release-gate
		# boilerplate. Submitting then drives the MR Release (docstatus 0->1) path.
		layout = make_release_ready_layout()
		layout.submit()  # Released state has docstatus 1; native submit runs on_submit

		self.assertEqual(layout.status, "Released")
		self.assertTrue(layout.generated_bom)
		bom = frappe.get_doc("BOM", layout.generated_bom)
		self.assertEqual(bom.is_active, 1)
		# FG item stock_uom is "Nos" (the factory sets it); validate_main_item set bom.uom.
		self.assertEqual(bom.uom, frappe.db.get_value("Item", layout.finished_part_code, "stock_uom"))
```

  > Note: this also exercises the new `on_submit` path end-to-end (replacing the old `validate()`-with-patched-action test). `make_release_ready_layout` is imported from `sheet_cutting_layout.tests.factories` (where `make_layout`/`make_release_ready_layout` permanently live after the develop merge — pinned in A-2); it is **not** imported from the doctype test module.

- [ ] Run it and see it FAIL: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service`
  - Expected failure: `AssertionError: 'Kg' != 'Nos'` because `_insert_frappe_bom` hard-codes `bom_doc.uom = "Kg"`, which currently survives (or, depending on validate ordering, the assertion still pins the bug).

- [ ] Implement `_insert_frappe_bom` (release_service): remove `bom_doc.uom = "Kg"`, `bom_doc.is_active = 1`, `bom_doc.disabled = 0`, the `if hasattr(bom_doc, "status"): bom_doc.status = "Active"` block, and the scrap `rate=rate` (and the whole `resolve_scrap_item_rate` try/except around it). The scrap row becomes `{"item_code": row.item_code, "stock_qty": row.qty, "qty": row.qty, "uom": row.uom}` — let BOM compute `rate` via `get_rm_rate`. Keep `bom_doc.item`, `bom_doc.company`, `bom_doc.quantity`, `bom_doc.custom_operation = "Shearing"`, `bom_doc.sheet_cutting_layout`, `mark_bom_app_controlled(bom_doc)`, the items append (item_code/qty/uom only), `bom_doc.insert()`, `bom_doc.submit()`. After submit, drop the lines that copy `is_active`/`disabled`/`status` back onto the `BomDocument` dataclass (or read them from `bom_doc` for the return value).

- [ ] Implement `_create_end_piece_bom` (end_piece_bom_service): remove `bom.uom = "Kg"`, `bom.is_active = 1`, `bom.disabled = 0`, the `status` block; in the items append drop `stock_uom`/`stock_qty`/`conversion_factor` (keep `item_code`/`qty`/`uom`); in the scrap append drop the resolved `rate` (keep `item_code`/`stock_qty`/`qty`/`uom`). Keep `bom.item`, `bom.company`, `bom.quantity`, `bom.custom_operation`, `bom.sheet_cutting_layout`, `mark_bom_app_controlled`, `bom.insert(ignore_permissions=True)` (revisited in E-4), `bom.submit()`.

- [ ] If `resolve_scrap_item_rate` / `_fetch_valuation_rate` in `bom_service.py` are now unused, grep (`grep -rn resolve_scrap_item_rate sheet_cutting_layout`) and remove them + their tests; if still referenced elsewhere, leave them.

- [ ] Run tests and see PASS: the new integration test, plus `test_bom_service`, `test_end_piece_bom_service`, `test_release_service`. Fix any characterization test that asserted the removed `rate`/`status`/`uom` fields (those were pinning the now-removed behaviour — update them to assert the controller-computed values instead).
- [ ] Run lint.
- [ ] Commit: `fix: let BOM controller compute uom, status, and scrap rate`

### Task D-3: retire BOMs natively on cancel (bom.cancel() with deactivate fallback)

**Behaviour change** (findings 1, 2, 9, 13, 14). Replace `deactivate_generated_bom` + `cancel_generated_bom` + `_clear_item_default_bom_reference` + the savepoint/backlink-unlink helpers with one `retire_layout(layout)` that, for each generated BOM, attempts native `bom.cancel()` and on `frappe.LinkExistsError` falls back to native deactivate (`bom.is_active = 0` + `bom.save()`, which runs `on_update_after_submit` → `manage_default_bom`). The layout's own backlink no longer needs manual clearing because `ignore_linked_doctypes = ["BOM"]` (D-4) exempts it.

**Files:**
- Modify: `sheet_cutting_layout/services/release_service.py` (delete `deactivate_generated_bom` lines 140-166, `cancel_generated_bom` lines 169-212, `_clear_item_default_bom_reference` 215-228, `_db_savepoint`/`_db_rollback_to_savepoint` 231-248, `_unlink_layout_bom_reference_fields` 276-299, `_unlink_generated_bom_from_layout` 614-625, `_unlink_layout_from_generated_bom` 628-640; add `retire_layout`)
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py` (replace the temporary `retire_layout` alias import with the real one)
- Test: `sheet_cutting_layout/tests/test_release_service.py` (unit-level `retire_layout` behaviour with a fake BOM)

- [ ] Write the failing test. Add to `TestReleaseService`:

```python
	def test_retire_layout_cancels_unused_bom(self) -> None:
		from sheet_cutting_layout.services import release_service

		cancelled: list[str] = []

		class FakeBom:
			def __init__(self, name: str) -> None:
				self.name = name
				self.docstatus = 1
				self.is_active = 1

			def cancel(self) -> None:
				cancelled.append(self.name)
				self.docstatus = 2
				self.is_active = 0

		fake_boms = {"BOM-X": FakeBom("BOM-X")}

		class FakeFrappe:
			class db:
				@staticmethod
				def get_all(doctype, filters=None, pluck=None):
					return []

			@staticmethod
			def get_doc(doctype, name):
				return fake_boms[name]

			class LinkExistsError(Exception):
				pass

		layout = Layout()
		layout.generated_bom = "BOM-X"

		with patch.object(release_service, "frappe", FakeFrappe):
			release_service.retire_layout(layout)

		self.assertEqual(cancelled, ["BOM-X"])

	def test_retire_layout_deactivates_when_cancel_blocked(self) -> None:
		from sheet_cutting_layout.services import release_service

		saved_active: list[int] = []

		class FakeFrappe:
			class db:
				@staticmethod
				def get_all(doctype, filters=None, pluck=None):
					return []

			class LinkExistsError(Exception):
				pass

			@staticmethod
			def get_doc(doctype, name):
				return bom

		class FakeBom:
			def __init__(self) -> None:
				self.name = "BOM-USED"
				self.docstatus = 1
				self.is_active = 1

			def cancel(self) -> None:
				raise FakeFrappe.LinkExistsError("used by Work Order")

			def save(self, ignore_permissions: bool = False) -> None:
				saved_active.append(self.is_active)

		bom = FakeBom()
		layout = Layout()
		layout.generated_bom = "BOM-USED"

		with patch.object(release_service, "frappe", FakeFrappe):
			release_service.retire_layout(layout)

		self.assertEqual(bom.is_active, 0)
		self.assertEqual(saved_active, [0])
```

- [ ] Run it and see it FAIL: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service`
  - Expected failure: `AttributeError: module 'sheet_cutting_layout.services.release_service' has no attribute 'retire_layout'`.

- [ ] Implement `retire_layout` in `release_service.py`:

```python
def retire_layout(layout: object) -> None:
	"""Deactivate every BOM this layout generated, natively.

	Attempt native cancel (unused BOM -> is_active=0, docstatus=2). If the BOM
	is consumed by a submitted Work Order / Manufacture Stock Entry, Frappe
	raises LinkExistsError; fall back to native deactivate (is_active=0 +
	save -> on_update_after_submit -> validate_bom_links + manage_default_bom).
	The layout's own BOM backlink is exempt via ignore_linked_doctypes=["BOM"].
	"""
	for bom_name in _layout_bom_names(layout):
		bom_doc = frappe.get_doc("BOM", bom_name)
		if _is_cancelled_document(bom_doc):
			continue
		try:
			bom_doc.cancel()
		except frappe.LinkExistsError:
			bom_doc.is_active = 0
			bom_doc.save(ignore_permissions=True)
```

  Keep `_layout_bom_names` (it gathers `layout.generated_bom`, the `finished_parts[*].generated_bom`, `end_pieces[*].generated_end_piece_bom`, and BOMs filtered by `sheet_cutting_layout == layout.name`). Keep `_is_cancelled_document`. Delete `deactivate_generated_bom`, `cancel_generated_bom`, `_clear_item_default_bom_reference`, `_db_savepoint`, `_db_rollback_to_savepoint`, `_unlink_layout_bom_reference_fields`, `_db_set_child_field`, `_unlink_generated_bom_from_layout`, `_unlink_layout_from_generated_bom`, and the `_set_frappe_field_if_supported` calls that wrote `is_active`/`disabled`/`status` for retirement.

- [ ] In the controller, change the import to the real symbol: `from sheet_cutting_layout.services.release_service import release_layout, retire_layout` and remove the temporary `cancel_generated_bom as retire_layout` alias. Confirm `on_cancel` calls `retire_layout(self)`.

- [ ] Update/remove the old `test_release_service.py` tests that exercised `deactivate_generated_bom` / `cancel_generated_bom` / savepoint rollback (they test deleted symbols). Replace their intent with `retire_layout` tests where still meaningful.

- [ ] Run tests and see PASS: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service`
- [ ] Run lint.
- [ ] Commit: `refactor: retire generated BOMs via native cancel/deactivate`

### Task D-4: ignore_linked_doctypes + framework-gated delete integration test

**Behaviour change** (findings 9, 17, §4.3). Confirm `ignore_linked_doctypes = ["BOM"]` (set on the class in D-1) lets a released layout cancel cleanly, that `on_cancel` deactivates its BOM, and that delete is purely framework-gated. Drive cancellation via native `doc.cancel()`, not the removed `status = "Cancel"` write.

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py` (verify `on_cancel`/`ignore_linked_doctypes`; ensure no leftover `status = "Cancel"` from the old `before_cancel`)
- Test: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py` (bench-gated integration)

- [ ] Write the failing integration test (bench runtime). Add to `TestSheetCuttingLayoutController`:

```python
	def test_cancel_released_layout_deactivates_bom_natively(self) -> None:
		import frappe

		# make_release_ready_layout (tests.factories) inserts + registers and puts
		# the layout in the release-gate state (Approved by Purchase, net == gross).
		layout = make_release_ready_layout()
		layout.status = "Released"
		layout.submit()
		bom_name = layout.generated_bom
		self.assertEqual(frappe.db.get_value("BOM", bom_name, "is_active"), 1)

		layout.cancel()  # native cancel -> on_cancel -> retire_layout

		self.assertEqual(frappe.db.get_value("BOM", bom_name, "is_active"), 0)
		self.assertEqual(frappe.db.get_value("Sheet Cutting Layout", layout.name, "docstatus"), 2)
```

  > `make_release_ready_layout` and `make_layout` are imported from `sheet_cutting_layout.tests.factories` (already imported at the top of `test_sheet_cutting_layout.py`, lines 11-15 after the merge); they no longer live in this module.

- [ ] Run it and see it FAIL: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout`
  - Expected failure: without `ignore_linked_doctypes` taking effect (or with leftover `status="Cancel"` writes conflicting with native cancel), `layout.cancel()` raises a `LinkExistsError` for the BOM backlink, or the BOM stays `is_active=1`.

- [ ] Implement: ensure the controller has `ignore_linked_doctypes = ["BOM"]` (from D-1) and that `on_cancel` calls `_record_workflow_snapshot(self, action="Supersede")` then `retire_layout(self)` — no `status = "Cancel"` assignment (the old `before_cancel` is gone; native cancel sets `docstatus=2`). At this point the `Superseded` state is still `doc_status: 1`; this D-4 test exercises cancellation via a **direct** `layout.cancel()` call, which fires `on_cancel` independent of the workflow transition. D-5 then makes the user-facing `Supersede` action reach `doc.cancel()` by flipping `Superseded` to `doc_status: 2` and removing the unreachable `Cancel` state. Note in the commit body that the `Supersede`-action path is wired in D-5.

- [ ] Run tests and see PASS.
- [ ] Run the full suite: `bench --site development.localhost run-tests --app sheet_cutting_layout`
- [ ] Run lint.
- [ ] Commit: `feat: cancel layouts natively via ignore_linked_doctypes`

### Task D-5: make Supersede drive doc.cancel() via the workflow fixture (Superseded → doc_status 2; remove Cancel)

**Behaviour change** (finding 17, §4.2). This is what wires the **user-facing** `Supersede` action to `on_cancel`. Today `fixtures/workflow.json` has `Superseded` at `doc_status: "1"` and an unreachable `Cancel` state at `doc_status: "2"`. The `Released --Supersede--> Superseded` transition is therefore submitted(1)→submitted(1), which native `apply_workflow` runs as `doc.save()` (verified `frappe/model/workflow.py:141-142`) — **no doc event fires**. Set `Superseded` to `doc_status: "2"` so the transition becomes submitted(1)→cancelled(2), which `apply_workflow` runs as `doc.cancel()` (verified `frappe/model/workflow.py:143-144`) → `on_cancel` → `_record_workflow_snapshot(action="Supersede")` + `retire_layout`. Remove the unreachable `Cancel` state, its `"Cancel"` entry in the SCL `status` Select options, and `"Cancel"` from the `hooks.py` `Workflow State` fixture filter list. `Superseded` becomes the single docstatus-2 retirement state.

> **Verified ground truth** (`sheet_cutting_layout/fixtures/workflow.json`): the retirement action is **`Supersede`** (`Released --Supersede--> Superseded`, allowed `System Manager`, transitions line 94-99). There is **no `Cancel` action/transition** — `Cancel` is only a dead `doc_status: "2"` state (states line 45-49) with no inbound transition. `Released` is `doc_status: "1"` (states line 30-34) and `Superseded` is `doc_status: "1"` (states line 40-44). After this change, `Superseded` is `doc_status: "2"` and the `Cancel` state is deleted.

**Files:**
- Modify: `sheet_cutting_layout/fixtures/workflow.json` (set `Superseded` state `doc_status` `"1"` → `"2"`, line 42; delete the `Cancel` state object, lines 45-49)
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json` (remove `Cancel` from the `status` field `options`, line 289)
- Modify: `sheet_cutting_layout/hooks.py` (remove `"Cancel"` from the `Workflow State` fixture filter `name in [...]` list, lines 16-24)
- Test: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py` (bench-gated integration: supersede via `apply_workflow` drives docstatus 2 and `on_cancel` retires the BOM)

- [ ] Write the failing integration test (bench runtime). Add to `TestSheetCuttingLayoutController` in `test_sheet_cutting_layout.py` (reuses `make_release_ready_layout`, imported from `sheet_cutting_layout.tests.factories` at the top of the module):

```python
	def test_supersede_action_cancels_layout_and_retires_bom(self) -> None:
		import frappe
		from frappe.model.workflow import apply_workflow

		# make_release_ready_layout (tests.factories) inserts + registers and puts
		# the layout in the release-gate state (Approved by Purchase, net == gross).
		layout = make_release_ready_layout()
		layout.status = "Released"
		layout.submit()  # MR Release path: docstatus 0 -> 1, on_submit releases
		bom_name = layout.generated_bom
		self.assertTrue(bom_name)
		self.assertEqual(frappe.db.get_value("BOM", bom_name, "is_active"), 1)

		# User-facing Supersede action: Superseded is doc_status 2, so native
		# apply_workflow runs doc.cancel() -> on_cancel -> retire_layout.
		apply_workflow(layout, "Supersede")

		layout.reload()
		self.assertEqual(layout.status, "Superseded")
		self.assertEqual(
			frappe.db.get_value("Sheet Cutting Layout", layout.name, "docstatus"), 2
		)
		self.assertEqual(frappe.db.get_value("BOM", bom_name, "is_active"), 0)

	def test_cancel_is_not_a_workflow_state(self) -> None:
		import frappe

		workflow = frappe.get_doc("Workflow", "Sheet Cutting Layout Approval Workflow")
		state_names = {state.state for state in workflow.states}
		self.assertNotIn("Cancel", state_names)
		superseded = next(s for s in workflow.states if s.state == "Superseded")
		self.assertEqual(int(superseded.doc_status), 2)
```

- [ ] Run it and see it FAIL: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout`
  - Expected failure: with `Superseded` still at `doc_status: "1"`, `apply_workflow(layout, "Supersede")` runs `doc.save()` (submitted→submitted), so `on_cancel` never fires, the BOM stays `is_active=1`, and `docstatus` stays `1`; `test_cancel_is_not_a_workflow_state` also fails because the `Cancel` state is still present and `Superseded.doc_status` is still `1`.

- [ ] Implement — in `fixtures/workflow.json`, change the `Superseded` state's `doc_status` from `"1"` to `"2"`:

```json
   {
    "allow_edit": "System Manager",
    "doc_status": "2",
    "state": "Superseded"
   }
```

  and delete the entire `Cancel` state object (the trailing element of the `states` array):

```json
   ,
   {
    "allow_edit": "System Manager",
    "doc_status": "2",
    "state": "Cancel"
   }
```

  (Leave all `transitions` untouched — `Supersede` already targets `Superseded`; no transition referenced `Cancel`.)

- [ ] In `sheet_cutting_layout.json`, change the `status` field `options` (line 289) from
  `"Draft\nSubmitted for Check\nPM Approved\nApproved by Purchase\nReleased\nRejected\nSuperseded\nCancel"`
  to
  `"Draft\nSubmitted for Check\nPM Approved\nApproved by Purchase\nReleased\nRejected\nSuperseded"` (drop the trailing `\nCancel`).

- [ ] In `hooks.py`, remove `"Cancel"` from the `Workflow State` fixture filter `name in [...]` list (it currently lists `Draft, Submitted for Check, PM Approved, Approved by Purchase, Released, Rejected, Superseded, Cancel` — drop `"Cancel,"`).

- [ ] Run `bench --site development.localhost migrate` from bench root to re-sync the workflow + doctype fixtures (dev-only hard-reset policy; this updates the live `Workflow` and `Superseded` state `doc_status`). Then delete the now-orphaned `Cancel` Workflow State if it lingers: `bench --site development.localhost console` → `frappe.delete_doc("Workflow State", "Cancel", ignore_missing=True, force=True); frappe.db.commit()` (the `Cancel` Workflow State doc is no longer exported, so a stale row may remain after migrate).

- [ ] Run tests and see PASS: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout`
- [ ] Run the full suite: `bench --site development.localhost run-tests --app sheet_cutting_layout`
- [ ] Validate JSON: `python -m json.tool sheet_cutting_layout/fixtures/workflow.json > /dev/null && python -m json.tool sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json > /dev/null`
- [ ] Run lint over `hooks.py`.
- [ ] Commit: `feat: supersede drives native cancel; drop unreachable Cancel state`

---

## Task group E — Remaining conformance

Resolves findings 4, 6, 7, 8, 12, 25, 26, 27, 28, 29, 30, 33, 35. Each task is small and behind a test. (Findings 6, 7, 23, 24, 32 were folded into D-2; 1, 2, 9, 13, 14 into D-3; 3, 10 into D-1; 17 into D-5; 11, 15, 16, 18, 31, 34, 36 into Group A; 19-22 into B-3.)

### Task E-1: BomDocument drops non-schema status/disabled fields

**Behaviour change** (finding 7). The frappe-free `BomDocument` dataclass (bom_service lines 58-68) carries `disabled` and `status` that mirror non-input BOM fields. After D-2 nothing reads them for persistence. Reduce the dataclass to the input fields BOM actually accepts (`item`, `name`, `quantity`, `sheet_cutting_layout`, `is_active`, `items`, `scrap_items`); drop `disabled` and `status`.

**Files:**
- Modify: `sheet_cutting_layout/services/bom_service.py` (`BomDocument` lines 58-68)
- Modify: `sheet_cutting_layout/services/release_service.py` (`BomRecord` Protocol lines 66-74, `_activate_boms` 463-467, `_save_bom_records` 529-541 — drop `disabled`/`status` writes)
- Test: `sheet_cutting_layout/tests/test_bom_service.py`

- [ ] Grep usages first: `grep -rn "\.disabled\b\|\.status\b" sheet_cutting_layout/services/bom_service.py sheet_cutting_layout/services/release_service.py`.
- [ ] Write the failing test (add to `TestBomService`):

```python
	def test_bom_document_has_no_status_or_disabled_fields(self) -> None:
		from sheet_cutting_layout.services.bom_service import BomDocument

		bom = BomDocument(item="X")
		self.assertFalse(hasattr(bom, "status"))
		self.assertFalse(hasattr(bom, "disabled"))
```

- [ ] Run it and see it FAIL — `AssertionError: True is not false` because `BomDocument` still declares `status`/`disabled`.
- [ ] Implement: remove `disabled: bool = False` and `status: str = "Active"` from `BomDocument`. In `release_service`, drop `disabled`/`status` from the `BomRecord` Protocol, `_activate_boms` (keep only `is_active = True`), and `_save_bom_records` (drop the two `_set_frappe_field_if_supported(..., "disabled"/"status", ...)` lines). Fix any test asserting `bom.status`/`bom.disabled`.
- [ ] Run tests and see PASS (`test_bom_service`, `test_release_service`).
- [ ] Run lint.
- [ ] Commit: `refactor: drop non-schema status/disabled from BomDocument`

### Task E-2: _company_for_layout uses erpnext.get_default_company

**Behaviour change** (finding 26). Both `release_service._company_for_layout` (lines 578-598) and `end_piece_bom_service._company_for_layout` (lines 230-251) reimplement company resolution. Replace the fallback ladder with `erpnext.get_default_company()` (verified present at `erpnext/__init__.py:10`).

**Files:**
- Modify: `sheet_cutting_layout/services/release_service.py` (`_company_for_layout` 578-598)
- Modify: `sheet_cutting_layout/services/end_piece_bom_service.py` (`_company_for_layout` 230-251)
- Test: `sheet_cutting_layout/tests/test_release_service.py` + `test_end_piece_bom_service.py`

- [ ] Write the failing test (add to `TestReleaseService`):

```python
	def test_company_for_layout_falls_back_to_erpnext_default(self) -> None:
		from sheet_cutting_layout.services import release_service

		layout = Layout()
		layout.company = None
		with patch("erpnext.get_default_company", return_value="ACME") as spy:
			company = release_service._company_for_layout(layout)
		self.assertEqual(company, "ACME")
		spy.assert_called_once()
```

- [ ] Run it and see it FAIL — current code does not call `erpnext.get_default_company`; it uses `frappe.defaults.get_user_default("Company")`, so the patch is never hit and `company` resolves differently (or throws).
- [ ] Implement both helpers as:

```python
def _company_for_layout(layout: object | None) -> str:
	if layout is not None:
		company = getattr(layout, "company", None)
		if company:
			return company

	import erpnext

	company = erpnext.get_default_company()
	if company:
		return company

	frappe.throw(_("Company is required to create generated BOMs"))
	raise RuntimeError("Company is required to create generated BOMs")
```

  (end_piece_bom_service version uses `_clean(getattr(layout, "company", None))` for the layout branch, matching its existing `_clean` usage.)
- [ ] Run tests and see PASS.
- [ ] Run lint.
- [ ] Commit: `refactor: resolve BOM company via erpnext.get_default_company`

### Task E-3: end-piece Item lookups use get_cached_value + None guard; valuation backfill via doc.save()

**Behaviour change** (findings 8, 25, 27, 28). In `end_piece_item_service.py`: `_get_value` (lines 221-229) uses `frappe.db.get_value` for stable Item config — switch to `frappe.get_cached_value` and guard a `None` name (return `None` instead of querying). `_ensure_existing_item_valuation_rate` (lines 177-192) backfills `valuation_rate` via `frappe.db.set_value` — switch to loading the Item doc and `doc.save()` so Item hooks run. In `end_piece_bom_service._persist_generated_links` (lines 170-219) replace the `_db_set` fallback ladder with direct `doc.db_set(...)`.

**Files:**
- Modify: `sheet_cutting_layout/services/end_piece_item_service.py` (`_get_value` 221-229; `_ensure_existing_item_valuation_rate` 177-192)
- Modify: `sheet_cutting_layout/services/end_piece_bom_service.py` (`_persist_generated_links` 170-219; `_db_set` 199-217)
- Test: `sheet_cutting_layout/tests/test_end_piece_bom_service.py`

- [ ] Write the failing test (add to the end-piece-item test class):

```python
	def test_get_value_returns_none_for_missing_name_without_query(self) -> None:
		from sheet_cutting_layout.services import end_piece_item_service

		# None name must short-circuit, never hitting the cache/db lookup.
		self.assertIsNone(end_piece_item_service._get_value("Item", None, "item_group"))

	def test_get_value_uses_get_cached_value(self) -> None:
		from sheet_cutting_layout.services import end_piece_item_service

		with patch("frappe.get_cached_value", return_value="GRP") as spy:
			result = end_piece_item_service._get_value("Item", "SOME-ITEM", "item_group")
		self.assertEqual(result, "GRP")
		spy.assert_called_once_with("Item", "SOME-ITEM", "item_group")
```

  (Add `from unittest.mock import patch` to the module imports if missing.)
- [ ] Run it and see it FAIL — `_get_value` currently calls `frappe.db.get_value`, not `frappe.get_cached_value`, and does not short-circuit on `None`.
- [ ] Implement `_get_value`:

```python
def _get_value(doctype: str, name: str | None, fieldname: str) -> object:
	if name is None or (isinstance(name, str) and not name.strip()):
		return None
	return frappe.get_cached_value(doctype, name, fieldname)
```

- [ ] Implement `_ensure_existing_item_valuation_rate`: after computing `raw_material_valuation_rate` and confirming it is positive, load the Item and save:

```python
	item = frappe.get_doc("Item", item_code)
	item.valuation_rate = raw_material_valuation_rate
	item.save(ignore_permissions=True)
```

  (Replaces the `frappe.db.set_value("Item", item_code, "valuation_rate", ...)` block.)
- [ ] Implement `_persist_generated_links`: for the submitted-layout branch, call `row.db_set("end_piece_item_code", ..., update_modified=False)` and `row.db_set("generated_end_piece_bom", ..., update_modified=False)` directly, and `layout.db_set("end_piece_bom_status", ..., update_modified=True)` directly; for the draft branch keep `layout.save(ignore_permissions=True)`. Delete the `_db_set` fallback-ladder helper.
- [ ] Run tests and see PASS (`test_end_piece_bom_service`).
- [ ] Run lint.
- [ ] Commit: `refactor: use cached Item lookups and native save for end-piece item config`

### Task E-4: end-piece Item insert justifies or drops ignore_permissions; UOM rows minimal

**Behaviour change** (findings 29, 30). `ensure_end_piece_item` inserts the Item with `ignore_permissions=True` (line 134) — replace the blanket elevation with an explicit permission check (`frappe.has_permission("Item", "create")`) and only elevate within an audited path, or drop it if the whitelisted entry point already checks `write` on the layout (it does, via `generate_sheet_cutting_layout_end_piece_boms`). Decision: keep `ignore_permissions=True` but document the justification (the operation is system-generated downstream of a permission-checked layout action) in a comment — **and** keep the UOM-row append minimal: `_append_app_created_item_uoms` already appends both the stock UOM and a converting UOM; per finding 29 append only the non-stock UOM and let the controller add the stock UOM row. Verify Frappe's Item controller auto-adds the stock UOM row before changing.

**Files:**
- Modify: `sheet_cutting_layout/services/end_piece_item_service.py` (`ensure_end_piece_item` line 134; `_append_app_created_item_uoms` 165-174)
- Test: `sheet_cutting_layout/tests/test_end_piece_bom_service.py` (bench-gated: insert an end-piece Item, assert UOM rows)

- [ ] Verify Frappe behaviour: from bench root `bench --site development.localhost console`, then `import frappe; i = frappe.new_doc("Item"); i.item_code="SCLTEST-UOM-PROBE"; i.item_group="All Item Groups"; i.stock_uom="Kg"; i.insert(ignore_permissions=True); print([u.uom for u in i.uoms])`. If the stock UOM `Kg` row is auto-present, the app should append only the non-stock `Nos` row. Record the result; if Frappe does **not** auto-add it, keep both appends and skip the UOM change (note in commit).
- [ ] Write the failing/characterization test (bench-gated) asserting the resulting `uoms` contain exactly the expected rows (stock UOM once, non-stock UOM once — no duplicate stock row).
- [ ] Run it and see it FAIL if a duplicate stock-UOM row currently appears (Frappe auto-adds it plus the app's explicit append).
- [ ] Implement per the probe result:
  - Add a comment above the `item.insert(ignore_permissions=True)` justifying it: `# System-generated Item downstream of a write-permission-checked layout action.`
  - If the probe showed Frappe auto-adds the stock UOM: change `_append_app_created_item_uoms` to append only the non-stock converting UOM (`Nos` when stock is `Kg`; `Kg` when stock is `Nos`).
- [ ] Run tests and see PASS.
- [ ] Run lint.
- [ ] Commit: `refactor: minimize app-created Item UOM rows and document insert elevation`

### Task E-5: scope the Custom Field fixture to BOM

**Behaviour change** (finding 4). `hooks.py` line 33 exports Custom Fields for `["BOM", "Work Order", "Production Plan"]`, but the app only adds fields to BOM (verified in `fixtures/custom_field.json` — both entries are `"dt": "BOM"`). Scope the filter to BOM so re-exporting fixtures does not pull unrelated Custom Fields.

**Files:**
- Modify: `sheet_cutting_layout/hooks.py` (line 33)
- Test: `sheet_cutting_layout/tests/test_fixtures_scope.py` (Create)

- [ ] Write the failing test `sheet_cutting_layout/tests/test_fixtures_scope.py`:

```python
from __future__ import annotations

from frappe.tests.utils import FrappeTestCase

import sheet_cutting_layout.hooks as hooks


class TestFixturesScope(FrappeTestCase):
	def test_custom_field_fixture_is_scoped_to_bom(self) -> None:
		custom_field_fixtures = [
			fixture
			for fixture in hooks.fixtures
			if isinstance(fixture, dict) and fixture.get("dt") == "Custom Field"
		]
		self.assertTrue(custom_field_fixtures)
		for fixture in custom_field_fixtures:
			filters = fixture["filters"]
			# Expect [["dt", "=", "BOM"]] or [["dt", "in", ["BOM"]]] — never Work Order / Production Plan.
			flattened = str(filters)
			self.assertNotIn("Work Order", flattened)
			self.assertNotIn("Production Plan", flattened)
```

- [ ] Run it and see it FAIL — `AssertionError: 'Work Order' unexpectedly found` because the filter is `[["dt", "in", ["BOM", "Work Order", "Production Plan"]]]`.
- [ ] Implement — change `hooks.py` line 33 to `{"dt": "Custom Field", "filters": [["dt", "=", "BOM"]]}`.
- [ ] Run tests and see PASS.
- [ ] Run lint.
- [ ] Commit: `fix: scope Custom Field fixture filter to BOM`

### Task E-6: add PM / Purchase / MR permission blocks to the SCL doctype

**Behaviour change** (finding 12). The doctype grants only `System Manager` (sheet_cutting_layout.json lines 327-340), so the workflow roles (`Project Manager`, `Purchase Manager`, `MR Coordinator`) cannot read/write the document the workflow moves them through. Add read/write permission blocks for each, with submit/cancel where the doc_status changes (MR Coordinator releases → submit; supersede/cancel).

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json` (`permissions` array lines 327-340)
- Test: `sheet_cutting_layout/tests/test_permissions.py` (Create)

- [ ] Write the failing test `sheet_cutting_layout/tests/test_permissions.py`:

```python
from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestSheetCuttingLayoutPermissions(FrappeTestCase):
	def test_workflow_roles_can_read_and_write(self) -> None:
		meta = frappe.get_meta("Sheet Cutting Layout")
		roles = {perm.role: perm for perm in meta.permissions}
		for role in ("Project Manager", "Purchase Manager", "MR Coordinator"):
			with self.subTest(role=role):
				self.assertIn(role, roles)
				self.assertTrue(roles[role].read)
				self.assertTrue(roles[role].write)

	def test_mr_coordinator_can_submit_and_cancel(self) -> None:
		meta = frappe.get_meta("Sheet Cutting Layout")
		roles = {perm.role: perm for perm in meta.permissions}
		self.assertTrue(roles["MR Coordinator"].submit)
		self.assertTrue(roles["MR Coordinator"].cancel)
```

- [ ] Run it and see it FAIL — only `System Manager` is present; `assertIn("Project Manager", roles)` fails.
- [ ] Implement — add permission blocks to the `permissions` array (alongside the existing System Manager block):

```json
  {
   "read": 1,
   "write": 1,
   "create": 1,
   "role": "Project Manager"
  },
  {
   "read": 1,
   "write": 1,
   "role": "Purchase Manager"
  },
  {
   "read": 1,
   "write": 1,
   "submit": 1,
   "cancel": 1,
   "role": "MR Coordinator"
  }
```

  (`Project Manager` and `MR Coordinator` are shipped via the app's role fixture — verified: `fixtures/role.json` ships **exactly** `["Project Manager", "MR Coordinator"]` and nothing else. `Purchase Manager` is **NOT** in the app's `role.json`; it is an **ERPNext-shipped** role — verified present in the installed ERPNext source, e.g. it appears in `erpnext/setup/doctype/supplier_group/supplier_group.json` permissions and many other buying-module doctypes. The permission blocks above therefore cover all three: `Project Manager` (app role), `Purchase Manager` (ERPNext role), `MR Coordinator` (app role).)
- [ ] **Confirm the `Purchase Manager` role exists on the bench before relying on it.** From bench root: `bench --site development.localhost console` → `frappe.db.exists("Role", "Purchase Manager")`. ERPNext installs it, so on an ERPNext-enabled site it is present. If the site somehow lacks it (a Frappe-only bench), add a `Purchase Manager` entry to `fixtures/role.json` alongside `Project Manager`/`MR Coordinator` so the permission block resolves to an existing role; otherwise the doctype perm references a missing role. Record the `exists` result in the commit body.
- [ ] Run `bench --site development.localhost migrate` to apply the doctype perm change.
- [ ] Run tests and see PASS.
- [ ] Run lint (JSON is not ruff-checked, but run `python -m json.tool` on the file to confirm valid JSON: `python -m json.tool sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json > /dev/null`).
- [ ] Commit: `feat: grant PM/Purchase/MR roles read-write on Sheet Cutting Layout`

### Task E-7: versioning lets copy_doc localize child rows

**Pure refactor** (finding 33). `versioning._reset_child_row` (lines 85-89) nulls `name`/`parent`/`parentfield`/`parenttype` that `frappe.copy_doc` already localizes; it should clear only the app field `end_piece_item_code` (and `generated_end_piece_bom` if present). `_copy_layout` (lines 73-82) currently has **two** `deepcopy` fallbacks, both dead under the bench: (1) the `except ImportError: return deepcopy(old_layout)` path (line 76-77), and (2) the `if callable(copy_doc): return copy_doc(...)` else `return deepcopy(old_layout)` path (line 79-82) — `copy_doc` is always callable under bench. Drop **both** fallbacks (and the now-unused `from copy import deepcopy` import at line 3) and let `frappe.copy_doc` handle child localization unconditionally.

**Files:**
- Modify: `sheet_cutting_layout/services/versioning.py` (`_copy_layout` 73-82 — collapse both deepcopy fallbacks; remove `from copy import deepcopy` line 3; `_reset_child_row` 85-89)
- Test: `sheet_cutting_layout/tests/test_versioning.py` (Create) + reconcile `sheet_cutting_layout/tests/test_model_workflow_state_machine.py` (the `frappe.copy_doc = None` monkeypatch is removed)

- [ ] Write the failing test `sheet_cutting_layout/tests/test_versioning.py`:

```python
from __future__ import annotations

import inspect

from frappe.tests.utils import FrappeTestCase

from sheet_cutting_layout.services import versioning


class TestVersioning(FrappeTestCase):
	def test_reset_child_row_only_clears_app_fields(self) -> None:
		source = inspect.getsource(versioning._reset_child_row)
		# copy_doc localizes name/parent/parentfield/parenttype; we must not touch them.
		self.assertNotIn('"parent"', source)
		self.assertNotIn('"parenttype"', source)
		self.assertIn("end_piece_item_code", source)

	def test_copy_layout_has_no_deepcopy_fallback(self) -> None:
		module_source = inspect.getsource(versioning)
		copy_source = inspect.getsource(versioning._copy_layout)
		# Both deepcopy fallbacks (the except-ImportError path and the
		# non-callable-copy_doc path) are gone; the module no longer imports deepcopy.
		self.assertNotIn("deepcopy", copy_source)
		self.assertNotIn("except ImportError", copy_source)
		self.assertNotIn("from copy import deepcopy", module_source)
```

- [ ] Run it and see it FAIL — `_reset_child_row` currently iterates `("name", "parent", "parentfield", "parenttype", "end_piece_item_code")`, so `'"parent"'` is present; and `_copy_layout` still contains both `deepcopy` fallbacks plus the `except ImportError` guard, so `test_copy_layout_has_no_deepcopy_fallback` fails on `'deepcopy' unexpectedly found`.
- [ ] Implement `_reset_child_row`:

```python
def _reset_child_row(row: object) -> None:
	for fieldname in ("end_piece_item_code", "generated_end_piece_bom"):
		if hasattr(row, fieldname):
			setattr(row, fieldname, None)
```

  And simplify `_copy_layout` to a single native call, dropping **both** deepcopy fallbacks and the module-level `from copy import deepcopy` import (line 3):

```python
def _copy_layout(old_layout: RevisionLayoutT) -> RevisionLayoutT:
	import frappe

	return frappe.copy_doc(old_layout)
```

  Also delete the now-unused `from copy import deepcopy` line at the top of `versioning.py` (grep `deepcopy` after the edit to confirm zero remaining references in the module).

  > Note: `test_model_workflow_state_machine.py` monkeypatches `frappe.copy_doc = None` to exercise the `deepcopy` fallback (the patch lives in that merged module directly — the develop merge already converted this suite to `FrappeTestCase` methods, so it is **not** something A-4 introduces). After this change that fallback is gone; update/remove the monkeypatch so those state-machine tests use real `copy_doc` or a fake doc with a `copy_doc`-compatible interface. Adjust the affected tests to construct revision layouts directly rather than relying on the removed deepcopy path. Confirm the current location with `grep -n "copy_doc" sheet_cutting_layout/tests/test_model_workflow_state_machine.py`.
- [ ] Run tests and see PASS (`test_versioning`, `test_model_workflow_state_machine`).
- [ ] Run lint.
- [ ] Commit: `refactor: let copy_doc localize revision child rows`

### Task E-8: final full-suite + lint gate

- [ ] Run the full Python suite from bench root: `bench --site development.localhost run-tests --app sheet_cutting_layout`. Expected: all green.
- [ ] Run the E2E suite: `bench --site development.localhost run-ui-tests sheet_cutting_layout --headless`. Expected: existing specs green (Phase 0 adds no UI; confirm no regression).
- [ ] Run lint gates from app root: `python -m ruff check .` and `python -m ruff format --check .`. Expected: clean.
- [ ] Confirm coverage stays above 96% (per `docs/development-philosophy.md`): `bench --site development.localhost run-tests --app sheet_cutting_layout --coverage` (or the repo's configured coverage command); investigate any new uncovered lines introduced by the refactors.
- [ ] No new commit unless a fix was needed; if fixes were made, commit them with an appropriate `fix:`/`test:` message.

---

## Notes for the executor

- **Grep before deleting symbols.** Several "remove this helper" steps depend on the helper being unused after an earlier step. Always `grep -rn <symbol> sheet_cutting_layout --include="*.py"` first; if an unexpected caller appears, adapt rather than break it.
- **`mark_bom_app_controlled` stays.** The `overrides/bom.py` guard (`validate_shearing_bom_source` on `before_insert`/`before_cancel`) and `mark_bom_app_controlled` flag remain — they protect generated Shearing BOMs from manual edits and are not part of the lifecycle being replaced. After D-3 the app cancels BOMs via `bom.cancel()`; `validate_shearing_bom_source` is wired to `before_cancel` and exempts app-controlled updates via the flag, so `retire_layout` should `mark_bom_app_controlled(bom_doc)` before calling `bom_doc.cancel()` to avoid the guard throwing. Add that `mark_bom_app_controlled(bom_doc)` call inside the `retire_layout` loop (before `bom_doc.cancel()`), mirroring the old retirement helpers.
- **`approval_snapshot` is kept** (finding 35) — it is the IATF signature trail; it is now populated from `_record_workflow_snapshot` in `on_submit`. Note the overlap with native workflow audit in the relevant commit body but do not remove it.
- **Migrate runs are dev-only.** Several tasks call `bench migrate` to drop a column or apply a perm/field change; the dev-only hard-reset policy (§6) makes this safe. Do not write migration patches to replace the dropped ones.
</content>
</invoke>
