# Pytest Removal and Frappe-Native Test Migration Design

Date: 2026-06-11
Status: Approved by user
Scope: Remove every pytest-derived artifact from the test suite and migrate fake-based tests to
real Frappe records where practical.

## 1. Problem and Goal

The 2026-05-25 bench-native migration moved test execution to `bench run-tests`, but it left
behind `sheet_cutting_layout/tests/unittest_adapter.py`: a 253-line shim that re-implements
pytest idioms (`approx`, `raises`, `fixture`, `MonkeyPatch`, `mark.parametrize`) and dynamically
attaches module-level `test_*` functions to `TestCase` classes via `add_pytest_style_tests()`.
Three test files still depend on it, and the suite retains a frappe-less fallback mode so tests
can run without a bench.

Goals:

1. Delete the `unittest_adapter` shim and its self-test.
2. Convert all 84 adapter-dependent test functions to native `FrappeTestCase` methods.
3. Remove the frappe-less fallback; the suite runs exclusively via `bench run-tests`.
4. Migrate fake-based tests to real Frappe records where practical.
5. Keep Hypothesis property/state tests (Hypothesis composes natively with unittest).

Production code needs no changes: pytest references exist only in the test layer.

## 2. Current State Inventory

Adapter-dependent files (module-level test functions attached via `add_pytest_style_tests`):

| File | Test functions | Notes |
| --- | --- | --- |
| `sheet_cutting_layout/tests/test_bom_service.py` | 15 | Pure BOM math against dataclass fakes |
| `sheet_cutting_layout/tests/test_model_workflow_state_machine.py` | 6 | Hypothesis state machine + workflow model |
| `sheet_cutting_layout/tests/test_release_service.py` | 63 | 2,573 lines; fixture contracts plus release/supersede/cancel flows against `FrappeStub` fakes |

Adapter infrastructure:

1. `sheet_cutting_layout/tests/unittest_adapter.py` — the shim (delete).
2. `sheet_cutting_layout/tests/test_unittest_adapter.py` — tests the shim (delete).

Frappe-less mode (`try: import frappe / except ImportError` guards) exists in six files:
`base.py`, `factories.py`, `test_setup.py`, `test_release_service.py`,
`test_model_workflow_state_machine.py`, and
`sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`.

CI (`scripts/run_ephemeral_python_tests.sh`) installs pytest even though it runs
`bench run-tests`. `pyproject.toml` is already pytest-free; `hypothesis` stays in
`[tool.bench.dev-dependencies]`.

## 3. Chosen Approach: Two Phases

Phase 1 performs a mechanical native conversion and full pytest eradication, leaving the suite
green and pytest-free. Phase 2 migrates fake-based tests to real records module by module.

Rationale: the explicit removal goal lands quickly and verifiably; conversion regressions cannot
be confused with integration-test failures; each phase is independently reviewable and
revertible. The trade-off is that the three files are touched twice.

Alternatives considered:

1. Single-pass per module (convert plus integrate in one rewrite per file): each test is touched
   once, but the adapter survives until the last module converts, and a single 2,500-line rewrite
   of the release service tests mixes two transformations, making failures hard to attribute.
2. Big-bang (everything in one pass): one review, but a huge diff with no bisection point.

## 4. Phase 1 — Pytest Eradication

### 4.1 Deletions

1. `sheet_cutting_layout/tests/unittest_adapter.py`
2. `sheet_cutting_layout/tests/test_unittest_adapter.py`

### 4.2 Conversion of the three adapter files

Module-level `test_*` functions become methods on their existing `SheetCuttingLayoutTestCase`
subclasses. `add_pytest_style_tests(globals(), ...)` calls are removed. Idiom mapping:

| Adapter idiom | Native replacement |
| --- | --- |
| `fixture(autouse=True)` | `setUp` with `unittest.mock.patch` and `addCleanup` |
| `MonkeyPatch.setattr` / `setitem` | `mock.patch.object` / `mock.patch.dict` (context manager or `addCleanup`) |
| `raises(X, match=...)` | `self.assertRaisesRegex(X, ...)` |
| `approx(x)` | `self.assertAlmostEqual` or the existing `assertFloatAlmostEqual` |
| `fail(msg)` | `self.fail(msg)` |
| `mark.parametrize` | `for case in ...:` with `self.subTest(...)` |
| Hypothesis functions collected via adapter | `FrappeTestCase` method invoking `run_state_machine_as_test(...)`; `@given` functions become plain methods |

