from __future__ import annotations

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


def _base_layout() -> dict[str, object]:
	return {
		"company": "Acme Press Parts",
		"part_name": "Brkt bumper top",
		"part_numbers": ["0102AAG06400SHR"],
		"is_lh_rh": False,
		"project": "PRJ-0001",
		"project_name": "Bumper Program",
		"sheet_thickness_mm": 2.0,
		"sheet_width_mm": 1000.0,
		"sheet_length_mm": 2000.0,
		"weight_of_strip_kg": 15.72,
		"strip_thickness_mm": 2.0,
		"strip_width_mm": 1000.0,
		"strip_length_mm": 1000.0,
		"parts_per_strip": 1,
		"no_of_strips": 2,
		"parts_per_sheet": 2,
		"gross_weight_per_part_kg": 15.72,
		"net_weight_per_part_kg": 15.52,
		"scrap_weight_per_part_kg": 0.2,
		"raw_material_weight_kg": 31.44,
		"end_pieces": [],
	}


class TestApprovedIatfTemplate(SheetCuttingLayoutTestCase):
	def test_committed_template_matches_approved_visual_anchors(self) -> None:
		from openpyxl import load_workbook

		from sheet_cutting_layout.services.export_service import default_template_path

		workbook = load_workbook(default_template_path())
		self.assertEqual(len(workbook.worksheets), 1)
		worksheet = workbook.active

		self.assertEqual(worksheet.page_setup.orientation, "landscape")
		self.assertEqual(str(worksheet.page_setup.paperSize), "9")
		self.assertIn("A1:A4", {str(item) for item in worksheet.merged_cells.ranges})
		self.assertIn("E1:P4", {str(item) for item in worksheet.merged_cells.ranges})
		self.assertIn("G5:M5", {str(item) for item in worksheet.merged_cells.ranges})
		self.assertIn("N5:Q5", {str(item) for item in worksheet.merged_cells.ranges})
		self.assertIn("R38:U40", {str(item) for item in worksheet.merged_cells.ranges})
		self.assertEqual(worksheet["Q1"].value, "DOC. NO.:  FRM/PRD/15")
		self.assertEqual(worksheet["O7"].value, "BOM")
		self.assertEqual(worksheet["Q7"].value, "Gross Wt")
		self.assertEqual(worksheet["R7"].value, "F.g Wt")
		self.assertEqual(worksheet["S7"].value, "Scrap Wt")
		self.assertEqual(worksheet["R38"].value, "Released By    \nManagement Rep")


