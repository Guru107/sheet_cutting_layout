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


@dataclass
class Layout:
	raw_material_item: str = "RAW-SHEET"
	process_scrap_item: str = "PROCESS-SCRAP"
	end_pieces: list[EndPiece] = field(default_factory=list)


def import_bom_service() -> types.ModuleType:
	try:
		return importlib.import_module("sheet_cutting_layout.services.bom_service")
	except ModuleNotFoundError as error:
		pytest.fail(f"BOM service module is not implemented: {error}")


def test_generated_bom_uses_quantity_one_and_gross_as_raw_qty() -> None:
	bom_service = import_bom_service()

	bom = bom_service.build_bom_from_layout_row(Layout(), FinishedPart())

	assert bom.item == "FINISHED-SHR"
	assert bom.quantity == 1
	assert bom.items[0].item_code == "RAW-SHEET"
	assert bom.items[0].qty == pytest.approx(12.5)
	assert bom.items[0].uom == "Kg"
	assert bom.items[0].row_type == "raw_material"


def test_process_scrap_row_is_included_when_scrap_weight_is_positive() -> None:
	bom_service = import_bom_service()

	bom = bom_service.build_bom_from_layout_row(
		Layout(),
		FinishedPart(scrap_weight_per_part_kg=1.25),
	)

	assert bom.items[1].item_code == "PROCESS-SCRAP"
	assert bom.items[1].qty == pytest.approx(1.25)
	assert bom.items[1].uom == "Kg"
	assert bom.items[1].row_type == "process_scrap"


def test_distributed_end_piece_scrap_rows_use_approved_formula() -> None:
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

	assert bom.items[1].item_code == "EP-1"
	assert bom.items[1].qty == pytest.approx(1)
	assert bom.items[1].uom == "Kg"
	assert bom.items[1].row_type == "end_piece_scrap"
	assert bom.items[2].item_code == "EP-2"
	assert bom.items[2].qty == pytest.approx(1)
	assert bom.items[2].uom == "Kg"
	assert bom.items[2].row_type == "end_piece_scrap"


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
