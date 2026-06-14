from __future__ import annotations

import io
import os
from collections.abc import Mapping, Sequence

from openpyxl import load_workbook


def build_cell_map(layout: Mapping[str, object]) -> dict[str, object]:
	"""Map a Sheet Cutting Layout dict to FRM/PRD/15 worksheet cells."""
	cells: dict[str, object] = {
		"B1": _text(layout.get("company")),
		"G5": _part_name_label(layout),
		"N5": _joined_part_numbers(layout),
		"B6": _text(layout.get("project")),
		"C6": _text(layout.get("project_name")),
		"K8": _num(layout.get("sheet_thickness_mm")),
		"K9": _num(layout.get("sheet_thickness_mm")),
		"L9": _num(layout.get("sheet_width_mm")),
		"M9": _num(layout.get("sheet_length_mm")),
		"K10": _num(layout.get("weight_of_strip_kg")),
		"K11": _num(layout.get("strip_thickness_mm")),
		"L11": _num(layout.get("strip_width_mm")),
		"M11": _num(layout.get("strip_length_mm")),
		"K12": _num(layout.get("parts_per_strip")),
		"K13": _num(layout.get("no_of_strips")),
		"K14": _num(layout.get("parts_per_sheet")),
		"K15": _num(layout.get("gross_weight_per_part_kg")),
		"K16": _num(layout.get("net_weight_per_part_kg")),
		"K17": _num(layout.get("scrap_weight_per_part_kg")),
	}
	cells.update(_bom_table_cells(layout))
	return cells


def default_template_path() -> str:
	return os.path.join(
		os.path.dirname(__file__),
		"..",
		"templates",
		"iatf",
		"sheet_cutting_layout.xlsx",
	)


def render_workbook_bytes(layout: Mapping[str, object], template_path: str) -> bytes:
	"""Open the FRM/PRD/15 template, apply the cell map, return .xlsx bytes."""
	workbook = load_workbook(template_path)
	worksheet = workbook.active
	for coordinate, value in build_cell_map(layout).items():
		worksheet[coordinate] = value if value != "" else None
	buffer = io.BytesIO()
	workbook.save(buffer)
	return buffer.getvalue()


def _bom_table_cells(layout: Mapping[str, object]) -> dict[str, object]:
	cells: dict[str, object] = {}
	gross = layout.get("gross_weight_per_part_kg")
	nos = layout.get("parts_per_sheet")
	cells["O8"] = _joined_part_numbers(layout)
	cells["P8"] = _num(gross)
	cells["Q8"] = _num(layout.get("net_weight_per_part_kg"))
	cells["R8"] = _num(layout.get("scrap_weight_per_part_kg"))
	cells["S8"] = _num(nos)
	cells["T8"] = _num(_product(gross, nos))
	cells["U8"] = _num(layout.get("raw_material_weight_kg"))

	end_pieces: Sequence[Mapping[str, object]] = layout.get("end_pieces") or []
	for offset, end_piece in enumerate(end_pieces):
		row = 9 + offset
		if row > 11:
			break
		ep_gross = end_piece.get("gross_weight_per_part_kg")
		ep_nos = end_piece.get("bom_quantity")
		cells[f"O{row}"] = _end_piece_label(end_piece)
		cells[f"P{row}"] = _num(ep_gross)
		cells[f"Q{row}"] = _num(end_piece.get("net_weight_per_part_kg"))
		cells[f"R{row}"] = _num(end_piece.get("scrap_weight_per_part_kg"))
		cells[f"S{row}"] = _num(ep_nos)
		cells[f"T{row}"] = _num(_product(ep_gross, ep_nos))
		cells[f"U{row}"] = _num(end_piece.get("weight_kg"))
	return cells


def _part_name_label(layout: Mapping[str, object]) -> str:
	base = _text(layout.get("part_name")).strip()
	if not base:
		return ""
	if layout.get("is_lh_rh"):
		return f"{base} LH & RH"
	return base


def _joined_part_numbers(layout: Mapping[str, object]) -> str:
	part_numbers = layout.get("part_numbers") or []
	cleaned = [str(part).strip() for part in part_numbers if str(part or "").strip()]
	return "_".join(cleaned)


def _end_piece_label(end_piece: Mapping[str, object]) -> str:
	item_code = _text(end_piece.get("end_piece_item_code")).strip()
	if item_code:
		return item_code
	width = end_piece.get("width_mm")
	length = end_piece.get("length_mm")
	if width and length:
		return f"{width} x {length}"
	return ""


def _num(value: object) -> object:
	if value is None or value == "":
		return ""
	return value


def _text(value: object) -> str:
	if value is None:
		return ""
	return str(value)


def _product(left: object, right: object) -> object:
	if left in (None, "") or right in (None, ""):
		return ""
	try:
		return float(left) * float(right)
	except (TypeError, ValueError):
		return ""
