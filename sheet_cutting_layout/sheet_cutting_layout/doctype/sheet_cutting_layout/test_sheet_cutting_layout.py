from __future__ import annotations

import json
from pathlib import Path
from typing import TypeAlias

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase
from sheet_cutting_layout.tests.unittest_adapter import add_pytest_style_tests

JSONValue: TypeAlias = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
DocTypeJSON: TypeAlias = dict[str, JSONValue]
FieldJSON: TypeAlias = dict[str, JSONValue]

DOCTYPE_ROOT = Path(__file__).resolve().parents[1]


def test_sheet_cutting_layout_doctypes_define_normalized_model() -> None:
	parent = load_doctype("sheet_cutting_layout", "sheet_cutting_layout")

	assert parent["name"] == "Sheet Cutting Layout"
	assert parent["module"] == "Sheet Cutting Layout"
	assert parent.get("is_submittable") == 1

	parent_fields = fields_by_name(parent)
	assert {
		"layout_code",
		"project",
		"revision_no",
		"is_active",
		"based_on_layout",
		"raw_material_item",
		"process_scrap_item",
		"sheet_thickness_mm",
		"sheet_width_mm",
		"sheet_length_mm",
		"weight_per_sheet_kg",
		"consumed_weight_kg",
		"leftover_weight_kg",
		"consumption_status",
		"end_piece_bom_status",
		"strip_thickness_mm",
		"strip_width_mm",
		"strip_length_mm",
		"weight_of_strip_kg",
		"gross_weight_per_part_kg",
		"parts_per_strip",
		"no_of_strips",
		"parts_per_sheet",
		"status",
		"project_manager_ok",
		"manufacturing_manager_ok",
	}.issubset(parent_fields)
	assert_float_fields(
		parent_fields,
		{
			"strip_thickness_mm",
			"strip_width_mm",
			"strip_length_mm",
			"weight_of_strip_kg",
			"gross_weight_per_part_kg",
			"consumed_weight_kg",
			"leftover_weight_kg",
		},
	)
	assert_int_fields(parent_fields, {"parts_per_strip", "no_of_strips", "parts_per_sheet"})
	assert_check_fields(parent_fields, {"is_active", "project_manager_ok", "manufacturing_manager_ok"})
	assert parent_fields["project"]["fieldtype"] == "Link"
	assert parent_fields["project"]["options"] == "Project"
	assert parent_fields["project"].get("reqd") == 1
	assert parent_fields["based_on_layout"]["fieldtype"] == "Link"
	assert parent_fields["based_on_layout"]["options"] == "Sheet Cutting Layout"
	assert parent_fields["based_on_layout"].get("read_only") == 1
	assert "layout_family" not in parent_fields
	assert parent_fields["weight_per_sheet_kg"].get("read_only") == 1
	assert parent_fields["weight_of_strip_kg"].get("read_only") == 1
	assert parent_fields["gross_weight_per_part_kg"].get("read_only") == 1
	assert parent_fields["parts_per_sheet"].get("read_only") == 1
	assert parent_fields["consumed_weight_kg"].get("read_only") == 1
	assert parent_fields["consumed_weight_kg"].get("precision") == "3"
	assert parent_fields["leftover_weight_kg"].get("read_only") == 1
	assert parent_fields["leftover_weight_kg"].get("precision") == "3"
	assert parent_fields["consumption_status"].get("read_only") == 1
	assert parent_fields["consumption_status"].get("options") == "Balanced\nShort\nExcess"
	assert parent_fields["end_piece_bom_status"]["fieldtype"] == "Select"
	assert parent_fields["end_piece_bom_status"].get("read_only") == 1
	assert parent_fields["end_piece_bom_status"].get("options") == "Not Required\nPending\nGenerated"

	assert_table_field(parent_fields["finished_parts"], "Layout Finished Part")
	assert_table_field(parent_fields["end_pieces"], "Layout End Piece")
	assert_table_field(parent_fields["approval_snapshot"], "Layout Approval Snapshot")
	assert "impact_resolutions" not in parent_fields

	assert_child_doctype_fields(
		"layout_finished_part",
		"layout_finished_part",
		"Layout Finished Part",
		{
			"finished_part_item",
			"parts_per_sheet",
			"net_weight_per_part_kg",
			"gross_weight_per_part_kg",
			"scrap_weight_per_part_kg",
			"generated_bom",
		},
	)
	finished_part = load_doctype("layout_finished_part", "layout_finished_part")
	finished_part_fields = fields_by_name(finished_part)
	assert finished_part_fields["parts_per_sheet"].get("read_only") == 1
	assert finished_part_fields["net_weight_per_part_kg"]["fieldtype"] == "Float"
	assert finished_part_fields["net_weight_per_part_kg"].get("reqd") == 1
	assert finished_part_fields["gross_weight_per_part_kg"].get("read_only") == 1
	assert finished_part_fields["scrap_weight_per_part_kg"].get("read_only") == 1
	assert_child_doctype_fields(
		"layout_end_piece",
		"layout_end_piece",
		"Layout End Piece",
		{
			"end_piece_item_code",
			"generated_end_piece_item",
			"width_mm",
			"length_mm",
			"weight_kg",
			"qty_per_sheet",
			"disposition",
			"scrap_item",
			"used_for_finished_part",
			"bom_quantity",
			"bom_scrap_quantity_kg",
			"generated_end_piece_bom",
		},
	)
	end_piece = load_doctype("layout_end_piece", "layout_end_piece")
	end_piece_fields = fields_by_name(end_piece)
	assert "end_piece_item" not in end_piece_fields
	assert end_piece_fields["end_piece_item_code"]["fieldtype"] == "Data"
	assert end_piece_fields["end_piece_item_code"].get("in_list_view") == 1
	assert end_piece_fields["generated_end_piece_item"]["fieldtype"] == "Link"
	assert end_piece_fields["generated_end_piece_item"]["options"] == "Item"
	assert end_piece_fields["generated_end_piece_item"].get("read_only") == 1
	assert end_piece_fields["width_mm"]["fieldtype"] == "Float"
	assert end_piece_fields["length_mm"]["fieldtype"] == "Float"
	assert end_piece_fields["weight_kg"]["fieldtype"] == "Float"
	assert end_piece_fields["weight_kg"].get("read_only") == 1
	assert end_piece_fields["qty_per_sheet"]["fieldtype"] == "Float"
	assert end_piece_fields["disposition"]["fieldtype"] == "Select"
	assert end_piece_fields["scrap_item"]["fieldtype"] == "Link"
	assert end_piece_fields["scrap_item"]["options"] == "Item"
	assert end_piece_fields["used_for_finished_part"]["fieldtype"] == "Link"
	assert end_piece_fields["used_for_finished_part"]["options"] == "Item"
	assert end_piece_fields["bom_quantity"]["fieldtype"] == "Float"
	assert end_piece_fields["bom_scrap_quantity_kg"]["fieldtype"] == "Float"
	assert end_piece_fields["generated_end_piece_bom"]["fieldtype"] == "Link"
	assert end_piece_fields["generated_end_piece_bom"]["options"] == "BOM"
	assert end_piece_fields["generated_end_piece_bom"].get("read_only") == 1
	assert "thickness" not in end_piece_fields
	assert_child_doctype_fields(
		"layout_approval_snapshot",
		"layout_approval_snapshot",
		"Layout Approval Snapshot",
		{"step_name", "approver", "decision", "comment", "decision_time"},
	)
	approval_snapshot = load_doctype("layout_approval_snapshot", "layout_approval_snapshot")
	assert "Submitted" in str(fields_by_name(approval_snapshot)["decision"].get("options"))


