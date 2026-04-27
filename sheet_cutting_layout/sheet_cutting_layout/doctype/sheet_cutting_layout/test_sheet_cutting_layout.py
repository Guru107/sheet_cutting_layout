from __future__ import annotations

import json
from pathlib import Path
from typing import TypeAlias

JSONValue: TypeAlias = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
DocTypeJSON: TypeAlias = dict[str, JSONValue]
FieldJSON: TypeAlias = dict[str, JSONValue]

DOCTYPE_ROOT = Path(__file__).resolve().parents[1]


def test_sheet_cutting_layout_doctypes_define_normalized_model() -> None:
	parent = load_doctype("sheet_cutting_layout", "sheet_cutting_layout")

	assert parent["name"] == "Sheet Cutting Layout"
	assert parent["module"] == "Sheet Cutting Layout"

	parent_fields = fields_by_name(parent)
	assert {
		"layout_code",
		"layout_family",
		"revision_no",
		"raw_material_item",
		"sheet_thickness_mm",
		"sheet_width_mm",
		"sheet_length_mm",
		"weight_per_sheet_kg",
		"strip_thickness_mm",
		"strip_width_mm",
		"strip_length_mm",
		"weight_of_strip_kg",
		"parts_per_strip",
		"no_of_strips",
		"parts_per_sheet",
		"status",
	}.issubset(parent_fields)
	assert_float_fields(
		parent_fields,
		{
			"strip_thickness_mm",
			"strip_width_mm",
			"strip_length_mm",
			"weight_of_strip_kg",
		},
	)
	assert_int_fields(parent_fields, {"parts_per_strip", "no_of_strips", "parts_per_sheet"})

	assert_table_field(parent_fields["finished_parts"], "Layout Finished Part")
	assert_table_field(parent_fields["end_pieces"], "Layout End Piece")
	assert_table_field(parent_fields["approval_snapshot"], "Layout Approval Snapshot")
	assert_table_field(parent_fields["impact_resolutions"], "Layout Impact Resolution")

	assert_child_doctype_fields(
		"layout_finished_part",
		"layout_finished_part",
		"Layout Finished Part",
		{
			"finished_part_item",
			"parts_per_sheet",
			"gross_weight_per_part_kg",
			"scrap_weight_per_part_kg",
			"generated_bom",
		},
	)
	assert_child_doctype_fields(
		"layout_end_piece",
		"layout_end_piece",
		"Layout End Piece",
		{"end_piece_item", "weight_kg", "qty_per_sheet", "disposition", "used_for_finished_part"},
	)
	assert_child_doctype_fields(
		"layout_approval_snapshot",
		"layout_approval_snapshot",
		"Layout Approval Snapshot",
		{"step_name", "approver", "decision", "comment", "decision_time"},
	)
	assert_child_doctype_fields(
		"layout_impact_resolution",
		"layout_impact_resolution",
		"Layout Impact Resolution",
		{
			"reference_doctype",
			"reference_docname",
			"old_bom",
			"new_bom",
			"decision",
			"decided_by",
			"decided_on",
			"status",
		},
	)


def load_doctype(directory: str, filename: str) -> DocTypeJSON:
	doctype_path = DOCTYPE_ROOT / directory / f"{filename}.json"
	assert doctype_path.exists(), f"Missing DocType JSON: {doctype_path}"
	loaded = json.loads(doctype_path.read_text(encoding="utf-8"))
	assert isinstance(loaded, dict)
	return loaded


def fields_by_name(doctype: DocTypeJSON) -> dict[str, FieldJSON]:
	fields = doctype.get("fields")
	assert isinstance(fields, list)

	field_map: dict[str, FieldJSON] = {}
	for field in fields:
		assert isinstance(field, dict)
		fieldname = field.get("fieldname")
		assert isinstance(fieldname, str)
		field_map[fieldname] = field
	return field_map


def assert_table_field(field: FieldJSON, options: str) -> None:
	assert field.get("fieldtype") == "Table"
	assert field.get("options") == options


def assert_float_fields(fields: dict[str, FieldJSON], fieldnames: set[str]) -> None:
	for fieldname in fieldnames:
		assert fields[fieldname].get("fieldtype") == "Float"


def assert_int_fields(fields: dict[str, FieldJSON], fieldnames: set[str]) -> None:
	for fieldname in fieldnames:
		assert fields[fieldname].get("fieldtype") == "Int"


def assert_child_doctype_fields(directory: str, filename: str, name: str, required_fields: set[str]) -> None:
	doctype = load_doctype(directory, filename)
	assert doctype["name"] == name
	assert doctype["module"] == "Sheet Cutting Layout"
	assert doctype["istable"] == 1
	assert required_fields.issubset(fields_by_name(doctype))
