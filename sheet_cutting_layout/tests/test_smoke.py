from __future__ import annotations

import frappe
from frappe.model.workflow import apply_workflow

from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.sheet_cutting_layout import (
	create_sheet_cutting_layout_revision,
	download_sheet_cutting_layout,
	generate_sheet_cutting_layout_end_piece_boms,
)
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase
from sheet_cutting_layout.tests.factories import ensure_item, make_layout, make_release_ready_layout


class TestSheetCuttingLayoutSmoke(SheetCuttingLayoutTestCase):
	def _native_release(self, layout):
		layout.workflow_status = "Released"
		layout.submit()
		layout.reload()
		return layout

	def _workflow_release(self, layout):
		for action in (
			"Submit for Check",
			"Project Manager Approves",
			"Purchase Approves",
			"MR Release",
		):
			layout = apply_workflow(layout, action)
		layout.reload()
		return layout

	def test_single_part_release_export_revision_and_supersede_smoke(self) -> None:
		layout = make_layout(
			finished_part_code=f"SCLTESTFG{frappe.generate_hash(length=5).upper()}SHR",
			sheet_thickness_mm=2,
			sheet_width_mm=1000,
			sheet_length_mm=2000,
			strip_thickness_mm=2,
			strip_width_mm=1000,
			strip_length_mm=1000,
			parts_per_strip=1,
			no_of_strips=2,
			net_weight_per_part_kg=15.52,
			gross_weight_per_part_kg=15.72,
			scrap_weight_per_part_kg=0.2,
		).insert()
		layout = self._workflow_release(layout)
		bom_name = layout.generated_bom

		self.assertEqual(layout.workflow_status, "Released")
		self.assertTrue(bom_name)
		self.assertEqual(len(layout.finished_parts), 1)
		self.assertIn("MR Approval", [row.step_name for row in layout.approval_snapshot])
		self.assertEqual(frappe.db.get_value("BOM", bom_name, "is_active"), 1)

		frappe.response.clear()
		download_sheet_cutting_layout(layout.name)
		self.assertEqual(frappe.response["type"], "binary")
		self.assertTrue(str(frappe.response["filename"]).endswith(".xlsx"))
		self.assertEqual(frappe.response["filecontent"][:2], b"PK")

		revision = frappe.get_doc("Sheet Cutting Layout", create_sheet_cutting_layout_revision(layout.name))
		self.assertEqual(revision.workflow_status, "Draft")
		self.assertEqual(revision.based_on_layout, layout.name)
		self.assertFalse(revision.generated_bom)

		apply_workflow(layout, "Supersede")
		layout.reload()
		self.assertEqual(layout.workflow_status, "Superseded")
		self.assertEqual(frappe.db.get_value("BOM", bom_name, "is_active"), 0)

	def test_reuse_end_piece_generation_smoke(self) -> None:
		finished_part = f"SCLTESTFG{frappe.generate_hash(length=5).upper()}SHR"
		scrap_item = ensure_item(f"SCLTESTSCRAP{frappe.generate_hash(length=5).upper()}", stock_uom="Kg")
		layout = make_layout(
			finished_part_code=finished_part,
			parts_per_strip=2,
			no_of_strips=1,
			strip_length_mm=2240,
			net_weight_per_part_kg=11.004,
			gross_weight_per_part_kg=11.004,
			scrap_weight_per_part_kg=0,
			end_pieces=[
				{
					"doctype": "Layout End Piece",
					"width_mm": 1250,
					"length_mm": 260,
					"weight_kg": 2.5545,
					"disposition": "Reuse",
					"used_for_finished_part": finished_part,
					"bom_quantity": 3,
					"net_weight_per_part_kg": 0.8515,
					"scrap_item": scrap_item,
				}
			],
		).insert()
		layout.db_set("workflow_status", "Approved by Purchase", update_modified=False)
		layout.reload()
		self._native_release(layout)

		result = generate_sheet_cutting_layout_end_piece_boms(layout.name)
		layout.reload()
		row = layout.end_pieces[0]

		self.assertEqual(layout.end_piece_bom_status, "Generated")
		self.assertTrue(row.end_piece_item_code)
		self.assertEqual(result["boms"], [row.generated_end_piece_bom])
		self.assertEqual(frappe.db.get_value("BOM", row.generated_end_piece_bom, "is_active"), 1)

	def test_lh_rh_release_smoke(self) -> None:
		twin_item = ensure_item(f"SCLTESTTWIN{frappe.generate_hash(length=5).upper()}SHR", stock_uom="Nos")
		layout = self._native_release(
			make_release_ready_layout(is_lh_rh=1, orientation="LH", twin_finished_part=twin_item)
		)
		bom_names = [row.generated_bom for row in layout.finished_parts]

		self.assertEqual([row.orientation for row in layout.finished_parts], ["LH", "RH"])
		self.assertEqual(layout.twin_generated_bom, bom_names[1])
		self.assertEqual(len(set(bom_names)), 2)
		self.assertTrue(all(frappe.db.get_value("BOM", bom_name, "is_active") for bom_name in bom_names))

	def test_reject_returns_layout_to_draft_smoke(self) -> None:
		layout = make_layout(
			finished_part_code=f"SCLTESTFG{frappe.generate_hash(length=5).upper()}SHR",
			parts_per_strip=1,
			no_of_strips=1,
			strip_length_mm=2500,
		).insert()

		layout = apply_workflow(layout, "Submit for Check")
		self.assertEqual(layout.workflow_status, "Submitted for Check")

		layout = apply_workflow(layout, "Reject")
		layout.reload()
		self.assertEqual(layout.workflow_status, "Draft")
		self.assertEqual(layout.docstatus, 0)
		self.assertIn(
			("Rejection", "Rejected"),
			[(row.step_name, row.decision) for row in layout.approval_snapshot],
		)
