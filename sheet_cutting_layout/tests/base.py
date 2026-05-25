from __future__ import annotations

from unittest import TestCase

try:
	from frappe.tests.utils import FrappeTestCase as _FrappeTestCase
except ImportError:
	_FrappeTestCase = TestCase


class SheetCuttingLayoutTestCase(_FrappeTestCase):
	@classmethod
	def setUpClass(cls) -> None:
		super().setUpClass()
		try:
			from sheet_cutting_layout.tests.factories import cleanup_test_records
		except Exception:
			return
		cls.addClassCleanup(cleanup_test_records)

	def assertFloatAlmostEqual(self, actual: float | int, expected: float | int, places: int = 6) -> None:
		self.assertAlmostEqual(float(actual), float(expected), places=places)