def test_workflow_fixture_uses_submitted_docstatus_only_for_released_layout() -> None:
	workflow = load_workflow_fixture()
	states = workflow.get("states")
	assert isinstance(states, list)

	for state in states:
		assert isinstance(state, dict)
		expected_docstatus = "1" if state.get("state") in {"Released", "Superseded"} else "0"
		assert state.get("doc_status") == expected_docstatus


def test_released_workflow_state_keeps_required_allow_edit_role_for_fixture_import() -> None:
	workflow = load_workflow_fixture()
	states = workflow.get("states")
	assert isinstance(states, list)

	states_by_name = {state.get("state"): state for state in states if isinstance(state, dict)}

	assert states_by_name["Released"].get("allow_edit") == "System Manager"


def test_submitted_workflow_fields_allow_supersede_after_submit() -> None:
	parent = load_doctype("sheet_cutting_layout", "sheet_cutting_layout")
	fields = fields_by_name(parent)

	assert fields["status"].get("allow_on_submit") == 1
	assert fields["is_active"].get("allow_on_submit") == 1


def test_sheet_cutting_layout_uses_project_as_version_group() -> None:
	parent = load_doctype("sheet_cutting_layout", "sheet_cutting_layout")
	fields = fields_by_name(parent)

	assert fields["project"]["fieldtype"] == "Link"
	assert fields["project"]["options"] == "Project"
	assert fields["project"]["reqd"] == 1
	assert fields["based_on_layout"]["fieldtype"] == "Link"
	assert fields["based_on_layout"]["options"] == "Sheet Cutting Layout"
	assert fields["based_on_layout"]["read_only"] == 1
	assert "layout_family" not in fields


