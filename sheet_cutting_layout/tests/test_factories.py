from __future__ import annotations

from sheet_cutting_layout.tests import factories
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


class TestFactories(SheetCuttingLayoutTestCase):
	def test_register_test_doc_is_a_noop_under_rollback(self) -> None:
		# Must not raise and must not touch any global registry.
		factories.register_test_doc("Sheet Cutting Layout", "SCL-TEST-NOOP")
		self.assertFalse(hasattr(factories, "_created_docs"))
		self.assertFalse(hasattr(factories, "_cleanup_registered"))

	def test_no_atexit_cleanup_is_registered(self) -> None:
		import inspect

		source = inspect.getsource(factories)
		self.assertNotIn("atexit", source)
		self.assertNotIn("cleanup_test_records", source)

	def test_factories_are_still_exported(self) -> None:
		# The merge moved the factories here; they must remain importable.
		for name in (
			"make_layout",
			"make_release_ready_layout",
			"ensure_item",
			"ensure_item_group",
			"ensure_project",
			"ensure_hsn_code",
			"insert_if_missing",
		):
			self.assertTrue(hasattr(factories, name))
