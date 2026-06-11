from __future__ import annotations

try:
	import frappe
except ImportError:
	frappe = None


DOCTYPE = "Sheet Cutting Layout"
PM_APPROVED = "PM Approved"
LEGACY_FLAG_FIELDS = ("project_manager_ok", "manufacturing_manager_ok")


def execute() -> None:
	if not frappe:
		raise RuntimeError("Frappe is required to migrate Sheet Cutting Layout workflow state")

	frappe.db.set_value(
		DOCTYPE,
		{"status": "Checked"},
		"status",
		PM_APPROVED,
		update_modified=False,
	)

	if not all(_has_column(fieldname) for fieldname in LEGACY_FLAG_FIELDS):
		return

	frappe.db.set_value(
		DOCTYPE,
		{
			"status": "Submitted for Check",
			"project_manager_ok": 1,
			"manufacturing_manager_ok": 1,
		},
		"status",
		PM_APPROVED,
		update_modified=False,
	)


def _has_column(fieldname: str) -> bool:
	db = frappe.db
	has_column = getattr(db, "has_column", None)
	if callable(has_column):
		return bool(has_column(DOCTYPE, fieldname))

	get_table_columns = getattr(db, "get_table_columns", None)
	if callable(get_table_columns):
		return fieldname in get_table_columns(DOCTYPE)

	return False
