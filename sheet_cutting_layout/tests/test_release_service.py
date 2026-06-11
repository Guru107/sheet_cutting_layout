import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import sheet_cutting_layout.hooks as hooks
from sheet_cutting_layout.services.release_service import LayoutReleaseStatus
from sheet_cutting_layout.services.versioning import LayoutVersionStatus
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase
from sheet_cutting_layout.tests.unittest_adapter import MonkeyPatch, add_pytest_style_tests, fixture, raises


@dataclass
class Layout:
	name: str = "SCL-NEW"
	project: str = "PROJECT-001"
	status: LayoutReleaseStatus = "Approved by Purchase"
	raw_material_item: str = "RMSHEET001"
	process_scrap_item: str = "PROCESSSCRAP001"
	no_of_strips: int = 11
	finished_part_code: str = "PART001SHR"
	net_weight_per_part_kg: float = 1.0
	gross_weight_per_part_kg: float = 1.0
	scrap_weight_per_part_kg: float = 0.0
	generated_bom: str | None = None
	weight_per_sheet_kg: float | None = None
	consumed_weight_kg: float | None = None
	leftover_weight_kg: float | None = None
	consumption_status: str | None = None
	parts_per_sheet: int = 1
	finished_parts: list["FinishedPart"] = field(default_factory=lambda: [FinishedPart("PART001SHR")])
	end_pieces: list["EndPiece"] = field(default_factory=list)

	def __post_init__(self) -> None:
		if self.finished_parts:
			self.finished_part_code = self.finished_parts[0].finished_part_item
			self.parts_per_sheet = self.finished_parts[0].parts_per_sheet
			self.gross_weight_per_part_kg = self.finished_parts[0].gross_weight_per_part_kg
			self.scrap_weight_per_part_kg = self.finished_parts[0].scrap_weight_per_part_kg
		self.net_weight_per_part_kg = self.gross_weight_per_part_kg - self.scrap_weight_per_part_kg


@dataclass
class FinishedPart:
	finished_part_item: str
	parts_per_sheet: int = 1
	gross_weight_per_part_kg: float = 1.0
	scrap_weight_per_part_kg: float = 0.0
	generated_bom: str | None = None
	bom_quantity: float | None = None
	scrap_weight_kg: float | None = None
	raw_material_weight_kg: float | None = None


@dataclass
class EndPiece:
	weight_kg: float
	qty_per_sheet: float = 1
	disposition: str = "Reuse"
	scrap_item: str | None = None
	end_piece_item_code: str | None = None
	used_for_finished_part: str | None = "FG002SHR"
	width_mm: float | None = 1250
	length_mm: float | None = 179
	idx: int = 1
	bom_quantity: float | None = 1
	net_weight_per_part_kg: float | None = 0
	gross_weight_per_part_kg: float | None = 0
	scrap_weight_per_part_kg: float | None = 0
	bom_scrap_quantity_kg: float | None = 0


@dataclass
class RevisionLayout:
	name: str
	project: str
	revision_no: int
	status: LayoutVersionStatus
	is_active: bool
	layout_code: str = ""
	raw_material_item: str = "RM-SHEET-001"
	process_scrap_item: str = "PROCESS-SCRAP-001"
	weight_per_sheet_kg: float = 2.5
	based_on_layout: str | None = None
	approval_snapshot: list[str] = field(default_factory=list)
	finished_parts: list[FinishedPart] = field(default_factory=list)
	end_pieces: list[EndPiece] = field(default_factory=list)
	finished_part_code: str = ""
	net_weight_per_part_kg: float = 1.0
	gross_weight_per_part_kg: float = 1.0
	scrap_weight_per_part_kg: float = 0.0
	generated_bom: str | None = None
	parts_per_sheet: int = 1
	end_piece_bom_status: str = ""

	def __post_init__(self) -> None:
		if self.finished_parts:
			self.finished_part_code = self.finished_parts[0].finished_part_item
			self.parts_per_sheet = self.finished_parts[0].parts_per_sheet
			self.gross_weight_per_part_kg = self.finished_parts[0].gross_weight_per_part_kg
			self.scrap_weight_per_part_kg = self.finished_parts[0].scrap_weight_per_part_kg
		self.net_weight_per_part_kg = self.gross_weight_per_part_kg - self.scrap_weight_per_part_kg


@dataclass
class Bom:
	name: str
	item: str
	custom_operation: str | None = "Shearing"
	sheet_cutting_layout: str | None = None
	is_active: bool = True
	disabled: bool = False
	status: str = "Active"


class SavableRevisionLayout(RevisionLayout):
	def __init__(self, **kwargs: object) -> None:
		super().__init__(**kwargs)
		self.save_calls = 0

	def save(self, **kwargs: object) -> None:
		assert kwargs == {"ignore_permissions": True}
		self.save_calls += 1


class SubmittedRevisionLayout(RevisionLayout):
	docstatus: int = 1

	def __init__(self, **kwargs: object) -> None:
		super().__init__(**kwargs)
		self.db_set_calls: list[tuple[dict[str, object], bool, bool]] = []
		self.save_calls = 0

	def db_set(
		self,
		values: dict[str, object],
		update_modified: bool = True,
		notify: bool = False,
	) -> None:
		self.db_set_calls.append((values, update_modified, notify))

	def save(self, **kwargs: object) -> None:
		self.save_calls += 1
		raise AssertionError("submitted layout state changes must use db_set")


@fixture(autouse=True)
def isolate_release_runtime_from_live_frappe(monkeypatch: MonkeyPatch) -> None:
	"""Keep unit-style tests deterministic under bench by disabling live persistence paths."""
	from sheet_cutting_layout.services import release_service

	try:
		import frappe as frappe_module
	except ImportError:
		frappe_module = None

	monkeypatch.setattr(release_service, "frappe", None)
	if frappe_module is not None:
		monkeypatch.setattr(frappe_module, "copy_doc", None, raising=False)


def _new_sheet_cutting_layout_doc(sheet_cutting_layout_module: object):
	doc = object.__new__(sheet_cutting_layout_module.SheetCuttingLayout)
	doc.doctype = "Sheet Cutting Layout"
	doc.approval_snapshot = []

	def append(fieldname: str, row: object) -> None:
		table = getattr(doc, fieldname, None)
		if table is None:
			setattr(doc, fieldname, [])
			table = getattr(doc, fieldname)
		table.append(row)

	doc.append = append
	return doc


def _in_memory_bom_factory(layout: Layout | RevisionLayout, row: FinishedPart, index: int):
	from sheet_cutting_layout.services.bom_service import build_bom_from_layout_row

	bom = build_bom_from_layout_row(layout, row)
	bom.name = f"BOM-{layout.name}-{index:03d}"
	bom.sheet_cutting_layout = layout.name
	return bom


def test_hooks_exposes_required_fixtures() -> None:
	expected_fixtures = [
		{
			"dt": "Workflow State",
			"filters": [
				[
					"name",
					"in",
					[
						"Draft",
						"Submitted for Check",
						"PM Approved",
						"Approved by Purchase",
						"Released",
						"Rejected",
						"Superseded",
						"Cancel",
					],
				]
			],
		},
		{
			"dt": "Workflow",
			"filters": [["name", "=", "Sheet Cutting Layout Approval Workflow"]],
		},
		{
			"dt": "Role",
			"filters": [["name", "in", ["Project Manager", "MR Coordinator"]]],
		},
		{
			"dt": "Custom Field",
			"filters": [["dt", "in", ["BOM", "Work Order", "Production Plan"]]],
		},
	]

	assert hooks.fixtures == expected_fixtures
	assert hooks.override_whitelisted_methods == {
		"frappe.model.workflow.apply_workflow": (
			"sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout."
			"sheet_cutting_layout.apply_sheet_cutting_layout_workflow"
		)
	}
	assert hooks.doc_events == {
		"BOM": {
			"before_insert": "sheet_cutting_layout.overrides.bom.validate_shearing_bom_source",
			"before_cancel": "sheet_cutting_layout.overrides.bom.validate_shearing_bom_source",
		}
	}
	assert hooks.before_tests == "sheet_cutting_layout.tests.test_setup.before_tests"

	fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures"
	for fixture_file_name in ("workflow_state.json", "workflow.json", "role.json", "custom_field.json"):
		fixture_path = fixtures_dir / fixture_file_name

		assert fixture_path.exists()
		assert isinstance(json.loads(fixture_path.read_text()), list)


def test_bom_custom_fields_are_fixture_owned() -> None:
	fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "custom_field.json"
	fields = {
		row["fieldname"]: row
		for row in json.loads(fixture_path.read_text(encoding="utf-8"))
		if row.get("dt") == "BOM"
	}

	assert fields["custom_operation"]["fieldtype"] in {"Data", "Select"}
	assert fields["sheet_cutting_layout"]["fieldtype"] == "Link"
	assert fields["sheet_cutting_layout"]["options"] == "Sheet Cutting Layout"
	assert fields["sheet_cutting_layout"]["read_only"] == 1
	assert fields["sheet_cutting_layout"]["hidden"] == 1
	assert fields["sheet_cutting_layout"]["no_copy"] == 1


def test_parent_finished_part_code_is_item_link() -> None:
	doctype_path = (
		Path(__file__).resolve().parents[1]
		/ "sheet_cutting_layout"
		/ "doctype"
		/ "sheet_cutting_layout"
		/ "sheet_cutting_layout.json"
	)
	fields = {
		row["fieldname"]: row
		for row in json.loads(doctype_path.read_text(encoding="utf-8"))["fields"]
		if "fieldname" in row
	}

	assert fields["finished_part_code"]["fieldtype"] == "Link"
	assert fields["finished_part_code"]["options"] == "Item"


def test_status_options_include_cancel_state() -> None:
	doctype_path = (
		Path(__file__).resolve().parents[1]
		/ "sheet_cutting_layout"
		/ "doctype"
		/ "sheet_cutting_layout"
		/ "sheet_cutting_layout.json"
	)
	fields = {
		row["fieldname"]: row
		for row in json.loads(doctype_path.read_text(encoding="utf-8"))["fields"]
		if "fieldname" in row
	}
	workflow_states = {
		row["state"]: row
		for row in json.loads(
			(Path(__file__).resolve().parents[1] / "fixtures" / "workflow.json").read_text(encoding="utf-8")
		)[0]["states"]
	}

	assert "Cancel" in fields["status"]["options"].splitlines()
	assert workflow_states["Cancel"]["doc_status"] == "2"


def test_generated_release_artifact_fields_are_not_copied() -> None:
	doctype_path = (
		Path(__file__).resolve().parents[1]
		/ "sheet_cutting_layout"
		/ "doctype"
		/ "sheet_cutting_layout"
		/ "sheet_cutting_layout.json"
	)
	fields = {
		row["fieldname"]: row
		for row in json.loads(doctype_path.read_text(encoding="utf-8"))["fields"]
		if "fieldname" in row
	}
	end_piece_path = (
		Path(__file__).resolve().parents[1]
		/ "sheet_cutting_layout"
		/ "doctype"
		/ "layout_end_piece"
		/ "layout_end_piece.json"
	)
	end_piece_fields = {
		row["fieldname"]: row
		for row in json.loads(end_piece_path.read_text(encoding="utf-8"))["fields"]
		if "fieldname" in row
	}

	for fieldname in (
		"generated_bom",
		"finished_parts",
		"approval_snapshot",
		"is_active",
		"end_piece_bom_status",
		"status",
	):
		assert fields[fieldname]["no_copy"] == 1
	assert end_piece_fields["end_piece_item_code"]["no_copy"] == 1


