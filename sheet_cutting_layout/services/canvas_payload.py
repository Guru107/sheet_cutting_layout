from __future__ import annotations

from collections.abc import Sequence
from math import isfinite
from typing import Protocol, TypeAlias

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


class FinishedPartRow(Protocol):
	finished_part_item: str
	parts_per_sheet: int
	gross_weight_per_part_kg: float
	scrap_weight_per_part_kg: float


class EndPieceRow(Protocol):
	end_piece_item_code: str | None
	weight_kg: float | None
	qty_per_sheet: float | None
	disposition: str | None
	used_for_finished_part: str | None


class SheetCuttingLayoutDocument(Protocol):
	sheet_width_mm: float | None
	sheet_length_mm: float | None
	sheet_thickness_mm: float | None
	strip_width_mm: float | None
	strip_length_mm: float | None
	no_of_strips: int | None
	parts_per_strip: int | None
	parts_per_sheet: int | None
	finished_parts: Sequence[FinishedPartRow]
	end_pieces: Sequence[EndPieceRow]


def build_canvas_payload(layout_doc: SheetCuttingLayoutDocument) -> dict[str, JsonValue]:
	invalid_markers: list[JsonValue] = []
	sheet_width = _positive_float(layout_doc, "sheet_width_mm", invalid_markers)
	sheet_length = _positive_float(layout_doc, "sheet_length_mm", invalid_markers)
	sheet_thickness = _positive_float(layout_doc, "sheet_thickness_mm", invalid_markers)
	strip_width = _positive_float(layout_doc, "strip_width_mm", invalid_markers)
	strip_length = _positive_float(layout_doc, "strip_length_mm", invalid_markers)
	no_of_strips = _positive_int(layout_doc, "no_of_strips", invalid_markers)
	parts_per_strip = _positive_int(layout_doc, "parts_per_strip", invalid_markers)
	parts_per_sheet = _positive_int(layout_doc, "parts_per_sheet", invalid_markers)

	finished_parts = list(getattr(layout_doc, "finished_parts", []) or [])
	end_pieces = list(getattr(layout_doc, "end_pieces", []) or [])

	return {
		"sheet_dimensions": {
			"width_mm": sheet_width,
			"length_mm": sheet_length,
			"thickness_mm": sheet_thickness,
		},
		"strips": _build_strip_zones(
			sheet_width=sheet_width,
			sheet_length=sheet_length,
			strip_width=strip_width,
			strip_length=strip_length,
			no_of_strips=no_of_strips,
		),
		"part_zones": _build_part_zones(
			finished_parts=finished_parts,
			sheet_width=sheet_width,
			sheet_length=sheet_length,
			strip_length=strip_length,
			no_of_strips=no_of_strips,
			parts_per_strip=parts_per_strip,
			parts_per_sheet=parts_per_sheet,
		),
		"end_piece_zones": _build_end_piece_zones(
			end_pieces=end_pieces,
			sheet_width=sheet_width,
			sheet_length=sheet_length,
			strip_length=strip_length,
			no_of_strips=no_of_strips,
			invalid_markers=invalid_markers,
		),
		"summary": _build_summary(
			finished_parts=finished_parts,
			end_pieces=end_pieces,
			invalid_markers=invalid_markers,
		),
		"invalid_markers": invalid_markers,
	}


def _build_strip_zones(
	*,
	sheet_width: float | None,
	sheet_length: float | None,
	strip_width: float | None,
	strip_length: float | None,
	no_of_strips: int | None,
) -> list[JsonValue]:
	if sheet_width is None or sheet_length is None or no_of_strips is None:
		return []

	width = strip_width if strip_width is not None else sheet_width
	length = strip_length if strip_length is not None else sheet_length / no_of_strips
	return [
		{
			"index": index + 1,
			"x_mm": 0,
			"y_mm": index * length,
			"width_mm": width,
			"length_mm": length,
		}
		for index in range(no_of_strips)
	]


