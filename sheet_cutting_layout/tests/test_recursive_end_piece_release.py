from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import frappe

from sheet_cutting_layout.services.end_piece_bom_service import _reuse_end_pieces
from sheet_cutting_layout.services.release_service import collect_descendant_layout_names
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase
from sheet_cutting_layout.tests.factories import ensure_item, ensure_project


class TestReuseEndPieceFilterSkipsChildLayouts(SheetCuttingLayoutTestCase):
	def test_rows_with_child_layout_are_excluded_from_simple_bom_generation(self) -> None:
		simple_row = SimpleNamespace(disposition="Reuse", child_layout=None)
		child_owned_row = SimpleNamespace(disposition="Reuse", child_layout="SCL-CHILD-001")
		scrap_row = SimpleNamespace(disposition="Scrap", child_layout=None)
		layout = SimpleNamespace(end_pieces=[simple_row, child_owned_row, scrap_row])

		result = _reuse_end_pieces(layout)

		self.assertIn(simple_row, result)
		self.assertNotIn(child_owned_row, result)
		self.assertNotIn(scrap_row, result)


class TestCollectDescendantLayoutNames(SheetCuttingLayoutTestCase):
	def test_walks_child_layout_links_leaves_first(self) -> None:
		grandchild = SimpleNamespace(end_pieces=[])
		child = SimpleNamespace(end_pieces=[SimpleNamespace(child_layout="SCL-GRANDCHILD")])
		root = SimpleNamespace(
			name="SCL-ROOT",
			end_pieces=[SimpleNamespace(child_layout="SCL-CHILD")],
		)
		registry = {"SCL-CHILD": child, "SCL-GRANDCHILD": grandchild}

		names = collect_descendant_layout_names(root, lambda layout_name: registry[layout_name])

		self.assertEqual(names, ["SCL-GRANDCHILD", "SCL-CHILD"])


def _release(layout: object) -> None:
	layout.db_set("status", "Approved by Purchase", update_modified=False)
	layout.reload()
	layout.status = "Released"
	layout.submit()


