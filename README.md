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
- Project Manager: approves submitted layouts.
- Purchase Manager: approves PM-approved layouts for release.
- MR Coordinator: releases approved layouts.

## Workflow

Layouts move through `Draft -> Submitted for Check -> PM Approved -> Approved by Purchase -> Released`.

## Validation Rules

Finished part item codes must be alphanumeric and end with `SHR`. Each layout uses one parent-level finished part input (`finished_part_code`) plus `net_weight_per_part_kg`; the app derives `gross_weight_per_part_kg`, `scrap_weight_per_part_kg`, and `parts_per_sheet`. The `finished_parts` table is hidden until a BOM is generated and then acts as a read-only BOM reference view. Process scrap requires `process_scrap_item`.

## BOM Mapping

MR Release creates one native ERPNext Shearing BOM for the finished part. BOM quantity equals `no_of_strips`, raw material quantity is the full sheet weight in Kg, process scrap uses `process_scrap_item`, reusable end pieces do not create Shearing BOM scrap rows, and end pieces marked `Scrap` create separate rows using their row-level `scrap_item`. After release, the layout stores the generated BOM link and audits that BOM against the layout on every save.

Derived shearing BOMs are not manually editable. Any change to a released shearing BOM must start from the Sheet Cutting Layout.

## Revisioning

Use `New Version` on a released Sheet Cutting Layout to create the next revision. The new draft carries forward the layout inputs, clears approval history, clears the generated BOM link, and goes through the full approval flow again. Releasing the new revision creates a new BOM version and leaves older released layouts and BOMs unchanged.

Use `Supersede` only when you want to retire a released layout. Superseding deactivates the BOM linked to that layout.

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
