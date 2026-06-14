from __future__ import annotations

from sheet_cutting_layout.tests import factories
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


class TestFactories(SheetCuttingLayoutTestCase):
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