`test_release_service.py` is split into multiple focused classes during conversion (fixture
contracts, release flow, supersede/cancel, audit validators) within the same file.

### 4.3 Frappe-less mode removal

1. `base.py` imports `FrappeTestCase` unconditionally. A frappe-version compatibility import is
   allowed (`frappe.tests.utils.FrappeTestCase` on v15, `frappe.tests.IntegrationTestCase` on v16
   if the old path is absent); both are frappe-native. No `unittest.TestCase` fallback remains.
2. `factories.py`, `test_setup.py`, `test_release_service.py`,
   `test_model_workflow_state_machine.py`, and `test_sheet_cutting_layout.py` drop their
   `try: import frappe` guards, `frappe = None` branches, and `skipUnless(frappe)` decorators.
3. The stale "pytest also collects it by name in frappe-less runs" comment in `test_setup.py` is
   deleted.

### 4.4 CI and config

1. `scripts/run_ephemeral_python_tests.sh`: change `bench pip install pytest hypothesis` to
   `bench pip install hypothesis`.
2. `pyproject.toml`: no change required; verify it stays pytest-free.

Phase 1 exit gate: full suite green via `bench run-tests` on both benches with no pytest
artifacts remaining.

## 5. Phase 2 — Integration Migration

Decision rule: if the behavior under test crosses a frappe API boundary (`get_doc`, `db`,
document lifecycle, workflow transitions, BOM submission), rewrite it against real records. If it
is pure calculation or data shaping, keep the fakes in native idiom.

Stays isolated (pure logic):

1. BOM math in `test_bom_service.py` (`build_bom_from_layout_row` quantity/weight/scrap
   arithmetic).
2. `LayoutWorkflowModel` state machine tests (pure in-memory model, no database).
3. Fixture-contract tests in `test_release_service.py` (hooks list, `workflow.json` and
   `custom_field.json` content checks).

Goes integration (real records):

1. Release service: release to BOM generation, supersede, cancel, and revision/versioning flows
   against real `Sheet Cutting Layout`, `Item`, `BOM`, and `Project` documents.
2. Audit validator paths that read real BOM documents.
3. BOM-service paths where ERPNext BOM document behavior matters (defaults, submission,
   `is_default` flag).

Infrastructure: the existing `factories.py` registry (`register_test_doc`, prefix-swept cleanup,
`atexit` hook) and the `_insert_if_missing` pattern from `test_sheet_cutting_layout.py` are
promoted into shared factory helpers (for example `ensure_item`, `ensure_project`,
`ensure_layout`) so all integration tests share one setup vocabulary.

Batch order (smallest blast radius first):

1. `test_model_workflow_state_machine.py`
2. `test_bom_service.py`
3. `test_release_service.py`

Each batch is verified with a module-scoped `bench run-tests --module` run before moving on.

## 6. Error Handling and Risks

1. Fake-versus-real divergence: integration conversion may expose behaviors the fakes papered
   over. Each such failure is investigated as a potential real finding before adjusting the test,
   never silently re-faked.
2. Runtime growth: real-record tests are slower. Mitigation: keep pure-logic tests isolated and
   reuse class-level `setUpClass` setup for expensive records.
3. Frappe v15/v16 compatibility: the unconditional `FrappeTestCase` import must work on both
   benches; verified by running the suite on both.
4. Hypothesis determinism: keep bounded settings (`max_examples`, deadline configuration) so
   bench runs stay stable.

## 7. Acceptance Criteria

1. No `pytest` string in any non-archived source, test, script, or CI file. Historical docs and
   specs are untouched.
2. `unittest_adapter.py` and `test_unittest_adapter.py` are deleted; no `add_pytest_style_tests`,
   `MonkeyPatch`, `approx`, `raises`, or `fixture` adapter imports remain.
3. No `try: import frappe / except ImportError` guards remain in test code; the suite requires a
   bench site.
4. All 84 converted tests pass via `bench --site <site> run-tests --app sheet_cutting_layout`,
   full suite green on bench15 (`development.localhost`) and bench16 (`frappe16.localhost`).
5. Framework-boundary tests use real records; only pure-logic tests remain fake-based.
6. Test-created records are cleaned up after runs via the existing registry and prefix sweep.
7. `pre-commit run --all-files` passes.
