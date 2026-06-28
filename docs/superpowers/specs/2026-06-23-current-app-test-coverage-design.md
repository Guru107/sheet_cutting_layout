# Current App Test Coverage Design

Date: 2026-06-23  
Status: Ready for user review  
Scope: Gap-driven unit, integration, and E2E coverage for the current live Sheet Cutting Layout app on Frappe v15 and v16

> **2026-06-28 marketplace-audit update:** The coverage-gate orchestration is now the shell runner
> `scripts/run_current_coverage_gates.sh`, not a Python subprocess wrapper. The Python scripts remain
> data checkers only; the shell runner executes `bench` and checker commands directly while keeping
> the same four independent gates and command flags.

## 1. Problem And Goal

The app already has Frappe-native Python tests and Cypress E2E specs, but the coverage gate is not
explicit enough for the current support target: both local benches must prove current live behavior
above 96% without carrying tests for removed features.

Goal:

1. Keep Python project-owned coverage above 96% on bench15 and bench16.
2. Keep Desk JS/E2E current-flow coverage above 96% on bench15 and bench16.
3. Add only behavior tests that prove real calculations, document lifecycle, workflow, permissions,
   exports, generated BOMs, and user-visible Desk flows.
4. Delete or exclude stale tests for removed features instead of preserving them for coverage.

## 2. Current Feature Boundary

The coverage matrix covers only behavior that exists in the current app:

1. Sheet Cutting Layout create, save, validate, approval, rejection-to-draft, release, supersede,
   cancel, and cleanup behavior.
2. BOM creation, generated BOM references, manual shearing BOM restrictions, end-piece reuse BOMs,
   generated end-piece Items, and strip or weight calculations.
3. LH/RH finished-part behavior that is still present.
4. Single-layout IATF export using the current template behavior.
5. Current Desk form behavior: field calculations, child table editing, validation feedback,
   workflow actions, generated links, and export/download flow.
6. Permissions that affect outcomes, such as workflow actions, release, export, and generated BOM
   access.

Out of scope:

1. Removed `child_layout` behavior.
2. Recursive end-piece release, recursive export, cascade cancellation, and child-layout permission
   checks.
3. Tests that only assert old fields are absent.
4. Cosmetic schema tests, import-only duplication, fixture text checks, and tests that only prove
   Frappe metadata exists.

Trade-off: stale tests may be deleted even if they raise coverage numbers. New coverage must come
from current behavior.

## 3. Coverage Gates

The four results are independent and must each pass:

1. bench15 Python coverage: `development.localhost`, greater than 96%.
2. bench16 Python coverage: `frappe16.localhost`, greater than 96%.
3. bench15 Desk JS/E2E current-flow coverage: `development.localhost`, greater than 96%.
4. bench16 Desk JS/E2E current-flow coverage: `frappe16.localhost`, greater than 96%.

Python coverage measures project-owned Python modules under `sheet_cutting_layout`. Exclude
framework, generated, vendored, empty package marker, and pass-through DocType boilerplate files
that have no app behavior. Do not add no-op tests just to execute those files.

Desk JS/E2E coverage is flow coverage, not Istanbul line coverage. A current-flow manifest defines
the executable live user-visible flow IDs. Cypress specs mark flow IDs only when the browser actually
exercises that behavior. Removed-feature IDs are not in the manifest.

Trade-off: flow coverage is less granular than JS line coverage, but it measures the Desk contract
users rely on and avoids heavy instrumentation inside Frappe Desk.

## 4. Test Strategy

Use the lightest test that proves the behavior:

1. Unit tests for pure calculations, naming, geometry, service branch logic, and failure handling.
2. Integration tests for DocType controllers, Frappe hooks, database behavior, workflow actions,
   permissions, BOM documents, and patches.
3. E2E tests for critical Desk workflows that lower-level tests cannot prove.

Coverage filling is measurement-led:

1. Add coverage configuration and dual-bench gate commands.
2. Run the current suite and collect Python uncovered lines plus missing E2E flow IDs.
3. Remove stale recursive or child-layout tests from the active E2E set.
4. Add focused behavior tests for real uncovered current behavior.
5. Repeat until all four gates pass.

Likely Python targets include uncovered branches in BOM services, end-piece BOM generation, controller
workflow guards, release and supersede cleanup, export failures, versioning, and permission-sensitive
paths. Likely E2E targets include live form calculations, validation feedback, approval and rejection,
release, generated BOM links, single-layout export, and reload persistence.

## 5. Runner Design

Add one small orchestration command for the full gate. It should:

1. Run Python coverage through Frappe's native test runner from each bench root.
2. Run Cypress through Frappe's native UI runner from each bench root.
3. Report all four results even when one fails.
4. Write reports under ignored output directories.
5. Print exact failing commands and report paths.

The runner must be conservative. It should preflight site reachability, app installation, migration
state, assets, Cypress availability, and coverage tooling. It must not run `bench migrate`,
`bench build`, or destructive cleanup automatically. When setup is stale, it prints the exact command
the developer should run.

Trade-off: one runner script adds a little maintenance, but it prevents manual bench drift and makes
the dual-version gate repeatable.

## 6. Failure Handling

Failures should be specific:

1. Missing coverage tooling: print the dev setup command.
2. Bench unavailable: identify the bench root and site.
3. App not installed, migration stale, or assets stale: print the exact `bench --site ... migrate` or
   `bench build` command.
4. Removed-feature specs or flow IDs in the active gate: fail with stale names so they can be deleted
   or excluded.
5. Python coverage at or below 96%: report uncovered project-owned files and lines.
6. E2E flow coverage at or below 96%: report missing live flow IDs.

Bench environment blockers are blockers, not coverage failures. They should be fixed explicitly
before interpreting coverage.

## 7. Documentation And Commands

Document:

1. The full dual-bench coverage command.
2. The per-bench Python coverage command.
3. The per-bench Cypress flow coverage command.
4. How to add a current E2E flow ID.
5. How to remove stale flow IDs when behavior is deleted.
6. Which files are excluded from Python coverage and why.

Keep generated reports, screenshots, videos, and coverage artifacts ignored.

## 8. Trade-offs

1. Measuring first avoids padding the suite with cosmetic tests, but it requires at least one full
   coverage cycle before final test additions are known.
2. Separate gates are stricter than a combined average because one strong bench cannot hide the other.
3. Flow coverage for Desk JS is intentionally behavior-first. It avoids heavy instrumentation but
   requires a maintained current-flow manifest.
4. Excluding boilerplate files keeps the Python gate meaningful. The cost is that exclusions must be
   reviewed when a previously empty file gains behavior.
5. Deleting removed-feature tests may temporarily lower coverage, but it keeps the suite honest.
