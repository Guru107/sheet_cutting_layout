from __future__ import annotations

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


def _base_layout() -> dict[str, object]:
	return {
		"company": "Acme Press Parts",
		"layout_code": "SCL-EXPORT-LAYOUT-001",
		"part_name": "Brkt bumper top",
		"part_numbers": ["0102AAG06400SHR"],
		"is_lh_rh": False,
		"project": "PRJ-0001",
		"project_name": "Bumper Program",
		"raw_material_item_name": "HSLA-340",
		"sheet_thickness_mm": 2.0,
		"sheet_width_mm": 1000.0,
		"sheet_length_mm": 2000.0,
		"weight_per_sheet_kg": 31.44,
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
		self.assertEqual(cells["A5"], "Sheet Cutting Layout No:- SCL-EXPORT-LAYOUT-001")
		self.assertEqual(cells["G5"], "Part Name:-Brkt bumper top")
		self.assertEqual(cells["N5"], "Part Number:-0102AAG06400SHR")
		self.assertEqual(cells["B6"], "PRJ-0001")
		self.assertEqual(cells["C6"], "Bumper Program")
		self.assertEqual(cells["J7"], "HSLA-340")
		self.assertEqual(cells["K8"], 2.0)
		self.assertEqual(cells["K9"], 2.0)
		self.assertEqual(cells["L9"], 1000.0)
		self.assertEqual(cells["M9"], 2000.0)
		self.assertEqual(cells["T6"], 31.44)
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
		self.assertNotIn("P8", cells)
		self.assertEqual(cells["Q8"], 15.72)
		self.assertEqual(cells["R8"], 15.52)
		self.assertEqual(cells["S8"], 0.2)
		self.assertEqual(cells["T8"], 2)
		self.assertAlmostEqual(float(cells["U8"]), 31.44, places=6)


class TestBuildCellMapLhRhLabels(SheetCuttingLayoutTestCase):
	def test_lh_rh_part_name_and_joined_numbers(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		layout = _base_layout()
		layout.update(
			{
				"part_name": "Brkt bumper top",
				"part_names": ["Brkt bumper top", "Brkt bumper top RH"],
				"is_lh_rh": True,
				"orientation": "LH",
				"part_numbers": ["0102AAG06400SHR", "0102AAG06410SHR"],
			}
		)

		cells = build_cell_map(layout)

		self.assertEqual(cells["G5"], "Part Name:-Brkt bumper top & Brkt bumper top RH")
		self.assertEqual(cells["N5"], "Part Number:-0102AAG06400SHR/0102AAG06410SHR")
		self.assertEqual(cells["O8"], "0102AAG06400SHR")

	def test_single_part_number_is_not_joined(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		layout = _base_layout()
		layout["part_numbers"] = ["0102AAG06400SHR"]

		cells = build_cell_map(layout)

		self.assertEqual(cells["N5"], "Part Number:-0102AAG06400SHR")
		self.assertEqual(cells["G5"], "Part Name:-Brkt bumper top")

	def test_blank_part_numbers_are_dropped_from_join(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		layout = _base_layout()
		layout["part_numbers"] = ["0102AAG06400SHR", "", None, "  "]

		cells = build_cell_map(layout)

		self.assertEqual(cells["N5"], "Part Number:-0102AAG06400SHR")


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
		self.assertNotIn("P9", cells)
		self.assertEqual(cells["Q9"], 0.47)
		self.assertEqual(cells["R9"], 0.4)
		self.assertEqual(cells["S9"], 0.07)
		self.assertEqual(cells["T9"], 2)
		self.assertAlmostEqual(float(cells["U9"]), 0.94, places=6)
		self.assertEqual(cells["O10"], "")
		self.assertEqual(cells["U10"], "")
		self.assertEqual(cells["O11"], "")
		self.assertEqual(cells["U11"], "")

	def test_end_piece_without_item_code_uses_size_label(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		layout = _base_layout()
		layout["end_pieces"] = [{"width_mm": 200.0, "length_mm": 300.0, "weight_kg": 0.94}]

		cells = build_cell_map(layout)

		self.assertEqual(cells["O9"], "200.0 x 300.0")

	def test_first_two_end_pieces_render_in_bom_and_first_three_render_in_detail_blocks(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		layout = _base_layout()
		layout["end_pieces"] = [
			{
				"end_piece_item_code": f"EP-{index}",
				"width_mm": 200 + index,
				"length_mm": 300 + index,
				"gross_weight_per_part_kg": 0.4 + index,
				"net_weight_per_part_kg": 0.3 + index,
				"scrap_weight_per_part_kg": 0.1 + index,
				"bom_quantity": index + 2,
				"used_for_finished_part": f"0102AAG0640{index}SHR",
			}
			for index in range(5)
		]

		cells = build_cell_map(layout)

		self.assertEqual(cells["O9"], "EP-0")
		self.assertEqual(cells["O10"], "EP-1")
		self.assertEqual(cells["O11"], "")
		self.assertNotIn("P10", cells)
		self.assertEqual(cells["K18"], 2.0)
		self.assertEqual(cells["L18"], 200)
		self.assertEqual(cells["M18"], 300)
		self.assertEqual(cells["J23"], "0102AAG06400SHR")
		self.assertEqual(cells["K22"], 2.0)
		self.assertEqual(cells["L22"], 200)
		self.assertEqual(cells["M22"], 300)
		self.assertEqual(cells["K24"], 2.0)
		self.assertEqual(cells["L24"], 200)
		self.assertEqual(cells["M24"], 300)
		self.assertEqual(cells["K25"], 2)
		self.assertEqual(cells["K26"], 0.4)
		self.assertEqual(cells["K27"], 0.3)
		self.assertEqual(cells["K28"], 0.1)
		self.assertEqual(cells["R12"], 2.0)
		self.assertEqual(cells["S12"], 201)
		self.assertEqual(cells["T12"], 301)
		self.assertEqual(cells["Q13"], "0102AAG06401SHR")
		self.assertEqual(cells["R14"], 2.0)
		self.assertEqual(cells["S14"], 201)
		self.assertEqual(cells["T14"], 301)
		self.assertEqual(cells["R15"], 3)
		self.assertEqual(cells["R16"], 1.4)
		self.assertEqual(cells["R17"], 1.3)
		self.assertEqual(cells["R18"], 1.1)
		self.assertEqual(cells["R22"], 2.0)
		self.assertEqual(cells["S22"], 202)
		self.assertEqual(cells["T22"], 302)
		self.assertEqual(cells["Q23"], "0102AAG06402SHR")
		self.assertEqual(cells["R24"], 2.0)
		self.assertEqual(cells["S24"], 202)
		self.assertEqual(cells["T24"], 302)
		self.assertEqual(cells["R25"], 4)
		self.assertEqual(cells["R26"], 2.4)
		self.assertEqual(cells["R27"], 2.3)
		self.assertEqual(cells["R28"], 2.1)
		self.assertNotIn("EP-3", cells.values())
		self.assertNotIn("EP-4", cells.values())

	def test_absent_end_piece_detail_blocks_clear_template_cells(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		cells = build_cell_map(_base_layout())

		for coordinate in (
			"K18",
			"L18",
			"M18",
			"K22",
			"L22",
			"M22",
			"J23",
			"K24",
			"L24",
			"M24",
			"K25",
			"K26",
			"K27",
			"K28",
			"R12",
			"S12",
			"T12",
			"Q13",
			"R14",
			"S14",
			"T14",
			"R15",
			"R16",
			"R17",
			"R18",
			"R22",
			"S22",
			"T22",
			"Q23",
			"R24",
			"S24",
			"T24",
			"R25",
			"R26",
			"R27",
			"R28",
		):
			self.assertEqual(cells[coordinate], "")

	def test_unused_bom_rows_clear_template_placeholders(self) -> None:
		from sheet_cutting_layout.services.export_service import build_cell_map

		cells = build_cell_map(_base_layout())

		for row in (9, 10, 11):
			for column in ("O", "Q", "R", "S", "T", "U"):
				self.assertEqual(cells[f"{column}{row}"], "")

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
				"weight_per_sheet_kg": None,
				"raw_material_weight_kg": None,
			}
		)

		cells = build_cell_map(layout)

		self.assertEqual(cells["K8"], "")
		self.assertEqual(cells["K9"], "")
		self.assertEqual(cells["K10"], "")
		self.assertEqual(cells["K15"], "")
		self.assertEqual(cells["K16"], "")
		self.assertEqual(cells["T6"], "")
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
				"part_names": ["Brkt bumper top", "Brkt bumper top RH"],
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
		self.assertEqual(worksheet["A5"].value, "Sheet Cutting Layout No:- SCL-EXPORT-LAYOUT-001")
		self.assertEqual(worksheet["G5"].value, "Part Name:-Brkt bumper top & Brkt bumper top RH")
		self.assertEqual(worksheet["N5"].value, "Part Number:-0102AAG06400SHR/0102AAG06410SHR")
		self.assertEqual(worksheet["T6"].value, 31.44)
		self.assertEqual(worksheet["K10"].value, 15.72)
		self.assertEqual(worksheet["K14"].value, 2)
		self.assertEqual(worksheet["Q1"].value, "DOC. NO.:  FRM/PRD/15")

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
		self.assertIn(worksheet["O9"].value, (None, ""))
		self.assertIn(worksheet["Q9"].value, (None, ""))
		self.assertIn(worksheet["U11"].value, (None, ""))
		for coordinate in ("K22", "L22", "M22"):
			self.assertIn(worksheet[coordinate].value, (None, ""))

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
		self.assertEqual(worksheet["G5"].value, "Part Name:-+part")
		self.assertEqual(worksheet["N5"].value, "Part Number:--PART001SHR")
		self.assertEqual(worksheet["B6"].value, "'@project")
		self.assertEqual(worksheet["O9"].value, "'=EP-001")
