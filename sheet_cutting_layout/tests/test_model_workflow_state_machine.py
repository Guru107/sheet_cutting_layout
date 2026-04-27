from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pytest
from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from sheet_cutting_layout.services.versioning import (
	LayoutVersionStatus,
	create_revision,
	finalize_new_revision_release,
)
from sheet_cutting_layout.services.workflow import LayoutWorkflowModel, apply_checker_action


@dataclass
class FinishedPart:
	finished_part_item: str
	generated_bom: str | None = None


@dataclass
class RevisionLayout:
	name: str
	layout_family: str
	revision_no: int
	status: LayoutVersionStatus
	is_active: bool
	based_on_layout: str | None = None
	approval_snapshot: list[str] = field(default_factory=list)
	impact_resolutions: list[str] = field(default_factory=list)
	finished_parts: list[FinishedPart] = field(default_factory=list)


def test_release_blocked_until_both_parallel_checkers_approve() -> None:
	machine = LayoutWorkflowModel()

	machine.submit()
	machine.project_manager_approves()

	with pytest.raises(AssertionError, match="both checker approvals"):
		machine.release()


def test_state_reaches_checked_only_after_both_checkers() -> None:
	machine = LayoutWorkflowModel()

	machine.submit()
	machine.project_manager_approves()

	assert machine.state == "Submitted for Check"

	machine.manufacturing_manager_approves()

	assert machine.project_manager_ok is True
	assert machine.manufacturing_manager_ok is True
	assert machine.state == "Checked"


def test_checker_action_helper_sets_parallel_approval_flags() -> None:
	machine = LayoutWorkflowModel()

	apply_checker_action(machine, "Project Manager Approves")
	apply_checker_action(machine, "Manufacturing Manager Approves")

	assert machine.project_manager_ok is True
	assert machine.manufacturing_manager_ok is True


def test_checker_action_helper_flags_allow_model_to_reach_checked() -> None:
	machine = LayoutWorkflowModel()

	machine.submit()
	apply_checker_action(machine, "Project Manager Approves")
	apply_checker_action(machine, "Manufacturing Manager Approves")
	machine.mark_checked_if_ready()

	assert machine.state == "Checked"


def test_release_blocked_after_checkers_before_purchase_approval() -> None:
	machine = LayoutWorkflowModel()

	machine.submit()
	machine.project_manager_approves()
	machine.manufacturing_manager_approves()

	with pytest.raises(AssertionError, match="purchase approval"):
		machine.release()


def test_purchase_approval_keeps_layout_pre_release_until_mr_release() -> None:
	machine = LayoutWorkflowModel()

	machine.submit()
	machine.project_manager_approves()
	machine.manufacturing_manager_approves()
	machine.purchase_approves()

	assert machine.state == "Approved by Purchase"


def test_purchase_and_mr_release_path_reaches_released() -> None:
	machine = LayoutWorkflowModel()

	machine.submit()
	machine.project_manager_approves()
	machine.manufacturing_manager_approves()
	machine.purchase_approves()
	machine.release(has_impacts=False)

	assert machine.state == "Released"


def test_impacts_move_to_release_pending_impact() -> None:
	machine = LayoutWorkflowModel()

	machine.submit()
	machine.project_manager_approves()
	machine.manufacturing_manager_approves()
	machine.purchase_approves()
	machine.release(has_impacts=True)

	assert machine.state == "Release Pending Impact"