def test_controller_before_insert_clears_copied_release_artifacts() -> None:
	from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import sheet_cutting_layout

	doc = object.__new__(sheet_cutting_layout.SheetCuttingLayout)
	doc.generated_bom = "BOM-OLD"
	doc.finished_parts = [SimpleNamespace(generated_bom="BOM-OLD")]
	doc.approval_snapshot = [SimpleNamespace(step_name="MR Approval")]
	doc.status = "Released"
	doc.is_active = True
	doc.end_piece_bom_status = "Generated"
	doc.end_pieces = [EndPiece(weight_kg=2.5, end_piece_item_code="FG01SHR-EP-1x1250x260")]

	doc.before_insert()

	assert doc.generated_bom is None
	assert doc.finished_parts == []
	assert doc.approval_snapshot == []
	assert doc.status == "Draft"
	assert doc.is_active is False
	assert doc.end_piece_bom_status == "Pending"
	assert doc.end_pieces[0].end_piece_item_code is None


def test_release_reaches_released() -> None:
	from sheet_cutting_layout.services.release_service import release_layout

	layout = Layout()
	result = release_layout(
		layout,
		layouts=[],
		boms=[],
		bom_document_factory=_in_memory_bom_factory,
	)

	assert result.status == "Released"
	assert layout.status == "Released"


def test_release_runs_default_layout_validation() -> None:
	from sheet_cutting_layout.services.release_service import ReleaseContext, release_layout
	from sheet_cutting_layout.services.validators import frappe

	layout = Layout(finished_parts=[FinishedPart("PART-001SHR")])

	try:
		validation_error = frappe.ValidationError
	except AttributeError:
		validation_error = Exception

	with raises(validation_error, match="alphanumeric"):
		release_layout(layout, release_context=ReleaseContext(layouts=(), boms=[]))

	assert layout.status == "Approved by Purchase"


def test_release_allows_injected_validators_for_testability() -> None:
	from sheet_cutting_layout.services.release_service import release_layout

	calls: list[str] = []
	layout = Layout(finished_parts=[FinishedPart("PART-001SHR")])

	release_layout(
		layout,
		validators=[lambda received: calls.append(received.status)],
		layouts=[],
		boms=[],
		bom_document_factory=_in_memory_bom_factory,
	)

	assert calls == ["Approved by Purchase"]
	assert layout.status == "Released"


def test_release_requires_process_scrap_item_when_process_scrap_is_positive() -> None:
	from sheet_cutting_layout.services.release_service import ReleaseContext, release_layout
	from sheet_cutting_layout.services.validators import frappe

	layout = Layout(
		process_scrap_item="",
		finished_parts=[FinishedPart("PART001SHR", scrap_weight_per_part_kg=0.25)],
	)

	with raises(frappe.ValidationError, match="Process scrap item"):
		release_layout(layout, release_context=ReleaseContext(layouts=(), boms=[]))


def test_release_stops_when_injected_validator_fails() -> None:
	from sheet_cutting_layout.services.release_service import release_layout

	def fail_validator(_layout: Layout) -> None:
		raise ValueError("not ready")

	layout = Layout()

	with raises(ValueError, match="not ready"):
		release_layout(layout, validators=[fail_validator], layouts=[], boms=[])

	assert layout.status == "Approved by Purchase"
	assert layout.finished_parts[0].generated_bom is None


def test_release_uses_injected_context_provider() -> None:
	from sheet_cutting_layout.services.release_service import ReleaseContext, release_layout

	layout = Layout()
	context = ReleaseContext(layouts=[], boms=[])
	calls: list[Layout] = []

	result = release_layout(
		layout,
		release_context_provider=lambda received: calls.append(received) or context,
		bom_document_factory=_in_memory_bom_factory,
	)

	assert calls == [layout]
	assert result.status == "Released"


def test_release_uses_injected_bom_document_factory_for_persisted_boms() -> None:
	from sheet_cutting_layout.services.bom_service import BomDocument
	from sheet_cutting_layout.services.release_service import release_layout

	layout = Layout(no_of_strips=11, parts_per_sheet=77, finished_parts=[])
	created: list[tuple[Layout, object, int]] = []

	def fake_factory(received_layout: Layout, row: object, index: int) -> BomDocument:
		created.append((received_layout, row, index))
		return BomDocument(item=row.finished_part_item, name=f"PERSISTED-BOM-{index}", quantity=11)

	result = release_layout(
		layout,
		bom_document_factory=fake_factory,
		layouts=[],
		boms=[],
	)

	assert created[0][0] is layout
	assert created[0][1].finished_part_item == "PART001SHR"
	assert created[0][2] == 1
	assert result.generated_boms[0].name == "PERSISTED-BOM-1"
	assert layout.generated_bom == "PERSISTED-BOM-1"
	assert [row.finished_part_item for row in layout.finished_parts] == ["PART001SHR"]
	assert [row.bom_quantity for row in layout.finished_parts] == [77]


def test_release_uses_parent_finished_part_contract_without_child_inputs() -> None:
	from sheet_cutting_layout.services.release_service import release_layout

	layout = Layout(
		weight_per_sheet_kg=100.0,
		parts_per_sheet=80,
		finished_part_code="PART001SHR",
		net_weight_per_part_kg=0.75,
		gross_weight_per_part_kg=1.0,
		scrap_weight_per_part_kg=0.25,
		finished_parts=[],
	)

	result = release_layout(
		layout,
		validators=[lambda _layout: None],
		layouts=[],
		boms=[],
		bom_document_factory=_in_memory_bom_factory,
	)

	assert result.generated_boms[0].item == "PART001SHR"
	assert result.generated_boms[0].quantity == 80
	assert layout.generated_bom == result.generated_boms[0].name
	assert [row.finished_part_item for row in layout.finished_parts] == ["PART001SHR"]
	assert [row.bom_quantity for row in layout.finished_parts] == [80]
	assert [row.scrap_weight_kg for row in layout.finished_parts] == [20.0]
	assert [row.raw_material_weight_kg for row in layout.finished_parts] == [100.0]


def test_release_syncs_finished_part_reference_rows_from_saved_bom() -> None:
	from sheet_cutting_layout.services.bom_service import BomDocument, BomItemRow
	from sheet_cutting_layout.services.release_service import release_layout

	layout = Layout(
		weight_per_sheet_kg=39.3,
		parts_per_sheet=77,
		finished_part_code="FG01SHR",
		net_weight_per_part_kg=0.289,
		gross_weight_per_part_kg=0.473846,
		scrap_weight_per_part_kg=0.184846,
		finished_parts=[],
	)

	def persisted_bom_factory(_layout: Layout, _row: object, _index: int) -> BomDocument:
		bom = BomDocument(item="FG01SHR", name="BOM-FG01SHR-SAVED", quantity=11)
		bom.items.append(BomItemRow(item_code="RMSHEET001", qty=39.3, row_type="raw_material"))
		bom.scrap_items.append(
			BomItemRow(item_code="PROCESSSCRAP001", qty=14.233142, row_type="process_scrap")
		)
		return bom

	release_layout(
		layout,
		validators=[lambda _layout: None],
		layouts=[],
		boms=[],
		bom_document_factory=persisted_bom_factory,
	)

	self_reference = layout.finished_parts[0]
	assert self_reference.finished_part_item == "FG01SHR"
	assert self_reference.bom_quantity == 77
	assert self_reference.raw_material_weight_kg == 39.3
	assert self_reference.scrap_weight_kg == 14.233142


