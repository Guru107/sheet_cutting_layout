from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

import frappe

from sheet_cutting_layout.overrides.bom import mark_bom_app_controlled
from sheet_cutting_layout.services.bom_service import (
	BomDocument,
	BomItemRow,
	ParentFinishedPartRow,
	build_bom_from_layout_row,
	parent_finished_part_row,
	twin_finished_part_row,
)
from sheet_cutting_layout.services.end_piece_item_service import ensure_end_piece_item
from sheet_cutting_layout.services.validators import collect_descendant_layouts, validate_sheet_cutting_layout
from sheet_cutting_layout.services.versioning import finalize_new_revision_release

_ = frappe._

LayoutReleaseStatus = Literal["Approved by Purchase", "Released"]


class EndPieceRow(Protocol):
	weight_kg: float
	disposition: str
	scrap_item: str | None
	child_layout: str | None


class ReleaseValidator(Protocol):
	def __call__(self, layout: ReleaseLayoutDocument) -> None: ...


class FinishedPartRow(Protocol):
	finished_part_item: str
	parts_per_sheet: int
	gross_weight_per_part_kg: float
	scrap_weight_per_part_kg: float
	orientation: str | None


class ReleaseLayoutDocument(Protocol):
	name: str
	project: str
	status: LayoutReleaseStatus
	raw_material_item: str
	process_scrap_item: str
	no_of_strips: int
	weight_per_sheet_kg: float
	finished_part_code: str | None
	is_lh_rh: int | bool | None
	orientation: str | None
	twin_finished_part: str | None
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


@dataclass
class ReleaseResult:
	status: LayoutReleaseStatus
	generated_boms: list[BomDocument] = field(default_factory=list)


@dataclass
class ReleaseContext:
	layouts: Sequence[object] = ()
	boms: list[BomRecord] | None = None


@dataclass
class FinishedPartReferenceRow:
	finished_part_item: str
	bom_quantity: float | None
	scrap_weight_kg: float | None
	raw_material_weight_kg: float | None
	generated_bom: str | None = None
	orientation: str | None = None


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
		finalize_new_revision_release(layout)  # type: ignore[arg-type]
	_sync_finished_part_reference_rows(layout, generated_boms, _parent_finished_part_rows(layout))
	if layouts:
		# Always persist the in-memory layout being released. The release context
		# contains a re-fetched copy of the same record; saving that copy instead
		# would write the pre-release status back and lose generated_bom.
		_save_layout_records((layout,))
	_save_bom_records(generated_boms)

	return ReleaseResult(status=layout.status, generated_boms=generated_boms)


def retire_layout(layout: object) -> None:
	for index, bom_name in enumerate(_layout_bom_names(layout), start=1):
		bom_doc = frappe.get_doc("BOM", bom_name)
		if _is_cancelled_document(bom_doc):
			continue

		save_point = f"scl_retire_bom_{index}"
		frappe.db.savepoint(save_point)
		mark_bom_app_controlled(bom_doc)
		try:
			bom_doc.cancel()
		except frappe.LinkExistsError:
			frappe.db.rollback(save_point=save_point)
			bom_doc = frappe.get_doc("BOM", bom_name)
			mark_bom_app_controlled(bom_doc)
			bom_doc.db_set("is_active", 0, update_modified=False)


def _layout_bom_names(layout: object) -> list[str]:
	names: list[str] = []

	_append_unique_clean(names, getattr(layout, "generated_bom", None))
	for row in getattr(layout, "finished_parts", []) or []:
		_append_unique_clean(names, getattr(row, "generated_bom", None))
	for row in getattr(layout, "end_pieces", []) or []:
		_append_unique_clean(names, getattr(row, "generated_end_piece_bom", None))

	layout_name = str(getattr(layout, "name", "") or "").strip()
	db = getattr(frappe, "db", None)
	get_all = getattr(db, "get_all", None)
	if layout_name and callable(get_all):
		for bom_name in get_all("BOM", filters={"sheet_cutting_layout": layout_name}, pluck="name"):
			_append_unique_clean(names, bom_name)

	return names


