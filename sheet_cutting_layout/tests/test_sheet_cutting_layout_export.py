from __future__ import annotations

import io

import frappe
from openpyxl import load_workbook

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase
from sheet_cutting_layout.tests.factories import ensure_hsn_code, ensure_item_group


def _ensure_item(item_code: str, item_name: str | None = None) -> str:
	if not frappe.db.exists("Item", item_code):
		doc: dict[str, object] = {
			"doctype": "Item",
			"item_code": item_code,
			"item_name": item_name or item_code,
			"item_group": ensure_item_group(),
			"stock_uom": "Kg",
			"is_stock_item": 1,
		}
		if frappe.get_meta("Item", cached=True).has_field("gst_hsn_code") and frappe.db.exists(
			"DocType", "GST HSN Code"
		):
			doc["gst_hsn_code"] = ensure_hsn_code("720810")
		frappe.get_doc(doc).insert(ignore_permissions=True)
	return item_code


def _ensure_project(project_name: str) -> str:
	existing = frappe.db.exists("Project", {"project_name": project_name})
	if existing:
		return str(existing)
	return frappe.get_doc({"doctype": "Project", "project_name": project_name}).insert(
		ignore_permissions=True
	).name


class TestSheetCuttingLayoutExport(SheetCuttingLayoutTestCase):
	def _build_layout(self, *, is_lh_rh: bool = False) -> str:
		suffix = frappe.generate_hash(length=8).upper()
		project = _ensure_project(f"SCL Export {suffix}")
		raw_material = _ensure_item(f"SCLRM{suffix}")
		scrap = _ensure_item(f"SCLSCRAP{suffix}")
		finished = _ensure_item(f"SCLPART{suffix}SHR", item_name="Brkt bumper top")
		twin = _ensure_item(f"SCLTWIN{suffix}SHR", item_name="Brkt bumper top RH")
		layout_code = f"SCL-EXPORT-LAYOUT-{suffix}"
		layout: dict[str, object] = {
			"doctype": "Sheet Cutting Layout",
			"layout_code": layout_code,
			"project": project,
			"revision_no": 1,
			"status": "Draft",
			"raw_material_item": raw_material,
			"process_scrap_item": scrap,
			"sheet_thickness_mm": 2.0,
			"sheet_width_mm": 1000.0,
			"sheet_length_mm": 2000.0,
			"weight_per_sheet_kg": 31.44,
			"strip_thickness_mm": 2.0,
			"strip_width_mm": 1000.0,
			"strip_length_mm": 1000.0,
			"weight_of_strip_kg": 15.72,
			"parts_per_strip": 1,
			"no_of_strips": 2,
			"parts_per_sheet": 2,
			"finished_part_code": finished,
			"net_weight_per_part_kg": 15.52,
			"gross_weight_per_part_kg": 15.72,
			"scrap_weight_per_part_kg": 0.2,
		}
		if is_lh_rh:
			layout.update({"is_lh_rh": 1, "orientation": "LH", "twin_finished_part": twin})
		doc = frappe.get_doc(layout)
		doc.insert(ignore_permissions=True)
		return doc.name

	def test_download_produces_workbook_with_expected_cells(self) -> None:
		from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.sheet_cutting_layout import (
			download_sheet_cutting_layout,
		)

		layout_name = self._build_layout()
		frappe.response.clear()

		download_sheet_cutting_layout(layout_name)

		self.assertEqual(frappe.response["type"], "binary")
		self.assertTrue(str(frappe.response["filename"]).endswith(".xlsx"))
		content = frappe.response["filecontent"]
		self.assertIsInstance(content, bytes)
		self.assertEqual(content[:2], b"PK")

		worksheet = load_workbook(io.BytesIO(content)).active
		self.assertEqual(worksheet["K9"].value, 2.0)
		self.assertEqual(worksheet["L9"].value, 1000.0)
		self.assertEqual(worksheet["M9"].value, 2000.0)
		self.assertEqual(worksheet["K14"].value, 2)
		self.assertEqual(worksheet["K15"].value, 15.72)
		self.assertEqual(worksheet["K16"].value, 15.52)
		self.assertIn("SCL Export", str(worksheet["C6"].value))
		self.assertIn("SCLPART", str(worksheet["N5"].value))
		self.assertEqual(worksheet["G5"].value, "Brkt bumper top")
		self.assertNotEqual(worksheet["G5"].value, worksheet["N5"].value)
		self.assertIn(worksheet["U8"].value, (None, ""))

	def test_download_uses_persisted_lh_rh_pairing(self) -> None:
		from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.sheet_cutting_layout import (
			download_sheet_cutting_layout,
		)

		layout_name = self._build_layout(is_lh_rh=True)
		frappe.response.clear()

		download_sheet_cutting_layout(layout_name)

		worksheet = load_workbook(io.BytesIO(frappe.response["filecontent"])).active
		self.assertEqual(worksheet["G5"].value, "Brkt bumper top LH & RH")
		self.assertTrue(str(worksheet["N5"].value).startswith("SCLPART"))
		self.assertIn("_SCLTWIN", str(worksheet["N5"].value))
		self.assertTrue(str(worksheet["N5"].value).endswith("SHR"))
