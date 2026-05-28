from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
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
	end_pieces: Sequence[EndPieceRow]


BomItemRowType = Literal["raw_material", "process_scrap", "end_piece_scrap"]


@dataclass
class BomItemRow:
	item_code: str
	qty: float
	row_type: BomItemRowType
	uom: str = "Kg"


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


BomDocumentFactory = Callable[[str], BomDocument]


def resolve_scrap_item_rate(
	*,
	item_code: str | None,
	company: str | None,
	existing_rate: float | int | str | None = None,
) -> float:
	if existing_rate is not None and float(existing_rate) > 0:
		return float(existing_rate)

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


def build_bom_from_layout_row(
	layout_doc: LayoutDocument,
	finished_part_row: FinishedPartRow,
	*,
	document_factory: BomDocumentFactory | None = None,
) -> BomDocument:
	bom = _new_bom(finished_part_row.finished_part_item, document_factory)
	bom.quantity = _bom_quantity(layout_doc, finished_part_row)
	bom.items.append(
		BomItemRow(
			item_code=layout_doc.raw_material_item,
			qty=_sheet_weight_kg(layout_doc, finished_part_row),
			row_type="raw_material",
		)
	)

	process_scrap_weight = finished_part_row.scrap_weight_per_part_kg * finished_part_row.parts_per_sheet
	if process_scrap_weight > 0:
		bom.scrap_items.append(
			BomItemRow(
				item_code=layout_doc.process_scrap_item,
				qty=process_scrap_weight,
				row_type="process_scrap",
			)
		)

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


def _bom_quantity(layout_doc: LayoutDocument, finished_part_row: FinishedPartRow) -> int:
	no_of_strips = getattr(layout_doc, "no_of_strips", None)
	if no_of_strips in (None, 0, "0"):
		return finished_part_row.parts_per_sheet

	try:
		quantity = Decimal(str(no_of_strips).strip())
	except (InvalidOperation, ValueError):
		raise ValueError("no_of_strips must be a positive integer") from None

	if quantity <= 0 or quantity != quantity.to_integral_value():
		raise ValueError("no_of_strips must be a positive integer")

	return int(quantity)


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
