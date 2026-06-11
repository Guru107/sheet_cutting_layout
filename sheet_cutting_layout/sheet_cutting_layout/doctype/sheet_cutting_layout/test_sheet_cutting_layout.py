from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase
from sheet_cutting_layout.tests.factories import register_test_doc

from . import sheet_cutting_layout as controller


@dataclass
class _FakeLayoutDoc:
	name: str = "SCL-TEST-001"
	doctype: str = "Sheet Cutting Layout"
	check_permission_calls: list[str] | None = None
	inserted: bool = False

	def check_permission(self, permission_type: str) -> None:
		if self.check_permission_calls is None:
			self.check_permission_calls = []
		self.check_permission_calls.append(permission_type)

	def insert(self) -> None:
		self.inserted = True


def _insert_if_missing(
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


def _ensure_layout_dependencies() -> tuple[str, str]:
	item_group = _insert_if_missing(
		{
			"doctype": "Item Group",
			"item_group_name": "SCL-TEST-ITEM-GROUP",
			"parent_item_group": "All Item Groups",
			"is_group": 0,
		},
		"item_group_name",
	)
	project = _insert_if_missing(
		{
			"doctype": "Project",
			"project_name": "SCL-TEST-PROJECT",
		},
		"project_name",
		exists_filters={"project_name": "SCL-TEST-PROJECT"},
	)
	return item_group, project


def _ensure_hsn_code(hsn_code: str) -> str:
	if not frappe.db.exists("DocType", "GST HSN Code"):
		raise RuntimeError("GST HSN Code DocType is not available on this site")
	return _insert_if_missing(
		{
			"doctype": "GST HSN Code",
			"hsn_code": hsn_code,
		},
		"hsn_code",
	)


def _ensure_item(item_code: str, *, item_group: str, stock_uom: str) -> str:
	doc = {
		"doctype": "Item",
		"item_code": item_code,
		"item_name": item_code,
		"item_group": item_group,
		"stock_uom": stock_uom,
		"is_stock_item": 1,
		"valuation_rate": 1,
	}
	if frappe.get_meta("Item", cached=True).has_field("gst_hsn_code") and frappe.db.exists(
		"DocType", "GST HSN Code"
	):
		doc["gst_hsn_code"] = _ensure_hsn_code("720810")
	return _insert_if_missing(doc, "item_code")


def make_layout(
	*,
	finished_part_code: str,
	net_weight_per_part_kg: float,
	generated_bom: str | None,
) -> object:
	unique_suffix = frappe.generate_hash(length=8)
	item_group, project = _ensure_layout_dependencies()
	raw_material_item = _ensure_item("SCLTESTRM001", item_group=item_group, stock_uom="Kg")
	_ensure_item(finished_part_code, item_group=item_group, stock_uom="Nos")
	return frappe.get_doc(
		{
			"doctype": "Sheet Cutting Layout",
			"layout_code": f"SCL-TEST-PARENT-CONTRACT-{unique_suffix}",
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
	)


class TestSheetCuttingLayoutController(SheetCuttingLayoutTestCase):
	def test_validate_delegates_to_validator(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"

		with (
			patch.object(controller, "_get_selected_workflow_action", return_value=None),
			patch.object(controller, "validate_sheet_cutting_layout") as validate_sheet_cutting_layout,
		):
			doc.validate()

		validate_sheet_cutting_layout.assert_called_once_with(doc)

	def test_validate_mr_release_records_snapshot_and_release_once(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"

		with (
			patch.object(controller, "_get_selected_workflow_action", return_value="MR Release"),
			patch.object(controller, "record_approval_snapshot") as record_approval_snapshot,
			patch.object(controller, "release_layout") as release_layout,
			patch.object(controller, "validate_sheet_cutting_layout") as validate_sheet_cutting_layout,
			patch.object(controller, "_get_session_user", return_value="Administrator"),
			patch.object(controller, "_get_now_datetime", return_value="2026-05-28T12:00:00"),
		):
			doc.validate()

		record_approval_snapshot.assert_called_once()
		release_layout.assert_called_once_with(doc)
		validate_sheet_cutting_layout.assert_called_once_with(doc)

	def test_generate_end_piece_boms_checks_write_permission_and_calls_service(self) -> None:
		doc = _FakeLayoutDoc(name="SCL-TEST-002")
		calls: list[tuple[str, str]] = []

		class _FakeFrappe:
			@staticmethod
			def get_doc(doctype: str, name: str) -> _FakeLayoutDoc:
				calls.append((doctype, name))
				return doc

		with (
			patch.object(controller, "frappe", _FakeFrappe),
			patch.object(
				controller,
				"generate_end_piece_boms",
				return_value={"items": ["FG001SHR-EP-1x1250x260"], "boms": ["BOM-EP-001"]},
			) as generate_end_piece_boms,
		):
			result = controller.generate_sheet_cutting_layout_end_piece_boms("SCL-TEST-002")

		self.assertEqual(result["items"], ["FG001SHR-EP-1x1250x260"])
		self.assertEqual(result["boms"], ["BOM-EP-001"])
		self.assertEqual(calls, [("Sheet Cutting Layout", "SCL-TEST-002")])
		self.assertEqual(doc.check_permission_calls, ["write"])
		generate_end_piece_boms.assert_called_once_with(doc)

	def test_create_revision_inserts_new_doc_and_returns_name(self) -> None:
		old_doc = _FakeLayoutDoc(name="SCL-TEST-003")
		new_doc = _FakeLayoutDoc(name="SCL-TEST-003-R1")

		class _FakeFrappe:
			@staticmethod
			def get_doc(doctype: str, name: str) -> _FakeLayoutDoc:
				self.assertEqual(doctype, "Sheet Cutting Layout")
				self.assertEqual(name, "SCL-TEST-003")
				return old_doc

		with (
			patch.object(controller, "frappe", _FakeFrappe),
			patch.object(controller, "create_revision", return_value=new_doc) as create_revision,
		):
			revision_name = controller.create_sheet_cutting_layout_revision("SCL-TEST-003")

		self.assertTrue(new_doc.inserted)
		self.assertEqual(revision_name, "SCL-TEST-003-R1")
		create_revision.assert_called_once_with(old_doc)

	def test_apply_workflow_sets_selected_action_only_for_sheet_cutting_layout(self) -> None:
		flags = SimpleNamespace()
		parsed_doc = {"doctype": "Sheet Cutting Layout", "name": "SCL-TEST-004"}
		apply_workflow_calls: list[tuple[object, str, str | None]] = []

		def _fake_apply_workflow(doc: object, action: str) -> str:
			apply_workflow_calls.append((doc, action, getattr(flags, "selected_workflow_action", None)))
			return "ok"

		fake_frappe = SimpleNamespace(
			flags=flags,
			parse_json=lambda _doc: parsed_doc,
		)

		with (
			patch.object(controller, "frappe", fake_frappe),
			patch.object(
				controller, "import_module", return_value=SimpleNamespace(apply_workflow=_fake_apply_workflow)
			),
		):
			result = controller.apply_sheet_cutting_layout_workflow(
				{"doctype": "Sheet Cutting Layout"}, "MR Release"
			)

		self.assertEqual(result, "ok")
		self.assertEqual(
			apply_workflow_calls, [({"doctype": "Sheet Cutting Layout"}, "MR Release", "MR Release")]
		)
		self.assertFalse(hasattr(flags, "selected_workflow_action"))

	def test_parent_finished_part_inputs_persist_without_child_rows(self) -> None:
		layout = make_layout(
			finished_part_code="FG01SHR",
			net_weight_per_part_kg=0.289,
			generated_bom=None,
		)
		layout.parts_per_strip = 1
		layout.no_of_strips = 1
		layout.strip_length_mm = 2500

		layout.insert()
		register_test_doc("Sheet Cutting Layout", layout.name)
		layout.reload()

		self.assertEqual(layout.finished_part_code, "FG01SHR")
		self.assertEqual(layout.net_weight_per_part_kg, 0.289)
		self.assertFalse(layout.finished_parts)

	def test_parent_formulas_derive_weights_without_child_inputs(self) -> None:
		layout = make_layout(
			finished_part_code="FG01SHR",
			net_weight_per_part_kg=0.289,
			generated_bom=None,
		)
		layout.parts_per_strip = 1
		layout.no_of_strips = 1
		layout.strip_length_mm = 2500
		layout.insert()
		register_test_doc("Sheet Cutting Layout", layout.name)

		layout.parts_per_strip = 7
		layout.no_of_strips = 11
		layout.sheet_length_mm = 3713.6
		layout.strip_thickness_mm = 1
		layout.strip_width_mm = 1250
		layout.strip_length_mm = 337.6
		layout.net_weight_per_part_kg = 0.289
		layout.save()

		self.assertEqual(layout.parts_per_sheet, 77)
		self.assertAlmostEqual(layout.gross_weight_per_part_kg, 3.31692 / 7, places=6)
		self.assertAlmostEqual(
			layout.scrap_weight_per_part_kg,
			layout.gross_weight_per_part_kg - 0.289,
			places=6,
		)

	def test_mr_release_generates_native_bom_with_test_uom_items(self) -> None:
		layout = make_layout(
			finished_part_code=f"SCLTESTFG{frappe.generate_hash(length=5).upper()}SHR",
			net_weight_per_part_kg=0.289,
			generated_bom=None,
		)
		layout.parts_per_strip = 1
		layout.no_of_strips = 1
		layout.strip_length_mm = 2500
		layout.insert()
		register_test_doc("Sheet Cutting Layout", layout.name)
		layout.db_set("status", "Approved by Purchase", update_modified=False)
		layout.reload()
		layout.net_weight_per_part_kg = layout.gross_weight_per_part_kg

		with patch.object(controller, "_get_selected_workflow_action", return_value="MR Release"):
			layout.validate()

		self.assertEqual(layout.status, "Released")
		self.assertTrue(layout.generated_bom)
		register_test_doc("BOM", layout.generated_bom)

	def test_unreleased_layout_with_qty_per_sheet_gt_one_is_blocked_until_rows_are_split(
		self,
	) -> None:
		layout = make_layout(
			finished_part_code="FG01SHR",
			net_weight_per_part_kg=11.004,
			generated_bom=None,
		)
		layout.strip_length_mm = 2240
		layout.append(
			"end_pieces",
			{
				"width_mm": 1250,
				"length_mm": 260,
				"qty_per_sheet": 2,
				"disposition": "Reuse",
				"used_for_finished_part": "FG01SHR",
				"bom_quantity": 1,
				"bom_scrap_quantity_kg": 0,
			},
		)

		with self.assertRaisesRegex(frappe.ValidationError, "split into duplicate rows"):
			layout.insert()
