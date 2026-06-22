from __future__ import annotations

import frappe

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


class TestLayoutEndPieceSchema(SheetCuttingLayoutTestCase):
	def test_legacy_cross_layout_field_is_removed_from_layout_end_piece(self) -> None:
		meta = frappe.get_meta("Layout End Piece")
		legacy_fieldname = "_".join(("child", "layout"))
		self.assertIsNone(meta.get_field(legacy_fieldname))
