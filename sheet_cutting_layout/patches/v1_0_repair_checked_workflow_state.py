from __future__ import annotations

try:
	import frappe
except ImportError:
	frappe = None


def execute() -> None:
	if not frappe:
		raise RuntimeError("Frappe is required to repair Sheet Cutting Layout workflow state")

	frappe.db.set_value(
		"Sheet Cutting Layout",
		{
			"status": "Submitted for Check",
			"project_manager_ok": 1,
			"manufacturing_manager_ok": 1,
		},
		"status",
		"Checked",
		update_modified=False,
	)
