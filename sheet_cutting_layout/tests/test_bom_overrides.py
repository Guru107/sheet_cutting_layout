from __future__ import annotations

import pytest

from sheet_cutting_layout.overrides.bom import frappe, validate_shearing_bom_source


def _bom(operation: str, layout: str | None = None) -> object:
	return type(
		"BOM",
		(),
		{
			"custom_operation": operation,
			"sheet_cutting_layout": layout,
			"flags": type("Flags", (), {})(),
		},
	)()


def test_manual_shearing_bom_requires_sheet_cutting_layout_link() -> None:
	with pytest.raises(frappe.ValidationError, match="Create a Sheet Cutting Layout"):
		validate_shearing_bom_source(_bom("Shearing"), None)


def test_generated_shearing_bom_with_layout_link_is_allowed() -> None:
	validate_shearing_bom_source(_bom("Shearing", "SCL-001"), None)


def test_non_shearing_bom_is_unaffected() -> None:
	validate_shearing_bom_source(_bom("Machining"), None)


def test_copied_shearing_bom_without_no_copy_layout_link_is_blocked() -> None:
	with pytest.raises(frappe.ValidationError, match="Create a Sheet Cutting Layout"):
		validate_shearing_bom_source(_bom("Shearing", None), None)
