from __future__ import annotations

import frappe

from sheet_cutting_layout.services.workflow import (
	MR_RELEASE_ACTION,
	PROJECT_MANAGER_APPROVAL_ACTION,
	PURCHASE_APPROVAL_ACTION,
	REJECT_ACTION,
	SUBMIT_FOR_CHECK_ACTION,
	SUPERSEDE_ACTION,
	approval_snapshot_row,
)

_COMMENT_STATUS_ACTIONS = {
	"Submitted for Check": SUBMIT_FOR_CHECK_ACTION,
	"PM Approved": PROJECT_MANAGER_APPROVAL_ACTION,
	"Approved by Purchase": PURCHASE_APPROVAL_ACTION,
	"Released": MR_RELEASE_ACTION,
	"Rejected": REJECT_ACTION,
	"Superseded": SUPERSEDE_ACTION,
}


def execute() -> None:
	comments = frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": "Sheet Cutting Layout",
			"comment_type": "Workflow",
		},
		fields=["reference_name", "content", "owner", "creation"],
		order_by="reference_name asc, creation asc",
	)
	next_idx_by_parent: dict[str, int] = {}
	seen_steps_by_parent: dict[str, set[str]] = {}

	for comment in comments:
		parent = str(comment.reference_name)
		action = _COMMENT_STATUS_ACTIONS.get(str(comment.content).strip())
		if not action:
			continue

		row = approval_snapshot_row(
			action=action,
			approver=comment.owner,
			decision_time=comment.creation,
		)
		if row is None:
			continue

		step_name = str(row["step_name"])
		seen_steps = seen_steps_by_parent.setdefault(parent, _existing_snapshot_steps(parent))
		if step_name in seen_steps:
			continue

		idx = next_idx_by_parent.setdefault(parent, _next_snapshot_idx(parent))
		frappe.get_doc(
			{
				"doctype": "Layout Approval Snapshot",
				"parent": parent,
				"parenttype": "Sheet Cutting Layout",
				"parentfield": "approval_snapshot",
				"idx": idx,
				**row,
			}
		).insert(ignore_permissions=True)
		seen_steps.add(step_name)
		next_idx_by_parent[parent] = idx + 1


def _existing_snapshot_steps(parent: str) -> set[str]:
	return set(
		frappe.get_all(
			"Layout Approval Snapshot",
			filters={
				"parent": parent,
				"parenttype": "Sheet Cutting Layout",
				"parentfield": "approval_snapshot",
			},
			pluck="step_name",
		)
	)


def _next_snapshot_idx(parent: str) -> int:
	rows = frappe.get_all(
		"Layout Approval Snapshot",
		filters={
			"parent": parent,
			"parenttype": "Sheet Cutting Layout",
			"parentfield": "approval_snapshot",
		},
		fields=["idx"],
		order_by="idx desc",
		limit=1,
	)
	if not rows:
		return 1
	return int(rows[0].idx or 0) + 1
