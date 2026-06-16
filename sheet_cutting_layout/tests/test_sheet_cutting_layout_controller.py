from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import (
	sheet_cutting_layout as controller,
)
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase
from sheet_cutting_layout.tests.factories import (
	ensure_item,
	make_layout,
	make_release_ready_layout,
)


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


@dataclass
class _PreviousDoc:
	status: str

	def get(self, fieldname: str) -> object:
		return getattr(self, fieldname, None)


class TestSheetCuttingLayoutController(SheetCuttingLayoutTestCase):
	def _ensure_project(self, project_name: str) -> str:
		existing = frappe.db.exists("Project", {"project_name": project_name})
		if existing:
			return str(existing)
		return (
			frappe.get_doc({"doctype": "Project", "project_name": project_name})
			.insert(ignore_permissions=True)
			.name
		)

	def _ensure_project_manager_user(self, email: str, project: str) -> str:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "SCL Export Permission",
				"enabled": 1,
				"send_welcome_email": 0,
				"new_password": frappe.generate_hash(length=12),
			}
		)
		user.flags.ignore_password_policy = True
		user.insert(ignore_permissions=True)
		user.add_roles("Project Manager")
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": email,
				"allow": "Project",
				"for_value": project,
				"applicable_for": "Sheet Cutting Layout",
			}
		).insert(ignore_permissions=True)
		return email

	def test_validate_only_runs_validator_no_workflow_side_effects(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"

		with patch.object(controller, "validate_sheet_cutting_layout") as validate:
			doc.validate()

		validate.assert_called_once_with(doc)
		self.assertFalse(hasattr(controller.SheetCuttingLayout, "before_workflow_action"))
		self.assertFalse(hasattr(controller, "apply_sheet_cutting_layout_workflow"))

	def test_on_submit_releases_and_snapshots_when_status_released(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"
		doc.name = "SCL-TEST-RELEASE"
		doc.status = "Released"

		with (
			patch.object(controller, "release_layout") as release,
			patch.object(controller, "_insert_approval_snapshot_row") as snapshot,
			patch.object(controller, "_get_session_user", return_value="Administrator"),
			patch.object(controller, "_get_now_datetime", return_value=datetime(2026, 6, 13, 12, 0, 0)),
		):
			doc.on_submit()

		release.assert_called_once_with(doc)
		snapshot.assert_called_once_with(
			doc,
			row={
				"step_name": "MR Approval",
				"approver": "Administrator",
				"decision": "Approved",
				"decision_time": datetime(2026, 6, 13, 12, 0, 0),
			},
		)

	def test_on_submit_does_not_snapshot_or_release_when_not_released(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"
		doc.status = "Approved by Purchase"

		with (
			patch.object(controller, "release_layout") as release,
			patch.object(controller, "_insert_approval_snapshot_row") as snapshot,
		):
			doc.on_submit()

		release.assert_not_called()
		snapshot.assert_not_called()

	def test_before_submit_allows_mr_release_only_after_purchase_approval(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"
		doc.status = "Released"
		doc._doc_before_save = _PreviousDoc(status="Approved by Purchase")

		with patch.object(controller.frappe, "throw") as throw:
			doc.before_submit()

		throw.assert_not_called()

	def test_before_submit_rejects_non_release_status(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"
		doc.status = "Approved by Purchase"
		doc._doc_before_save = _PreviousDoc(status="Approved by Purchase")

		with (
			patch.object(controller.frappe, "throw", side_effect=Exception("release required")),
			self.assertRaisesRegex(Exception, "release required"),
		):
			doc.before_submit()

	def test_before_submit_rejects_owner_self_approval_on_native_submit(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"
		doc.owner = "mr@example.com"
		doc.status = "Released"
		doc._doc_before_save = _PreviousDoc(status="Approved by Purchase")

		with (
			patch.object(controller, "_get_session_user", return_value="mr@example.com"),
			patch.object(
				controller, "_workflow_action_allows_self_approval", return_value=False
			) as allows_self,
			patch.object(controller.frappe, "throw", side_effect=Exception("self approval blocked")),
			self.assertRaisesRegex(Exception, "self approval blocked"),
		):
			doc.before_submit()

		allows_self.assert_called_once_with(doc, action="MR Release")

	def test_before_submit_allows_administrator_owner_without_self_approval_lookup(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"
		doc.owner = "Administrator"
		doc.status = "Released"
		doc._doc_before_save = _PreviousDoc(status="Approved by Purchase")

		with (
			patch.object(controller, "_get_session_user", return_value="Administrator"),
			patch.object(controller, "_workflow_action_allows_self_approval") as allows_self,
			patch.object(controller.frappe, "throw") as throw,
		):
			doc.before_submit()

		allows_self.assert_not_called()
		throw.assert_not_called()

	def test_before_submit_allows_non_owner_without_self_approval_lookup(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"
		doc.owner = "owner@example.com"
		doc.status = "Released"
		doc._doc_before_save = _PreviousDoc(status="Approved by Purchase")

		with (
			patch.object(controller, "_get_session_user", return_value="mr@example.com"),
			patch.object(controller, "_workflow_action_allows_self_approval") as allows_self,
			patch.object(controller.frappe, "throw") as throw,
		):
			doc.before_submit()

		allows_self.assert_not_called()
		throw.assert_not_called()

	def test_before_submit_allows_owner_when_transition_allows_self_approval(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"
		doc.owner = "mr@example.com"
		doc.status = "Released"
		doc._doc_before_save = _PreviousDoc(status="Approved by Purchase")

		with (
			patch.object(controller, "_get_session_user", return_value="mr@example.com"),
			patch.object(controller, "_workflow_action_allows_self_approval", return_value=True),
			patch.object(controller.frappe, "throw") as throw,
		):
			doc.before_submit()

		throw.assert_not_called()

	def test_before_submit_rejects_direct_release_without_purchase_approval(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"
		doc.status = "Released"
		doc._doc_before_save = _PreviousDoc(status="Draft")

		with (
			patch.object(controller.frappe, "throw", side_effect=Exception("MR Release requires approval")),
			self.assertRaisesRegex(Exception, "MR Release requires approval"),
		):
			doc.before_submit()

	def test_before_submit_rejects_release_without_previous_status(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"
		doc.status = "Released"

		with (
			patch.object(controller.frappe, "throw", side_effect=Exception("MR Release requires approval")),
			self.assertRaisesRegex(Exception, "MR Release requires approval"),
		):
			doc.before_submit()

	def test_before_cancel_snapshots_supersede(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"
		doc.name = "SCL-TEST-SUPERSEDE"
		doc.status = "Superseded"

		with (
			patch.object(controller, "_insert_approval_snapshot_row") as snapshot,
			patch.object(controller, "_get_session_user", return_value="Administrator"),
			patch.object(controller, "_get_now_datetime", return_value=datetime(2026, 6, 13, 12, 0, 0)),
		):
			doc.before_cancel()

		snapshot.assert_called_once_with(
			doc,
			row={
				"step_name": "Supersession",
				"approver": "Administrator",
				"decision": "Approved",
				"decision_time": datetime(2026, 6, 13, 12, 0, 0),
			},
		)

	def test_before_cancel_rejects_owner_self_approval_on_native_cancel(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"
		doc.owner = "mr@example.com"
		doc.status = "Superseded"

		with (
			patch.object(controller, "_get_session_user", return_value="mr@example.com"),
			patch.object(
				controller, "_workflow_action_allows_self_approval", return_value=False
			) as allows_self,
			patch.object(controller, "_insert_approval_snapshot_row") as snapshot,
			patch.object(controller.frappe, "throw", side_effect=Exception("self approval blocked")),
			self.assertRaisesRegex(Exception, "self approval blocked"),
		):
			doc.before_cancel()

		allows_self.assert_called_once_with(doc, action="Supersede")
		snapshot.assert_not_called()

	def test_before_cancel_rejects_direct_cancel_without_supersede_state(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"
		doc.status = "Released"

		with (
			patch.object(controller.frappe, "throw", side_effect=Exception("Supersede required")),
			self.assertRaisesRegex(Exception, "Supersede required"),
		):
			doc.before_cancel()

	def test_workflow_action_allows_self_approval_reads_matching_transition(self) -> None:
		doc = SimpleNamespace(doctype="Sheet Cutting Layout")
		workflow = SimpleNamespace(
			transitions=[
				SimpleNamespace(action="MR Release", allow_self_approval=1),
				SimpleNamespace(action="Supersede", allow_self_approval=0),
			]
		)

		with patch("frappe.model.workflow.get_workflow", return_value=workflow):
			self.assertTrue(controller._workflow_action_allows_self_approval(doc, action="MR Release"))
			self.assertFalse(controller._workflow_action_allows_self_approval(doc, action="Supersede"))
			self.assertFalse(controller._workflow_action_allows_self_approval(doc, action="Missing"))

	def test_on_cancel_retires_layout_without_snapshot(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"

		with (
			patch.object(controller, "retire_layout") as retire,
			patch.object(controller, "_insert_approval_snapshot_row") as snapshot,
		):
			doc.on_cancel()

		retire.assert_called_once_with(doc)
		snapshot.assert_not_called()

	def test_on_trash_keeps_rejected_layout_without_workflow_actions(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"
		doc.name = "SCL-TEST-REJECTED"
		doc.status = "Rejected"

		with (
			patch.object(controller.frappe.db, "get_all", return_value=[]) as get_all,
			patch.object(controller.frappe.db, "delete") as delete,
		):
			doc.on_trash()

		get_all.assert_called_once()
		delete.assert_not_called()

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

	def test_download_checks_child_layout_read_permission_before_export(self) -> None:
		parent = _FakeLayoutDoc(name="SCL-PARENT")
		parent.end_pieces = [SimpleNamespace(disposition="Reuse", child_layout="SCL-CHILD")]
		child = _FakeLayoutDoc(name="SCL-CHILD")

		def deny_read(permission_type: str) -> None:
			child.check_permission_calls = [permission_type]
			raise PermissionError("child denied")

		child.check_permission = deny_read

		def get_doc(doctype: str, name: str) -> _FakeLayoutDoc:
			self.assertEqual(doctype, "Sheet Cutting Layout")
			return {"SCL-PARENT": parent, "SCL-CHILD": child}[name]

		with (
			patch.object(controller.frappe, "get_doc", side_effect=get_doc),
			patch.object(controller, "_export_layout_dict", return_value={"end_pieces": []}) as export,
			patch.object(controller, "build_multi_sheet_workbook") as build_workbook,
			self.assertRaisesRegex(PermissionError, "child denied"),
		):
			controller.download_sheet_cutting_layout("SCL-PARENT")

		self.assertEqual(parent.check_permission_calls, ["read"])
		self.assertEqual(child.check_permission_calls, ["read"])
		export.assert_not_called()
		build_workbook.assert_not_called()

	def test_download_denies_real_user_without_child_layout_read_access(self) -> None:
		suffix = frappe.generate_hash(length=6).upper()
		parent_project = self._ensure_project(f"SCL-PARENT-PERM-{suffix}")
		child_project = self._ensure_project(f"SCL-CHILD-PERM-{suffix}")
		raw_material = ensure_item(f"SCLPERMRM{suffix}", stock_uom="Kg")
		scrap_item = ensure_item(f"SCLPERMSCRAP{suffix}", stock_uom="Kg")
		parent_part = ensure_item(f"SCLPERMP{suffix}SHR", stock_uom="Nos")
		child_part = ensure_item(f"SCLPERMC{suffix}SHR", stock_uom="Nos")
		end_piece_item = ensure_item(f"{child_part}-EP-2x500x1000", stock_uom="Kg")
		child = frappe.get_doc(
			{
				"doctype": "Sheet Cutting Layout",
				"layout_code": f"SCL-PERM-CHILD-{suffix}",
				"project": child_project,
				"revision_no": 1,
				"status": "Draft",
				"raw_material_item": end_piece_item,
				"process_scrap_item": scrap_item,
				"finished_part_code": child_part,
				"net_weight_per_part_kg": 7.86,
				"sheet_thickness_mm": 2,
				"sheet_width_mm": 500,
				"sheet_length_mm": 1000,
				"strip_thickness_mm": 2,
				"strip_width_mm": 500,
				"strip_length_mm": 1000,
				"parts_per_strip": 1,
				"no_of_strips": 1,
			}
		).insert(ignore_permissions=True)
		parent = frappe.get_doc(
			{
				"doctype": "Sheet Cutting Layout",
				"layout_code": f"SCL-PERM-PARENT-{suffix}",
				"project": parent_project,
				"revision_no": 1,
				"status": "Draft",
				"raw_material_item": raw_material,
				"process_scrap_item": scrap_item,
				"finished_part_code": parent_part,
				"net_weight_per_part_kg": 7.86,
				"sheet_thickness_mm": 2,
				"sheet_width_mm": 1000,
				"sheet_length_mm": 1000,
				"strip_thickness_mm": 2,
				"strip_width_mm": 500,
				"strip_length_mm": 1000,
				"parts_per_strip": 1,
				"no_of_strips": 1,
				"end_pieces": [
					{
						"width_mm": 500,
						"length_mm": 1000,
						"disposition": "Reuse",
						"used_for_finished_part": child_part,
						"scrap_item": scrap_item,
						"child_layout": child.name,
						"bom_quantity": 1,
						"net_weight_per_part_kg": 7.86,
					}
				],
			}
		).insert(ignore_permissions=True)
		user = self._ensure_project_manager_user(f"scl-export-{suffix.lower()}@example.com", parent_project)

		frappe.response.clear()
		self.addCleanup(frappe.set_user, frappe.session.user)
		frappe.set_user(user)
		frappe.get_doc("Sheet Cutting Layout", parent.name).check_permission("read")
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc("Sheet Cutting Layout", child.name).check_permission("read")

		with self.assertRaises(frappe.PermissionError):
			controller.download_sheet_cutting_layout(parent.name)
		self.assertNotIn("filecontent", frappe.response)

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
		layout = make_release_ready_layout()

		layout.status = "Released"
		layout.on_submit()

		self.assertEqual(layout.status, "Released")
		self.assertTrue(layout.generated_bom)

	def test_native_submit_persists_release_artifacts_after_reload(self) -> None:
		layout = make_release_ready_layout()

		# D-1 moves side effects to native on_submit, while D-5 will align the
		# workflow fixture so user-facing MR Release reaches this status naturally.
		layout.status = "Released"
		layout.submit()
		generated_bom = layout.generated_bom

		layout.reload()

		self.assertEqual(layout.status, "Released")
		self.assertEqual(layout.generated_bom, generated_bom)
		self.assertEqual(len(layout.finished_parts), 1)
		self.assertEqual(layout.finished_parts[0].generated_bom, generated_bom)
		self.assertEqual(len(layout.approval_snapshot), 1)
		self.assertEqual(layout.approval_snapshot[0].step_name, "MR Approval")
		self.assertEqual(layout.approval_snapshot[0].decision, "Approved")

	def test_draft_workflow_actions_persist_approval_snapshots_after_reload(self) -> None:
		from frappe.model.workflow import apply_workflow

		layout = make_layout(
			finished_part_code=f"SCLTESTFG{frappe.generate_hash(length=5).upper()}SHR",
			parts_per_strip=1,
			no_of_strips=1,
			strip_length_mm=2500,
		).insert()

		layout = apply_workflow(layout, "Submit for Check")
		layout = apply_workflow(layout, "Reject")
		layout.reload()

		snapshots = [(row.step_name, row.decision) for row in layout.approval_snapshot]
		self.assertEqual(
			snapshots,
			[
				("Submit for Check", "Submitted"),
				("Rejection", "Rejected"),
			],
		)

	def test_native_cancel_persists_supersession_snapshot_after_reload(self) -> None:
		layout = make_release_ready_layout()
		layout.status = "Released"
		layout.submit()

		layout.status = "Superseded"
		layout.cancel()
		layout.reload()

		snapshot_steps = [row.step_name for row in layout.approval_snapshot]
		self.assertIn("Supersession", snapshot_steps)

	def test_cancel_released_layout_deactivates_bom_natively(self) -> None:
		import frappe

		layout = make_release_ready_layout()
		layout.status = "Released"
		layout.submit()
		bom_name = layout.generated_bom
		self.assertEqual(frappe.db.get_value("BOM", bom_name, "is_active"), 1)

		layout.status = "Superseded"
		layout.cancel()

		self.assertEqual(frappe.db.get_value("BOM", bom_name, "is_active"), 0)
		self.assertEqual(frappe.db.get_value("Sheet Cutting Layout", layout.name, "docstatus"), 2)

	def test_supersede_action_cancels_layout_and_retires_bom(self) -> None:
		import frappe
		from frappe.model.workflow import apply_workflow

		layout = make_release_ready_layout()
		layout.status = "Released"
		layout.submit()
		bom_name = layout.generated_bom
		self.assertTrue(bom_name)
		self.assertEqual(frappe.db.get_value("BOM", bom_name, "is_active"), 1)

		apply_workflow(layout, "Supersede")

		layout.reload()
		self.assertEqual(layout.status, "Superseded")
		self.assertEqual(frappe.db.get_value("Sheet Cutting Layout", layout.name, "docstatus"), 2)
		self.assertEqual(frappe.db.get_value("BOM", bom_name, "is_active"), 0)

	def test_cancel_is_not_a_workflow_state(self) -> None:
		import frappe

		workflow = frappe.get_doc("Workflow", "Sheet Cutting Layout Approval Workflow")
		state_names = {state.state for state in workflow.states}
		self.assertNotIn("Cancel", state_names)
		superseded = next(state for state in workflow.states if state.state == "Superseded")
		self.assertEqual(int(superseded.doc_status), 2)
