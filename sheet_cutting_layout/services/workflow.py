from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

LayoutWorkflowState = Literal[
	"Draft",
	"Submitted for Check",
	"Checked",
	"Approved by Purchase",
	"Release Pending Impact",
	"Released",
	"Rejected",
	"Superseded",
]


class CheckerApprovalDocument(Protocol):
	project_manager_ok: bool
	manufacturing_manager_ok: bool


PROJECT_MANAGER_APPROVAL_ACTION = "Projects Manager Approves"
MANUFACTURING_MANAGER_APPROVAL_ACTION = "Manufacturing Manager Approves"
PURCHASE_APPROVAL_ACTION = "Purchase Approves"
MR_RELEASE_ACTION = "MR Release"
MR_RELEASE_WITH_IMPACT_ACTION = "MR Release With Impact"
FINALIZE_IMPACT_RELEASE_ACTION = "Finalize Impact Release"
SUBMIT_FOR_CHECK_ACTION = "Submit for Check"
REJECT_ACTION = "Reject"

APPROVAL_SNAPSHOT_ACTIONS: dict[str, str] = {
	SUBMIT_FOR_CHECK_ACTION: "Submit for Check",
	PROJECT_MANAGER_APPROVAL_ACTION: "Projects Manager Approval",
	MANUFACTURING_MANAGER_APPROVAL_ACTION: "Manufacturing Manager Approval",
	PURCHASE_APPROVAL_ACTION: "Purchase Approval",
	MR_RELEASE_ACTION: "MR Approval",
	MR_RELEASE_WITH_IMPACT_ACTION: "MR Approval",
	FINALIZE_IMPACT_RELEASE_ACTION: "MR Approval",
	REJECT_ACTION: "Rejection",
}


def apply_checker_action(doc: CheckerApprovalDocument, action: str) -> None:
	if action == PROJECT_MANAGER_APPROVAL_ACTION:
		doc.project_manager_ok = True
	elif action == MANUFACTURING_MANAGER_APPROVAL_ACTION:
		doc.manufacturing_manager_ok = True


def record_approval_snapshot(
	doc: object,
	*,
	action: str,
	approver: str | None,
	decision_time: datetime,
) -> bool:
	step_name = APPROVAL_SNAPSHOT_ACTIONS.get(action)
	if not step_name:
		return False

	decision = (
		"Submitted"
		if action == SUBMIT_FOR_CHECK_ACTION
		else "Rejected"
		if action == REJECT_ACTION
		else "Approved"
	)
	row = {
		"step_name": step_name,
		"approver": approver,
		"decision": decision,
		"decision_time": decision_time,
	}
	if hasattr(doc, "append"):
		doc.append("approval_snapshot", row)
		return True

	snapshot_rows = list(getattr(doc, "approval_snapshot", []) or [])
	snapshot_rows.append(row)
	doc.approval_snapshot = snapshot_rows
	return True


@dataclass
class LayoutWorkflowModel:
	state: LayoutWorkflowState = "Draft"
	project_manager_ok: bool = False
	manufacturing_manager_ok: bool = False

	def submit(self) -> None:
		self._require_state("Draft")
		self.state = "Submitted for Check"

	def project_manager_approves(self) -> None:
		self._require_state("Submitted for Check")
		self.project_manager_ok = True
		self.mark_checked_if_ready()

	def manufacturing_manager_approves(self) -> None:
		self._require_state("Submitted for Check")
		if not self.project_manager_ok:
			raise AssertionError("Manufacturing Manager approval requires Projects Manager approval")
		self.manufacturing_manager_ok = True
		self.mark_checked_if_ready()

	def purchase_approves(self) -> None:
		self._require_state("Checked")
		self.state = "Approved by Purchase"

	def release(self, *, has_impacts: bool = False) -> None:
		self._require_checker_approvals()
		if self.state != "Approved by Purchase":
			raise AssertionError("Release requires purchase approval")
		self.state = "Release Pending Impact" if has_impacts else "Released"

	def reject(self) -> None:
		if self.state not in {
			"Submitted for Check",
			"Checked",
			"Approved by Purchase",
			"Release Pending Impact",
		}:
			raise AssertionError("Only in-review or pre-release layouts can be rejected")
		self.state = "Rejected"

	def supersede(self) -> None:
		self._require_state("Released")
		self.state = "Superseded"

	def mark_checked_if_ready(self) -> None:
		self._require_state("Submitted for Check")
		if self.project_manager_ok and self.manufacturing_manager_ok:
			self.state = "Checked"

	def _require_checker_approvals(self) -> None:
		if not (self.project_manager_ok and self.manufacturing_manager_ok):
			raise AssertionError("Release requires both checker approvals")

	def _require_state(self, expected: LayoutWorkflowState) -> None:
		if self.state != expected:
			raise AssertionError(f"Expected layout state {expected}, got {self.state}")