def test_workflow_uses_existing_projects_manager_role_for_checker_approval() -> None:
	workflow = load_workflow_fixture()
	transitions = workflow.get("transitions")
	assert isinstance(transitions, list)

	allowed_by_action = {
		transition.get("action"): transition.get("allowed")
		for transition in transitions
		if isinstance(transition, dict)
	}

	assert allowed_by_action["Projects Manager Approves"] == "Projects Manager"
	assert "Project Manager" not in allowed_by_action.values()


def test_checker_workflow_actions_require_projects_manager_before_manufacturing_manager() -> None:
	workflow = load_workflow_fixture()
	transitions = workflow.get("transitions")
	assert isinstance(transitions, list)

	project_manager_transitions = transitions_for_action(transitions, "Projects Manager Approves")
	manufacturing_manager_transitions = transitions_for_action(transitions, "Manufacturing Manager Approves")

	assert {
		(transition.get("next_state"), transition.get("condition"))
		for transition in project_manager_transitions
	} == {
		("Submitted for Check", "not doc.project_manager_ok and not doc.manufacturing_manager_ok"),
	}
	assert {
		(transition.get("next_state"), transition.get("condition"))
		for transition in manufacturing_manager_transitions
	} == {
		("Checked", "doc.project_manager_ok and not doc.manufacturing_manager_ok"),
	}
	assert not transitions_for_action(transitions, "Mark Checked")


def test_client_workflow_action_does_not_pre_save_checker_flags() -> None:
	client_script = (DOCTYPE_ROOT / "sheet_cutting_layout" / "sheet_cutting_layout.js").read_text(
		encoding="utf-8"
	)

	assert "before_workflow_action(frm)" in client_script
	assert "Projects Manager Approves" in client_script
	assert "Manufacturing Manager Approves" in client_script
	assert "CHECKER_ACTION_FLAGS" not in client_script
	assert "project_manager_ok" not in client_script
	assert "manufacturing_manager_ok" not in client_script
	before_start = client_script.index("before_workflow_action(frm)")
	after_start = client_script.index("after_workflow_action(frm)")
	before_workflow_block = client_script[before_start:after_start]
	assert "frm.set_value" not in before_workflow_block
	assert "frm.save()" not in before_workflow_block


def test_client_workflow_action_records_approval_snapshot_after_successful_action() -> None:
	client_script = (DOCTYPE_ROOT / "sheet_cutting_layout" / "sheet_cutting_layout.js").read_text(
		encoding="utf-8"
	)

	assert "after_workflow_action(frm)" in client_script
	assert "frm.reload_doc()" in client_script
	assert 'frm.add_child("approval_snapshot")' not in client_script


def test_list_view_enables_bulk_delete_for_workflow_records() -> None:
	list_script = (DOCTYPE_ROOT / "sheet_cutting_layout" / "sheet_cutting_layout_list.js").read_text(
		encoding="utf-8"
	)

	assert 'frappe.listview_settings["Sheet Cutting Layout"]' in list_script
	assert "allow_edit: true" in list_script
	assert "listview.list_view_settings.allow_edit = true" in list_script
	assert "listview.page.clear_actions_menu()" in list_script
	assert "listview.set_actions_menu_items()" in list_script


def test_client_recalculates_sheet_weight_from_dimensions() -> None:
	client_script = (DOCTYPE_ROOT / "sheet_cutting_layout" / "sheet_cutting_layout.js").read_text(
		encoding="utf-8"
	)

	assert "calculateSheetWeight" in client_script
	assert "STEEL_DENSITY_G_PER_CM3 = 7.86" in client_script
	assert "STEEL_DENSITY_G_PER_CM3 = 7.850000" not in client_script
	assert "frappe.boot.sysdefaults.float_precision" in client_script
	assert "getSteelDensity()" in client_script
	assert "toFixed(getFloatPrecision())" in client_script
	assert "weight_per_sheet_kg" in client_script


def test_client_recalculates_strip_weight_from_dimensions() -> None:
	client_script = (DOCTYPE_ROOT / "sheet_cutting_layout" / "sheet_cutting_layout.js").read_text(
		encoding="utf-8"
	)

	assert "updateStripWeight" in client_script
	assert "strip_thickness_mm" in client_script
	assert "strip_width_mm" in client_script
	assert "strip_length_mm" in client_script
	assert "weight_of_strip_kg" in client_script


