# Bench-Native Test Migration Design

Date: 2026-05-25  
Status: Ready for user review  
Scope: Migrate the Sheet Cutting Layout test suite from pytest execution to Frappe bench-native tests.

## 1. Problem and Goal

The current suite is written as pytest tests and is exposed to `bench run-tests` through a bridge
that shells out to pytest. This is fragile in real bench environments because the subprocess can
import the wrong `frappe` package, requires pytest-specific runtime behavior, and does not follow
the standard Frappe/ERPNext test style.

Goals:

1. Run the full app suite directly with `bench --site <site> run-tests --app sheet_cutting_layout`.
2. Remove the pytest bridge and pytest-only test patterns.
3. Use Frappe-supported `unittest` discovery and `frappe.tests.utils.FrappeTestCase`.
4. Favor real Frappe documents and database-backed integration tests wherever practical.
5. Keep Hypothesis property and state tests, but make them bench-discoverable.
6. Clean up test-created records after the suite so local bench sites do not accumulate test data.

## 2. Chosen Approach

Use a bench-native hybrid test suite.

All tests will be converted to `unittest` style and discovered by Frappe's native test runner. Test
classes will inherit from `FrappeTestCase`. Tests that depend on Frappe metadata, hooks, permissions,
document lifecycle, workflow, database state, or ERPNext BOM behavior will use real records wherever
practical. Small isolated tests may remain for pure transformations or branch-heavy helpers where a
database setup would hide the behavior being tested.

Trade-off: the suite will be slower than the current mostly isolated pytest suite, but it will better
match production behavior and remove the fragile bridge.

## 3. Alternatives Considered

### Option A: Full Frappe Integration Migration

Convert every test into a real Frappe document/database test.

Pros:

1. Strongest alignment with Frappe behavior.
2. Best coverage of hooks, permissions, workflow, and ERPNext document interactions.

Cons:

1. Slowest option.
2. Some pure service branches become harder to test clearly.
3. More test data setup increases maintenance cost.

### Option B: Bench-Native Hybrid With Integration Preference (Selected)

Convert all tests to bench-native `unittest`/`FrappeTestCase`, use real records wherever practical,
and keep isolated tests for pure logic.

Pros:

1. Uses Frappe's supported test runner and style.
2. Improves confidence in real app behavior without making every test database-heavy.
3. Keeps pure calculation and data-shaping tests readable.

Cons:

1. Some fakes remain by design.
2. Requires careful judgment on whether each test should be integration or isolated.

### Option C: Minimal Mechanical Conversion

Replace pytest syntax with `unittest` syntax but keep most fake-object tests unchanged.

Pros:

1. Fastest migration.
2. Least risk of changing test intent.

Cons:

1. Weakest improvement in Frappe best-practice alignment.
2. Does not address the requirement to favor real document/database tests.

## 4. Test Structure

Remove:

1. `sheet_cutting_layout/tests/bench_pytest_bridge.py`
2. `sheet_cutting_layout/tests/test_bench_pytest_bridge.py`

Convert test modules so Frappe can discover them directly:

1. Use classes inheriting from `frappe.tests.utils.FrappeTestCase`.
2. Keep `test_*.py` filenames.
3. Keep current file locations unless a test clearly belongs beside a DocType controller.
4. Replace pytest idioms:
   - `pytest.raises` -> `self.assertRaisesRegex`
   - `pytest.approx` -> `self.assertAlmostEqual`
   - `pytest.mark.parametrize` -> `subTest`
   - `monkeypatch` -> `unittest.mock.patch`
   - fixtures -> `setUp`, helper methods, or module-level factories

Hypothesis property and state tests will remain, but they must be wrapped in bench-discoverable
`FrappeTestCase` classes and avoid pytest-only assertions or decorators.

## 5. Integration Strategy

Use real Frappe/ERPNext records for behavior where framework state matters:

1. Sheet Cutting Layout validation and derived fields through `frappe.get_doc`, `insert`, `save`,
   and controller lifecycle hooks.
