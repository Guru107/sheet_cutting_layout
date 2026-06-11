# Pytest Removal and Frappe-Native Test Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the pytest-idiom `unittest_adapter` shim, convert all 84 adapter-dependent tests to native `FrappeTestCase` methods, remove the frappe-less fallback so tests run only via `bench run-tests`, and add real-record integration coverage for frappe-boundary flows.

**Architecture:** Two phases per the approved spec ([docs/superpowers/specs/2026-06-11-pytest-removal-frappe-native-tests-design.md](../specs/2026-06-11-pytest-removal-frappe-native-tests-design.md)). Phase 1 is a mechanical conversion: module-level `test_*` functions move into `unittest`-style classes, adapter idioms map to stdlib equivalents, and the adapter + frappe-less guards are deleted. Phase 2 promotes the doctype test's record helpers into shared factories and adds integration tests against real `Sheet Cutting Layout`, `Item`, `BOM`, and `Project` documents.

**Tech Stack:** Frappe `FrappeTestCase` / `bench run-tests`, `unittest.mock`, Hypothesis (`run_state_machine_as_test`), ERPNext BOM doctype.

**Verification environment:** All test runs happen from a bench root where this app is installed. Two benches must pass: bench15 site `development.localhost` and bench16 site `frappe16.localhost`. Module-scoped run command pattern:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_service
```

**Conversion rulebook (applies to every Phase 1 task):**

| Adapter idiom | Native replacement |
| --- | --- |
| `with raises(Exc, match="pat"):` | `with self.assertRaisesRegex(Exc, "pat"):` |
| `with raises(Exc):` | `with self.assertRaises(Exc):` |
| `assert x == approx(y)` | `self.assertFloatAlmostEqual(x, y)` (defined on `SheetCuttingLayoutTestCase`; tolerance moves from abs 1e-12 to 6 decimal places — acceptable for these kg/rate magnitudes) |
| `fail(msg)` | `raise AssertionError(msg)` in helpers, `self.fail(msg)` in test methods |
| `monkeypatch.setattr(obj, "name", value)` | `patcher = patch.object(obj, "name", value); patcher.start(); self.addCleanup(patcher.stop)` — or `with patch.object(obj, "name", value):` when scoped to a few lines |
| `monkeypatch.setattr(obj, "name", value, raising=False)` | same, with `create=True` |
| `monkeypatch.setitem(sys.modules, "mod", stub)` | `patch.dict(sys.modules, {"mod": stub})` started/cleaned the same way |
| `@fixture(autouse=True)` | `setUp` on the test class (call `super().setUp()` first) |
| `def test_x() -> None:` at module level | `def test_x(self) -> None:` method inside a class; module-level dataclasses/stub factories stay at module level |
| `add_pytest_style_tests(globals(), Cls)` | delete the call |
| Hypothesis state machine run via collected function | `run_state_machine_as_test(MachineCls, settings=STATE_MACHINE_SETTINGS)` inside a test method |

Tests not using any idiom convert by indenting into the class and adding `self`. Every converted file keeps `from __future__ import annotations`, drops the `unittest_adapter` import, drops any `try: import frappe / except ImportError` guard (plain `import frappe`), and adds `from unittest.mock import patch` where patching is needed.

---

## Phase 1 — Pytest Eradication

### Task 1: Convert `test_model_workflow_state_machine.py`

**Files:**
- Modify: `sheet_cutting_layout/tests/test_model_workflow_state_machine.py` (full rewrite, 274 lines)

- [ ] **Step 1: Rewrite the file**

Replace the entire file with the following. The dataclasses, both `RuleBasedStateMachine` classes, and all assertions are unchanged except: the autouse fixture becomes `setUp`, `raises(...)` becomes `assertRaisesRegex`/try-except, the two state-machine driver functions become methods using `run_state_machine_as_test`, and the empty `TestModelWorkflowStateMachine` + `add_pytest_style_tests` scaffolding is replaced by a real class.

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from unittest.mock import patch

import frappe
from hypothesis import settings
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule, run_state_machine_as_test

from sheet_cutting_layout.services.versioning import (
	LayoutVersionStatus,
	create_revision,
	finalize_new_revision_release,
)
from sheet_cutting_layout.services.workflow import LayoutWorkflowModel
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase

STATE_MACHINE_SETTINGS = settings(
	max_examples=40,
	stateful_step_count=20,
	deadline=None,
)


@dataclass
class FinishedPart:
	finished_part_item: str
	generated_bom: str | None = None


@dataclass
class RevisionLayout:
	name: str
	project: str
	revision_no: int
	status: LayoutVersionStatus
	is_active: bool
	based_on_layout: str | None = None
	approval_snapshot: list[str] = field(default_factory=list)
	finished_parts: list[FinishedPart] = field(default_factory=list)
	finished_part_code: str = ""
	net_weight_per_part_kg: float = 0.0
	generated_bom: str | None = None


class WorkflowStateMachine(RuleBasedStateMachine):
	# ... body identical to the current file (rules, invariants) EXCEPT _assert_transition:

	def _assert_transition(
		self,
		valid: bool,
		action: Callable[[], None],
		update_expected: Callable[[], None],
	) -> None:
		if valid:
			action()
			update_expected()
			return

		try:
			action()
		except AssertionError:
			return
		raise AssertionError("Expected invalid transition to raise AssertionError")


class RevisionVersioningStateMachine(RuleBasedStateMachine):
	# ... body identical to the current file (rules, invariants, _active_released_layouts)
	...


class TestModelWorkflowStateMachine(SheetCuttingLayoutTestCase):
	def setUp(self) -> None:
		super().setUp()
		copy_doc_patcher = patch.object(frappe, "copy_doc", None, create=True)
		copy_doc_patcher.start()
		self.addCleanup(copy_doc_patcher.stop)

	def test_project_manager_approval_moves_state_to_pm_approved(self) -> None:
		machine = LayoutWorkflowModel()
		machine.submit()
		machine.project_manager_approves()

		self.assertEqual(machine.state, "PM Approved")

	def test_purchase_approval_requires_pm_approved(self) -> None:
		machine = LayoutWorkflowModel()
		machine.submit()

		with self.assertRaisesRegex(AssertionError, "Expected layout state PM Approved"):
			machine.purchase_approves()

	def test_release_blocked_before_purchase_approval(self) -> None:
		machine = LayoutWorkflowModel()
		machine.submit()
		machine.project_manager_approves()

		with self.assertRaisesRegex(AssertionError, "purchase approval"):
			machine.release()

	def test_purchase_and_mr_release_path_reaches_released(self) -> None:
		machine = LayoutWorkflowModel()
		machine.submit()
		machine.project_manager_approves()
		machine.purchase_approves()
		machine.release()

		self.assertEqual(machine.state, "Released")

	def test_state_machine_never_reaches_released_without_purchase_and_mr(self) -> None:
		run_state_machine_as_test(WorkflowStateMachine, settings=STATE_MACHINE_SETTINGS)

	def test_state_machine_keeps_all_active_layouts_released_after_new_versions(self) -> None:
		run_state_machine_as_test(RevisionVersioningStateMachine, settings=STATE_MACHINE_SETTINGS)
```

