# Reject Returns Sheet Cutting Layout To Draft Design

## Goal

When an approver rejects a Sheet Cutting Layout at any approval stage, the document returns to `Draft` so the creator can fix small mistakes and submit it again through the existing workflow.

## Current Behavior

The workflow fixture sends `Reject` actions to the `Rejected` state. That state is docstatus `0`, but it is only editable by `System Manager`, so the creator cannot make corrections through normal Draft editing.

The controller currently records draft workflow snapshots when status changes to mapped states. Rejection audit history must stay intact after the status target changes to `Draft`.

## Chosen Approach

Change the `Sheet Cutting Layout Approval Workflow` fixture so every `Reject` transition from these states has `next_state: "Draft"`:

- `Submitted for Check`
- `PM Approved`
- `Approved by Purchase`

Keep the action label as `Reject`. Record the rejection approval snapshot from the workflow action, not from the resulting status, so rejection history remains visible in `approval_snapshot` even though the document status becomes `Draft`.

## Trade-Offs

The current status will no longer show `Rejected`. This is intentional: the latest editable state is `Draft`, and rejection history lives in the approval snapshot table. If users later need list filters for currently rejected layouts, add a separate revision-needed state then.

The existing `Rejected` workflow state can remain in fixtures for compatibility with old records and status options. Removing it is unnecessary for this behavior and would create migration risk without solving the editability issue.

> **Update (2026-06-25):** The unreachable `Rejected` *status* was removed from the workflow fixture, the `Workflow State` fixture, the `status` Select options, and the `hooks.py` fixture filter. No transition produced it after this change, and no layout in any environment carried it, so the removal is config-only with no data migration. The `Rejection` / `Rejected` approval-snapshot **decision** value is unchanged and still records rejections.

## Data Flow

1. Approver clicks `Reject`.
2. Frappe applies the workflow transition and sets `status` back to `Draft`.
3. Controller records a `Rejection` approval snapshot for the `Reject` action.
4. Desk reloads the document through existing workflow-action refresh handling.
5. Creator edits the Draft document and submits it again with `Submit for Check`.

## Error Handling

No new error path is needed. Existing Frappe workflow permission checks decide who can reject at each stage. Existing validation still runs when the creator edits and resubmits.

## Tests

Add or update focused tests to verify:

- Rejecting from `Submitted for Check` returns the layout to `Draft`.
- Rejecting still persists a `Rejection` / `Rejected` approval snapshot.
- A rejected-to-draft layout can be edited by its creator under normal Draft behavior.
- Existing release and supersede tests continue to pass.

