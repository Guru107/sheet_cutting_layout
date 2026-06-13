from __future__ import annotations

try:
	# Frappe v16's canonical base class; probe it first because v16 still ships
	# frappe.tests.utils.FrappeTestCase as a deprecated shim slated for removal.
	from frappe.tests import IntegrationTestCase as FrappeTestCase
except ImportError:  # Frappe v15 ships FrappeTestCase instead.
	from frappe.tests.utils import FrappeTestCase


class SheetCuttingLayoutTestCase(FrappeTestCase):
	def start_patcher(self, patcher: object) -> object:
		"""Start a mock patcher and guarantee teardown, returning what start() returns."""
		started = patcher.start()
		self.addCleanup(patcher.stop)
		return started

	def assertFloatAlmostEqual(self, actual: float | int, expected: float | int, places: int = 6) -> None:
		self.assertAlmostEqual(float(actual), float(expected), places=places)