Where the comment says "body identical", copy the rule/invariant methods verbatim from the current file — they contain no pytest idioms apart from `_assert_transition` (shown above). Delete the two `*.TestCase.settings = settings(...)` module-level assignments (replaced by `STATE_MACHINE_SETTINGS`), the `@fixture` block, the two module-level `test_state_machine_*` functions, and the `add_pytest_style_tests` call.

- [ ] **Step 2: Run the module under bench**

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_model_workflow_state_machine
```

Expected: 6 tests, OK.

- [ ] **Step 3: Commit**

```bash
git add sheet_cutting_layout/tests/test_model_workflow_state_machine.py
git commit -m "refactor(tests): convert workflow state machine tests to native unittest"
```

### Task 2: Convert `test_bom_service.py`

**Files:**
- Modify: `sheet_cutting_layout/tests/test_bom_service.py`

- [ ] **Step 1: Convert the module**

1. Imports: drop `from sheet_cutting_layout.tests.unittest_adapter import add_pytest_style_tests, approx, fail, raises`.
2. Keep the `FinishedPart`, `EndPiece`, `Layout` dataclasses at module level unchanged.
3. Replace the `fail(...)` call in `import_bom_service`:

```python
def import_bom_service() -> types.ModuleType:
	try:
		return importlib.import_module("sheet_cutting_layout.services.bom_service")
	except ModuleNotFoundError as error:
		raise AssertionError(f"BOM service module is not implemented: {error}")
```

4. Move all 15 module-level test functions into the existing `TestBomService(SheetCuttingLayoutTestCase)` class (line 297) as methods, above the methods already there. Add `self`, then apply the rulebook. The full list with required edits:

| Test | Edits beyond indent+self |
| --- | --- |
| `test_generated_bom_uses_parts_per_sheet_quantity_and_sheet_weight_raw_qty` | `assert bom.items[0].qty == approx(50)` → `self.assertFloatAlmostEqual(bom.items[0].qty, 50)` |
| `test_process_scrap_row_is_included_when_scrap_weight_is_positive` | `approx(5)` → `self.assertFloatAlmostEqual(..., 5)` |
| `test_process_scrap_and_reuse_end_piece_byproduct_rows_are_both_included` | none (plain asserts) |
| `test_reuse_end_pieces_create_main_bom_byproduct_rows` | none |
| `test_existing_reuse_end_piece_item_code_wins_over_resolver` | none |
| `test_reuse_end_piece_resolver_runs_before_pure_derivation` | none |
| `test_reuse_end_piece_resolver_must_return_item_code` | `with raises(ValueError, match="Reusable end piece requires generated item code")` → `with self.assertRaisesRegex(ValueError, "Reusable end piece requires generated item code")` |
| `test_scrap_endpiece_creates_row_level_scrap_item_separate_from_process_scrap` | none |
| `test_scrap_endpiece_requires_scrap_item_before_creating_bom_row` | `raises(ValueError, match="Scrap end piece requires scrap_item")` → `assertRaisesRegex` |
| `test_bom_quantity_ignores_no_of_strips_when_parts_per_sheet_is_available` | none |
| `test_custom_bom_document_factory_is_used` | none |
| `test_resolve_scrap_item_rate_reuses_positive_existing_rate_without_lookup` | `rate == approx(42.5)` → `self.assertFloatAlmostEqual(rate, 42.5)` |
| `test_resolve_scrap_item_rate_looks_up_when_existing_rate_is_zero_or_invalid` | two `approx(88.25)` → `assertFloatAlmostEqual` |
| `test_weight_split_helper_matches_main_bom_raw_and_scrap_rows` | none |
| `test_weight_split_helper_skips_scrap_row_when_scrap_quantity_is_zero` | none |

Plain `assert a == b` statements may stay as bare asserts (the file already mixes them) or become `self.assertEqual` — match each test's surrounding style, do not restyle untouched assertions.

5. Delete `add_pytest_style_tests(globals(), TestBomService)` at the bottom.

- [ ] **Step 2: Run the module under bench**

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_service
```