def test_save_time_audit_rejects_generated_bom_quantity_drift(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import validators

	class FrappeStub:
		ValidationError = ValueError

		@staticmethod
		def get_system_settings(_fieldname: str) -> None:
			return None

		@staticmethod
		def get_doc(doctype: str, name: str) -> object:
			assert (doctype, name) == ("BOM", "BOM-FG01SHR")
			return type(
				"Bom",
				(),
				{
					"item": "FG01SHR",
					"quantity": 99,
					"items": [type("BomItem", (), {"item_code": "RMSHEET001", "qty": 39.3})()],
					"scrap_items": [
						type(
							"ScrapItem",
							(),
							{"item_code": "PROCESSSCRAP001", "stock_qty": 14.233142, "qty": 14.233142},
						)(),
						type(
							"ScrapItem",
							(),
							{"item_code": "ENDSCRAP001", "stock_qty": 2.81388, "qty": 2.81388},
						)(),
					],
				},
			)()

		@staticmethod
		def throw(message: str) -> None:
			raise ValueError(message)

	layout = type(
		"AuditLayout",
		(),
		{
			"finished_part_code": "FG01SHR",
			"net_weight_per_part_kg": 0.289,
			"generated_bom": "BOM-FG01SHR",
			"end_pieces": [
				type(
					"EndPieceRow",
					(),
					{
						"weight_kg": 2.81388,
						"qty_per_sheet": 1,
						"width_mm": 1250,
						"length_mm": 179,
						"disposition": "Scrap",
						"scrap_item": "ENDSCRAP001",
					},
				)()
			],
			"raw_material_item": "RMSHEET001",
			"process_scrap_item": "PROCESSSCRAP001",
			"end_piece_bom_status": "",
			"sheet_thickness_mm": None,
			"sheet_width_mm": None,
			"sheet_length_mm": None,
			"weight_per_sheet_kg": 39.3,
			"strip_thickness_mm": None,
			"strip_width_mm": None,
			"strip_length_mm": None,
			"weight_of_strip_kg": None,
			"gross_weight_per_part_kg": 0.473846,
			"scrap_weight_per_part_kg": 0.184846,
			"parts_per_strip": 7,
			"no_of_strips": 11,
			"parts_per_sheet": 77,
			"consumed_weight_kg": None,
			"leftover_weight_kg": None,
			"consumption_status": None,
		},
	)()
	monkeypatch.setattr(validators, "frappe", FrappeStub)
	monkeypatch.setattr(validators, "_", lambda message: message)

	with raises(ValueError, match="BOM quantity mismatch"):
		validators.validate_sheet_cutting_layout(layout)


def test_save_time_audit_rejects_missing_reuse_end_piece_byproduct_row(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import validators

	class FrappeStub:
		ValidationError = ValueError

		@staticmethod
		def get_system_settings(_fieldname: str) -> None:
			return None

		@staticmethod
		def get_doc(doctype: str, name: str) -> object:
			assert (doctype, name) == ("BOM", "BOM-FG01SHR")
			return type(
				"Bom",
				(),
				{
					"item": "FG01SHR",
					"quantity": 77,
					"items": [type("BomItem", (), {"item_code": "RMSHEET001", "qty": 39.3})()],
					"scrap_items": [
						type(
							"ScrapItem",
							(),
							{"item_code": "PROCESSSCRAP001", "stock_qty": 14.233142, "qty": 14.233142},
						)(),
					],
				},
			)()

		@staticmethod
		def throw(message: str) -> None:
			raise ValueError(message)

	layout = type(
		"AuditLayout",
		(),
		{
			"finished_part_code": "FG01SHR",
			"net_weight_per_part_kg": 0.289,
			"generated_bom": "BOM-FG01SHR",
			"end_pieces": [
				type(
					"EndPieceRow",
					(),
					{
						"idx": 1,
						"end_piece_item_code": None,
						"weight_kg": 2.81388,
						"qty_per_sheet": 1,
						"width_mm": 1250,
						"length_mm": 179,
						"disposition": "Reuse",
						"scrap_item": None,
						"used_for_finished_part": "FG002SHR",
						"bom_quantity": 1,
						"net_weight_per_part_kg": 2.81388,
						"gross_weight_per_part_kg": 2.81388,
						"scrap_weight_per_part_kg": 0,
						"bom_scrap_quantity_kg": 0,
					},
				)()
			],
			"raw_material_item": "RMSHEET001",
			"process_scrap_item": "PROCESSSCRAP001",
			"end_piece_bom_status": "",
			"sheet_thickness_mm": 1.6,
			"sheet_width_mm": None,
			"sheet_length_mm": None,
			"weight_per_sheet_kg": 39.3,
			"strip_thickness_mm": None,
			"strip_width_mm": None,
			"strip_length_mm": None,
			"weight_of_strip_kg": None,
			"gross_weight_per_part_kg": 0.473846,
			"scrap_weight_per_part_kg": 0.184846,
			"parts_per_strip": 7,
			"no_of_strips": 11,
			"parts_per_sheet": 77,
			"consumed_weight_kg": None,
			"leftover_weight_kg": None,
			"consumption_status": None,
		},
	)()
	monkeypatch.setattr(validators, "frappe", FrappeStub)
	monkeypatch.setattr(validators, "_", lambda message: message)

	with raises(ValueError, match="BOM scrap item mismatch"):
		validators.validate_sheet_cutting_layout(layout)


def test_save_time_audit_rejects_fractional_generated_bom_quantity(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import validators

	class FrappeStub:
		ValidationError = ValueError

		@staticmethod
		def get_system_settings(_fieldname: str) -> None:
			return None

		@staticmethod
		def get_doc(doctype: str, name: str) -> object:
			assert (doctype, name) == ("BOM", "BOM-FG01SHR")
			return type(
				"Bom",
				(),
				{
					"item": "FG01SHR",
					"quantity": 11.5,
					"items": [type("BomItem", (), {"item_code": "RMSHEET001", "qty": 39.3})()],
					"scrap_items": [
						type(
							"ScrapItem",
							(),
							{"item_code": "PROCESSSCRAP001", "stock_qty": 14.233142, "qty": 14.233142},
						)(),
						type(
							"ScrapItem",
							(),
							{"item_code": "ENDSCRAP001", "stock_qty": 2.81388, "qty": 2.81388},
						)(),
					],
				},
			)()

		@staticmethod
		def throw(message: str) -> None:
			raise ValueError(message)

	layout = type(
		"AuditLayout",
		(),
		{
			"finished_part_code": "FG01SHR",
			"net_weight_per_part_kg": 0.289,
			"generated_bom": "BOM-FG01SHR",
			"end_pieces": [
				type(
					"EndPieceRow",
					(),
					{
						"weight_kg": 2.81388,
						"qty_per_sheet": 1,
						"width_mm": 1250,
						"length_mm": 179,
						"disposition": "Scrap",
						"scrap_item": "ENDSCRAP001",
					},
				)()
			],
			"raw_material_item": "RMSHEET001",
			"process_scrap_item": "PROCESSSCRAP001",
			"end_piece_bom_status": "",
			"sheet_thickness_mm": None,
			"sheet_width_mm": None,
			"sheet_length_mm": None,
			"weight_per_sheet_kg": 39.3,
			"strip_thickness_mm": None,
			"strip_width_mm": None,
			"strip_length_mm": None,
			"weight_of_strip_kg": None,
			"gross_weight_per_part_kg": 0.473846,
			"scrap_weight_per_part_kg": 0.184846,
			"parts_per_strip": 7,
			"no_of_strips": 11,
			"parts_per_sheet": 77,
			"consumed_weight_kg": None,
			"leftover_weight_kg": None,
			"consumption_status": None,
		},
	)()
	monkeypatch.setattr(validators, "frappe", FrappeStub)
	monkeypatch.setattr(validators, "_", lambda message: message)

	with raises(ValueError, match="BOM quantity mismatch"):
		validators.validate_sheet_cutting_layout(layout)


def test_release_generates_bom_for_one_sheet_in_kg_with_scrap_outputs() -> None:
	from sheet_cutting_layout.services.release_service import release_layout

	layout = Layout(
		weight_per_sheet_kg=100.0,
		finished_parts=[
			FinishedPart(
				"PART001SHR",
				parts_per_sheet=80,
				gross_weight_per_part_kg=1.0,
				scrap_weight_per_part_kg=0.25,
			)
		],
		end_pieces=[
			EndPiece(
				weight_kg=10.0,
				qty_per_sheet=2,
				disposition="Scrap",
				scrap_item="ENDSCRAP001",
			)
		],
	)

	result = release_layout(
		layout,
		validators=[lambda _layout: None],
		layouts=[],
		boms=[],
		bom_document_factory=_in_memory_bom_factory,
	)

	bom = result.generated_boms[0]
	assert bom.item == "PART001SHR"
	assert bom.quantity == 80
	assert [(row.item_code, row.qty, row.row_type) for row in bom.items] == [
		("RMSHEET001", 100.0, "raw_material")
	]
	assert [(row.item_code, row.qty, row.row_type) for row in bom.scrap_items] == [
		("PROCESSSCRAP001", 20.0, "process_scrap"),
		("ENDSCRAP001", 10.0, "end_piece_scrap"),
	]


def test_generated_boms_are_activated_on_release() -> None:
	from sheet_cutting_layout.services.release_service import release_layout

	old_layout = RevisionLayout(
		name="SCL-001",
		project="FAM-001",
		revision_no=1,
		status="Released",
		is_active=True,
		finished_parts=[FinishedPart("PART001LHSHR", generated_bom="BOM-PART001LHSHR-OLD")],
	)
	new_layout = RevisionLayout(
		name="SCL-002",
		project="FAM-001",
		revision_no=2,
		status="Approved by Purchase",
		is_active=False,
		finished_parts=[FinishedPart("PART001LHSHR", gross_weight_per_part_kg=2.5)],
	)
	old_bom = Bom("BOM-PART001LHSHR-OLD", item="PART001LHSHR")
	boms = [old_bom]

	result = release_layout(
		new_layout,
		layouts=[old_layout, new_layout],
		boms=boms,
		bom_document_factory=_in_memory_bom_factory,
	)
	new_bom = result.generated_boms[0]

	assert result.status == "Released"
	assert new_bom.is_active is True
	assert new_bom.disabled is False
	assert new_bom.status == "Active"


def test_release_persists_only_new_revision_layout_when_frappe_is_available(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import release_service
	from sheet_cutting_layout.services.bom_service import BomDocument
	from sheet_cutting_layout.services.release_service import release_layout

	old_layout = SavableRevisionLayout(
		name="SCL-001",
		project="FAM-001",
		revision_no=1,
		status="Released",
		is_active=True,
		finished_parts=[FinishedPart("PART001LHSHR", generated_bom="BOM-PART001LHSHR-OLD")],
	)
	new_layout = SavableRevisionLayout(
		name="SCL-002",
		project="FAM-001",
		revision_no=2,
		status="Approved by Purchase",
		is_active=False,
		finished_parts=[FinishedPart("PART001LHSHR", gross_weight_per_part_kg=2.5)],
	)

	class FrappeStub:
		@staticmethod
		def get_doc(_doctype: str, name: str) -> object:
			return type("SavableBom", (), {"name": name, "save": lambda self, **kwargs: None})()

	monkeypatch.setattr(release_service, "frappe", FrappeStub)

	release_layout(
		new_layout,
		layouts=[old_layout, new_layout],
		boms=[],
		bom_document_factory=lambda _layout, row, _index: BomDocument(
			item=row.finished_part_item,
			name="BOM-PART001LHSHR-NEW",
		),
	)

	assert old_layout.status == "Released"
	assert old_layout.save_calls == 0
	assert new_layout.status == "Released"
	assert new_layout.save_calls == 1


def test_release_does_not_db_set_unchanged_submitted_layouts(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import release_service
	from sheet_cutting_layout.services.bom_service import BomDocument
	from sheet_cutting_layout.services.release_service import release_layout

	old_layout = SubmittedRevisionLayout(
		name="SCL-001",
		project="FAM-001",
		revision_no=1,
		status="Released",
		is_active=True,
		finished_parts=[FinishedPart("PART001LHSHR", generated_bom="BOM-PART001LHSHR-OLD")],
	)
	new_layout = SavableRevisionLayout(
		name="SCL-002",
		project="FAM-001",
		revision_no=2,
		status="Approved by Purchase",
		is_active=False,
		finished_parts=[FinishedPart("PART001LHSHR", gross_weight_per_part_kg=2.5)],
	)

	class FrappeStub:
		@staticmethod
		def get_doc(_doctype: str, name: str) -> object:
			return type("SavableBom", (), {"name": name, "save": lambda self, **kwargs: None})()

	monkeypatch.setattr(release_service, "frappe", FrappeStub)

	release_layout(
		new_layout,
		layouts=[old_layout, new_layout],
		boms=[],
		bom_document_factory=lambda _layout, row, _index: BomDocument(
			item=row.finished_part_item,
			name="BOM-PART001LHSHR-NEW",
		),
	)

	assert old_layout.status == "Released"
	assert old_layout.is_active is True
	assert old_layout.save_calls == 0
	assert old_layout.db_set_calls == []


def test_controller_mr_release_action_calls_release_service_with_release_context(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import sheet_cutting_layout

	calls: list[object] = []
	context = object()

	def fake_release_layout(layout: object, **kwargs: object) -> None:
		calls.append((layout, kwargs))
		return type("ReleaseResult", (), {"status": "Released"})()

	monkeypatch.setattr(sheet_cutting_layout, "_get_selected_workflow_action", lambda: "MR Release")
	monkeypatch.setattr(sheet_cutting_layout, "get_release_context", lambda layout: context)
	monkeypatch.setattr(sheet_cutting_layout, "release_layout", fake_release_layout)

	doc = _new_sheet_cutting_layout_doc(sheet_cutting_layout)
	doc.before_workflow_action()

	assert calls == [(doc, {"release_context": context})]


def test_mr_release_records_mr_approval_snapshot() -> None:
	from sheet_cutting_layout.services.workflow import record_approval_snapshot

	doc = type("Doc", (), {"approval_snapshot": []})()
	decision_time = datetime(2026, 5, 18, 12, 30, 0)

	recorded = record_approval_snapshot(
		doc,
		action="MR Release",
		approver="mr@example.com",
		decision_time=decision_time,
	)

	assert recorded is True
	assert doc.approval_snapshot == [
		{
			"step_name": "MR Approval",
			"approver": "mr@example.com",
			"decision": "Approved",
			"decision_time": decision_time,
		}
	]


def test_controller_mr_release_suppresses_side_effects_during_internal_layout_saves(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import sheet_cutting_layout

	class Flags:
		selected_workflow_action = "MR Release"

	class FrappeStub:
		flags = Flags()

		class _Session:
			user = "mr@example.com"

		session = _Session()

		@staticmethod
		def now_datetime() -> datetime:
			return datetime(2026, 5, 15, 12, 30, 0)

	calls: list[object] = []
	context = object()

	def fake_release_layout(layout: object, **kwargs: object) -> object:
		calls.append((layout, kwargs))
		if len(calls) == 1:
			related_layout = _new_sheet_cutting_layout_doc(sheet_cutting_layout)
			related_layout.approval_snapshot = []
			related_layout.validate()
		return type("ReleaseResult", (), {"status": "Released"})()

	monkeypatch.setattr(sheet_cutting_layout, "frappe", FrappeStub)
	monkeypatch.setattr(sheet_cutting_layout, "get_release_context", lambda layout: context)
	monkeypatch.setattr(sheet_cutting_layout, "release_layout", fake_release_layout)
	monkeypatch.setattr(sheet_cutting_layout, "validate_sheet_cutting_layout", lambda _doc: None)

	doc = _new_sheet_cutting_layout_doc(sheet_cutting_layout)
	doc.approval_snapshot = []

	doc.before_workflow_action()

	assert calls == [(doc, {"release_context": context})]


def test_controller_validate_applies_workflow_side_effects_and_records_snapshot(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import sheet_cutting_layout

	class FrappeStub:
		class _Session:
			user = "projects@example.com"

		session = _Session()

		@staticmethod
		def now_datetime() -> datetime:
			return datetime(2026, 5, 15, 9, 30, 0)

	monkeypatch.setattr(
		sheet_cutting_layout,
		"_get_selected_workflow_action",
		lambda: "Project Manager Approves",
	)
	monkeypatch.setattr(sheet_cutting_layout, "frappe", FrappeStub)
	monkeypatch.setattr(sheet_cutting_layout, "validate_sheet_cutting_layout", lambda _doc: None)

	doc = _new_sheet_cutting_layout_doc(sheet_cutting_layout)
	doc.approval_snapshot = []

	doc.validate()

	assert len(doc.approval_snapshot) == 1
	assert doc.approval_snapshot[0]["step_name"] == "Project Manager Approval"
	assert doc.approval_snapshot[0]["approver"] == "projects@example.com"
	assert doc.approval_snapshot[0]["decision"] == "Approved"
	assert doc.approval_snapshot[0]["decision_time"] == datetime(2026, 5, 15, 9, 30, 0)


def test_controller_validate_records_submit_for_check_snapshot(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import sheet_cutting_layout

	class FrappeStub:
		class _Session:
			user = "system@example.com"

		session = _Session()

		@staticmethod
		def now_datetime() -> datetime:
			return datetime(2026, 5, 15, 10, 0, 0)

	monkeypatch.setattr(
		sheet_cutting_layout,
		"_get_selected_workflow_action",
		lambda: "Submit for Check",
	)
	monkeypatch.setattr(sheet_cutting_layout, "frappe", FrappeStub)
	monkeypatch.setattr(sheet_cutting_layout, "validate_sheet_cutting_layout", lambda _doc: None)

	doc = _new_sheet_cutting_layout_doc(sheet_cutting_layout)
	doc.approval_snapshot = []

	doc.validate()

	assert len(doc.approval_snapshot) == 1
	assert doc.approval_snapshot[0]["step_name"] == "Submit for Check"
	assert doc.approval_snapshot[0]["approver"] == "system@example.com"
	assert doc.approval_snapshot[0]["decision"] == "Submitted"
	assert doc.approval_snapshot[0]["decision_time"] == datetime(2026, 5, 15, 10, 0, 0)


def test_workflow_wrapper_sets_selected_action_for_sheet_cutting_layout(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import sheet_cutting_layout

	calls: list[tuple[object, str, object]] = []

	class Flags:
		selected_workflow_action = "old-action"

	class FrappeStub:
		flags = Flags()

		@staticmethod
		def parse_json(doc: object) -> dict[str, str]:
			return doc  # type: ignore[return-value]

	class FrappeWorkflowStub:
		@staticmethod
		def apply_workflow(doc: object, action: str) -> str:
			calls.append((doc, action, FrappeStub.flags.selected_workflow_action))
			return "applied"

	monkeypatch.setattr(sheet_cutting_layout, "frappe", FrappeStub)
	monkeypatch.setitem(sys.modules, "frappe.model.workflow", FrappeWorkflowStub)

	result = sheet_cutting_layout.apply_sheet_cutting_layout_workflow(
		{"doctype": "Sheet Cutting Layout"},
		"MR Release",
	)

	assert result == "applied"
	assert calls == [({"doctype": "Sheet Cutting Layout"}, "MR Release", "MR Release")]
	assert FrappeStub.flags.selected_workflow_action == "old-action"


def test_workflow_wrapper_is_whitelisted() -> None:
	assert hooks.override_whitelisted_methods.get("frappe.model.workflow.apply_workflow", "").endswith(
		"sheet_cutting_layout.apply_sheet_cutting_layout_workflow"
	)


def test_rejected_layout_on_trash_removes_workflow_action_links(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import sheet_cutting_layout

	deletions: list[tuple[str, dict[str, str]]] = []

	class DbStub:
		@staticmethod
		def get_all(doctype: str, **kwargs: object) -> list[str]:
			assert doctype == "Workflow Action"
			assert kwargs == {
				"filters": {
					"reference_doctype": "Sheet Cutting Layout",
					"reference_name": "SCL-REJECTED",
				},
				"pluck": "name",
			}
			return ["WF-ACTION-1", "WF-ACTION-2"]

		@staticmethod
		def delete(doctype: str, filters: dict[str, str]) -> None:
			deletions.append((doctype, filters))

	class FrappeStub:
		db = DbStub()

	monkeypatch.setattr(sheet_cutting_layout, "frappe", FrappeStub)

	doc = _new_sheet_cutting_layout_doc(sheet_cutting_layout)
	doc.name = "SCL-REJECTED"
	doc.status = "Rejected"

	doc.on_trash()

	assert deletions == [
		(
			"Workflow Action Permitted Role",
			{"parenttype": "Workflow Action", "parent": ["in", ["WF-ACTION-1", "WF-ACTION-2"]]},
		),
		(
			"Workflow Action",
			{"reference_doctype": "Sheet Cutting Layout", "reference_name": "SCL-REJECTED"},
		),
	]


def test_non_rejected_layout_on_trash_keeps_workflow_action_links(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import sheet_cutting_layout

	deletions: list[object] = []

	class DbStub:
		@staticmethod
		def get_all(doctype: str, **kwargs: object) -> list[str]:
			raise AssertionError("non-rejected layouts must not query workflow actions")

		@staticmethod
		def delete(doctype: str, filters: dict[str, str]) -> None:
			deletions.append((doctype, filters))

	class FrappeStub:
		db = DbStub()

	monkeypatch.setattr(sheet_cutting_layout, "frappe", FrappeStub)

	doc = _new_sheet_cutting_layout_doc(sheet_cutting_layout)
	doc.name = "SCL-RELEASED"
	doc.status = "Released"

	doc.on_trash()

	assert deletions == []


def test_patch_submits_existing_released_layouts(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.patches import v1_0_submit_released_layouts

	class DbStub:
		calls: ClassVar[list[tuple[str, dict[str, object], str, int, str | None]]] = []

		@classmethod
		def set_value(
			cls,
			doctype: str,
			filters: dict[str, object],
			fieldname: str,
			value: int,
			update_modified: bool = False,
		) -> None:
			cls.calls.append((doctype, filters, fieldname, value, str(update_modified)))

	class FrappeStub:
		db = DbStub

	monkeypatch.setattr(v1_0_submit_released_layouts, "frappe", FrappeStub)

	v1_0_submit_released_layouts.execute()

	assert DbStub.calls == [
		(
			"Sheet Cutting Layout",
			{"status": "Released", "docstatus": 0},
			"docstatus",
			1,
			"False",
		)
	]


def test_patch_submits_existing_superseded_layouts(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.patches import v1_0_submit_superseded_layouts

	class DbStub:
		calls: ClassVar[list[tuple[str, dict[str, object], str, int, str | None]]] = []

		@classmethod
		def set_value(
			cls,
			doctype: str,
			filters: dict[str, object],
			fieldname: str,
			value: int,
			update_modified: bool = False,
		) -> None:
			cls.calls.append((doctype, filters, fieldname, value, str(update_modified)))

	class FrappeStub:
		db = DbStub

	monkeypatch.setattr(v1_0_submit_superseded_layouts, "frappe", FrappeStub)

	v1_0_submit_superseded_layouts.execute()

	assert DbStub.calls == [
		(
			"Sheet Cutting Layout",
			{"status": "Superseded", "docstatus": 0},
			"docstatus",
			1,
			"False",
		)
	]


def test_patch_marks_cancelled_layouts_and_unlinks_generated_boms(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.patches import v1_0_mark_cancelled_layouts_and_unlink_boms

	class DbStub:
		set_value_calls: ClassVar[list[tuple[str, object, object, object, bool]]] = []

		@staticmethod
		def get_all(
			doctype: str,
			filters: dict[str, object],
			fields: list[str] | None = None,
			pluck: str | None = None,
		) -> list[object]:
			if doctype == "Sheet Cutting Layout":
				assert filters == {"docstatus": 2}
				assert fields == ["name", "generated_bom"]
				return [{"name": "002-R2", "generated_bom": "BOM-FG01SHR-004"}]
			if doctype == "BOM":
				assert filters == {"docstatus": 2, "sheet_cutting_layout": ["is", "set"]}
				assert pluck == "name"
				return ["BOM-CANCELLED-LINKED"]
			raise AssertionError(doctype)

		@staticmethod
		def exists(doctype: str, name: str) -> bool:
			return (doctype, name) == ("BOM", "BOM-FG01SHR-004")

		@classmethod
		def set_value(
			cls,
			doctype: str,
			name: object,
			fieldname: object,
			value: object = None,
			update_modified: bool = False,
		) -> None:
			cls.set_value_calls.append((doctype, name, fieldname, value, update_modified))

	class FrappeStub:
		db = DbStub

	monkeypatch.setattr(v1_0_mark_cancelled_layouts_and_unlink_boms, "frappe", FrappeStub)

	v1_0_mark_cancelled_layouts_and_unlink_boms.execute()

	assert DbStub.set_value_calls == [
		(
			"Sheet Cutting Layout",
			"002-R2",
			{"status": "Cancel", "generated_bom": None},
			None,
			False,
		),
		("BOM", "BOM-FG01SHR-004", "sheet_cutting_layout", None, False),
		("BOM", "BOM-CANCELLED-LINKED", "sheet_cutting_layout", None, False),
	]


def test_patch_repairs_checked_workflow_state_to_pm_approved(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.patches import (
		v1_0_migrate_checked_workflow_state_to_pm_approved,
	)

	class DbStub:
		calls: ClassVar[list[tuple[str, dict[str, object], str, str, bool]]] = []

		@classmethod
		def set_value(
			cls,
			doctype: str,
			filters: dict[str, object],
			fieldname: str,
			value: str,
			update_modified: bool = False,
		) -> None:
			cls.calls.append((doctype, filters, fieldname, value, update_modified))

		@staticmethod
		def has_column(doctype: str, fieldname: str) -> bool:
			assert doctype == "Sheet Cutting Layout"
			return fieldname in {"project_manager_ok", "manufacturing_manager_ok"}

	class FrappeStub:
		db = DbStub

	monkeypatch.setattr(
		v1_0_migrate_checked_workflow_state_to_pm_approved,
		"frappe",
		FrappeStub,
	)

	v1_0_migrate_checked_workflow_state_to_pm_approved.execute()

	assert DbStub.calls == [
		(
			"Sheet Cutting Layout",
			{"status": "Checked"},
			"status",
			"PM Approved",
			False,
		),
		(
			"Sheet Cutting Layout",
			{
				"status": "Submitted for Check",
				"project_manager_ok": 1,
				"manufacturing_manager_ok": 1,
			},
			"status",
			"PM Approved",
			False,
		),
	]


def test_patch_skips_legacy_hidden_flag_repair_when_columns_are_absent(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.patches import (
		v1_0_migrate_checked_workflow_state_to_pm_approved,
	)

	class DbStub:
		calls: ClassVar[list[tuple[str, dict[str, object], str, str, bool]]] = []

		@classmethod
		def set_value(
			cls,
			doctype: str,
			filters: dict[str, object],
			fieldname: str,
			value: str,
			update_modified: bool = False,
		) -> None:
			cls.calls.append((doctype, filters, fieldname, value, update_modified))

		@staticmethod
		def has_column(doctype: str, fieldname: str) -> bool:
			assert doctype == "Sheet Cutting Layout"
			assert fieldname in {"project_manager_ok", "manufacturing_manager_ok"}
			return False

	class FrappeStub:
		db = DbStub

	monkeypatch.setattr(
		v1_0_migrate_checked_workflow_state_to_pm_approved,
		"frappe",
		FrappeStub,
	)

	v1_0_migrate_checked_workflow_state_to_pm_approved.execute()

	assert DbStub.calls == [
		(
			"Sheet Cutting Layout",
			{"status": "Checked"},
			"status",
			"PM Approved",
			False,
		)
	]


def test_patch_backfills_missing_mr_approval_snapshots(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.patches import v1_0_backfill_mr_approval_snapshots

	inserted_rows: list[dict[str, object]] = []

	class DbStub:
		@staticmethod
		def get_all(doctype: str, **kwargs: object) -> list[dict[str, object]]:
			assert doctype == "Sheet Cutting Layout"
			assert kwargs == {
				"filters": {"status": ["in", ["Released", "Superseded"]]},
				"fields": ["name", "owner", "modified_by", "modified"],
			}
			return [
				{
					"name": "SCL-RELEASED",
					"owner": "owner@example.com",
					"modified_by": "mr@example.com",
					"modified": datetime(2026, 5, 18, 14, 30, 0),
				},
				{
					"name": "SCL-ALREADY-HAS-MR",
					"owner": "owner@example.com",
					"modified_by": "mr@example.com",
					"modified": datetime(2026, 5, 18, 14, 31, 0),
				},
			]

		@staticmethod
		def exists(doctype: str, filters: dict[str, object]) -> bool:
			assert doctype == "Layout Approval Snapshot"
			return filters["parent"] == "SCL-ALREADY-HAS-MR"

		@staticmethod
		def count(doctype: str, filters: dict[str, object]) -> int:
			assert doctype == "Layout Approval Snapshot"
			assert filters == {"parent": "SCL-RELEASED", "parenttype": "Sheet Cutting Layout"}
			return 4

	class InsertableDoc(dict[str, object]):
		def insert(self, **kwargs: object) -> None:
			assert kwargs == {"ignore_permissions": True}
			inserted_rows.append(dict(self))

	class FrappeStub:
		db = DbStub

		@staticmethod
		def get_doc(row: dict[str, object]) -> InsertableDoc:
			return InsertableDoc(row)

	monkeypatch.setattr(v1_0_backfill_mr_approval_snapshots, "frappe", FrappeStub)

	v1_0_backfill_mr_approval_snapshots.execute()

	assert inserted_rows == [
		{
			"doctype": "Layout Approval Snapshot",
			"parent": "SCL-RELEASED",
			"parenttype": "Sheet Cutting Layout",
			"parentfield": "approval_snapshot",
			"idx": 5,
			"step_name": "MR Approval",
			"approver": "mr@example.com",
			"decision": "Approved",
			"decision_time": datetime(2026, 5, 18, 14, 30, 0),
		}
	]


def test_frappe_bom_insert_sets_required_company_from_layout(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import release_service
	from sheet_cutting_layout.services.bom_service import BomDocument

	class FrappeBom:
		def __init__(self) -> None:
			self.name = ""
			self.items: list[dict[str, object]] = []
			self.insert_calls = 0
			self.submit_calls = 0

		def append(self, fieldname: str, row: dict[str, object]) -> None:
			assert fieldname == "items"
			self.items.append(row)

		def insert(self) -> None:
			self.insert_calls += 1
			assert self.company == "Test Company"
			assert self.custom_operation == "Shearing"
			assert self.sheet_cutting_layout == "SCL-001"
			self.name = self.name or "BOM-PERSISTED"

		def submit(self) -> None:
			self.submit_calls += 1

	class FrappeStub:
		@staticmethod
		def new_doc(doctype: str) -> FrappeBom:
			assert doctype == "BOM"
			return FrappeBom()

	bom = BomDocument(item="PART001SHR", name="BOM-PART001SHR")
	bom._layout = type("LayoutWithCompany", (), {"company": "Test Company", "name": "SCL-001"})()
	monkeypatch.setattr(release_service, "frappe", FrappeStub)

	inserted = release_service._insert_frappe_bom(bom)

	assert inserted.name == "BOM-PART001SHR"
	assert inserted.status == "Active"


def test_frappe_bom_insert_wraps_scrap_rate_resolution_error(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import release_service
	from sheet_cutting_layout.services.bom_service import BomDocument, BomItemRow

	class FrappeBom:
		def __init__(self) -> None:
			self.name = ""
			self.items: list[dict[str, object]] = []
			self.scrap_items: list[dict[str, object]] = []

		def append(self, fieldname: str, row: dict[str, object]) -> None:
			getattr(self, fieldname).append(row)

		def insert(self) -> None:
			self.name = self.name or "BOM-PERSISTED"

		def submit(self) -> None:
			raise AssertionError("submit should not run after scrap-rate resolution failure")

	class FrappeStub:
		@staticmethod
		def new_doc(doctype: str) -> FrappeBom:
			assert doctype == "BOM"
			return FrappeBom()

		@staticmethod
		def throw(message: str) -> None:
			raise ValueError(message)

	bom = BomDocument(item="PART001SHR", name="BOM-PART001SHR")
	bom._layout = type("LayoutWithCompany", (), {"company": "Test Company", "name": "SCL-001"})()
	bom.scrap_items.append(BomItemRow(item_code="SCRAP-ITEM", qty=1.0, row_type="process_scrap"))
	monkeypatch.setattr(release_service, "frappe", FrappeStub)

	def _raise_rate_error(**_kwargs: object) -> float:
		raise ValueError("Valuation rate is required for scrap item SCRAP-ITEM")

	monkeypatch.setattr(release_service, "resolve_scrap_item_rate", _raise_rate_error)

	with raises(
		ValueError,
		match=(
			r"^Failed to resolve valuation rate for scrap item SCRAP-ITEM: "
			r"Valuation rate is required for scrap item SCRAP-ITEM$"
		),
	):
		release_service._insert_frappe_bom(bom)


def test_default_release_creates_reuse_end_piece_byproduct_row(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import release_service

	created_boms: list[object] = []

	class FrappeBom:
		def __init__(self) -> None:
			self.name = ""
			self.items: list[dict[str, object]] = []
			self.scrap_items: list[dict[str, object]] = []
			self.flags = type("Flags", (), {})()

		def append(self, fieldname: str, row: dict[str, object]) -> None:
			getattr(self, fieldname).append(row)

		def insert(self) -> None:
			self.name = self.name or "BOM-FG01SHR-001"
			created_boms.append(self)

		def submit(self) -> None:
			self.docstatus = 1

	class FrappeStub:
		@staticmethod
		def new_doc(doctype: str) -> FrappeBom:
			assert doctype == "BOM"
			return FrappeBom()

		@staticmethod
		def throw(message: str) -> None:
			raise ValueError(message)

	layout = Layout(
		name="002-R2",
		weight_per_sheet_kg=39.3,
		parts_per_sheet=77,
		finished_part_code="FG01SHR",
		net_weight_per_part_kg=0.289,
		gross_weight_per_part_kg=0.473846,
		scrap_weight_per_part_kg=0.184846,
		finished_parts=[],
		end_pieces=[
			EndPiece(
				weight_kg=2.81388,
				disposition="Reuse",
				used_for_finished_part="FG002SHR",
				width_mm=1250,
				length_mm=179,
			)
		],
	)
	layout.company = "Test Company"
	layout.sheet_thickness_mm = 1.6

	def fake_ensure(_layout: object, _row: object) -> str:
		return "FG002SHR-EP-1.6x1250x179"

	monkeypatch.setattr(release_service, "frappe", FrappeStub)
	monkeypatch.setattr(release_service, "ensure_end_piece_item", fake_ensure)
	monkeypatch.setattr(release_service, "resolve_scrap_item_rate", lambda **_kwargs: 62.0)

	result = release_service.release_layout(
		layout,
		validators=[lambda _layout: None],
		release_context=release_service.ReleaseContext(layouts=(), boms=[]),
	)

	assert result.generated_boms[0].name == "BOM-002-R2-001-FG01SHR"
	assert layout.end_pieces[0].end_piece_item_code == "FG002SHR-EP-1.6x1250x179"
	assert len(created_boms) == 1
	assert created_boms[0].scrap_items == [
		{
			"item_code": "PROCESSSCRAP001",
			"stock_qty": 14.233142,
			"qty": 14.233142,
			"uom": "Kg",
			"rate": 62.0,
		},
		{
			"item_code": "FG002SHR-EP-1.6x1250x179",
			"stock_qty": 2.81388,
			"qty": 2.81388,
			"uom": "Kg",
			"rate": 62.0,
		},
	]
	assert round(layout.finished_parts[0].scrap_weight_kg, 6) == 17.047022
	assert layout.finished_parts[0].raw_material_weight_kg == 39.3


def test_default_release_persists_generated_end_piece_item_code_on_saved_layout(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import release_service

	created_boms: list[object] = []

	class SavableLayout(Layout):
		def __init__(self, **kwargs: object) -> None:
			super().__init__(**kwargs)
			self.save_calls = 0

		def save(self, **kwargs: object) -> None:
			assert kwargs == {"ignore_permissions": True}
			self.save_calls += 1

	class FrappeBom:
		def __init__(self) -> None:
			self.name = ""
			self.items: list[dict[str, object]] = []
			self.scrap_items: list[dict[str, object]] = []
			self.flags = type("Flags", (), {})()

		def append(self, fieldname: str, row: dict[str, object]) -> None:
			getattr(self, fieldname).append(row)

		def insert(self) -> None:
			self.name = self.name or "BOM-FG01SHR-001"
			created_boms.append(self)

		def submit(self) -> None:
			self.docstatus = 1

	class FrappeStub:
		@staticmethod
		def new_doc(doctype: str) -> FrappeBom:
			assert doctype == "BOM"
			return FrappeBom()

		@staticmethod
		def throw(message: str) -> None:
			raise ValueError(message)

	layout = Layout(
		name="002-R2",
		weight_per_sheet_kg=39.3,
		parts_per_sheet=77,
		finished_part_code="FG01SHR",
		net_weight_per_part_kg=0.289,
		gross_weight_per_part_kg=0.473846,
		scrap_weight_per_part_kg=0.184846,
		finished_parts=[],
		end_pieces=[
			EndPiece(
				weight_kg=2.81388,
				disposition="Reuse",
				used_for_finished_part="FG002SHR",
				width_mm=1250,
				length_mm=179,
			)
		],
	)
	layout.company = "Test Company"
	layout.sheet_thickness_mm = 1.6

	persisted_layout = SavableLayout(
		name=layout.name,
		weight_per_sheet_kg=layout.weight_per_sheet_kg,
		parts_per_sheet=layout.parts_per_sheet,
		finished_part_code=layout.finished_part_code,
		net_weight_per_part_kg=layout.net_weight_per_part_kg,
		gross_weight_per_part_kg=layout.gross_weight_per_part_kg,
		scrap_weight_per_part_kg=layout.scrap_weight_per_part_kg,
		finished_parts=[],
		end_pieces=[
			EndPiece(
				weight_kg=2.81388,
				disposition="Reuse",
				used_for_finished_part="FG002SHR",
				width_mm=1250,
				length_mm=179,
			)
		],
	)
	assert persisted_layout is not layout

	def fake_ensure(_layout: object, _row: object) -> str:
		return "FG002SHR-EP-1.6x1250x179"

	monkeypatch.setattr(release_service, "frappe", FrappeStub)
	monkeypatch.setattr(release_service, "ensure_end_piece_item", fake_ensure)
	monkeypatch.setattr(release_service, "resolve_scrap_item_rate", lambda **_kwargs: 62.0)

	release_service.release_layout(
		layout,
		validators=[lambda _layout: None],
		release_context=release_service.ReleaseContext(layouts=(persisted_layout,), boms=[]),
	)

	assert layout.end_pieces[0].end_piece_item_code == "FG002SHR-EP-1.6x1250x179"
	assert persisted_layout.save_calls == 1
	assert persisted_layout.end_pieces[0].end_piece_item_code == "FG002SHR-EP-1.6x1250x179"


def test_get_release_context_requires_frappe_outside_tests(monkeypatch: MonkeyPatch) -> None:
	from sheet_cutting_layout.services import release_service

	monkeypatch.setattr(release_service, "frappe", None)

	with raises(RuntimeError, match="Frappe is required"):
		release_service.get_release_context(Layout())


def test_release_context_discovers_layouts_and_boms(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import release_service

	class FrappeStub:
		@staticmethod
		def get_all(doctype: str, **kwargs: object) -> list[object]:
			if doctype == "Sheet Cutting Layout":
				return ["SCL-OLD"]
			if doctype == "BOM":
				return ["BOM-OLD"]
			raise AssertionError(f"Unexpected doctype {doctype}")

		@staticmethod
		def get_doc(doctype: str, name: str) -> object:
			return type("Doc", (), {"doctype": doctype, "name": name})()

	layout = RevisionLayout(
		name="SCL-NEW",
		project="FAM-001",
		revision_no=2,
		status="Approved by Purchase",
		is_active=False,
		finished_parts=[FinishedPart("PART001SHR")],
	)
	monkeypatch.setattr(release_service, "frappe", FrappeStub)

	context = release_service.get_release_context(layout)

	assert [getattr(doc, "name", None) for doc in context.layouts] == ["SCL-OLD", "SCL-NEW"]
	assert [getattr(doc, "name", None) for doc in context.boms or []] == ["BOM-OLD"]


def test_release_context_handles_layout_without_family_or_finished_parts(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import release_service

	class FrappeStub:
		@staticmethod
		def get_all(doctype: str, **_kwargs: object) -> list[object]:
			raise AssertionError(f"Unexpected doctype {doctype}")

	layout = type(
		"LayoutWithoutFamily",
		(),
		{
			"project": "",
			"finished_parts": [],
		},
	)()
	monkeypatch.setattr(release_service, "frappe", FrappeStub)

	context = release_service.get_release_context(layout)

	assert context.layouts == [layout]
	assert context.boms == []


def test_release_helpers_raise_without_frappe(monkeypatch: MonkeyPatch) -> None:
	from sheet_cutting_layout.services import release_service

	monkeypatch.setattr(release_service, "frappe", None)

	with raises(RuntimeError, match="BOM records"):
		release_service._get_finished_part_boms(Layout())


def test_default_bom_factory_requires_frappe_outside_tests(monkeypatch: MonkeyPatch) -> None:
	from sheet_cutting_layout.services import release_service

	layout = Layout()
	finished_part = layout.finished_parts[0]
	monkeypatch.setattr(release_service, "frappe", None)

	with raises(RuntimeError, match="persist generated BOM"):
		release_service._default_bom_document_factory(layout, finished_part, 1, None)


def test_company_resolution_uses_defaults_and_errors_when_missing(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import release_service

	class DefaultsOnly:
		class defaults:
			@staticmethod
			def get_user_default(_key: str) -> str:
				return "Default Company"

	class DbDefault:
		class defaults:
			@staticmethod
			def get_user_default(_key: str) -> str:
				return ""

		class db:
			@staticmethod
			def get_default(_key: str) -> str:
				return "DB Company"

	class NoCompany:
		class ValidationError(Exception):
			pass

		class defaults:
			@staticmethod
			def get_user_default(_key: str) -> str:
				return ""

		@staticmethod
		def throw(message: str) -> None:
			raise NoCompany.ValidationError(message)

	monkeypatch.setattr(release_service, "frappe", DefaultsOnly)
	assert release_service._company_for_layout(None) == "Default Company"

	monkeypatch.setattr(release_service, "frappe", DbDefault)
	assert release_service._company_for_layout(None) == "DB Company"

	monkeypatch.setattr(release_service, "frappe", NoCompany)
	with raises(NoCompany.ValidationError, match="Company is required"):
		release_service._company_for_layout(None)


def test_set_frappe_field_only_when_supported() -> None:
	from sheet_cutting_layout.services import release_service

	class Meta:
		@staticmethod
		def has_field(fieldname: str) -> bool:
			return fieldname == "enabled"

	class Doc:
		meta = Meta()
		enabled = 0

	doc = Doc()
	release_service._set_frappe_field_if_supported(doc, "enabled", 1)
	release_service._set_frappe_field_if_supported(doc, "missing", 1)
	release_service._set_frappe_field_if_supported(object(), "missing", 1)

	assert doc.enabled == 1
	assert not hasattr(doc, "missing")


def test_revising_released_layout_clones_and_increments_revision() -> None:
	from sheet_cutting_layout.services.versioning import create_revision

	old_layout = RevisionLayout(
		name="SCL-001",
		project="FAM-001",
		layout_code="SCL-001",
		revision_no=2,
		status="Released",
		is_active=True,
	)

	new_layout = create_revision(old_layout)

	assert new_layout is not old_layout
	assert new_layout.revision_no == 3
	assert new_layout.layout_code == "SCL-001-R3"
	assert new_layout.status == "Draft"
	assert new_layout.based_on_layout == "SCL-001"
	assert new_layout.is_active is False


def test_revision_resets_approval_snapshot_and_generated_boms() -> None:
	from sheet_cutting_layout.services.versioning import create_revision

	old_layout = RevisionLayout(
		name="SCL-001",
		project="FAM-001",
		revision_no=1,
		status="Released",
		is_active=True,
		approval_snapshot=["purchase-approved"],
		generated_bom="BOM-PARENT-001-001",
		finished_parts=[
			FinishedPart("PART001SHR", generated_bom="BOM-PART-001-001"),
			FinishedPart("PART002SHR", generated_bom="BOM-PART-002-001"),
		],
		end_pieces=[EndPiece(weight_kg=2.5, end_piece_item_code="PART001SHR-EP-1x1250x260")],
		end_piece_bom_status="Generated",
	)

	new_layout = create_revision(old_layout)

	assert new_layout.approval_snapshot == []
	assert new_layout.generated_bom is None
	assert new_layout.end_piece_bom_status == "Pending"
	assert new_layout.finished_parts == []
	assert new_layout.end_pieces[0].end_piece_item_code is None
	assert new_layout.finished_part_code == "PART001SHR"
	assert new_layout.net_weight_per_part_kg == 1.0
	assert old_layout.generated_bom == "BOM-PARENT-001-001"
	assert [row.generated_bom for row in old_layout.finished_parts] == [
		"BOM-PART-001-001",
		"BOM-PART-002-001",
	]


def test_finalizing_new_revision_keeps_previous_active_layouts_released() -> None:
	from sheet_cutting_layout.services.versioning import finalize_new_revision_release

	old_layout = RevisionLayout(
		name="SCL-001",
		project="FAM-001",
		revision_no=1,
		status="Released",
		is_active=True,
	)
	other_family_layout = RevisionLayout(
		name="SCL-OTHER",
		project="FAM-OTHER",
		revision_no=1,
		status="Released",
		is_active=True,
	)
	new_layout = RevisionLayout(
		name="SCL-002",
		project="FAM-001",
		revision_no=2,
		status="Approved by Purchase",
		is_active=False,
	)

	finalize_new_revision_release([old_layout, other_family_layout, new_layout], new_layout, [])

	assert old_layout.status == "Released"
	assert old_layout.is_active is True
	assert new_layout.status == "Released"
	assert new_layout.is_active is True
	assert other_family_layout.status == "Released"
	assert other_family_layout.is_active is True


def test_finalizing_new_revision_keeps_old_boms_for_affected_finished_parts_active() -> None:
	from sheet_cutting_layout.services.versioning import finalize_new_revision_release

	old_layout = RevisionLayout(
		name="SCL-001",
		project="FAM-001",
		revision_no=1,
		status="Released",
		is_active=True,
		finished_parts=[
			FinishedPart("PART001SHR", generated_bom="BOM-PART-001-OLD"),
			FinishedPart("PARTUNTOUCHEDSHR", generated_bom="BOM-UNTOUCHED-OLD"),
		],
	)
	new_layout = RevisionLayout(
		name="SCL-002",
		project="FAM-001",
		revision_no=2,
		status="Approved by Purchase",
		is_active=False,
		finished_parts=[FinishedPart("PART001SHR", generated_bom="BOM-PART-001-NEW")],
	)
	old_bom = Bom("BOM-PART-001-OLD", item="PART001SHR")
	new_bom = Bom("BOM-PART-001-NEW", item="PART001SHR")
	unaffected_bom = Bom("BOM-UNTOUCHED-OLD", item="PARTUNTOUCHEDSHR")

	finalize_new_revision_release([old_layout, new_layout], new_layout, [old_bom, new_bom, unaffected_bom])

	assert old_bom.is_active is True
	assert old_bom.disabled is False
	assert old_bom.status == "Active"
	assert new_bom.is_active is True
	assert new_bom.disabled is False
	assert new_bom.status == "Active"
	assert unaffected_bom.is_active is True
	assert unaffected_bom.disabled is False
	assert unaffected_bom.status == "Active"


def test_finalizing_new_revision_keeps_unlinked_same_item_boms_active() -> None:
	from sheet_cutting_layout.services.versioning import finalize_new_revision_release

	old_layout = RevisionLayout(
		name="SCL-001",
		project="FAM-001",
		revision_no=1,
		status="Released",
		is_active=True,
		finished_parts=[FinishedPart("PART001SHR", generated_bom="BOM-PART-001-OLD")],
	)
	new_layout = RevisionLayout(
		name="SCL-002",
		project="FAM-001",
		revision_no=2,
		status="Approved by Purchase",
		is_active=False,
		finished_parts=[FinishedPart("PART001SHR", generated_bom="BOM-PART-001-NEW")],
	)
	old_linked_bom = Bom("BOM-PART-001-OLD", item="PART001SHR")
	unlinked_same_item_bom = Bom("BOM-PART-001-UNRELATED", item="PART001SHR")
	new_bom = Bom("BOM-PART-001-NEW", item="PART001SHR")

	finalize_new_revision_release(
		[old_layout, new_layout],
		new_layout,
		[old_linked_bom, unlinked_same_item_bom, new_bom],
	)

	assert old_linked_bom.is_active is True
	assert old_linked_bom.disabled is False
	assert old_linked_bom.status == "Active"
	assert unlinked_same_item_bom.is_active is True
	assert unlinked_same_item_bom.disabled is False
	assert unlinked_same_item_bom.status == "Active"
	assert new_bom.is_active is True
	assert new_bom.disabled is False
	assert new_bom.status == "Active"


def test_finalizing_new_revision_keeps_old_parent_generated_bom_active() -> None:
	from sheet_cutting_layout.services.versioning import finalize_new_revision_release

	old_layout = RevisionLayout(
		name="SCL-001",
		project="FAM-001",
		revision_no=1,
		status="Released",
		is_active=True,
		generated_bom="BOM-PART-001-OLD",
		finished_parts=[FinishedPart("PART001SHR")],
	)
	new_layout = RevisionLayout(
		name="SCL-002",
		project="FAM-001",
		revision_no=2,
		status="Approved by Purchase",
		is_active=False,
		generated_bom="BOM-PART-001-NEW",
		finished_parts=[FinishedPart("PART001SHR")],
	)
	old_bom = Bom("BOM-PART-001-OLD", item="PART001SHR")
	new_bom = Bom("BOM-PART-001-NEW", item="PART001SHR")

	finalize_new_revision_release([old_layout, new_layout], new_layout, [old_bom, new_bom])

	assert old_bom.is_active is True
	assert old_bom.disabled is False
	assert old_bom.status == "Active"
	assert new_bom.is_active is True
	assert new_bom.disabled is False
	assert new_bom.status == "Active"


def test_release_generates_one_bom_for_single_finished_part_and_keeps_existing_boms_active() -> None:
	from sheet_cutting_layout.services.release_service import release_layout

	old_layout = RevisionLayout(
		name="SCL-001",
		project="PROJECT-001",
		revision_no=1,
		status="Released",
		is_active=True,
		finished_parts=[FinishedPart("PART001SHR", generated_bom="BOM-PART001SHR-OLD")],
	)
	new_layout = RevisionLayout(
		name="SCL-002",
		project="PROJECT-001",
		revision_no=2,
		status="Approved by Purchase",
		is_active=False,
		weight_per_sheet_kg=5.0,
		finished_parts=[
			FinishedPart("PART001SHR", gross_weight_per_part_kg=5.0, scrap_weight_per_part_kg=0.2)
		],
	)
	old_bom = Bom("BOM-PART001SHR-OLD", item="PART001SHR")

	result = release_layout(
		new_layout,
		layouts=[old_layout, new_layout],
		boms=[old_bom],
		bom_document_factory=_in_memory_bom_factory,
	)

	assert result.status == "Released"
	assert len(result.generated_boms) == 1
	assert [bom.item for bom in result.generated_boms] == ["PART001SHR"]
	assert [bom.quantity for bom in result.generated_boms] == [1]
	assert [
		[(item.item_code, item.qty, item.row_type) for item in bom.items] for bom in result.generated_boms
	] == [[("RM-SHEET-001", 5.0, "raw_material")]]
	assert [
		[(item.item_code, item.qty, item.row_type) for item in bom.scrap_items]
		for bom in result.generated_boms
	] == [[("PROCESS-SCRAP-001", 0.2, "process_scrap")]]
	assert new_layout.generated_bom == result.generated_boms[0].name
	assert [row.finished_part_item for row in new_layout.finished_parts] == ["PART001SHR"]
	assert [row.bom_quantity for row in new_layout.finished_parts] == [1]
	assert result.superseded_layout is None
	assert old_layout.status == "Released"
	assert old_layout.is_active is True
	assert old_bom.is_active is True
	assert old_bom.disabled is False
	assert old_bom.status == "Active"
	assert all(bom.is_active is True for bom in result.generated_boms)
	assert all(bom.disabled is False for bom in result.generated_boms)
	assert all(bom.status == "Active" for bom in result.generated_boms)


def test_deactivate_generated_bom_marks_linked_bom_superseded(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import release_service
	from sheet_cutting_layout.services.release_service import deactivate_generated_bom

	class BomDoc:
		def __init__(self) -> None:
			self.name = "BOM-PART001SHR-001"
			self.item = "PART001SHR"
			self.flags = type("Flags", (), {})()
			self.is_active = 1
			self.disabled = 0
			self.is_default = 1
			self.status = "Active"
			self.save_calls: list[dict[str, object]] = []

		def save(self, **kwargs: object) -> None:
			self.save_calls.append(kwargs)

	bom_doc = BomDoc()

	class FrappeStub:
		class db:
			set_value_calls: ClassVar[list[tuple[object, ...]]] = []

			@staticmethod
			def get_value(doctype: str, name: str, fieldname: str) -> str:
				assert (doctype, name, fieldname) == ("Item", "PART001SHR", "default_bom")
				return "BOM-OTHER-001"

			@classmethod
			def set_value(cls, *args: object, **kwargs: object) -> None:
				cls.set_value_calls.append(args)

		@staticmethod
		def get_doc(doctype: str, name: str) -> BomDoc:
			assert (doctype, name) == ("BOM", "BOM-PART001SHR-001")
			return bom_doc

	monkeypatch.setattr(release_service, "frappe", FrappeStub)

	result = deactivate_generated_bom(type("Layout", (), {"generated_bom": "BOM-PART001SHR-001"})())

	assert result is bom_doc
	assert bom_doc.is_active == 0
	assert bom_doc.disabled == 1
	assert bom_doc.is_default == 0
	assert bom_doc.status == "Superseded"
	assert getattr(bom_doc.flags, "sheet_cutting_layout_allow_bom_update", False) is True
	assert bom_doc.save_calls == [{"ignore_permissions": True}]
	# Item.default_bom points at another BOM, so it must be left untouched.
	assert FrappeStub.db.set_value_calls == []


def test_deactivate_generated_bom_uses_db_set_for_submitted_bom(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import release_service
	from sheet_cutting_layout.services.release_service import deactivate_generated_bom

	class BomDoc:
		docstatus = 1

		def __init__(self) -> None:
			self.name = "BOM-PART001SHR-001"
			self.is_active = 1
			self.disabled = 0
			self.status = "Active"
			self.db_set_calls: list[tuple[dict[str, object], bool, bool]] = []
			self.save_calls: list[dict[str, object]] = []

		def db_set(
			self,
			values: dict[str, object],
			update_modified: bool = True,
			notify: bool = False,
		) -> None:
			self.db_set_calls.append((values, update_modified, notify))

		def save(self, **kwargs: object) -> None:
			self.save_calls.append(kwargs)

	bom_doc = BomDoc()

	class FrappeStub:
		@staticmethod
		def get_doc(doctype: str, name: str) -> BomDoc:
			assert (doctype, name) == ("BOM", "BOM-PART001SHR-001")
			return bom_doc

	monkeypatch.setattr(release_service, "frappe", FrappeStub)

	result = deactivate_generated_bom(type("Layout", (), {"generated_bom": "BOM-PART001SHR-001"})())

	assert result is bom_doc
	assert bom_doc.is_active == 0
	assert bom_doc.disabled == 1
	assert bom_doc.status == "Superseded"
	assert bom_doc.db_set_calls == [
		({"is_active": 0, "disabled": 1, "is_default": 0, "status": "Superseded"}, True, False)
	]
	assert bom_doc.save_calls == []


def test_deactivate_generated_bom_deactivates_every_bom_linked_to_layout(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import release_service
	from sheet_cutting_layout.services.release_service import deactivate_generated_bom

	class BomDoc:
		docstatus = 1

		def __init__(self, name: str, item: str) -> None:
			self.name = name
			self.item = item
			self.is_active = 1
			self.disabled = 0
			self.is_default = 1
			self.status = "Active"
			self.db_set_calls: list[tuple[dict[str, object], bool, bool]] = []

		def db_set(
			self,
			values: dict[str, object],
			update_modified: bool = True,
			notify: bool = False,
		) -> None:
			self.db_set_calls.append((values, update_modified, notify))

	bom_docs = {
		"BOM-MAIN-001": BomDoc("BOM-MAIN-001", "PART001SHR"),
		"BOM-ENDPIECE-001": BomDoc("BOM-ENDPIECE-001", "EPITEM001"),
	}
	item_default_boms = {"PART001SHR": "BOM-MAIN-001", "EPITEM001": "BOM-ENDPIECE-001"}

	class FrappeStub:
		class db:
			@staticmethod
			def get_all(doctype: str, filters: dict[str, object], pluck: str) -> list[str]:
				assert doctype == "BOM"
				assert filters == {"sheet_cutting_layout": "SCL-001"}
				assert pluck == "name"
				return ["BOM-MAIN-001", "BOM-ENDPIECE-001"]

			@staticmethod
			def get_value(doctype: str, name: str, fieldname: str) -> str | None:
				assert (doctype, fieldname) == ("Item", "default_bom")
				return item_default_boms.get(name)

			@staticmethod
			def set_value(
				doctype: str,
				name: str,
				fieldname: str,
				value: object = None,
				update_modified: bool = True,
			) -> None:
				assert (doctype, fieldname, value, update_modified) == ("Item", "default_bom", None, False)
				item_default_boms[name] = value

		@staticmethod
		def get_doc(doctype: str, name: str) -> BomDoc:
			assert doctype == "BOM"
			return bom_docs[name]

	monkeypatch.setattr(release_service, "frappe", FrappeStub)

	layout = type(
		"Layout",
		(),
		{"doctype": "Sheet Cutting Layout", "name": "SCL-001", "generated_bom": "BOM-MAIN-001"},
	)()

	result = deactivate_generated_bom(layout)

	assert result is bom_docs["BOM-MAIN-001"]
	assert bom_docs["BOM-MAIN-001"].db_set_calls == [
		({"is_active": 0, "disabled": 1, "is_default": 0, "status": "Superseded"}, True, False)
	]
	assert bom_docs["BOM-ENDPIECE-001"].db_set_calls == [
		({"is_active": 0, "disabled": 1, "is_default": 0, "status": "Superseded"}, True, False)
	]
	assert item_default_boms == {"PART001SHR": None, "EPITEM001": None}


def test_cancel_generated_bom_cancels_submitted_bom_with_app_control_flag(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.overrides.bom import APP_CONTROLLED_BOM_UPDATE_FLAG
	from sheet_cutting_layout.services import release_service
	from sheet_cutting_layout.services.release_service import cancel_generated_bom

	class BomDoc:
		docstatus = 1
		custom_operation = "Shearing"
		sheet_cutting_layout = "SCL-001"

		def __init__(self) -> None:
			self.name = "BOM-PART001SHR-001"
			self.flags = type("Flags", (), {})()
			self.is_active = 1
			self.disabled = 0
			self.status = "Superseded"
			self.cancel_calls = 0

		def cancel(self) -> None:
			assert getattr(self.flags, APP_CONTROLLED_BOM_UPDATE_FLAG, False) is True
			assert getattr(self.flags, "ignore_links", False) is False
			self.cancel_calls += 1
			self.docstatus = 2

	bom_doc = BomDoc()

	class FrappeStub:
		class db:
			set_value_calls: ClassVar[list[tuple[str, str, object, object, bool]]] = []

			@classmethod
			def set_value(
				cls,
				doctype: str,
				name: str,
				fieldname: object,
				value: object = None,
				update_modified: bool = True,
			) -> None:
				cls.set_value_calls.append((doctype, name, fieldname, value, update_modified))

		@staticmethod
		def get_doc(doctype: str, name: str) -> BomDoc:
			assert (doctype, name) == ("BOM", "BOM-PART001SHR-001")
			return bom_doc

	monkeypatch.setattr(release_service, "frappe", FrappeStub)

	layout = type(
		"Layout",
		(),
		{"doctype": "Sheet Cutting Layout", "name": "SCL-001", "generated_bom": "BOM-PART001SHR-001"},
	)()

	result = cancel_generated_bom(layout)

	assert result is bom_doc
	assert layout.generated_bom is None
	assert bom_doc.is_active == 0
	assert bom_doc.disabled == 1
	assert bom_doc.sheet_cutting_layout is None
	assert bom_doc.cancel_calls == 1
	assert bom_doc.docstatus == 2
	assert FrappeStub.db.set_value_calls == [
		("Sheet Cutting Layout", "SCL-001", "generated_bom", None, False),
		("BOM", "BOM-PART001SHR-001", "sheet_cutting_layout", None, False),
	]


def test_cancel_generated_bom_cancels_every_bom_linked_to_layout(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.overrides.bom import APP_CONTROLLED_BOM_UPDATE_FLAG
	from sheet_cutting_layout.services import release_service
	from sheet_cutting_layout.services.release_service import cancel_generated_bom

	class BomDoc:
		docstatus = 1
		custom_operation = "Shearing"
		sheet_cutting_layout = "SCL-001"

		def __init__(self, name: str) -> None:
			self.name = name
			self.flags = type("Flags", (), {})()
			self.is_active = 1
			self.disabled = 0
			self.cancel_calls = 0

		def cancel(self) -> None:
			assert getattr(self.flags, APP_CONTROLLED_BOM_UPDATE_FLAG, False) is True
			assert getattr(self.flags, "ignore_links", False) is False
			self.cancel_calls += 1
			self.docstatus = 2

	bom_docs = {
		"BOM-MAIN-001": BomDoc("BOM-MAIN-001"),
		"BOM-ENDPIECE-001": BomDoc("BOM-ENDPIECE-001"),
	}

	class FrappeStub:
		class db:
			set_value_calls: ClassVar[list[tuple[str, str, object, object, bool]]] = []

			@staticmethod
			def get_all(doctype: str, filters: dict[str, object], pluck: str) -> list[str]:
				assert doctype == "BOM"
				assert filters == {"sheet_cutting_layout": "SCL-001"}
				assert pluck == "name"
				return ["BOM-MAIN-001", "BOM-ENDPIECE-001"]

			@classmethod
			def set_value(
				cls,
				doctype: str,
				name: str,
				fieldname: object,
				value: object = None,
				update_modified: bool = True,
			) -> None:
				cls.set_value_calls.append((doctype, name, fieldname, value, update_modified))

		@staticmethod
		def get_doc(doctype: str, name: str) -> BomDoc:
			assert doctype == "BOM"
			return bom_docs[name]

	monkeypatch.setattr(release_service, "frappe", FrappeStub)

	layout = type(
		"Layout",
		(),
		{"doctype": "Sheet Cutting Layout", "name": "SCL-001", "generated_bom": "BOM-MAIN-001"},
	)()

	result = cancel_generated_bom(layout)

	assert result is bom_docs["BOM-MAIN-001"]
	assert layout.generated_bom is None
	assert bom_docs["BOM-MAIN-001"].cancel_calls == 1
	assert bom_docs["BOM-ENDPIECE-001"].cancel_calls == 1
	assert bom_docs["BOM-MAIN-001"].sheet_cutting_layout is None
	assert bom_docs["BOM-ENDPIECE-001"].sheet_cutting_layout is None
	assert FrappeStub.db.set_value_calls == [
		("Sheet Cutting Layout", "SCL-001", "generated_bom", None, False),
		("BOM", "BOM-MAIN-001", "sheet_cutting_layout", None, False),
		("BOM", "BOM-ENDPIECE-001", "sheet_cutting_layout", None, False),
	]


class _SavepointFrappeStub:
	"""Frappe stub whose db honours savepoint/rollback over recorded set_value calls."""

	def __init__(self, bom_docs: dict[str, object]) -> None:
		class db:
			set_value_calls: ClassVar[list[tuple[str, str, object, object, bool]]] = []
			savepoint_names: ClassVar[list[str]] = []
			rollback_savepoints: ClassVar[list[str]] = []
			_savepoint_marks: ClassVar[dict[str, int]] = {}

			@classmethod
			def savepoint(cls, name: str) -> None:
				cls.savepoint_names.append(name)
				cls._savepoint_marks[name] = len(cls.set_value_calls)

			@classmethod
			def rollback(cls, *, save_point: str) -> None:
				cls.rollback_savepoints.append(save_point)
				del cls.set_value_calls[cls._savepoint_marks[save_point] :]

			@classmethod
			def set_value(
				cls,
				doctype: str,
				name: str,
				fieldname: object,
				value: object = None,
				update_modified: bool = True,
			) -> None:
				cls.set_value_calls.append((doctype, name, fieldname, value, update_modified))

		self.db = db
		self._bom_docs = bom_docs

	def get_doc(self, doctype: str, name: str) -> object:
		assert doctype == "BOM"
		return self._bom_docs[name]


def test_cancel_generated_bom_rolls_back_savepoint_when_submitted_cancel_fails(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import release_service
	from sheet_cutting_layout.services.release_service import cancel_generated_bom

	class BomDoc:
		docstatus = 1
		custom_operation = "Shearing"
		sheet_cutting_layout = "SCL-001"

		def __init__(self) -> None:
			self.name = "BOM-PART001SHR-001"
			self.flags = type("Flags", (), {})()
			self.is_active = 1
			self.disabled = 0

		def cancel(self) -> None:
			raise RuntimeError("BOM is linked with Work Order")

	frappe_stub = _SavepointFrappeStub({"BOM-PART001SHR-001": BomDoc()})
	monkeypatch.setattr(release_service, "frappe", frappe_stub)

	layout = type(
		"Layout",
		(),
		{"doctype": "Sheet Cutting Layout", "name": "SCL-001", "generated_bom": "BOM-PART001SHR-001"},
	)()

	with raises(RuntimeError, match="Work Order"):
		cancel_generated_bom(layout)

	assert len(frappe_stub.db.savepoint_names) == 1
	assert frappe_stub.db.rollback_savepoints == frappe_stub.db.savepoint_names
	assert frappe_stub.db.set_value_calls == []


def test_cancel_generated_bom_rolls_back_savepoint_when_draft_save_fails(
	monkeypatch: MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import release_service
	from sheet_cutting_layout.services.release_service import cancel_generated_bom

	class BomDoc:
		docstatus = 0
		custom_operation = "Shearing"
		sheet_cutting_layout = "SCL-001"

		def __init__(self) -> None:
			self.name = "BOM-PART001SHR-001"
			self.flags = type("Flags", (), {})()
			self.is_active = 1
			self.disabled = 0

		def save(self, ignore_permissions: bool = False) -> None:
			raise RuntimeError("draft BOM save failed")

	frappe_stub = _SavepointFrappeStub({"BOM-PART001SHR-001": BomDoc()})
	monkeypatch.setattr(release_service, "frappe", frappe_stub)

	layout = type(
		"Layout",
		(),
		{"doctype": "Sheet Cutting Layout", "name": "SCL-001", "generated_bom": "BOM-PART001SHR-001"},
	)()

	with raises(RuntimeError, match="draft BOM save failed"):
		cancel_generated_bom(layout)

	assert len(frappe_stub.db.savepoint_names) == 1
	assert frappe_stub.db.rollback_savepoints == frappe_stub.db.savepoint_names
	assert frappe_stub.db.set_value_calls == []


def test_controller_supersede_action_deactivates_generated_bom(monkeypatch: MonkeyPatch) -> None:
	from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import sheet_cutting_layout

	calls: list[object] = []

	monkeypatch.setattr(sheet_cutting_layout, "_get_selected_workflow_action", lambda: "Supersede")
	monkeypatch.setattr(
		sheet_cutting_layout,
		"deactivate_generated_bom",
		lambda layout: calls.append(layout),
	)

	doc = _new_sheet_cutting_layout_doc(sheet_cutting_layout)
	doc.generated_bom = "BOM-PART001SHR-001"
	doc.before_workflow_action()

	assert calls == [doc]


def test_controller_before_cancel_cancels_generated_bom(monkeypatch: MonkeyPatch) -> None:
	from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import sheet_cutting_layout

	calls: list[object] = []
	monkeypatch.setattr(
		sheet_cutting_layout,
		"cancel_generated_bom",
		lambda layout: calls.append(layout),
	)

	doc = _new_sheet_cutting_layout_doc(sheet_cutting_layout)
	doc.status = "Superseded"
	doc.generated_bom = "BOM-PART001SHR-001"
	doc.before_cancel()

	assert calls == [doc]
	assert doc.status == "Cancel"


def test_form_cancel_lets_layout_controller_cancel_linked_bom() -> None:
	content = (
		Path(__file__)
		.resolve()
		.parents[1]
		.joinpath(
			"sheet_cutting_layout",
			"doctype",
			"sheet_cutting_layout",
			"sheet_cutting_layout.js",
		)
		.read_text(encoding="utf-8")
	)

	assert "ignoreBomInGenericCancelAll(frm);" in content
	assert 'frm.ignore_doctypes_on_cancel_all || []), "BOM"' in content


def test_readme_mentions_release_gate_and_bom_qty_parts_per_sheet() -> None:
	content = Path(__file__).resolve().parents[2].joinpath("README.md").read_text(encoding="utf-8")

	assert "BOM quantity equals `parts_per_sheet`" in content
	assert "Draft -> Submitted for Check -> PM Approved -> Approved by Purchase -> Released" in content


class TestReleaseService(SheetCuttingLayoutTestCase):
	pass


add_pytest_style_tests(globals(), TestReleaseService)
