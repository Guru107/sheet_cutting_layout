from __future__ import annotations

import atexit
from collections import defaultdict

try:
	import frappe
except ImportError:
	frappe = None

TEST_PREFIX = "SCL-TEST-"
ITEM_CODE_PREFIX = "SCLTEST"

_created_docs: dict[str, set[str]] = defaultdict(set)
_cleanup_registered = False


def register_test_doc(doctype: str, name: str | None) -> None:
	if name:
		_created_docs[doctype].add(name)


def cleanup_order() -> list[str]:
	return [
		"BOM",
		"Sheet Cutting Layout",
		"Project",
		"Item",
		"Item Group",
		"UOM",
	]


def _ensure_connection() -> bool:
	if frappe is None:
		return False
	site = getattr(frappe.local, "site", None)
	if not site:
		return False
	if not getattr(frappe.local, "db", None):
		frappe.connect(site=site)
	return True


def delete_if_exists(doctype: str, name: str) -> None:
	if doctype == "Item" and not name.startswith(ITEM_CODE_PREFIX):
		return
	if doctype in {"Project", "Item Group", "UOM"} and not name.startswith(TEST_PREFIX):
		return
	if not frappe.db.exists(doctype, name):
		return
	try:
		frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
	except Exception:
		pass


def get_prefixed_records(doctype: str) -> list[str]:
	if not frappe.db.table_exists(doctype):
		return []
	prefix = ITEM_CODE_PREFIX if doctype == "Item" else TEST_PREFIX
	return frappe.get_all(doctype, filters={"name": ["like", f"{prefix}%"]}, pluck="name")


def cleanup_test_records() -> None:
	if not _ensure_connection():
		return

	for doctype in cleanup_order():
		for name in sorted(_created_docs.get(doctype, set()), reverse=True):
			delete_if_exists(doctype, name)
		for name in get_prefixed_records(doctype):
			delete_if_exists(doctype, name)

	frappe.db.commit()


def register_cleanup() -> None:
	global _cleanup_registered
	if not _cleanup_registered:
		atexit.register(cleanup_test_records)
		_cleanup_registered = True


register_cleanup()
