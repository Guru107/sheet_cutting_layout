from __future__ import annotations

try:
	import frappe
except ImportError:
	frappe = None


def execute() -> None:
	if not frappe:
		raise RuntimeError("Frappe is required to normalize cancelled Sheet Cutting Layouts")

	cancelled_layouts = frappe.db.get_all(
		"Sheet Cutting Layout",
		filters={"docstatus": 2},
		fields=["name", "generated_bom"],
	)
	for layout in cancelled_layouts:
		layout_name = _get_value(layout, "name")
		if not layout_name:
			continue

		generated_bom = _get_value(layout, "generated_bom")
		frappe.db.set_value(
			"Sheet Cutting Layout",
			layout_name,
			{"status": "Cancel", "generated_bom": None},
			update_modified=False,
		)
		if generated_bom and frappe.db.exists("BOM", generated_bom):
			frappe.db.set_value(
				"BOM",
				generated_bom,
				"sheet_cutting_layout",
				None,
				update_modified=False,
			)

	cancelled_bom_names = frappe.db.get_all(
		"BOM",
		filters={"docstatus": 2, "sheet_cutting_layout": ["is", "set"]},
		pluck="name",
	)
	for bom_name in cancelled_bom_names:
		frappe.db.set_value(
			"BOM",
			bom_name,
			"sheet_cutting_layout",
			None,
			update_modified=False,
		)


def _get_value(row: object, fieldname: str) -> object:
	if isinstance(row, dict):
		return row.get(fieldname)
	return getattr(row, fieldname, None)
