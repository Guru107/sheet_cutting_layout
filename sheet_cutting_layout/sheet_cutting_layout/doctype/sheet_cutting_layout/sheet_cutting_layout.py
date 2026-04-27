from __future__ import annotations

try:
	import frappe
	from frappe.model.document import Document
except ImportError:
	frappe = None

	class Document:
		pass


from sheet_cutting_layout.services.validators import validate_sheet_cutting_layout
from sheet_cutting_layout.services.workflow import apply_checker_action


class SheetCuttingLayout(Document):
	def before_workflow_action(self) -> None:
		action = _get_selected_workflow_action()
		if action is not None:
			apply_checker_action(self, action)

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
