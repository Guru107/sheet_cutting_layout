# Sheet Cutting Layout

Frappe/ERPNext app for controlled sheet cutting layout releases for press parts. The module owns layout validation, approval workflow, BOM generation, revisioning, end-piece handling, and workbook export from a single `Sheet Cutting Layout` document.

## Current Module Scope

- Create and validate single-part and LH/RH paired sheet cutting layouts.
- Drive the approval flow from draft through release and supersede with approval snapshots.
- Generate native ERPNext shearing BOMs only after release.
- Generate reuse end-piece item masters and end-piece BOMs from released layouts.
- Export released layouts as `.xlsx` workbooks.
- Keep generated BOM references on the layout and audit them on save.

## Development And Operations Docs

- Setup and local bench install: `docs/development-setup.md`
- Release procedure: `docs/release-checklist.md`
- Contributor workflow: `AGENTS.md`

## Release Management

- `develop` is the integration branch
- `release/v1` is the stable branch for all `1.x` releases
- create release tags such as `v1.0.0` from `release/v1` only
- promote tested changes from `develop` into `release/v1`; do not do feature work directly on the stable branch

Before tagging a release:

```bash
python -m unittest scripts.tests.test_check_release_metadata -v
python scripts/check_release_metadata.py
pre-commit run --all-files
python scripts/run_current_coverage_gates.py
```

See `docs/release-checklist.md` for the operator checklist and rollback flow.

## Repository Shape

- `sheet_cutting_layout/hooks.py`: app metadata and exported fixtures
- `sheet_cutting_layout/services/`: release, BOM, validation, export, geometry, and versioning logic
- `sheet_cutting_layout/overrides/bom.py`: app-owned BOM behavior overrides
- `sheet_cutting_layout/fixtures/`: workflow, roles, custom fields, and workflow states
- `sheet_cutting_layout/tests/`: Frappe-native Python tests and smoke coverage
- `scripts/`: dev bootstrap, coverage checks, and bench runners

## Workflow

Layouts move through `Draft -> Submitted for Check -> PM Approved -> Approved by Purchase -> Released`.

Primary roles:

- Projects User: creates draft layouts and submits them for check
- Projects Manager: approves submitted layouts
- Purchase Manager: approves PM-approved layouts
- MR Coordinator: releases approved layouts and supersedes released ones

`Reject` returns an in-review layout to `Draft`. `Supersede` retires a released layout and deactivates its generated BOMs. `System Manager` keeps administrative access outside the normal role handoff.

## Release Behavior

Finished part item codes must be alphanumeric and end with `SHR`. Each layout uses one parent-level finished part input (`finished_part_code`) plus `net_weight_per_part_kg`; the app derives `gross_weight_per_part_kg`, `scrap_weight_per_part_kg`, and `parts_per_sheet`. The `finished_parts` table is hidden until a BOM is generated and then acts as a read-only BOM reference view. Process scrap requires `process_scrap_item`.

MR Release creates one native ERPNext Shearing BOM for the finished part and submits it immediately. BOM quantity equals `parts_per_sheet`, raw material quantity is the full sheet weight in Kg, process scrap uses `process_scrap_item`, reusable end pieces do not create Shearing BOM scrap rows, and end pieces marked `Scrap` create separate rows using their row-level `scrap_item`. End-piece `qty_per_sheet` is no longer an active input; each row represents one end piece per sheet. End-piece BOMs generated from released layouts are also submitted immediately. After release, the layout stores the generated BOM link and audits that BOM against the layout on every save.

Derived shearing BOMs are layout-owned. `Update Cost` remains allowed through ERPNext, but `New Version`, `Cancel`, and `Amend` must be driven from `Sheet Cutting Layout` instead.

LH/RH layouts generate two finished-part BOMs with persisted orientation on the reference rows and a secondary `twin_generated_bom` link on the layout.

## Revisioning And Recovery

Use `New Version` on a released Sheet Cutting Layout to create the next revision. The new draft carries forward the layout inputs, clears approval history, clears the generated BOM link, and goes through the full approval flow again. Releasing the new revision creates a new BOM version and leaves older released layouts and BOMs unchanged.

Use `Supersede` only when you want to retire a released layout. Superseding deactivates the BOM linked to that layout.

If release fails, keep the layout in `Approved by Purchase`, fix the validation or master-data issue, and rerun the release action. Scrap items used in generated BOMs must have a resolvable valuation rate before release or end-piece BOM generation can succeed.

## Testing

Documentation-only changes do not need new tests, but production behavior in this repo is test-first and coverage-gated.

Focused commands:

```bash
bench --site <site-name> run-tests --app sheet_cutting_layout
bench --site <site-name> run-ui-tests sheet_cutting_layout --headless
pre-commit run --all-files
```

Full current-behavior coverage gate:

```bash
python scripts/run_current_coverage_gates.py
```

The gate runs four checks:

1. `bench15` Python coverage on `development.localhost`
2. `bench16` Python coverage on `frappe16.localhost`
3. `bench15` Desk JS/E2E flow coverage on `development.localhost`
4. `bench16` Desk JS/E2E flow coverage on `frappe16.localhost`

Each gate must be above 96%, and each included Python file must stay at or above 90%.

For isolated app verification against a throwaway site:

```bash
DB_ROOT_PASSWORD=<mariadb-root-password> ./scripts/run_ephemeral_python_tests.sh
```

## Related Docs

- `AGENTS.md`
- `docs/project-overview.md`
- `docs/coding-conventions.md`
- `docs/development-philosophy.md`
- `docs/current-app-test-coverage.md`
