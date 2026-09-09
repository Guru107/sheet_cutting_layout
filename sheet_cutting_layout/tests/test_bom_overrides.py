from __future__ import annotations

from unittest.mock import patch

from sheet_cutting_layout.overrides.bom import frappe, validate_generated_shearing_bom_lifecycle
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


def _bom(
	operation: str,
	layout: str | None = None,
	*,
	amended_from: str | None = None,
) -> object:
	return type(
		"BOM",
		(),
		{
			"custom_operation": operation,
			"sheet_cutting_layout": layout,
			"amended_from": amended_from,
		},
	)()


class TestBomOverrides(SheetCuttingLayoutTestCase):
	def test_manual_shearing_bom_insert_is_allowed(self) -> None:
		validate_generated_shearing_bom_lifecycle(_bom("Shearing"), "before_insert")

	def test_linked_shearing_bom_insert_is_allowed(self) -> None:
		validate_generated_shearing_bom_lifecycle(_bom("Shearing", "SCL-001"), "before_insert")

	def test_non_shearing_bom_is_unaffected(self) -> None:
		validate_generated_shearing_bom_lifecycle(_bom("Machining"), "before_insert")

	def test_copied_shearing_bom_without_layout_link_is_allowed(self) -> None:
		validate_generated_shearing_bom_lifecycle(_bom("Shearing", None), "before_insert")

	def test_amendment_of_layout_generated_shearing_bom_is_blocked(self) -> None:
		with (
			patch.object(frappe.db, "get_value", return_value="SCL-001") as get_value,
			self.assertRaisesRegex(frappe.ValidationError, "workflow instead of.*amending"),
		):
			validate_generated_shearing_bom_lifecycle(
				_bom("Shearing", amended_from="BOM-SCL-001"),
				"before_insert",
			)

		get_value.assert_any_call("BOM", "BOM-SCL-001", "sheet_cutting_layout")

	def test_amendment_of_manual_shearing_bom_is_allowed(self) -> None:
		with patch.object(frappe.db, "get_value", return_value=None) as get_value:
			validate_generated_shearing_bom_lifecycle(
				_bom("Shearing", amended_from="BOM-MANUAL"),
				"before_insert",
			)

		get_value.assert_called_once_with("BOM", "BOM-MANUAL", "sheet_cutting_layout")

	def test_update_cost_style_resaves_are_allowed_for_layout_generated_bom(self) -> None:
		validate_generated_shearing_bom_lifecycle(_bom("Shearing", "SCL-001"), "before_save")

	def test_cancel_is_blocked_for_layout_generated_bom(self) -> None:
		with self.assertRaisesRegex(
			frappe.ValidationError,
			"workflow instead of cancelling or amending this BOM",
		):
			validate_generated_shearing_bom_lifecycle(_bom("Shearing", "SCL-001"), "before_cancel")

	def test_cancel_is_allowed_when_linked_layout_is_superseded(self) -> None:
		with patch.object(frappe.db, "get_value", return_value="Superseded") as get_value:
			validate_generated_shearing_bom_lifecycle(_bom("Shearing", "SCL-001"), "before_cancel")

		get_value.assert_called_once_with("Sheet Cutting Layout", "SCL-001", "workflow_status")