def collect_descendant_layout_names(
	layout: object,
	load_layout: Callable[[str], object],
) -> list[str]:
	"""Return descendant layout names via end-piece child_layout links, leaves first."""

	def child_links(layout_name: str) -> list[str]:
		source = layout if layout_name == _layout_name(layout) else load_layout(layout_name)
		return _child_layout_links(source)

	layout_name = _layout_name(layout)
	if not layout_name:
		return []
	return collect_descendant_layouts(layout_name, child_links)


def cancel_descendant_layouts(layout: object) -> list[str]:
	"""Cancel descendant layouts leaves-first through the native document lifecycle."""
	cancelled: list[str] = []

	def load_layout(layout_name: str) -> object:
		return frappe.get_doc("Sheet Cutting Layout", layout_name)

	for descendant_name in collect_descendant_layout_names(layout, load_layout):
		descendant = frappe.get_doc("Sheet Cutting Layout", descendant_name)
		if _is_cancelled_document(descendant) or not _is_submitted_document(descendant):
			continue
		if hasattr(descendant, "status"):
			descendant.status = "Superseded"
		ignore_linked_doctypes = list(getattr(descendant, "ignore_linked_doctypes", None) or [])
		for doctype in ("BOM", "Sheet Cutting Layout"):
			if doctype not in ignore_linked_doctypes:
				ignore_linked_doctypes.append(doctype)
		descendant.ignore_linked_doctypes = ignore_linked_doctypes
		descendant.cancel()
		cancelled.append(descendant_name)
	return cancelled


def _child_layout_links(source: object) -> list[str]:
	names: list[str] = []
	for row in getattr(source, "end_pieces", []) or []:
		_append_unique_clean(names, getattr(row, "child_layout", None))
	return names


def _layout_name(layout: object) -> str:
	return str(getattr(layout, "name", "") or "").strip()


def _append_unique_clean(values: list[str], value: object) -> None:
	clean_value = str(value or "").strip()
	if clean_value and clean_value not in values:
		values.append(clean_value)


def get_release_context(layout: ReleaseLayoutDocument) -> ReleaseContext:
	layouts = _get_same_project_layouts(layout)
	boms = _get_finished_part_boms(layout)
	return ReleaseContext(layouts=layouts, boms=boms)


def _generate_boms(
	layout: ReleaseLayoutDocument,
	bom_name_factory: Callable[[ReleaseLayoutDocument, FinishedPartRow, int], str] | None,
	bom_document_factory: BomDocumentFactory | None,
) -> list[BomDocument]:
	finished_parts = _parent_finished_part_rows(layout)
	generated_boms: list[BomDocument] = []

	for index, finished_part in enumerate(finished_parts, start=1):
		bom = (
			bom_document_factory(layout, finished_part, index)
			if bom_document_factory is not None
			else _default_bom_document_factory(layout, finished_part, index, bom_name_factory)
		)
		if index == 1:
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
	bom = build_bom_from_layout_row(
		layout,
		finished_part,
		end_piece_item_code_resolver=_ensure_and_link_end_piece_item,
	)  # type: ignore[arg-type]
	bom.name = (
		bom_name_factory(layout, finished_part, index)
		if bom_name_factory is not None
		else _default_bom_name(layout, finished_part, index)
	)
	bom._layout = layout
	bom.sheet_cutting_layout = getattr(layout, "name", None)

	return _insert_frappe_bom(bom)


def _ensure_and_link_end_piece_item(
	layout: ReleaseLayoutDocument, row: object, finished_part: FinishedPartRow
) -> str:
	item_code = ensure_end_piece_item(
		layout,
		row,
		source_finished_part=finished_part.finished_part_item,
	)  # type: ignore[arg-type]
	if hasattr(row, "end_piece_item_code"):
		row.end_piece_item_code = item_code
	return item_code