class WorkflowStateMachine(RuleBasedStateMachine):
	def __init__(self) -> None:
		super().__init__()
		self.machine = LayoutWorkflowModel()
		self.expected_state = "Draft"
		self.expected_project_manager_ok = False
		self.expected_manufacturing_manager_ok = False
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
			self.expected_project_manager_ok = True
			self._mark_checked_if_ready()

		self._assert_transition(valid, self.machine.project_manager_approves, update_expected)

	@rule()
	def manufacturing_manager_approves(self) -> None:
		valid = self.expected_state == "Submitted for Check"

		def update_expected() -> None:
			self.expected_manufacturing_manager_ok = True
			self._mark_checked_if_ready()

		self._assert_transition(valid, self.machine.manufacturing_manager_approves, update_expected)

	@rule()
	def purchase_approves(self) -> None:
		valid = self.expected_state == "Checked"

		def update_expected() -> None:
			self.expected_state = "Approved by Purchase"
			self.purchase_approved = True

		self._assert_transition(valid, self.machine.purchase_approves, update_expected)

	@rule(has_impacts=st.booleans())
	def mr_releases(self, has_impacts: bool) -> None:
		valid = self.expected_state == "Approved by Purchase" and self._both_checkers_approved()

		def update_expected() -> None:
			self.expected_state = "Release Pending Impact" if has_impacts else "Released"
			self.mr_released = True
			self.was_released = self.expected_state == "Released"

		self._assert_transition(
			valid,
			lambda: self.machine.release(has_impacts=has_impacts),
			update_expected,
		)

	@rule()
	def reject(self) -> None:
		valid = self.expected_state in {
			"Submitted for Check",
			"Checked",
			"Approved by Purchase",
			"Release Pending Impact",
		}

		def update_expected() -> None:
			self.expected_state = "Rejected"

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
		assert self.machine.project_manager_ok is self.expected_project_manager_ok
		assert self.machine.manufacturing_manager_ok is self.expected_manufacturing_manager_ok

	@invariant()
	def released_requires_all_approvals_and_mr_release(self) -> None:
		if self.machine.state == "Released":
			assert self.expected_project_manager_ok is True
			assert self.expected_manufacturing_manager_ok is True
			assert self.purchase_approved is True
			assert self.mr_released is True

	@invariant()
	def terminal_rejected_and_superseded_states_stay_valid(self) -> None:
		if self.machine.state == "Rejected":
			assert self.expected_state == "Rejected"
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

		with pytest.raises(AssertionError):
			action()

	def _mark_checked_if_ready(self) -> None:
		if self._both_checkers_approved():
			self.expected_state = "Checked"

	def _both_checkers_approved(self) -> bool:
		return self.expected_project_manager_ok and self.expected_manufacturing_manager_ok


WorkflowStateMachine.TestCase.settings = settings(
	max_examples=40,
	stateful_step_count=20,
	deadline=None,
)


def test_state_machine_never_reaches_released_without_purchase_and_mr() -> None:
	machine = WorkflowStateMachine.TestCase()
	machine.runTest()


class RevisionVersioningStateMachine(RuleBasedStateMachine):
	def __init__(self) -> None:
		super().__init__()
		self.layout_family = "FAM-STATEFUL"
		self.layouts = [
			RevisionLayout(
				name="SCL-STATEFUL-001",
				layout_family=self.layout_family,
				revision_no=1,
				status="Released",
				is_active=True,
				approval_snapshot=["purchase-approved"],
				impact_resolutions=["WO-001"],
				finished_parts=[FinishedPart("PART-001SHR", generated_bom="BOM-PART-001-001")],
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
		assert new_layout.impact_resolutions == []
		assert [row.generated_bom for row in new_layout.finished_parts] == [None]
		self.one_layout_family_has_at_most_one_active_released_layout()

		finalize_new_revision_release(self.layouts, new_layout, [])

		assert new_layout.status == "Released"
		assert new_layout.is_active is True
		assert active_layout.status == "Superseded"
		assert active_layout.is_active is False

	@invariant()
	def one_layout_family_has_at_most_one_active_released_layout(self) -> None:
		active_released_layouts = self._active_released_layouts()

		assert len(active_released_layouts) <= 1

	@invariant()
	def every_active_layout_in_family_is_released(self) -> None:
		for layout in self.layouts:
			if layout.layout_family == self.layout_family and layout.is_active:
				assert layout.status == "Released"

	def _active_released_layouts(self) -> list[RevisionLayout]:
		return [
			layout
			for layout in self.layouts
			if layout.layout_family == self.layout_family and layout.status == "Released" and layout.is_active
		]


RevisionVersioningStateMachine.TestCase.settings = settings(
	max_examples=40,
	stateful_step_count=20,
	deadline=None,
)


def test_state_machine_keeps_single_active_released_layout_per_family() -> None:
	machine = RevisionVersioningStateMachine.TestCase()
	machine.runTest()
