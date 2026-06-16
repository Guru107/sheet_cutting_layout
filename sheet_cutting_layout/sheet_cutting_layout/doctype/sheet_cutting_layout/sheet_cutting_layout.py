from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import ClassVar

import erpnext
import frappe
from frappe.model.document import Document

whitelist = frappe.whitelist
_ = frappe._

from sheet_cutting_layout.services.end_piece_bom_service import (
	generate_end_piece_boms,
)
from sheet_cutting_layout.services.export_service import (
	build_multi_sheet_workbook,
	walk_layout_tree,
)
from sheet_cutting_layout.services.release_service import (
	cancel_descendant_layouts,
	release_layout,
	retire_layout,
)
from sheet_cutting_layout.services.validators import apply_end_piece_bom_status, validate_sheet_cutting_layout
from sheet_cutting_layout.services.versioning import create_revision
from sheet_cutting_layout.services.workflow import (
	MR_RELEASE_ACTION,
	SUPERSEDE_ACTION,
	record_approval_snapshot,
)


class SheetCuttingLayout(Document):
	ignore_linked_doctypes: ClassVar[list[str]] = ["BOM"]

	def before_insert(self) -> None:
		_clear_copied_release_artifacts(self)

	def validate(self) -> None:
		validate_sheet_cutting_layout(self)

	def before_submit(self) -> None:
		if getattr(self, "status", None) != "Released":
			frappe.throw(_("Sheet Cutting Layout can be submitted only through MR Release"))
		if _previous_status(self) != "Approved by Purchase":
			frappe.throw(_("MR Release requires Approved by Purchase status"))
		_validate_workflow_approval_access(self, action=MR_RELEASE_ACTION)

	def on_submit(self) -> None:
		if getattr(self, "status", None) != "Released":
			return

		_record_workflow_snapshot(self, action=MR_RELEASE_ACTION)
		release_layout(self)

	def before_cancel(self) -> None:
		self.ignore_linked_doctypes = ["BOM", "Sheet Cutting Layout"]
		if getattr(self, "status", None) != "Superseded":
			frappe.throw(_("Sheet Cutting Layout can be cancelled only through Supersede"))
		_validate_workflow_approval_access(self, action=SUPERSEDE_ACTION)
		_record_workflow_snapshot(self, action=SUPERSEDE_ACTION)

	def on_cancel(self) -> None:
		cancel_descendant_layouts(self)
		retire_layout(self)

	def on_trash(self) -> None:
		_clear_rejected_workflow_actions(self)


def _clear_copied_release_artifacts(doc: object) -> None:
	if hasattr(doc, "generated_bom"):
		doc.generated_bom = None
	if hasattr(doc, "finished_parts"):
		doc.finished_parts = []
	if hasattr(doc, "approval_snapshot"):
		doc.approval_snapshot = []
	if hasattr(doc, "status"):
		doc.status = "Draft"
	if hasattr(doc, "is_active"):
		doc.is_active = False

	end_pieces = list(getattr(doc, "end_pieces", []) or [])
	for end_piece in end_pieces:
		if hasattr(end_piece, "end_piece_item_code"):
			end_piece.end_piece_item_code = None
		if hasattr(end_piece, "generated_end_piece_bom"):
			end_piece.generated_end_piece_bom = None
	if hasattr(doc, "end_piece_bom_status"):
		apply_end_piece_bom_status(doc, end_pieces)


def _record_workflow_snapshot(doc: object, *, action: str) -> None:
	record_approval_snapshot(
		doc,
		action=action,
		approver=_get_session_user(),
		decision_time=_get_now_datetime(),
	)


def _previous_status(doc: object) -> object:
	previous = getattr(doc, "_doc_before_save", None)
	get = getattr(previous, "get", None)
	if callable(get):
		return get("status")
	return None


def _validate_workflow_approval_access(doc: object, *, action: str) -> None:
	user = _get_session_user()
	owner = getattr(doc, "owner", None)
	if not user or user == "Administrator" or user != owner:
		return
	if _workflow_action_allows_self_approval(doc, action=action):
		return
	frappe.throw(_("Document owners cannot approve their own Sheet Cutting Layout workflow action"))


def _workflow_action_allows_self_approval(doc: object, *, action: str) -> bool:
	from frappe.model.workflow import get_workflow

	workflow = get_workflow(getattr(doc, "doctype", None) or "Sheet Cutting Layout")
	for transition in getattr(workflow, "transitions", []) or []:
		if getattr(transition, "action", None) == action:
			return bool(getattr(transition, "allow_self_approval", False))
	return False


def _clear_rejected_workflow_actions(doc: object) -> None:
	if getattr(doc, "status", None) != "Rejected":
		return

	doctype = getattr(doc, "doctype", "Sheet Cutting Layout")
	workflow_action_names = frappe.db.get_all(
		"Workflow Action",
		filters={"reference_doctype": doctype, "reference_name": doc.name},
		pluck="name",
	)
	if not workflow_action_names:
		return

	frappe.db.delete(
		"Workflow Action Permitted Role",
		{"parenttype": "Workflow Action", "parent": ["in", workflow_action_names]},
	)
	frappe.db.delete(
		"Workflow Action",
		{"reference_doctype": doctype, "reference_name": doc.name},
	)


def _get_session_user() -> str | None:
	session = getattr(frappe, "session", None)
	user = getattr(session, "user", None)
	return user if isinstance(user, str) else None


