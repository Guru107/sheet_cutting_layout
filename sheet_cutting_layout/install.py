from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

BOM_CUSTOM_FIELDS = [
	{
		"fieldname": "custom_operation",
		"fieldtype": "Data",
		"insert_after": "image",
		"label": "Custom Operation",
	},
	{
		"fieldname": "sheet_cutting_layout",
		"fieldtype": "Link",
		"insert_after": "custom_operation",
		"label": "Sheet Cutting Layout",
		"no_copy": 1,
		"options": "Sheet Cutting Layout",
		"read_only": 1,
	},
]


def create_missing_bom_custom_fields() -> None:
	meta = frappe.get_meta("BOM", cached=False)
	missing_fields = [field for field in BOM_CUSTOM_FIELDS if not meta.has_field(field["fieldname"])]
	if missing_fields:
		create_custom_fields({"BOM": missing_fields}, update=False)
