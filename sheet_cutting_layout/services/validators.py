from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol

import frappe

from sheet_cutting_layout.services import geometry
from sheet_cutting_layout.services.bom_service import (
	BomItemRow,
	build_bom_from_layout,
)
from sheet_cutting_layout.services.end_piece_item_service import (
	derive_end_piece_item_code,
	format_code_number,
)

_ = frappe._


class EndPieceRow(Protocol):
	end_piece_item_code: str | None
	width_mm: float | None
	length_mm: float | None
	weight_kg: float | None
	disposition: str | None
	used_for_finished_part: str | None
	bom_quantity: float | None
	net_weight_per_part_kg: float | None
	gross_weight_per_part_kg: float | None
	scrap_weight_per_part_kg: float | None
	bom_scrap_quantity_kg: float | None
	scrap_item: str | None


class SheetCuttingLayoutDocument(Protocol):
	finished_part_code: str | None
	net_weight_per_part_kg: float | None
	generated_bom: str | None
	end_pieces: Sequence[EndPieceRow]
	raw_material_item: str | None
	process_scrap_item: str | None
	end_piece_bom_status: str | None
	sheet_thickness_mm: float | None
	sheet_width_mm: float | None
	sheet_length_mm: float | None
	weight_per_sheet_kg: float | None
	strip_thickness_mm: float | None
	strip_width_mm: float | None
	strip_length_mm: float | None
	weight_of_strip_kg: float | None
	gross_weight_per_part_kg: float | None
	scrap_weight_per_part_kg: float | None
	parts_per_strip: int | None
	no_of_strips: int | None
	parts_per_sheet: int | None
	consumed_weight_kg: float | None
	leftover_weight_kg: float | None
	consumption_status: str | None


ALNUM_RE = re.compile(r"^[A-Za-z0-9]+$")
DEFAULT_FLOAT_PRECISION = 6
SHEET_CONSUMPTION_PRECISION = 3
SHEET_CONSUMPTION_TOLERANCE_KG = 0.005


def validate_finished_part_code(code: str) -> None:
	if not ALNUM_RE.fullmatch(code):
		frappe.throw(_("Finished part item code must be alphanumeric only"))
	if not code.endswith("SHR"):
		frappe.throw(_("Finished part item code must end with SHR"))


def validate_sheet_cutting_layout(layout: SheetCuttingLayoutDocument) -> None:
	apply_sheet_weight_formula(layout)
	apply_strip_weight_formula(layout)
	apply_parent_gross_weight_per_part_formula(layout)
	apply_parent_scrap_weight_per_part_formula(layout)
	end_pieces = list(getattr(layout, "end_pieces", []) or [])
	apply_parts_per_sheet_formula(layout)
	apply_end_piece_weight_formulas(layout, end_pieces)
	apply_end_piece_reuse_weight_formulas(end_pieces)
	_validate_parent_finished_part_fields(layout)

	for end_piece in end_pieces:
		_validate_end_piece_item_code_is_locked(end_piece)
		_validate_end_piece_required_fields(layout, end_piece)

	if end_pieces:
		_validate_end_piece_distribution(layout, end_pieces)
	apply_consumption_tracking(
		layout,
		end_pieces,
	)
	apply_end_piece_bom_status(layout, end_pieces)
	_validate_complete_sheet_consumption(layout, end_pieces)
	_validate_generated_bom_matches_layout(layout)


def apply_sheet_weight_formula(layout: SheetCuttingLayoutDocument) -> None:
	weight = calculate_sheet_weight_kg(
		thickness_mm=getattr(layout, "sheet_thickness_mm", None),
		width_mm=getattr(layout, "sheet_width_mm", None),
		length_mm=getattr(layout, "sheet_length_mm", None),
	)
	if weight is not None:
		layout.weight_per_sheet_kg = weight


def apply_strip_weight_formula(layout: SheetCuttingLayoutDocument) -> None:
	weight = calculate_sheet_weight_kg(
		thickness_mm=getattr(layout, "strip_thickness_mm", None),
		width_mm=getattr(layout, "strip_width_mm", None),
		length_mm=getattr(layout, "strip_length_mm", None),
	)
	if weight is not None:
		layout.weight_of_strip_kg = weight


