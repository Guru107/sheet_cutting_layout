import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import pytest

import sheet_cutting_layout.hooks as hooks
from sheet_cutting_layout.services.release_service import LayoutImpactResolution, LayoutReleaseStatus
from sheet_cutting_layout.services.versioning import LayoutVersionStatus


@dataclass
class ManufacturingDocument:
	doctype: Literal["Work Order", "Production Plan"]
	name: str
	bom_no: str
	status: str = "Open"


@dataclass
class Layout:
	bom_replacements: dict[str, str]
	status: LayoutReleaseStatus = "Approved by Purchase"
	impact_resolutions: list[LayoutImpactResolution] = field(default_factory=list)
	raw_material_item: str = "RMSHEET001"
	process_scrap_item: str = "PROCESSSCRAP001"
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
	end_piece_item: str
	weight_kg: float
	qty_per_sheet: float


@dataclass
class RevisionLayout:
	name: str
	layout_family: str
	revision_no: int
	status: LayoutVersionStatus
	is_active: bool
	raw_material_item: str = "RM-SHEET-001"
	process_scrap_item: str = "PROCESS-SCRAP-001"
	based_on_layout: str | None = None
	approval_snapshot: list[str] = field(default_factory=list)
	impact_resolutions: list[str] = field(default_factory=list)
	finished_parts: list[FinishedPart] = field(default_factory=list)
	end_pieces: list[EndPiece] = field(default_factory=list)


@dataclass
class Bom:
	name: str
	item: str
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


class FrappeLikeLayout(Layout):
	def __init__(self) -> None:
		super().__init__(bom_replacements={"BOM-OLD-1": "BOM-NEW-1"})
		self.appended_rows: list[dict[str, object]] = []

	def set(self, fieldname: str, value: object) -> None:
		assert fieldname == "impact_resolutions"
		self.impact_resolutions = []
		self.appended_rows = []

	def append(self, fieldname: str, value: dict[str, object]) -> None:
		assert fieldname == "impact_resolutions"
		self.appended_rows.append(value)
		self.impact_resolutions.append(
			LayoutImpactResolution(
				reference_doctype=value["reference_doctype"],
				reference_docname=value["reference_docname"],
				old_bom=value["old_bom"],
				new_bom=value["new_bom"],
				decision=value["decision"],
				decided_by=value["decided_by"],
				decided_on=value["decided_on"],
				status=value["status"],
			)
		)


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
						"Release Pending Impact",
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
			"dt": "Custom Field",
			"filters": [["dt", "in", ["BOM", "Work Order", "Production Plan"]]],
		},
	]

	assert hooks.fixtures == expected_fixtures

	fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures"
	for fixture_file_name in ("workflow_state.json", "workflow.json", "custom_field.json"):
		fixture_path = fixtures_dir / fixture_file_name

		assert fixture_path.exists()
		assert isinstance(json.loads(fixture_path.read_text()), list)


def test_release_creates_impact_rows_when_open_docs_exist() -> None:
	from sheet_cutting_layout.services.release_service import release_layout

	layout = Layout(bom_replacements={"BOM-OLD-1": "BOM-NEW-1"})
	result = release_layout(
		layout,
		open_documents=[
			ManufacturingDocument("Work Order", "WO-001", "BOM-OLD-1"),
			ManufacturingDocument("Production Plan", "PP-001", "BOM-OLD-1"),
		],
	)

	assert result.status == "Release Pending Impact"
	assert layout.status == "Release Pending Impact"
	assert len(result.impact_rows) == 2
	assert result.impact_rows[0].reference_doctype == "Work Order"
	assert result.impact_rows[0].reference_docname == "WO-001"
	assert result.impact_rows[0].old_bom == "BOM-OLD-1"
	assert result.impact_rows[0].new_bom == "BOM-NEW-1"
	assert result.impact_rows[0].decision is None
	assert result.impact_rows[0].decided_by is None
	assert result.impact_rows[0].decided_on is None
	assert result.impact_rows[0].status == "Open"


def test_release_appends_impact_rows_for_frappe_child_tables() -> None:
	from sheet_cutting_layout.services.release_service import release_layout

	layout = FrappeLikeLayout()

	release_layout(
		layout,
		open_documents=[ManufacturingDocument("Work Order", "WO-001", "BOM-OLD-1")],
	)

	assert layout.appended_rows == [
		{
			"reference_doctype": "Work Order",
			"reference_docname": "WO-001",
			"old_bom": "BOM-OLD-1",
			"new_bom": "BOM-NEW-1",
			"decision": None,
			"decided_by": None,
			"decided_on": None,
			"status": "Open",
		}
	]


