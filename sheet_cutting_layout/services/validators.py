from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol

try:
	import frappe
except ImportError:

	class _ValidationError(Exception):
		pass

	class _FrappeCompat:
		ValidationError = _ValidationError

		@staticmethod
		def throw(message: str) -> None:
			raise _ValidationError(message)

	frappe = _FrappeCompat()

_ = getattr(frappe, "_", lambda message: message)


class FinishedPartRow(Protocol):
	finished_part_item: str
	parts_per_sheet: int
	net_weight_per_part_kg: float | None
	gross_weight_per_part_kg: float
	scrap_weight_per_part_kg: float


class EndPieceRow(Protocol):
	end_piece_item_code: str | None
	width_mm: float | None
	length_mm: float | None
	weight_kg: float | None
	qty_per_sheet: float | None
	disposition: str | None
	used_for_finished_part: str | None
	bom_quantity: float | None
	bom_scrap_quantity_kg: float | None
	generated_end_piece_item: str | None
	generated_end_piece_bom: str | None
	scrap_item: str | None


class SheetCuttingLayoutDocument(Protocol):
	finished_parts: Sequence[FinishedPartRow]
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
	parts_per_strip: int | None
	no_of_strips: int | None
	parts_per_sheet: int | None
	consumed_weight_kg: float | None
	leftover_weight_kg: float | None
	consumption_status: str | None


ALNUM_RE = re.compile(r"^[A-Za-z0-9]+$")
STEEL_DENSITY_G_PER_CM3 = 7.86
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
	finished_parts = list(getattr(layout, "finished_parts", []) or [])
	end_pieces = list(getattr(layout, "end_pieces", []) or [])
	apply_parts_per_sheet_formula(layout, finished_parts)
	apply_finished_part_weight_formulas(layout, finished_parts)
	apply_end_piece_weight_formulas(layout, end_pieces)
	accounted_finished_parts = _accounted_finished_parts(finished_parts)

	if len(accounted_finished_parts) != 1:
		frappe.throw(_("Sheet Cutting Layout requires exactly one finished part"))

	for finished_part in accounted_finished_parts:
		validate_finished_part_code(finished_part.finished_part_item)
		_validate_finished_part_weights(finished_part)
		if finished_part.scrap_weight_per_part_kg > 0 and _is_missing(
			getattr(layout, "process_scrap_item", None)
		):
			frappe.throw(_("Process scrap item is required when process scrap weight is positive"))

	for end_piece in end_pieces:
		_validate_generated_end_piece_item_code_is_locked(end_piece)
		_validate_end_piece_required_fields(end_piece)

	if _requires_process_scrap_item_for_reuse_bom(end_pieces) and _is_missing(
		getattr(layout, "process_scrap_item", None)
	):
		frappe.throw(_("Process scrap item is required when reuse BOM scrap weight is positive"))

	if end_pieces:
		_validate_end_piece_distribution(accounted_finished_parts, end_pieces)
	apply_consumption_tracking(layout, accounted_finished_parts, end_pieces)
	apply_end_piece_bom_status(layout, end_pieces)
	_validate_complete_sheet_consumption(layout, accounted_finished_parts, end_pieces)


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


def apply_finished_part_weight_formulas(
	layout: SheetCuttingLayoutDocument,
	finished_parts: Sequence[FinishedPartRow],
) -> None:
	gross_weight = calculate_gross_weight_per_part_kg(
		weight_of_strip_kg=getattr(layout, "weight_of_strip_kg", None),
		parts_per_strip=getattr(layout, "parts_per_strip", None),
	)
	if gross_weight is None:
		return

	for finished_part in finished_parts:
		if _is_missing(finished_part.finished_part_item):
			continue
		net_weight = getattr(finished_part, "net_weight_per_part_kg", None)
		if net_weight is None:
			continue
		finished_part.gross_weight_per_part_kg = gross_weight
		finished_part.scrap_weight_per_part_kg = _flt(gross_weight - _flt(net_weight))