Expected: all tests (15 converted + existing native methods) pass.

- [ ] **Step 3: Commit**

```bash
git add sheet_cutting_layout/tests/test_bom_service.py
git commit -m "refactor(tests): convert BOM service tests to native unittest"
```

### Task 3: `test_release_service.py` — shared isolation base + contract tests

The 63 module-level tests in this file convert incrementally across Tasks 3–6. This works because `add_pytest_style_tests(globals(), TestReleaseService)` only collects functions still at module level; each task moves a group into a class, and the suite stays green at every commit. The adapter import stays in this file until Task 6 removes it.

**Files:**
- Modify: `sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Add the shared isolation base class**

Insert after the existing module-level stub dataclasses (`Layout`, `FinishedPart`, `EndPiece`, `RevisionLayout`, `Bom`, `SavableRevisionLayout`, `SubmittedRevisionLayout`), replicating the current autouse fixture `isolate_release_runtime_from_live_frappe`:

```python
import frappe
from unittest.mock import patch

from sheet_cutting_layout.services import release_service


class ReleaseServiceIsolatedTestCase(SheetCuttingLayoutTestCase):
	"""Keep unit-style tests deterministic under bench by disabling live persistence paths."""

	def setUp(self) -> None:
		super().setUp()
		frappe_patcher = patch.object(release_service, "frappe", None)
		frappe_patcher.start()
		self.addCleanup(frappe_patcher.stop)
		copy_doc_patcher = patch.object(frappe, "copy_doc", None, create=True)
		copy_doc_patcher.start()
		self.addCleanup(copy_doc_patcher.stop)
```

Do NOT yet delete the `@fixture(autouse=True)` function — unconverted module-level tests still need it. It is deleted in Task 6 when the last group converts.

- [ ] **Step 2: Convert group A — contract tests (7 tests, no frappe isolation needed)**

Create `class TestReleaseContracts(SheetCuttingLayoutTestCase)` (plain base — these read JSON/source files only) and move these module-level functions into it as methods:

1. `test_hooks_exposes_required_fixtures`
2. `test_bom_custom_fields_are_fixture_owned`
3. `test_parent_finished_part_code_is_item_link`
4. `test_status_options_include_cancel_state`
5. `test_generated_release_artifact_fields_are_not_copied`
6. `test_workflow_wrapper_is_whitelisted`
7. `test_readme_mentions_release_gate_and_bom_qty_parts_per_sheet`

These contain no adapter idioms — indent, add `self`, keep their helper functions (`_load_doctype_json` etc., if any are only used by this group, they may move in as `@staticmethod`s or stay module-level; prefer staying module-level to minimize diff).

- [ ] **Step 3: Run the module under bench**

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
```

Expected: same test count as before the change (63 plus any pre-existing native methods), OK.

- [ ] **Step 4: Commit**

```bash
git add sheet_cutting_layout/tests/test_release_service.py
git commit -m "refactor(tests): native isolation base and contract test class for release service"
```

### Task 4: `test_release_service.py` — release flow + save-time audit groups

**Files:**
- Modify: `sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Convert group B — `class TestReleaseFlow(ReleaseServiceIsolatedTestCase)` (14 tests)**

Move these into the class:

1. `test_release_reaches_released`
2. `test_release_runs_default_layout_validation`
3. `test_release_allows_injected_validators_for_testability`
4. `test_release_requires_process_scrap_item_when_process_scrap_is_positive`
5. `test_release_stops_when_injected_validator_fails`
6. `test_release_uses_injected_context_provider`
7. `test_release_uses_injected_bom_document_factory_for_persisted_boms`
8. `test_release_uses_parent_finished_part_contract_without_child_inputs`
9. `test_release_syncs_finished_part_reference_rows_from_saved_bom`
10. `test_release_generates_bom_for_one_sheet_in_kg_with_scrap_outputs`
11. `test_generated_boms_are_activated_on_release`
12. `test_release_persists_only_new_revision_layout_when_frappe_is_available`
13. `test_release_does_not_db_set_unchanged_submitted_layouts`
14. `test_mr_release_records_mr_approval_snapshot`

Idiom edits: every `with raises(Exc, match=...)` → `assertRaisesRegex`. Tests 12 and 13 take a `monkeypatch` parameter used as `monkeypatch.setattr(release_service, "frappe", FrappeStub)`; replace with:

```python
		frappe_stub_patcher = patch.object(release_service, "frappe", FrappeStub)
		frappe_stub_patcher.start()
		self.addCleanup(frappe_stub_patcher.stop)
