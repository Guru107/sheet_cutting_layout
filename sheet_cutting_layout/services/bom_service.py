from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from sheet_cutting_layout.services.end_piece_item_service import derive_end_piece_item_code_from_row


class FinishedPartRow(Protocol):
	finished_part_item: str
	parts_per_sheet: int
	gross_weight_per_part_kg: float
	scrap_weight_per_part_kg: float
	orientation: str | None


class EndPieceRow(Protocol):
	weight_kg: float
	strip_weight_kg: float | None
	disposition: str
	scrap_item: str | None
	end_piece_item_code: str | None
	used_for_finished_part: str | None
	width_mm: float | None
	length_mm: float | None


class LayoutDocument(Protocol):
	raw_material_item: str
	process_scrap_item: str
	weight_per_sheet_kg: float
	no_of_strips: int
	finished_part_code: str | None
	is_lh_rh: int | bool | None
	orientation: str | None
	twin_finished_part: str | None
	parts_per_sheet: int
	gross_weight_per_part_kg: float
	scrap_weight_per_part_kg: float
	sheet_thickness_mm: float | None
	end_pieces: Sequence[EndPieceRow]


BomItemRowType = Literal["raw_material", "process_scrap", "end_piece_scrap", "end_piece_byproduct"]


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
	items: list[BomItemRow] = field(default_factory=list)
	scrap_items: list[BomItemRow] = field(default_factory=list)


@dataclass
class ParentFinishedPartRow:
	finished_part_item: str
	parts_per_sheet: int
	gross_weight_per_part_kg: float
	scrap_weight_per_part_kg: float
	orientation: str | None = None


@dataclass
class ExpectedBomWeightBalance:
	raw_material_weight_kg: float
	finished_part_weight_kg: float
	scrap_and_byproduct_weight_kg: float
	difference_kg: float


BomDocumentFactory = Callable[[str], BomDocument]
EndPieceItemCodeResolver = Callable[[LayoutDocument, EndPieceRow, FinishedPartRow], str]


def build_weight_split_bom_rows(
	*,
	raw_material_item: str,
	raw_material_qty_kg: float,
	scrap_qty_kg: float,
	scrap_item: str | None,
	scrap_row_type: BomItemRowType,
) -> BomWeightRows:
	rows = BomWeightRows(
		items=[
			BomItemRow(
				item_code=raw_material_item,
				qty=raw_material_qty_kg,
				row_type="raw_material",
			)
		]
	)
	if scrap_qty_kg > 0:
		rows.scrap_items.append(
			BomItemRow(
				item_code=scrap_item,
				qty=scrap_qty_kg,
				row_type=scrap_row_type,
			)
		)
	return rows