2. Workflow and release paths through real `Sheet Cutting Layout` documents and the app's workflow
   wrapper where practical.
3. BOM creation and manual shearing BOM restrictions through ERPNext native `BOM` documents and real
   custom fields.
4. End-piece BOM preview/generation through real Items, BOMs, Projects, and layout rows for main
   happy paths and validation paths.
5. Patch behavior through real records when setup is compact and reliable.

Keep isolated tests only when:

1. The target is pure calculation or data shaping.
2. Creating database state would be slow or obscure the branch under test.
3. The branch explicitly handles missing Frappe/runtime dependencies.

Pytest-specific production seams must not remain. Existing code such as runtime checks based on
`"pytest" in sys.modules` should be removed or replaced with explicit dependency injection,
bench-safe helpers, or direct failure behavior that is meaningful outside tests. Missing-Frappe
branches may still be tested with `unittest.mock.patch`, but the product code must not know about
pytest as a runtime.

## 6. Test Data and Factories

Add a small test support layer, for example `sheet_cutting_layout/tests/factories.py`.

Factories should create only records needed by the app:

1. Item groups and UOM prerequisites if missing.
2. Raw material Item.
3. Process scrap Item.
4. Finished part Item ending in `SHR`.
5. Reusable end-piece Item.
6. Project.
7. Valid Sheet Cutting Layout documents with child rows.

Rules:

1. Use deterministic names or a common test prefix.
2. Check for existing records before creating shared prerequisites.
3. Avoid large global fixtures.
4. Let each test class request the setup it needs.
5. Keep helpers small and explicit.
6. Any test that creates records without using the shared factories must still use the reserved test
   prefix and register those records for cleanup.

## 7. Teardown and Site Cleanliness

The suite must remove documents and objects it creates so local bench sites remain clean after test
runs.

Design:

1. Test factories will register created document names in a central test registry.
2. Factories will also use a reserved test prefix such as `SCL-TEST-` for records they create.
3. The first import of the test support module will register an `atexit` cleanup callback. This is
   the bench-native end-of-process hook for full app runs.
4. Shared base test classes will also register class cleanup as a fallback for focused module runs.
5. Cleanup will run both the registry and a conservative prefix sweep. The registry removes records
   known to this process; the prefix sweep removes stale records from interrupted previous runs.
6. The cleanup callback must verify that a Frappe site and DB connection are available. If the
   connection has already been torn down, it should reconnect to the current site before deleting
   records.
7. Cleanup must be best-effort and failure-tolerant:
   - ignore missing records
   - continue after individual delete failures where safe
   - log or print skipped records for follow-up
   - commit only cleanup deletes, never application test assertions
8. Cleanup will delete records in dependency-safe order, for example:
   - BOMs and generated child records
   - Sheet Cutting Layout records
   - Project records
   - test Items
   - optional test-only UOM or Item Group records if they were created by this app's tests
9. Cleanup must use force/delete APIs carefully and only target records created by the test suite.
10. Prefix sweeps must be limited to explicit DocTypes and fields used by the factories. They must
   not run broad deletes across arbitrary DocTypes.
11. Tests should still rely on `FrappeTestCase` rollback behavior for per-test isolation where
   Frappe supports it.

Trade-off: a global cleanup registry plus prefix sweep adds test infrastructure and must be kept
conservative, but it prevents test artifacts from polluting developer bench sites and makes repeated
local runs safer.

## 8. Migration Batches

### Batch 1: Foundation

1. Add shared `FrappeTestCase` helpers and factories.
2. Add the teardown registry.
3. Convert one small module and confirm direct bench discovery.

### Batch 2: Pure and Low-Risk Modules

1. Convert config/source-contract tests.
2. Convert pure BOM service tests.
3. Keep isolated tests where the subject is pure logic.

### Batch 3: Validation and Document Lifecycle

1. Convert validator tests to real `Sheet Cutting Layout` documents where practical.
2. Keep direct helper tests only for pure calculations.

### Batch 4: Release, Workflow, and BOM Integration

