from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

LayoutWorkflowState = Literal[
	"Draft",
	"Submitted for Check",
	"PM Approved",
	"Approved by Purchase",
	"Released",
	"Rejected",
	"Superseded",
]


PROJECT_MANAGER_APPROVAL_ACTION = "Project Manager Approves"
PURCHASE_APPROVAL_ACTION = "Purchase Approves"
MR_RELEASE_ACTION = "MR Release"
SUBMIT_FOR_CHECK_ACTION = "Submit for Check"
REJECT_ACTION = "Reject"

APPROVAL_SNAPSHOT_ACTIONS: dict[str, str] = {
	SUBMIT_FOR_CHECK_ACTION: "Submit for Check",
	PROJECT_MANAGER_APPROVAL_ACTION: "Project Manager Approval",
	PURCHASE_APPROVAL_ACTION: "Purchase Approval",
	MR_RELEASE_ACTION: "MR Approval",
	REJECT_ACTION: "Rejection",
}


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

	def submit(self) -> None:
		self._require_state("Draft")
		self.state = "Submitted for Check"

	def project_manager_approves(self) -> None:
		self._require_state("Submitted for Check")
		self.state = "PM Approved"

	def purchase_approves(self) -> None:
		self._require_state("PM Approved")
		self.state = "Approved by Purchase"

	def release(self) -> None:
		if self.state != "Approved by Purchase":
			raise AssertionError("Release requires purchase approval")
		self.state = "Released"

	def reject(self) -> None:
		if self.state not in {
			"Submitted for Check",
			"PM Approved",
			"Approved by Purchase",
		}:
			raise AssertionError("Only in-review or pre-release layouts can be rejected")
		self.state = "Rejected"

	def supersede(self) -> None:
		self._require_state("Released")
		self.state = "Superseded"

	def _require_state(self, expected: LayoutWorkflowState) -> None:
		if self.state != expected:
			raise AssertionError(f"Expected layout state {expected}, got {self.state}")
