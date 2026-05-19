from __future__ import annotations

try:
	import frappe
except ImportError:
	frappe = None


def execute() -> None:
	if frappe is None:
		raise RuntimeError("Frappe is required to submit released Sheet Cutting Layouts")

	frappe.db.set_value(
		"Sheet Cutting Layout",
		{"status": "Released", "docstatus": 0},
		"docstatus",
		1,
		update_modified=False,
	)
