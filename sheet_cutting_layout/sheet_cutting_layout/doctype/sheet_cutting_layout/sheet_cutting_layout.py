from __future__ import annotations

from datetime import datetime

import frappe
from frappe.model.document import Document

whitelist = frappe.whitelist
_ = frappe._

from sheet_cutting_layout.services.end_piece_bom_service import (
	generate_end_piece_boms,
)
from sheet_cutting_layout.services.release_service import (
	cancel_generated_bom as retire_layout,
	release_layout,
)
from sheet_cutting_layout.services.validators import apply_end_piece_bom_status, validate_sheet_cutting_layout
from sheet_cutting_layout.services.versioning import create_revision
from sheet_cutting_layout.services.workflow import MR_RELEASE_ACTION, SUPERSEDE_ACTION, record_approval_snapshot


class SheetCuttingLayout(Document):
	ignore_linked_doctypes = ["BOM"]

	def before_insert(self) -> None:
		_clear_copied_release_artifacts(self)

	def validate(self) -> None:
		validate_sheet_cutting_layout(self)

	def on_submit(self) -> None:
		if getattr(self, "status", None) != "Released":
			return

		_record_workflow_snapshot(self, action=MR_RELEASE_ACTION)
		release_layout(self)

	def before_cancel(self) -> None:
		_record_workflow_snapshot(self, action=SUPERSEDE_ACTION)

	def on_cancel(self) -> None:
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

	return datetime.now()


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