```

(this layers over the base-class `None` patch within the test — `mock.patch` unwinds in LIFO order, so cleanup is correct).

- [ ] **Step 2: Convert group C — `class TestSaveTimeAudit(ReleaseServiceIsolatedTestCase)` (3 tests)**

1. `test_save_time_audit_rejects_generated_bom_quantity_drift`
2. `test_save_time_audit_rejects_missing_reuse_end_piece_byproduct_row`
3. `test_save_time_audit_rejects_fractional_generated_bom_quantity`

Each uses `monkeypatch.setattr(validators, ...)` twice plus `raises(ValueError, match=...)`. Pattern for the first one (apply identically to all three, with their respective stub args and match strings):

```python
	def test_save_time_audit_rejects_generated_bom_quantity_drift(self) -> None:
		from sheet_cutting_layout.services import validators

		layout = _audit_layout()  # keep existing module-level helpers as-is

		with (
			patch.object(validators, "frappe", _audit_frappe_stub(bom_quantity=99)),
			patch.object(validators, "_", lambda message: message),
			self.assertRaisesRegex(ValueError, "BOM quantity mismatch"),
		):
			validators.validate_sheet_cutting_layout(layout)
```

Preserve each test's exact existing body lines — only the patching/raises wrappers change. (Check the current body for the exact function invoked and keep it.)

- [ ] **Step 3: Run module under bench, expected OK, same total count**

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
```

- [ ] **Step 4: Commit**

```bash
git add sheet_cutting_layout/tests/test_release_service.py
git commit -m "refactor(tests): native release flow and audit test classes"
```

### Task 5: `test_release_service.py` — controller/workflow + patch groups

**Files:**
- Modify: `sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Convert group D — `class TestControllerWorkflow(ReleaseServiceIsolatedTestCase)` (11 tests)**

1. `test_controller_before_insert_clears_copied_release_artifacts`
2. `test_controller_mr_release_action_calls_release_service`
3. `test_controller_mr_release_suppresses_side_effects_during_internal_layout_saves`
4. `test_controller_validate_applies_workflow_side_effects_and_records_snapshot`
5. `test_controller_validate_records_submit_for_check_snapshot`
6. `test_workflow_wrapper_sets_selected_action_for_sheet_cutting_layout`
7. `test_rejected_layout_on_trash_removes_workflow_action_links`
8. `test_non_rejected_layout_on_trash_keeps_workflow_action_links`
9. `test_controller_supersede_action_deactivates_generated_bom`
10. `test_controller_before_cancel_cancels_generated_bom`
11. `test_form_cancel_lets_layout_controller_cancel_linked_bom`

`monkeypatch.setattr(sheet_cutting_layout, "x", y)` calls → started `patch.object(...)` + `addCleanup` as in Task 4. Test 6 additionally uses `monkeypatch.setitem(sys.modules, "frappe.model.workflow", FrappeWorkflowStub)` — replace with:

```python
		modules_patcher = patch.dict(sys.modules, {"frappe.model.workflow": FrappeWorkflowStub})
		modules_patcher.start()
		self.addCleanup(modules_patcher.stop)
```

- [ ] **Step 2: Convert group E — `class TestPatches(ReleaseServiceIsolatedTestCase)` (6 tests)**

1. `test_patch_submits_existing_released_layouts`
2. `test_patch_submits_existing_superseded_layouts`
3. `test_patch_marks_cancelled_layouts_and_unlinks_generated_boms`
4. `test_patch_repairs_checked_workflow_state_to_pm_approved`
5. `test_patch_skips_legacy_hidden_flag_repair_when_columns_are_absent`
6. `test_patch_backfills_missing_mr_approval_snapshots`

Each monkeypatches its patch-module's `frappe` attribute (e.g. `monkeypatch.setattr(v1_0_submit_released_layouts, "frappe", FrappeStub)`) — same started-patcher replacement.

- [ ] **Step 3: Run module under bench, expected OK; commit**

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
git add sheet_cutting_layout/tests/test_release_service.py
git commit -m "refactor(tests): native controller workflow and patch test classes"
```

### Task 6: `test_release_service.py` — remaining groups, delete fixture

