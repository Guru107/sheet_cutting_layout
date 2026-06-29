from __future__ import annotations

from unittest.mock import patch

from sheet_cutting_layout.overrides.bom import frappe, validate_shearing_bom_source
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


def _bom(
	operation: str,
	layout: str | None = None,
) -> object:
	return type(
		"BOM",
		(),
		{
			"custom_operation": operation,
			"sheet_cutting_layout": layout,
		},
	)()


class TestBomOverrides(SheetCuttingLayoutTestCase):
	def test_manual_shearing_bom_requires_sheet_cutting_layout_link(self) -> None:
		with self.assertRaisesRegex(frappe.ValidationError, "Create a Sheet Cutting Layout"):
			validate_shearing_bom_source(_bom("Shearing"), "before_insert")

	def test_linked_shearing_bom_insert_is_allowed(self) -> None:
		validate_shearing_bom_source(_bom("Shearing", "SCL-001"), "before_insert")

	def test_non_shearing_bom_is_unaffected(self) -> None:
		validate_shearing_bom_source(_bom("Machining"), "before_insert")

	def test_copied_shearing_bom_without_no_copy_layout_link_is_blocked(self) -> None:
		with self.assertRaisesRegex(frappe.ValidationError, "Create a Sheet Cutting Layout"):
			validate_shearing_bom_source(_bom("Shearing", None), "before_insert")

	def test_update_cost_style_resaves_are_allowed_for_layout_generated_bom(self) -> None:
		validate_shearing_bom_source(_bom("Shearing", "SCL-001"), "before_save")

	def test_cancel_is_blocked_for_layout_generated_bom(self) -> None:
		with self.assertRaisesRegex(
			frappe.ValidationError,
			"workflow instead of cancelling or amending this BOM",
		):
			validate_shearing_bom_source(_bom("Shearing", "SCL-001"), "before_cancel")

	def test_cancel_is_allowed_when_linked_layout_is_superseded(self) -> None:
		with patch.object(frappe.db, "get_value", return_value="Superseded") as get_value:
			validate_shearing_bom_source(_bom("Shearing", "SCL-001"), "before_cancel")

		get_value.assert_called_once_with("Sheet Cutting Layout", "SCL-001", "workflow_status")
