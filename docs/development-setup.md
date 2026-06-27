# Development Setup

Run bench commands from a local bench root such as `~/Workspace/bench15` or `~/Workspace/bench16`.

## Install The App Into A Bench

```bash
bench get-app <repo-url> --branch develop
bench --site <site-name> install-app sheet_cutting_layout
bench --site <site-name> migrate
```

## Repo Tooling Setup

```bash
git clone <repo-url>
cd sheet_cutting_layout
cp .env.example .env
./scripts/setup_dev.sh
source .venv/bin/activate
```

`scripts/setup_dev.sh` creates `.venv`, installs the editable package plus dev dependencies from `pyproject.toml`, and installs `pre-commit`.
