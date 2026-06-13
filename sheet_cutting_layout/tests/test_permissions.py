from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestSheetCuttingLayoutPermissions(FrappeTestCase):
	def test_workflow_roles_can_read_and_write(self) -> None:
		meta = frappe.get_meta("Sheet Cutting Layout")
		roles = {perm.role: perm for perm in meta.permissions}
		for role in ("Project Manager", "Purchase Manager", "MR Coordinator"):
			with self.subTest(role=role):
				self.assertIn(role, roles)
				self.assertTrue(roles[role].read)
				self.assertTrue(roles[role].write)

	def test_mr_coordinator_can_submit_and_cancel(self) -> None:
		meta = frappe.get_meta("Sheet Cutting Layout")
		roles = {perm.role: perm for perm in meta.permissions}
		self.assertTrue(roles["MR Coordinator"].submit)
		self.assertTrue(roles["MR Coordinator"].cancel)
		self.assertTrue(roles["System Manager"].cancel)

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