def apply_parts_per_sheet_formula(
	layout: SheetCuttingLayoutDocument,
	finished_parts: Sequence[FinishedPartRow],
) -> None:
	parts_per_sheet = calculate_parts_per_sheet(
		parts_per_strip=getattr(layout, "parts_per_strip", None),
		no_of_strips=getattr(layout, "no_of_strips", None),
	)
	if parts_per_sheet is None:
		return

	layout.parts_per_sheet = parts_per_sheet
	for finished_part in finished_parts:
		if _is_missing(finished_part.finished_part_item):
			continue
		finished_part.parts_per_sheet = parts_per_sheet


def calculate_parts_per_sheet(
	*,
	parts_per_strip: int | None,
	no_of_strips: int | None,
) -> int | None:
	if parts_per_strip is None or no_of_strips is None:
		return None
	if parts_per_strip <= 0 or no_of_strips <= 0:
		return None
	return int(parts_per_strip) * int(no_of_strips)


def calculate_gross_weight_per_part_kg(
	*,
	weight_of_strip_kg: float | None,
	parts_per_strip: int | None,
) -> float | None:
	if weight_of_strip_kg is None or parts_per_strip is None or parts_per_strip <= 0:
		return None
	return _flt(weight_of_strip_kg / parts_per_strip)


def calculate_parent_gross_weight_per_part_kg(
	*,
	weight_of_strip_kg: float | None,
	parts_per_strip: int | None,
) -> float | None:
	if weight_of_strip_kg is None or parts_per_strip is None or parts_per_strip <= 0:
		return None
	return _flt(weight_of_strip_kg / parts_per_strip)


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
		qty_per_sheet = getattr(end_piece, "qty_per_sheet", None)
		if weight is not None and qty_per_sheet is not None and qty_per_sheet > 0:
			end_piece.weight_kg = _flt(weight * qty_per_sheet)


def suggest_end_piece_item_code(
	*,
	raw_material_item: str | None,
	thickness_mm: float | None,
	width_mm: float | None,
	length_mm: float | None,
) -> str | None:
	if (
		_is_missing(raw_material_item)
		or thickness_mm is None
		or width_mm is None
		or length_mm is None
	):
		return None
	return (
		f"{raw_material_item}-EP-"
		f"{_format_code_number(thickness_mm)}x{_format_code_number(width_mm)}x{_format_code_number(length_mm)}"
	)


def apply_end_piece_item_code_suggestions(
	layout: SheetCuttingLayoutDocument,
	end_pieces: Sequence[EndPieceRow],
) -> None:
	for end_piece in end_pieces:
		if not _is_missing(getattr(end_piece, "end_piece_item_code", None)):
			continue

		suggested_code = suggest_end_piece_item_code(
			raw_material_item=getattr(layout, "raw_material_item", None),
			thickness_mm=getattr(layout, "sheet_thickness_mm", None),
			width_mm=getattr(end_piece, "width_mm", None),
			length_mm=getattr(end_piece, "length_mm", None),
		)
		if suggested_code is not None:
			end_piece.end_piece_item_code = suggested_code


def calculate_sheet_weight_kg(
	*,
	thickness_mm: float | None,
	width_mm: float | None,
	length_mm: float | None,
) -> float | None:
	if thickness_mm is None or width_mm is None or length_mm is None:
		return None
	if thickness_mm <= 0 or width_mm <= 0 or length_mm <= 0:
		return None

	weight = length_mm * width_mm * thickness_mm * _steel_density_g_per_cm3() / 1_000_000
	return _flt(weight)


def apply_consumption_tracking(
	layout: SheetCuttingLayoutDocument,
	finished_parts: Sequence[FinishedPartRow],
	end_pieces: Sequence[EndPieceRow],
) -> None:
	sheet_weight = getattr(layout, "weight_per_sheet_kg", None)
	if sheet_weight is None:
		return

	consumed_weight = calculate_consumed_weight_kg(finished_parts, end_pieces)
	leftover_weight = _sheet_consumption_flt(_sheet_consumption_flt(sheet_weight) - consumed_weight)

	layout.consumed_weight_kg = consumed_weight
	layout.leftover_weight_kg = leftover_weight
	layout.consumption_status = _consumption_status(leftover_weight)


