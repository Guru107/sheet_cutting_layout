from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from types import SimpleNamespace

import frappe
from hypothesis import settings
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule, run_state_machine_as_test

from sheet_cutting_layout.services.versioning import (
	create_revision,
	finalize_new_revision_release,
)
from sheet_cutting_layout.services.workflow import LayoutWorkflowModel, record_approval_snapshot
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase

STATE_MACHINE_SETTINGS = settings(
	max_examples=40,
	stateful_step_count=20,
	deadline=None,
)


class WorkflowStateMachine(RuleBasedStateMachine):
	def __init__(self) -> None:
		super().__init__()
		self.machine = LayoutWorkflowModel()
		self.expected_state = "Draft"
		self.purchase_approved = False
		self.mr_released = False
		self.was_released = False

	@rule()
	def submit(self) -> None:
		valid = self.expected_state == "Draft"

		def update_expected() -> None:
			self.expected_state = "Submitted for Check"

		self._assert_transition(valid, self.machine.submit, update_expected)

	@rule()
	def project_manager_approves(self) -> None:
		valid = self.expected_state == "Submitted for Check"

		def update_expected() -> None:
			self.expected_state = "PM Approved"

		self._assert_transition(valid, self.machine.project_manager_approves, update_expected)

	@rule()
	def purchase_approves(self) -> None:
		valid = self.expected_state == "PM Approved"

		def update_expected() -> None:
			self.expected_state = "Approved by Purchase"
			self.purchase_approved = True

		self._assert_transition(valid, self.machine.purchase_approves, update_expected)

	@rule()
	def mr_releases(self) -> None:
		valid = self.expected_state == "Approved by Purchase"

		def update_expected() -> None:
			self.expected_state = "Released"
			self.mr_released = True
			self.was_released = True

		self._assert_transition(valid, self.machine.release, update_expected)

	@rule()
	def reject(self) -> None:
		valid = self.expected_state in {
			"Submitted for Check",
			"PM Approved",
			"Approved by Purchase",
		}

		def update_expected() -> None:
			self.expected_state = "Draft"

		self._assert_transition(valid, self.machine.reject, update_expected)

	@rule()
	def revise_by_superseding_released_layout(self) -> None:
		valid = self.expected_state == "Released"

		def update_expected() -> None:
			self.expected_state = "Superseded"

		self._assert_transition(valid, self.machine.supersede, update_expected)

	@invariant()
	def model_and_workflow_state_match(self) -> None:
		assert self.machine.state == self.expected_state

	@invariant()
	def released_requires_purchase_and_mr_release(self) -> None:
		if self.machine.state == "Released":
			assert self.purchase_approved is True
			assert self.mr_released is True

	@invariant()
	def terminal_superseded_state_stays_valid(self) -> None:
		if self.machine.state == "Superseded":
			assert self.expected_state == "Superseded"
			assert self.was_released is True

	def _assert_transition(
		self,
		valid: bool,
		action: Callable[[], None],
		update_expected: Callable[[], None],
	) -> None:
		if valid:
			action()
			update_expected()
			return

		try:
			action()
		except AssertionError:
			return
		raise AssertionError("Expected invalid transition to raise AssertionError")


class RevisionVersioningStateMachine(RuleBasedStateMachine):
	def __init__(self) -> None:
		super().__init__()
		self.project = "FAM-STATEFUL"
		self.layouts = [
			frappe.get_doc(
				{
					"doctype": "Sheet Cutting Layout",
					"name": "SCL-STATEFUL-001",
					"project": self.project,
					"layout_code": "SCL-STATEFUL-001-R1",
					"revision_no": 1,
					"status": "Released",
					"is_active": True,
					"approval_snapshot": [],
					"finished_part_code": "PART-001SHR",
					"net_weight_per_part_kg": 1.25,
					"generated_bom": "BOM-PARENT-001-001",
					"finished_parts": [
						{
							"doctype": "Sheet Cutting Layout Finished Part",
							"finished_part_item": "PART-001SHR",
							"generated_bom": "BOM-PART-001-001",
						}
					],
				}
			)
		]
		self.next_layout_id = 2

	@rule()
	def revise_active_released_layout_and_finalize_new_release(self) -> None:
		active_layout = self._active_released_layouts()[0]

		new_layout = create_revision(active_layout)
		new_layout.name = f"SCL-STATEFUL-{self.next_layout_id:03d}"
		self.next_layout_id += 1
		self.layouts.append(new_layout)

		assert new_layout.status == "Draft"
		assert new_layout.is_active is False
		assert new_layout.based_on_layout == active_layout.name
		assert new_layout.revision_no == active_layout.revision_no + 1
		assert new_layout.approval_snapshot == []
		assert new_layout.finished_parts == []
		assert new_layout.finished_part_code == active_layout.finished_part_code
		assert new_layout.net_weight_per_part_kg == active_layout.net_weight_per_part_kg

		finalize_new_revision_release(new_layout)

		assert new_layout.status == "Released"
		assert new_layout.is_active is True
		assert active_layout.status == "Released"
		assert active_layout.is_active is True

	@invariant()
	def every_active_layout_in_family_is_released(self) -> None:
		for layout in self.layouts:
			if layout.project == self.project and layout.is_active:
				assert layout.status == "Released"

	def _active_released_layouts(self) -> list[object]:
		return [
			layout
			for layout in self.layouts
			if layout.project == self.project and layout.status == "Released" and layout.is_active
		]


