from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol

from sheet_cutting_layout.services import validators

try:
	import frappe
except ImportError:

	class _ValidationError(Exception):
		pass

	class _FrappeCompat:
		ValidationError = _ValidationError
		_ = staticmethod(lambda message: message)

		@staticmethod
		def throw(message: str) -> None:
			raise _ValidationError(message)

	frappe = _FrappeCompat()

_ = getattr(frappe, "_", lambda message: message)


ItemStatus = Literal["Exists", "Will be created"]
BomStatus = Literal["Already linked", "Will be created"]


class EndPieceRow(Protocol):
	idx: int
	disposition: str | None
	end_piece_item_code: str | None
	width_mm: float | None
	length_mm: float | None
	weight_kg: float | None
	used_for_finished_part: str | None
	bom_quantity: float | None
	bom_scrap_quantity_kg: float | None
	generated_end_piece_item: str | None
	generated_end_piece_bom: str | None


class LayoutDocument(Protocol):
	name: str
	status: str | None
	company: str | None
	raw_material_item: str | None
	sheet_thickness_mm: float | None
	process_scrap_item: str | None
	end_pieces: Sequence[EndPieceRow]


def preview_end_piece_boms(layout: LayoutDocument) -> list[dict[str, object]]:
	return [_preview_row(layout, row) for row in _reuse_end_pieces(layout)]


def generate_end_piece_boms(layout: LayoutDocument) -> dict[str, list[str]]:
	if getattr(layout, "status", None) != "Released":
		_throw(_("End-piece BOMs can be generated only after release"))

	generated_items: list[str] = []
	generated_boms: list[str] = []
	pending_rows = [
		row for row in _reuse_end_pieces(layout) if _is_missing(getattr(row, "generated_end_piece_bom", None))
	]

	for row in pending_rows:
		_validate_pending_row(layout, row)
		item_code = _ensure_end_piece_item(layout, row)
		bom_name = _create_end_piece_bom(layout, row, item_code)
		row.generated_end_piece_item = item_code
		row.generated_end_piece_bom = bom_name
		generated_items.append(item_code)
		generated_boms.append(bom_name)

	if generated_boms:
		_apply_end_piece_bom_status(layout)
		_persist_generated_links(layout, pending_rows)

	return {"items": generated_items, "boms": generated_boms}


def _preview_row(layout: LayoutDocument, row: EndPieceRow) -> dict[str, object]:
	item_code = _clean(getattr(row, "end_piece_item_code", None))
	return {
		"idx": getattr(row, "idx", 0),
		"end_piece_item_code": item_code,
		"suggested_item_code": validators.suggest_end_piece_item_code(
			raw_material_item=getattr(layout, "raw_material_item", None),
			thickness_mm=getattr(layout, "sheet_thickness_mm", None),
			width_mm=getattr(row, "width_mm", None),
			length_mm=getattr(row, "length_mm", None),
		),
		"item_status": "Exists" if item_code and _item_exists(item_code) else "Will be created",
		"used_for_finished_part": _clean(getattr(row, "used_for_finished_part", None)),
		"bom_quantity": getattr(row, "bom_quantity", None),
		"raw_material_qty_kg": getattr(row, "weight_kg", None),
		"bom_scrap_quantity_kg": getattr(row, "bom_scrap_quantity_kg", None),
		"bom_status": "Already linked"
		if not _is_missing(getattr(row, "generated_end_piece_bom", None))
		else "Will be created",
		"generated_end_piece_bom": _clean(getattr(row, "generated_end_piece_bom", None)),
	}


def _ensure_end_piece_item(layout: LayoutDocument, row: EndPieceRow) -> str:
	item_code = _required_clean(row, "end_piece_item_code")
	if _item_exists(item_code):
		return item_code

	item = frappe.new_doc("Item")
	item.item_code = item_code
	item.item_name = item_code
	item.item_group = _get_value("Item", getattr(layout, "raw_material_item", None), "item_group")
	item.stock_uom = "Kg"
	item.is_stock_item = 1
	item.disabled = 0
	item.insert(ignore_permissions=True)
	return item_code


def _create_end_piece_bom(layout: LayoutDocument, row: EndPieceRow, item_code: str) -> str:
	bom = frappe.new_doc("BOM")
	bom.item = _required_clean(row, "used_for_finished_part")
	bom.company = _company_for_layout(layout)
	bom.quantity = getattr(row, "bom_quantity", None)
	bom.uom = "Kg"
	bom.custom_operation = "Shearing"
	bom.sheet_cutting_layout = getattr(layout, "name", None)
	bom.append("items", {"item_code": item_code, "qty": getattr(row, "weight_kg", None), "uom": "Kg"})

	scrap_qty = getattr(row, "bom_scrap_quantity_kg", None) or 0
	if scrap_qty > 0:
		bom.append(
			"scrap_items",
			{
				"item_code": _clean(getattr(layout, "process_scrap_item", None)),
				"qty": scrap_qty,
				"stock_qty": scrap_qty,
				"uom": "Kg",
			},
		)

	bom.insert(ignore_permissions=True)
	return bom.name