def build_bom_from_layout_row(
	layout_doc: LayoutDocument,
	finished_part_row: FinishedPartRow,
	*,
	document_factory: BomDocumentFactory | None = None,
	end_piece_item_code_resolver: EndPieceItemCodeResolver | None = None,
) -> BomDocument:
	bom = _new_bom(finished_part_row.finished_part_item, document_factory)
	bom.quantity = _bom_quantity(layout_doc, finished_part_row)

	weight_rows = build_weight_split_bom_rows(
		raw_material_item=layout_doc.raw_material_item,
		raw_material_qty_kg=_sheet_weight_kg(layout_doc, finished_part_row),
		scrap_qty_kg=finished_part_row.scrap_weight_per_part_kg * finished_part_row.parts_per_sheet,
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
			continue
		if _is_reuse_end_piece(end_piece):
			item_code = _end_piece_byproduct_item_code(
				layout_doc,
				finished_part_row,
				end_piece,
				end_piece_item_code_resolver,
			)
			bom.scrap_items.append(
				BomItemRow(
					item_code=item_code,
					qty=_end_piece_bom_qty_kg(end_piece),
					row_type="end_piece_byproduct",
				)
			)

	return bom


def build_bom_from_layout(
	layout_doc: LayoutDocument,
	*,
	document_factory: BomDocumentFactory | None = None,
	end_piece_item_code_resolver: EndPieceItemCodeResolver | None = None,
) -> BomDocument:
	return build_bom_from_layout_row(
		layout_doc,
		parent_finished_part_row(layout_doc),
		document_factory=document_factory,
		end_piece_item_code_resolver=end_piece_item_code_resolver,
	)


def expected_main_bom_weight_balance(layout_doc: LayoutDocument) -> ExpectedBomWeightBalance:
	finished_part = parent_finished_part_row(layout_doc)
	bom = build_bom_from_layout_row(layout_doc, finished_part)
	raw_material_weight = sum(row.qty for row in bom.items)
	scrap_and_byproduct_weight = sum(row.qty for row in bom.scrap_items)
	net_weight_per_part = finished_part.gross_weight_per_part_kg - finished_part.scrap_weight_per_part_kg
	finished_part_weight = net_weight_per_part * finished_part.parts_per_sheet
	difference = raw_material_weight - finished_part_weight - scrap_and_byproduct_weight
	return ExpectedBomWeightBalance(
		raw_material_weight_kg=raw_material_weight,
		finished_part_weight_kg=finished_part_weight,
		scrap_and_byproduct_weight_kg=scrap_and_byproduct_weight,
		difference_kg=difference,
	)


def parent_finished_part_row(layout_doc: LayoutDocument) -> ParentFinishedPartRow:
	finished_part_item = str(getattr(layout_doc, "finished_part_code", "") or "").strip()
	if not finished_part_item:
		raise ValueError("finished_part_code is required to create generated BOM")
	return ParentFinishedPartRow(
		finished_part_item=finished_part_item,
		parts_per_sheet=int(getattr(layout_doc, "parts_per_sheet", 0) or 0),
		gross_weight_per_part_kg=float(getattr(layout_doc, "gross_weight_per_part_kg", 0) or 0),
		scrap_weight_per_part_kg=float(getattr(layout_doc, "scrap_weight_per_part_kg", 0) or 0),
		orientation=_parent_orientation(layout_doc),
	)


def twin_finished_part_row(layout_doc: LayoutDocument) -> ParentFinishedPartRow:
	primary = parent_finished_part_row(layout_doc)
	twin_item = str(getattr(layout_doc, "twin_finished_part", "") or "").strip()
	if not twin_item:
		raise ValueError("twin_finished_part is required to create the LH/RH twin BOM")
	return ParentFinishedPartRow(
		finished_part_item=twin_item,
		parts_per_sheet=primary.parts_per_sheet,
		gross_weight_per_part_kg=primary.gross_weight_per_part_kg,
		scrap_weight_per_part_kg=primary.scrap_weight_per_part_kg,
		orientation=_opposite_orientation(primary.orientation),
	)


def _parent_orientation(layout_doc: LayoutDocument) -> str | None:
	if not getattr(layout_doc, "is_lh_rh", None):
		return None
	orientation = str(getattr(layout_doc, "orientation", "") or "").strip().upper()
	return orientation or None


def _opposite_orientation(orientation: str | None) -> str | None:
	if orientation == "LH":
		return "RH"
	if orientation == "RH":
		return "LH"
	return None


def _new_bom(item: str, document_factory: BomDocumentFactory | None) -> BomDocument:
	if document_factory is not None:
		return document_factory(item)
	return BomDocument(item=item)


def _is_scrap_end_piece(end_piece: EndPieceRow) -> bool:
	return str(getattr(end_piece, "disposition", "") or "").strip().lower() == "scrap"


def _is_reuse_end_piece(end_piece: EndPieceRow) -> bool:
	return str(getattr(end_piece, "disposition", "") or "").strip().lower() == "reuse"


def _end_piece_bom_qty_kg(end_piece: EndPieceRow) -> float:
	if _is_reuse_end_piece(end_piece):
		return float(getattr(end_piece, "strip_weight_kg", 0) or 0)
	return float(getattr(end_piece, "weight_kg", 0) or 0)


def _end_piece_byproduct_item_code(
	layout_doc: LayoutDocument,
	finished_part_row: FinishedPartRow,
	end_piece: EndPieceRow,
	end_piece_item_code_resolver: EndPieceItemCodeResolver | None,
) -> str:
	existing_item_code = str(getattr(end_piece, "end_piece_item_code", "") or "").strip()
	if existing_item_code:
		return existing_item_code
	if end_piece_item_code_resolver is not None:
		resolved_item_code = str(
			end_piece_item_code_resolver(layout_doc, end_piece, finished_part_row) or ""
		).strip()
		if not resolved_item_code:
			raise ValueError(
				"Reusable end piece requires generated item code before creating BOM byproduct row"
			)
		return resolved_item_code
	return derive_end_piece_item_code_from_row(
		layout_doc,
		end_piece,
		source_finished_part=finished_part_row.finished_part_item,
	)


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

	end_piece_weight = sum(_end_piece_bom_qty_kg(end_piece) for end_piece in layout_doc.end_pieces)
	return finished_part_row.gross_weight_per_part_kg * finished_part_row.parts_per_sheet + end_piece_weight