**Files:**
- Modify: `sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Convert the four remaining groups**

`class TestFrappeBomInsertAndEndPieces(ReleaseServiceIsolatedTestCase)` (4 tests):

1. `test_frappe_bom_insert_sets_required_company_from_layout`
2. `test_frappe_bom_insert_wraps_scrap_rate_resolution_error`
3. `test_default_release_creates_reuse_end_piece_byproduct_row`
4. `test_default_release_persists_generated_end_piece_item_code_on_saved_layout`

`class TestReleaseContextAndHelpers(ReleaseServiceIsolatedTestCase)` (7 tests):

1. `test_get_release_context_requires_frappe_outside_tests`
2. `test_release_context_discovers_layouts_and_boms`
3. `test_release_context_handles_layout_without_family_or_finished_parts`
4. `test_release_helpers_raise_without_frappe`
5. `test_default_bom_factory_requires_frappe_outside_tests`
6. `test_company_resolution_uses_defaults_and_errors_when_missing`
7. `test_set_frappe_field_only_when_supported`

`class TestRevisioning(ReleaseServiceIsolatedTestCase)` (4 tests):

1. `test_revising_released_layout_clones_and_increments_revision`
2. `test_revision_resets_approval_snapshot_and_generated_boms`
3. `test_finalizing_new_revision_marks_only_the_new_layout_released_and_active`
4. `test_release_generates_one_bom_for_single_finished_part_and_keeps_existing_boms_active`

`class TestBomLifecycle(ReleaseServiceIsolatedTestCase)` (7 tests):

1. `test_deactivate_generated_bom_marks_linked_bom_superseded`
2. `test_deactivate_generated_bom_uses_db_set_for_submitted_bom`
3. `test_deactivate_generated_bom_deactivates_every_bom_linked_to_layout`
4. `test_cancel_generated_bom_cancels_submitted_bom_with_app_control_flag`
5. `test_cancel_generated_bom_cancels_every_bom_linked_to_layout`
6. `test_cancel_generated_bom_rolls_back_savepoint_when_submitted_cancel_fails`
7. `test_cancel_generated_bom_rolls_back_savepoint_when_draft_save_fails`

All `monkeypatch.setattr(...)` → started `patch.object` + `addCleanup`; all `raises(..., match=...)` → `assertRaisesRegex`. Local `class FrappeStub:` / `class BomDoc:` definitions inside each test stay inside the method body unchanged.

- [ ] **Step 2: Delete the leftovers**

After this step zero module-level `test_*` functions remain. Delete:

1. The `@fixture(autouse=True) def isolate_release_runtime_from_live_frappe(...)` function.
2. `class TestReleaseService(SheetCuttingLayoutTestCase): ...` (the now-empty collector class).
3. `add_pytest_style_tests(globals(), TestReleaseService)`.
4. `from sheet_cutting_layout.tests.unittest_adapter import MonkeyPatch, add_pytest_style_tests, fixture, raises`.
5. The `try: import frappe / except ImportError` guard at the top, if present — replace with plain `import frappe`.

Verify: `grep -n "unittest_adapter\|^def test_\|MonkeyPatch" sheet_cutting_layout/tests/test_release_service.py` returns nothing.

- [ ] **Step 3: Run module under bench, expected OK (63 tests in classes); commit**

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
git add sheet_cutting_layout/tests/test_release_service.py
git commit -m "refactor(tests): finish native conversion of release service tests"
```

### Task 7: Delete the adapter

**Files:**
- Delete: `sheet_cutting_layout/tests/unittest_adapter.py`
- Delete: `sheet_cutting_layout/tests/test_unittest_adapter.py`

- [ ] **Step 1: Delete both files**

```bash
git rm sheet_cutting_layout/tests/unittest_adapter.py sheet_cutting_layout/tests/test_unittest_adapter.py
```

- [ ] **Step 2: Verify nothing references the adapter**

```bash
grep -rn "unittest_adapter\|add_pytest_style_tests" sheet_cutting_layout/ scripts/ .github/
```

Expected: no output.

- [ ] **Step 3: Run the full app suite**

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout
```

Expected: OK, no errors, no import failures.

- [ ] **Step 4: Commit**

```bash
git commit -m "refactor(tests): delete pytest unittest adapter shim"
```

### Task 8: Remove frappe-less mode

**Files:**
- Modify: `sheet_cutting_layout/tests/base.py`
- Modify: `sheet_cutting_layout/tests/factories.py`
- Modify: `sheet_cutting_layout/tests/test_setup.py`
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`

- [ ] **Step 1: Rewrite `base.py`**

```python
from __future__ import annotations

try:
	from frappe.tests.utils import FrappeTestCase
except ImportError:  # Frappe v16 renamed the integration base class.
	from frappe.tests import IntegrationTestCase as FrappeTestCase


class SheetCuttingLayoutTestCase(FrappeTestCase):
	@classmethod
	def setUpClass(cls) -> None:
		super().setUpClass()
		from sheet_cutting_layout.tests.factories import cleanup_test_records

		cls.addClassCleanup(cleanup_test_records)

	def assertFloatAlmostEqual(self, actual: float | int, expected: float | int, places: int = 6) -> None:
		self.assertAlmostEqual(float(actual), float(expected), places=places)
```

The remaining try/except targets two frappe-internal paths only (allowed by spec section 4.3); there is no `unittest.TestCase` fallback and no broad `except Exception` around the factories import.

- [ ] **Step 2: Clean `factories.py`**

Replace lines 6–9:

```python
try:
	import frappe
except ImportError:
	frappe = None
```

with plain `import frappe`. In `_ensure_connection`, delete the `if frappe is None: return False` branch.

- [ ] **Step 3: Clean `test_setup.py`**

Replace the guarded import (lines 5–11), including the "pytest also collects it" comment, with plain `import frappe`.

- [ ] **Step 4: Clean `test_sheet_cutting_layout.py`**

1. Replace the `try: import frappe / except ImportError: frappe = None` block with `import frappe`.
2. Remove `skipUnless` from the import list and delete all four `@skipUnless(frappe is not None, "Frappe bench runtime required")` decorators.
3. Delete every `assert frappe is not None` line (in `_insert_if_missing`, `_ensure_layout_dependencies`, `_ensure_hsn_code`, `_ensure_item`, `make_layout`, and the qty-split test).

