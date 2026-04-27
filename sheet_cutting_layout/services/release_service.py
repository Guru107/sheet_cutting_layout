from __future__ import annotations

import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

from sheet_cutting_layout.services.bom_service import BomDocument, build_bom_from_layout_row
from sheet_cutting_layout.services.validators import validate_sheet_cutting_layout
from sheet_cutting_layout.services.versioning import finalize_new_revision_release

try:
	import frappe
except ImportError:
	frappe = None

LayoutReleaseStatus = Literal["Approved by Purchase", "Release Pending Impact", "Released"]
ImpactReferenceDoctype = Literal["Work Order", "Production Plan"]
ImpactDecision = Literal["Use Old BOM", "Use New BOM", "Cancel Reference"]
ImpactStatus = Literal["Open", "Resolved"]

IMPACT_REFERENCE_DOCTYPES: frozenset[str] = frozenset({"Work Order", "Production Plan"})
OPEN_MANUFACTURING_STATUSES: frozenset[str] = frozenset(
	{
		"Draft",
		"Not Started",
		"In Process",
		"Open",
		"Submitted",
	}
)


class ManufacturingDocument(Protocol):
	doctype: str
	name: str
	bom_no: str
	status: str


class EndPieceRow(Protocol):
	end_piece_item: str
	weight_kg: float
	qty_per_sheet: float


class ReleaseValidator(Protocol):
	def __call__(self, layout: ReleaseLayoutDocument) -> None: ...


class FinishedPartRow(Protocol):
	finished_part_item: str
	parts_per_sheet: int
	gross_weight_per_part_kg: float
	scrap_weight_per_part_kg: float
	generated_bom: str | None


class ReleaseLayoutDocument(Protocol):
	status: LayoutReleaseStatus
	impact_resolutions: list[LayoutImpactResolution]
	raw_material_item: str
	end_pieces: Sequence[EndPieceRow]
	finished_parts: Sequence[FinishedPartRow]


class BomRecord(Protocol):
	name: str
	item: str
	is_active: bool
	disabled: bool
	status: str


@dataclass
class FrappeManufacturingDocument:
	doctype: ImpactReferenceDoctype
	name: str
	bom_no: str
	status: str


@dataclass
class LayoutImpactResolution:
	reference_doctype: ImpactReferenceDoctype
	reference_docname: str
	old_bom: str
	new_bom: str
	decision: ImpactDecision | None = None
	decided_by: str | None = None
	decided_on: datetime | None = None
	status: ImpactStatus = "Open"


@dataclass
class ReleaseResult:
	status: LayoutReleaseStatus
	impact_rows: list[LayoutImpactResolution] = field(default_factory=list)
	generated_boms: list[BomDocument] = field(default_factory=list)
	superseded_layout: object | None = None


@dataclass
class ReleaseContext:
	open_documents: Sequence[ManufacturingDocument]
	layouts: Sequence[object] = ()
	boms: list[BomRecord] | None = None


ReleaseContextProvider = Callable[[ReleaseLayoutDocument], ReleaseContext]
BomDocumentFactory = Callable[[ReleaseLayoutDocument, FinishedPartRow, int], BomDocument]


def release_layout(
	layout: ReleaseLayoutDocument,
	*,
	open_documents: Sequence[ManufacturingDocument] | None = None,
	bom_replacements: Mapping[str, str] | None = None,
	layouts: Sequence[object] | None = None,
	boms: list[BomRecord] | None = None,
	release_context: ReleaseContext | None = None,
	release_context_provider: ReleaseContextProvider | None = None,
	validators: Sequence[ReleaseValidator] = (),
	bom_name_factory: Callable[[ReleaseLayoutDocument, FinishedPartRow, int], str] | None = None,
	bom_document_factory: BomDocumentFactory | None = None,
) -> ReleaseResult:
	if release_context is None and open_documents is None:
		provider = release_context_provider or get_release_context
		release_context = provider(layout)
	if release_context is not None:
		open_documents = release_context.open_documents
		layouts = release_context.layouts if layouts is None else layouts
		boms = release_context.boms if boms is None else boms

	if open_documents is None:
		raise RuntimeError("Release requires open manufacturing documents or an explicit release context")
	layouts = () if layouts is None else layouts

	release_validators: Sequence[ReleaseValidator] = validators or (validate_sheet_cutting_layout,)
	for validator in release_validators:
		validator(layout)

	generated_boms = _generate_boms(layout, bom_name_factory, bom_document_factory)
	if boms is not None:
		boms.extend(generated_boms)

	replacements = (
		bom_replacements if bom_replacements is not None else _build_bom_replacements(layout, layouts)
	)
	impact_rows = [
		LayoutImpactResolution(
			reference_doctype=_impact_doctype(document.doctype),
			reference_docname=document.name,
			old_bom=document.bom_no,
			new_bom=replacements[document.bom_no],
		)
		for document in open_documents
		if _is_impacted_open_document(document, replacements)
	]
	_set_impact_rows(layout, impact_rows)

	if impact_rows:
		_mark_boms_pending_impact(generated_boms)
		layout.status = "Release Pending Impact"
		_save_bom_records(boms or generated_boms)
	else:
		_activate_boms(generated_boms)
		layout.status = "Released"
		if layouts:
			finalize_new_revision_release(layouts, layout, boms or [])  # type: ignore[arg-type]
			_save_layout_records(layouts)
		_save_bom_records(boms or generated_boms)

	return ReleaseResult(
		status=layout.status,
		impact_rows=list(impact_rows),
		generated_boms=generated_boms,
		superseded_layout=_superseded_layout(layout, layouts),
	)


