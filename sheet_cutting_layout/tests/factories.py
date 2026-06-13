from __future__ import annotations

import frappe

ITEM_CODE_PREFIX = "SCLTEST"


def register_test_doc(doctype: str, name: str | None) -> None:
	"""No-op kept for call-site compatibility.

	FrappeTestCase rolls back the database after each test, so explicitly
	created docs do not need to be tracked or swept.
	"""
	return None


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
	"""Build an UNINSERTED Sheet Cutting Layout doc; callers must insert() it and
	register_test_doc("Sheet Cutting Layout", doc.name) themselves. Item/Project
	prerequisites are inserted here."""
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


def make_release_ready_layout(*, finished_part_code: str | None = None, **overrides: object):
	"""Insert a registered layout and put it in the release-gate state
	(status Approved by Purchase, net weight equal to gross)."""
	if finished_part_code is None:
		suffix = frappe.generate_hash(length=5).upper()
		finished_part_code = f"{ITEM_CODE_PREFIX}FG{suffix}SHR"
	layout = make_layout(
		finished_part_code=finished_part_code,
		parts_per_strip=1,
		no_of_strips=1,
		strip_length_mm=2500,
		**overrides,
	)
	layout.insert()
	register_test_doc("Sheet Cutting Layout", layout.name)
	layout.db_set("status", "Approved by Purchase", update_modified=False)
	# Persist the release-gate weight too, so re-fetching the record by name also
	# yields a release-ready document (db_set keeps the in-memory value in sync).
	layout.db_set(
		"net_weight_per_part_kg",
		layout.gross_weight_per_part_kg,
		update_modified=False,
	)
	layout.reload()
	return layout