def apply_parent_gross_weight_per_part_formula(layout: SheetCuttingLayoutDocument) -> None:
	gross_weight = calculate_parent_gross_weight_per_part_kg(
		weight_of_strip_kg=getattr(layout, "weight_of_strip_kg", None),
		parts_per_strip=getattr(layout, "parts_per_strip", None),
	)
	if gross_weight is not None:
		layout.gross_weight_per_part_kg = gross_weight


def apply_parent_scrap_weight_per_part_formula(layout: SheetCuttingLayoutDocument) -> None:
	gross_weight = getattr(layout, "gross_weight_per_part_kg", None)
	net_weight = getattr(layout, "net_weight_per_part_kg", None)
	if gross_weight is None or net_weight is None:
		return
	layout.scrap_weight_per_part_kg = _flt(gross_weight - _flt(net_weight))


def apply_parts_per_sheet_formula(layout: SheetCuttingLayoutDocument) -> None:
	parts_per_sheet = calculate_parts_per_sheet(
		parts_per_strip=getattr(layout, "parts_per_strip", None),
		no_of_strips=getattr(layout, "no_of_strips", None),
	)
	if parts_per_sheet is None:
		return

	layout.parts_per_sheet = parts_per_sheet


def calculate_parts_per_sheet(
	*,
	parts_per_strip: int | None,
	no_of_strips: int | None,
) -> int | None:
	return geometry.parts_per_sheet(parts_per_strip=parts_per_strip, no_of_strips=no_of_strips)


def calculate_parent_gross_weight_per_part_kg(
	*,
	weight_of_strip_kg: float | None,
	parts_per_strip: int | None,
) -> float | None:
	return geometry.gross_weight_per_part_kg(
		weight_of_strip_kg=weight_of_strip_kg,
		parts_per_strip=parts_per_strip,
		precision=_calculation_precision(),
	)


def apply_end_piece_weight_formulas(
	layout: SheetCuttingLayoutDocument,
	end_pieces: Sequence[EndPieceRow],
) -> None:
	for end_piece in end_pieces:
		weight = calculate_sheet_weight_kg(
			thickness_mm=getattr(layout, "sheet_thickness_mm", None),
			width_mm=getattr(end_piece, "width_mm", None),
			length_mm=getattr(end_piece, "length_mm", None),
		)
		if weight is not None:
			end_piece.weight_kg = _flt(weight)


def apply_end_piece_reuse_weight_formulas(end_pieces: Sequence[EndPieceRow]) -> None:
	for end_piece in end_pieces:
		if not _is_reuse_end_piece(end_piece):
			continue
		weight = getattr(end_piece, "weight_kg", None)
		bom_quantity = getattr(end_piece, "bom_quantity", None)
		net_weight = getattr(end_piece, "net_weight_per_part_kg", None)
		if weight is None or bom_quantity is None or bom_quantity <= 0:
			continue
		gross_weight = _flt(_flt(weight) / _flt(bom_quantity))
		end_piece.gross_weight_per_part_kg = gross_weight
		if net_weight is None:
			continue
		scrap_weight = _flt(gross_weight - _flt(net_weight))
		end_piece.scrap_weight_per_part_kg = scrap_weight
		end_piece.bom_scrap_quantity_kg = _flt(scrap_weight * _flt(bom_quantity))


def calculate_sheet_weight_kg(
	*,
	thickness_mm: float | None,
	width_mm: float | None,
	length_mm: float | None,
) -> float | None:
	return geometry.sheet_weight_kg(
		thickness_mm=thickness_mm,
		width_mm=width_mm,
		length_mm=length_mm,
		precision=_calculation_precision(),
		density_precision=_float_precision(),
	)


def apply_consumption_tracking(
	layout: SheetCuttingLayoutDocument,
	end_pieces: Sequence[EndPieceRow],
) -> None:
	sheet_weight = getattr(layout, "weight_per_sheet_kg", None)
	if sheet_weight is None:
		return

	consumed_weight = calculate_consumed_weight_kg(layout, end_pieces)
	leftover_weight = _sheet_consumption_flt(_sheet_consumption_flt(sheet_weight) - consumed_weight)

	layout.consumed_weight_kg = consumed_weight
	layout.leftover_weight_kg = leftover_weight
	layout.consumption_status = _consumption_status(leftover_weight)


