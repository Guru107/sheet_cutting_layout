# Development Setup

Run bench commands from a local bench root such as `~/Workspace/bench15` or `~/Workspace/bench16`.

## Add The App To A Bench

Use Frappe Bench to add this app to your local bench, enable it on the target site, and run the site
migration. Keep site-specific commands in your local runbook instead of this marketplace-facing
repository description.

## Repo Tooling Setup

```bash
cd sheet_cutting_layout
cp .env.example .env
./scripts/setup_dev.sh
source .venv/bin/activate
```

`scripts/setup_dev.sh` creates `.venv`, installs the editable package plus dev dependencies from `pyproject.toml`, and installs `pre-commit`.
