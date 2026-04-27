# Project Overview

`sheet_cutting_layout` is a Frappe/ERPNext app for creating sheet cutting layouts for press parts.
It is currently a small app scaffold with room for DocTypes, server-side calculations, client scripts,
and reporting workflows.

## Local Bench Environments

Two local bench workspaces are available:

- `~/Workspace/bench15`
- `~/Workspace/bench16`

Local MariaDB credentials for development:

- Username: `gurudattkulkarni`
- Password: `123`

Treat these as local-only development credentials. Do not reuse them for production or shared
environments.

## Repository Structure

- `pyproject.toml`: Python package metadata and Ruff configuration.
- `sheet_cutting_layout/hooks.py`: Frappe app metadata and framework hooks.
- `sheet_cutting_layout/modules.txt`: Frappe module registration.
- `sheet_cutting_layout/patches.txt`: ordered patch list for migrations.
- `sheet_cutting_layout/patches/`: database migration patch modules.
- `sheet_cutting_layout/sheet_cutting_layout/`: app feature modules and future DocType code.
- `sheet_cutting_layout/templates/`: website templates and page modules.
- `sheet_cutting_layout/public/`: public JavaScript, CSS, and static assets.
- `docs/superpowers/`: design and implementation planning notes.

## Development Shape

Keep business behavior in server-side Python controllers and services. Use client scripts only for UI
interaction and lightweight form behavior. Add patches only for versioned database changes that must
run during `bench migrate`.