def calculate_consumed_weight_kg(
	layout: SheetCuttingLayoutDocument,
	end_pieces: Sequence[EndPieceRow],
) -> float:
	part_gross_weight = 0.0
	if not _is_missing(getattr(layout, "finished_part_code", None)):
		part_gross_weight = _flt(getattr(layout, "gross_weight_per_part_kg", 0)) * int(
			getattr(layout, "parts_per_sheet", 0) or 0
		)
	end_piece_weight = sum(end_piece.weight_kg for end_piece in end_pieces if end_piece.weight_kg is not None)
	return _sheet_consumption_flt(part_gross_weight + end_piece_weight)


def _validate_parent_finished_part_fields(layout: SheetCuttingLayoutDocument) -> None:
	finished_part_code = getattr(layout, "finished_part_code", None)
	if _is_missing(finished_part_code):
		frappe.throw(_("Finished part code is required"))
	validate_finished_part_code(str(finished_part_code))

	net_weight = getattr(layout, "net_weight_per_part_kg", None)
	if net_weight is None:
		frappe.throw(_("Net weight per part is required"))
	if net_weight < 0:
		frappe.throw(_("Net weight per part must be non-negative"))

	gross_weight = _flt(getattr(layout, "gross_weight_per_part_kg", 0))
	if gross_weight < 0:
		frappe.throw(_("Gross weight per part must be non-negative"))
	scrap_weight = _flt(getattr(layout, "scrap_weight_per_part_kg", 0))
	if scrap_weight < 0:
		frappe.throw(_("Scrap weight per part cannot be negative"))
	if scrap_weight > 0:
		process_scrap_item = getattr(layout, "process_scrap_item", None)
		if _is_missing(process_scrap_item):
			frappe.throw(_("Process scrap item is required when process scrap weight is positive"))
		if _same_item_code(process_scrap_item, finished_part_code):
			frappe.throw(_("Process scrap item cannot be the finished part item"))


def _validate_end_piece_required_fields(
	layout: SheetCuttingLayoutDocument,
	end_piece: EndPieceRow,
) -> None:
	if end_piece.width_mm is None:
		frappe.throw(_("End piece width is required"))
	if end_piece.length_mm is None:
		frappe.throw(_("End piece length is required"))
	if end_piece.weight_kg is None:
		frappe.throw(_("End piece weight is required"))
	_validate_end_piece_disposition(end_piece)
	_validate_non_reuse_end_piece_fields_are_empty(end_piece)
	_validate_non_scrap_end_piece_fields_are_empty(end_piece)
	if _is_reuse_end_piece(end_piece):
		if _is_missing(getattr(end_piece, "used_for_finished_part", None)):
			frappe.throw(_("Used for finished part is required for reuse end pieces"))
		_validate_reuse_suffix(end_piece)
		if getattr(end_piece, "bom_quantity", None) is None or end_piece.bom_quantity <= 0:
			frappe.throw(_("BOM quantity must be greater than zero for reuse end pieces"))
		_validate_reuse_weight_split(layout, end_piece)
	if _is_scrap_end_piece(end_piece) and _is_missing(getattr(end_piece, "scrap_item", None)):
		frappe.throw(_("Scrap item is required for scrap end pieces"))


def _validate_end_piece_disposition(end_piece: EndPieceRow) -> None:
	disposition = getattr(end_piece, "disposition", None)
	if disposition in {"Reuse", "Scrap"}:
		return
	frappe.throw(_("Disposition must be either Reuse or Scrap"))


def _validate_non_reuse_end_piece_fields_are_empty(end_piece: EndPieceRow) -> None:
	if _is_reuse_end_piece(end_piece):
		return
	if not _is_missing(getattr(end_piece, "used_for_finished_part", None)):
		frappe.throw(_("Used for finished part is allowed only for reuse end pieces"))
	if _has_non_zero_value(getattr(end_piece, "bom_quantity", None)):
		frappe.throw(_("BOM quantity is allowed only for reuse end pieces"))
	if _has_non_zero_value(getattr(end_piece, "net_weight_per_part_kg", None)):
		frappe.throw(_("Net weight per part is only allowed for reuse end pieces"))
	if _has_non_zero_value(getattr(end_piece, "gross_weight_per_part_kg", None)):
		frappe.throw(_("Gross weight per part is only allowed for reuse end pieces"))
	if _has_non_zero_value(getattr(end_piece, "scrap_weight_per_part_kg", None)):
		frappe.throw(_("Scrap weight per part is only allowed for reuse end pieces"))
	if _has_non_zero_value(getattr(end_piece, "bom_scrap_quantity_kg", None)):
		frappe.throw(_("BOM scrap quantity is allowed only for reuse end pieces"))


