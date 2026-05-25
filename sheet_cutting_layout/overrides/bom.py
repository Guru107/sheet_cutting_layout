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


def validate_shearing_bom_source(doc: object, method: str | None = None) -> None:
	if getattr(doc, "custom_operation", None) != "Shearing":
		return
	if getattr(doc, "sheet_cutting_layout", None):
		return
	frappe.throw(_("Create a Sheet Cutting Layout to generate a Shearing BOM."))