def _validate_pending_row(layout: LayoutDocument, row: EndPieceRow) -> None:
	prefix = f"Row {getattr(row, 'idx', 0)}: "
	if _is_missing(getattr(row, "end_piece_item_code", None)):
		_throw(_(prefix + "End piece item code is required"))
	if _is_missing(getattr(row, "used_for_finished_part", None)):
		_throw(_(prefix + "Used for finished part is required"))
	if getattr(row, "bom_quantity", None) is None or row.bom_quantity <= 0:
		_throw(_(prefix + "BOM quantity must be greater than zero"))
	if getattr(row, "bom_scrap_quantity_kg", None) is None or row.bom_scrap_quantity_kg < 0:
		_throw(_(prefix + "BOM scrap quantity must be non-negative"))
	if getattr(row, "weight_kg", None) is None or row.weight_kg <= 0:
		_throw(_(prefix + "End piece weight must be greater than zero"))
	if row.bom_scrap_quantity_kg > 0 and _is_missing(getattr(layout, "process_scrap_item", None)):
		_throw(_(prefix + "Process scrap item is required when BOM scrap quantity is positive"))


def _reuse_end_pieces(layout: LayoutDocument) -> list[EndPieceRow]:
	return [row for row in getattr(layout, "end_pieces", []) or [] if _is_reuse(row)]


def _is_reuse(row: EndPieceRow) -> bool:
	return str(getattr(row, "disposition", "") or "").strip().lower() == "reuse"


def _item_exists(item_code: str) -> bool:
	db = getattr(frappe, "db", None)
	exists = getattr(db, "exists", None)
	if callable(exists):
		return bool(exists("Item", item_code))
	db_exists = getattr(frappe, "db_exists", None)
	if callable(db_exists):
		return bool(db_exists("Item", item_code))
	return False


def _get_value(doctype: str, name: str | None, fieldname: str) -> object:
	db = getattr(frappe, "db", None)
	get_value = getattr(db, "get_value", None)
	if callable(get_value):
		return get_value(doctype, name, fieldname)
	get_value = getattr(frappe, "get_value", None)
	if callable(get_value):
		return get_value(doctype, name, fieldname)
	return None


def _apply_end_piece_bom_status(layout: LayoutDocument) -> None:
	try:
		validators.apply_end_piece_bom_status(layout)
	except TypeError:
		validators.apply_end_piece_bom_status(layout, getattr(layout, "end_pieces", []) or [])


def _persist_generated_links(layout: LayoutDocument, rows: Sequence[EndPieceRow]) -> None:
	if _is_submitted_document(layout):
		for row in rows:
			_set_generated_row_links(row)
		_db_set(layout, "end_piece_bom_status", getattr(layout, "end_piece_bom_status", None), update_modified=True)
		return

	save = getattr(layout, "save", None)
	if callable(save):
		save(ignore_permissions=True)


def _set_generated_row_links(row: EndPieceRow) -> None:
	_db_set(
		row,
		{
			"generated_end_piece_item": getattr(row, "generated_end_piece_item", None),
			"generated_end_piece_bom": getattr(row, "generated_end_piece_bom", None),
		},
		update_modified=False,
	)


def _db_set(
	doc: object,
	fieldname: object,
	value: object = None,
	*,
	update_modified: bool,
) -> None:
	db_set = getattr(doc, "db_set", None)
	if callable(db_set):
		db_set(fieldname, value, update_modified=update_modified, notify=False)
		return

	db = getattr(frappe, "db", None)
	set_value = getattr(db, "set_value", None)
	doctype = getattr(doc, "doctype", None)
	name = getattr(doc, "name", None)
	if callable(set_value) and doctype and name:
		set_value(doctype, name, fieldname, value, update_modified=update_modified)
		return

	_throw(_("Generated end-piece BOM links could not be persisted safely on a submitted layout"))


def _is_submitted_document(doc: object) -> bool:
	docstatus = getattr(doc, "docstatus", None)
	if docstatus == 1:
		return True
	is_submitted = getattr(docstatus, "is_submitted", None)
	return bool(callable(is_submitted) and is_submitted())


def _company_for_layout(layout: LayoutDocument | None) -> str:
	if layout is not None:
		company = _clean(getattr(layout, "company", None))
		if company:
			return company

	defaults = getattr(frappe, "defaults", None)
	get_user_default = getattr(defaults, "get_user_default", None)
	if callable(get_user_default):
		company = _clean(get_user_default("Company"))
		if company:
			return company

	db = getattr(frappe, "db", None)
	get_default = getattr(db, "get_default", None)
	if callable(get_default):
		company = _clean(get_default("company"))
		if company:
			return company

	_throw(_("Company is required to create generated BOMs"))
	raise RuntimeError("Company is required to create generated BOMs")


def _required_clean(row: EndPieceRow, fieldname: str) -> str:
	value = _clean(getattr(row, fieldname, None))
	if value is None:
		_throw(_(f"Row {getattr(row, 'idx', 0)}: {fieldname} is required"))
	return value


def _is_missing(value: object) -> bool:
	return value is None or (isinstance(value, str) and value.strip() == "")


def _clean(value: object) -> str | None:
	if value is None:
		return None
	if isinstance(value, str):
		value = value.strip()
		return value or None
	return str(value)


def _throw(message: str) -> None:
	frappe.throw(message)