def _build_part_zones(
	*,
	finished_parts: Sequence[FinishedPartRow],
	sheet_width: float | None,
	sheet_length: float | None,
	strip_length: float | None,
	no_of_strips: int | None,
	parts_per_strip: int | None,
	parts_per_sheet: int | None,
) -> list[JsonValue]:
	if sheet_width is None or sheet_length is None:
		return []

	zones: list[JsonValue] = []
	rows = no_of_strips or 1
	columns = parts_per_strip or max(1, ((parts_per_sheet or 1) + rows - 1) // rows)
	default_parts = (no_of_strips or 0) * (parts_per_strip or 0) or parts_per_sheet or 1
	for finished_part in finished_parts:
		row_parts = _as_positive_int(getattr(finished_part, "parts_per_sheet", None))
		part_count = row_parts or default_parts
		rows = no_of_strips or max(1, (part_count + columns - 1) // columns)
		cell_width = sheet_width / columns
		cell_length = (
			strip_length if strip_length is not None and no_of_strips is not None else sheet_length / rows
		)

		for index in range(part_count):
			zones.append(
				{
					"finished_part_item": str(getattr(finished_part, "finished_part_item", "")),
					"index": index + 1,
					"x_mm": (index % columns) * cell_width,
					"y_mm": (index // columns) * cell_length,
					"width_mm": cell_width,
					"length_mm": cell_length,
				}
			)

	return zones


def _build_end_piece_zones(
	*,
	end_pieces: Sequence[EndPieceRow],
	sheet_width: float | None,
	sheet_length: float | None,
	strip_length: float | None,
	no_of_strips: int | None,
	invalid_markers: list[JsonValue],
) -> list[JsonValue]:
	width = sheet_width or 1
	length = sheet_length or 1
	used_length = (
		(strip_length * no_of_strips) if strip_length is not None and no_of_strips is not None else 0
	)
	remnant_length = max(0.0, length - used_length)
	zone_width = width / max(1, len(end_pieces))
	zones: list[JsonValue] = []

	for index, end_piece in enumerate(end_pieces):
		weight = _row_non_negative_float(end_piece, "weight_kg", f"end_pieces[{index}]", invalid_markers)
		qty = _row_positive_float(end_piece, "qty_per_sheet", f"end_pieces[{index}]", invalid_markers)
		zones.append(
			{
				"end_piece_item_code": _optional_str(getattr(end_piece, "end_piece_item_code", None)),
				"weight_kg": weight,
				"qty_per_sheet": qty,
				"disposition": _optional_str(getattr(end_piece, "disposition", None)),
				"used_for_finished_part": _optional_str(getattr(end_piece, "used_for_finished_part", None)),
				"x_mm": index * zone_width,
				"y_mm": used_length,
				"width_mm": zone_width,
				"length_mm": remnant_length if remnant_length > 0 else length / max(1, len(end_pieces)),
			}
		)

	return zones


def _build_summary(
	*,
	finished_parts: Sequence[FinishedPartRow],
	end_pieces: Sequence[EndPieceRow],
	invalid_markers: list[JsonValue],
) -> dict[str, JsonValue]:
	total_gross = 0.0
	total_process_scrap = 0.0
	total_end_piece_weight = 0.0
	derived_fg_estimate = 0.0

	for end_piece in end_pieces:
		weight = _as_float(getattr(end_piece, "weight_kg", None))
		if weight is not None and weight >= 0:
			total_end_piece_weight += weight

	for index, finished_part in enumerate(finished_parts):
		parts = _row_positive_int(
			finished_part, "parts_per_sheet", f"finished_parts[{index}]", invalid_markers
		)
		gross = _row_non_negative_float(
			finished_part,
			"gross_weight_per_part_kg",
			f"finished_parts[{index}]",
			invalid_markers,
		)
		scrap = _row_non_negative_float(
			finished_part,
			"scrap_weight_per_part_kg",
			f"finished_parts[{index}]",
			invalid_markers,
		)
		if parts is None or gross is None or scrap is None:
			continue

		total_gross += gross * parts
		total_process_scrap += scrap * parts
		derived_fg_estimate += (gross - scrap) * parts

	derived_fg_estimate -= total_end_piece_weight

	return {
		"total_gross_weight_kg": total_gross,
		"total_process_scrap_weight_kg": total_process_scrap,
		"total_end_piece_weight_kg": total_end_piece_weight,
		"total_scrap_weight_kg": total_process_scrap + total_end_piece_weight,
		"derived_fg_estimate_kg": derived_fg_estimate,
	}


def _positive_float(source: object, fieldname: str, invalid_markers: list[JsonValue]) -> float | None:
	value = _as_float(getattr(source, fieldname, None))
	if value is None or value <= 0:
		invalid_markers.append(
			_invalid_marker(fieldname, getattr(source, fieldname, None), "must be greater than zero")
		)
		return None
	return value


def _positive_int(source: object, fieldname: str, invalid_markers: list[JsonValue]) -> int | None:
	value = _as_int(getattr(source, fieldname, None))
	if value is None or value <= 0:
		invalid_markers.append(
			_invalid_marker(fieldname, getattr(source, fieldname, None), "must be greater than zero")
		)
		return None
	return value


def _row_positive_int(
	source: object,
	fieldname: str,
	path: str,
	invalid_markers: list[JsonValue],
) -> int | None:
	value = _as_int(getattr(source, fieldname, None))
	if value is None or value <= 0:
		invalid_markers.append(
			_invalid_marker(
				f"{path}.{fieldname}", getattr(source, fieldname, None), "must be greater than zero"
			)
		)
		return None
	return value


def _row_positive_float(
	source: object,
	fieldname: str,
	path: str,
	invalid_markers: list[JsonValue],
) -> float | None:
	value = _as_float(getattr(source, fieldname, None))
	if value is None or value <= 0:
		invalid_markers.append(
			_invalid_marker(
				f"{path}.{fieldname}", getattr(source, fieldname, None), "must be greater than zero"
			)
		)
		return None
	return value


def _row_non_negative_float(
	source: object,
	fieldname: str,
	path: str,
	invalid_markers: list[JsonValue],
) -> float | None:
	value = _as_float(getattr(source, fieldname, None))
	if value is None or value < 0:
		invalid_markers.append(
			_invalid_marker(f"{path}.{fieldname}", getattr(source, fieldname, None), "must be non-negative")
		)
		return None
	return value


def _invalid_marker(fieldname: str, value: object, message: str) -> dict[str, JsonValue]:
	return {
		"field": fieldname,
		"value": _json_scalar(value),
		"message": message,
	}


def _as_float(value: object) -> float | None:
	if value is None or isinstance(value, bool):
		return None
	try:
		number = float(value)
	except (TypeError, ValueError):
		return None
	if not isfinite(number):
		return None
	return number


def _as_int(value: object) -> int | None:
	if value is None or isinstance(value, bool):
		return None
	if isinstance(value, int):
		return value
	if isinstance(value, float) and not isfinite(value):
		return None
	try:
		number = int(value)
	except (OverflowError, TypeError, ValueError):
		return None
	if str(value).strip() not in {str(number), f"{number}.0"}:
		return None
	return number


def _as_positive_int(value: object) -> int | None:
	number = _as_int(value)
	if number is None or number <= 0:
		return None
	return number


def _optional_str(value: object) -> str | None:
	if value is None:
		return None
	text = str(value).strip()
	return text or None


def _json_scalar(value: object) -> JsonValue:
	if value is None or isinstance(value, bool | int | str):
		return value
	if isinstance(value, float):
		return value if isfinite(value) else str(value)
	return str(value)
