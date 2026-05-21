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
	end_piece_item: str | None
	width_mm: float | None
	length_mm: float | None
	weight_kg: float | None
	qty_per_sheet: float | None


class SheetCuttingLayoutDocument(Protocol):
	finished_parts: Sequence[FinishedPartRow]
	end_pieces: Sequence[EndPieceRow]
	process_scrap_item: str | None
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
		_validate_end_piece_required_fields(end_piece)

	if end_pieces:
		_validate_end_piece_distribution(accounted_finished_parts, end_pieces)
	apply_consumption_tracking(layout, accounted_finished_parts, end_pieces)
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
		if weight is not None:
			end_piece.weight_kg = weight


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
		end_piece.weight_kg * end_piece.qty_per_sheet
		for end_piece in end_pieces
		if end_piece.weight_kg is not None and end_piece.qty_per_sheet is not None
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
	if _is_missing(end_piece.end_piece_item):
		frappe.throw(_("End piece item is required"))
	if end_piece.width_mm is None:
		frappe.throw(_("End piece width is required"))
	if end_piece.length_mm is None:
		frappe.throw(_("End piece length is required"))
	if end_piece.weight_kg is None:
		frappe.throw(_("End piece weight is required"))
	if end_piece.qty_per_sheet is None:
		frappe.throw(_("End piece quantity is required"))


def _validate_end_piece_distribution(
	finished_parts: Sequence[FinishedPartRow],
	end_pieces: Sequence[EndPieceRow],
) -> None:
	for finished_part in finished_parts:
		if finished_part.parts_per_sheet <= 0:
			frappe.throw(_("Parts per sheet must be greater than zero for end-piece distribution"))

		end_piece_weight_per_part = sum(
			(end_piece.weight_kg * end_piece.qty_per_sheet) / finished_part.parts_per_sheet
			for end_piece in end_pieces
			if end_piece.weight_kg is not None and end_piece.qty_per_sheet is not None
		)
		derived_fg_weight = (
			finished_part.gross_weight_per_part_kg
			- finished_part.scrap_weight_per_part_kg
			- end_piece_weight_per_part
		)
		if derived_fg_weight < 0:
			frappe.throw(_("Derived finished goods weight must be non-negative"))


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
