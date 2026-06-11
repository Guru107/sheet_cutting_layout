from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from hypothesis import settings
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from sheet_cutting_layout.services.versioning import (
	LayoutVersionStatus,
	create_revision,
	finalize_new_revision_release,
)
from sheet_cutting_layout.services.workflow import LayoutWorkflowModel
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase
from sheet_cutting_layout.tests.unittest_adapter import MonkeyPatch, add_pytest_style_tests, fixture, raises


@fixture(autouse=True)
def isolate_state_tests_from_frappe_copy_doc(monkeypatch: MonkeyPatch) -> None:
	try:
		import frappe as frappe_module
	except ImportError:
		return
	monkeypatch.setattr(frappe_module, "copy_doc", None, raising=False)


@dataclass
class FinishedPart:
	finished_part_item: str
	generated_bom: str | None = None


@dataclass
class RevisionLayout:
	name: str
	project: str
	revision_no: int
	status: LayoutVersionStatus
	is_active: bool
	based_on_layout: str | None = None
	approval_snapshot: list[str] = field(default_factory=list)
	finished_parts: list[FinishedPart] = field(default_factory=list)
	finished_part_code: str = ""
	net_weight_per_part_kg: float = 0.0
	generated_bom: str | None = None


def test_project_manager_approval_moves_state_to_pm_approved() -> None:
	machine = LayoutWorkflowModel()
	machine.submit()
	machine.project_manager_approves()

	assert machine.state == "PM Approved"


def test_purchase_approval_requires_pm_approved() -> None:
	machine = LayoutWorkflowModel()
	machine.submit()

	with raises(AssertionError, match="Expected layout state PM Approved"):
		machine.purchase_approves()


def test_release_blocked_before_purchase_approval() -> None:
	machine = LayoutWorkflowModel()
	machine.submit()
	machine.project_manager_approves()

	with raises(AssertionError, match="purchase approval"):
		machine.release()


def test_purchase_and_mr_release_path_reaches_released() -> None:
	machine = LayoutWorkflowModel()
	machine.submit()
	machine.project_manager_approves()
	machine.purchase_approves()
	machine.release()

	assert machine.state == "Released"


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

	@invariant()
	def released_requires_purchase_and_mr_release(self) -> None:
		if self.machine.state == "Released":
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

		with raises(AssertionError):
			action()


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
		self.project = "FAM-STATEFUL"
		self.layouts = [
			RevisionLayout(
				name="SCL-STATEFUL-001",
				project=self.project,
				revision_no=1,
				status="Released",
				is_active=True,
				approval_snapshot=["purchase-approved"],
				finished_part_code="PART-001SHR",
				net_weight_per_part_kg=1.25,
				generated_bom="BOM-PARENT-001-001",
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

	def _active_released_layouts(self) -> list[RevisionLayout]:
		return [
			layout
			for layout in self.layouts
			if layout.project == self.project and layout.status == "Released" and layout.is_active
		]


RevisionVersioningStateMachine.TestCase.settings = settings(
	max_examples=40,
	stateful_step_count=20,
	deadline=None,
)


def test_state_machine_keeps_all_active_layouts_released_after_new_versions() -> None:
	machine = RevisionVersioningStateMachine.TestCase()
	machine.runTest()


class TestModelWorkflowStateMachine(SheetCuttingLayoutTestCase):
	pass


add_pytest_style_tests(globals(), TestModelWorkflowStateMachine)