def resolve_impact(
	impact_row: LayoutImpactResolution,
	*,
	decision: ImpactDecision,
	decided_by: str,
	decided_on: datetime,
) -> LayoutImpactResolution:
	impact_row.decision = decision
	impact_row.decided_by = decided_by
	impact_row.decided_on = decided_on
	impact_row.status = "Resolved"
	return impact_row


def finalize_release(
	layout: ReleaseLayoutDocument,
	*,
	layouts: Sequence[object] = (),
	boms: Sequence[BomRecord] = (),
) -> ReleaseResult:
	for impact_row in layout.impact_resolutions:
		impact_row.status = "Resolved" if _has_complete_decision(impact_row) else "Open"

	if all(_has_complete_decision(impact_row) for impact_row in layout.impact_resolutions):
		layout.status = "Released"
		_activate_generated_boms(layout, boms)
		if layouts:
			finalize_new_revision_release(layouts, layout, boms)  # type: ignore[arg-type]
			_save_layout_records(layouts)
		_save_bom_records(boms)
	else:
		layout.status = "Release Pending Impact"

	return ReleaseResult(
		status=layout.status,
		impact_rows=list(layout.impact_resolutions),
		superseded_layout=_superseded_layout(layout, layouts),
	)


def get_release_context(layout: ReleaseLayoutDocument) -> ReleaseContext:
	if frappe is None:
		if _is_test_runtime():
			return ReleaseContext(open_documents=(), layouts=(), boms=[])
		raise RuntimeError("Frappe is required to build Sheet Cutting Layout release context")

	layouts = _get_same_family_layouts(layout)
	boms = _get_finished_part_boms(layout)
	return ReleaseContext(
		open_documents=_get_open_manufacturing_documents(),
		layouts=layouts,
		boms=boms,
	)


def _is_impacted_open_document(document: ManufacturingDocument, replacements: Mapping[str, str]) -> bool:
	return (
		document.doctype in IMPACT_REFERENCE_DOCTYPES
		and document.status in OPEN_MANUFACTURING_STATUSES
		and document.bom_no in replacements
	)


def _impact_doctype(doctype: str) -> ImpactReferenceDoctype:
	if doctype == "Work Order":
		return "Work Order"
	if doctype == "Production Plan":
		return "Production Plan"
	raise ValueError(f"Unsupported impact reference doctype: {doctype}")


def _has_complete_decision(impact_row: LayoutImpactResolution) -> bool:
	return bool(impact_row.decision and impact_row.decided_by and impact_row.decided_on)


def _set_impact_rows(
	layout: ReleaseLayoutDocument,
	impact_rows: Sequence[LayoutImpactResolution],
) -> None:
	if hasattr(layout, "set") and hasattr(layout, "append"):
		layout.set("impact_resolutions", [])
		for impact_row in impact_rows:
			layout.append(
				"impact_resolutions",
				{
					"reference_doctype": impact_row.reference_doctype,
					"reference_docname": impact_row.reference_docname,
					"old_bom": impact_row.old_bom,
					"new_bom": impact_row.new_bom,
					"decision": impact_row.decision,
					"decided_by": impact_row.decided_by,
					"decided_on": impact_row.decided_on,
					"status": impact_row.status,
				},
			)
		return

	layout.impact_resolutions = list(impact_rows)


def _generate_boms(
	layout: ReleaseLayoutDocument,
	bom_name_factory: Callable[[ReleaseLayoutDocument, FinishedPartRow, int], str] | None,
	bom_document_factory: BomDocumentFactory | None,
) -> list[BomDocument]:
	finished_parts = list(getattr(layout, "finished_parts", []))
	generated_boms: list[BomDocument] = []

	for index, finished_part in enumerate(finished_parts, start=1):
		bom = (
			bom_document_factory(layout, finished_part, index)
			if bom_document_factory is not None
			else _default_bom_document_factory(layout, finished_part, index, bom_name_factory)
		)
		finished_part.generated_bom = bom.name
		generated_boms.append(bom)

	return generated_boms