class TestBuildCellMapHeaderAndStrip(SheetCuttingLayoutTestCase):
	def test_header_strip_and_per_part_cells(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		cells = build_cell_map(_base_layout())

		self.assertEqual(cells["B1"], "Acme Press Parts")
		self.assertEqual(cells["G5"], "Brkt bumper top")
		self.assertEqual(cells["N5"], "0102AAG06400SHR")
		self.assertEqual(cells["B6"], "PRJ-0001")
		self.assertEqual(cells["C6"], "Bumper Program")
		self.assertEqual(cells["K8"], 2.0)
		self.assertEqual(cells["K9"], 2.0)
		self.assertEqual(cells["L9"], 1000.0)
		self.assertEqual(cells["M9"], 2000.0)
		self.assertEqual(cells["K10"], 15.72)
		self.assertEqual(cells["K11"], 2.0)
		self.assertEqual(cells["L11"], 1000.0)
		self.assertEqual(cells["M11"], 1000.0)
		self.assertEqual(cells["K12"], 1)
		self.assertEqual(cells["K13"], 2)
		self.assertEqual(cells["K14"], 2)
		self.assertEqual(cells["K15"], 15.72)
		self.assertEqual(cells["K16"], 15.52)
		self.assertEqual(cells["K17"], 0.2)
		self.assertEqual(cells["O8"], "0102AAG06400SHR")
		self.assertEqual(cells["P8"], 15.72)
		self.assertEqual(cells["Q8"], 15.52)
		self.assertEqual(cells["R8"], 0.2)
		self.assertEqual(cells["S8"], 2)
		self.assertAlmostEqual(float(cells["T8"]), 31.44, places=6)
		self.assertEqual(cells["U8"], 31.44)


class TestBuildCellMapLhRhLabels(SheetCuttingLayoutTestCase):
	def test_lh_rh_part_name_and_joined_numbers(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		layout = _base_layout()
		layout.update(
			{
				"part_name": "Brkt bumper top",
				"is_lh_rh": True,
				"orientation": "LH",
				"part_numbers": ["0102AAG06400SHR", "0102AAG06410SHR"],
			}
		)

		cells = build_cell_map(layout)

		self.assertEqual(cells["G5"], "Brkt bumper top LH & RH")
		self.assertEqual(cells["N5"], "0102AAG06400SHR_0102AAG06410SHR")
		self.assertEqual(cells["O8"], "0102AAG06400SHR_0102AAG06410SHR")

	def test_single_part_number_is_not_joined(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		layout = _base_layout()
		layout["part_numbers"] = ["0102AAG06400SHR"]

		cells = build_cell_map(layout)

		self.assertEqual(cells["N5"], "0102AAG06400SHR")
		self.assertEqual(cells["G5"], "Brkt bumper top")

	def test_blank_part_numbers_are_dropped_from_join(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		layout = _base_layout()
		layout["part_numbers"] = ["0102AAG06400SHR", "", None, "  "]

		cells = build_cell_map(layout)

		self.assertEqual(cells["N5"], "0102AAG06400SHR")


class TestBuildCellMapEndPiecesAndGuards(SheetCuttingLayoutTestCase):
	def test_end_piece_rows_populate_bom_table(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		layout = _base_layout()
		layout["end_pieces"] = [
			{
				"end_piece_item_code": "EP-0102AAG06400-1",
				"width_mm": 200.0,
				"length_mm": 300.0,
				"weight_kg": 0.94,
				"gross_weight_per_part_kg": 0.47,
				"net_weight_per_part_kg": 0.4,
				"scrap_weight_per_part_kg": 0.07,
				"bom_quantity": 2,
			}
		]

		cells = build_cell_map(layout)

		self.assertEqual(cells["O9"], "EP-0102AAG06400-1")
		self.assertEqual(cells["P9"], 0.47)
		self.assertEqual(cells["Q9"], 0.4)
		self.assertEqual(cells["R9"], 0.07)
		self.assertEqual(cells["S9"], 2)
		self.assertAlmostEqual(float(cells["T9"]), 0.94, places=6)
		self.assertEqual(cells["U9"], 0.94)

	def test_end_piece_without_item_code_uses_size_label(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		layout = _base_layout()
		layout["end_pieces"] = [{"width_mm": 200.0, "length_mm": 300.0, "weight_kg": 0.94}]

		cells = build_cell_map(layout)

		self.assertEqual(cells["O9"], "200.0 x 300.0")

	def test_only_first_three_end_pieces_render(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		layout = _base_layout()
		layout["end_pieces"] = [{"end_piece_item_code": f"EP-{index}"} for index in range(5)]

		cells = build_cell_map(layout)

		self.assertEqual(cells["O9"], "EP-0")
		self.assertEqual(cells["O10"], "EP-1")
		self.assertEqual(cells["O11"], "EP-2")
		self.assertNotIn("O12", cells)

	def test_missing_numeric_inputs_render_as_empty_string(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		layout = _base_layout()
		layout.update(
			{
				"sheet_thickness_mm": None,
				"weight_of_strip_kg": None,
				"gross_weight_per_part_kg": None,
				"net_weight_per_part_kg": "",
				"parts_per_sheet": None,
				"raw_material_weight_kg": None,
			}
		)

		cells = build_cell_map(layout)

		self.assertEqual(cells["K8"], "")
		self.assertEqual(cells["K9"], "")
		self.assertEqual(cells["K10"], "")
		self.assertEqual(cells["K15"], "")
		self.assertEqual(cells["K16"], "")
		self.assertEqual(cells["T8"], "")
		self.assertEqual(cells["U8"], "")
		for value in cells.values():
			self.assertNotEqual(value, "None")


class TestRenderWorkbookBytes(SheetCuttingLayoutTestCase):
	def test_renders_cells_into_template_and_returns_xlsx_bytes(self) -> None:
		import io

		from openpyxl import load_workbook

		from sheet_cutting_layout.services.export_service import (
			default_template_path,
			render_workbook_bytes,
		)

		layout = _base_layout()
		layout.update(
			{
				"is_lh_rh": True,
				"part_numbers": ["0102AAG06400SHR", "0102AAG06410SHR"],
			}
		)

		content = render_workbook_bytes(layout, default_template_path())

		self.assertIsInstance(content, bytes)
		self.assertGreater(len(content), 0)
		self.assertEqual(content[:2], b"PK")

		workbook = load_workbook(io.BytesIO(content))
		worksheet = workbook.active
		self.assertEqual(worksheet["B1"].value, "Acme Press Parts")
		self.assertEqual(worksheet["G5"].value, "Brkt bumper top LH & RH")
		self.assertEqual(worksheet["N5"].value, "0102AAG06400SHR_0102AAG06410SHR")
		self.assertEqual(worksheet["K14"].value, 2)
		self.assertEqual(worksheet["B2"].value, "FRM/PRD/15")

	def test_empty_string_cells_clear_the_target_cell(self) -> None:
		import io

		from openpyxl import load_workbook

		from sheet_cutting_layout.services.export_service import (
			default_template_path,
			render_workbook_bytes,
		)

		layout = _base_layout()
		layout["sheet_thickness_mm"] = None

		content = render_workbook_bytes(layout, default_template_path())
		workbook = load_workbook(io.BytesIO(content))
		worksheet = workbook.active
		self.assertIn(worksheet["K8"].value, (None, ""))

	def test_formula_like_text_cells_are_escaped(self) -> None:
		import io

		from openpyxl import load_workbook

		from sheet_cutting_layout.services.export_service import (
			default_template_path,
			render_workbook_bytes,
		)

		layout = _base_layout()
		layout.update(
			{
				"company": "=2+2",
				"part_name": "+part",
				"part_numbers": ["-PART001SHR"],
				"project": "@project",
				"end_pieces": [{"end_piece_item_code": "=EP-001"}],
			}
		)

		content = render_workbook_bytes(layout, default_template_path())
		workbook = load_workbook(io.BytesIO(content))
		worksheet = workbook.active

		self.assertEqual(worksheet["B1"].value, "'=2+2")
		self.assertEqual(worksheet["G5"].value, "'+part")
		self.assertEqual(worksheet["N5"].value, "'-PART001SHR")
		self.assertEqual(worksheet["B6"].value, "'@project")
		self.assertEqual(worksheet["O9"].value, "'=EP-001")
