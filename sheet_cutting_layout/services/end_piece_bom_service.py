from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import frappe

from sheet_cutting_layout.overrides.bom import APP_CONTROLLED_BOM_UPDATE_FLAG
from sheet_cutting_layout.services import validators
from sheet_cutting_layout.services.bom_service import resolve_scrap_item_rate

_ = frappe._


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


class LayoutDocument(Protocol):
	name: str
	status: str | None
	company: str | None
	raw_material_item: str | None
	sheet_thickness_mm: float | None
	process_scrap_item: str | None
	end_pieces: Sequence[EndPieceRow]
	end_piece_bom_status: str | None


def generate_end_piece_boms(layout: LayoutDocument) -> dict[str, list[str]]:
	if getattr(layout, "status", None) != "Released":
		_throw(_("End-piece BOMs can be generated only after release"))

	generated_items: list[str] = []
	generated_boms: list[str] = []
	reuse_rows = _reuse_end_pieces(layout)
	pending_rows = [row for row in reuse_rows if _is_missing(getattr(row, "end_piece_item_code", None))]

	for row in pending_rows:
		_validate_pending_row(layout, row)
		item_code = _ensure_end_piece_item(layout, row)
		bom_name = _create_end_piece_bom(layout, row, item_code)
		row.end_piece_item_code = item_code
		generated_items.append(item_code)
		generated_boms.append(bom_name)

	if generated_items:
		_apply_end_piece_bom_status(layout)
		_persist_generated_links(layout, pending_rows)

	return {"items": generated_items, "boms": generated_boms}


def _ensure_end_piece_item(layout: LayoutDocument, row: EndPieceRow) -> str:
	item_code = _derived_item_code(layout, row)
	if _item_exists(item_code):
		return item_code

	weight_kg = getattr(row, "weight_kg", None)
	if weight_kg is None or weight_kg <= 0:
		_throw(_("Row {0}: End piece weight must be greater than zero").format(getattr(row, "idx", 0)))

	item = frappe.new_doc("Item")
	item.item_code = item_code
	item.item_name = item_code
	item.description = _build_item_description(layout, row)
	item.item_group = _get_value("Item", getattr(layout, "raw_material_item", None), "item_group")
	item.stock_uom = "Nos"
	item.is_stock_item = 1
	item.disabled = 0
	item.append("uoms", {"uom": "Nos", "conversion_factor": 1})
	item.append("uoms", {"uom": "Kg", "conversion_factor": 1 / weight_kg})
	insert_error_types = _item_insert_exception_types()
	if insert_error_types:
		try:
			item.insert(ignore_permissions=True)
		except insert_error_types as error:
			_log_item_insert_error(item_code=item_code, row=row, error=error)
			error_message = str(error)
			_throw(
				_("Row {0}: Failed to create end piece item '{1}': {2}").format(
					getattr(row, "idx", 0),
					item_code,
					error_message,
				)
			)
	else:
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
		scrap_item = _clean(getattr(layout, "process_scrap_item", None))
		if scrap_item is None:
			_throw(_("Row {0}: Process scrap item is required").format(getattr(row, "idx", 0)))
		try:
			rate = resolve_scrap_item_rate(item_code=scrap_item, company=bom.company)
		except ValueError as error:
			_throw(_("Row {0}: {1}").format(getattr(row, "idx", 0), str(error)))
		bom.append(
			"scrap_items",
			{
				"item_code": scrap_item,
				"qty": scrap_qty,
				"stock_qty": scrap_qty,
				"uom": "Kg",
				"rate": rate,
			},
		)

	flags = getattr(bom, "flags", None)
	if flags is None:
		flags = type("Flags", (), {})()
		bom.flags = flags
	setattr(flags, APP_CONTROLLED_BOM_UPDATE_FLAG, True)
	bom.insert(ignore_permissions=True)
	return bom.name


