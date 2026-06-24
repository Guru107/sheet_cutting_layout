from __future__ import annotations

from importlib import import_module

import frappe


def _call_erpnext_before_tests() -> None:
	try:
		erpnext_setup_utils = import_module("erpnext.setup.utils")
	except ImportError:
		return

	before_tests = getattr(erpnext_setup_utils, "before_tests", None)
	if callable(before_tests):
		before_tests()


def _ensure_erpnext_test_master_data() -> None:
	if frappe.db.a_row_exists("Company"):
		return

	try:
		import_module("erpnext.tests.utils")
	except ImportError:
		return


def _ensure_gender_records() -> None:
	for gender in ("Male", "Female", "Other"):
		if frappe.db.exists("Gender", gender):
			continue
		frappe.get_doc({"doctype": "Gender", "gender": gender}).insert(ignore_permissions=True)


def _ensure_transit_warehouse_type() -> None:
	if frappe.db.exists("Warehouse Type", "Transit"):
		return

	frappe.get_doc(
		{
			"doctype": "Warehouse Type",
			"name": "Transit",
			"description": "Transit Warehouse",
		}
	).insert(ignore_permissions=True)


def before_tests() -> None:
	"""Bootstrap missing ERPNext test records for CI test-site runs."""
	_call_erpnext_before_tests()
	_ensure_erpnext_test_master_data()
	_ensure_gender_records()
	_ensure_transit_warehouse_type()
	# This app's tests create their live records explicitly. Frappe's automatic
	# dependency records can conflict with installed regional compliance apps.
	frappe.flags.skip_test_records = True
	frappe.db.commit()  # nosemgrep: frappe-manual-commit - test bootstrap seed must persist
