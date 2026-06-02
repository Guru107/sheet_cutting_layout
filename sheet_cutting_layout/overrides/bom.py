from __future__ import annotations

try:
	import frappe
except ImportError:

	class _ValidationError(Exception):
		pass

	class _FrappeCompat:
		ValidationError = _ValidationError

		@staticmethod
		def throw(message: str) -> None:
			raise _ValidationError(message)

	frappe = _FrappeCompat()

_ = getattr(frappe, "_", lambda message: message)


APP_CONTROLLED_BOM_UPDATE_FLAG = "sheet_cutting_layout_allow_bom_update"


def validate_shearing_bom_source(doc: object, method: str | None = None) -> None:
	if getattr(doc, "custom_operation", None) != "Shearing":
		return
	if _is_app_controlled_bom_update(doc):
		return
	if getattr(doc, "sheet_cutting_layout", None):
		frappe.throw(
			_(
				"This Shearing BOM is generated from a Sheet Cutting Layout. "
				"To change it, create a new Sheet Cutting Layout version."
			)
		)
	frappe.throw(_("Create a Sheet Cutting Layout to generate a Shearing BOM."))


def _is_app_controlled_bom_update(doc: object) -> bool:
	flags = getattr(doc, "flags", None)
	return bool(getattr(flags, APP_CONTROLLED_BOM_UPDATE_FLAG, False))
