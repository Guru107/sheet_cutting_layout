from __future__ import annotations

import inspect

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase
from sheet_cutting_layout.overrides import bom as bom_override
from sheet_cutting_layout.services import (
	bom_service,
	end_piece_bom_service,
	end_piece_item_service,
	release_service,
	validators,
)


class TestServiceImports(SheetCuttingLayoutTestCase):
	def test_services_have_no_frappe_import_shim(self) -> None:
		for module in (
			validators,
			end_piece_item_service,
			end_piece_bom_service,
			release_service,
			bom_override,
		):
			with self.subTest(module=module.__name__):
				self.assertNotIn("except ImportError", inspect.getsource(module))

	def test_validators_throw_uses_real_frappe(self) -> None:
		import frappe

		with self.assertRaises(frappe.ValidationError):
			validators.validate_finished_part_code("not-alnum-!")

	def test_bom_service_remains_frappe_free_at_import(self) -> None:
		# Pure-domain module: no top-level `import frappe`.
		self.assertNotIn("\nimport frappe", inspect.getsource(bom_service))
