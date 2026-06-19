from __future__ import annotations

from types import SimpleNamespace

from sheet_cutting_layout.services.bom_service import (
	ParentFinishedPartRow,
	parent_finished_part_row,
	twin_finished_part_row,
)
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


def _layout(**overrides: object) -> SimpleNamespace:
	defaults = dict(
		finished_part_code="BRKT-LH-SHR",
		parts_per_sheet=4,
		gross_weight_per_part_kg=3.5,
		scrap_weight_per_part_kg=0.5,
		is_lh_rh=0,
		orientation=None,
		twin_finished_part=None,
	)
	defaults.update(overrides)
	return SimpleNamespace(**defaults)


class TestLhRhExpansion(SheetCuttingLayoutTestCase):
	def test_parent_row_defaults_orientation_to_none(self) -> None:
		row = parent_finished_part_row(_layout(orientation="LH"))

		self.assertEqual(row.finished_part_item, "BRKT-LH-SHR")
		self.assertIsNone(row.orientation)
		self.assertIsInstance(row, ParentFinishedPartRow)

	def test_parent_row_carries_layout_orientation_when_lh_rh(self) -> None:
		row = parent_finished_part_row(_layout(is_lh_rh=1, orientation="LH"))

		self.assertEqual(row.orientation, "LH")

	def test_twin_row_inherits_primary_quantities_with_opposite_orientation(self) -> None:
		layout = _layout(is_lh_rh=1, orientation="LH", twin_finished_part="BRKT-RH-SHR")
		primary = parent_finished_part_row(layout)
		twin = twin_finished_part_row(layout)

		self.assertEqual(twin.finished_part_item, "BRKT-RH-SHR")
		self.assertEqual(twin.parts_per_sheet, primary.parts_per_sheet)
		self.assertEqual(twin.gross_weight_per_part_kg, primary.gross_weight_per_part_kg)
		self.assertEqual(twin.scrap_weight_per_part_kg, primary.scrap_weight_per_part_kg)
		self.assertEqual(twin.orientation, "RH")

	def test_twin_row_orientation_is_lh_when_primary_is_rh(self) -> None:
		layout = _layout(is_lh_rh=1, orientation="RH", twin_finished_part="BRKT-LH-SHR")

		self.assertEqual(twin_finished_part_row(layout).orientation, "LH")

	def test_twin_row_requires_twin_finished_part(self) -> None:
		layout = _layout(is_lh_rh=1, orientation="LH", twin_finished_part="")

		with self.assertRaisesRegex(ValueError, "twin_finished_part"):
			twin_finished_part_row(layout)
