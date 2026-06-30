from __future__ import annotations

import frappe

ALLOW_ALTERNATIVE_ITEM_FIELD = "allow_alternative_item"


def set_allow_alternative_item_if_supported(doc: object) -> bool:
	if not _field_is_supported(doc, ALLOW_ALTERNATIVE_ITEM_FIELD):
		return False
	setattr(doc, ALLOW_ALTERNATIVE_ITEM_FIELD, 1)
	return True


def with_bom_item_allow_alternative_item(
	bom_doc: object,
	table_fieldname: str,
	values: dict[str, object],
) -> dict[str, object]:
	row = dict(values)
	if _child_table_field_is_supported(
		bom_doc,
		table_fieldname,
		ALLOW_ALTERNATIVE_ITEM_FIELD,
	):
		row[ALLOW_ALTERNATIVE_ITEM_FIELD] = 1
	return row


def ensure_item_allows_alternatives(item_code: object) -> bool:
	clean_item_code = _clean(item_code)
	if clean_item_code is None:
		return False
	if not _doctype_field_is_supported("Item", ALLOW_ALTERNATIVE_ITEM_FIELD):
		return False
	frappe.db.set_value("Item", clean_item_code, ALLOW_ALTERNATIVE_ITEM_FIELD, 1)
	return True


def _field_is_supported(doc: object, fieldname: str) -> bool:
	meta = getattr(doc, "meta", None)
	has_field = getattr(meta, "has_field", None)
	if callable(has_field):
		return bool(has_field(fieldname))

	doctype = _clean(getattr(doc, "doctype", None))
	if doctype is not None:
		return _doctype_field_is_supported(doctype, fieldname)

	return False


def _child_table_field_is_supported(
	parent_doc: object,
	table_fieldname: str,
	child_fieldname: str,
) -> bool:
	parent_meta = getattr(parent_doc, "meta", None)
	get_field = getattr(parent_meta, "get_field", None)
	if not callable(get_field):
		return False

	table_field = get_field(table_fieldname)
	child_doctype = _clean(getattr(table_field, "options", None))
	if child_doctype is None:
		return False

	return _doctype_field_is_supported(child_doctype, child_fieldname)


def _doctype_field_is_supported(doctype: str, fieldname: str) -> bool:
	meta = frappe.get_meta(doctype)
	has_field = getattr(meta, "has_field", None)
	return bool(callable(has_field) and has_field(fieldname))


def _clean(value: object) -> str | None:
	if value is None:
		return None
	if isinstance(value, str):
		value = value.strip()
		return value or None
	return str(value)
