from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from sheet_cutting_layout.overrides.bom import APP_CONTROLLED_BOM_UPDATE_FLAG
from sheet_cutting_layout.services.bom_service import (
	BomDocument,
	build_bom_from_layout_row,
	resolve_scrap_item_rate,
)
from sheet_cutting_layout.services.validators import validate_sheet_cutting_layout
from sheet_cutting_layout.services.versioning import finalize_new_revision_release

try:
	import frappe
except ImportError:
	frappe = None

_ = getattr(frappe, "_", lambda message: message)

LayoutReleaseStatus = Literal["Approved by Purchase", "Released"]


class EndPieceRow(Protocol):
	weight_kg: float
	qty_per_sheet: float
	disposition: str
	scrap_item: str | None


class ReleaseValidator(Protocol):
	def __call__(self, layout: ReleaseLayoutDocument) -> None: ...


class FinishedPartRow(Protocol):
	finished_part_item: str
	parts_per_sheet: int
	gross_weight_per_part_kg: float
	scrap_weight_per_part_kg: float
	generated_bom: str | None


class ReleaseLayoutDocument(Protocol):
	name: str
	project: str
	status: LayoutReleaseStatus
	raw_material_item: str
	process_scrap_item: str
	no_of_strips: int
	weight_per_sheet_kg: float
	finished_part_code: str | None
	net_weight_per_part_kg: float | None
	gross_weight_per_part_kg: float | None
	scrap_weight_per_part_kg: float | None
	generated_bom: str | None
	parts_per_sheet: int
	end_pieces: Sequence[EndPieceRow]
	finished_parts: Sequence[FinishedPartRow]


class BomRecord(Protocol):
	name: str
	item: str
	custom_operation: str | None
	sheet_cutting_layout: str | None
	is_active: bool
	disabled: bool
	status: str


@dataclass
class ReleaseResult:
	status: LayoutReleaseStatus
	generated_boms: list[BomDocument] = field(default_factory=list)
	superseded_layout: object | None = None


@dataclass
class ReleaseContext:
	layouts: Sequence[object] = ()
	boms: list[BomRecord] | None = None


@dataclass
class ParentFinishedPartRow:
	finished_part_item: str
	parts_per_sheet: int
	gross_weight_per_part_kg: float
	scrap_weight_per_part_kg: float
	generated_bom: str | None = None


@dataclass
class FinishedPartReferenceRow:
	finished_part_item: str
	bom_quantity: float | None
	scrap_weight_kg: float | None
	raw_material_weight_kg: float | None


ReleaseContextProvider = Callable[[ReleaseLayoutDocument], ReleaseContext]
BomDocumentFactory = Callable[[ReleaseLayoutDocument, FinishedPartRow, int], BomDocument]


def release_layout(
	layout: ReleaseLayoutDocument,
	*,
	layouts: Sequence[object] | None = None,
	boms: list[BomRecord] | None = None,
	release_context: ReleaseContext | None = None,
	release_context_provider: ReleaseContextProvider | None = None,
	validators: Sequence[ReleaseValidator] = (),
	bom_name_factory: Callable[[ReleaseLayoutDocument, FinishedPartRow, int], str] | None = None,
	bom_document_factory: BomDocumentFactory | None = None,
) -> ReleaseResult:
	if release_context is None and layouts is None and boms is None:
		provider = release_context_provider or get_release_context
		release_context = provider(layout)
	if release_context is not None:
		layouts = release_context.layouts if layouts is None else layouts
		boms = release_context.boms if boms is None else boms

	layouts = () if layouts is None else layouts

	release_validators: Sequence[ReleaseValidator] = validators or (validate_sheet_cutting_layout,)
	for validator in release_validators:
		validator(layout)

	generated_boms = _generate_boms(layout, bom_name_factory, bom_document_factory)
	if boms is not None:
		boms.extend(generated_boms)

	_activate_boms(generated_boms)
	layout.status = "Released"
	if layouts:
		finalize_new_revision_release(layouts, layout, generated_boms)  # type: ignore[arg-type]
	_sync_finished_part_reference_rows(layout, generated_boms, _release_finished_part_rows(layout))
	if layouts:
		_save_layout_records(_release_layout_records(layouts, layout))
	_save_bom_records(generated_boms)

	return ReleaseResult(
		status=layout.status,
		generated_boms=generated_boms,
		superseded_layout=None,
	)


def deactivate_generated_bom(layout: object) -> object | None:
	generated_bom = str(getattr(layout, "generated_bom", "") or "").strip()
	if not generated_bom or not frappe:
		return None

	bom_doc = frappe.get_doc("BOM", generated_bom)
	_set_frappe_field_if_supported(bom_doc, "is_active", 0)
	_set_frappe_field_if_supported(bom_doc, "disabled", 1)
	_set_frappe_field_if_supported(bom_doc, "status", "Superseded")
	if _is_submitted_document(bom_doc) and hasattr(bom_doc, "db_set"):
		bom_doc.db_set(
			{"is_active": 0, "disabled": 1, "status": "Superseded"},
			update_modified=True,
			notify=False,
		)
	else:
		_mark_bom_app_controlled(bom_doc)
		bom_doc.save(ignore_permissions=True)
	return bom_doc


