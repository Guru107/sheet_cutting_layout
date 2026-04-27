from __future__ import annotations

try:
	from frappe.model.document import Document
except ImportError:

	class Document:
		pass


from sheet_cutting_layout.services.validators import validate_sheet_cutting_layout


class SheetCuttingLayout(Document):
	def validate(self) -> None:
		validate_sheet_cutting_layout(self)
