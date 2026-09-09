from __future__ import annotations

import frappe

_ = frappe._


def validate_generated_shearing_bom_lifecycle(doc: object, method: str | None = None) -> None:
	if getattr(doc, "custom_operation", None) != "Shearing":
		return

	if method == "before_insert":
		amended_from = str(getattr(doc, "amended_from", "") or "").strip()
		if not amended_from:
			return
		if frappe.db.get_value("BOM", amended_from, "sheet_cutting_layout"):
			frappe.throw(
				_(
					"This Shearing BOM amends a BOM generated from a Sheet Cutting Layout. "
					"Use the Sheet Cutting Layout workflow instead of amending this BOM."
				)
			)
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