def get_release_context(layout: ReleaseLayoutDocument) -> ReleaseContext:
	if not frappe:
		raise RuntimeError("Frappe is required to build Sheet Cutting Layout release context")

	layouts = _get_same_project_layouts(layout)
	boms = _get_finished_part_boms(layout)
	return ReleaseContext(layouts=layouts, boms=boms)


def _generate_boms(
	layout: ReleaseLayoutDocument,
	bom_name_factory: Callable[[ReleaseLayoutDocument, FinishedPartRow, int], str] | None,
	bom_document_factory: BomDocumentFactory | None,
) -> list[BomDocument]:
	finished_parts = _release_finished_part_rows(layout)
	generated_boms: list[BomDocument] = []

	for index, finished_part in enumerate(finished_parts, start=1):
		bom = (
			bom_document_factory(layout, finished_part, index)
			if bom_document_factory is not None
			else _default_bom_document_factory(layout, finished_part, index, bom_name_factory)
		)
		finished_part.generated_bom = bom.name
		_set_frappe_field_if_supported(layout, "generated_bom", bom.name)
		generated_boms.append(bom)

	return generated_boms


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
	bom.sheet_cutting_layout = getattr(layout, "name", None)

	if not frappe:
		raise RuntimeError("Frappe is required to persist generated BOM documents")

	return _insert_frappe_bom(bom)


def _insert_frappe_bom(bom: BomDocument) -> BomDocument:
	if not frappe:
		raise RuntimeError("Frappe is required to persist generated BOM documents")

	bom_doc = frappe.new_doc("BOM")
	if bom.name:
		bom_doc.name = bom.name
	bom_doc.item = bom.item
	bom_doc.company = _company_for_layout(getattr(bom, "_layout", None))
	bom_doc.quantity = bom.quantity
	bom_doc.uom = "Kg"
	bom_doc.is_active = 0
	bom_doc.disabled = 1
	bom_doc.custom_operation = "Shearing"
	bom_doc.sheet_cutting_layout = bom.sheet_cutting_layout or getattr(
		getattr(bom, "_layout", None), "name", None
	)
	_mark_bom_app_controlled(bom_doc)
	for row in bom.items:
		bom_doc.append(
			"items",
			{
				"item_code": row.item_code,
				"qty": row.qty,
				"uom": row.uom,
			},
		)
	for row in bom.scrap_items:
		try:
			rate = resolve_scrap_item_rate(
				item_code=row.item_code,
				company=bom_doc.company,
				existing_rate=getattr(row, "rate", None),
			)
		except ValueError as error:
			frappe.throw(
				_("Failed to resolve valuation rate for scrap item {0}: {1}").format(
					row.item_code,
					str(error),
				)
			)
		bom_doc.append(
			"scrap_items",
			{
				"item_code": row.item_code,
				"stock_qty": row.qty,
				"qty": row.qty,
				"uom": row.uom,
				"rate": rate,
			},
		)
	bom_doc.insert()

	bom.name = bom_doc.name
	bom.is_active = bool(getattr(bom_doc, "is_active", False))
	bom.disabled = bool(getattr(bom_doc, "disabled", True))
	bom.status = "Active"
	return bom


def _release_finished_part_rows(layout: ReleaseLayoutDocument) -> list[FinishedPartRow]:
	return _parent_finished_part_rows(layout)


def _parent_finished_part_rows(layout: ReleaseLayoutDocument) -> list[ParentFinishedPartRow]:
	finished_part_code = str(getattr(layout, "finished_part_code", "") or "").strip()
	if not finished_part_code:
		return []

	return [
		ParentFinishedPartRow(
			finished_part_item=finished_part_code,
			parts_per_sheet=int(getattr(layout, "parts_per_sheet", 0) or 0),
			gross_weight_per_part_kg=float(getattr(layout, "gross_weight_per_part_kg", 0) or 0),
			scrap_weight_per_part_kg=float(getattr(layout, "scrap_weight_per_part_kg", 0) or 0),
			generated_bom=getattr(layout, "generated_bom", None),
		)
	]


