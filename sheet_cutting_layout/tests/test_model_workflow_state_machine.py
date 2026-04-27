from __future__ import annotations

import pytest

from sheet_cutting_layout.services.workflow import LayoutWorkflowModel, apply_checker_action


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
