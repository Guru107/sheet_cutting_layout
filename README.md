# Sheet Cutting Layout

Frappe/ERPNext app for controlled sheet cutting layout releases for press parts. The app stores layout parameters, validates finished-part and scrap rules, tracks sheet consumption, and generates ERPNext BOMs only after approval.

## Installation

```bash
cd ~/Workspace/bench15
bench get-app $URL_OF_THIS_REPO --branch develop
bench --site <site-name> install-app sheet_cutting_layout
bench --site <site-name> migrate
```

Local bench roots used for development are `~/Workspace/bench15` and `~/Workspace/bench16`.

## Role Matrix

- Project User: creates draft layouts and submits for check.
- Projects Manager: performs the first checker approval.
- Manufacturing Manager: performs the second checker approval after Projects approval.
- Purchase Manager: approves checked layouts for release.
- MR Coordinator: releases approved layouts.

## Workflow

Layouts move through `Draft -> Submitted for Check -> Checked -> Approved by Purchase`. MR release moves layouts directly to `Released`.

## Validation Rules

Finished part item codes must be alphanumeric and end with `SHR`. Each layout needs exactly one finished part, positive `parts_per_sheet`, non-negative gross and scrap weights, and required end-piece item/weight/quantity values. Process scrap requires `process_scrap_item`.

## BOM Mapping

MR Release creates one native ERPNext Shearing BOM for the finished part. BOM quantity equals `no_of_strips`, raw material quantity is the full sheet weight in Kg, process scrap uses `process_scrap_item`, reusable end pieces do not create Shearing BOM scrap rows, and end pieces marked `Scrap` create separate rows using their row-level `scrap_item`.

## Recovery

If release fails, keep the layout in `Approved by Purchase`, fix validation errors, and rerun the workflow action.

## Development

```bash
bench --site <site-name> run-tests --app sheet_cutting_layout
python -m ruff check .
python -m ruff format --check .
bench --site <site-name> run-ui-tests sheet_cutting_layout --headless
```

Follow `AGENTS.md` and `docs/development-philosophy.md`: all behavior changes require tests first.