def test_release_without_impacts_reaches_released() -> None:
	from sheet_cutting_layout.services.release_service import release_layout

	layout = Layout(bom_replacements={"BOM-OLD-1": "BOM-NEW-1"})
	result = release_layout(
		layout,
		open_documents=[
			ManufacturingDocument("Work Order", "WO-001", "BOM-UNRELATED"),
			ManufacturingDocument("Production Plan", "PP-001", "BOM-OLD-1", status="Closed"),
		],
	)

	assert result.status == "Released"
	assert layout.status == "Released"
	assert result.impact_rows == []


def test_release_runs_default_layout_validation() -> None:
	from sheet_cutting_layout.services.release_service import release_layout
	from sheet_cutting_layout.services.validators import frappe

	layout = Layout(
		bom_replacements={},
		finished_parts=[FinishedPart("PART-001SHR")],
	)

	try:
		validation_error = frappe.ValidationError
	except AttributeError:
		validation_error = Exception

	with pytest.raises(validation_error, match="alphanumeric"):
		release_layout(layout, open_documents=[])

	assert layout.status == "Approved by Purchase"


def test_release_allows_injected_validators_for_testability() -> None:
	from sheet_cutting_layout.services.release_service import release_layout

	calls: list[str] = []
	layout = Layout(
		bom_replacements={},
		finished_parts=[FinishedPart("PART-001SHR")],
	)

	release_layout(layout, open_documents=[], validators=[lambda received: calls.append(received.status)])

	assert calls == ["Approved by Purchase"]
	assert layout.status == "Released"


def test_release_requires_process_scrap_item_when_process_scrap_is_positive() -> None:
	from sheet_cutting_layout.services.release_service import release_layout
	from sheet_cutting_layout.services.validators import frappe

	layout = Layout(
		bom_replacements={},
		process_scrap_item="",
		finished_parts=[FinishedPart("PART001SHR", scrap_weight_per_part_kg=0.25)],
	)

	with pytest.raises(frappe.ValidationError, match="Process scrap item"):
		release_layout(layout, open_documents=[])


def test_release_stops_when_injected_validator_fails() -> None:
	from sheet_cutting_layout.services.release_service import release_layout

	def fail_validator(_layout: Layout) -> None:
		raise ValueError("not ready")

	layout = Layout(bom_replacements={})

	with pytest.raises(ValueError, match="not ready"):
		release_layout(layout, open_documents=[], validators=[fail_validator])

	assert layout.status == "Approved by Purchase"
	assert layout.finished_parts[0].generated_bom is None


def test_release_uses_injected_context_provider_when_open_documents_are_not_given() -> None:
	from sheet_cutting_layout.services.release_service import ReleaseContext, release_layout

	layout = Layout(bom_replacements={"BOM-OLD-1": "BOM-NEW-1"})
	context = ReleaseContext(
		open_documents=[ManufacturingDocument("Work Order", "WO-001", "BOM-OLD-1")],
		layouts=[],
		boms=[],
	)
	calls: list[Layout] = []

	result = release_layout(
		layout,
		release_context_provider=lambda received: calls.append(received) or context,
	)

	assert calls == [layout]
	assert result.status == "Release Pending Impact"
	assert result.impact_rows[0].reference_docname == "WO-001"


def test_release_uses_injected_bom_document_factory_for_persisted_boms() -> None:
	from sheet_cutting_layout.services.bom_service import BomDocument
	from sheet_cutting_layout.services.release_service import release_layout

	layout = Layout(bom_replacements={})
	created: list[tuple[Layout, FinishedPart, int]] = []

	def fake_factory(received_layout: Layout, row: FinishedPart, index: int) -> BomDocument:
		created.append((received_layout, row, index))
		return BomDocument(item=row.finished_part_item, name=f"PERSISTED-BOM-{index}")

	result = release_layout(
		layout,
		open_documents=[],
		bom_document_factory=fake_factory,
	)

	assert created == [(layout, layout.finished_parts[0], 1)]
	assert result.generated_boms[0].name == "PERSISTED-BOM-1"
	assert layout.finished_parts[0].generated_bom == "PERSISTED-BOM-1"


