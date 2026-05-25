import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import ClassVar

import pytest

import sheet_cutting_layout.hooks as hooks
from sheet_cutting_layout.services.release_service import LayoutReleaseStatus
from sheet_cutting_layout.services.versioning import LayoutVersionStatus


@dataclass
class Layout:
	name: str = "SCL-NEW"
	project: str = "PROJECT-001"
	status: LayoutReleaseStatus = "Approved by Purchase"
	raw_material_item: str = "RMSHEET001"
	process_scrap_item: str = "PROCESSSCRAP001"
	no_of_strips: int = 11
	weight_per_sheet_kg: float | None = None
	consumed_weight_kg: float | None = None
	leftover_weight_kg: float | None = None
	consumption_status: str | None = None
	finished_parts: list["FinishedPart"] = field(default_factory=lambda: [FinishedPart("PART001SHR")])
	end_pieces: list["EndPiece"] = field(default_factory=list)


@dataclass
class FinishedPart:
	finished_part_item: str
	parts_per_sheet: int = 1
	gross_weight_per_part_kg: float = 1.0
	scrap_weight_per_part_kg: float = 0.0
	generated_bom: str | None = None


@dataclass
class EndPiece:
	weight_kg: float
	qty_per_sheet: float = 1
	disposition: str = "Reuse"
	scrap_item: str | None = None


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
						"Checked",
						"Approved by Purchase",
						"Released",
						"Rejected",
						"Superseded",
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
			"filters": [["name", "in", ["Projects Manager", "Manufacturing Manager", "MR Coordinator"]]],
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
			"validate": "sheet_cutting_layout.overrides.bom.validate_shearing_bom_source",
		}
	}

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


def test_release_reaches_released() -> None:
	from sheet_cutting_layout.services.release_service import release_layout

	layout = Layout()
	result = release_layout(layout)

	assert result.status == "Released"
	assert layout.status == "Released"


def test_release_runs_default_layout_validation() -> None:
	from sheet_cutting_layout.services.release_service import release_layout
	from sheet_cutting_layout.services.validators import frappe

	layout = Layout(finished_parts=[FinishedPart("PART-001SHR")])

	try:
		validation_error = frappe.ValidationError
	except AttributeError:
		validation_error = Exception

	with pytest.raises(validation_error, match="alphanumeric"):
		release_layout(layout)

	assert layout.status == "Approved by Purchase"


def test_release_allows_injected_validators_for_testability() -> None:
	from sheet_cutting_layout.services.release_service import release_layout

	calls: list[str] = []
	layout = Layout(finished_parts=[FinishedPart("PART-001SHR")])

	release_layout(layout, validators=[lambda received: calls.append(received.status)])

	assert calls == ["Approved by Purchase"]
	assert layout.status == "Released"


def test_release_requires_process_scrap_item_when_process_scrap_is_positive() -> None:
	from sheet_cutting_layout.services.release_service import release_layout
	from sheet_cutting_layout.services.validators import frappe

	layout = Layout(
		process_scrap_item="",
		finished_parts=[FinishedPart("PART001SHR", scrap_weight_per_part_kg=0.25)],
	)

	with pytest.raises(frappe.ValidationError, match="Process scrap item"):
		release_layout(layout)


def test_release_stops_when_injected_validator_fails() -> None:
	from sheet_cutting_layout.services.release_service import release_layout

	def fail_validator(_layout: Layout) -> None:
		raise ValueError("not ready")

	layout = Layout()

	with pytest.raises(ValueError, match="not ready"):
		release_layout(layout, validators=[fail_validator])

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
	)

	assert calls == [layout]
	assert result.status == "Released"


def test_release_uses_injected_bom_document_factory_for_persisted_boms() -> None:
	from sheet_cutting_layout.services.bom_service import BomDocument
	from sheet_cutting_layout.services.release_service import release_layout

	layout = Layout()
	created: list[tuple[Layout, FinishedPart, int]] = []

	def fake_factory(received_layout: Layout, row: FinishedPart, index: int) -> BomDocument:
		created.append((received_layout, row, index))
		return BomDocument(item=row.finished_part_item, name=f"PERSISTED-BOM-{index}")

	result = release_layout(
		layout,
		bom_document_factory=fake_factory,
	)

	assert created == [(layout, layout.finished_parts[0], 1)]
	assert result.generated_boms[0].name == "PERSISTED-BOM-1"
	assert layout.finished_parts[0].generated_bom == "PERSISTED-BOM-1"


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
	)

	bom = result.generated_boms[0]
	assert bom.item == "PART001SHR"
	assert bom.quantity == 11
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
	)
	new_bom = result.generated_boms[0]

	assert result.status == "Released"
	assert new_bom.is_active is True
	assert new_bom.disabled is False
	assert new_bom.status == "Active"


