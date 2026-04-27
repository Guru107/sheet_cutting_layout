from __future__ import annotations

try:
	import frappe
	from frappe.model.document import Document
except ImportError:
	frappe = None

	class Document:
		pass


from sheet_cutting_layout.services.release_service import (
	finalize_release,
	get_release_context,
	release_layout,
)
from sheet_cutting_layout.services.validators import validate_sheet_cutting_layout
from sheet_cutting_layout.services.workflow import apply_checker_action


class SheetCuttingLayout(Document):
	def before_workflow_action(self) -> None:
		action = _get_selected_workflow_action()
		if action is not None:
			apply_checker_action(self, action)
		context = (
			get_release_context(self)
			if action
			in {
				"MR Release",
				"MR Release With Impact",
				"Finalize Impact Release",
			}
			else None
		)
		if action in {"MR Release", "MR Release With Impact"}:
			result = release_layout(self, release_context=context)
			if frappe is not None and action == "MR Release" and result.status == "Release Pending Impact":
				frappe.throw("Use MR Release With Impact when open manufacturing documents are impacted")
			if frappe is not None and action == "MR Release With Impact" and result.status == "Released":
				frappe.throw("Use MR Release when no open manufacturing documents are impacted")
		if action == "Finalize Impact Release" and context is not None:
			result = finalize_release(
				self, layouts=context.layouts, boms=context.boms if context.boms is not None else ()
			)
			if frappe is not None and result.status == "Release Pending Impact":
				frappe.throw("Resolve all impact decisions before final release")

	def validate(self) -> None:
		validate_sheet_cutting_layout(self)


def _get_selected_workflow_action() -> str | None:
	if frappe is None:
		return None

	flags = getattr(frappe, "flags", None)
	action = getattr(flags, "selected_workflow_action", None)
	if isinstance(action, str):
		return action

	form_dict = getattr(getattr(frappe, "local", None), "form_dict", None)
	action = getattr(form_dict, "workflow_action", None)
	if isinstance(action, str):
		return action

	return None