def _sync_finished_part_reference_rows(
	layout: ReleaseLayoutDocument,
	generated_boms: Sequence[BomDocument],
	finished_parts: Sequence[FinishedPartRow],
) -> None:
	references = [
		{
			"finished_part_item": finished_part.finished_part_item,
			"bom_quantity": bom.quantity,
			"scrap_weight_kg": _sum_bom_qty(bom.scrap_items),
			"raw_material_weight_kg": _sum_bom_qty(bom.items),
		}
		for finished_part, bom in zip(finished_parts, generated_boms, strict=False)
	]
	set_child_table = getattr(layout, "set", None)
	if callable(set_child_table):
		set_child_table("finished_parts", references)
		return
	layout.finished_parts = [FinishedPartReferenceRow(**row) for row in references]


def _activate_boms(boms: Sequence[BomRecord]) -> None:
	for bom in boms:
		bom.is_active = True
		bom.disabled = False
		bom.status = "Active"


def _release_layout_records(
	layouts: Sequence[object],
	layout: ReleaseLayoutDocument,
) -> Sequence[object]:
	layout_name = getattr(layout, "name", None)
	for existing_layout in layouts:
		if getattr(existing_layout, "name", None) == layout_name:
			return (existing_layout,)
	return (layout,)


def _get_same_project_layouts(layout: ReleaseLayoutDocument) -> list[object]:
	if not frappe:
		raise RuntimeError("Frappe is required to discover same-project layouts")

	project = getattr(layout, "project", None)
	if not project:
		return [layout]

	layout_names = frappe.get_all(
		"Sheet Cutting Layout",
		filters={"project": project},
		pluck="name",
	)
	layouts = [frappe.get_doc("Sheet Cutting Layout", name) for name in layout_names]
	if getattr(layout, "name", None) not in {getattr(existing, "name", None) for existing in layouts}:
		layouts.append(layout)
	return layouts


def _get_finished_part_boms(layout: ReleaseLayoutDocument) -> list[BomRecord]:
	if not frappe:
		raise RuntimeError("Frappe is required to discover BOM records")

	finished_part_items = [
		row.finished_part_item for row in _release_finished_part_rows(layout) if row.finished_part_item
	]
	if not finished_part_items:
		return []

	bom_names = frappe.get_all(
		"BOM",
		filters={"item": ["in", finished_part_items], "custom_operation": "Shearing"},
		pluck="name",
	)
	return [frappe.get_doc("BOM", name) for name in bom_names]


def _save_bom_records(boms: Sequence[BomRecord]) -> None:
	if not frappe:
		return

	for bom in boms:
		bom_doc = bom if hasattr(bom, "save") else frappe.get_doc("BOM", bom.name)
		_set_frappe_field_if_supported(bom_doc, "is_active", 1 if bom.is_active else 0)
		_set_frappe_field_if_supported(bom_doc, "disabled", 1 if bom.disabled else 0)
		_set_frappe_field_if_supported(bom_doc, "status", bom.status)
		_mark_bom_app_controlled(bom_doc)
		bom_doc.save(ignore_permissions=True)


def _save_layout_records(layouts: Sequence[object]) -> None:
	if not frappe:
		return

	for layout in layouts:
		if _is_submitted_document(layout) and hasattr(layout, "db_set"):
			layout.db_set(
				{
					"status": getattr(layout, "status", None),
					"is_active": getattr(layout, "is_active", None),
				},
				update_modified=True,
				notify=False,
			)
		elif hasattr(layout, "save"):
			layout.save(ignore_permissions=True)


def _is_submitted_document(doc: object) -> bool:
	docstatus = getattr(doc, "docstatus", None)
	if docstatus == 1:
		return True
	is_submitted = getattr(docstatus, "is_submitted", None)
	return bool(callable(is_submitted) and is_submitted())


def _company_for_layout(layout: object | None) -> str:
	if layout is not None:
		company = getattr(layout, "company", None)
		if company:
			return company

	if not frappe:
		raise RuntimeError("Frappe is required to resolve BOM company")

	company = frappe.defaults.get_user_default("Company")
	if company:
		return company

	db = getattr(frappe, "db", None)
	if db is not None and hasattr(db, "get_default"):
		company = db.get_default("company")
		if company:
			return company

	frappe.throw(_("Company is required to create generated BOMs"))
	raise RuntimeError("Company is required to create generated BOMs")


def _set_frappe_field_if_supported(doc: object, fieldname: str, value: object) -> None:
	meta = getattr(doc, "meta", None)
	if meta is not None and hasattr(meta, "has_field") and not meta.has_field(fieldname):
		return
	if meta is None and not hasattr(doc, fieldname):
		return
	setattr(doc, fieldname, value)


def _sum_bom_qty(rows: Sequence[object]) -> float:
	return sum(float(getattr(row, "qty", 0) or 0) for row in rows)


def _mark_bom_app_controlled(bom_doc: object) -> None:
	flags = getattr(bom_doc, "flags", None)
	if flags is None:
		flags = type("Flags", (), {})()
		bom_doc.flags = flags
	setattr(flags, APP_CONTROLLED_BOM_UPDATE_FLAG, True)