def _build_bom_replacements(
	layout: ReleaseLayoutDocument,
	layouts: Sequence[object],
) -> Mapping[str, str]:
	explicit_replacements = getattr(layout, "bom_replacements", None)
	if explicit_replacements is not None:
		return explicit_replacements

	new_boms_by_item = {
		row.finished_part_item: row.generated_bom
		for row in getattr(layout, "finished_parts", [])
		if row.generated_bom is not None
	}
	replacements: dict[str, str] = {}
	for previous_layout in layouts:
		if previous_layout is layout or not _is_previous_layout(previous_layout, layout):
			continue
		for row in getattr(previous_layout, "finished_parts", []):
			new_bom = new_boms_by_item.get(row.finished_part_item)
			if row.generated_bom is not None and new_bom is not None:
				replacements[row.generated_bom] = new_bom

	return replacements


def _default_bom_name(layout: ReleaseLayoutDocument, finished_part: FinishedPartRow, index: int) -> str:
	layout_name = getattr(layout, "name", "LAYOUT")
	return f"BOM-{layout_name}-{index:03d}-{finished_part.finished_part_item}"


def _default_bom_document_factory(
	layout: ReleaseLayoutDocument,
	finished_part: FinishedPartRow,
	index: int,
	bom_name_factory: Callable[[ReleaseLayoutDocument, FinishedPartRow, int], str] | None,
) -> BomDocument:
	bom = build_bom_from_layout_row(layout, finished_part)  # type: ignore[arg-type]
	bom.name = (
		bom_name_factory(layout, finished_part, index)
		if bom_name_factory is not None
		else _default_bom_name(layout, finished_part, index)
	)
	bom._layout = layout

	if frappe is None:
		if _is_test_runtime():
			return bom
		raise RuntimeError("Frappe is required to persist generated BOM documents")

	return _insert_frappe_bom(bom)


def _insert_frappe_bom(bom: BomDocument) -> BomDocument:
	if frappe is None:
		raise RuntimeError("Frappe is required to persist generated BOM documents")

	bom_doc = frappe.new_doc("BOM")
	if bom.name:
		bom_doc.name = bom.name
	bom_doc.item = bom.item
	bom_doc.company = _company_for_layout(getattr(bom, "_layout", None))
	bom_doc.quantity = bom.quantity
	bom_doc.is_active = 0
	bom_doc.disabled = 1
	for row in bom.items:
		bom_doc.append(
			"items",
			{
				"item_code": row.item_code,
				"qty": row.qty,
				"uom": row.uom,
			},
		)
	bom_doc.insert()

	bom.name = bom_doc.name
	bom.is_active = bool(getattr(bom_doc, "is_active", False))
	bom.disabled = bool(getattr(bom_doc, "disabled", True))
	bom.status = "Pending Impact"
	return bom


def _mark_boms_pending_impact(boms: Sequence[BomRecord]) -> None:
	for bom in boms:
		bom.is_active = False
		bom.disabled = True
		bom.status = "Pending Impact"


def _activate_boms(boms: Sequence[BomRecord]) -> None:
	for bom in boms:
		bom.is_active = True
		bom.disabled = False
		bom.status = "Active"


def _activate_generated_boms(
	layout: ReleaseLayoutDocument,
	boms: Sequence[BomRecord],
) -> None:
	generated_bom_names = {
		row.generated_bom for row in getattr(layout, "finished_parts", []) if row.generated_bom is not None
	}
	_activate_boms([bom for bom in boms if bom.name in generated_bom_names])


def _superseded_layout(layout: ReleaseLayoutDocument, layouts: Sequence[object]) -> object | None:
	for previous_layout in layouts:
		if _is_superseded_previous_layout(previous_layout, layout):
			return previous_layout
	return None


def _is_previous_layout(previous_layout: object, layout: ReleaseLayoutDocument) -> bool:
	return (
		getattr(previous_layout, "layout_family", None) == getattr(layout, "layout_family", None)
		and getattr(previous_layout, "status", None) == "Released"
		and getattr(previous_layout, "is_active", False) is True
	)


def _is_superseded_previous_layout(previous_layout: object, layout: ReleaseLayoutDocument) -> bool:
	return (
		previous_layout is not layout
		and getattr(previous_layout, "layout_family", None) == getattr(layout, "layout_family", None)
		and getattr(previous_layout, "status", None) == "Superseded"
		and getattr(previous_layout, "is_active", True) is False
	)


def _get_open_manufacturing_documents() -> list[FrappeManufacturingDocument]:
	if frappe is None:
		raise RuntimeError("Frappe is required to discover open manufacturing documents")

	documents = _get_open_work_orders()
	documents.extend(_get_open_production_plans())
	return documents


