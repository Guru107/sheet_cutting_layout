from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestSheetCuttingLayoutPermissions(FrappeTestCase):
	def test_workflow_roles_can_read_and_write(self) -> None:
		permissions = frappe.get_meta("Sheet Cutting Layout").permissions
		for role in ("Projects Manager", "Purchase Manager", "MR Coordinator"):
			with self.subTest(role=role):
				self.assertTrue(any(permission.role == role for permission in permissions))
				self.assertTrue(
					any(permission.role == role and permission.read for permission in permissions)
				)
				self.assertTrue(
					any(permission.role == role and permission.write for permission in permissions)
				)

	def test_mr_coordinator_can_submit_and_cancel(self) -> None:
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