def _insert_frappe_bom(bom: BomDocument) -> BomDocument:
	bom_doc = frappe.new_doc("BOM")
	if bom.name:
		bom_doc.name = bom.name
	bom_doc.item = bom.item
	bom_doc.company = _company_for_layout(getattr(bom, "_layout", None))
	bom_doc.quantity = bom.quantity
	bom_doc.custom_operation = "Shearing"
	bom_doc.sheet_cutting_layout = bom.sheet_cutting_layout or getattr(
		getattr(bom, "_layout", None), "name", None
	)
	mark_bom_app_controlled(bom_doc)
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
		_append_frappe_bom_scrap_row(bom_doc, row)
	bom_doc.insert()
	bom_doc.submit()

	bom.name = bom_doc.name
	bom.is_active = bool(getattr(bom_doc, "is_active", True))
	bom._persisted_with_frappe = True
	return bom


def _append_frappe_bom_scrap_row(bom_doc: object, row: BomItemRow) -> None:
	if _has_bom_child_table(bom_doc, "scrap_items"):
		bom_doc.append(
			"scrap_items",
			{
				"item_code": row.item_code,
				"stock_qty": row.qty,
				"stock_uom": row.uom,
			},
		)
		return

	if _has_bom_child_table(bom_doc, "secondary_items"):
		bom_doc.append(
			"secondary_items",
			{
				"type": _secondary_item_type(row),
				"item_code": row.item_code,
				"stock_qty": row.qty,
				"qty": row.qty,
				"uom": row.uom,
				"stock_uom": row.uom,
				"conversion_factor": 1,
				"cost_allocation_per": 0,
				"process_loss_per": 0,
				"process_loss_qty": 0,
				"cost": 0,
				"base_cost": 0,
			},
		)
		return

	frappe.throw(_("BOM DocType must include a scrap or secondary item table"))


def _secondary_item_type(row: BomItemRow) -> str:
	return "By-Product" if row.row_type == "end_piece_byproduct" else "Scrap"


def _has_bom_child_table(bom_doc: object, fieldname: str) -> bool:
	meta = getattr(bom_doc, "meta", None)
	if meta is not None and hasattr(meta, "get_field"):
		return meta.get_field(fieldname) is not None
	return hasattr(bom_doc, fieldname)


def _parent_finished_part_rows(layout: ReleaseLayoutDocument) -> list[ParentFinishedPartRow]:
	if not str(getattr(layout, "finished_part_code", "") or "").strip():
		return []
	rows = [parent_finished_part_row(layout)]  # type: ignore[arg-type]
	if getattr(layout, "is_lh_rh", None):
		rows.append(twin_finished_part_row(layout))  # type: ignore[arg-type]
	return rows


def _sync_finished_part_reference_rows(
	layout: ReleaseLayoutDocument,
	generated_boms: Sequence[BomDocument],
	finished_parts: Sequence[FinishedPartRow],
) -> None:
	if len(generated_boms) != len(finished_parts):
		raise ValueError("generated_boms and finished_parts length mismatch")

	references = [
		{
			"finished_part_item": finished_part.finished_part_item,
			"bom_quantity": _finished_part_bom_quantity(finished_part),
			"scrap_weight_kg": _sum_bom_qty(bom.scrap_items),
			"raw_material_weight_kg": _sum_bom_qty(bom.items),
			"generated_bom": getattr(bom, "name", None),
			"orientation": getattr(finished_part, "orientation", None),
		}
		for finished_part, bom in zip(finished_parts, generated_boms, strict=False)
	]
	set_child_table = getattr(layout, "set", None)
	if callable(set_child_table):
		set_child_table("finished_parts", references)
		return
	layout.finished_parts = [FinishedPartReferenceRow(**row) for row in references]


def _finished_part_bom_quantity(finished_part: FinishedPartRow) -> int:
	return int(getattr(finished_part, "parts_per_sheet", 0) or 0)


def _activate_boms(boms: Sequence[BomRecord]) -> None:
	for bom in boms:
		bom.is_active = True


