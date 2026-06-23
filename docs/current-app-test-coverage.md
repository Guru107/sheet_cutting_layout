# Current App Test Coverage

The Sheet Cutting Layout coverage gate measures current live behavior only.
Removed `child_layout` and recursive end-piece flows are not part of the active test matrix.

## Full Gate

Run from the app repo:

```bash
python scripts/run_current_coverage_gates.py
```

The command runs four independent gates:

1. bench15 Python coverage on `development.localhost`
2. bench16 Python coverage on `frappe16.localhost`
3. bench15 Desk JS/E2E flow coverage on `development.localhost`
4. bench16 Desk JS/E2E flow coverage on `frappe16.localhost`

Each gate must be above 96%. A combined average is not accepted.

## Focused Commands

```bash
python scripts/run_current_coverage_gates.py --bench bench15 --skip-e2e
python scripts/run_current_coverage_gates.py --bench bench16 --skip-e2e
python scripts/run_current_coverage_gates.py --bench bench15 --skip-python
python scripts/run_current_coverage_gates.py --bench bench16 --skip-python
```

## Current E2E Flow IDs

The current-flow manifest lives at `cypress/support/current_flows.json`.
Cypress specs mark a flow only after the user-visible assertion has passed:

```javascript
cy.markFlow("release.single-part-generates-bom");
```

Do not add IDs for removed behavior. When a feature is removed, delete the spec or remove the flow ID
from the manifest in the same change.

## Python Coverage Scope

Python coverage is recalculated from Frappe's `coverage.xml` for project-owned code. The checker
excludes tests, package markers, patches, generated/framework scaffolding, and pass-through DocType
controller files that contain no app behavior. If a previously empty file gains behavior, remove it
from the exclusion list and add behavior coverage.

Generated reports are written under `coverage-results/` and are not committed.
