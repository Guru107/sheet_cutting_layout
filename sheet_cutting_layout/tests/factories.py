from __future__ import annotations

import atexit
from collections import defaultdict

import frappe
from frappe.utils import cint

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
	site = getattr(frappe.local, "site", None)
	if not site:
		return False
	if not getattr(frappe.local, "db", None):
		frappe.connect(site=site)
	return True


def _cancel_submitted_bom(name: str) -> None:
	# Submitted BOMs must be cancelled before deletion. Mirror the production
	# cancel path (release_service.cancel_generated_bom) by setting the
	# app-control flag so the before_cancel guard in overrides/bom.py allows it.
	from sheet_cutting_layout.overrides.bom import mark_bom_app_controlled

	doc = frappe.get_doc("BOM", name)
	mark_bom_app_controlled(doc)
	doc.cancel()


def delete_if_exists(doctype: str, name: str) -> None:
	if doctype == "Item" and not name.startswith(ITEM_CODE_PREFIX):
		return
	if doctype in {"Project", "Item Group", "UOM"} and not name.startswith(TEST_PREFIX):
		return
	if not frappe.db.exists(doctype, name):
		return
	try:
		if doctype == "BOM" and cint(frappe.db.get_value("BOM", name, "docstatus")) == 1:
			_cancel_submitted_bom(name)
		frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
	except Exception:
		pass


def get_prefixed_records(doctype: str) -> list[str]:
	if not frappe.db.table_exists(doctype):
		return []
	prefix = ITEM_CODE_PREFIX if doctype == "Item" else TEST_PREFIX
	return frappe.get_all(doctype, filters={"name": ["like", f"{prefix}%"]}, pluck="name")


def get_generated_test_boms() -> list[str]:
	# Generated BOMs are named like "BOM-SCLTEST..." (not "SCL-TEST-..."), so the
	# generic prefix sweep misses them. Sweep narrowly via the layout backlink
	# and the generated-name prefix only.
	if not frappe.db.table_exists("BOM"):
		return []
	names: set[str] = set()
	names.update(
		frappe.get_all(
			"BOM",
			filters={"sheet_cutting_layout": ["like", f"{TEST_PREFIX}%"]},
			pluck="name",
		)
	)
	names.update(
		frappe.get_all(
			"BOM",
			filters={"name": ["like", f"BOM-{ITEM_CODE_PREFIX}%"]},
			pluck="name",
		)
	)
	return sorted(names)


def cleanup_test_records() -> None:
	if not _ensure_connection():
		return

	for doctype in cleanup_order():
		for name in sorted(_created_docs.get(doctype, set()), reverse=True):
			delete_if_exists(doctype, name)
		if doctype == "BOM":
			for name in get_generated_test_boms():
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


def insert_if_missing(
	doc: dict[str, object],
	name_field: str,
	*,
	exists_filters: dict[str, object] | None = None,
) -> str:
	name = str(doc[name_field])
	existing_name = frappe.db.exists(str(doc["doctype"]), exists_filters or name)
	if existing_name:
		return str(existing_name)

	inserted = frappe.get_doc(doc).insert(ignore_permissions=True)
	register_test_doc(str(doc["doctype"]), inserted.name)
	return inserted.name


def ensure_item_group() -> str:
	return insert_if_missing(
		{
			"doctype": "Item Group",
			"item_group_name": "SCL-TEST-ITEM-GROUP",
			"parent_item_group": "All Item Groups",
			"is_group": 0,
		},
		"item_group_name",
	)


def ensure_project() -> str:
	return insert_if_missing(
		{"doctype": "Project", "project_name": "SCL-TEST-PROJECT"},
		"project_name",
		exists_filters={"project_name": "SCL-TEST-PROJECT"},
	)


def ensure_hsn_code(hsn_code: str) -> str:
	if not frappe.db.exists("DocType", "GST HSN Code"):
		raise RuntimeError("GST HSN Code DocType is not available on this site")
	return insert_if_missing({"doctype": "GST HSN Code", "hsn_code": hsn_code}, "hsn_code")


def ensure_item(item_code: str, *, stock_uom: str, valuation_rate: float = 1) -> str:
	doc: dict[str, object] = {
		"doctype": "Item",
		"item_code": item_code,
		"item_name": item_code,
		"item_group": ensure_item_group(),
		"stock_uom": stock_uom,
		"is_stock_item": 1,
		"valuation_rate": valuation_rate,
	}
	if frappe.get_meta("Item", cached=True).has_field("gst_hsn_code") and frappe.db.exists(
		"DocType", "GST HSN Code"
	):
		doc["gst_hsn_code"] = ensure_hsn_code("720810")
	return insert_if_missing(doc, "item_code")


def make_layout(
	*,
	finished_part_code: str,
	net_weight_per_part_kg: float = 0.289,
	generated_bom: str | None = None,
	**overrides: object,
):
	unique_suffix = frappe.generate_hash(length=8)
	project = ensure_project()
	raw_material_item = ensure_item("SCLTESTRM001", stock_uom="Kg")
	ensure_item(finished_part_code, stock_uom="Nos")
	values: dict[str, object] = {
		"doctype": "Sheet Cutting Layout",
		"layout_code": f"SCL-TEST-LAYOUT-{unique_suffix}",
		"project": project,
		"raw_material_item": raw_material_item,
		"process_scrap_item": raw_material_item,
		"sheet_thickness_mm": 1,
		"sheet_width_mm": 1250,
		"sheet_length_mm": 2500,
		"strip_thickness_mm": 1,
		"strip_width_mm": 1250,
		"strip_length_mm": 260,
		"parts_per_strip": 2,
		"no_of_strips": 1,
		"status": "Draft",
		"finished_part_code": finished_part_code,
		"net_weight_per_part_kg": net_weight_per_part_kg,
		"generated_bom": generated_bom,
		"finished_parts": [],
		"end_pieces": [],
	}
	values.update(overrides)
	return frappe.get_doc(values)
