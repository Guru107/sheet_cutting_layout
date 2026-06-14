from __future__ import annotations

import io
import os
import re
from collections.abc import Callable, Mapping, Sequence
from copy import copy as _copy

from openpyxl import load_workbook

_INVALID_SHEET_TITLE_CHARS = re.compile(r"[\\*?:/\[\]]")
_MAX_SHEET_TITLE_LENGTH = 31


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
	_apply_cell_map(worksheet, layout)
	buffer = io.BytesIO()
	workbook.save(buffer)
	return buffer.getvalue()


def walk_layout_tree(layout: object, fetch_child: Callable[[str], object]) -> list[object]:
	"""Return the layout and every descendant child layout, depth-first."""
	visited: set[str] = set()
	return list(_walk_layout_tree(layout, fetch_child, visited))


def unique_sheet_title(base: object, used: set[str]) -> str:
	"""Return an openpyxl-safe worksheet title unique within ``used``."""
	title = _INVALID_SHEET_TITLE_CHARS.sub("_", str(base or "").strip())
	title = title[:_MAX_SHEET_TITLE_LENGTH] or "Sheet"
	if title not in used:
		return title

	for index in range(2, 10000):
		suffix = f" ({index})"
		trimmed = title[: _MAX_SHEET_TITLE_LENGTH - len(suffix)]
		candidate = f"{trimmed}{suffix}"
		if candidate not in used:
			return candidate
	raise ValueError(f"Could not build a unique sheet title from {base!r}")


def build_multi_sheet_workbook(pages: Sequence[tuple[object, Mapping[str, object]]]):
	"""Build one workbook with one templated worksheet per layout page."""
	pages = list(pages)
	if not pages:
		raise ValueError("Cannot build a workbook without at least one layout page")

	used_titles: set[str] = set()
	workbook = None
	for index, (page_title, layout) in enumerate(pages):
		template = load_workbook(default_template_path())
		source_worksheet = template.active
		title = unique_sheet_title(page_title, used_titles)
		used_titles.add(title)

		if index == 0:
			workbook = template
			worksheet = source_worksheet
			worksheet.title = title
		else:
			worksheet = _clone_template_worksheet(workbook, source_worksheet, title)
		_apply_cell_map(worksheet, layout)

	return workbook


def _walk_layout_tree(layout: object, fetch_child: Callable[[str], object], visited: set[str]):
	name = str(getattr(layout, "name", "") or "").strip()
	if name in visited:
		return
	visited.add(name)
	yield layout

	for row in getattr(layout, "end_pieces", []) or []:
		if str(getattr(row, "disposition", "") or "").strip() != "Reuse":
			continue
		child_name = str(getattr(row, "child_layout", "") or "").strip()
		if not child_name or child_name in visited:
			continue
		child = fetch_child(child_name)
		yield from _walk_layout_tree(child, fetch_child, visited)


def _apply_cell_map(worksheet: object, layout: Mapping[str, object]) -> None:
	for coordinate, value in build_cell_map(layout).items():
		worksheet[coordinate] = value if value != "" else None


def _clone_template_worksheet(workbook: object, source_worksheet: object, title: str) -> object:
	worksheet = workbook.create_sheet(title=title)
	for row in source_worksheet.iter_rows():
		for cell in row:
			target = worksheet.cell(row=cell.row, column=cell.column, value=cell.value)
			if cell.has_style:
				target.font = _copy(cell.font)
				target.border = _copy(cell.border)
				target.fill = _copy(cell.fill)
				target.number_format = cell.number_format
				target.protection = _copy(cell.protection)
				target.alignment = _copy(cell.alignment)
	for merged_range in list(source_worksheet.merged_cells.ranges):
		worksheet.merge_cells(str(merged_range))
	for column_letter, dimension in source_worksheet.column_dimensions.items():
		worksheet.column_dimensions[column_letter].width = dimension.width
	for row_index, dimension in source_worksheet.row_dimensions.items():
		worksheet.row_dimensions[row_index].height = dimension.height
	return worksheet


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