def test_client_updates_consumption_tracking_when_user_enters_dimensions_and_net_weight() -> None:
	client_script = (DOCTYPE_ROOT / "sheet_cutting_layout" / "sheet_cutting_layout.js").read_text(
		encoding="utf-8"
	)

	assert "updateConsumptionTracking" in client_script
	assert "calculateConsumptionTracking" in client_script
	assert "updateFinishedPartWeights" in client_script
	assert "updateEndPieceWeights" in client_script
	assert "updatePartsPerSheet" in client_script
	assert "preview_sheet_cutting_layout_end_piece_boms" in client_script
	assert "generate_sheet_cutting_layout_end_piece_boms" in client_script
	assert "Preview End Piece Items" in client_script
	assert "Generate End Piece BOMs" in client_script
	assert "end_piece_item_code" in client_script
	assert "suggested_item_code" in client_script
	assert "Current Item Code" in client_script
	assert "Suggested Item Code" in client_script
	assert "generated_end_piece_bom" in client_script
	assert "hasRequiredEndPiecePreviewInputs" in client_script
	assert "raw_material_item: updateEndPieceItemCodesFromForm" in client_script
	assert "numberOrZero(row.weight_kg)" in client_script
	assert "numberOrZero(row.weight_kg) * numberOrZero(row.qty_per_sheet)" not in client_script
	assert "row.finished_part_item" in client_script
	assert "consumed_weight_kg" in client_script
	assert "leftover_weight_kg" in client_script
	assert "consumption_status" in client_script
	assert "net_weight_per_part_kg: updateFinishedPartWeightsAndConsumption" in client_script
	assert "finished_part_item: updatePartsPerSheetAndDerivedFields" in client_script
	assert "parts_per_strip: updatePartsPerSheetAndDerivedFields" in client_script
	assert "no_of_strips: updatePartsPerSheetAndDerivedFields" in client_script
	assert "width_mm: updateEndPieceWeightsAndConsumption" in client_script
	assert "length_mm: updateEndPieceWeightsAndConsumption" in client_script
	assert "qty_per_sheet: updateEndPieceWeightsAndConsumption" in client_script
	assert "disposition: updateEndPieceItemCodesFromForm" in client_script


def test_client_has_no_sheet_layout_canvas_dependency() -> None:
	client_script = (DOCTYPE_ROOT / "sheet_cutting_layout" / "sheet_cutting_layout.js").read_text(
		encoding="utf-8"
	)

	assert "sheet_layout_canvas.js" not in client_script
	assert "SheetLayoutCanvas" not in client_script
	assert "sheet-layout-canvas-preview" not in client_script
	assert "ensurePreviewCanvas" not in client_script
	assert "redrawSheetLayout" not in client_script
	assert "scheduleSheetLayoutRedraw" not in client_script
	assert "frappe.require" not in client_script


def test_client_preview_dialog_uses_local_escape_html_helper() -> None:
	client_script = (DOCTYPE_ROOT / "sheet_cutting_layout" / "sheet_cutting_layout.js").read_text(
		encoding="utf-8"
	)
	preview_start = client_script.index("function buildEndPiecePreviewHtml(rows)")
	preview_end = client_script.index('frappe.ui.form.on("Sheet Cutting Layout"', preview_start)
	preview_block = client_script[preview_start:preview_end]

	assert "function escapeHtml(value)" in client_script
	assert "frappe.utils.escape_html" not in client_script
	assert "escapeHtml(" in preview_block


def test_client_refresh_does_not_dirty_saved_documents_with_weight_recalculation() -> None:
	client_script = (DOCTYPE_ROOT / "sheet_cutting_layout" / "sheet_cutting_layout.js").read_text(
		encoding="utf-8"
	)
	refresh_start = client_script.index("refresh(frm) {")
	before_workflow_start = client_script.index("before_workflow_action(frm)")
	refresh_block = client_script[refresh_start:before_workflow_start]

	assert "updateSheetWeight(frm)" not in refresh_block
	assert "updateStripWeight(frm)" not in refresh_block