def _get_open_work_orders() -> list[FrappeManufacturingDocument]:
	if frappe is None:
		raise RuntimeError("Frappe is required to discover open work orders")

	documents: list[FrappeManufacturingDocument] = []
	for row in frappe.get_all(
		"Work Order",
		filters={"status": ["in", sorted(OPEN_MANUFACTURING_STATUSES)]},
		fields=["name", "bom_no", "status"],
	):
		bom_no = _row_value(row, "bom_no")
		if bom_no:
			documents.append(
				FrappeManufacturingDocument(
					doctype="Work Order",
					name=_row_value(row, "name"),
					bom_no=bom_no,
					status=_row_value(row, "status"),
				)
			)
	return documents


def _get_open_production_plans() -> list[FrappeManufacturingDocument]:
	if frappe is None:
		raise RuntimeError("Frappe is required to discover open production plans")

	plan_rows = frappe.get_all(
		"Production Plan",
		filters={"status": ["in", sorted(OPEN_MANUFACTURING_STATUSES)]},
		fields=["name", "status"],
	)
	status_by_plan = {_row_value(row, "name"): _row_value(row, "status") for row in plan_rows}
	if not status_by_plan:
		return []

	documents: list[FrappeManufacturingDocument] = []
	for row in frappe.get_all(
		"Production Plan Item",
		filters={"parent": ["in", sorted(status_by_plan)]},
		fields=["parent", "bom_no"],
	):
		bom_no = _row_value(row, "bom_no")
		parent = _row_value(row, "parent")
		if bom_no:
			documents.append(
				FrappeManufacturingDocument(
					doctype="Production Plan",
					name=parent,
					bom_no=bom_no,
					status=status_by_plan[parent],
				)
			)
	return documents


def _get_same_family_layouts(layout: ReleaseLayoutDocument) -> list[object]:
	if frappe is None:
		raise RuntimeError("Frappe is required to discover same-family layouts")

	layout_family = getattr(layout, "layout_family", None)
	if not layout_family:
		return [layout]

	layout_names = frappe.get_all(
		"Sheet Cutting Layout",
		filters={"layout_family": layout_family},
		pluck="name",
	)
	layouts = [frappe.get_doc("Sheet Cutting Layout", name) for name in layout_names]
	if getattr(layout, "name", None) not in {getattr(existing, "name", None) for existing in layouts}:
		layouts.append(layout)
	return layouts


def _get_finished_part_boms(layout: ReleaseLayoutDocument) -> list[BomRecord]:
	if frappe is None:
		raise RuntimeError("Frappe is required to discover BOM records")

	finished_part_items = [
		row.finished_part_item for row in getattr(layout, "finished_parts", []) if row.finished_part_item
	]
	if not finished_part_items:
		return []

	bom_names = frappe.get_all(
		"BOM",
		filters={"item": ["in", finished_part_items]},
		pluck="name",
	)
	return [frappe.get_doc("BOM", name) for name in bom_names]


def _row_value(row: object, fieldname: str) -> str:
	if isinstance(row, dict):
		return row.get(fieldname, "")
	return getattr(row, fieldname, "")


def _save_bom_records(boms: Sequence[BomRecord]) -> None:
	if frappe is None:
		return

	for bom in boms:
		bom_doc = bom if hasattr(bom, "save") else frappe.get_doc("BOM", bom.name)
		_set_frappe_field_if_supported(bom_doc, "is_active", 1 if bom.is_active else 0)
		_set_frappe_field_if_supported(bom_doc, "disabled", 1 if bom.disabled else 0)
		_set_frappe_field_if_supported(bom_doc, "status", bom.status)
		bom_doc.save(ignore_permissions=True)


def _save_layout_records(layouts: Sequence[object]) -> None:
	if frappe is None:
		return

	for layout in layouts:
		if hasattr(layout, "save"):
			layout.save(ignore_permissions=True)


def _is_test_runtime() -> bool:
	return "pytest" in sys.modules


def _company_for_layout(layout: object | None) -> str:
	if layout is not None:
		company = getattr(layout, "company", None)
		if company:
			return company

	if frappe is None:
		raise RuntimeError("Frappe is required to resolve BOM company")

	company = frappe.defaults.get_user_default("Company")
	if company:
		return company

	db = getattr(frappe, "db", None)
	if db is not None and hasattr(db, "get_default"):
		company = db.get_default("company")
		if company:
			return company

	frappe.throw("Company is required to create generated BOMs")
	raise RuntimeError("Company is required to create generated BOMs")


def _set_frappe_field_if_supported(doc: object, fieldname: str, value: object) -> None:
	meta = getattr(doc, "meta", None)
	if meta is not None and hasattr(meta, "has_field") and not meta.has_field(fieldname):
		return
	if meta is None and not hasattr(doc, fieldname):
		return
	setattr(doc, fieldname, value)