1. Convert release service tests.
2. Convert BOM override tests.
3. Convert end-piece BOM service tests.
4. Convert workflow state tests to real Frappe paths where practical.

### Batch 5: Property and State Tests

1. Keep Hypothesis.
2. Convert pytest-specific assertions to `unittest` assertions.
3. Use deterministic settings and bounded example counts so bench runtime stays stable.
4. For state-machine tests, use a bench-discoverable `FrappeTestCase` method that invokes the
   Hypothesis state machine runner rather than relying on pytest collection behavior.

### Batch 6: Cleanup

1. Delete the pytest bridge.
2. Remove pytest dependency assumptions from current docs/config and production code. Do not edit
   archived historical specs or plans just because they mention pytest.
3. Run bench15 and bench16 app suites.
4. Run pre-commit.

## 9. Acceptance Criteria

1. `bench --site <site> run-tests --app sheet_cutting_layout` runs the full suite directly.
2. No `pytest` import, pytest fixture, pytest marker, `pytest.raises`, `pytest.approx`, or pytest
   bridge remains in app tests.
3. Hypothesis property/state tests remain and run under bench.
4. Framework-sensitive behavior uses real Frappe/ERPNext records wherever practical.
5. Isolated tests remain only for pure logic or impractical framework branches.
6. The suite does not require `SHEET_CUTTING_LAYOUT_PYTEST_PYTHON` or any pytest subprocess wrapper.
7. Product code does not contain pytest-specific runtime detection.
8. Test-created documents are removed after the suite completes, and stale prefixed records from
   interrupted previous runs are cleaned conservatively.
9. Current docs/config no longer recommend pytest for this app's primary test workflow.
10. Bench15 passes: `bench --site development.localhost run-tests --app sheet_cutting_layout`.
11. Bench16 passes: `bench --site frappe16.localhost run-tests --app sheet_cutting_layout`.
12. `pre-commit run --all-files` passes.

## 10. Rollout Risks

1. Runtime may increase because more tests will use the database and ERPNext documents.
2. Some current fake-based tests may reveal real setup gaps when moved to integration tests.
3. Cleanup must be conservative to avoid deleting real local records.
4. Hypothesis tests must stay bounded to avoid slow or flaky bench runs.

The implementation should proceed in batches, verifying bench discovery and runtime after each
major group.

## 11. Migration Inventory

| Current module | Batch | Expected style |
| --- | --- | --- |
| `sheet_cutting_layout/tests/test_cypress_config.py` | Batch 2 | Isolated source/config assertions under `FrappeTestCase` |
| `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py` | Batch 2 and 3 | Source-contract tests plus integration tests for the DocType controller |
| `sheet_cutting_layout/tests/test_bom_service.py` | Batch 2 | Mostly isolated pure service tests, with integration coverage added where BOM document behavior matters |
| `sheet_cutting_layout/tests/test_property_layout_invariants.py` | Batch 5 | Hypothesis property tests wrapped in bench-discoverable `FrappeTestCase` |
| `sheet_cutting_layout/tests/test_validators.py` | Batch 3 | Real `Sheet Cutting Layout` document validation tests wherever practical; isolated tests only for pure helpers or permission seams |
| `sheet_cutting_layout/tests/test_bom_overrides.py` | Batch 4 | ERPNext native `BOM` integration tests |
| `sheet_cutting_layout/tests/test_end_piece_bom_service.py` | Batch 4 | Real Item, BOM, Project, and layout integration tests for preview/generation paths |
| `sheet_cutting_layout/tests/test_release_service.py` | Batch 4 | Real release/workflow/BOM integration tests, with isolated tests only for explicit dependency-injection or missing-runtime branches |
| `sheet_cutting_layout/tests/test_model_workflow_state_machine.py` | Batch 5 | Hypothesis state tests invoked from a `FrappeTestCase` method |
| `sheet_cutting_layout/tests/test_bench_pytest_bridge.py` | Batch 6 | Delete |
| `sheet_cutting_layout/tests/bench_pytest_bridge.py` | Batch 6 | Delete |