def _validate_non_scrap_end_piece_fields_are_empty(end_piece: EndPieceRow) -> None:
	if _is_scrap_end_piece(end_piece):
		return
	if _is_reuse_end_piece(end_piece):
		return
	if not _is_missing(getattr(end_piece, "scrap_item", None)):
		frappe.throw(_("Scrap item is allowed only for scrap end pieces"))


def _validate_end_piece_distribution(
	layout: SheetCuttingLayoutDocument,
	end_pieces: Sequence[EndPieceRow],
) -> None:
	parts_per_sheet = int(getattr(layout, "parts_per_sheet", 0) or 0)
	if parts_per_sheet <= 0:
		frappe.throw(_("Parts per sheet must be greater than zero for end-piece distribution"))

	end_piece_weight_per_part = sum(
		end_piece.weight_kg / parts_per_sheet for end_piece in end_pieces if end_piece.weight_kg is not None
	)
	derived_fg_weight = (
		_flt(getattr(layout, "gross_weight_per_part_kg", 0))
		- _flt(getattr(layout, "scrap_weight_per_part_kg", 0))
		- end_piece_weight_per_part
	)
	if derived_fg_weight < 0:
		frappe.throw(_("Derived finished goods weight must be non-negative"))


def _validate_reuse_suffix(end_piece: EndPieceRow) -> None:
	used_for_finished_part = str(getattr(end_piece, "used_for_finished_part", "") or "").strip().upper()
	if used_for_finished_part.endswith(("SHR", "BLK", "DR")):
		return
	frappe.throw(_("Used for finished part must end with SHR, BLK, or DR"))


def _validate_reuse_weight_split(
	layout: SheetCuttingLayoutDocument,
	end_piece: EndPieceRow,
) -> None:
	net_weight = getattr(end_piece, "net_weight_per_part_kg", None)
	if net_weight is None:
		frappe.throw(_("Net weight per part is required for reuse end pieces"))
	if net_weight < 0:
		frappe.throw(_("Net weight per part must be non-negative for reuse end pieces"))
	gross_weight = _flt(getattr(end_piece, "gross_weight_per_part_kg", 0))
	if gross_weight <= 0:
		frappe.throw(_("Gross weight per part must be greater than zero for reuse end pieces"))
	scrap_weight = _flt(getattr(end_piece, "scrap_weight_per_part_kg", 0))
	if scrap_weight < 0:
		frappe.throw(_("Scrap weight per part cannot be negative for reuse end pieces"))
	bom_scrap_quantity = _flt(getattr(end_piece, "bom_scrap_quantity_kg", 0))
	if bom_scrap_quantity < 0:
		frappe.throw(_("BOM scrap quantity must be non-negative for reuse end pieces"))
	scrap_item = getattr(end_piece, "scrap_item", None)
	if bom_scrap_quantity > 0:
		if _is_missing(scrap_item):
			frappe.throw(_("Scrap item is required for reuse end pieces when BOM scrap quantity is positive"))
	if not _is_missing(scrap_item):
		if _same_item_code(scrap_item, getattr(end_piece, "used_for_finished_part", None)):
			frappe.throw(_("Scrap item cannot be the used-for finished part"))
		_validate_scrap_item_is_not_generated_end_piece_item(layout, end_piece, scrap_item)


def _validate_scrap_item_is_not_generated_end_piece_item(
	layout: SheetCuttingLayoutDocument,
	end_piece: EndPieceRow,
	scrap_item: str | None,
) -> None:
	if _is_missing(scrap_item):
		return
	try:
		generated_item_code = derive_end_piece_item_code(
			used_for_finished_part=getattr(end_piece, "used_for_finished_part", None),
			thickness_mm=getattr(layout, "sheet_thickness_mm", None),
			width_mm=getattr(end_piece, "width_mm", None),
			length_mm=getattr(end_piece, "length_mm", None),
		)
	except ValueError:
		return
	if _same_item_code(scrap_item, generated_item_code):
		frappe.throw(_("Scrap item cannot be the generated end-piece item"))


