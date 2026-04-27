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


class LayoutDocument(Protocol):
	raw_material_item: str
	process_scrap_item: str
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
	is_active: bool = True
	disabled: bool = False
	status: str = "Active"
	items: list[BomItemRow] = field(default_factory=list)


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
	bom.items.append(
		BomItemRow(
			item_code=layout_doc.raw_material_item,
			qty=finished_part_row.gross_weight_per_part_kg,
			row_type="raw_material",
		)
	)

	if finished_part_row.scrap_weight_per_part_kg > 0:
		bom.items.append(
			BomItemRow(
				item_code=layout_doc.process_scrap_item,
				qty=finished_part_row.scrap_weight_per_part_kg,
				row_type="process_scrap",
			)
		)

	for end_piece in layout_doc.end_pieces:
		bom.items.append(
			BomItemRow(
				item_code=end_piece.end_piece_item,
				qty=end_piece_per_part_kg(
					end_piece.weight_kg,
					end_piece.qty_per_sheet,
					finished_part_row.parts_per_sheet,
				),
				row_type="end_piece_scrap",
			)
		)

	return bom


def _new_bom(item: str, document_factory: BomDocumentFactory | None) -> BomDocument:
	if document_factory is not None:
		return document_factory(item)
	return BomDocument(item=item)
