from __future__ import annotations

from dataclasses import dataclass, field

from sheet_cutting_layout.services import bom_service
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


@dataclass
class FinishedPart:
	finished_part_item: str = "FINISHED-SHR"
	parts_per_sheet: int = 4
	gross_weight_per_part_kg: float = 12.5
	scrap_weight_per_part_kg: float = 0


@dataclass
class EndPiece:
	weight_kg: float
	disposition: str = "Reuse"
	scrap_item: str | None = None
	end_piece_item_code: str | None = None
	used_for_finished_part: str | None = "FG002SHR"
	width_mm: float | None = 1250
	length_mm: float | None = 179
	strip_weight_kg: float | None = None

	def __post_init__(self) -> None:
		if self.disposition == "Reuse" and self.strip_weight_kg is None:
			self.strip_weight_kg = self.weight_kg


@dataclass
class Layout:
	raw_material_item: str = "RAW-SHEET"
	process_scrap_item: str = "PROCESS-SCRAP"
	weight_per_sheet_kg: float = 50
	no_of_strips: int = 11
	finished_part_code: str = "FINISHED-SHR"
	net_weight_per_part_kg: float = 12.5
	gross_weight_per_part_kg: float = 12.5
	scrap_weight_per_part_kg: float = 0
	parts_per_sheet: int = 4
	sheet_thickness_mm: float | None = 1.6
	is_lh_rh: int = 0
	twin_finished_part: str | None = None
	end_pieces: list[EndPiece] = field(default_factory=list)


