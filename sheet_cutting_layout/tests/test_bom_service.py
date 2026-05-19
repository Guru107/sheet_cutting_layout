from __future__ import annotations

import importlib
import types
from dataclasses import dataclass, field

import pytest


@dataclass
class FinishedPart:
	finished_part_item: str = "FINISHED-SHR"
	parts_per_sheet: int = 4
	gross_weight_per_part_kg: float = 12.5
	scrap_weight_per_part_kg: float = 0


@dataclass
class EndPiece:
	end_piece_item: str
	weight_kg: float
	qty_per_sheet: float
	disposition: str = "Reuse"


@dataclass
class Layout:
	raw_material_item: str = "RAW-SHEET"
	process_scrap_item: str = "PROCESS-SCRAP"
	weight_per_sheet_kg: float = 50
	end_pieces: list[EndPiece] = field(default_factory=list)


def import_bom_service() -> types.ModuleType:
	try:
		return importlib.import_module("sheet_cutting_layout.services.bom_service")
	except ModuleNotFoundError as error:
		pytest.fail(f"BOM service module is not implemented: {error}")


def test_generated_bom_uses_parts_per_sheet_quantity_and_sheet_weight_raw_qty() -> None:
	bom_service = import_bom_service()

	bom = bom_service.build_bom_from_layout_row(Layout(), FinishedPart())

	assert bom.item == "FINISHED-SHR"
	assert bom.quantity == 4
	assert bom.items[0].item_code == "RAW-SHEET"
	assert bom.items[0].qty == pytest.approx(50)
	assert bom.items[0].uom == "Kg"
	assert bom.items[0].row_type == "raw_material"


def test_process_scrap_row_is_included_when_scrap_weight_is_positive() -> None:
	bom_service = import_bom_service()

	bom = bom_service.build_bom_from_layout_row(
		Layout(),
		FinishedPart(scrap_weight_per_part_kg=1.25),
	)

	assert bom.scrap_items[0].item_code == "PROCESS-SCRAP"
	assert bom.scrap_items[0].qty == pytest.approx(5)
	assert bom.scrap_items[0].uom == "Kg"
	assert bom.scrap_items[0].row_type == "process_scrap"


def test_reusable_end_piece_scrap_rows_use_total_sheet_weight() -> None:
	bom_service = import_bom_service()

	bom = bom_service.build_bom_from_layout_row(
		Layout(
			end_pieces=[
				EndPiece("EP-1", weight_kg=3, qty_per_sheet=2),
				EndPiece("EP-2", weight_kg=1.5, qty_per_sheet=4),
			]
		),
		FinishedPart(parts_per_sheet=6),
	)

	assert bom.scrap_items[0].item_code == "EP-1"
	assert bom.scrap_items[0].qty == pytest.approx(6)
	assert bom.scrap_items[0].uom == "Kg"
	assert bom.scrap_items[0].row_type == "end_piece_scrap"
	assert bom.scrap_items[1].item_code == "EP-2"
	assert bom.scrap_items[1].qty == pytest.approx(6)
	assert bom.scrap_items[1].uom == "Kg"
	assert bom.scrap_items[1].row_type == "end_piece_scrap"


def test_scrap_endpiece_weight_is_folded_into_process_scrap_total() -> None:
	bom_service = import_bom_service()

	bom = bom_service.build_bom_from_layout_row(
		Layout(end_pieces=[EndPiece("EP-SCRAP", weight_kg=8, qty_per_sheet=1, disposition="Scrap")]),
		FinishedPart(parts_per_sheet=4, scrap_weight_per_part_kg=1),
	)

	assert [(row.item_code, row.qty, row.row_type) for row in bom.scrap_items] == [
		("PROCESS-SCRAP", 12, "process_scrap")
	]


def test_parts_per_sheet_must_be_positive_for_end_piece_distribution() -> None:
	bom_service = import_bom_service()

	with pytest.raises(bom_service.ValidationError, match="Parts per sheet"):
		bom_service.end_piece_per_part_kg(ep_weight_kg=3, qty_per_sheet=2, parts_per_sheet=0)


def test_custom_bom_document_factory_is_used() -> None:
	bom_service = import_bom_service()

	bom = bom_service.build_bom_from_layout_row(
		Layout(),
		FinishedPart(),
		document_factory=lambda item: bom_service.BomDocument(item=item, name="CUSTOM-BOM"),
	)

	assert bom.name == "CUSTOM-BOM"
