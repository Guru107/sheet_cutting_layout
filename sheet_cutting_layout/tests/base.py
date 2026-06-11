from __future__ import annotations

try:
	from frappe.tests.utils import FrappeTestCase
except ImportError:  # Frappe v16 renamed the integration base class.
	from frappe.tests import IntegrationTestCase as FrappeTestCase


class SheetCuttingLayoutTestCase(FrappeTestCase):
	@classmethod
	def setUpClass(cls) -> None:
		super().setUpClass()
		from sheet_cutting_layout.tests.factories import cleanup_test_records

		cls.addClassCleanup(cleanup_test_records)

	def assertFloatAlmostEqual(self, actual: float | int, expected: float | int, places: int = 6) -> None:
		self.assertAlmostEqual(float(actual), float(expected), places=places)
