from __future__ import annotations

import inspect

from frappe.model.document import Document

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase
from sheet_cutting_layout.sheet_cutting_layout.doctype.layout_approval_snapshot import (
	layout_approval_snapshot as snapshot_module,
)
from sheet_cutting_layout.sheet_cutting_layout.doctype.layout_end_piece import (
	layout_end_piece as end_piece_module,
)
from sheet_cutting_layout.sheet_cutting_layout.doctype.layout_finished_part import (
	layout_finished_part as finished_part_module,
)
from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import (
	sheet_cutting_layout as controller,
)


class TestControllerImports(SheetCuttingLayoutTestCase):
	def test_child_controllers_use_real_document_base(self) -> None:
		self.assertTrue(issubclass(end_piece_module.LayoutEndPiece, Document))
		self.assertTrue(issubclass(finished_part_module.LayoutFinishedPart, Document))
		self.assertTrue(issubclass(snapshot_module.LayoutApprovalSnapshot, Document))

	def test_controllers_have_no_frappe_import_shim(self) -> None:
		for module in (controller, end_piece_module, finished_part_module, snapshot_module):
			self.assertNotIn("except ImportError", inspect.getsource(module))
