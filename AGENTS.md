# Repository Guidelines

## Start Here

This is a Frappe/ERPNext app for sheet cutting layouts for press parts. Keep this file lean; use the
focused docs for details:

- [Project Overview](docs/project-overview.md)
- [Coding Conventions](docs/coding-conventions.md)
- [Development Philosophy](docs/development-philosophy.md)

## Build, Test, and Development Commands

Run bench commands from a local bench root, such as `~/Workspace/bench15` or `~/Workspace/bench16`.

- `bench get-app <repo-url> --branch develop`: install this app into a bench.
- `bench --site <site-name> install-app sheet_cutting_layout`: install the app on a site.
- `bench --site <site-name> migrate`: apply schema changes and patches.
- `bench --site <site-name> run-tests --app sheet_cutting_layout`: run app tests.
- `pre-commit install`: enable local formatting and lint checks from the app directory.
- `pre-commit run --all-files`: run Ruff, Prettier, ESLint, and repository sanity checks.

## Testing Guidelines

No test suite exists yet. Add focused Frappe tests alongside the feature module they exercise, using
`test_*.py` filenames. Prefer tests that verify document behavior, calculations, permissions, and
patches through Frappe APIs instead of isolated mocks. Run
`bench --site <site-name> run-tests --app sheet_cutting_layout` before opening a PR.

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