def _is_reuse_end_piece(end_piece: EndPieceRow) -> bool:
	return getattr(end_piece, "disposition", None) == "Reuse"


def _is_scrap_end_piece(end_piece: EndPieceRow) -> bool:
	return getattr(end_piece, "disposition", None) == "Scrap"


def apply_end_piece_bom_status(
	layout: SheetCuttingLayoutDocument,
	end_pieces: Sequence[EndPieceRow],
) -> None:
	reuse_end_pieces = [end_piece for end_piece in end_pieces if _is_reuse_end_piece(end_piece)]
	if not reuse_end_pieces:
		layout.end_piece_bom_status = "Not Required"
		return
	if all(
		not _is_missing(getattr(end_piece, "generated_end_piece_bom", None)) for end_piece in reuse_end_pieces
	):
		layout.end_piece_bom_status = "Generated"
		return
	layout.end_piece_bom_status = "Pending"


def _validate_end_piece_item_code_is_locked(end_piece: EndPieceRow) -> None:
	has_value_changed = getattr(end_piece, "has_value_changed", None)
	if not callable(has_value_changed) or not has_value_changed("end_piece_item_code"):
		return
	if _has_generated_end_piece_records(end_piece):
		frappe.throw(_("End piece item code cannot be changed after generated records exist"))


def _has_generated_end_piece_records(end_piece: EndPieceRow) -> bool:
	return not _is_missing(getattr(end_piece, "generated_end_piece_item", None)) or not _is_missing(
		getattr(end_piece, "generated_end_piece_bom", None)
	)


def _validate_complete_sheet_consumption(
	layout: SheetCuttingLayoutDocument,
	end_pieces: Sequence[EndPieceRow],
) -> None:
	sheet_weight = getattr(layout, "weight_per_sheet_kg", None)
	if sheet_weight is None:
		return

	consumed_weight = calculate_consumed_weight_kg(layout, end_pieces)
	unaccounted_weight = _sheet_consumption_flt(_sheet_consumption_flt(sheet_weight) - consumed_weight)

	if unaccounted_weight > SHEET_CONSUMPTION_TOLERANCE_KG:
		frappe.throw(
			_("There is no accounting for {0} kg of sheet consumption").format(
				_format_sheet_consumption_weight(unaccounted_weight)
			)
		)
	if unaccounted_weight < -SHEET_CONSUMPTION_TOLERANCE_KG:
		frappe.throw(
			_("Sheet consumption exceeds sheet weight by {0} kg").format(
				_format_sheet_consumption_weight(abs(unaccounted_weight))
			)
		)


def _validate_generated_bom_matches_layout(layout: SheetCuttingLayoutDocument) -> None:
	generated_bom = str(getattr(layout, "generated_bom", "") or "").strip()
	if not generated_bom:
		return

	get_doc = getattr(frappe, "get_doc", None)
	if not callable(get_doc):
		return

	bom = get_doc("BOM", generated_bom)
	expected = build_bom_from_layout(layout)  # type: ignore[arg-type]

	if str(getattr(bom, "item", "") or "").strip() != expected.item:
		frappe.throw(
			_("BOM item mismatch: expected {0}, found {1}").format(
				expected.item,
				getattr(bom, "item", None),
			)
		)
	actual_quantity = _coerce_bom_quantity(getattr(bom, "quantity", None))
	if actual_quantity != expected.quantity:
		frappe.throw(
			_("BOM quantity mismatch: expected {0}, found {1}").format(
				expected.quantity,
				getattr(bom, "quantity", None),
			)
		)

	_validate_bom_rows(
		actual_rows=list(getattr(bom, "items", []) or []),
		expected_rows=expected.items,
		qty_getter=_bom_row_qty,
		category="raw material",
	)
	_validate_bom_rows(
		actual_rows=list(getattr(bom, "scrap_items", []) or []),
		expected_rows=expected.scrap_items,
		qty_getter=_bom_scrap_row_qty,
		category="scrap",
	)


