from __future__ import annotations

from frappe.tests.utils import FrappeTestCase

import sheet_cutting_layout.hooks as hooks


class TestFixturesScope(FrappeTestCase):
	def test_custom_field_fixture_is_scoped_to_bom(self) -> None:
		custom_field_fixtures = [
			fixture
			for fixture in hooks.fixtures
			if isinstance(fixture, dict) and fixture.get("dt") == "Custom Field"
		]
		self.assertTrue(custom_field_fixtures)
		for fixture in custom_field_fixtures:
			filters = fixture["filters"]
			flattened = str(filters)
			self.assertNotIn("Work Order", flattened)
			self.assertNotIn("Production Plan", flattened)
