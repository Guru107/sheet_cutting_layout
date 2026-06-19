from __future__ import annotations

import frappe

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


class TestEndPieceBomVisibility(SheetCuttingLayoutTestCase):
	def test_generated_end_piece_bom_is_gated_not_hidden(self) -> None:
		field = frappe.get_meta("Layout End Piece").get_field("generated_end_piece_bom")
		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "BOM")
		self.assertEqual(field.read_only, 1)
		# Shown as a grid column, revealed only once the BOM is generated.
		self.assertFalse(field.hidden)
		self.assertEqual(field.in_list_view, 1)
		self.assertEqual(field.depends_on, "eval:doc.generated_end_piece_bom")
