from __future__ import annotations

from types import SimpleNamespace

import frappe

from sheet_cutting_layout.services.release_service import _parent_finished_part_rows
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase
from sheet_cutting_layout.tests.factories import ensure_item, make_release_ready_layout


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


class TestLhRhSchema(SheetCuttingLayoutTestCase):
	def test_parent_lh_rh_fields_exist(self) -> None:
		meta = frappe.get_meta("Sheet Cutting Layout")
		self.assertEqual(meta.get_field("is_lh_rh").fieldtype, "Check")
		self.assertEqual(meta.get_field("orientation").options, "\nLH\nRH")
		self.assertEqual(meta.get_field("twin_finished_part").options, "Item")

	def test_finished_part_orientation_field_exists(self) -> None:
		field = frappe.get_meta("Layout Finished Part").get_field("orientation")
		self.assertEqual(field.fieldtype, "Select")
		self.assertEqual(field.options, "\nLH\nRH")


class TestParentFinishedPartRows(SheetCuttingLayoutTestCase):
	def test_non_lh_rh_layout_returns_single_primary_row(self) -> None:
		rows = _parent_finished_part_rows(_layout())

		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].finished_part_item, "BRKT-LH-SHR")
		self.assertIsNone(rows[0].orientation)

	def test_lh_rh_layout_returns_primary_then_twin(self) -> None:
		rows = _parent_finished_part_rows(
			_layout(is_lh_rh=1, orientation="LH", twin_finished_part="BRKT-RH-SHR")
		)

		self.assertEqual([row.finished_part_item for row in rows], ["BRKT-LH-SHR", "BRKT-RH-SHR"])
		self.assertEqual([row.orientation for row in rows], ["LH", "RH"])

	def test_twin_row_inherits_primary_quantities(self) -> None:
		rows = _parent_finished_part_rows(
			_layout(is_lh_rh=1, orientation="RH", twin_finished_part="BRKT-LH-SHR")
		)
		primary, twin = rows

		self.assertEqual(twin.parts_per_sheet, primary.parts_per_sheet)
		self.assertEqual(twin.gross_weight_per_part_kg, primary.gross_weight_per_part_kg)
		self.assertEqual(twin.scrap_weight_per_part_kg, primary.scrap_weight_per_part_kg)
		self.assertEqual([primary.orientation, twin.orientation], ["RH", "LH"])

	def test_blank_finished_part_code_returns_empty(self) -> None:
		self.assertEqual(_parent_finished_part_rows(_layout(finished_part_code="")), [])


class TestLhRhReleaseIntegration(SheetCuttingLayoutTestCase):
	def test_lh_rh_release_creates_two_boms_and_mirror_rows(self) -> None:
		twin_item = ensure_item("SCLTESTFGTWINSHR", stock_uom="Nos")
		layout = make_release_ready_layout(
			is_lh_rh=1,
			orientation="LH",
			twin_finished_part=twin_item,
		)

		layout.status = "Released"
		layout.submit()
		layout.reload()

		self.assertEqual(layout.status, "Released")
		self.assertEqual(len(layout.finished_parts), 2)
		self.assertEqual([row.orientation for row in layout.finished_parts], ["LH", "RH"])
		self.assertEqual(layout.finished_parts[1].finished_part_item, twin_item)
		bom_names = [row.generated_bom for row in layout.finished_parts]
		self.assertEqual(len(set(bom_names)), 2)
		self.assertTrue(all(bom_names))
		self.assertEqual(layout.generated_bom, bom_names[0])

		layout.status = "Superseded"
		layout.cancel()
		for bom_name in bom_names:
			self.assertEqual(frappe.db.get_value("BOM", bom_name, "is_active"), 0)