def _validate_pending_row(layout: LayoutDocument, row: EndPieceRow) -> None:
	row_idx = getattr(row, "idx", 0)
	if _is_missing(getattr(row, "used_for_finished_part", None)):
		_throw(_("Row {0}: Used for finished part is required").format(row_idx))
	if getattr(row, "bom_quantity", None) is None or row.bom_quantity <= 0:
		_throw(_("Row {0}: BOM quantity must be greater than zero").format(row_idx))
	if getattr(row, "bom_scrap_quantity_kg", None) is None or row.bom_scrap_quantity_kg < 0:
		_throw(_("Row {0}: BOM scrap quantity must be non-negative").format(row_idx))
	if getattr(row, "weight_kg", None) is None or row.weight_kg <= 0:
		_throw(_("Row {0}: End piece weight must be greater than zero").format(row_idx))
	if row.bom_scrap_quantity_kg > 0 and _is_missing(getattr(layout, "process_scrap_item", None)):
		_throw(
			_("Row {0}: Process scrap item is required when BOM scrap quantity is positive").format(row_idx)
		)


def _reuse_end_pieces(layout: LayoutDocument) -> list[EndPieceRow]:
	return [row for row in getattr(layout, "end_pieces", []) or [] if _is_reuse(row)]


def _is_reuse(row: EndPieceRow) -> bool:
	return str(getattr(row, "disposition", "") or "").strip().lower() == "reuse"


def _derived_item_code(layout: LayoutDocument, row: EndPieceRow) -> str:
	try:
		item_code = validators.derive_end_piece_item_code(
			used_for_finished_part=getattr(row, "used_for_finished_part", None),
			thickness_mm=getattr(layout, "sheet_thickness_mm", None),
			width_mm=getattr(row, "width_mm", None),
			length_mm=getattr(row, "length_mm", None),
		)
	except ValueError as error:
		_throw(_("Row {0}: {1}").format(getattr(row, "idx", 0), str(error)))

	max_item_code_length = 140
	if len(item_code) > max_item_code_length:
		_throw(
			_("Row {0}: Generated end piece item code for '{1}' exceeds {2} characters").format(
				getattr(row, "idx", 0),
				_clean(getattr(row, "used_for_finished_part", None)),
				max_item_code_length,
			)
		)
	return item_code


def _build_item_description(layout: LayoutDocument, row: EndPieceRow) -> str:
	raw_material_item = _clean(getattr(layout, "raw_material_item", None)) or "Unknown raw material"
	thickness_mm = validators.format_code_number(getattr(layout, "sheet_thickness_mm", 0))
	width_mm = validators.format_code_number(getattr(row, "width_mm", 0))
	length_mm = validators.format_code_number(getattr(row, "length_mm", 0))
	return f"Derived from {raw_material_item}; End Piece {thickness_mm}x{width_mm}x{length_mm} mm"


def _item_insert_exception_types() -> tuple[type[Exception], ...]:
	exception_types: list[type[Exception]] = []
	for attr in ("ValidationError", "DuplicateEntryError"):
		error_type = getattr(frappe, attr, None)
		if isinstance(error_type, type) and issubclass(error_type, Exception):
			exception_types.append(error_type)
	return tuple(dict.fromkeys(exception_types))


def _log_item_insert_error(*, item_code: str, row: EndPieceRow, error: Exception) -> None:
	log_error = getattr(frappe, "log_error", None)
	if not callable(log_error):
		return
	get_traceback = getattr(frappe, "get_traceback", None)
	traceback = get_traceback() if callable(get_traceback) else str(error)
	log_error(
		message=traceback,
		title=f"Row {getattr(row, 'idx', 0)}: Failed to create end piece item '{item_code}'",
	)


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
	validators.apply_end_piece_bom_status(layout, getattr(layout, "end_pieces", []) or [])


def _persist_generated_links(layout: LayoutDocument, rows: Sequence[EndPieceRow]) -> None:
	if _is_submitted_document(layout):
		for row in rows:
			_db_set(
				row,
				"end_piece_item_code",
				getattr(row, "end_piece_item_code", None),
				update_modified=False,
			)
		_db_set(
			layout,
			"end_piece_bom_status",
			getattr(layout, "end_piece_bom_status", None),
			update_modified=True,
		)
		return

	save = getattr(layout, "save", None)
	if callable(save):
		save(ignore_permissions=True)


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

	_throw(_("Generated end-piece item links could not be persisted safely on a submitted layout"))


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
		_throw(_("Row {0}: {1} is required").format(getattr(row, "idx", 0), fieldname))
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