def _validate_bom_rows(
	*,
	actual_rows: Sequence[object],
	expected_rows: Sequence[BomItemRow],
	qty_getter: object,
	category: str,
) -> None:
	expected_by_item = _sum_expected_bom_rows(expected_rows)
	actual_by_item = _sum_actual_bom_rows(actual_rows, qty_getter)  # type: ignore[arg-type]
	if set(actual_by_item) != set(expected_by_item):
		frappe.throw(
			_("BOM {0} item mismatch: expected {1}, found {2}").format(
				category,
				", ".join(sorted(expected_by_item)) or "none",
				", ".join(sorted(actual_by_item)) or "none",
			)
		)
	for item_code, expected_qty in expected_by_item.items():
		actual_qty = actual_by_item[item_code]
		if _flt(actual_qty - expected_qty) != 0:
			frappe.throw(
				_("BOM {0} quantity mismatch for {1}: expected {2}, found {3}").format(
					category,
					item_code,
					expected_qty,
					actual_qty,
				)
			)


def _sum_expected_bom_rows(rows: Sequence[BomItemRow]) -> dict[str, float]:
	totals: dict[str, float] = {}
	for row in rows:
		totals[row.item_code] = _flt(totals.get(row.item_code, 0) + row.qty)
	return totals


def _coerce_bom_quantity(value: object) -> int | None:
	try:
		number = float(value)
	except (TypeError, ValueError):
		return None
	if not number.is_integer():
		return None
	return int(number)


def _sum_actual_bom_rows(rows: Sequence[object], qty_getter: object) -> dict[str, float]:
	totals: dict[str, float] = {}
	for row in rows:
		item_code = str(getattr(row, "item_code", "") or "").strip()
		if not item_code:
			continue
		qty = qty_getter(row)  # type: ignore[operator]
		totals[item_code] = _flt(totals.get(item_code, 0) + qty)
	return totals


def _bom_row_qty(row: object) -> float:
	return float(getattr(row, "qty", 0) or 0)


def _bom_scrap_row_qty(row: object) -> float:
	return float(getattr(row, "stock_qty", None) or getattr(row, "qty", 0) or 0)


def _is_missing(value: object) -> bool:
	return value is None or (isinstance(value, str) and value.strip() == "")


def _same_item_code(left: object, right: object) -> bool:
	if _is_missing(left) or _is_missing(right):
		return False
	return str(left).strip().casefold() == str(right).strip().casefold()


def _has_non_zero_value(value: object) -> bool:
	if _is_missing(value):
		return False
	try:
		return float(value) != 0
	except (TypeError, ValueError):
		return True


def _float_precision() -> int:
	get_system_settings = getattr(frappe, "get_system_settings", None)
	if callable(get_system_settings):
		precision = get_system_settings("float_precision")
		if precision:
			return int(precision)
	return DEFAULT_FLOAT_PRECISION


def _calculation_precision() -> int:
	return max(_float_precision(), DEFAULT_FLOAT_PRECISION)


def _sheet_consumption_flt(value: float | int | str | None) -> float:
	utils = getattr(frappe, "utils", None)
	flt = getattr(utils, "flt", None)
	if callable(flt):
		return flt(value or 0, SHEET_CONSUMPTION_PRECISION)
	return round(float(value or 0), SHEET_CONSUMPTION_PRECISION)


def _format_sheet_consumption_weight(value: float) -> str:
	return f"{_sheet_consumption_flt(value):.{SHEET_CONSUMPTION_PRECISION}f}"


def _consumption_status(leftover_weight: float) -> str:
	if leftover_weight > SHEET_CONSUMPTION_TOLERANCE_KG:
		return "Short"
	if leftover_weight < -SHEET_CONSUMPTION_TOLERANCE_KG:
		return "Excess"
	return "Balanced"


def _flt(value: float | int | str | None) -> float:
	precision = _calculation_precision()
	return _round_value(value, precision)


def _round_value(value: float | int | str | None, precision: int) -> float:
	utils = getattr(frappe, "utils", None)
	flt = getattr(utils, "flt", None)
	if callable(flt):
		return flt(value or 0, precision)
	return round(float(value or 0), precision)