def calculate_consumed_weight_kg(
	finished_parts: Sequence[FinishedPartRow],
	end_pieces: Sequence[EndPieceRow],
) -> float:
	part_gross_weight = sum(
		finished_part.gross_weight_per_part_kg * finished_part.parts_per_sheet
		for finished_part in finished_parts
		if not _is_missing(finished_part.finished_part_item)
	)
	end_piece_weight = sum(
		end_piece.weight_kg
		for end_piece in end_pieces
		if end_piece.weight_kg is not None
	)
	return _sheet_consumption_flt(part_gross_weight + end_piece_weight)


def _accounted_finished_parts(
	finished_parts: Sequence[FinishedPartRow],
) -> list[FinishedPartRow]:
	return [
		finished_part for finished_part in finished_parts if not _is_missing(finished_part.finished_part_item)
	]


def _validate_finished_part_weights(finished_part: FinishedPartRow) -> None:
	net_weight = getattr(finished_part, "net_weight_per_part_kg", None)
	if net_weight is not None and net_weight < 0:
		frappe.throw(_("Net weight per part must be non-negative"))
	if finished_part.gross_weight_per_part_kg < 0:
		frappe.throw(_("Gross weight per part must be non-negative"))
	if finished_part.scrap_weight_per_part_kg < 0:
		if net_weight is None:
			frappe.throw(_("Scrap weight per part must be non-negative"))
		frappe.throw(_("Net weight per part cannot exceed gross weight"))


def _validate_end_piece_required_fields(end_piece: EndPieceRow) -> None:
	if end_piece.width_mm is None:
		frappe.throw(_("End piece width is required"))
	if end_piece.length_mm is None:
		frappe.throw(_("End piece length is required"))
	if end_piece.weight_kg is None:
		frappe.throw(_("End piece weight is required"))
	if end_piece.qty_per_sheet is None:
		frappe.throw(_("End piece quantity is required"))
	if _is_reuse_end_piece(end_piece):
		if _is_missing(getattr(end_piece, "used_for_finished_part", None)):
			frappe.throw(_("Used for finished part is required for reuse end pieces"))
		if _is_missing(getattr(end_piece, "end_piece_item_code", None)):
			frappe.throw(_("End piece item code is required for reuse end pieces"))
		if getattr(end_piece, "bom_quantity", None) is None or end_piece.bom_quantity <= 0:
			frappe.throw(_("BOM quantity must be greater than zero for reuse end pieces"))
		if getattr(end_piece, "bom_scrap_quantity_kg", None) is None or end_piece.bom_scrap_quantity_kg < 0:
			frappe.throw(_("BOM scrap quantity must be non-negative for reuse end pieces"))
	if _is_scrap_end_piece(end_piece) and _is_missing(getattr(end_piece, "scrap_item", None)):
		frappe.throw(_("Scrap item is required for scrap end pieces"))


def _validate_end_piece_distribution(
	finished_parts: Sequence[FinishedPartRow],
	end_pieces: Sequence[EndPieceRow],
) -> None:
	for finished_part in finished_parts:
		if finished_part.parts_per_sheet <= 0:
			frappe.throw(_("Parts per sheet must be greater than zero for end-piece distribution"))

		end_piece_weight_per_part = sum(
			end_piece.weight_kg / finished_part.parts_per_sheet
			for end_piece in end_pieces
			if end_piece.weight_kg is not None
		)
		derived_fg_weight = (
			finished_part.gross_weight_per_part_kg
			- finished_part.scrap_weight_per_part_kg
			- end_piece_weight_per_part
		)
		if derived_fg_weight < 0:
			frappe.throw(_("Derived finished goods weight must be non-negative"))


def _is_reuse_end_piece(end_piece: EndPieceRow) -> bool:
	return getattr(end_piece, "disposition", None) == "Reuse"


