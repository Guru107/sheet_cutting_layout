from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from typing import Literal, Protocol, TypeVar

LayoutVersionStatus = Literal[
	"Draft",
	"Approved by Purchase",
	"Release Pending Impact",
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
	impact_resolutions: list[object]
	finished_parts: list[FinishedPartRow]


class BomDocument(Protocol):
	name: str
	item: str
	is_active: bool
	disabled: bool
	status: str


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
	new_layout.impact_resolutions = []

	for finished_part in new_layout.finished_parts:
		_reset_child_row(finished_part)
		finished_part.generated_bom = None

	for row in getattr(new_layout, "end_pieces", []) or []:
		_reset_child_row(row)

	return new_layout


def finalize_new_revision_release(
	layouts: Sequence[RevisionLayoutDocument],
	new_layout: RevisionLayoutDocument,
	boms: Sequence[BomDocument],
) -> RevisionLayoutDocument:
	previous_active_layouts = [
		layout for layout in layouts if _is_previous_active_released_layout(layout, new_layout)
	]
	affected_items = {row.finished_part_item for row in new_layout.finished_parts}
	superseded_bom_names = {
		row.generated_bom
		for layout in previous_active_layouts
		for row in layout.finished_parts
		if row.generated_bom is not None and row.finished_part_item in affected_items
	}

	new_layout.status = "Released"
	new_layout.is_active = True

	new_bom_names = {row.generated_bom for row in new_layout.finished_parts if row.generated_bom is not None}

	for layout in previous_active_layouts:
		layout.status = "Superseded"
		layout.is_active = False

	for bom in boms:
		if bom.name in new_bom_names:
			bom.is_active = True
			bom.disabled = False
			bom.status = "Active"
		elif bom.name in superseded_bom_names and bom.is_active:
			bom.is_active = False
			bom.disabled = True
			bom.status = "Superseded"

	return new_layout


def _is_previous_active_released_layout(
	layout: RevisionLayoutDocument,
	new_layout: RevisionLayoutDocument,
) -> bool:
	return (
		layout is not new_layout
		and layout.project == new_layout.project
		and layout.status == "Released"
		and layout.is_active
	)


def _copy_layout(old_layout: RevisionLayoutT) -> RevisionLayoutT:
	try:
		import frappe
	except ImportError:
		return deepcopy(old_layout)

	copy_doc = getattr(frappe, "copy_doc", None)
	if callable(copy_doc):
		return copy_doc(old_layout)
	return deepcopy(old_layout)


def _reset_child_row(row: object) -> None:
	for fieldname in ("name", "parent", "parentfield", "parenttype"):
		if hasattr(row, fieldname):
			setattr(row, fieldname, None)


def _revision_layout_code(layout_code: str, revision_no: int) -> str:
	base = layout_code.rsplit("-R", 1)[0]
	return f"{base}-R{revision_no}"
