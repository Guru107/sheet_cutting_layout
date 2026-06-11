from __future__ import annotations

try:
	import frappe
except ImportError:
	frappe = None


def execute() -> None:
	if not frappe:
		raise RuntimeError("Frappe is required to clear orphan end-piece item codes")

	rows = frappe.db.get_all(
		"Layout End Piece",
		filters={"end_piece_item_code": ["is", "set"]},
		fields=["name", "end_piece_item_code"],
	)
	for row in rows:
		item_code = _get_value(row, "end_piece_item_code")
		if item_code and frappe.db.exists("Item", item_code):
			continue
		frappe.db.set_value(
			"Layout End Piece",
			_get_value(row, "name"),
			"end_piece_item_code",
			None,
			update_modified=False,
		)


def _get_value(row: object, fieldname: str) -> object:
	if isinstance(row, dict):
		return row.get(fieldname)
	return getattr(row, fieldname, None)
