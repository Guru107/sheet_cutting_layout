from __future__ import annotations

from types import SimpleNamespace

import frappe

from sheet_cutting_layout.services.validators import validate_sheet_cutting_layout
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


def _layout(**overrides: object) -> SimpleNamespace:
	values = {
		"finished_part_code": "SCLTESTFG001SHR",
		"twin_finished_part": "SCLTESTFG002SHR",
		"is_lh_rh": 1,
		"orientation": "LH",
		"raw_material_item": "SCLTESTRM001",
		"process_scrap_item": None,
		"sheet_thickness_mm": 1,
		"sheet_width_mm": 1250,
		"sheet_length_mm": 2500,
		"strip_thickness_mm": 1,
		"strip_width_mm": 1250,
		"strip_length_mm": 2500,
		"weight_of_strip_kg": None,
		"weight_per_sheet_kg": None,
		"parts_per_strip": 1,
		"no_of_strips": 1,
		"parts_per_sheet": None,
		"gross_weight_per_part_kg": None,
		"net_weight_per_part_kg": 24.5625,
		"scrap_weight_per_part_kg": None,
		"generated_bom": None,
		"end_piece_bom_status": None,
		"consumed_weight_kg": None,
		"leftover_weight_kg": None,
		"consumption_status": None,
		"end_pieces": [],
	}
	values.update(overrides)
	return SimpleNamespace(**values)


class TestLhRhValidation(SheetCuttingLayoutTestCase):
	def test_lh_rh_requires_orientation(self) -> None:
		with self.assertRaisesRegex(frappe.ValidationError, "Primary orientation"):
			validate_sheet_cutting_layout(_layout(orientation=None))

	def test_lh_rh_requires_twin_finished_part(self) -> None:
		with self.assertRaisesRegex(frappe.ValidationError, "Twin finished part"):
			validate_sheet_cutting_layout(_layout(twin_finished_part=""))

	def test_lh_rh_rejects_primary_as_twin(self) -> None:
		with self.assertRaisesRegex(frappe.ValidationError, "cannot match"):
			validate_sheet_cutting_layout(_layout(twin_finished_part="SCLTESTFG001SHR"))

	def test_lh_rh_rejects_raw_material_as_twin(self) -> None:
		with self.assertRaisesRegex(frappe.ValidationError, "raw material"):
			validate_sheet_cutting_layout(
				_layout(raw_material_item="SCLTESTRM001SHR", twin_finished_part="SCLTESTRM001SHR")
			)

	def test_lh_rh_rejects_process_scrap_as_twin(self) -> None:
		with self.assertRaisesRegex(frappe.ValidationError, "process scrap"):
			validate_sheet_cutting_layout(_layout(process_scrap_item="SCLTESTFG002SHR"))

	def test_lh_rh_rejects_invalid_twin_code(self) -> None:
		with self.assertRaisesRegex(frappe.ValidationError, "must end with SHR"):
			validate_sheet_cutting_layout(_layout(twin_finished_part="SCLTESTFG002"))

	def test_lh_rh_accepts_valid_pair(self) -> None:
		layout = _layout()
		validate_sheet_cutting_layout(layout)
		self.assertEqual(layout.consumption_status, "Balanced")

	def test_non_lh_rh_ignores_stale_pair_fields(self) -> None:
		layout = _layout(is_lh_rh=0, orientation=None, twin_finished_part="")
		validate_sheet_cutting_layout(layout)
		self.assertEqual(layout.consumption_status, "Balanced")