class TestModelWorkflowStateMachine(SheetCuttingLayoutTestCase):
	def test_project_manager_approval_moves_state_to_pm_approved(self) -> None:
		machine = LayoutWorkflowModel()
		machine.submit()
		machine.project_manager_approves()

		self.assertEqual(machine.state, "PM Approved")

	def test_purchase_approval_requires_pm_approved(self) -> None:
		machine = LayoutWorkflowModel()
		machine.submit()

		with self.assertRaisesRegex(AssertionError, "Expected layout state PM Approved"):
			machine.purchase_approves()

	def test_release_blocked_before_purchase_approval(self) -> None:
		machine = LayoutWorkflowModel()
		machine.submit()
		machine.project_manager_approves()

		with self.assertRaisesRegex(AssertionError, "purchase approval"):
			machine.release()

	def test_purchase_and_mr_release_path_reaches_released(self) -> None:
		machine = LayoutWorkflowModel()
		machine.submit()
		machine.project_manager_approves()
		machine.purchase_approves()
		machine.release()

		self.assertEqual(machine.state, "Released")

	def test_reject_returns_approval_states_to_draft_for_resubmission(self) -> None:
		paths = {
			"Submitted for Check": [LayoutWorkflowModel.submit],
			"PM Approved": [LayoutWorkflowModel.submit, LayoutWorkflowModel.project_manager_approves],
			"Approved by Purchase": [
				LayoutWorkflowModel.submit,
				LayoutWorkflowModel.project_manager_approves,
				LayoutWorkflowModel.purchase_approves,
			],
		}

		for rejected_state, actions in paths.items():
			with self.subTest(rejected_state=rejected_state):
				machine = LayoutWorkflowModel()
				for action in actions:
					action(machine)
				self.assertEqual(machine.state, rejected_state)

				machine.reject()

				self.assertEqual(machine.state, "Draft")
				machine.submit()
				self.assertEqual(machine.state, "Submitted for Check")

	def test_supersede_moves_released_layout_to_superseded(self) -> None:
		machine = LayoutWorkflowModel()
		machine.submit()
		machine.project_manager_approves()
		machine.purchase_approves()
		machine.release()

		machine.supersede()

		self.assertEqual(machine.state, "Superseded")

	def test_record_approval_snapshot_returns_false_for_unknown_action(self) -> None:
		doc = SimpleNamespace(approval_snapshot=[])

		recorded = record_approval_snapshot(
			doc,
			action="Unknown Action",
			approver="qa@example.com",
			decision_time=datetime(2026, 6, 23, 8, 30),
		)

		self.assertFalse(recorded)
		self.assertEqual(doc.approval_snapshot, [])

	def test_record_approval_snapshot_prefers_append_when_available(self) -> None:
		class AppendOnlyDoc:
			def __init__(self) -> None:
				self.approval_snapshot = []
				self.calls: list[tuple[str, dict[str, object]]] = []

			def append(self, fieldname: str, row: dict[str, object]) -> None:
				self.calls.append((fieldname, row))

		doc = AppendOnlyDoc()
		recorded = record_approval_snapshot(
			doc,
			action="MR Release",
			approver="mr@example.com",
			decision_time=datetime(2026, 6, 23, 8, 30),
		)

		self.assertTrue(recorded)
		self.assertEqual(len(doc.calls), 1)
		fieldname, row = doc.calls[0]
		self.assertEqual(fieldname, "approval_snapshot")
		self.assertEqual(row["step_name"], "MR Approval")
		self.assertEqual(row["decision"], "Approved")
		self.assertEqual(row["approver"], "mr@example.com")
		self.assertEqual(row["decision_time"], datetime(2026, 6, 23, 8, 30))
		self.assertEqual(doc.approval_snapshot, [])

	def test_state_machine_never_reaches_released_without_purchase_and_mr(self) -> None:
		run_state_machine_as_test(WorkflowStateMachine, settings=STATE_MACHINE_SETTINGS)

	def test_state_machine_keeps_all_active_layouts_released_after_new_versions(self) -> None:
		run_state_machine_as_test(RevisionVersioningStateMachine, settings=STATE_MACHINE_SETTINGS)
