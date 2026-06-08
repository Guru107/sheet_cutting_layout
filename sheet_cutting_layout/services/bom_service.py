from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

import frappe


class FinishedPartRow(Protocol):
	finished_part_item: str
	parts_per_sheet: int
	gross_weight_per_part_kg: float
	scrap_weight_per_part_kg: float


class EndPieceRow(Protocol):
	weight_kg: float
	qty_per_sheet: float
	disposition: str
	scrap_item: str | None


class LayoutDocument(Protocol):
	raw_material_item: str
	process_scrap_item: str
	weight_per_sheet_kg: float
	no_of_strips: int
	finished_part_code: str | None
	parts_per_sheet: int
	gross_weight_per_part_kg: float
	scrap_weight_per_part_kg: float
	end_pieces: Sequence[EndPieceRow]


BomItemRowType = Literal["raw_material", "process_scrap", "end_piece_scrap"]


@dataclass
class BomItemRow:
	item_code: str
	qty: float
	row_type: BomItemRowType
	uom: str = "Kg"


@dataclass
class BomWeightRows:
	items: list[BomItemRow] = field(default_factory=list)
	scrap_items: list[BomItemRow] = field(default_factory=list)


@dataclass
class BomDocument:
	item: str
	name: str = ""
	quantity: int = 1
	sheet_cutting_layout: str | None = None
	is_active: bool = True
	disabled: bool = False
	status: str = "Active"
	items: list[BomItemRow] = field(default_factory=list)
	scrap_items: list[BomItemRow] = field(default_factory=list)


@dataclass
class ParentFinishedPartRow:
	finished_part_item: str
	parts_per_sheet: int
	gross_weight_per_part_kg: float
	scrap_weight_per_part_kg: float


@dataclass
class ExpectedBomConsumption:
	item: str
	quantity: int
	raw_material_rows: list[BomItemRow]
	scrap_rows: list[BomItemRow]
	total_raw_material_qty: float
	total_scrap_qty: float


BomDocumentFactory = Callable[[str], BomDocument]


def resolve_scrap_item_rate(
	*,
	item_code: str | None,
	company: str | None,
	existing_rate: float | int | str | None = None,
) -> float:
	# Zero/negative/invalid existing rates are treated as unresolved and fall back
	# to valuation-rate lookup for deterministic BOM scrap pricing.
	if existing_rate is not None:
		try:
			existing_rate_value = float(existing_rate)
		except (TypeError, ValueError):
			existing_rate_value = 0.0
		if existing_rate_value > 0:
			return existing_rate_value

	item_code = str(item_code or "").strip()
	if not item_code:
		raise ValueError("Scrap item code is required to resolve scrap rate")
	company = str(company or "").strip()
	if not company:
		raise ValueError(f"Company is required to resolve scrap rate for scrap item {item_code}")

	rate = _fetch_valuation_rate(item_code=item_code, company=company)
	try:
		rate_value = float(rate)
	except (TypeError, ValueError):
		raise ValueError(f"Valuation rate is required for scrap item {item_code}") from None
	if rate_value <= 0:
		raise ValueError(f"Valuation rate is required for scrap item {item_code}")
	return rate_value


def build_weight_split_bom_rows(
	*,
	raw_material_item: str,
	gross_weight_per_part_kg: float,
	scrap_weight_per_part_kg: float,
	quantity: float,
	scrap_item: str | None,
	scrap_row_type: BomItemRowType,
) -> BomWeightRows:
	rows = BomWeightRows(
		items=[
			BomItemRow(
				item_code=raw_material_item,
				qty=gross_weight_per_part_kg * quantity,
				row_type="raw_material",
			)
		]
	)
	scrap_qty = scrap_weight_per_part_kg * quantity
	if scrap_qty > 0:
		if not scrap_item:
			raise ValueError("Scrap item is required when scrap quantity is positive")
		rows.scrap_items.append(
			BomItemRow(
				item_code=scrap_item,
				qty=scrap_qty,
				row_type=scrap_row_type,
			)
		)
	return rows