def _get_same_project_layouts(layout: ReleaseLayoutDocument) -> list[object]:
	project = getattr(layout, "project", None)
	if not project:
		return [layout]

	# Lightweight rows are enough here: release_layout only uses this list to
	# decide whether the revision path applies, and the released layout itself
	# must be the in-memory document, never a re-fetched copy. Full get_doc
	# fetches would be wasted reads on the release hot path.
	layout_rows = frappe.get_all(
		"Sheet Cutting Layout",
		filters={"project": project},
		fields=["name"],
	)
	layout_name = getattr(layout, "name", None)
	layouts: list[object] = [row for row in layout_rows if row["name"] != layout_name]
	layouts.append(layout)
	return layouts


def _get_finished_part_boms(layout: ReleaseLayoutDocument) -> list[BomRecord]:
	finished_part_items = [
		row.finished_part_item for row in _parent_finished_part_rows(layout) if row.finished_part_item
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
	for bom in boms:
		if getattr(bom, "_persisted_with_frappe", False):
			continue
		bom_doc = bom if hasattr(bom, "save") else frappe.get_doc("BOM", bom.name)
		_set_frappe_field_if_supported(bom_doc, "is_active", 1 if bom.is_active else 0)
		mark_bom_app_controlled(bom_doc)
		bom_doc.save(ignore_permissions=True)


def _save_layout_records(layouts: Sequence[object]) -> None:
	for layout in layouts:
		if _is_submitted_document(layout):
			_save_submitted_layout_record(layout)
		elif hasattr(layout, "save"):
			layout.save(ignore_permissions=True)


def _save_submitted_layout_record(layout: object) -> None:
	save = getattr(layout, "save", None)
	if callable(save):
		flags = getattr(layout, "flags", None)
		previous_value = getattr(flags, "ignore_validate_update_after_submit", None)
		had_previous_value = hasattr(flags, "ignore_validate_update_after_submit")
		if flags is not None:
			flags.ignore_validate_update_after_submit = True
		try:
			save(ignore_permissions=True)
		finally:
			if flags is not None:
				if had_previous_value:
					flags.ignore_validate_update_after_submit = previous_value
				else:
					delattr(flags, "ignore_validate_update_after_submit")
		return

	db_set = getattr(layout, "db_set", None)
	if not callable(db_set):
		return

	state_values = _supported_field_values(
		layout,
		{
			"status": getattr(layout, "status", None),
			"is_active": getattr(layout, "is_active", None),
			"generated_bom": getattr(layout, "generated_bom", None),
		},
	)
	if state_values:
		db_set(state_values, update_modified=True, notify=False)


def _is_submitted_document(doc: object) -> bool:
	docstatus = getattr(doc, "docstatus", None)
	if docstatus == 1:
		return True
	is_submitted = getattr(docstatus, "is_submitted", None)
	return bool(callable(is_submitted) and is_submitted())


def _is_cancelled_document(doc: object) -> bool:
	docstatus = getattr(doc, "docstatus", None)
	if docstatus == 2:
		return True
	is_cancelled = getattr(docstatus, "is_cancelled", None)
	return bool(callable(is_cancelled) and is_cancelled())


def _company_for_layout(layout: object | None) -> str:
	if layout is not None:
		company = getattr(layout, "company", None)
		if company:
			return company

	import erpnext

	company = erpnext.get_default_company()
	if company:
		return company

	frappe.throw(_("Company is required to create generated BOMs"))
	raise RuntimeError("Company is required to create generated BOMs")


def _field_is_supported(doc: object, fieldname: str) -> bool:
	meta = getattr(doc, "meta", None)
	if meta is not None and hasattr(meta, "has_field"):
		return bool(meta.has_field(fieldname))
	return hasattr(doc, fieldname)


def _set_frappe_field_if_supported(doc: object, fieldname: str, value: object) -> None:
	if _field_is_supported(doc, fieldname):
		setattr(doc, fieldname, value)


def _supported_field_values(doc: object, values: dict[str, object]) -> dict[str, object]:
	return {field: value for field, value in values.items() if _field_is_supported(doc, field)}


def _sum_bom_qty(rows: Sequence[object]) -> float:
	return sum(float(getattr(row, "qty", 0) or 0) for row in rows)