def _get_now_datetime() -> datetime:
	now_datetime = getattr(frappe, "now_datetime", None)
	if callable(now_datetime):
		return now_datetime()

	utils = getattr(frappe, "utils", None)
	now_datetime = getattr(utils, "now_datetime", None)
	if callable(now_datetime):
		return now_datetime()

	return datetime.now(tz=timezone.utc)


@whitelist()
def create_sheet_cutting_layout_revision(name: str) -> str:
	old_doc = frappe.get_doc("Sheet Cutting Layout", name)
	new_doc = create_revision(old_doc)
	new_doc.insert()
	return new_doc.name


@whitelist()
def generate_sheet_cutting_layout_end_piece_boms(name: str) -> dict[str, list[str]]:
	doc = frappe.get_doc("Sheet Cutting Layout", name)
	check_permission = getattr(doc, "check_permission", None)
	if callable(check_permission):
		check_permission("write")
	return generate_end_piece_boms(doc)


@whitelist()
def download_sheet_cutting_layout(name: str) -> None:
	doc = frappe.get_doc("Sheet Cutting Layout", name)
	check_permission = getattr(doc, "check_permission", None)
	if callable(check_permission):
		check_permission("read")

	def fetch_child(child_name: str) -> object:
		child = frappe.get_doc("Sheet Cutting Layout", child_name)
		child_check_permission = getattr(child, "check_permission", None)
		if callable(child_check_permission):
			child_check_permission("read")
		return child

	layouts = walk_layout_tree(doc, fetch_child)
	pages = [(layout.name, _export_layout_dict(layout)) for layout in layouts]
	workbook = build_multi_sheet_workbook(pages)
	stream = BytesIO()
	workbook.save(stream)
	frappe.response["filename"] = f"{doc.name}.xlsx"
	frappe.response["filecontent"] = stream.getvalue()
	frappe.response["type"] = "binary"


def _export_layout_dict(doc: object) -> dict[str, object]:
	finished_part_code = getattr(doc, "finished_part_code", None)
	part_numbers = [finished_part_code] if finished_part_code else []
	twin_finished_part = getattr(doc, "twin_finished_part", None)
	if getattr(doc, "is_lh_rh", None) and twin_finished_part:
		part_numbers.append(twin_finished_part)

	part_name = ""
	part_names = []
	if finished_part_code:
		part_name = frappe.get_cached_value("Item", finished_part_code, "item_name") or finished_part_code
		part_names.append(part_name)
	if getattr(doc, "is_lh_rh", None) and twin_finished_part:
		part_names.append(
			frappe.get_cached_value("Item", twin_finished_part, "item_name") or twin_finished_part
		)

	project = getattr(doc, "project", None)
	project_name = frappe.db.get_value("Project", project, "project_name") if project else ""
	raw_material_item = getattr(doc, "raw_material_item", None)
	raw_material_item_name = (
		frappe.get_cached_value("Item", raw_material_item, "item_name") or raw_material_item
		if raw_material_item
		else ""
	)

	return {
		"company": _default_company(),
		"layout_code": getattr(doc, "layout_code", None),
		"part_name": part_name,
		"part_names": part_names,
		"part_numbers": part_numbers,
		"is_lh_rh": bool(getattr(doc, "is_lh_rh", False)),
		"project": project,
		"project_name": project_name or "",
		"raw_material_item_name": raw_material_item_name,
		"sheet_thickness_mm": getattr(doc, "sheet_thickness_mm", None),
		"sheet_width_mm": getattr(doc, "sheet_width_mm", None),
		"sheet_length_mm": getattr(doc, "sheet_length_mm", None),
		"weight_per_sheet_kg": getattr(doc, "weight_per_sheet_kg", None),
		"weight_of_strip_kg": getattr(doc, "weight_of_strip_kg", None),
		"strip_thickness_mm": getattr(doc, "strip_thickness_mm", None),
		"strip_width_mm": getattr(doc, "strip_width_mm", None),
		"strip_length_mm": getattr(doc, "strip_length_mm", None),
		"parts_per_strip": getattr(doc, "parts_per_strip", None),
		"no_of_strips": getattr(doc, "no_of_strips", None),
		"parts_per_sheet": getattr(doc, "parts_per_sheet", None),
		"gross_weight_per_part_kg": getattr(doc, "gross_weight_per_part_kg", None),
		"net_weight_per_part_kg": getattr(doc, "net_weight_per_part_kg", None),
		"scrap_weight_per_part_kg": getattr(doc, "scrap_weight_per_part_kg", None),
		"end_pieces": [_export_end_piece_dict(row) for row in getattr(doc, "end_pieces", None) or []],
	}


def _export_end_piece_dict(row: object) -> dict[str, object]:
	return {
		"end_piece_item_code": getattr(row, "end_piece_item_code", None),
		"disposition": getattr(row, "disposition", None),
		"used_for_finished_part": getattr(row, "used_for_finished_part", None),
		"width_mm": getattr(row, "width_mm", None),
		"length_mm": getattr(row, "length_mm", None),
		"weight_kg": getattr(row, "weight_kg", None),
		"gross_weight_per_part_kg": getattr(row, "gross_weight_per_part_kg", None),
		"net_weight_per_part_kg": getattr(row, "net_weight_per_part_kg", None),
		"scrap_weight_per_part_kg": getattr(row, "scrap_weight_per_part_kg", None),
		"bom_quantity": getattr(row, "bom_quantity", None),
	}


def _default_company() -> str:
	return erpnext.get_default_company() or ""
