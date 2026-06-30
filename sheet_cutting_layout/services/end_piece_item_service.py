from __future__ import annotations

from typing import Protocol

import frappe

from sheet_cutting_layout.services.alternative_item import set_allow_alternative_item_if_supported

_ = frappe._


class EndPieceRow(Protocol):
	idx: int
	end_piece_item_code: str | None
	width_mm: float | None
	length_mm: float | None
	weight_kg: float | None
	strip_weight_kg: float | None
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


def derive_end_piece_item_code_from_row(
	layout: LayoutDocument,
	row: EndPieceRow,
	*,
	source_finished_part: str | None = None,
) -> str:
	try:
		width_mm, length_mm = _end_piece_item_dimensions(row)
		item_code = derive_end_piece_item_code(
			used_for_finished_part=source_finished_part or getattr(row, "used_for_finished_part", None),
			thickness_mm=getattr(layout, "sheet_thickness_mm", None),
			width_mm=width_mm,
			length_mm=length_mm,
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


def layout_end_piece_source_finished_part(layout: object, fallback: object = None) -> str | None:
	primary = _clean(getattr(layout, "finished_part_code", None)) or _clean(fallback)
	twin = _clean(getattr(layout, "twin_finished_part", None))
	if getattr(layout, "is_lh_rh", None) and primary and twin:
		return f"{primary}-{twin}"
	return primary


def ensure_end_piece_item(
	layout: LayoutDocument,
	row: EndPieceRow,
	*,
	source_finished_part: str | None = None,
) -> str:
	item_code = derive_end_piece_item_code_from_row(
		layout,
		row,
		source_finished_part=source_finished_part,
	)
	if _item_exists(item_code):
		_repair_existing_item(
			item_code,
			layout,
			weight_kg=_end_piece_item_weight(row),
			row_idx=getattr(row, "idx", 0),
		)
		return item_code

	weight_kg = _end_piece_item_weight(row)
	if weight_kg is None or weight_kg <= 0:
		_throw(_("Row {0}: End piece weight must be greater than zero").format(getattr(row, "idx", 0)))

	item = frappe.new_doc("Item")
	item.item_code = item_code
	item.item_name = item_code
	item.description = _build_item_description(layout, row)
	item.item_group = _get_value("Item", getattr(layout, "raw_material_item", None), "item_group")
	item.valuation_rate = _raw_material_valuation_rate(layout)
	item.gst_hsn_code = _get_value(
		"Item", _clean(getattr(row, "used_for_finished_part", None)), "gst_hsn_code"
	)
	item.stock_uom = "Kg"
	item.is_stock_item = 1
	item.disabled = 0
	set_allow_alternative_item_if_supported(item)
	_append_app_created_item_uoms(item, stock_uom=item.stock_uom, weight_kg=weight_kg)
	try:
		# System-generated Item downstream of a write-permission-checked layout action.
		item.insert(ignore_permissions=True)
	except (frappe.ValidationError, frappe.DuplicateEntryError) as error:
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Row {getattr(row, 'idx', 0)}: Failed to create end piece item '{item_code}'",
		)
		_throw(
			_("Row {0}: Failed to create end piece item '{1}': {2}").format(
				getattr(row, "idx", 0),
				item_code,
				str(error),
			)
		)
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
		_upsert_uom_row(item, uom="Nos", conversion_factor=weight_kg)
		return
	if stock_uom == "Nos":
		_upsert_uom_row(item, uom="Kg", conversion_factor=1 / weight_kg)
		return
	_throw(_("Unsupported stock UOM for app-created Item: {0}").format(stock_uom))


def _repair_existing_item(
	item_code: str,
	layout: LayoutDocument,
	*,
	weight_kg: float | None,
	row_idx: int,
) -> None:
	needs_valuation = not _is_positive_number(_get_value("Item", item_code, "valuation_rate"))
	item = frappe.get_doc("Item", item_code)
	changed = False

	if needs_valuation:
		raw_material_valuation_rate = _raw_material_valuation_rate(layout)
		if _is_positive_number(raw_material_valuation_rate):
			item.valuation_rate = raw_material_valuation_rate
			changed = True

	if weight_kg is None or weight_kg <= 0:
		_throw(_("Row {0}: End piece weight must be greater than zero").format(row_idx))
	if _item_needs_required_uom_row(item, stock_uom="Kg", weight_kg=weight_kg):
		_append_app_created_item_uoms(item, stock_uom="Kg", weight_kg=weight_kg)
		changed = True

	if changed:
		item.save(ignore_permissions=True)