def _is_scrap_end_piece(end_piece: EndPieceRow) -> bool:
	return getattr(end_piece, "disposition", None) == "Scrap"


def _requires_process_scrap_item_for_reuse_bom(end_pieces: Sequence[EndPieceRow]) -> bool:
	return any(
		_is_reuse_end_piece(end_piece)
		and getattr(end_piece, "bom_scrap_quantity_kg", None) is not None
		and end_piece.bom_scrap_quantity_kg > 0
		for end_piece in end_pieces
	)


def apply_end_piece_bom_status(
	layout: SheetCuttingLayoutDocument,
	end_pieces: Sequence[EndPieceRow],
) -> None:
	reuse_end_pieces = [end_piece for end_piece in end_pieces if _is_reuse_end_piece(end_piece)]
	if not reuse_end_pieces:
		layout.end_piece_bom_status = "Not Required"
		return
	if all(not _is_missing(getattr(end_piece, "generated_end_piece_bom", None)) for end_piece in reuse_end_pieces):
		layout.end_piece_bom_status = "Generated"
		return
	layout.end_piece_bom_status = "Pending"


def _validate_generated_end_piece_item_code_is_locked(end_piece: EndPieceRow) -> None:
	has_value_changed = getattr(end_piece, "has_value_changed", None)
	if not callable(has_value_changed) or not has_value_changed("end_piece_item_code"):
		return
	if not _is_missing(getattr(end_piece, "generated_end_piece_item", None)) or not _is_missing(
		getattr(end_piece, "generated_end_piece_bom", None)
	):
		frappe.throw(_("End piece item code cannot be changed after generated records exist"))


def _validate_complete_sheet_consumption(
	layout: SheetCuttingLayoutDocument,
	finished_parts: Sequence[FinishedPartRow],
	end_pieces: Sequence[EndPieceRow],
) -> None:
	sheet_weight = getattr(layout, "weight_per_sheet_kg", None)
	if sheet_weight is None:
		return

	consumed_weight = calculate_consumed_weight_kg(finished_parts, end_pieces)
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


def _is_missing(value: object) -> bool:
	return value is None or (isinstance(value, str) and value.strip() == "")


def _float_precision() -> int:
	get_system_settings = getattr(frappe, "get_system_settings", None)
	if callable(get_system_settings):
		precision = get_system_settings("float_precision")
		if precision:
			return int(precision)
	return DEFAULT_FLOAT_PRECISION


def _calculation_precision() -> int:
	return max(_float_precision(), DEFAULT_FLOAT_PRECISION)


def _steel_density_g_per_cm3() -> float:
	return _system_flt(STEEL_DENSITY_G_PER_CM3)


def _sheet_consumption_flt(value: float | int | str | None) -> float:
	utils = getattr(frappe, "utils", None)
	flt = getattr(utils, "flt", None)
	if callable(flt):
		return flt(value or 0, SHEET_CONSUMPTION_PRECISION)
	return round(float(value or 0), SHEET_CONSUMPTION_PRECISION)


def _format_sheet_consumption_weight(value: float) -> str:
	return f"{_sheet_consumption_flt(value):.{SHEET_CONSUMPTION_PRECISION}f}"


def _format_code_number(value: float | int | str) -> str:
	return f"{float(value):.6f}".rstrip("0").rstrip(".")


def _consumption_status(leftover_weight: float) -> str:
	if leftover_weight > SHEET_CONSUMPTION_TOLERANCE_KG:
		return "Short"
	if leftover_weight < -SHEET_CONSUMPTION_TOLERANCE_KG:
		return "Excess"
	return "Balanced"


def _flt(value: float | int | str | None) -> float:
	precision = _calculation_precision()
	return _round_value(value, precision)


def _system_flt(value: float | int | str | None) -> float:
	return _round_value(value, _float_precision())


def _round_value(value: float | int | str | None, precision: int) -> float:
	utils = getattr(frappe, "utils", None)
	flt = getattr(utils, "flt", None)
	if callable(flt):
		return flt(value or 0, precision)
	return round(float(value or 0), precision)
