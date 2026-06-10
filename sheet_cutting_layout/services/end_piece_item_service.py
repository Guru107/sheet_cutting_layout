from __future__ import annotations

from typing import Protocol

import frappe

_ = frappe._


class EndPieceRow(Protocol):
	idx: int
	end_piece_item_code: str | None
	width_mm: float | None
	length_mm: float | None
	weight_kg: float | None
	used_for_finished_part: str | None


class LayoutDocument(Protocol):
	raw_material_item: str | None
	sheet_thickness_mm: float | None


def format_code_number(value: float | int | str) -> str:
	return f"{float(value):.6f}".rstrip("0").rstrip(".")


def derive_end_piece_item_code(
	*,
	used_for_finished_part: str | None,
	thickness_mm: float | int | str | None,
	width_mm: float | int | str | None,
	length_mm: float | int | str | None,
) -> str:
	finished_part = _clean(used_for_finished_part)
	if finished_part is None:
		raise ValueError("Used for finished part is required")
	finished_part = finished_part.upper()

	thickness = _coerce_positive_number(
		value=thickness_mm,
		field_label="Sheet thickness",
		message="Sheet thickness is required to derive end piece item code",
	)
	width = _coerce_positive_number(
		value=width_mm,
		field_label="End piece width",
		message="End piece width must be greater than zero",
	)
	length = _coerce_positive_number(
		value=length_mm,
		field_label="End piece length",
		message="End piece length must be greater than zero",
	)
	return (
		f"{finished_part}-EP-"
		f"{format_code_number(thickness)}x"
		f"{format_code_number(width)}x"
		f"{format_code_number(length)}"
	)


def derive_end_piece_item_code_from_row(layout: LayoutDocument, row: EndPieceRow) -> str:
	try:
		item_code = derive_end_piece_item_code(
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


def ensure_end_piece_item(layout: LayoutDocument, row: EndPieceRow) -> str:
	item_code = derive_end_piece_item_code_from_row(layout, row)
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
	item.valuation_rate = _get_value("Item", getattr(layout, "raw_material_item", None), "valuation_rate")
	item.gst_hsn_code = _get_value(
		"Item", _clean(getattr(row, "used_for_finished_part", None)), "gst_hsn_code"
	)
	item.stock_uom = "Kg"
	item.is_stock_item = 1
	item.disabled = 0
	_append_app_created_item_uoms(item, stock_uom=item.stock_uom, weight_kg=weight_kg)
	insert_error_types = _item_insert_exception_types()
	if insert_error_types:
		try:
			item.insert(ignore_permissions=True)
		except insert_error_types as error:
			_log_item_insert_error(item_code=item_code, row=row, error=error)
			_throw(
				_("Row {0}: Failed to create end piece item '{1}': {2}").format(
					getattr(row, "idx", 0),
					item_code,
					str(error),
				)
			)
	else:
		item.insert(ignore_permissions=True)
	return item_code


def _coerce_positive_number(
	*,
	value: float | int | str | None,
	field_label: str,
	message: str,
) -> float:
	try:
		number = float(value)
	except (TypeError, ValueError):
		raise ValueError(f"{field_label} must be a number") from None
	if number <= 0:
		raise ValueError(message)
	return number


def _append_app_created_item_uoms(item: object, *, stock_uom: str, weight_kg: float) -> None:
	if stock_uom == "Kg":
		item.append("uoms", {"uom": "Kg", "conversion_factor": 1})
		item.append("uoms", {"uom": "Nos", "conversion_factor": weight_kg})
		return
	if stock_uom == "Nos":
		item.append("uoms", {"uom": "Nos", "conversion_factor": 1})
		item.append("uoms", {"uom": "Kg", "conversion_factor": 1 / weight_kg})
		return
	_throw(_("Unsupported stock UOM for app-created Item: {0}").format(stock_uom))


def _build_item_description(layout: LayoutDocument, row: EndPieceRow) -> str:
	raw_material_item = _clean(getattr(layout, "raw_material_item", None)) or "Unknown raw material"
	thickness_mm = format_code_number(getattr(layout, "sheet_thickness_mm", 0))
	width_mm = format_code_number(getattr(row, "width_mm", 0))
	length_mm = format_code_number(getattr(row, "length_mm", 0))
	return f"Derived from {raw_material_item}; End Piece {thickness_mm}x{width_mm}x{length_mm} mm"


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


def _clean(value: object) -> str | None:
	if value is None:
		return None
	if isinstance(value, str):
		value = value.strip()
		return value or None
	return str(value)


def _throw(message: str) -> None:
	frappe.throw(message)
