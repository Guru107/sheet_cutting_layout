# Sheet Cutting Layout E2E UI Flow Coverage Design

Date: 2026-04-27  
Status: Approved for planning  
Scope: Browser-based Cypress coverage for current Sheet Cutting Layout module flows on Frappe 15 and 16

## 1. Problem and Goal

Recent local installation exposed browser-visible failures that lower-level tests did not catch: missing public assets, missing workflow state records, and a blank canvas preview. The module needs a hard browser test gate that proves the real Desk UI works in both supported local benches.

Goal: add bench-native Cypress UI-flow tests with a hard 96% checklist coverage gate, 100% critical-flow coverage, and semantic canvas-rendering assertions.

## 2. Hard Gate Policy

The E2E gate is mandatory for browser-visible module work.

1. Run the same Cypress suite against both benches:
   - `~/Workspace/bench15`, site `development.localhost`
   - `~/Workspace/bench16`, site `frappe16.localhost`
2. Each bench must independently satisfy:
   - 100% of current critical flows.
   - At least 96% of executable current UI flows.
3. The runner must execute both benches and report both results even if one fails.
4. Unknown flow IDs, missing critical mappings, app-owned console errors, and app-owned network `4xx/5xx` responses fail the gate.
5. Generated reports live under `cypress/results/` and are not committed.

## 3. Coverage Model

Coverage is measured by atomic user-visible flow assertions, not line coverage or spec count.

Each flow item has:

1. `id`
2. `label`
3. `priority`: `critical` or `standard`
4. `source`: design/regression reference
5. `assertedBy`: helper/spec assertion names allowed to mark it
6. optional `supportedFrappeMajors`
7. optional `status: not_implemented`

Only executable flows for the current Frappe major version count in that bench’s denominator. `not_implemented` flows remain visible but excluded until the UI exists.

## 4. Test Runner

Use Frappe’s native UI runner:

```bash
bench --site <site> run-ui-tests sheet_cutting_layout
```

Add `scripts/run_ui_flow_tests.py` as the project hard-gate command. It will:

1. Preflight both benches without mutating them.
2. Verify app installation, site reachability, DocTypes, workflow states, workflow fixture sync, assets, and Cypress availability.
3. Fail with exact commands when migration or asset build is missing.
4. Run `bench run-ui-tests` once per bench.
5. Aggregate per-bench Cypress coverage JSON.
6. Print a concise terminal table and write full JSON reports.

The preflight must not run `bench migrate` or `bench build`; it should instruct the developer to run those commands.

## 5. Cypress Structure

Use multiple focused specs and thin support helpers:

1. `cypress/integration/sheet_cutting_layout_assets.cy.js`
2. `cypress/integration/sheet_cutting_layout_form_canvas.cy.js`
3. `cypress/integration/sheet_cutting_layout_workflow.cy.js`
4. `cypress/integration/sheet_cutting_layout_roles.cy.js`
5. `cypress/support/sheet_cutting_layout_flows.js`
6. `cypress/support/sheet_cutting_layout_helpers.js`

Helpers should cover repeated behavior only: deterministic data setup, login/session reuse, role setup, workflow actions, app-console monitoring, app-network monitoring, canvas assertions, and flow marking.

## 6. Data Setup

Tests use seeded deterministic records, never manual local records like `001`.

1. Backend API setup is allowed only for prerequisites: Items, test users, roles, cleanup of `CY-SCL-*` records, and support data.
2. Browser UI must exercise the flows under test: new layout form, child table editing, save validation, workflow actions, release, reload, and BOM link navigation.
3. Cleanup is limited to Cypress-owned prefixes before each run. Failed-run records may remain for debugging.
4. Tests must not mutate global workflow definitions.

## 7. Required Flow Areas

Critical current flows:

1. App assets return `200`.
2. Form script loads `window.SheetLayoutCanvas`.
3. Sheet Cutting Layout list loads without app-relevant console errors.
4. Seeded layout appears in list and opens from list.
5. New layout form opens and saves valid data.
6. Required validation is visible on invalid save.
7. Finished Parts child table add/edit/remove works.
8. End Pieces child table add/edit/remove works.
9. Canvas preview is inserted exactly once.
10. Canvas backing dimensions are nonzero.
11. Canvas pixels are nonblank.
12. Canvas contains semantic sheet, strip, part, and end-piece color bands.
13. Invalid layout data renders the invalid marker area.
14. Editing a representative dimension redraws the canvas.
15. Reload preserves fields, child rows, status, and canvas rendering.
16. Workflow actions are visible only to expected roles for critical steps.
17. One full approval/release path completes.
18. Generated BOM links appear, open, and show expected item/active status.

Standard current flows include search/filter essentials, representative rejection path, no duplicate canvases after repeated redraws, basic desktop resize behavior, light performance sanity, and usable validation/workflow messages.

Out of scope for this suite:

1. Work Order and Production Plan pages.
2. Full BOM accounting/math validation.
3. Mobile/responsive hard gate.
4. Full accessibility audit.
5. Cypress/Istanbul JavaScript line coverage.

## 8. Canvas Correctness

Canvas tests use semantic visual invariants, not exact screenshot matching.

Assertions must check:

1. DOM presence and accessible label.
2. Nonzero CSS and backing-store dimensions.
3. Nonblank pixel ratio.
4. Expected color bands for sheet base, strips, parts, and end pieces using tolerant ranges.
5. Invalid marker color/region for invalid data.
6. Pixel changes after a dimension edit and debounce.
7. No duplicate preview wrapper/canvas after refresh or edits.
8. Optional debug image capture only when explicitly enabled; failure screenshots stay on by default.

## 9. Version Strategy

The suite is shared across Frappe 15 and Frappe 16. Version-specific differences must be centralized in helpers that detect `frappe.boot.versions.frappe`. Specs should not contain scattered version branches.

If a flow genuinely applies to only one major version, declare `supportedFrappeMajors` in the checklist with a reason.

## 10. Documentation

Update:

1. `AGENTS.md` with the short E2E gate command.
2. `docs/e2e-ui-flow-testing.md` with setup, bench URLs, preflight behavior, coverage rules, headed debugging, and how to add flow IDs.
3. `.gitignore` to exclude `.playwright-mcp/` and `cypress/results/`.

## 11. Trade-offs

1. UI-flow coverage is intentionally not line coverage. It measures the user-visible contract that matters for this Frappe module.
2. Running both benches is slower but prevents one Frappe version from masking the other.
3. Pixel-level canvas checks are more maintenance than DOM checks but directly prevent blank or malformed render regressions.
4. Backend setup for prerequisites keeps the suite focused; browser flows still validate the actual module UI.
5. Bench-native `run-ui-tests` aligns with Frappe conventions; the repo runner is only for two-bench orchestration and coverage enforcement.
