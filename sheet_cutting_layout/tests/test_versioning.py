from __future__ import annotations

import inspect

from frappe.tests.utils import FrappeTestCase

from sheet_cutting_layout.services import versioning


class TestVersioning(FrappeTestCase):
	def test_reset_child_row_only_clears_app_fields(self) -> None:
		source = inspect.getsource(versioning._reset_child_row)
		# copy_doc localizes name/parent/parentfield/parenttype; we must not touch them.
		self.assertNotIn('"parent"', source)
		self.assertNotIn('"parenttype"', source)
		self.assertIn("end_piece_item_code", source)

	def test_copy_layout_has_no_deepcopy_fallback(self) -> None:
		module_source = inspect.getsource(versioning)
		copy_source = inspect.getsource(versioning._copy_layout)
		# Both deepcopy fallbacks (the except-ImportError path and the
		# non-callable-copy_doc path) are gone; the module no longer imports deepcopy.
		self.assertNotIn("deepcopy", copy_source)
		self.assertNotIn("except ImportError", copy_source)
		self.assertNotIn("from copy import deepcopy", module_source)
