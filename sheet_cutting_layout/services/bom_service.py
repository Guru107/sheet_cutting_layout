from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol


class ValidationError(ValueError):
	pass


class FinishedPartRow(Protocol):
	finished_part_item: str
	parts_per_sheet: int
	gross_weight_per_part_kg: float
	scrap_weight_per_part_kg: float


class EndPieceRow(Protocol):
	end_piece_item: str
	weight_kg: float
	qty_per_sheet: float
	disposition: str | None


class LayoutDocument(Protocol):
	raw_material_item: str
	process_scrap_item: str
	weight_per_sheet_kg: float
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


def end_piece_per_part_kg(ep_weight_kg: float, qty_per_sheet: float, parts_per_sheet: int) -> float:
	if parts_per_sheet <= 0:
		raise ValidationError("Parts per sheet must be greater than zero for end-piece distribution")
	return (ep_weight_kg * qty_per_sheet) / parts_per_sheet


def build_bom_from_layout_row(
	layout_doc: LayoutDocument,
	finished_part_row: FinishedPartRow,
	*,
	document_factory: BomDocumentFactory | None = None,
) -> BomDocument:
	bom = _new_bom(finished_part_row.finished_part_item, document_factory)
	bom.quantity = finished_part_row.parts_per_sheet
	bom.items.append(
		BomItemRow(
			item_code=layout_doc.raw_material_item,
			qty=_sheet_weight_kg(layout_doc, finished_part_row),
			row_type="raw_material",
		)
	)

	scrap_endpiece_weight = sum(
		end_piece.weight_kg * end_piece.qty_per_sheet
		for end_piece in layout_doc.end_pieces
		if _is_scrap_end_piece(end_piece)
	)
	process_scrap_weight = (
		finished_part_row.scrap_weight_per_part_kg * finished_part_row.parts_per_sheet
		+ scrap_endpiece_weight
	)
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
			continue
		bom.scrap_items.append(
			BomItemRow(
				item_code=end_piece.end_piece_item,
				qty=end_piece.weight_kg * end_piece.qty_per_sheet,
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


def _sheet_weight_kg(layout_doc: LayoutDocument, finished_part_row: FinishedPartRow) -> float:
	weight_per_sheet_kg = getattr(layout_doc, "weight_per_sheet_kg", None)
	if weight_per_sheet_kg is not None:
		return weight_per_sheet_kg

	end_piece_weight = sum(
		end_piece.weight_kg * end_piece.qty_per_sheet for end_piece in layout_doc.end_pieces
	)
	return finished_part_row.gross_weight_per_part_kg * finished_part_row.parts_per_sheet + end_piece_weight