def _item_needs_required_uom_row(item: object, *, stock_uom: str, weight_kg: float) -> bool:
	required_uom = "Nos" if stock_uom == "Kg" else "Kg" if stock_uom == "Nos" else None
	if required_uom is None:
		return True
	required_factor = weight_kg if stock_uom == "Kg" else 1 / weight_kg
	for row in getattr(item, "uoms", []) or []:
		if _clean(getattr(row, "uom", None) if not isinstance(row, dict) else row.get("uom")) == required_uom:
			factor = (
				getattr(row, "conversion_factor", None)
				if not isinstance(row, dict)
				else row.get("conversion_factor")
			)
			return float(factor or 0) != float(required_factor)
	return True


def _upsert_uom_row(item: object, *, uom: str, conversion_factor: float) -> None:
	for row in getattr(item, "uoms", []) or []:
		row_uom = _clean(getattr(row, "uom", None) if not isinstance(row, dict) else row.get("uom"))
		if row_uom != uom:
			continue
		if isinstance(row, dict):
			row["conversion_factor"] = conversion_factor
		else:
			row.conversion_factor = conversion_factor
		return
	item.append("uoms", {"uom": uom, "conversion_factor": conversion_factor})


def _build_item_description(layout: LayoutDocument, row: EndPieceRow) -> str:
	raw_material_item = _clean(getattr(layout, "raw_material_item", None)) or "Unknown raw material"
	thickness_mm = format_code_number(getattr(layout, "sheet_thickness_mm", 0))
	width, length = _end_piece_item_dimensions(row)
	width_mm = format_code_number(width or 0)
	length_mm = format_code_number(length or 0)
	return f"Derived from {raw_material_item}; End Piece {thickness_mm}x{width_mm}x{length_mm} mm"


def _end_piece_item_dimensions(row: EndPieceRow) -> tuple[object, object]:
	if (_clean(getattr(row, "disposition", None)) or "").casefold() == "reuse":
		return (
			getattr(row, "strip_width_mm", None) or getattr(row, "width_mm", None),
			getattr(row, "strip_length_mm", None) or getattr(row, "length_mm", None),
		)
	return getattr(row, "width_mm", None), getattr(row, "length_mm", None)


def _end_piece_item_weight(row: EndPieceRow) -> object:
	if (_clean(getattr(row, "disposition", None)) or "").casefold() == "reuse":
		strip_weight = getattr(row, "strip_weight_kg", None)
		return strip_weight if strip_weight is not None else getattr(row, "weight_kg", None)
	return getattr(row, "weight_kg", None)


def _is_positive_number(value: object) -> bool:
	try:
		return float(value) > 0
	except (TypeError, ValueError):
		return False


def _raw_material_valuation_rate(layout: LayoutDocument) -> object:
	raw_material_item = _clean(getattr(layout, "raw_material_item", None))
	if raw_material_item is None:
		return None

	effective_rate = _effective_raw_material_valuation_rate(
		item_code=raw_material_item,
		company=_company_for_layout(layout),
	)
	if _is_positive_number(effective_rate):
		return effective_rate

	return _get_value("Item", raw_material_item, "valuation_rate")


def _effective_raw_material_valuation_rate(*, item_code: str, company: str | None) -> object:
	if company is None:
		return None

	from erpnext.manufacturing.doctype.bom.bom import get_valuation_rate

	try:
		return get_valuation_rate({"item_code": item_code, "company": company})
	except Exception:
		# Effective BOM valuation is best-effort; item master valuation remains the fallback.
		return None


def _company_for_layout(layout: LayoutDocument) -> str | None:
	company = _clean(getattr(layout, "company", None))
	if company:
		return company

	import erpnext

	return _clean(erpnext.get_default_company())


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
	if name is None or (isinstance(name, str) and not name.strip()):
		return None
	return frappe.get_cached_value(doctype, name, fieldname)


def _clean(value: object) -> str | None:
	if value is None:
		return None
	if isinstance(value, str):
		value = value.strip()
		return value or None
	return str(value)


def _throw(message: str) -> None:
	frappe.throw(message)