- [ ] **Step 5: Run the full suite and commit**

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout
git add sheet_cutting_layout/tests/base.py sheet_cutting_layout/tests/factories.py sheet_cutting_layout/tests/test_setup.py sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py
git commit -m "refactor(tests): remove frappe-less fallback, require bench runtime"
```

### Task 9: CI cleanup and Phase 1 acceptance

**Files:**
- Modify: `scripts/run_ephemeral_python_tests.sh`

- [ ] **Step 1: Drop pytest from CI installs**

In `scripts/run_ephemeral_python_tests.sh` change:

```bash
bench pip install pytest hypothesis
```

to:

```bash
bench pip install hypothesis
```

- [ ] **Step 2: Acceptance greps**

```bash
grep -rn "pytest" sheet_cutting_layout/ scripts/ .github/ pyproject.toml README.md
grep -rn "except ImportError" sheet_cutting_layout/tests/ sheet_cutting_layout/sheet_cutting_layout/doctype/
```

Expected: first grep returns nothing; second returns only the `base.py` frappe-version compat import.

- [ ] **Step 3: Full verification on both benches**

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout
bench --site frappe16.localhost run-tests --app sheet_cutting_layout   # from the bench16 root
pre-commit run --all-files
```

Expected: both suites OK, pre-commit passes.

- [ ] **Step 4: Commit**

```bash
git add scripts/run_ephemeral_python_tests.sh
git commit -m "ci: stop installing pytest for bench-native test runs"
```

---

## Phase 2 — Integration Migration

Per spec section 5: framework-boundary flows gain real-record tests; fake-based tests that assert call discipline (`db_set` vs `save`), savepoint rollback on injected failures, or dependency-injection seams stay isolated — database state cannot observe those behaviors, which is the spec's "impractical framework branches" category. Phase 2 is therefore additive (new integration tests) plus factory promotion; no coverage is dropped.

### Task 10: Promote record factories

**Files:**
- Modify: `sheet_cutting_layout/tests/factories.py`
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`

- [ ] **Step 1: Move the record helpers into `factories.py`**

Append to `factories.py` (moved nearly verbatim from `test_sheet_cutting_layout.py`, with `assert frappe is not None` lines already gone after Task 8, and `make_layout` generalized with `**overrides`):

```python
def insert_if_missing(
	doc: dict[str, object],
	name_field: str,
	*,
	exists_filters: dict[str, object] | None = None,
) -> str:
	name = str(doc[name_field])
	existing_name = frappe.db.exists(str(doc["doctype"]), exists_filters or name)
	if existing_name:
		return str(existing_name)

	inserted = frappe.get_doc(doc).insert(ignore_permissions=True)
	register_test_doc(str(doc["doctype"]), inserted.name)
	return inserted.name


def ensure_item_group() -> str:
	return insert_if_missing(
		{
			"doctype": "Item Group",
			"item_group_name": "SCL-TEST-ITEM-GROUP",
			"parent_item_group": "All Item Groups",
			"is_group": 0,
		},
		"item_group_name",
	)


def ensure_project() -> str:
	return insert_if_missing(
		{"doctype": "Project", "project_name": "SCL-TEST-PROJECT"},
		"project_name",
		exists_filters={"project_name": "SCL-TEST-PROJECT"},
	)


def ensure_hsn_code(hsn_code: str) -> str:
	if not frappe.db.exists("DocType", "GST HSN Code"):
		raise RuntimeError("GST HSN Code DocType is not available on this site")
	return insert_if_missing({"doctype": "GST HSN Code", "hsn_code": hsn_code}, "hsn_code")


def ensure_item(item_code: str, *, stock_uom: str, valuation_rate: float = 1) -> str:
	doc: dict[str, object] = {
		"doctype": "Item",
		"item_code": item_code,
		"item_name": item_code,
		"item_group": ensure_item_group(),
		"stock_uom": stock_uom,
		"is_stock_item": 1,
		"valuation_rate": valuation_rate,
	}
	if frappe.get_meta("Item", cached=True).has_field("gst_hsn_code") and frappe.db.exists(
		"DocType", "GST HSN Code"
	):
		doc["gst_hsn_code"] = ensure_hsn_code("720810")
	return insert_if_missing(doc, "item_code")


def make_layout(
	*,
	finished_part_code: str,
	net_weight_per_part_kg: float = 0.289,
	generated_bom: str | None = None,
	**overrides: object,
):
	unique_suffix = frappe.generate_hash(length=8)
	project = ensure_project()
	raw_material_item = ensure_item("SCLTESTRM001", stock_uom="Kg")
	ensure_item(finished_part_code, stock_uom="Nos")
	values: dict[str, object] = {
		"doctype": "Sheet Cutting Layout",
		"layout_code": f"SCL-TEST-LAYOUT-{unique_suffix}",
		"project": project,
		"raw_material_item": raw_material_item,
		"process_scrap_item": raw_material_item,
		"sheet_thickness_mm": 1,
		"sheet_width_mm": 1250,
		"sheet_length_mm": 2500,
		"strip_thickness_mm": 1,
		"strip_width_mm": 1250,
		"strip_length_mm": 260,
		"parts_per_strip": 2,
		"no_of_strips": 1,
		"status": "Draft",
		"finished_part_code": finished_part_code,
		"net_weight_per_part_kg": net_weight_per_part_kg,
		"generated_bom": generated_bom,
		"finished_parts": [],
		"end_pieces": [],
	}
	values.update(overrides)
	return frappe.get_doc(values)
