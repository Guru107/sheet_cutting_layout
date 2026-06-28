# Developer Operations

This page holds development, verification, and release-maintenance notes that are intentionally kept
out of `README.md`. The README is the package long description and should stay focused on end-user
behavior.

## Local Setup

Use `docs/development-setup.md` for local bench preparation and repository tooling notes.

## Release Management

- `develop` is the integration branch.
- `release/v1` is the stable branch for all `1.x` releases.
- Create release tags such as `v1.0.0` from `release/v1` only.
- Promote tested changes from `develop` into `release/v1`; do not do feature work directly on the
  stable branch.

Before tagging a release:

```bash
python -m unittest scripts.tests.test_check_release_metadata -v
python scripts/check_release_metadata.py
pre-commit run --all-files
scripts/run_current_coverage_gates.sh
```

See `docs/release-checklist.md` for the operator checklist and rollback flow.

## Repository Shape

- `sheet_cutting_layout/hooks.py`: app metadata and exported fixtures.
- `sheet_cutting_layout/services/`: release, BOM, validation, export, geometry, and versioning logic.
- `sheet_cutting_layout/overrides/bom.py`: app-owned BOM behavior overrides.
- `sheet_cutting_layout/fixtures/`: workflow, roles, custom fields, and workflow states.
- `sheet_cutting_layout/tests/`: Frappe-native Python tests and smoke coverage.
- `scripts/`: developer bootstrap, coverage checks, and bench runners.

## Verification

Documentation-only changes do not need new tests, but production behavior in this repo is test-first
and coverage-gated.

Focused commands:

```bash
bench --site <site-name> run-tests --app sheet_cutting_layout
bench --site <site-name> run-ui-tests sheet_cutting_layout --headless
pre-commit run --all-files
```

Full current-behavior coverage gate:

```bash
scripts/run_current_coverage_gates.sh
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
