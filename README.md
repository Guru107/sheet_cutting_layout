# Sheet Cutting Layout

Frappe/ERPNext app for controlled sheet cutting layout releases for press parts. The app stores layout parameters, validates finished-part and scrap rules, renders a form-driven canvas preview, and generates ERPNext BOMs only after approval.

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
- Project Manager: performs one parallel checker approval.
- Manufacturing Manager: performs the second parallel checker approval.
- Purchase Manager: approves checked layouts for release.
- MR Coordinator: releases approved layouts or finalizes impact releases.

## Workflow

Layouts move through `Draft -> Submitted for Check -> Checked -> Approved by Purchase`. MR release moves to `Released` when no impacted manufacturing documents exist, or `Release Pending Impact` when open Work Orders or Production Plans still reference replaced BOMs. Use `Finalize Impact Release` only after every impact row has a decision.

## Validation Rules

Finished part item codes must be alphanumeric and end with `SHR`. Each layout needs at least one finished part, positive `parts_per_sheet`, non-negative gross and scrap weights, and required end-piece item/weight/quantity values. Process scrap requires `process_scrap_item`.

## BOM Mapping

BOM quantity is always 1. Each finished-part row generates one BOM. Raw material quantity equals gross finished-part weight. Process scrap uses `process_scrap_item`. End-piece scrap is distributed as `(end_piece.weight_kg * qty_per_sheet) / parts_per_sheet`.

## Impact Resolution

When a new revision replaces active BOMs, the release service creates one impact row per open reference. Choose `Use Old BOM`, `Use New BOM`, or `Cancel Reference` for each row, then run `Finalize Impact Release`. The prior active layout is superseded and linked old BOMs are disabled.

## Recovery

If release fails, keep the layout in `Approved by Purchase` or `Release Pending Impact`, fix validation or impact rows, and rerun the workflow action. If generated BOMs were created but not activated, keep them disabled until finalization or manually disable them before retrying.

## Development

```bash
pytest -q
python -m ruff check .
python -m ruff format --check .
bench --site <site-name> run-ui-tests sheet_cutting_layout --headless
```

Follow `AGENTS.md` and `docs/development-philosophy.md`: all behavior changes require tests first.