```

- [ ] **Step 2: Point the doctype test at the shared factories**

In `test_sheet_cutting_layout.py`: delete `_insert_if_missing`, `_ensure_layout_dependencies`, `_ensure_hsn_code`, `_ensure_item`, and `make_layout`; import instead:

```python
from sheet_cutting_layout.tests.factories import ensure_item, make_layout, register_test_doc
```

The original `make_layout` set `layout_code` prefix `SCL-TEST-PARENT-CONTRACT-`; the shared one uses `SCL-TEST-LAYOUT-` — both are swept by the `SCL-TEST-` cleanup prefix, no behavior change.

- [ ] **Step 3: Run the affected modules, then commit**

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout
git add sheet_cutting_layout/tests/factories.py sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py
git commit -m "refactor(tests): promote record factories for shared integration use"
```

### Task 11: BOM service — real-record rate resolution

**Files:**
- Modify: `sheet_cutting_layout/tests/test_bom_service.py`

- [ ] **Step 1: Add an integration class**

The two `resolve_scrap_item_rate` tests cross the frappe boundary (rate lookup); their fake versions stay (they pin the lookup-skip contract), and this real-record test is added at the end of the file:

```python
class TestBomServiceIntegration(SheetCuttingLayoutTestCase):
	def test_resolve_scrap_item_rate_reads_real_item_valuation(self) -> None:
		from sheet_cutting_layout.services.bom_service import resolve_scrap_item_rate
		from sheet_cutting_layout.tests.factories import ensure_item

		scrap_item = ensure_item("SCLTESTSCRAPRATE001", stock_uom="Kg", valuation_rate=62.5)

		rate = resolve_scrap_item_rate(item_code=scrap_item, existing_rate=0)

		self.assertFloatAlmostEqual(rate, 62.5)
```

If `resolve_scrap_item_rate`'s real signature differs (check `sheet_cutting_layout/services/bom_service.py` — the fake tests call it with keyword args), match the call to the actual signature; the assertion target is the Item's `valuation_rate`. If the resolver reads a different rate source (e.g. Item Price), set that record up via `insert_if_missing` instead and assert against it — investigate the real lookup path first, per the spec's fake-vs-real divergence rule.

- [ ] **Step 2: Run, commit**

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_service
git add sheet_cutting_layout/tests/test_bom_service.py
git commit -m "test: real-record scrap rate resolution coverage"
```

### Task 12: Release service — real release flow integration

**Files:**
- Modify: `sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Add the integration class with the release happy path**

Add at the end of the file (note: plain `SheetCuttingLayoutTestCase`, NOT the isolated base — these tests want live frappe):

```python
class TestReleaseServiceIntegration(SheetCuttingLayoutTestCase):
	def _release_ready_layout(self):
		from sheet_cutting_layout.tests.factories import make_layout, register_test_doc

		suffix = frappe.generate_hash(length=5).upper()
		layout = make_layout(
			finished_part_code=f"SCLTESTFG{suffix}SHR",
			parts_per_strip=1,
			no_of_strips=1,
			strip_length_mm=2500,
		)
		layout.insert()
		register_test_doc("Sheet Cutting Layout", layout.name)
		layout.db_set("status", "Approved by Purchase", update_modified=False)
		layout.reload()
		layout.net_weight_per_part_kg = layout.gross_weight_per_part_kg
		return layout

	def _release(self, layout):
		from sheet_cutting_layout.services.release_service import release_layout
		from sheet_cutting_layout.tests.factories import register_test_doc

		result = release_layout(layout)
		if layout.generated_bom:
			register_test_doc("BOM", layout.generated_bom)
		return result

	def test_release_layout_creates_active_bom_with_sheet_weight_raw_row(self) -> None:
		layout = self._release_ready_layout()

		self._release(layout)

		self.assertEqual(layout.status, "Released")
		self.assertTrue(layout.generated_bom)
		bom = frappe.get_doc("BOM", layout.generated_bom)
		self.assertEqual(bom.item, layout.finished_part_code)
		self.assertEqual(bom.is_active, 1)
		self.assertFloatAlmostEqual(bom.quantity, layout.parts_per_sheet)
		raw_rows = [row for row in bom.items if row.item_code == layout.raw_material_item]
		self.assertEqual(len(raw_rows), 1)
		self.assertFloatAlmostEqual(raw_rows[0].qty, layout.weight_per_sheet_kg)
		self.assertEqual(raw_rows[0].uom, "Kg")

	def test_release_persists_released_status_in_database(self) -> None:
		layout = self._release_ready_layout()

		self._release(layout)

		self.assertEqual(
			frappe.db.get_value("Sheet Cutting Layout", layout.name, "status"),
			"Released",
		)
```

If `release_layout(layout)` fails on a real document where the fake passed, that is a finding to investigate (spec section 6), not a reason to re-fake: compare against the working controller-driven path in `test_mr_release_generates_native_bom_with_test_uom_items` (doctype test) and align setup, not assertions.