def test_release_persists_superseded_layouts_when_frappe_is_available(
	monkeypatch: pytest.MonkeyPatch,
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

	assert old_layout.status == "Superseded"
	assert old_layout.save_calls == 1
	assert new_layout.status == "Released"
	assert new_layout.save_calls == 1


def test_release_supersedes_submitted_layouts_with_db_set(
	monkeypatch: pytest.MonkeyPatch,
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

	assert old_layout.status == "Superseded"
	assert old_layout.is_active is False
	assert old_layout.save_calls == 0
	assert old_layout.db_set_calls == [({"status": "Superseded", "is_active": False}, True, False)]


def test_controller_mr_release_action_calls_release_service_with_release_context(
	monkeypatch: pytest.MonkeyPatch,
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

	doc = sheet_cutting_layout.SheetCuttingLayout()
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
	monkeypatch: pytest.MonkeyPatch,
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
			related_layout = sheet_cutting_layout.SheetCuttingLayout()
			related_layout.approval_snapshot = []
			related_layout.validate()
		return type("ReleaseResult", (), {"status": "Released"})()

	monkeypatch.setattr(sheet_cutting_layout, "frappe", FrappeStub)
	monkeypatch.setattr(sheet_cutting_layout, "get_release_context", lambda layout: context)
	monkeypatch.setattr(sheet_cutting_layout, "release_layout", fake_release_layout)
	monkeypatch.setattr(sheet_cutting_layout, "validate_sheet_cutting_layout", lambda _doc: None)

	doc = sheet_cutting_layout.SheetCuttingLayout()
	doc.approval_snapshot = []

	doc.before_workflow_action()

	assert calls == [(doc, {"release_context": context})]


def test_controller_validate_applies_workflow_side_effects_and_records_snapshot(
	monkeypatch: pytest.MonkeyPatch,
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
		lambda: "Projects Manager Approves",
	)
	monkeypatch.setattr(sheet_cutting_layout, "frappe", FrappeStub)
	monkeypatch.setattr(sheet_cutting_layout, "validate_sheet_cutting_layout", lambda _doc: None)

	doc = sheet_cutting_layout.SheetCuttingLayout()
	doc.project_manager_ok = False
	doc.manufacturing_manager_ok = False
	doc.approval_snapshot = []

	doc.validate()

	assert doc.project_manager_ok is True
	assert len(doc.approval_snapshot) == 1
	assert doc.approval_snapshot[0]["step_name"] == "Projects Manager Approval"
	assert doc.approval_snapshot[0]["approver"] == "projects@example.com"
	assert doc.approval_snapshot[0]["decision"] == "Approved"
	assert doc.approval_snapshot[0]["decision_time"] == datetime(2026, 5, 15, 9, 30, 0)


def test_controller_validate_records_submit_for_check_snapshot(
	monkeypatch: pytest.MonkeyPatch,
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

	doc = sheet_cutting_layout.SheetCuttingLayout()
	doc.approval_snapshot = []

	doc.validate()

	assert len(doc.approval_snapshot) == 1
	assert doc.approval_snapshot[0]["step_name"] == "Submit for Check"
	assert doc.approval_snapshot[0]["approver"] == "system@example.com"
	assert doc.approval_snapshot[0]["decision"] == "Submitted"
	assert doc.approval_snapshot[0]["decision_time"] == datetime(2026, 5, 15, 10, 0, 0)


def test_workflow_wrapper_sets_selected_action_for_sheet_cutting_layout(
	monkeypatch: pytest.MonkeyPatch,
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
	from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import sheet_cutting_layout

	assert getattr(sheet_cutting_layout.apply_sheet_cutting_layout_workflow, "whitelisted", False) is True


def test_rejected_layout_on_trash_removes_workflow_action_links(
	monkeypatch: pytest.MonkeyPatch,
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

	doc = sheet_cutting_layout.SheetCuttingLayout()
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
	monkeypatch: pytest.MonkeyPatch,
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

	doc = sheet_cutting_layout.SheetCuttingLayout()
	doc.name = "SCL-RELEASED"
	doc.status = "Released"

	doc.on_trash()

	assert deletions == []


def test_patch_repairs_submitted_layouts_with_both_checker_flags(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from sheet_cutting_layout.patches import v1_0_repair_checked_workflow_state

	class DbStub:
		calls: ClassVar[list[tuple[str, str, str, dict[str, object], str | None]]] = []

		@classmethod
		def set_value(
			cls,
			doctype: str,
			filters: dict[str, object],
			fieldname: str,
			value: str,
			update_modified: bool = False,
		) -> None:
			cls.calls.append((doctype, fieldname, value, filters, str(update_modified)))

	class FrappeStub:
		db = DbStub

	monkeypatch.setattr(v1_0_repair_checked_workflow_state, "frappe", FrappeStub)

	v1_0_repair_checked_workflow_state.execute()

	assert DbStub.calls == [
		(
			"Sheet Cutting Layout",
			"status",
			"Checked",
			{
				"status": "Submitted for Check",
				"project_manager_ok": 1,
				"manufacturing_manager_ok": 1,
			},
			"False",
		)
	]


def test_patch_submits_existing_released_layouts(
	monkeypatch: pytest.MonkeyPatch,
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
	monkeypatch: pytest.MonkeyPatch,
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


def test_patch_backfills_missing_mr_approval_snapshots(
	monkeypatch: pytest.MonkeyPatch,
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
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import release_service
	from sheet_cutting_layout.services.bom_service import BomDocument

	class FrappeBom:
		def __init__(self) -> None:
			self.name = ""
			self.items: list[dict[str, object]] = []

		def append(self, fieldname: str, row: dict[str, object]) -> None:
			assert fieldname == "items"
			self.items.append(row)

		def insert(self) -> None:
			assert self.company == "Test Company"
			assert self.custom_operation == "Shearing"
			assert self.sheet_cutting_layout == "SCL-001"
			self.name = self.name or "BOM-PERSISTED"

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


def test_get_release_context_uses_test_fallback_when_frappe_is_unavailable(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import release_service

	monkeypatch.setattr(release_service, "frappe", None)
	monkeypatch.setattr(release_service, "_is_test_runtime", lambda: True)

	context = release_service.get_release_context(Layout())

	assert context.layouts == ()
	assert context.boms == []


def test_get_release_context_requires_frappe_outside_tests(monkeypatch: pytest.MonkeyPatch) -> None:
	from sheet_cutting_layout.services import release_service

	monkeypatch.setattr(release_service, "frappe", None)
	monkeypatch.setattr(release_service, "_is_test_runtime", lambda: False)

	with pytest.raises(RuntimeError, match="Frappe is required"):
		release_service.get_release_context(Layout())


def test_release_context_discovers_layouts_and_boms(
	monkeypatch: pytest.MonkeyPatch,
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
	monkeypatch: pytest.MonkeyPatch,
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


def test_release_helpers_raise_without_frappe(monkeypatch: pytest.MonkeyPatch) -> None:
	from sheet_cutting_layout.services import release_service

	monkeypatch.setattr(release_service, "frappe", None)

	with pytest.raises(RuntimeError, match="BOM records"):
		release_service._get_finished_part_boms(Layout())


def test_default_bom_factory_requires_frappe_outside_tests(monkeypatch: pytest.MonkeyPatch) -> None:
	from sheet_cutting_layout.services import release_service

	layout = Layout()
	finished_part = layout.finished_parts[0]
	monkeypatch.setattr(release_service, "frappe", None)
	monkeypatch.setattr(release_service, "_is_test_runtime", lambda: False)

	with pytest.raises(RuntimeError, match="persist generated BOM"):
		release_service._default_bom_document_factory(layout, finished_part, 1, None)


def test_company_resolution_uses_defaults_and_errors_when_missing(
	monkeypatch: pytest.MonkeyPatch,
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
	with pytest.raises(NoCompany.ValidationError, match="Company is required"):
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
		finished_parts=[
			FinishedPart("PART001SHR", generated_bom="BOM-PART-001-001"),
			FinishedPart("PART002SHR", generated_bom="BOM-PART-002-001"),
		],
	)

	new_layout = create_revision(old_layout)

	assert new_layout.approval_snapshot == []
	assert [row.generated_bom for row in new_layout.finished_parts] == [None, None]
	assert [row.generated_bom for row in old_layout.finished_parts] == [
		"BOM-PART-001-001",
		"BOM-PART-002-001",
	]


def test_finalizing_new_revision_supersedes_previous_active_layout() -> None:
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

	assert old_layout.status == "Superseded"
	assert old_layout.is_active is False
	assert new_layout.status == "Released"
	assert new_layout.is_active is True
	assert other_family_layout.status == "Released"
	assert other_family_layout.is_active is True


def test_finalizing_new_revision_disables_old_boms_for_affected_finished_parts() -> None:
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

	assert old_bom.is_active is False
	assert old_bom.disabled is True
	assert old_bom.status == "Superseded"
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

	assert old_linked_bom.is_active is False
	assert old_linked_bom.disabled is True
	assert old_linked_bom.status == "Superseded"
	assert unlinked_same_item_bom.is_active is True
	assert unlinked_same_item_bom.disabled is False
	assert unlinked_same_item_bom.status == "Active"
	assert new_bom.is_active is True
	assert new_bom.disabled is False
	assert new_bom.status == "Active"


def test_release_generates_one_bom_for_single_finished_part_and_supersedes_old() -> None:
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

	result = release_layout(new_layout, layouts=[old_layout, new_layout], boms=[old_bom])

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
	assert [row.generated_bom for row in new_layout.finished_parts] == [result.generated_boms[0].name]
	assert result.superseded_layout is old_layout
	assert old_layout.status == "Superseded"
	assert old_layout.is_active is False
	assert old_bom.is_active is False
	assert old_bom.disabled is True
	assert old_bom.status == "Superseded"
	assert all(bom.is_active is True for bom in result.generated_boms)
	assert all(bom.disabled is False for bom in result.generated_boms)
	assert all(bom.status == "Active" for bom in result.generated_boms)


def test_readme_mentions_release_gate_and_bom_qty_no_of_strips() -> None:
	content = Path("README.md").read_text(encoding="utf-8")

	assert "BOM quantity equals `no_of_strips`" in content
	assert "MR release moves layouts directly to `Released`" in content
