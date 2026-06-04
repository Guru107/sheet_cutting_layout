from __future__ import annotations

from sheet_cutting_layout.overrides.bom import frappe, validate_shearing_bom_source
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


def _bom(
	operation: str,
	layout: str | None = None,
	*,
	allow_app_update: bool = False,
) -> object:
	flags = type("Flags", (), {})()
	if allow_app_update:
		flags.sheet_cutting_layout_allow_bom_update = True

	return type(
		"BOM",
		(),
		{
			"custom_operation": operation,
			"sheet_cutting_layout": layout,
			"flags": flags,
		},
	)()


class TestBomOverrides(SheetCuttingLayoutTestCase):
	def test_manual_shearing_bom_requires_sheet_cutting_layout_link(self) -> None:
		with self.assertRaisesRegex(frappe.ValidationError, "Create a Sheet Cutting Layout"):
			validate_shearing_bom_source(_bom("Shearing"), "before_insert")

	def test_app_generated_shearing_bom_with_layout_link_is_allowed(self) -> None:
		validate_shearing_bom_source(_bom("Shearing", "SCL-001", allow_app_update=True), "before_insert")

	def test_non_shearing_bom_is_unaffected(self) -> None:
		validate_shearing_bom_source(_bom("Machining"), "before_insert")

	def test_copied_shearing_bom_without_no_copy_layout_link_is_blocked(self) -> None:
		with self.assertRaisesRegex(frappe.ValidationError, "Create a Sheet Cutting Layout"):
			validate_shearing_bom_source(_bom("Shearing", None), "before_insert")

	def test_update_cost_style_resaves_are_allowed_for_layout_generated_bom(self) -> None:
		validate_shearing_bom_source(_bom("Shearing", "SCL-001"), "before_save")

	def test_manual_insert_with_layout_link_is_blocked(self) -> None:
		with self.assertRaisesRegex(
			frappe.ValidationError,
			"create a new Sheet Cutting Layout version",
		):
			validate_shearing_bom_source(_bom("Shearing", "SCL-001"), "before_insert")

	def test_cancel_is_blocked_for_layout_generated_bom(self) -> None:
		with self.assertRaisesRegex(
			frappe.ValidationError,
			"workflow instead of cancelling or amending this BOM",
		):
			validate_shearing_bom_source(_bom("Shearing", "SCL-001"), "before_cancel")
