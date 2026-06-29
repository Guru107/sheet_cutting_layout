from __future__ import annotations

import frappe

_ = frappe._


def validate_shearing_bom_source(doc: object, method: str | None = None) -> None:
	if getattr(doc, "custom_operation", None) != "Shearing":
		return
	layout_name = str(getattr(doc, "sheet_cutting_layout", "") or "").strip()
	if layout_name and method == "before_cancel":
		if frappe.db.get_value("Sheet Cutting Layout", layout_name, "workflow_status") == "Superseded":
			return
		frappe.throw(
			_(
				"This Shearing BOM is generated from a Sheet Cutting Layout. "
				"Use the Sheet Cutting Layout workflow instead of cancelling or amending this BOM."
			)
		)
	if method == "before_insert":
		if layout_name:
			return
		frappe.throw(_("Create a Sheet Cutting Layout to generate a Shearing BOM."))
