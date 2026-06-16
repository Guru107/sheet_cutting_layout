from __future__ import annotations

import frappe

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase
from sheet_cutting_layout.tests.factories import ensure_item, ensure_project


class TestLayoutEndPieceChildLayoutField(SheetCuttingLayoutTestCase):
	def test_child_layout_field_exists_on_layout_end_piece(self) -> None:
		meta = frappe.get_meta("Layout End Piece")
		field = meta.get_field("child_layout")
		self.assertIsNotNone(field)
		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "Sheet Cutting Layout")
		self.assertEqual(field.depends_on, 'eval:doc.disposition=="Reuse"')
		self.assertEqual(field.no_copy, 1)


class TestChildLayoutValidation(SheetCuttingLayoutTestCase):
	def setUp(self) -> None:
		super().setUp()
		suffix = frappe.generate_hash(length=8).upper()
		self.project = ensure_project()
		self.raw_material = ensure_item(f"SCLRECURRM{suffix}", stock_uom="Kg")
		self.scrap_item = ensure_item(f"SCLRECURSCRAP{suffix}", stock_uom="Kg")
		self.finished_part = ensure_item(f"SCLRECURFG{suffix}SHR", stock_uom="Nos")
		self.end_piece_item = ensure_item(f"{self.finished_part}-EP-2x500x500", stock_uom="Kg")
		self.suffix = suffix

	def _child(self, raw_material_item: str) -> object:
		return frappe.get_doc(
			{
				"doctype": "Sheet Cutting Layout",
				"layout_code": f"SCL-RECUR-CHILD-{self.suffix}",
				"project": self.project,
				"revision_no": 1,
				"status": "Draft",
				"raw_material_item": raw_material_item,
				"process_scrap_item": self.scrap_item,
				"sheet_thickness_mm": 2,
				"sheet_width_mm": 500,
				"sheet_length_mm": 500,
				"strip_thickness_mm": 2,
				"strip_width_mm": 500,
				"strip_length_mm": 500,
				"parts_per_strip": 1,
				"no_of_strips": 1,
				"finished_part_code": self.finished_part,
				"net_weight_per_part_kg": 1.865,
			}
		)

	def _parent(self, child_layout: str | None) -> object:
		return frappe.get_doc(
			{
				"doctype": "Sheet Cutting Layout",
				"layout_code": f"SCL-RECUR-PARENT-{self.suffix}",
				"project": self.project,
				"revision_no": 1,
				"status": "Draft",
				"raw_material_item": self.raw_material,
				"process_scrap_item": self.scrap_item,
				"sheet_thickness_mm": 2,
				"sheet_width_mm": 1000,
				"sheet_length_mm": 750,
				"strip_thickness_mm": 2,
				"strip_width_mm": 500,
				"strip_length_mm": 1000,
				"parts_per_strip": 1,
				"no_of_strips": 1,
				"finished_part_code": self.finished_part,
				"net_weight_per_part_kg": 7.86,
				"end_pieces": [
					{
						"width_mm": 500,
						"length_mm": 500,
						"disposition": "Reuse",
						"used_for_finished_part": self.finished_part,
						"scrap_item": self.scrap_item,
						"child_layout": child_layout,
						"bom_quantity": 1,
						"net_weight_per_part_kg": 3.93,
					}
				],
			}
		)

	def test_child_raw_material_must_match_end_piece_item(self) -> None:
		child = self._child(self.raw_material).insert(ignore_permissions=True)
		parent = self._parent(child.name)
		with self.assertRaises(frappe.ValidationError):
			parent.insert(ignore_permissions=True)

	def test_child_with_matching_raw_material_validates(self) -> None:
		child = self._child(self.end_piece_item).insert(ignore_permissions=True)
		parent = self._parent(child.name).insert(ignore_permissions=True)
		self.assertEqual(parent.end_pieces[0].child_layout, child.name)

	def test_self_reference_is_rejected(self) -> None:
		parent = self._parent(f"SCL-RECUR-PARENT-{self.suffix}")
		with self.assertRaises(frappe.ValidationError):
			parent.insert(ignore_permissions=True)

	def test_child_cannot_be_released_before_parent_end_piece_item_exists(self) -> None:
		child = self._child(self.end_piece_item).insert(ignore_permissions=True)
		frappe.delete_doc("Item", self.end_piece_item, force=True, ignore_permissions=True)
		child.reload()
		child.status = "Released"
		with self.assertRaises(frappe.ValidationError):
			child.save(ignore_permissions=True)
