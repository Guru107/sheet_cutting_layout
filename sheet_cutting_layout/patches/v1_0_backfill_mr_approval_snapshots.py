from __future__ import annotations

from datetime import datetime
from typing import Any

try:
	import frappe
except ImportError:
	frappe = None

MR_APPROVAL_STEP = "MR Approval"


def execute() -> None:
	if not frappe:
		raise RuntimeError("Frappe is required to backfill MR approval snapshots")

	layouts = frappe.db.get_all(
		"Sheet Cutting Layout",
		filters={"status": ["in", ["Released", "Superseded"]]},
		fields=["name", "owner", "modified_by", "modified"],
	)
	for layout in layouts:
		layout_name = _get_value(layout, "name")
		if not isinstance(layout_name, str) or _has_mr_approval_snapshot(layout_name):
			continue

		frappe.get_doc(
			{
				"doctype": "Layout Approval Snapshot",
				"parent": layout_name,
				"parenttype": "Sheet Cutting Layout",
				"parentfield": "approval_snapshot",
				"idx": _next_snapshot_idx(layout_name),
				"step_name": MR_APPROVAL_STEP,
				"approver": _get_first_string(layout, "modified_by", "owner"),
				"decision": "Approved",
				"decision_time": _get_value(layout, "modified") or _now_datetime(),
			}
		).insert(ignore_permissions=True)


def _has_mr_approval_snapshot(layout_name: str) -> bool:
	return bool(
		frappe.db.exists(
			"Layout Approval Snapshot",
			{
				"parent": layout_name,
				"parenttype": "Sheet Cutting Layout",
				"step_name": MR_APPROVAL_STEP,
				"decision": "Approved",
			},
		)
	)


def _next_snapshot_idx(layout_name: str) -> int:
	return (
		frappe.db.count(
			"Layout Approval Snapshot",
			filters={"parent": layout_name, "parenttype": "Sheet Cutting Layout"},
		)
		+ 1
	)


def _get_first_string(row: object, *fieldnames: str) -> str | None:
	for fieldname in fieldnames:
		value = _get_value(row, fieldname)
		if isinstance(value, str) and value:
			return value
	return None


def _get_value(row: object, fieldname: str) -> Any:
	if isinstance(row, dict):
		return row.get(fieldname)
	return getattr(row, fieldname, None)


def _now_datetime() -> datetime:
	now_datetime = getattr(frappe, "now_datetime", None)
	if callable(now_datetime):
		return now_datetime()
	return datetime.now()