class TestRecursiveEndPieceLifecycle(SheetCuttingLayoutTestCase):
	def setUp(self) -> None:
		super().setUp()
		suffix = frappe.generate_hash(length=8).upper()
		self.suffix = suffix
		self.project = ensure_project()
		self.raw_material = ensure_item(f"SCLRECURRM{suffix}", stock_uom="Kg")
		self.scrap_item = ensure_item(f"SCLRECURSCRAP{suffix}", stock_uom="Kg")
		self.finished_part = ensure_item(f"SCLRECURFG{suffix}SHR", stock_uom="Nos")
		self.parent_end_piece_item = ensure_item(
			f"{self.finished_part}-EP-2x500x1000",
			stock_uom="Kg",
			valuation_rate=50,
		)
		self.child_end_piece_item = ensure_item(
			f"{self.finished_part}-EP-2x250x500",
			stock_uom="Kg",
			valuation_rate=50,
		)

	def _layout_doc(
		self,
		*,
		code: str,
		raw_material_item: str,
		width: int,
		length: int,
		strip_width: int,
		strip_length: int,
		net_weight: float,
		end_piece: dict[str, object] | None = None,
	) -> object:
		values: dict[str, object] = {
			"doctype": "Sheet Cutting Layout",
			"layout_code": code,
			"project": self.project,
			"revision_no": 1,
			"status": "Draft",
			"raw_material_item": raw_material_item,
			"process_scrap_item": self.scrap_item,
			"sheet_thickness_mm": 2,
			"sheet_width_mm": width,
			"sheet_length_mm": length,
			"strip_thickness_mm": 2,
			"strip_width_mm": strip_width,
			"strip_length_mm": strip_length,
			"parts_per_strip": 1,
			"no_of_strips": 1,
			"finished_part_code": self.finished_part,
			"net_weight_per_part_kg": net_weight,
		}
		if end_piece:
			values["end_pieces"] = [end_piece]
		return frappe.get_doc(values)

	def _build_two_level_tree(self) -> tuple[object, object, object]:
		grandchild = self._layout_doc(
			code=f"SCL-RECUR-GC-{self.suffix}",
			raw_material_item=self.child_end_piece_item,
			width=250,
			length=500,
			strip_width=250,
			strip_length=500,
			net_weight=1.965,
		).insert(ignore_permissions=True)
		child = self._layout_doc(
			code=f"SCL-RECUR-CHILD-{self.suffix}",
			raw_material_item=self.parent_end_piece_item,
			width=500,
			length=1000,
			strip_width=375,
			strip_length=1000,
			net_weight=5.895,
			end_piece={
				"width_mm": 250,
				"length_mm": 500,
				"disposition": "Reuse",
				"used_for_finished_part": self.finished_part,
				"scrap_item": self.scrap_item,
				"child_layout": grandchild.name,
				"bom_quantity": 1,
				"net_weight_per_part_kg": 1.965,
			},
		).insert(ignore_permissions=True)
		parent = self._layout_doc(
			code=f"SCL-RECUR-PARENT-{self.suffix}",
			raw_material_item=self.raw_material,
			width=1000,
			length=1000,
			strip_width=500,
			strip_length=1000,
			net_weight=7.86,
			end_piece={
				"width_mm": 500,
				"length_mm": 1000,
				"disposition": "Reuse",
				"used_for_finished_part": self.finished_part,
				"scrap_item": self.scrap_item,
				"child_layout": child.name,
				"bom_quantity": 1,
				"net_weight_per_part_kg": 7.86,
			},
		).insert(ignore_permissions=True)
		return parent, child, grandchild

	def test_release_builds_a_bom_for_every_layout_in_the_tree(self) -> None:
		parent, child, grandchild = self._build_two_level_tree()

		for layout in (grandchild, child, parent):
			_release(layout)
			self.assertTrue(frappe.db.exists("BOM", {"sheet_cutting_layout": layout.name}))

	def test_cancel_parent_cascades_and_deactivates_descendant_boms(self) -> None:
		parent, child, grandchild = self._build_two_level_tree()
		for layout in (grandchild, child, parent):
			_release(layout)

		parent.reload()
		parent.status = "Superseded"
		parent.cancel()

		for layout in (child, grandchild):
			layout.reload()
			self.assertEqual(layout.docstatus, 2)
			boms = frappe.get_all(
				"BOM",
				filters={"sheet_cutting_layout": layout.name},
				fields=["name", "is_active"],
			)
			self.assertTrue(boms)
			self.assertTrue(all(not bom.is_active for bom in boms))

	def test_descendant_bom_cancel_block_deactivates_instead(self) -> None:
		parent, child, grandchild = self._build_two_level_tree()
		for layout in (grandchild, child, parent):
			_release(layout)

		blocked_bom = frappe.db.get_value("BOM", {"sheet_cutting_layout": grandchild.name}, "name")
		self.assertIsNotNone(blocked_bom)
		original_get_doc = frappe.get_doc

		def get_doc_with_blocked_cancel(*args: object, **kwargs: object) -> object:
			doc = original_get_doc(*args, **kwargs)
			if args[:2] == ("BOM", blocked_bom):
				def blocked_cancel() -> None:
					raise frappe.LinkExistsError("linked manufacture stock entry")

				doc.cancel = blocked_cancel
			return doc

		self.start_patcher(patch("frappe.get_doc", side_effect=get_doc_with_blocked_cancel))

		parent.reload()
		parent.status = "Superseded"
		parent.cancel()

		bom = original_get_doc("BOM", blocked_bom)
		self.assertEqual(bom.docstatus, 1)
		self.assertFalse(bom.is_active)

	def test_delete_is_framework_gated_while_child_layout_links(self) -> None:
		parent, child, grandchild = self._build_two_level_tree()
		for layout in (grandchild, child, parent):
			_release(layout)

		parent.reload()
		parent.status = "Superseded"
		parent.cancel()

		grandchild.reload()
		with self.assertRaises(frappe.LinkExistsError):
			grandchild.delete()
