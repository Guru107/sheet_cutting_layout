from __future__ import annotations

try:
	# Frappe v16's canonical base class; probe it first because v16 still ships
	# frappe.tests.utils.FrappeTestCase as a deprecated shim slated for removal.
	from frappe.tests import IntegrationTestCase as FrappeTestCase
except ImportError:  # Frappe v15 ships FrappeTestCase instead.
	from frappe.tests.utils import FrappeTestCase


class SheetCuttingLayoutTestCase(FrappeTestCase):
	@classmethod
	def setUpClass(cls) -> None:
		super().setUpClass()
		from sheet_cutting_layout.tests.factories import cleanup_test_records

		cls.addClassCleanup(cleanup_test_records)

	def assertFloatAlmostEqual(self, actual: float | int, expected: float | int, places: int = 6) -> None:
		self.assertAlmostEqual(float(actual), float(expected), places=places)
