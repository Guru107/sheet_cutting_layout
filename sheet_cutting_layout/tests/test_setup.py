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


def _ensure_test_holiday_list() -> None:
	if frappe.db.exists("Holiday List", "_Test Holiday List"):
		return

	frappe.get_doc(
		{
			"doctype": "Holiday List",
			"holiday_list_name": "_Test Holiday List",
			"from_date": "2013-01-01",
			"to_date": "2013-12-31",
			"holidays": [{"description": "New Year", "holiday_date": "2013-01-01"}],
		}
	).insert(ignore_permissions=True)


def _ensure_company_record() -> None:
	company = frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {}, "name")
	if not company:
		_ensure_test_holiday_list()
		company = (
			frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": "_Test Company",
					"abbr": "_TC",
					"country": "India",
					"default_currency": "INR",
					"domain": "Manufacturing",
					"chart_of_accounts": "Standard",
					"default_holiday_list": "_Test Holiday List",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	frappe.defaults.set_global_default("company", company)
	currency = frappe.db.get_value("Company", company, "default_currency")
	if currency:
		frappe.defaults.set_global_default("currency", currency)


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
	_ensure_company_record()
	_ensure_gender_records()
	_ensure_transit_warehouse_type()
	# This app's tests create their live records explicitly. Frappe's automatic
	# dependency records can conflict with installed regional compliance apps.
	frappe.flags.skip_test_records = True
	frappe.db.commit()  # nosemgrep: frappe-manual-commit - test bootstrap seed must persist
