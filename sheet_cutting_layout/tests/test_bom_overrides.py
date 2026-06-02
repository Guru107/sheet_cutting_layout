from __future__ import annotations

from sheet_cutting_layout.overrides.bom import frappe, validate_shearing_bom_source
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


def _bom(
	operation: str,
	layout: str | None = None,
	*,
	allow_app_update: bool = False,
	changed_fields: set[str] | None = None,
	is_new: bool = False,
) -> object:
	flags = type("Flags", (), {})()
	if allow_app_update:
		flags.sheet_cutting_layout_allow_bom_update = True

	def has_value_changed(fieldname: str) -> bool:
		return changed_fields is None or fieldname in changed_fields

	return type(
		"BOM",
		(),
		{
			"custom_operation": operation,
			"sheet_cutting_layout": layout,
			"flags": flags,
			"is_new": lambda self: is_new,
			"has_value_changed": staticmethod(has_value_changed),
		},
	)()


class TestBomOverrides(SheetCuttingLayoutTestCase):
	def test_manual_shearing_bom_requires_sheet_cutting_layout_link(self) -> None:
		with self.assertRaisesRegex(frappe.ValidationError, "Create a Sheet Cutting Layout"):
			validate_shearing_bom_source(_bom("Shearing"), None)

	def test_app_generated_shearing_bom_with_layout_link_is_allowed(self) -> None:
		validate_shearing_bom_source(_bom("Shearing", "SCL-001", allow_app_update=True), None)

	def test_non_shearing_bom_is_unaffected(self) -> None:
		validate_shearing_bom_source(_bom("Machining"), None)

	def test_copied_shearing_bom_without_no_copy_layout_link_is_blocked(self) -> None:
		with self.assertRaisesRegex(frappe.ValidationError, "Create a Sheet Cutting Layout"):
			validate_shearing_bom_source(_bom("Shearing", None), None)

	def test_manual_edit_to_layout_generated_bom_is_blocked(self) -> None:
		with self.assertRaisesRegex(
			frappe.ValidationError,
			"create a new Sheet Cutting Layout version",
		):
			validate_shearing_bom_source(_bom("Shearing", "SCL-001", changed_fields={"quantity"}), None)

	def test_erpnext_new_version_of_layout_generated_bom_is_blocked(self) -> None:
		with self.assertRaisesRegex(
			frappe.ValidationError,
			"create a new Sheet Cutting Layout version",
		):
			validate_shearing_bom_source(_bom("Shearing", "SCL-001", is_new=True), None)
