from __future__ import annotations

import importlib
import types
from dataclasses import dataclass, field
from unittest.mock import patch

import pytest

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase
from sheet_cutting_layout.tests.unittest_adapter import add_pytest_style_tests


@dataclass
class FinishedPart:
	finished_part_item: str = "FINISHED-SHR"
	parts_per_sheet: int = 4
	gross_weight_per_part_kg: float = 12.5
	scrap_weight_per_part_kg: float = 0


@dataclass
class EndPiece:
	weight_kg: float
	qty_per_sheet: float = 1
	disposition: str = "Reuse"
	scrap_item: str | None = None


@dataclass
class Layout:
	raw_material_item: str = "RAW-SHEET"
	process_scrap_item: str = "PROCESS-SCRAP"
	weight_per_sheet_kg: float = 50
	no_of_strips: int = 11
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
	assert bom.quantity == 11
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


def test_reuse_end_pieces_do_not_create_shearing_bom_scrap_rows() -> None:
	bom_service = import_bom_service()

	bom = bom_service.build_bom_from_layout_row(
		Layout(
			end_pieces=[
				EndPiece(weight_kg=3, qty_per_sheet=2),
				EndPiece(weight_kg=1.5, qty_per_sheet=4),
			]
		),
		FinishedPart(parts_per_sheet=6),
	)

	assert bom.scrap_items == []


def test_scrap_endpiece_creates_row_level_scrap_item_separate_from_process_scrap() -> None:
	bom_service = import_bom_service()

	bom = bom_service.build_bom_from_layout_row(
		Layout(
			end_pieces=[EndPiece(weight_kg=8, qty_per_sheet=2, disposition="Scrap", scrap_item="EP-SCRAP")]
		),
		FinishedPart(parts_per_sheet=4, scrap_weight_per_part_kg=1),
	)

	assert [(row.item_code, row.qty, row.row_type) for row in bom.scrap_items] == [
		("PROCESS-SCRAP", 4, "process_scrap"),
		("EP-SCRAP", 8, "end_piece_scrap"),
	]


def test_scrap_endpiece_requires_scrap_item_before_creating_bom_row() -> None:
	bom_service = import_bom_service()

	with pytest.raises(ValueError, match="Scrap end piece requires scrap_item"):
		bom_service.build_bom_from_layout_row(
			Layout(end_pieces=[EndPiece(weight_kg=8, disposition="Scrap", scrap_item=None)]),
			FinishedPart(),
		)


def test_bom_quantity_falls_back_to_parts_per_sheet_when_no_of_strips_is_zero() -> None:
	bom_service = import_bom_service()

	bom = bom_service.build_bom_from_layout_row(Layout(no_of_strips=0), FinishedPart(parts_per_sheet=4))

	assert bom.quantity == 4


def test_bom_quantity_coerces_integer_like_no_of_strips() -> None:
	bom_service = import_bom_service()

	bom = bom_service.build_bom_from_layout_row(Layout(no_of_strips="11"), FinishedPart(parts_per_sheet=4))

	assert bom.quantity == 11


@pytest.mark.parametrize("no_of_strips", ["many", 1.5, -1])
def test_bom_quantity_rejects_invalid_no_of_strips(no_of_strips: object) -> None:
	bom_service = import_bom_service()

	with pytest.raises(ValueError, match="no_of_strips must be a positive integer"):
		bom_service.build_bom_from_layout_row(
			Layout(no_of_strips=no_of_strips),
			FinishedPart(parts_per_sheet=4),
		)


def test_custom_bom_document_factory_is_used() -> None:
	bom_service = import_bom_service()

	bom = bom_service.build_bom_from_layout_row(
		Layout(),
		FinishedPart(),
		document_factory=lambda item: bom_service.BomDocument(item=item, name="CUSTOM-BOM"),
	)

	assert bom.name == "CUSTOM-BOM"


