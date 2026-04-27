from __future__ import annotations

from dataclasses import dataclass
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


PROJECT_MANAGER_APPROVAL_ACTION = "Project Manager Approves"
MANUFACTURING_MANAGER_APPROVAL_ACTION = "Manufacturing Manager Approves"


def apply_checker_action(doc: CheckerApprovalDocument, action: str) -> None:
	if action == PROJECT_MANAGER_APPROVAL_ACTION:
		doc.project_manager_ok = True
	elif action == MANUFACTURING_MANAGER_APPROVAL_ACTION:
		doc.manufacturing_manager_ok = True


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
