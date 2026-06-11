from __future__ import annotations

from datetime import datetime
from importlib import import_module

try:
	import frappe
	from frappe.model.document import Document

	whitelist = frappe.whitelist
except ImportError:
	frappe = None

	def whitelist():
		def decorator(function):
			function.whitelisted = True
			return function

		return decorator

	class Document:
		pass


_ = getattr(frappe, "_", lambda message: message)


from sheet_cutting_layout.services.end_piece_bom_service import (
	generate_end_piece_boms,
)
from sheet_cutting_layout.services.release_service import (
	cancel_generated_bom,
	deactivate_generated_bom,
	get_release_context,
	release_layout,
)
from sheet_cutting_layout.services.validators import apply_end_piece_bom_status, validate_sheet_cutting_layout
from sheet_cutting_layout.services.versioning import create_revision
from sheet_cutting_layout.services.workflow import record_approval_snapshot


class SheetCuttingLayout(Document):
	def before_insert(self) -> None:
		_clear_copied_release_artifacts(self)

	def before_workflow_action(self) -> None:
		action = _get_selected_workflow_action()
		self._apply_workflow_action_effects(action)

	def validate(self) -> None:
		action = _get_selected_workflow_action()
		self._apply_workflow_action_effects(action)
		validate_sheet_cutting_layout(self)

	def before_cancel(self) -> None:
		cancel_generated_bom(self)
		self.status = "Cancel"

	def on_trash(self) -> None:
		if getattr(self, "status", None) != "Rejected" or not frappe:
			return

		doctype = getattr(self, "doctype", "Sheet Cutting Layout")
		workflow_action_names = frappe.db.get_all(
			"Workflow Action",
			filters={"reference_doctype": doctype, "reference_name": self.name},
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
			{"reference_doctype": doctype, "reference_name": self.name},
		)

	def _apply_workflow_action_effects(self, action: str | None) -> None:
		if (
			action is None
			or _workflow_side_effects_are_suppressed()
			or getattr(self, "_sheet_cutting_layout_applied_workflow_action", None) == action
		):
			return

		self._sheet_cutting_layout_applied_workflow_action = action
		record_approval_snapshot(
			self,
			action=action,
			approver=_get_session_user(),
			decision_time=_get_now_datetime(),
		)
		context = get_release_context(self) if action == "MR Release" else None
		if action == "MR Release":
			with _suppress_workflow_side_effects():
				release_layout(self, release_context=context)
		if action == "Supersede":
			deactivate_generated_bom(self)


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


def _get_selected_workflow_action() -> str | None:
	if not frappe:
		return None

	flags = getattr(frappe, "flags", None)
	action = getattr(flags, "selected_workflow_action", None)
	if isinstance(action, str):
		return action

	form_dict = getattr(getattr(frappe, "local", None), "form_dict", None)
	action = getattr(form_dict, "workflow_action", None)
	if isinstance(action, str):
		return action
	action = getattr(form_dict, "action", None)
	if isinstance(action, str):
		return action

	return None


def _get_session_user() -> str | None:
	if not frappe:
		return None

	session = getattr(frappe, "session", None)
	user = getattr(session, "user", None)
	return user if isinstance(user, str) else None


def _get_now_datetime() -> datetime:
	if frappe:
		now_datetime = getattr(frappe, "now_datetime", None)
		if callable(now_datetime):
			return now_datetime()

		utils = getattr(frappe, "utils", None)
		now_datetime = getattr(utils, "now_datetime", None)
		if callable(now_datetime):
			return now_datetime()

	return datetime.now()


class _suppress_workflow_side_effects:
	def __enter__(self) -> None:
		self.flags = getattr(frappe, "flags", None) if frappe else None
		if self.flags is None:
			self.previous_value = None
			self.had_previous_value = False
			return

		self.previous_value = getattr(self.flags, "sheet_cutting_layout_suppress_workflow_side_effects", None)
		self.had_previous_value = hasattr(self.flags, "sheet_cutting_layout_suppress_workflow_side_effects")
		self.flags.sheet_cutting_layout_suppress_workflow_side_effects = True

	def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
		if self.flags is None:
			return

		if self.had_previous_value:
			self.flags.sheet_cutting_layout_suppress_workflow_side_effects = self.previous_value
		else:
			delattr(self.flags, "sheet_cutting_layout_suppress_workflow_side_effects")


def _workflow_side_effects_are_suppressed() -> bool:
	if not frappe:
		return False

	flags = getattr(frappe, "flags", None)
	return bool(getattr(flags, "sheet_cutting_layout_suppress_workflow_side_effects", False))


@whitelist()
def apply_sheet_cutting_layout_workflow(doc: object, action: str) -> object:
	if not frappe:
		raise RuntimeError("Frappe is required to apply Sheet Cutting Layout workflow")

	frappe_workflow = import_module("frappe.model.workflow")
	apply_workflow = frappe_workflow.apply_workflow
	parsed_doc = frappe.parse_json(doc)
	doctype = (
		parsed_doc.get("doctype") if isinstance(parsed_doc, dict) else getattr(parsed_doc, "doctype", None)
	)
	if doctype != "Sheet Cutting Layout":
		return apply_workflow(doc, action)

	flags = getattr(frappe, "flags", None)
	previous_action = getattr(flags, "selected_workflow_action", None)
	had_previous_action = hasattr(flags, "selected_workflow_action")
	flags.selected_workflow_action = action
	try:
		return apply_workflow(doc, action)
	finally:
		if had_previous_action:
			flags.selected_workflow_action = previous_action
		else:
			delattr(flags, "selected_workflow_action")


@whitelist()
def create_sheet_cutting_layout_revision(name: str) -> str:
	if not frappe:
		raise RuntimeError("Frappe is required to create Sheet Cutting Layout revisions")

	old_doc = frappe.get_doc("Sheet Cutting Layout", name)
	new_doc = create_revision(old_doc)
	new_doc.insert()
	return new_doc.name


@whitelist()
def generate_sheet_cutting_layout_end_piece_boms(name: str) -> dict[str, list[str]]:
	if not frappe:
		raise RuntimeError("Frappe is required to generate End Piece BOMs")

	doc = frappe.get_doc("Sheet Cutting Layout", name)
	check_permission = getattr(doc, "check_permission", None)
	if callable(check_permission):
		check_permission("write")
	return generate_end_piece_boms(doc)
