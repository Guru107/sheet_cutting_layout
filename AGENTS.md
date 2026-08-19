# Repository Guidelines

## Start Here

This is a Frappe/ERPNext app for sheet cutting layouts for press parts. Keep this file lean; use the
focused docs for details:

- [Project Overview](docs/project-overview.md)
- [Coding Conventions](docs/coding-conventions.md)
- [Development Philosophy](docs/development-philosophy.md)
- [Developer Operations](docs/developer-operations.md)

## Build, Test, and Development Commands

Run bench commands from a local bench root, such as `~/Workspace/bench15` or `~/Workspace/bench16`.

- Use Frappe Bench to add this app into a local bench.
- Enable the app on the target site through the local bench workflow.
- `bench --site <site-name> migrate`: apply schema changes and patches.
- `bench --site <site-name> run-tests --app sheet_cutting_layout`: run app tests.
- `pre-commit install`: enable local formatting and lint checks from the app directory.
- `pre-commit run --all-files`: run Ruff, Prettier, ESLint, and repository sanity checks.

## Testing Guidelines

The app has Frappe-native Python tests and Cypress Desk tests. Add focused tests alongside the module
they exercise, using `test_*.py` filenames for Python and current-flow IDs for Cypress. Prefer tests
that verify document behavior, calculations, permissions, workflow, patches, and user-visible Desk
flows through Frappe APIs or the Desk UI. Before opening a PR, run the dual-bench coverage gate:

```bash
scripts/run_current_coverage_gates.sh
```

The runner uses `~/Workspace` benches when present and falls back to `/root/workspace`; set
`SCL_BENCH15_ROOT` and `SCL_BENCH16_ROOT` for any other layout.

These gates are not enforced in CI; run them locally before opening a PR.

Each Python and Desk JS/E2E gate must be above 96% independently on bench15 and bench16; included
Python files must also stay at or above 90%.

## Commit & Pull Request Guidelines

Current history uses Conventional Commit style, for example `feat: Initialize App`. Keep commits
small and use prefixes such as `feat:`, `fix:`, `docs:`, `test:`, or `chore:`. Pull requests should
include a short summary, testing evidence, linked issue or task context, and screenshots for visible
UI changes. Call out migrations, patches, or configuration changes so reviewers can assess rollout
risk.

## Security & Configuration Tips

Do not commit bench site config, credentials, API keys, generated build output, or private data.
Keep long-running work out of request hooks; use Frappe background jobs for expensive operations.
When adding database-heavy features, include selective filters and mention useful indexes in the PR.

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues using the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the canonical `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, and `wontfix`
labels. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repository using root `CONTEXT.md` and `docs/adr/`. See
`docs/agents/domain.md`.