- [ ] **Step 2: Run, commit**

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
git add sheet_cutting_layout/tests/test_release_service.py
git commit -m "test: real-record release flow integration coverage"
```

### Task 13: Release service — real BOM lifecycle (supersede + cancel)

**Files:**
- Modify: `sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Add lifecycle tests to `TestReleaseServiceIntegration`**

```python
	def test_deactivate_generated_bom_supersedes_real_bom(self) -> None:
		from sheet_cutting_layout.services.release_service import deactivate_generated_bom

		layout = self._release_ready_layout()
		self._release(layout)

		deactivate_generated_bom(layout)

		bom = frappe.get_doc("BOM", layout.generated_bom)
		self.assertEqual(bom.is_active, 0)
		self.assertEqual(bom.is_default, 0)
		self.assertEqual(bom.status, "Superseded")

	def test_cancel_generated_bom_cancels_real_bom(self) -> None:
		from sheet_cutting_layout.services.release_service import cancel_generated_bom

		layout = self._release_ready_layout()
		self._release(layout)
		bom_before = frappe.get_doc("BOM", layout.generated_bom)

		cancel_generated_bom(layout)

		bom = frappe.get_doc("BOM", layout.generated_bom)
		if bom_before.docstatus == 1:
			self.assertEqual(bom.docstatus, 2)
		else:
			self.assertEqual(bom.status, "Cancelled")
```

Notes for the implementer: the fake tests show `deactivate_generated_bom` sets `is_active=0, disabled=1, is_default=0, status="Superseded"` — assert `disabled` too if the site's BOM doctype has that field (`frappe.get_meta("BOM").has_field("disabled")`); skip that single assertion otherwise rather than the whole test. `cancel_generated_bom`'s draft-vs-submitted branches come from the fake tests at lines 2242/2469 of the pre-conversion file — the conditional assertion above covers whichever docstatus the real release flow produces.

- [ ] **Step 2: Run, commit**

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
git add sheet_cutting_layout/tests/test_release_service.py
git commit -m "test: real-record BOM supersede and cancel coverage"
```

### Task 14: Release service — real revision flow and release context

**Files:**
- Modify: `sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Add revision + context tests to `TestReleaseServiceIntegration`**

```python
	def test_controller_revision_clones_real_released_layout(self) -> None:
		from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.sheet_cutting_layout import (
			create_sheet_cutting_layout_revision,
		)
		from sheet_cutting_layout.tests.factories import register_test_doc

		layout = self._release_ready_layout()
		self._release(layout)

		revision_name = create_sheet_cutting_layout_revision(layout.name)
		register_test_doc("Sheet Cutting Layout", revision_name)

		revision = frappe.get_doc("Sheet Cutting Layout", revision_name)
		self.assertEqual(revision.status, "Draft")
		self.assertEqual(revision.based_on_layout, layout.name)
		self.assertEqual(revision.revision_no, layout.revision_no + 1)
		self.assertFalse(revision.generated_bom)
		self.assertFalse(revision.is_active)

	def test_get_release_context_discovers_real_family_layouts_and_boms(self) -> None:
		from sheet_cutting_layout.services.release_service import get_release_context

		layout = self._release_ready_layout()
		self._release(layout)
		layout.reload()

		context = get_release_context(layout)

		context_layout_names = [getattr(row, "name", None) for row in context.layouts]
		self.assertIn(layout.name, context_layout_names)
		context_bom_names = [getattr(row, "name", None) for row in context.boms]
		self.assertIn(layout.generated_bom, context_bom_names)
```

If `get_release_context` returns lightweight rows (dicts or namedtuples) rather than documents, adapt the attribute access (`row.name` vs `row["name"]`) to the real return shape — check `ReleaseContext` in `sheet_cutting_layout/services/release_service.py` first.

- [ ] **Step 2: Run, commit**

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
git add sheet_cutting_layout/tests/test_release_service.py
git commit -m "test: real-record revision and release context coverage"
```

### Task 15: Final verification

- [ ] **Step 1: Acceptance criteria sweep (spec section 7)**

```bash
# 1+2: no pytest artifacts anywhere current
grep -rn "pytest\|unittest_adapter\|add_pytest_style_tests" sheet_cutting_layout/ scripts/ .github/ pyproject.toml README.md
# 3: no frappe-less guards (only base.py's frappe-version compat import may appear)
grep -rn "except ImportError" sheet_cutting_layout/
```

Expected: first grep empty; second shows only `sheet_cutting_layout/tests/base.py`.

- [ ] **Step 2: Full suites on both benches**

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout
bench --site frappe16.localhost run-tests --app sheet_cutting_layout   # from the bench16 root
```

Expected: OK on both. Re-run each twice in a row to confirm cleanup leaves the site reusable (criterion 6) — second run must also pass and `bench --site development.localhost console` query `frappe.get_all("Item", filters={"name": ["like", "SCLTEST%"]})` after the run returns `[]`.

- [ ] **Step 3: Lint**

```bash
pre-commit run --all-files
```

Expected: all hooks pass.

- [ ] **Step 4: Final commit if any stragglers, then done**

```bash
git status   # should be clean; commit anything outstanding with an appropriate message
```
