from __future__ import annotations

import importlib
import importlib.util
from unittest.mock import patch

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


class _Meta:
	def __init__(self, existing_fields: set[str]) -> None:
		self.existing_fields = existing_fields

	def has_field(self, fieldname: str) -> bool:
		return fieldname in self.existing_fields


class TestInstall(SheetCuttingLayoutTestCase):
	def _install_module(self):
		self.assertIsNotNone(importlib.util.find_spec("sheet_cutting_layout.install"))
		return importlib.import_module("sheet_cutting_layout.install")

	def test_create_missing_bom_custom_fields_creates_both_fields_when_absent(self) -> None:
		install = self._install_module()
		calls = []

		self.start_patcher(patch.object(install.frappe, "get_meta", return_value=_Meta(set())))
		self.start_patcher(
			patch.object(
				install,
				"create_custom_fields",
				lambda fields, update: calls.append((fields, update)),
			)
		)

		install.create_missing_bom_custom_fields()

		self.assertEqual(calls, [({"BOM": install.BOM_CUSTOM_FIELDS}, False)])

	def test_create_missing_bom_custom_fields_preserves_existing_operation_field(self) -> None:
		install = self._install_module()
		calls = []

		self.start_patcher(
			patch.object(install.frappe, "get_meta", return_value=_Meta({"custom_operation"}))
		)
		self.start_patcher(
			patch.object(
				install,
				"create_custom_fields",
				lambda fields, update: calls.append((fields, update)),
			)
		)

		install.create_missing_bom_custom_fields()

		self.assertEqual(calls, [({"BOM": install.BOM_CUSTOM_FIELDS[1:]}, False)])

	def test_create_missing_bom_custom_fields_skips_when_all_fields_exist(self) -> None:
		install = self._install_module()
		calls = []

		self.start_patcher(
			patch.object(
				install.frappe,
				"get_meta",
				return_value=_Meta({"custom_operation", "sheet_cutting_layout"}),
			)
		)
		self.start_patcher(
			patch.object(
				install,
				"create_custom_fields",
				lambda fields, update: calls.append((fields, update)),
			)
		)

		install.create_missing_bom_custom_fields()

		self.assertEqual(calls, [])