class TestBomService(SheetCuttingLayoutTestCase):
	def test_bom_document_has_no_status_or_disabled_fields(self) -> None:
		bom = bom_service.BomDocument(item="FINISHED-SHR")

		self.assertFalse(hasattr(bom, "status"))
		self.assertFalse(hasattr(bom, "disabled"))

	def test_generated_bom_uses_parts_per_sheet_quantity_and_sheet_weight_raw_qty(self) -> None:
		bom = bom_service.build_bom_from_layout_row(
			Layout(no_of_strips=11, parts_per_sheet=77),
			FinishedPart(parts_per_sheet=77),
		)

		assert bom.item == "FINISHED-SHR"
		assert bom.quantity == 77
		assert bom.items[0].item_code == "RAW-SHEET"
		self.assertFloatAlmostEqual(bom.items[0].qty, 50)
		assert bom.items[0].uom == "Kg"
		assert bom.items[0].row_type == "raw_material"

	def test_process_scrap_row_is_included_when_scrap_weight_is_positive(self) -> None:
		bom = bom_service.build_bom_from_layout_row(
			Layout(),
			FinishedPart(scrap_weight_per_part_kg=1.25),
		)

		assert bom.scrap_items[0].item_code == "PROCESS-SCRAP"
		self.assertFloatAlmostEqual(bom.scrap_items[0].qty, 5)
		assert bom.scrap_items[0].uom == "Kg"
		assert bom.scrap_items[0].row_type == "process_scrap"

	def test_process_scrap_and_reuse_end_piece_byproduct_rows_are_both_included(self) -> None:
		bom = bom_service.build_bom_from_layout_row(
			Layout(
				process_scrap_item="MSScrap",
				sheet_thickness_mm=1.6,
				end_pieces=[EndPiece(weight_kg=2.81388, used_for_finished_part="FG002SHR")],
			),
			FinishedPart(parts_per_sheet=77, scrap_weight_per_part_kg=0.184846),
		)

		assert [(row.item_code, row.qty, row.row_type) for row in bom.scrap_items] == [
			("MSScrap", 14.233142, "process_scrap"),
			("FINISHED-SHR-EP-1.6x1250x179", 2.81388, "end_piece_byproduct"),
		]

	def test_reuse_end_pieces_create_main_bom_byproduct_rows(self) -> None:
		bom = bom_service.build_bom_from_layout_row(
			Layout(
				sheet_thickness_mm=1.6,
				end_pieces=[
					EndPiece(weight_kg=2.81388, used_for_finished_part="FG002SHR"),
				],
			),
			FinishedPart(parts_per_sheet=77),
		)

		assert [(row.item_code, row.qty, row.uom, row.row_type) for row in bom.scrap_items] == [
			("FINISHED-SHR-EP-1.6x1250x179", 2.81388, "Kg", "end_piece_byproduct"),
		]

	def test_reuse_end_piece_byproduct_uses_strip_weight(self) -> None:
		bom = bom_service.build_bom_from_layout_row(
			Layout(
				sheet_thickness_mm=1.6,
				end_pieces=[
					EndPiece(weight_kg=5, strip_weight_kg=3, used_for_finished_part="FG002SHR"),
				],
			),
			FinishedPart(parts_per_sheet=77),
		)

		assert [(row.item_code, row.qty, row.uom, row.row_type) for row in bom.scrap_items] == [
			("FINISHED-SHR-EP-1.6x1250x179", 3, "Kg", "end_piece_byproduct"),
		]

	def test_lh_rh_bom_uses_primary_and_twin_for_end_piece_byproduct_code(self) -> None:
		bom = bom_service.build_bom_from_layout_row(
			Layout(
				finished_part_code="BRKT-LH-SHR",
				sheet_thickness_mm=1.6,
				is_lh_rh=1,
				twin_finished_part="BRKT-RH-SHR",
				end_pieces=[
					EndPiece(weight_kg=2.81388, used_for_finished_part="FG002SHR"),
				],
			),
			FinishedPart(finished_part_item="BRKT-RH-SHR", parts_per_sheet=77),
		)

		assert [(row.item_code, row.qty, row.uom, row.row_type) for row in bom.scrap_items] == [
			("BRKT-LH-SHR-BRKT-RH-SHR-EP-1.6x1250x179", 2.81388, "Kg", "end_piece_byproduct"),
		]

	def test_existing_reuse_end_piece_item_code_wins_over_resolver(self) -> None:
		def fail_resolver(_layout: object, _row: object, _finished_part: object) -> str:
			raise AssertionError("resolver should not run when row is already linked")

		bom = bom_service.build_bom_from_layout_row(
			Layout(end_pieces=[EndPiece(weight_kg=2.5, end_piece_item_code=" LINKED-EP ")]),
			FinishedPart(),
			end_piece_item_code_resolver=fail_resolver,
		)

		assert [(row.item_code, row.qty, row.row_type) for row in bom.scrap_items] == [
			("LINKED-EP", 2.5, "end_piece_byproduct"),
		]

	def test_reuse_end_piece_resolver_runs_before_pure_derivation(self) -> None:
		def resolver(_layout: object, _row: object, _finished_part: object) -> str:
			return "RESOLVED-EP"

		bom = bom_service.build_bom_from_layout_row(
			Layout(sheet_thickness_mm=None, end_pieces=[EndPiece(weight_kg=2.5)]),
			FinishedPart(),
			end_piece_item_code_resolver=resolver,
		)

		assert [(row.item_code, row.qty, row.row_type) for row in bom.scrap_items] == [
			("RESOLVED-EP", 2.5, "end_piece_byproduct"),
		]

	def test_reuse_end_piece_resolver_must_return_item_code(self) -> None:
		for resolver_result in ("   ", None):
			created_boms = []

			def capture_bom(item: str) -> object:
				bom = bom_service.BomDocument(item=item)
				created_boms.append(bom)
				return bom

			with self.assertRaisesRegex(ValueError, "Reusable end piece requires generated item code"):
				bom_service.build_bom_from_layout_row(
					Layout(end_pieces=[EndPiece(weight_kg=2.5)]),
					FinishedPart(),
					document_factory=capture_bom,
					end_piece_item_code_resolver=lambda _layout, _row, _finished_part: resolver_result,
				)

			assert created_boms[0].scrap_items == []

	def test_scrap_endpiece_creates_row_level_scrap_item_separate_from_process_scrap(self) -> None:
		bom = bom_service.build_bom_from_layout_row(
			Layout(
				no_of_strips=11,
				parts_per_sheet=77,
				end_pieces=[EndPiece(weight_kg=8, disposition="Scrap", scrap_item="EP-SCRAP")],
			),
			FinishedPart(parts_per_sheet=77, scrap_weight_per_part_kg=1),
		)

		assert [(row.item_code, row.qty, row.row_type) for row in bom.scrap_items] == [
			("PROCESS-SCRAP", 77, "process_scrap"),
			("EP-SCRAP", 8, "end_piece_scrap"),
		]

	def test_scrap_endpiece_requires_scrap_item_before_creating_bom_row(self) -> None:
		with self.assertRaisesRegex(ValueError, "Scrap end piece requires scrap_item"):
			bom_service.build_bom_from_layout_row(
				Layout(end_pieces=[EndPiece(weight_kg=8, disposition="Scrap", scrap_item=None)]),
				FinishedPart(),
			)

	def test_bom_quantity_ignores_no_of_strips_when_parts_per_sheet_is_available(self) -> None:
		bom = bom_service.build_bom_from_layout_row(
			Layout(no_of_strips="11", parts_per_sheet=77),
			FinishedPart(parts_per_sheet=77),
		)

		assert bom.quantity == 77

	def test_custom_bom_document_factory_is_used(self) -> None:
		bom = bom_service.build_bom_from_layout_row(
			Layout(),
			FinishedPart(),
			document_factory=lambda item: bom_service.BomDocument(item=item, name="CUSTOM-BOM"),
		)

		assert bom.name == "CUSTOM-BOM"

	def test_weight_split_helper_matches_main_bom_raw_and_scrap_rows(self) -> None:
		from sheet_cutting_layout.services.bom_service import build_weight_split_bom_rows

		rows = build_weight_split_bom_rows(
			raw_material_item="RAW-001",
			raw_material_qty_kg=12.0,
			scrap_qty_kg=2.25,
			scrap_item="EP-SCRAP",
			scrap_row_type="process_scrap",
		)

		assert [(row.item_code, row.qty, row.row_type) for row in rows.items] == [
			("RAW-001", 12.0, "raw_material")
		]
		assert [(row.item_code, row.qty, row.row_type) for row in rows.scrap_items] == [
			("EP-SCRAP", 2.25, "process_scrap")
		]

	def test_weight_split_helper_skips_scrap_row_when_scrap_quantity_is_zero(self) -> None:
		from sheet_cutting_layout.services.bom_service import build_weight_split_bom_rows

		rows = build_weight_split_bom_rows(
			raw_material_item="RAW-001",
			raw_material_qty_kg=12.0,
			scrap_qty_kg=0,
			scrap_item=None,
			scrap_row_type="process_scrap",
		)

		assert [(row.item_code, row.qty, row.row_type) for row in rows.items] == [
			("RAW-001", 12.0, "raw_material")
		]
		assert rows.scrap_items == []

	def test_main_bom_is_derived_from_parent_finished_part_fields(self) -> None:
		layout = Layout(
			raw_material_item="RM001",
			process_scrap_item="PROCESS-SCRAP",
			finished_part_code="FG01SHR",
			net_weight_per_part_kg=0.289,
			parts_per_sheet=77,
			no_of_strips=11,
			weight_per_sheet_kg=39.3,
			gross_weight_per_part_kg=0.473846,
			scrap_weight_per_part_kg=0.184846,
		)

		bom = bom_service.build_bom_from_layout(layout)

		self.assertEqual(bom.item, "FG01SHR")
		self.assertEqual(bom.quantity, 77)
		self.assertAlmostEqual(self._sum_bom_qty(bom.items, "raw_material"), 39.3, places=6)
		self.assertAlmostEqual(self._sum_bom_qty(bom.scrap_items, "process_scrap"), 14.233142, places=6)

	def test_main_bom_uses_exact_sheet_weight_raw_quantity(self) -> None:
		layout = Layout(
			weight_per_sheet_kg=123.456789,
			parts_per_sheet=3,
			gross_weight_per_part_kg=41.152263,
		)

		bom = bom_service.build_bom_from_layout_row(
			layout,
			FinishedPart(parts_per_sheet=3, gross_weight_per_part_kg=41.152263),
		)

		self.assertEqual(bom.items[0].qty, layout.weight_per_sheet_kg)

	def test_main_bom_includes_reuse_end_piece_byproduct_rows(self) -> None:
		layout = Layout(
			raw_material_item="RM001",
			process_scrap_item="PROCESS-SCRAP",
			finished_part_code="FG01SHR",
			parts_per_sheet=77,
			no_of_strips=11,
			weight_per_sheet_kg=39.3,
			gross_weight_per_part_kg=0.473846,
			scrap_weight_per_part_kg=0.184846,
			end_pieces=[
				EndPiece(
					weight_kg=2.81388,
					used_for_finished_part="FG002SHR",
					width_mm=1250,
					length_mm=179,
				)
			],
		)

		bom = bom_service.build_bom_from_layout(layout)

		self.assertEqual(bom.item, "FG01SHR")
		self.assertEqual(bom.quantity, 77)
		self.assertEqual(
			[(row.item_code, row.qty, row.row_type) for row in bom.items],
			[("RM001", 39.3, "raw_material")],
		)
		self.assertEqual(
			[(row.item_code, row.qty, row.row_type) for row in bom.scrap_items],
			[
				("PROCESS-SCRAP", 14.233142, "process_scrap"),
				("FG01SHR-EP-1.6x1250x179", 2.81388, "end_piece_byproduct"),
			],
		)

	def test_expected_main_bom_weight_balance_includes_reuse_end_piece_byproducts(self) -> None:
		layout = Layout(
			raw_material_item="RM001",
			process_scrap_item="MSScrap",
			finished_part_code="FG01SHR",
			net_weight_per_part_kg=0.289,
			parts_per_sheet=77,
			no_of_strips=11,
			weight_per_sheet_kg=39.3,
			gross_weight_per_part_kg=0.473846,
			scrap_weight_per_part_kg=0.184846,
			sheet_thickness_mm=1.6,
			end_pieces=[
				EndPiece(
					weight_kg=2.81388,
					used_for_finished_part="FG002SHR",
					width_mm=1250,
					length_mm=179,
				)
			],
		)

		balance = bom_service.expected_main_bom_weight_balance(layout)

		self.assertAlmostEqual(balance.raw_material_weight_kg, 39.3, places=6)
		self.assertAlmostEqual(balance.finished_part_weight_kg, 22.253, places=6)
		self.assertAlmostEqual(balance.scrap_and_byproduct_weight_kg, 17.047022, places=6)
		self.assertAlmostEqual(balance.difference_kg, -0.000022, places=6)

	def test_bom_invariants_hold_for_representative_layouts(self) -> None:
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
				2.5,
				1.25,
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
				0,
				3.75,
			),
		]
		for (
			name,
			layout,
			finished_part,
			expected_end_piece_scrap_qty,
			expected_end_piece_byproduct_qty,
		) in cases:
			with self.subTest(name=name):
				bom = bom_service.build_bom_from_layout_row(layout, finished_part)
				process_scrap_qty = self._sum_bom_qty(bom.scrap_items, "process_scrap")
				end_piece_scrap_qty = self._sum_bom_qty(bom.scrap_items, "end_piece_scrap")
				end_piece_byproduct_qty = self._sum_bom_qty(bom.scrap_items, "end_piece_byproduct")

				self.assertEqual(bom.quantity, finished_part.parts_per_sheet)
				self.assertEqual(self._sum_bom_qty(bom.items, "raw_material"), layout.weight_per_sheet_kg)
				self.assertEqual(
					process_scrap_qty,
					finished_part.scrap_weight_per_part_kg * finished_part.parts_per_sheet,
				)
				self.assertEqual(end_piece_scrap_qty, expected_end_piece_scrap_qty)
				self.assertEqual(end_piece_byproduct_qty, expected_end_piece_byproduct_qty)

	def _sum_bom_qty(self, items: list[object], row_type: str) -> float:
		return sum(item.qty for item in items if item.row_type == row_type)
