from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

MODULE_ROOT = Path(__file__).resolve().parents[1]
SHEET_CUTTING_LAYOUT_DOCTYPE = (
	MODULE_ROOT / "sheet_cutting_layout" / "doctype" / "sheet_cutting_layout" / "sheet_cutting_layout.json"
)


class TestSheetCuttingLayoutPermissions(FrappeTestCase):
	def test_cancel_permissions_include_submit_and_write_dependencies(self) -> None:
		doctype = json.loads(SHEET_CUTTING_LAYOUT_DOCTYPE.read_text(encoding="utf-8"))
		invalid_rows = [
			f"{permission.get('role')} at row {index}"
			for index, permission in enumerate(doctype["permissions"], start=1)
			if permission.get("cancel") and (not permission.get("submit") or not permission.get("write"))
		]

		self.assertEqual(invalid_rows, [])

	def test_workflow_roles_can_read_and_write(self) -> None:
		permissions = frappe.get_meta("Sheet Cutting Layout").permissions
		for role in ("Projects User", "Projects Manager", "Purchase Manager", "MR Coordinator"):
			with self.subTest(role=role):
				self.assertTrue(any(permission.role == role for permission in permissions))
				self.assertTrue(
					any(permission.role == role and permission.read for permission in permissions)
				)
				self.assertTrue(
					any(permission.role == role and permission.write for permission in permissions)
				)

	def test_projects_user_can_create_and_submit_draft_layouts(self) -> None:
		permissions = frappe.get_meta("Sheet Cutting Layout").permissions
		self.assertTrue(
			any(permission.role == "Projects User" and permission.create for permission in permissions)
		)

		workflow = frappe.get_doc("Workflow", "Sheet Cutting Layout Approval Workflow")
		draft_roles = {state.allow_edit for state in workflow.states if state.state == "Draft"}
		self.assertEqual(draft_roles, {"Projects User"})

		allowed_roles = {
			(transition.allowed, int(getattr(transition, "allow_self_approval", 0) or 0))
			for transition in workflow.transitions
			if transition.state == "Draft"
			and transition.action == "Submit for Check"
			and transition.next_state == "Submitted for Check"
		}
		self.assertEqual(allowed_roles, {("Projects User", 1)})

	def test_mr_coordinator_and_system_manager_can_submit_and_cancel(self) -> None:
		permissions = frappe.get_meta("Sheet Cutting Layout").permissions
		self.assertTrue(
			any(permission.role == "MR Coordinator" and permission.submit for permission in permissions)
		)
		self.assertTrue(
			any(permission.role == "MR Coordinator" and permission.cancel for permission in permissions)
		)
		self.assertTrue(
			any(permission.role == "System Manager" and permission.cancel for permission in permissions)
		)
		self.assertTrue(
			any(permission.role == "System Manager" and permission.submit for permission in permissions)
		)

	def test_supersede_workflow_is_available_to_mr_coordinator_and_system_manager(self) -> None:
		workflow = frappe.get_doc("Workflow", "Sheet Cutting Layout Approval Workflow")
		allowed_roles = {
			transition.allowed
			for transition in workflow.transitions
			if transition.state == "Released"
			and transition.action == "Supersede"
			and transition.next_state == "Superseded"
		}
		self.assertIn("MR Coordinator", allowed_roles)
		self.assertIn("System Manager", allowed_roles)
