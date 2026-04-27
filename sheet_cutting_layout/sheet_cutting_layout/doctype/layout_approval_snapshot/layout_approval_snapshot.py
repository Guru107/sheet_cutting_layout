from __future__ import annotations

try:
	from frappe.model.document import Document
except ImportError:

	class Document:
		pass


class LayoutApprovalSnapshot(Document):
	pass