def build_bom_from_layout_row(
	layout_doc: LayoutDocument,
	finished_part_row: FinishedPartRow,
	*,
	document_factory: BomDocumentFactory | None = None,
) -> BomDocument:
	bom = _new_bom(finished_part_row.finished_part_item, document_factory)
	bom.quantity = _bom_quantity(layout_doc, finished_part_row)
	quantity = finished_part_row.parts_per_sheet
	row_quantity = quantity or 1
	raw_material_weight_per_unit = _sheet_weight_kg(layout_doc, finished_part_row) / row_quantity
	process_scrap_weight_per_unit = (
		finished_part_row.scrap_weight_per_part_kg * quantity / row_quantity
	)

	weight_rows = build_weight_split_bom_rows(
		raw_material_item=layout_doc.raw_material_item,
		gross_weight_per_part_kg=raw_material_weight_per_unit,
		scrap_weight_per_part_kg=process_scrap_weight_per_unit,
		quantity=row_quantity,
		scrap_item=layout_doc.process_scrap_item,
		scrap_row_type="process_scrap",
	)
	bom.items.extend(weight_rows.items)
	bom.scrap_items.extend(weight_rows.scrap_items)

	for end_piece in layout_doc.end_pieces:
		if _is_scrap_end_piece(end_piece):
			scrap_item = _required_scrap_item(end_piece)
			bom.scrap_items.append(
				BomItemRow(
					item_code=scrap_item,
					qty=end_piece.weight_kg,
					row_type="end_piece_scrap",
				)
			)

	return bom


def build_bom_from_layout(
	layout_doc: LayoutDocument,
	*,
	document_factory: BomDocumentFactory | None = None,
) -> BomDocument:
	return build_bom_from_layout_row(
		layout_doc,
		_parent_finished_part_row(layout_doc),
		document_factory=document_factory,
	)


def expected_bom_consumption_from_layout(layout_doc: LayoutDocument) -> ExpectedBomConsumption:
	bom = build_bom_from_layout(layout_doc)
	total_raw_material_qty = sum(row.qty for row in bom.items)
	total_scrap_qty = sum(row.qty for row in bom.scrap_items)
	return ExpectedBomConsumption(
		item=bom.item,
		quantity=bom.quantity,
		raw_material_rows=list(bom.items),
		scrap_rows=list(bom.scrap_items),
		total_raw_material_qty=total_raw_material_qty,
		total_scrap_qty=total_scrap_qty,
	)


def _parent_finished_part_row(layout_doc: LayoutDocument) -> ParentFinishedPartRow:
	finished_part_item = str(getattr(layout_doc, "finished_part_code", "") or "").strip()
	if not finished_part_item:
		raise ValueError("finished_part_code is required to create generated BOM")
	return ParentFinishedPartRow(
		finished_part_item=finished_part_item,
		parts_per_sheet=int(getattr(layout_doc, "parts_per_sheet", 0) or 0),
		gross_weight_per_part_kg=float(getattr(layout_doc, "gross_weight_per_part_kg", 0) or 0),
		scrap_weight_per_part_kg=float(getattr(layout_doc, "scrap_weight_per_part_kg", 0) or 0),
	)


def _new_bom(item: str, document_factory: BomDocumentFactory | None) -> BomDocument:
	if document_factory is not None:
		return document_factory(item)
	return BomDocument(item=item)


def _is_scrap_end_piece(end_piece: EndPieceRow) -> bool:
	return str(getattr(end_piece, "disposition", "") or "").strip().lower() == "scrap"


def _required_scrap_item(end_piece: EndPieceRow) -> str:
	scrap_item = str(getattr(end_piece, "scrap_item", "") or "").strip()
	if not scrap_item:
		raise ValueError("Scrap end piece requires scrap_item before creating BOM scrap row")
	return scrap_item


def _bom_quantity(_layout_doc: LayoutDocument, finished_part_row: FinishedPartRow) -> int:
	return finished_part_row.parts_per_sheet


def _sheet_weight_kg(layout_doc: LayoutDocument, finished_part_row: FinishedPartRow) -> float:
	weight_per_sheet_kg = getattr(layout_doc, "weight_per_sheet_kg", None)
	if weight_per_sheet_kg is not None:
		return weight_per_sheet_kg

	end_piece_weight = sum(end_piece.weight_kg for end_piece in layout_doc.end_pieces)
	return finished_part_row.gross_weight_per_part_kg * finished_part_row.parts_per_sheet + end_piece_weight


def _fetch_valuation_rate(*, item_code: str, company: str) -> float | int | str | None:
	from erpnext.manufacturing.doctype.bom.bom import get_valuation_rate

	args = frappe._dict({"item_code": item_code, "company": company})
	return get_valuation_rate(args)