def test_client_adds_new_version_button_for_released_and_superseded_layouts() -> None:
	client_script = (DOCTYPE_ROOT / "sheet_cutting_layout" / "sheet_cutting_layout.js").read_text(
		encoding="utf-8"
	)

	assert 'frm.add_custom_button(__("New Version")' in client_script
	assert '["Released", "Superseded"].includes(frm.doc.status)' in client_script
	assert "create_sheet_cutting_layout_revision" in client_script
	assert 'frappe.set_route("Form", "Sheet Cutting Layout", r.message)' in client_script


def test_sheet_cutting_layout_form_uses_two_column_sections_for_parent_fields() -> None:
	parent = load_doctype("sheet_cutting_layout", "sheet_cutting_layout")
	field_order = parent.get("field_order")
	assert isinstance(field_order, list)

	for section, column_break in {
		"identity_section": "identity_column_break",
		"material_section": "material_column_break",
		"strip_section": "strip_column_break",
		"workflow_section": "workflow_column_break",
	}.items():
		assert section in field_order
		assert column_break in field_order
		assert field_order.index(section) < field_order.index(column_break)

	fields = fields_by_name(parent)
	assert fields["identity_section"]["fieldtype"] == "Section Break"
	assert fields["identity_column_break"]["fieldtype"] == "Column Break"
	assert fields["material_section"]["fieldtype"] == "Section Break"
	assert fields["material_column_break"]["fieldtype"] == "Column Break"
	assert fields["strip_section"]["fieldtype"] == "Section Break"
	assert fields["strip_column_break"]["fieldtype"] == "Column Break"
	assert fields["workflow_section"]["fieldtype"] == "Section Break"
	assert fields["workflow_column_break"]["fieldtype"] == "Column Break"
	assert fields["tables_section"]["fieldtype"] == "Section Break"


def test_workflow_states_are_exported_as_master_records() -> None:
	workflow_states = load_workflow_states_fixture()
	workflow = load_workflow_fixture()
	states = workflow.get("states")
	assert isinstance(states, list)

	expected_states = {state["state"] for state in states if isinstance(state.get("state"), str)}
	exported_states = {state.get("name") for state in workflow_states}

	assert expected_states.issubset(exported_states)


def test_child_doctypes_have_controller_modules_for_frappe_sync() -> None:
	for directory, filename in (
		("layout_finished_part", "layout_finished_part"),
		("layout_end_piece", "layout_end_piece"),
		("layout_approval_snapshot", "layout_approval_snapshot"),
	):
		controller_path = DOCTYPE_ROOT / directory / f"{filename}.py"
		assert controller_path.exists(), f"Missing DocType controller: {controller_path}"


def load_doctype(directory: str, filename: str) -> DocTypeJSON:
	doctype_path = DOCTYPE_ROOT / directory / f"{filename}.json"
	assert doctype_path.exists(), f"Missing DocType JSON: {doctype_path}"
	loaded = json.loads(doctype_path.read_text(encoding="utf-8"))
	assert isinstance(loaded, dict)
	return loaded


def load_workflow_fixture() -> DocTypeJSON:
	fixture_path = DOCTYPE_ROOT.parents[1] / "fixtures" / "workflow.json"
	loaded = json.loads(fixture_path.read_text(encoding="utf-8"))
	assert isinstance(loaded, list)
	assert len(loaded) == 1
	workflow = loaded[0]
	assert isinstance(workflow, dict)
	return workflow


def load_workflow_states_fixture() -> list[DocTypeJSON]:
	fixture_path = DOCTYPE_ROOT.parents[1] / "fixtures" / "workflow_state.json"
	loaded = json.loads(fixture_path.read_text(encoding="utf-8"))
	assert isinstance(loaded, list)
	for state in loaded:
		assert isinstance(state, dict)
	return loaded


def transitions_for_action(transitions: list[JSONValue], action: str) -> list[DocTypeJSON]:
	matching = [
		transition
		for transition in transitions
		if isinstance(transition, dict) and transition.get("action") == action
	]
	return matching


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


def assert_check_fields(fields: dict[str, FieldJSON], fieldnames: set[str]) -> None:
	for fieldname in fieldnames:
		assert fields[fieldname].get("fieldtype") == "Check"


def assert_child_doctype_fields(directory: str, filename: str, name: str, required_fields: set[str]) -> None:
	doctype = load_doctype(directory, filename)
	assert doctype["name"] == name
	assert doctype["module"] == "Sheet Cutting Layout"
	assert doctype["istable"] == 1
	assert required_fields.issubset(fields_by_name(doctype))


class TestSheetCuttingLayoutSourceContract(SheetCuttingLayoutTestCase):
	pass


add_pytest_style_tests(globals(), TestSheetCuttingLayoutSourceContract)
