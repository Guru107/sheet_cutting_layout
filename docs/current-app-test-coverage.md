# Current App Test Coverage

The Sheet Cutting Layout coverage gate measures current live behavior only.
Removed `child_layout` and recursive end-piece flows are not part of the active test matrix.

## Full Gate

Run from the app repo:

```bash
scripts/run_current_coverage_gates.sh
```

The runner uses `~/Workspace/bench15` and `~/Workspace/bench16` when they exist, then falls back to
`/root/workspace`. Set `SCL_BENCH15_ROOT` and `SCL_BENCH16_ROOT` for any other layout.

The command runs four independent gates:

1. bench15 Python coverage on `development.localhost`
2. bench16 Python coverage on `frappe16.localhost`
3. bench15 Desk JS/E2E flow coverage on `development.localhost`
4. bench16 Desk JS/E2E flow coverage on `frappe16.localhost`

Each gate must be above 96%, and each included Python file must be at least 90%. A combined average
is not accepted.

## Focused Commands

```bash
scripts/run_current_coverage_gates.sh --bench bench15 --skip-e2e
scripts/run_current_coverage_gates.sh --bench bench16 --skip-e2e
scripts/run_current_coverage_gates.sh --bench bench15 --skip-python
scripts/run_current_coverage_gates.sh --bench bench16 --skip-python
```

## Current E2E Flow IDs

The current-flow manifest lives at `cypress/support/current_flows.json`.
Cypress specs mark a flow only after the user-visible assertion has passed:

```javascript
cy.markFlow("release.single-part-generates-bom");
```

E2E reports are stamped per run; use the focused runner commands below instead of checking old JSON
reports directly.

Do not add IDs for removed behavior. When a feature is removed, delete the spec or remove the flow ID
from the manifest in the same change.

## Python Coverage Scope

Python coverage is recalculated from Frappe's `coverage.xml` for project-owned code. The checker
excludes tests, package markers, patches, generated/framework scaffolding, and pass-through DocType
controller files only while they remain pass-only. If a previously empty file gains behavior, it is
included automatically and must meet the gate.

Generated reports are written under `coverage-results/` and are not committed.