def test_resolve_scrap_item_rate_reuses_positive_existing_rate_without_lookup() -> None:
	bom_service = import_bom_service()
	with patch.object(bom_service, "_fetch_valuation_rate", return_value=99.0) as fetch_rate:
		rate = bom_service.resolve_scrap_item_rate(
			item_code="SCRAP-001",
			company="Test Company",
			existing_rate=42.5,
		)

	assert rate == pytest.approx(42.5)
	fetch_rate.assert_not_called()


def test_resolve_scrap_item_rate_looks_up_when_existing_rate_is_zero_or_invalid() -> None:
	bom_service = import_bom_service()
	with patch.object(bom_service, "_fetch_valuation_rate", return_value=88.25) as fetch_rate:
		rate_zero = bom_service.resolve_scrap_item_rate(
			item_code="SCRAP-001",
			company="Test Company",
			existing_rate=0,
		)
		rate_invalid = bom_service.resolve_scrap_item_rate(
			item_code="SCRAP-001",
			company="Test Company",
			existing_rate="not-a-number",
		)

	assert rate_zero == pytest.approx(88.25)
	assert rate_invalid == pytest.approx(88.25)
	assert fetch_rate.call_count == 2
	assert fetch_rate.call_args_list[0].kwargs == {"item_code": "SCRAP-001", "company": "Test Company"}
	assert fetch_rate.call_args_list[1].kwargs == {"item_code": "SCRAP-001", "company": "Test Company"}


class TestBomService(SheetCuttingLayoutTestCase):
	def test_bom_invariants_hold_for_representative_layouts(self) -> None:
		bom_service = import_bom_service()
		cases = [
			(
				"scrap_end_piece",
				Layout(
					weight_per_sheet_kg=50,
					no_of_strips=11,
					end_pieces=[
						EndPiece(weight_kg=2.5, disposition="Scrap", scrap_item="EP-SCRAP"),
						EndPiece(weight_kg=1.25, disposition="Reuse"),
					],
				),
				FinishedPart(
					finished_part_item="FINISHEDSHR",
					parts_per_sheet=4,
					gross_weight_per_part_kg=12.5,
					scrap_weight_per_part_kg=1.25,
				),
				11.25,
				2.5,
			),
			(
				"reuse_end_piece",
				Layout(
					weight_per_sheet_kg=50,
					no_of_strips=8,
					end_pieces=[EndPiece(weight_kg=3.75, disposition="Reuse")],
				),
				FinishedPart(
					finished_part_item="FINISHEDSHR",
					parts_per_sheet=4,
					gross_weight_per_part_kg=12.5,
					scrap_weight_per_part_kg=0.5,
				),
				12,
				0,
			),
		]
		for name, layout, finished_part, expected_derived_fg_weight_kg, expected_end_piece_scrap_qty in cases:
			with self.subTest(name=name):
				bom = bom_service.build_bom_from_layout_row(layout, finished_part)
				process_scrap_qty = self._sum_bom_qty(bom.scrap_items, "process_scrap")
				end_piece_scrap_qty = self._sum_bom_qty(bom.scrap_items, "end_piece_scrap")
				total_scrap_qty = process_scrap_qty + end_piece_scrap_qty
				derived_fg_weight_kg = (
					finished_part.gross_weight_per_part_kg - finished_part.scrap_weight_per_part_kg
				)

				self.assertEqual(bom.quantity, layout.no_of_strips)
				self.assertEqual(self._sum_bom_qty(bom.items, "raw_material"), layout.weight_per_sheet_kg)
				self.assertEqual(
					process_scrap_qty,
					finished_part.scrap_weight_per_part_kg * finished_part.parts_per_sheet,
				)
				self.assertEqual(end_piece_scrap_qty, expected_end_piece_scrap_qty)
				self.assertEqual(
					total_scrap_qty,
					finished_part.scrap_weight_per_part_kg * finished_part.parts_per_sheet
					+ expected_end_piece_scrap_qty,
				)
				self.assertEqual(derived_fg_weight_kg, expected_derived_fg_weight_kg)

	def _sum_bom_qty(self, items: list[object], row_type: str) -> float:
		return sum(item.qty for item in items if item.row_type == row_type)


add_pytest_style_tests(globals(), TestBomService)
