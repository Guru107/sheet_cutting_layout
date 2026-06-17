from __future__ import annotations

from typing import Literal, Protocol, TypeVar

LayoutVersionStatus = Literal[
	"Draft",
	"Approved by Purchase",
	"Released",
	"Superseded",
]


class FinishedPartRow(Protocol):
	finished_part_item: str
	generated_bom: str | None


class RevisionLayoutDocument(Protocol):
	name: str
	project: str
	revision_no: int
	status: LayoutVersionStatus
	based_on_layout: str | None
	is_active: bool
	approval_snapshot: list[object]
	finished_parts: list[FinishedPartRow]
	finished_part_code: str | None
	generated_bom: str | None
	twin_generated_bom: str | None


RevisionLayoutT = TypeVar("RevisionLayoutT", bound=RevisionLayoutDocument)


def create_revision(old_layout: RevisionLayoutT) -> RevisionLayoutT:
	if old_layout.status != "Released":
		raise ValueError("Only released layouts can be revised")

	new_layout = _copy_layout(old_layout)
	new_layout.name = ""
	new_layout.revision_no = old_layout.revision_no + 1
	if hasattr(new_layout, "layout_code"):
		new_layout.layout_code = _revision_layout_code(
			getattr(old_layout, "layout_code", old_layout.name),
			new_layout.revision_no,
		)
	new_layout.status = "Draft"
	new_layout.based_on_layout = old_layout.name
	new_layout.is_active = False
	new_layout.approval_snapshot = []
	if hasattr(new_layout, "generated_bom"):
		new_layout.generated_bom = None
	if hasattr(new_layout, "twin_generated_bom"):
		new_layout.twin_generated_bom = None

	new_layout.finished_parts = []

	for row in getattr(new_layout, "end_pieces", []) or []:
		_reset_child_row(row)

	if hasattr(new_layout, "end_piece_bom_status"):
		from sheet_cutting_layout.services.validators import apply_end_piece_bom_status

		apply_end_piece_bom_status(new_layout, getattr(new_layout, "end_pieces", []) or [])

	return new_layout


def finalize_new_revision_release(new_layout: RevisionLayoutDocument) -> RevisionLayoutDocument:
	new_layout.status = "Released"
	new_layout.is_active = True
	return new_layout


def _copy_layout(old_layout: RevisionLayoutT) -> RevisionLayoutT:
	import frappe

	return frappe.copy_doc(old_layout)


def _reset_child_row(row: object) -> None:
	for fieldname in ("end_piece_item_code", "generated_end_piece_bom"):
		if hasattr(row, fieldname):
			setattr(row, fieldname, None)


def _revision_layout_code(layout_code: str, revision_no: int) -> str:
	base = layout_code.rsplit("-R", 1)[0]
	return f"{base}-R{revision_no}"