def test_generated_boms_remain_pending_until_impact_release_is_finalized() -> None:
	from sheet_cutting_layout.services.release_service import finalize_release, release_layout, resolve_impact

	old_layout = RevisionLayout(
		name="SCL-001",
		layout_family="FAM-001",
		revision_no=1,
		status="Released",
		is_active=True,
		finished_parts=[FinishedPart("PART001LHSHR", generated_bom="BOM-PART001LHSHR-OLD")],
	)
	new_layout = RevisionLayout(
		name="SCL-002",
		layout_family="FAM-001",
		revision_no=2,
		status="Approved by Purchase",
		is_active=False,
		finished_parts=[FinishedPart("PART001LHSHR", gross_weight_per_part_kg=2.5)],
	)
	old_bom = Bom("BOM-PART001LHSHR-OLD", item="PART001LHSHR")
	boms = [old_bom]

	result = release_layout(
		new_layout,
		open_documents=[ManufacturingDocument("Work Order", "WO-001", "BOM-PART001LHSHR-OLD")],
		layouts=[old_layout, new_layout],
		boms=boms,
	)
	new_bom = result.generated_boms[0]

	assert result.status == "Release Pending Impact"
	assert new_bom.is_active is False
	assert new_bom.disabled is True
	assert new_bom.status == "Pending Impact"

	resolve_impact(
		new_layout.impact_resolutions[0],
		decision="Use New BOM",
		decided_by="purchase@example.com",
		decided_on=datetime(2026, 4, 27, 10, 0, 0),
	)
	finalize_release(new_layout, layouts=[old_layout, new_layout], boms=boms)

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
		layout_family="FAM-001",
		revision_no=1,
		status="Released",
		is_active=True,
		finished_parts=[FinishedPart("PART001LHSHR", generated_bom="BOM-PART001LHSHR-OLD")],
	)
	new_layout = SavableRevisionLayout(
		name="SCL-002",
		layout_family="FAM-001",
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
		open_documents=[],
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


def test_controller_mr_release_with_impact_action_calls_release_service(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import sheet_cutting_layout

	calls: list[object] = []
	context = object()

	def fake_release_layout(layout: object, **kwargs: object) -> object:
		calls.append((layout, kwargs))
		return type("ReleaseResult", (), {"status": "Release Pending Impact"})()

	monkeypatch.setattr(
		sheet_cutting_layout,
		"_get_selected_workflow_action",
		lambda: "MR Release With Impact",
	)
	monkeypatch.setattr(sheet_cutting_layout, "get_release_context", lambda layout: context)
	monkeypatch.setattr(sheet_cutting_layout, "release_layout", fake_release_layout)

	doc = sheet_cutting_layout.SheetCuttingLayout()
	doc.before_workflow_action()

	assert calls == [(doc, {"release_context": context})]


def test_controller_mr_release_with_impact_rejects_clean_release(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import sheet_cutting_layout

	class FrappeStub:
		class ValidationError(Exception):
			pass

		@staticmethod
		def throw(message: str) -> None:
			raise FrappeStub.ValidationError(message)

	def fake_release_layout(_layout: object, **_kwargs: object) -> object:
		return type("ReleaseResult", (), {"status": "Released"})()

	monkeypatch.setattr(
		sheet_cutting_layout,
		"_get_selected_workflow_action",
		lambda: "MR Release With Impact",
	)
	monkeypatch.setattr(sheet_cutting_layout, "get_release_context", lambda layout: object())
	monkeypatch.setattr(sheet_cutting_layout, "release_layout", fake_release_layout)
	monkeypatch.setattr(sheet_cutting_layout, "frappe", FrappeStub)

	doc = sheet_cutting_layout.SheetCuttingLayout()

	with pytest.raises(FrappeStub.ValidationError, match="Use MR Release when no open"):
		doc.before_workflow_action()


def test_controller_finalize_impact_release_calls_finalize_with_context(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services.release_service import ReleaseContext
	from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import sheet_cutting_layout

	calls: list[object] = []
	context = ReleaseContext(open_documents=[], layouts=[object()], boms=[])

	def fake_finalize_release(layout: object, **kwargs: object) -> None:
		calls.append((layout, kwargs))

	monkeypatch.setattr(
		sheet_cutting_layout,
		"_get_selected_workflow_action",
		lambda: "Finalize Impact Release",
	)
	monkeypatch.setattr(sheet_cutting_layout, "get_release_context", lambda layout: context)
	monkeypatch.setattr(sheet_cutting_layout, "finalize_release", fake_finalize_release)

	doc = sheet_cutting_layout.SheetCuttingLayout()
	doc.before_workflow_action()

	assert calls == [(doc, {"layouts": context.layouts, "boms": context.boms})]


def test_controller_finalize_impact_release_blocks_unresolved_decisions(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services.release_service import ReleaseContext, ReleaseResult
	from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import sheet_cutting_layout

	class FrappeStub:
		class ValidationError(Exception):
			pass

		@staticmethod
		def throw(message: str) -> None:
			raise FrappeStub.ValidationError(message)

	monkeypatch.setattr(
		sheet_cutting_layout,
		"_get_selected_workflow_action",
		lambda: "Finalize Impact Release",
	)
	monkeypatch.setattr(
		sheet_cutting_layout,
		"get_release_context",
		lambda layout: ReleaseContext(open_documents=[], layouts=[], boms=[]),
	)
	monkeypatch.setattr(
		sheet_cutting_layout,
		"finalize_release",
		lambda *args, **kwargs: ReleaseResult(status="Release Pending Impact"),
	)
	monkeypatch.setattr(sheet_cutting_layout, "frappe", FrappeStub)

	doc = sheet_cutting_layout.SheetCuttingLayout()

	with pytest.raises(FrappeStub.ValidationError, match="Resolve all impact decisions"):
		doc.before_workflow_action()


def test_open_manufacturing_documents_reads_production_plan_item_boms(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import release_service

	class FrappeStub:
		@staticmethod
		def get_all(doctype: str, **kwargs: object) -> list[dict[str, str]]:
			if doctype == "Work Order":
				return [{"name": "WO-001", "bom_no": "BOM-WO", "status": "Not Started"}]
			if doctype == "Production Plan":
				assert kwargs["fields"] == ["name", "status"]
				return [{"name": "PP-001", "status": "Draft"}]
			if doctype == "Production Plan Item":
				assert kwargs["fields"] == ["parent", "bom_no"]
				return [{"parent": "PP-001", "bom_no": "BOM-PP"}]
			raise AssertionError(f"Unexpected doctype {doctype}")

	monkeypatch.setattr(release_service, "frappe", FrappeStub)

	documents = release_service._get_open_manufacturing_documents()

	assert [(doc.doctype, doc.name, doc.bom_no, doc.status) for doc in documents] == [
		("Work Order", "WO-001", "BOM-WO", "Not Started"),
		("Production Plan", "PP-001", "BOM-PP", "Draft"),
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
			self.name = self.name or "BOM-PERSISTED"

	class FrappeStub:
		@staticmethod
		def new_doc(doctype: str) -> FrappeBom:
			assert doctype == "BOM"
			return FrappeBom()

	bom = BomDocument(item="PART001SHR", name="BOM-PART001SHR")
	bom._layout = type("LayoutWithCompany", (), {"company": "Test Company"})()
	monkeypatch.setattr(release_service, "frappe", FrappeStub)

	inserted = release_service._insert_frappe_bom(bom)

	assert inserted.name == "BOM-PART001SHR"


def test_release_requires_context_when_provider_returns_none() -> None:
	from sheet_cutting_layout.services.release_service import release_layout

	with pytest.raises(RuntimeError, match="Release requires open"):
		release_layout(Layout(bom_replacements={}), release_context_provider=lambda _layout: None)


def test_get_release_context_uses_test_fallback_when_frappe_is_unavailable(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import release_service

	monkeypatch.setattr(release_service, "frappe", None)
	monkeypatch.setattr(release_service, "_is_test_runtime", lambda: True)

	context = release_service.get_release_context(Layout(bom_replacements={}))

	assert context.open_documents == ()
	assert context.layouts == ()
	assert context.boms == []


def test_get_release_context_requires_frappe_outside_tests(monkeypatch: pytest.MonkeyPatch) -> None:
	from sheet_cutting_layout.services import release_service

	monkeypatch.setattr(release_service, "frappe", None)
	monkeypatch.setattr(release_service, "_is_test_runtime", lambda: False)

	with pytest.raises(RuntimeError, match="Frappe is required"):
		release_service.get_release_context(Layout(bom_replacements={}))


def test_release_context_discovers_layouts_boms_and_open_documents(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import release_service

	class FrappeStub:
		@staticmethod
		def get_all(doctype: str, **kwargs: object) -> list[object]:
			if doctype == "Work Order":
				return [type("Row", (), {"name": "WO-001", "bom_no": "BOM-WO", "status": "Open"})()]
			if doctype == "Production Plan":
				return [{"name": "PP-001", "status": "Draft"}]
			if doctype == "Production Plan Item":
				return [{"parent": "PP-001", "bom_no": "BOM-PP"}]
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
		layout_family="FAM-001",
		revision_no=2,
		status="Approved by Purchase",
		is_active=False,
		finished_parts=[FinishedPart("PART001SHR")],
	)
	monkeypatch.setattr(release_service, "frappe", FrappeStub)

	context = release_service.get_release_context(layout)

	assert [(doc.doctype, doc.name, doc.bom_no) for doc in context.open_documents] == [
		("Work Order", "WO-001", "BOM-WO"),
		("Production Plan", "PP-001", "BOM-PP"),
	]
	assert [getattr(doc, "name", None) for doc in context.layouts] == ["SCL-OLD", "SCL-NEW"]
	assert [getattr(doc, "name", None) for doc in context.boms or []] == ["BOM-OLD"]


def test_release_context_handles_layout_without_family_or_finished_parts(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from sheet_cutting_layout.services import release_service

	class FrappeStub:
		@staticmethod
		def get_all(doctype: str, **_kwargs: object) -> list[object]:
			if doctype in {"Work Order", "Production Plan"}:
				return []
			raise AssertionError(f"Unexpected doctype {doctype}")

	layout = type(
		"LayoutWithoutFamily",
		(),
		{
			"layout_family": "",
			"finished_parts": [],
		},
	)()
	monkeypatch.setattr(release_service, "frappe", FrappeStub)

	context = release_service.get_release_context(layout)

	assert context.layouts == [layout]
	assert context.boms == []


def test_release_context_skips_empty_production_plan_result(monkeypatch: pytest.MonkeyPatch) -> None:
	from sheet_cutting_layout.services import release_service

	class FrappeStub:
		@staticmethod
		def get_all(doctype: str, **_kwargs: object) -> list[object]:
			assert doctype == "Production Plan"
			return []

	monkeypatch.setattr(release_service, "frappe", FrappeStub)

	assert release_service._get_open_production_plans() == []


def test_release_helpers_raise_without_frappe(monkeypatch: pytest.MonkeyPatch) -> None:
	from sheet_cutting_layout.services import release_service

	monkeypatch.setattr(release_service, "frappe", None)

	with pytest.raises(RuntimeError, match="open manufacturing"):
		release_service._get_open_manufacturing_documents()
	with pytest.raises(RuntimeError, match="work orders"):
		release_service._get_open_work_orders()
	with pytest.raises(RuntimeError, match="production plans"):
		release_service._get_open_production_plans()
	with pytest.raises(RuntimeError, match="same-family"):
		release_service._get_same_family_layouts(Layout(bom_replacements={}))
	with pytest.raises(RuntimeError, match="BOM records"):
		release_service._get_finished_part_boms(Layout(bom_replacements={}))


def test_unsupported_impact_doctype_raises() -> None:
	from sheet_cutting_layout.services import release_service

	with pytest.raises(ValueError, match="Unsupported impact"):
		release_service._impact_doctype("Sales Order")


def test_default_bom_factory_requires_frappe_outside_tests(monkeypatch: pytest.MonkeyPatch) -> None:
	from sheet_cutting_layout.services import release_service

	layout = Layout(bom_replacements={})
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


def test_finalize_waits_until_all_impact_decisions_are_present() -> None:
	from sheet_cutting_layout.services.release_service import finalize_release, release_layout, resolve_impact

	layout = Layout(bom_replacements={"BOM-OLD-1": "BOM-NEW-1"})
	release_layout(
		layout,
		open_documents=[
			ManufacturingDocument("Work Order", "WO-001", "BOM-OLD-1"),
			ManufacturingDocument("Production Plan", "PP-001", "BOM-OLD-1"),
		],
	)
	resolve_impact(
		layout.impact_resolutions[0],
		decision="Use New BOM",
		decided_by="purchase@example.com",
		decided_on=datetime(2026, 4, 27, 10, 0, 0),
	)

	result = finalize_release(layout)

	assert result.status == "Release Pending Impact"
	assert layout.status == "Release Pending Impact"
	assert result.impact_rows[0].status == "Resolved"
	assert result.impact_rows[1].status == "Open"


def test_finalize_completes_when_all_impact_decisions_are_present() -> None:
	from sheet_cutting_layout.services.release_service import finalize_release, release_layout, resolve_impact

	layout = Layout(bom_replacements={"BOM-OLD-1": "BOM-NEW-1"})
	release_layout(
		layout,
		open_documents=[
			ManufacturingDocument("Work Order", "WO-001", "BOM-OLD-1"),
			ManufacturingDocument("Production Plan", "PP-001", "BOM-OLD-1"),
		],
	)
	for impact_row in layout.impact_resolutions:
		resolve_impact(
			impact_row,
			decision="Use New BOM",
			decided_by="purchase@example.com",
			decided_on=datetime(2026, 4, 27, 10, 0, 0),
		)

	result = finalize_release(layout)

	assert result.status == "Released"
	assert layout.status == "Released"
	assert {impact_row.status for impact_row in result.impact_rows} == {"Resolved"}


def test_finalize_after_impact_decisions_runs_revision_and_bom_activation() -> None:
	from sheet_cutting_layout.services.release_service import finalize_release, release_layout, resolve_impact

	old_layout = RevisionLayout(
		name="SCL-001",
		layout_family="FAM-001",
		revision_no=1,
		status="Released",
		is_active=True,
		finished_parts=[FinishedPart("PART001LHSHR", generated_bom="BOM-PART001LHSHR-OLD")],
	)
	new_layout = RevisionLayout(
		name="SCL-002",
		layout_family="FAM-001",
		revision_no=2,
		status="Approved by Purchase",
		is_active=False,
		finished_parts=[FinishedPart("PART001LHSHR", gross_weight_per_part_kg=2.5)],
	)
	old_bom = Bom("BOM-PART001LHSHR-OLD", item="PART001LHSHR")
	boms = [old_bom]
	release_layout(
		new_layout,
		open_documents=[ManufacturingDocument("Work Order", "WO-001", "BOM-PART001LHSHR-OLD")],
		layouts=[old_layout, new_layout],
		boms=boms,
	)
	new_bom = boms[-1]
	resolve_impact(
		new_layout.impact_resolutions[0],
		decision="Use New BOM",
		decided_by="purchase@example.com",
		decided_on=datetime(2026, 4, 27, 10, 0, 0),
	)

	result = finalize_release(new_layout, layouts=[old_layout, new_layout], boms=boms)

	assert result.status == "Released"
	assert result.superseded_layout is old_layout
	assert old_layout.status == "Superseded"
	assert old_layout.is_active is False
	assert new_layout.is_active is True
	assert old_bom.is_active is False
	assert old_bom.disabled is True
	assert old_bom.status == "Superseded"
	assert new_bom.is_active is True
	assert new_bom.disabled is False
	assert new_bom.status == "Active"


def test_revising_released_layout_clones_and_increments_revision() -> None:
	from sheet_cutting_layout.services.versioning import create_revision

	old_layout = RevisionLayout(
		name="SCL-001",
		layout_family="FAM-001",
		revision_no=2,
		status="Released",
		is_active=True,
	)

	new_layout = create_revision(old_layout)

	assert new_layout is not old_layout
	assert new_layout.revision_no == 3
	assert new_layout.status == "Draft"
	assert new_layout.based_on_layout == "SCL-001"
	assert new_layout.is_active is False


def test_revision_resets_approval_snapshot_impact_rows_and_generated_boms() -> None:
	from sheet_cutting_layout.services.versioning import create_revision

	old_layout = RevisionLayout(
		name="SCL-001",
		layout_family="FAM-001",
		revision_no=1,
		status="Released",
		is_active=True,
		approval_snapshot=["purchase-approved"],
		impact_resolutions=["WO-001"],
		finished_parts=[
			FinishedPart("PART001SHR", generated_bom="BOM-PART-001-001"),
			FinishedPart("PART002SHR", generated_bom="BOM-PART-002-001"),
		],
	)

	new_layout = create_revision(old_layout)

	assert new_layout.approval_snapshot == []
	assert new_layout.impact_resolutions == []
	assert [row.generated_bom for row in new_layout.finished_parts] == [None, None]
	assert [row.generated_bom for row in old_layout.finished_parts] == [
		"BOM-PART-001-001",
		"BOM-PART-002-001",
	]


def test_finalizing_new_revision_supersedes_previous_active_layout() -> None:
	from sheet_cutting_layout.services.versioning import finalize_new_revision_release

	old_layout = RevisionLayout(
		name="SCL-001",
		layout_family="FAM-001",
		revision_no=1,
		status="Released",
		is_active=True,
	)
	other_family_layout = RevisionLayout(
		name="SCL-OTHER",
		layout_family="FAM-OTHER",
		revision_no=1,
		status="Released",
		is_active=True,
	)
	new_layout = RevisionLayout(
		name="SCL-002",
		layout_family="FAM-001",
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
		layout_family="FAM-001",
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
		layout_family="FAM-001",
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
		layout_family="FAM-001",
		revision_no=1,
		status="Released",
		is_active=True,
		finished_parts=[FinishedPart("PART001SHR", generated_bom="BOM-PART-001-OLD")],
	)
	new_layout = RevisionLayout(
		name="SCL-002",
		layout_family="FAM-001",
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


def test_release_generates_two_boms_for_lh_rh_and_supersedes_old() -> None:
	from sheet_cutting_layout.services.release_service import release_layout

	old_layout = RevisionLayout(
		name="SCL-001",
		layout_family="FAM-001",
		revision_no=1,
		status="Released",
		is_active=True,
		finished_parts=[
			FinishedPart("PART001LHSHR", generated_bom="BOM-PART001LHSHR-OLD"),
			FinishedPart("PART001RHSHR", generated_bom="BOM-PART001RHSHR-OLD"),
		],
	)
	new_layout = RevisionLayout(
		name="SCL-002",
		layout_family="FAM-001",
		revision_no=2,
		status="Approved by Purchase",
		is_active=False,
		finished_parts=[
			FinishedPart("PART001LHSHR", gross_weight_per_part_kg=2.5, scrap_weight_per_part_kg=0.2),
			FinishedPart("PART001RHSHR", gross_weight_per_part_kg=2.5, scrap_weight_per_part_kg=0.2),
		],
	)
	old_lh_bom = Bom("BOM-PART001LHSHR-OLD", item="PART001LHSHR")
	old_rh_bom = Bom("BOM-PART001RHSHR-OLD", item="PART001RHSHR")

	result = release_layout(
		new_layout, open_documents=[], layouts=[old_layout, new_layout], boms=[old_lh_bom, old_rh_bom]
	)

	assert result.status == "Released"
	assert len(result.generated_boms) == 2
	assert [bom.item for bom in result.generated_boms] == ["PART001LHSHR", "PART001RHSHR"]
	assert [bom.quantity for bom in result.generated_boms] == [1, 1]
	assert [
		[(item.item_code, item.qty, item.row_type) for item in bom.items] for bom in result.generated_boms
	] == [
		[("RM-SHEET-001", 2.5, "raw_material"), ("PROCESS-SCRAP-001", 0.2, "process_scrap")],
		[("RM-SHEET-001", 2.5, "raw_material"), ("PROCESS-SCRAP-001", 0.2, "process_scrap")],
	]
	assert [row.generated_bom for row in new_layout.finished_parts] == [
		result.generated_boms[0].name,
		result.generated_boms[1].name,
	]
	assert result.superseded_layout is old_layout
	assert old_layout.status == "Superseded"
	assert old_layout.is_active is False
	assert old_lh_bom.is_active is False
	assert old_lh_bom.disabled is True
	assert old_lh_bom.status == "Superseded"
	assert old_rh_bom.is_active is False
	assert old_rh_bom.disabled is True
	assert old_rh_bom.status == "Superseded"
	assert all(bom.is_active is True for bom in result.generated_boms)
	assert all(bom.disabled is False for bom in result.generated_boms)
	assert all(bom.status == "Active" for bom in result.generated_boms)


def test_readme_mentions_release_gate_and_bom_qty_one() -> None:
	content = Path("README.md").read_text(encoding="utf-8")

	assert "BOM quantity is always 1" in content
	assert "Release Pending Impact" in content
