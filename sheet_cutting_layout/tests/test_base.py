from __future__ import annotations

from sheet_cutting_layout.tests.base import FrappeTestCase, SheetCuttingLayoutTestCase


class TestSheetCuttingLayoutTestCase(FrappeTestCase):
	def test_base_extends_frappe_test_case(self) -> None:
		self.assertTrue(issubclass(SheetCuttingLayoutTestCase, FrappeTestCase))

	def test_base_does_not_register_class_cleanup_sweep(self) -> None:
		# Cleanup is handled by FrappeTestCase per-test rollback, not a custom sweep.
		import inspect

		self.assertNotIn("setUpClass", SheetCuttingLayoutTestCase.__dict__)
		source = inspect.getsource(SheetCuttingLayoutTestCase)
		self.assertNotIn("cleanup_test_records", source)

	def test_assert_float_almost_equal_helper_is_available(self) -> None:
		case = SheetCuttingLayoutTestCase()
		case.assertFloatAlmostEqual(0.1 + 0.2, 0.3)
