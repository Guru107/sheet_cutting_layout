from __future__ import annotations

import frappe

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


class TestLayoutEndPieceSchema(SheetCuttingLayoutTestCase):
	def test_child_layout_field_is_removed_from_layout_end_piece(self) -> None:
		meta = frappe.get_meta("Layout End Piece")
		self.assertIsNone(meta.get_field("child_layout"))
