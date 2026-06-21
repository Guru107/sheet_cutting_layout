from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import frappe

from sheet_cutting_layout.services import validators
from sheet_cutting_layout.services.bom_service import build_weight_split_bom_rows
from sheet_cutting_layout.services.end_piece_item_service import (
	ensure_end_piece_item,
	layout_end_piece_source_finished_part,
)

_ = frappe._


class EndPieceRow(Protocol):
	idx: int
	disposition: str
	end_piece_item_code: str | None
	generated_end_piece_bom: str | None
	width_mm: float | None
	length_mm: float | None
	weight_kg: float | None
	strip_width_mm: float | None
	strip_length_mm: float | None
	strip_weight_kg: float | None
	used_for_finished_part: str | None
	bom_quantity: float | None
	net_weight_per_part_kg: float | None
	gross_weight_per_part_kg: float | None
	scrap_weight_per_part_kg: float | None
	bom_scrap_quantity_kg: float | None
	scrap_item: str | None


class LayoutDocument(Protocol):
	name: str
	status: str | None
	company: str | None
	finished_part_code: str | None
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
	pending_rows = _pending_rows(layout)

	for row in pending_rows:
		_apply_missing_strip_weight(layout, row)
		_validate_pending_row(layout, row)
		item_code = _clean(getattr(row, "end_piece_item_code", None))
		if not item_code:
			item_code = ensure_end_piece_item(
				layout,
				row,
				source_finished_part=layout_end_piece_source_finished_part(layout),
			)
			row.end_piece_item_code = item_code
			generated_items.append(item_code)
		bom_name = _create_end_piece_bom(layout, row, item_code)
		if hasattr(row, "generated_end_piece_bom"):
			row.generated_end_piece_bom = bom_name
		generated_boms.append(bom_name)

	if generated_boms:
		_apply_end_piece_bom_status(layout)
		_persist_generated_links(layout, pending_rows)

	return {"items": generated_items, "boms": generated_boms}


def _create_end_piece_bom(layout: LayoutDocument, row: EndPieceRow, item_code: str) -> str:
	bom = frappe.new_doc("BOM")
	bom.item = _required_clean(row, "used_for_finished_part")
	bom.company = _company_for_layout(layout)
	bom.quantity = getattr(row, "bom_quantity", None)
	bom.custom_operation = "Shearing"
	bom.sheet_cutting_layout = getattr(layout, "name", None)

	weight_rows = build_weight_split_bom_rows(
		raw_material_item=item_code,
		raw_material_qty_kg=float(getattr(row, "strip_weight_kg", 0) or 0),
		scrap_qty_kg=float(getattr(row, "bom_scrap_quantity_kg", 0) or 0),
		scrap_item=_clean(getattr(row, "scrap_item", None)),
		scrap_row_type="process_scrap",
	)
	for item_row in weight_rows.items:
		bom.append(
			"items",
			{
				"item_code": item_row.item_code,
				"qty": item_row.qty,
				"uom": item_row.uom,
			},
		)

	for scrap_row in weight_rows.scrap_items:
		bom.append(
			"scrap_items",
			{
				"item_code": scrap_row.item_code,
				"qty": scrap_row.qty,
				"stock_qty": scrap_row.qty,
				"uom": scrap_row.uom,
			},
		)

	bom.insert(ignore_permissions=True)
	bom.submit()
	return bom.name


def _validate_pending_row(layout: LayoutDocument, row: EndPieceRow) -> None:
	row_idx = getattr(row, "idx", 0)
	if _is_missing(getattr(row, "used_for_finished_part", None)):
		_throw(_("Row {0}: Used for finished part is required").format(row_idx))
	if getattr(row, "bom_quantity", None) is None or row.bom_quantity <= 0:
		_throw(_("Row {0}: BOM quantity must be greater than zero").format(row_idx))
	if getattr(row, "bom_scrap_quantity_kg", None) is None or row.bom_scrap_quantity_kg < 0:
		_throw(_("Row {0}: BOM scrap quantity must be non-negative").format(row_idx))
	if getattr(row, "strip_weight_kg", None) is None or row.strip_weight_kg <= 0:
		_throw(_("Row {0}: Strip weight must be greater than zero").format(row_idx))
	if row.bom_scrap_quantity_kg > 0 and _is_missing(getattr(row, "scrap_item", None)):
		_throw(_("Row {0}: Scrap item is required when BOM scrap quantity is positive").format(row_idx))


def _apply_missing_strip_weight(layout: LayoutDocument, row: EndPieceRow) -> None:
	if _flt(getattr(row, "strip_weight_kg", 0)) > 0:
		return
	validators.apply_end_piece_strip_weight_formulas(layout, [row])


def _reuse_end_pieces(layout: LayoutDocument) -> list[EndPieceRow]:
	return [row for row in getattr(layout, "end_pieces", []) or [] if _is_reuse(row)]


def _pending_rows(layout: LayoutDocument) -> list[EndPieceRow]:
	return [
		row
		for row in _reuse_end_pieces(layout)
		if _is_missing(getattr(row, "end_piece_item_code", None))
		or _is_missing(getattr(row, "generated_end_piece_bom", None))
	]


def _is_reuse(row: EndPieceRow) -> bool:
	return str(getattr(row, "disposition", "") or "").strip().lower() == "reuse"


def _flt(value: float | int | str | None) -> float:
	try:
		return float(value or 0)
	except (TypeError, ValueError):
		return 0.0


def _apply_end_piece_bom_status(layout: LayoutDocument) -> None:
	validators.apply_end_piece_bom_status(layout, getattr(layout, "end_pieces", []) or [])


def _persist_generated_links(layout: LayoutDocument, rows: Sequence[EndPieceRow]) -> None:
	if _is_submitted_document(layout):
		for row in rows:
			_db_set_row_field(row, "end_piece_item_code")
			_db_set_row_field(row, "strip_width_mm", skip_none=True)
			_db_set_row_field(row, "strip_length_mm", skip_none=True)
			_db_set_row_field(row, "strip_weight_kg", skip_none=True)
			if hasattr(row, "generated_end_piece_bom"):
				_db_set_row_field(row, "generated_end_piece_bom")
		layout.db_set(
			"end_piece_bom_status",
			getattr(layout, "end_piece_bom_status", None),
			update_modified=True,
		)
		return

	save = getattr(layout, "save", None)
	if callable(save):
		save(ignore_permissions=True)


def _db_set_row_field(row: EndPieceRow, fieldname: str, *, skip_none: bool = False) -> None:
	value = getattr(row, fieldname, None)
	if skip_none and value is None:
		return
	row.db_set(fieldname, value, update_modified=False)


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

	import erpnext

	company = _clean(erpnext.get_default_company())
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
