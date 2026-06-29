import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import frappe

import sheet_cutting_layout.hooks as hooks
from sheet_cutting_layout.services import release_service
from sheet_cutting_layout.services.release_service import LayoutWorkflowStatus as ReleaseWorkflowStatus
from sheet_cutting_layout.services.versioning import LayoutWorkflowStatus as VersionWorkflowStatus
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase
from sheet_cutting_layout.tests.factories import (
	make_layout,
	make_release_ready_layout,
)


@dataclass
class Layout:
	name: str = "SCL-NEW"
	project: str = "PROJECT-001"
	workflow_status: ReleaseWorkflowStatus = "Approved by Purchase"
	raw_material_item: str = "RMSHEET001"
	process_scrap_item: str = "PROCESSSCRAP001"
	no_of_strips: int = 11
	finished_part_code: str = "PART001SHR"
	net_weight_per_part_kg: float = 1.0
	gross_weight_per_part_kg: float = 1.0
	scrap_weight_per_part_kg: float = 0.0
	generated_bom: str | None = None
	twin_generated_bom: str | None = None
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

	def as_dict(self) -> dict[str, object]:
		return {
			"doctype": "Layout Finished Part",
			"finished_part_item": self.finished_part_item,
			"parts_per_sheet": self.parts_per_sheet,
			"gross_weight_per_part_kg": self.gross_weight_per_part_kg,
			"scrap_weight_per_part_kg": self.scrap_weight_per_part_kg,
			"generated_bom": self.generated_bom,
			"bom_quantity": self.bom_quantity,
			"scrap_weight_kg": self.scrap_weight_kg,
			"raw_material_weight_kg": self.raw_material_weight_kg,
		}


@dataclass
class EndPiece:
	weight_kg: float
	strip_weight_kg: float | None = None
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
	generated_end_piece_bom: str | None = None

	def as_dict(self) -> dict[str, object]:
		return {
			"doctype": "Layout End Piece",
			"weight_kg": self.weight_kg,
			"strip_weight_kg": self.strip_weight_kg,
			"disposition": self.disposition,
			"scrap_item": self.scrap_item,
			"end_piece_item_code": self.end_piece_item_code,
			"used_for_finished_part": self.used_for_finished_part,
			"width_mm": self.width_mm,
			"length_mm": self.length_mm,
			"idx": self.idx,
			"bom_quantity": self.bom_quantity,
			"net_weight_per_part_kg": self.net_weight_per_part_kg,
			"gross_weight_per_part_kg": self.gross_weight_per_part_kg,
			"scrap_weight_per_part_kg": self.scrap_weight_per_part_kg,
			"bom_scrap_quantity_kg": self.bom_scrap_quantity_kg,
			"generated_end_piece_bom": self.generated_end_piece_bom,
		}


@dataclass
class RevisionLayout:
	name: str
	project: str
	revision_no: int
	workflow_status: VersionWorkflowStatus
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
	twin_generated_bom: str | None = None
	parts_per_sheet: int = 1
	end_piece_bom_status: str = ""

	def __post_init__(self) -> None:
		if self.finished_parts:
			self.finished_part_code = self.finished_parts[0].finished_part_item
			self.parts_per_sheet = self.finished_parts[0].parts_per_sheet
			self.gross_weight_per_part_kg = self.finished_parts[0].gross_weight_per_part_kg
			self.scrap_weight_per_part_kg = self.finished_parts[0].scrap_weight_per_part_kg
		self.net_weight_per_part_kg = self.gross_weight_per_part_kg - self.scrap_weight_per_part_kg

	def as_dict(self) -> dict[str, object]:
		return {
			"doctype": "Sheet Cutting Layout",
			"name": self.name,
			"project": self.project,
			"revision_no": self.revision_no,
			"workflow_status": self.workflow_status,
			"is_active": self.is_active,
			"layout_code": self.layout_code,
			"raw_material_item": self.raw_material_item,
			"process_scrap_item": self.process_scrap_item,
			"weight_per_sheet_kg": self.weight_per_sheet_kg,
			"based_on_layout": self.based_on_layout,
			"approval_snapshot": [
				{
					"doctype": "Layout Approval Snapshot",
					"step_name": str(row),
				}
				for row in self.approval_snapshot
			],
			"finished_parts": [row.as_dict() for row in self.finished_parts],
			"end_pieces": [row.as_dict() for row in self.end_pieces],
			"finished_part_code": self.finished_part_code,
			"net_weight_per_part_kg": self.net_weight_per_part_kg,
			"gross_weight_per_part_kg": self.gross_weight_per_part_kg,
			"scrap_weight_per_part_kg": self.scrap_weight_per_part_kg,
			"generated_bom": self.generated_bom,
			"twin_generated_bom": self.twin_generated_bom,
			"parts_per_sheet": self.parts_per_sheet,
			"end_piece_bom_status": self.end_piece_bom_status,
		}


@dataclass
class Bom:
	name: str
	item: str
	custom_operation: str | None = "Shearing"
	sheet_cutting_layout: str | None = None
	is_active: bool = True


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


class _SavableBomFrappeStub:
	"""Minimal frappe stand-in whose get_doc returns a BOM with a no-op save."""

	@staticmethod
	def get_doc(_doctype: str, name: str) -> object:
		return type("SavableBom", (), {"name": name, "save": lambda self, **kwargs: None})()


class ReleaseServiceIsolatedTestCase(SheetCuttingLayoutTestCase):
	"""Keep unit-style tests deterministic under bench by disabling live persistence paths."""

	def setUp(self) -> None:
		super().setUp()
		self.start_patcher(patch.object(release_service, "frappe", new=_SavableBomFrappeStub))


class TestReleaseContracts(SheetCuttingLayoutTestCase):
	def test_hooks_exposes_required_fixtures(self) -> None:
		assert hooks.doc_events == {
			"BOM": {
				"before_insert": "sheet_cutting_layout.overrides.bom.validate_shearing_bom_source",
				"before_cancel": "sheet_cutting_layout.overrides.bom.validate_shearing_bom_source",
			}
		}
		assert hooks.before_tests == "sheet_cutting_layout.tests.test_setup.before_tests"

		fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures"
		for fixture_file_name in (
			"workflow_state.json",
			"workflow_action_master.json",
			"workflow.json",
			"role.json",
		):
			fixture_path = fixtures_dir / fixture_file_name

			assert fixture_path.exists()
			assert isinstance(json.loads(fixture_path.read_text()), list)

	def test_workflow_action_masters_cover_transition_actions(self) -> None:
		fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures"
		workflow = json.loads((fixtures_dir / "workflow.json").read_text(encoding="utf-8"))[0]
		action_masters = json.loads(
			(fixtures_dir / "workflow_action_master.json").read_text(encoding="utf-8")
		)

		transition_actions = {transition["action"] for transition in workflow["transitions"]}
		fixture_actions = {row["workflow_action_name"] for row in action_masters}

		assert len(action_masters) == len(fixture_actions)
		assert len(action_masters) == len({row["name"] for row in action_masters})
		assert fixture_actions == transition_actions

	def test_parent_finished_part_code_is_item_link(self) -> None:
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

	def test_status_options_use_superseded_as_cancel_state(self) -> None:
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
				(Path(__file__).resolve().parents[1] / "fixtures" / "workflow.json").read_text(
					encoding="utf-8"
				)
			)[0]["states"]
		}

		workflow_status_options = fields["workflow_status"]["options"].splitlines()
		assert "Cancel" not in workflow_status_options
		assert "Superseded" in workflow_status_options
		assert workflow_states["Superseded"]["doc_status"] == "2"
		assert "Cancel" not in workflow_states

	def test_workflow_status_fields_are_hidden_from_users(self) -> None:
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

		assert fields["workflow_section"]["hidden"] == 1
		assert fields["workflow_status"]["hidden"] == 1

	def test_reject_workflow_transitions_return_to_draft(self) -> None:
		workflow_path = Path(__file__).resolve().parents[1] / "fixtures" / "workflow.json"
		workflow = json.loads(workflow_path.read_text(encoding="utf-8"))[0]
		reject_transitions = [
			transition for transition in workflow["transitions"] if transition["action"] == "Reject"
		]

		self.assertEqual(
			{transition["state"]: transition["next_state"] for transition in reject_transitions},
			{
				"Submitted for Check": "Draft",
				"PM Approved": "Draft",
				"Approved by Purchase": "Draft",
			},
		)
		self.assertEqual(
			{transition["state"]: transition["allowed"] for transition in reject_transitions},
			{
				"Submitted for Check": "Projects Manager",
				"PM Approved": "Purchase Manager",
				"Approved by Purchase": "MR Coordinator",
			},
		)

	def test_generated_release_artifact_fields_are_not_copied(self) -> None:
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
			"workflow_status",
		):
			assert fields[fieldname]["no_copy"] == 1
		assert end_piece_fields["end_piece_item_code"]["no_copy"] == 1

	def test_layout_end_piece_has_reuse_strip_fields(self) -> None:
		doctype_path = (
			Path(__file__).resolve().parents[1]
			/ "sheet_cutting_layout"
			/ "doctype"
			/ "layout_end_piece"
			/ "layout_end_piece.json"
		)
		doctype = json.loads(doctype_path.read_text(encoding="utf-8"))
		fields = {field["fieldname"]: field for field in doctype["fields"]}

		assert doctype["field_order"].index("strip_width_mm") > doctype["field_order"].index("length_mm")
		assert doctype["field_order"].index("strip_weight_kg") < doctype["field_order"].index("weight_kg")
		assert fields["strip_width_mm"]["fieldtype"] == "Float"
		assert fields["strip_width_mm"]["depends_on"] == 'eval:doc.disposition=="Reuse"'
		assert fields["strip_length_mm"]["fieldtype"] == "Float"
		assert fields["strip_length_mm"]["depends_on"] == 'eval:doc.disposition=="Reuse"'
		assert fields["strip_weight_kg"]["fieldtype"] == "Float"
		assert fields["strip_weight_kg"]["read_only"] == 1
		assert fields["strip_weight_kg"]["depends_on"] == 'eval:doc.disposition=="Reuse"'

	def test_approval_snapshot_table_is_system_maintained(self) -> None:
		doctype_dir = Path(__file__).resolve().parents[1] / "sheet_cutting_layout" / "doctype"
		layout_fields = {
			row["fieldname"]: row
			for row in json.loads(
				(doctype_dir / "sheet_cutting_layout" / "sheet_cutting_layout.json").read_text(
					encoding="utf-8"
				)
			)["fields"]
			if "fieldname" in row
		}
		snapshot = json.loads(
			(doctype_dir / "layout_approval_snapshot" / "layout_approval_snapshot.json").read_text(
				encoding="utf-8"
			)
		)

		assert layout_fields["approval_snapshot"]["read_only"] == 1
		assert snapshot["editable_grid"] == 0
		assert {row["fieldname"] for row in snapshot["fields"] if row.get("read_only") == 1} == {
			"step_name",
			"approver",
			"decision",
			"comment",
			"decision_time",
		}

	def test_readme_mentions_release_gate_and_bom_qty_parts_per_sheet(self) -> None:
		content = Path(__file__).resolve().parents[2].joinpath("README.md").read_text(encoding="utf-8")

		assert "BOM quantity equals `parts_per_sheet`" in content
		assert "Draft -> Submitted for Check -> PM Approved -> Approved by Purchase -> Released" in content

	def test_reuse_end_piece_byproduct_uses_strip_weight(self) -> None:
		from sheet_cutting_layout.services.bom_service import (
			build_bom_from_layout_row,
			parent_finished_part_row,
		)

		layout = SimpleNamespace(
			raw_material_item="RM-001",
			process_scrap_item="SCRAP-001",
			weight_per_sheet_kg=10.0,
			no_of_strips=1,
			finished_part_code="FG01SHR",
			is_lh_rh=0,
			orientation=None,
			twin_finished_part=None,
			parts_per_sheet=1,
			gross_weight_per_part_kg=2.0,
			scrap_weight_per_part_kg=0.0,
			sheet_thickness_mm=2.0,
			end_pieces=[
				SimpleNamespace(
					disposition="Reuse",
					weight_kg=5.0,
					strip_weight_kg=3.0,
					end_piece_item_code="EP-001",
					used_for_finished_part="FG02SHR",
					width_mm=200.0,
					length_mm=300.0,
				)
			],
		)

		bom = build_bom_from_layout_row(layout, parent_finished_part_row(layout))

		assert bom.scrap_items[-1].qty == 3.0


class TestReleaseFlow(ReleaseServiceIsolatedTestCase):
	def test_release_reaches_released(self) -> None:
		from sheet_cutting_layout.services.release_service import release_layout

		layout = Layout()
		result = release_layout(
			layout,
			layouts=[],
			boms=[],
			bom_document_factory=_in_memory_bom_factory,
		)

		assert result.status == "Released"
		assert layout.workflow_status == "Released"

	def test_release_runs_default_layout_validation(self) -> None:
		from sheet_cutting_layout.services.release_service import ReleaseContext, release_layout
		from sheet_cutting_layout.services.validators import frappe

		layout = Layout(finished_parts=[FinishedPart("PART-001SHR")])

		try:
			validation_error = frappe.ValidationError
		except AttributeError:
			validation_error = Exception

		with self.assertRaisesRegex(validation_error, "alphanumeric"):
			release_layout(layout, release_context=ReleaseContext(layouts=(), boms=[]))

		assert layout.workflow_status == "Approved by Purchase"

	def test_release_allows_injected_validators_for_testability(self) -> None:
		from sheet_cutting_layout.services.release_service import release_layout

		calls: list[str] = []
		layout = Layout(finished_parts=[FinishedPart("PART-001SHR")])

		release_layout(
			layout,
			validators=[lambda received: calls.append(received.workflow_status)],
			layouts=[],
			boms=[],
			bom_document_factory=_in_memory_bom_factory,
		)

		assert calls == ["Approved by Purchase"]
		assert layout.workflow_status == "Released"

	def test_release_requires_process_scrap_item_when_process_scrap_is_positive(self) -> None:
		from sheet_cutting_layout.services.release_service import ReleaseContext, release_layout
		from sheet_cutting_layout.services.validators import frappe

		layout = Layout(
			process_scrap_item="",
			finished_parts=[FinishedPart("PART001SHR", scrap_weight_per_part_kg=0.25)],
		)

		with self.assertRaisesRegex(frappe.ValidationError, "Process scrap item"):
			release_layout(layout, release_context=ReleaseContext(layouts=(), boms=[]))

	def test_release_stops_when_injected_validator_fails(self) -> None:
		from sheet_cutting_layout.services.release_service import release_layout

		def fail_validator(_layout: Layout) -> None:
			raise ValueError("not ready")

		layout = Layout()

		with self.assertRaisesRegex(ValueError, "not ready"):
			release_layout(layout, validators=[fail_validator], layouts=[], boms=[])

		assert layout.workflow_status == "Approved by Purchase"
		assert layout.finished_parts[0].generated_bom is None

	def test_release_uses_injected_context_provider(self) -> None:
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

	def test_release_uses_injected_bom_document_factory_for_persisted_boms(self) -> None:
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

	def test_generated_bom_holds_primary_part_with_multiple_finished_parts(self) -> None:
		layout = Layout()
		layout.finished_part_code = "PART001SHR"
		built: list[str] = []

		def fake_factory(layout_doc, finished_part, index):
			from sheet_cutting_layout.services.bom_service import BomDocument

			name = f"BOM-{index:03d}-{finished_part.finished_part_item}"
			built.append(name)
			return BomDocument(item=finished_part.finished_part_item, name=name)

		from sheet_cutting_layout.services import release_service

		def two_rows(_layout):
			from sheet_cutting_layout.services.bom_service import ParentFinishedPartRow

			return [
				ParentFinishedPartRow("PART001SHR", 1, 1.0, 0.0),
				ParentFinishedPartRow("PART001SHR_TWIN", 1, 1.0, 0.0),
			]

		with patch.object(release_service, "_parent_finished_part_rows", two_rows):
			result = release_service.release_layout(
				layout,
				layouts=(),
				boms=[],
				validators=(),
				bom_document_factory=fake_factory,
			)

		self.assertEqual(len(result.generated_boms), 2)
		self.assertEqual(layout.generated_bom, built[0])
		self.assertEqual([row.generated_bom for row in layout.finished_parts], built)

	def test_sync_finished_part_reference_rows_rejects_mismatched_lengths(self) -> None:
		from sheet_cutting_layout.services import release_service
		from sheet_cutting_layout.services.bom_service import BomDocument

		layout = Layout(finished_parts=[])
		finished_parts = [
			FinishedPart("PART001SHR"),
			FinishedPart("PART001SHR_TWIN"),
		]
		generated_boms = [BomDocument(item="PART001SHR", name="BOM-001-PART001SHR")]

		with self.assertRaisesRegex(
			ValueError,
			"generated_boms and finished_parts length mismatch",
		):
			release_service._sync_finished_part_reference_rows(layout, generated_boms, finished_parts)

	def test_sync_finished_part_reference_rows_maps_generated_bom_and_optional_orientation(self) -> None:
		from sheet_cutting_layout.services import release_service
		from sheet_cutting_layout.services.bom_service import BomDocument

		layout = Layout(finished_parts=[])
		finished_parts = [
			SimpleNamespace(
				finished_part_item="PART001LHSHR",
				parts_per_sheet=2,
				orientation="LH",
			),
			SimpleNamespace(
				finished_part_item="PART001SHR",
				parts_per_sheet=1,
			),
		]
		generated_boms = [
			BomDocument(item="PART001LHSHR", name="BOM-001-PART001LHSHR"),
			BomDocument(item="PART001SHR", name="BOM-002-PART001SHR"),
		]

		release_service._sync_finished_part_reference_rows(layout, generated_boms, finished_parts)

		self.assertEqual(
			[row.generated_bom for row in layout.finished_parts],
			["BOM-001-PART001LHSHR", "BOM-002-PART001SHR"],
		)
		self.assertEqual([row.orientation for row in layout.finished_parts], ["LH", None])

	def test_release_uses_parent_finished_part_contract_without_child_inputs(self) -> None:
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

	def test_release_syncs_finished_part_reference_rows_from_saved_bom(self) -> None:
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

	def test_release_generates_bom_for_one_sheet_in_kg_with_scrap_outputs(self) -> None:
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

	def test_generated_boms_are_activated_on_release(self) -> None:
		from sheet_cutting_layout.services.release_service import release_layout

		old_layout = RevisionLayout(
			name="SCL-001",
			project="FAM-001",
			revision_no=1,
			workflow_status="Released",
			is_active=True,
			finished_parts=[FinishedPart("PART001LHSHR", generated_bom="BOM-PART001LHSHR-OLD")],
		)
		new_layout = RevisionLayout(
			name="SCL-002",
			project="FAM-001",
			revision_no=2,
			workflow_status="Approved by Purchase",
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

	def test_release_persists_only_new_revision_layout_when_frappe_is_available(self) -> None:
		from sheet_cutting_layout.services import release_service
		from sheet_cutting_layout.services.bom_service import BomDocument
		from sheet_cutting_layout.services.release_service import release_layout

		old_layout = SavableRevisionLayout(
			name="SCL-001",
			project="FAM-001",
			revision_no=1,
			workflow_status="Released",
			is_active=True,
			finished_parts=[FinishedPart("PART001LHSHR", generated_bom="BOM-PART001LHSHR-OLD")],
		)
		new_layout = SavableRevisionLayout(
			name="SCL-002",
			project="FAM-001",
			revision_no=2,
			workflow_status="Approved by Purchase",
			is_active=False,
			finished_parts=[FinishedPart("PART001LHSHR", gross_weight_per_part_kg=2.5)],
		)

		self.start_patcher(patch.object(release_service, "frappe", _SavableBomFrappeStub))

		release_layout(
			new_layout,
			layouts=[old_layout, new_layout],
			boms=[],
			bom_document_factory=lambda _layout, row, _index: BomDocument(
				item=row.finished_part_item,
				name="BOM-PART001LHSHR-NEW",
			),
		)

		assert old_layout.workflow_status == "Released"
		assert old_layout.save_calls == 0
		assert new_layout.workflow_status == "Released"
		assert new_layout.save_calls == 1

	def test_release_does_not_db_set_unchanged_submitted_layouts(self) -> None:
		from sheet_cutting_layout.services import release_service
		from sheet_cutting_layout.services.bom_service import BomDocument
		from sheet_cutting_layout.services.release_service import release_layout

		old_layout = SubmittedRevisionLayout(
			name="SCL-001",
			project="FAM-001",
			revision_no=1,
			workflow_status="Released",
			is_active=True,
			finished_parts=[FinishedPart("PART001LHSHR", generated_bom="BOM-PART001LHSHR-OLD")],
		)
		new_layout = SavableRevisionLayout(
			name="SCL-002",
			project="FAM-001",
			revision_no=2,
			workflow_status="Approved by Purchase",
			is_active=False,
			finished_parts=[FinishedPart("PART001LHSHR", gross_weight_per_part_kg=2.5)],
		)

		self.start_patcher(patch.object(release_service, "frappe", _SavableBomFrappeStub))

		release_layout(
			new_layout,
			layouts=[old_layout, new_layout],
			boms=[],
			bom_document_factory=lambda _layout, row, _index: BomDocument(
				item=row.finished_part_item,
				name="BOM-PART001LHSHR-NEW",
			),
		)

		assert old_layout.workflow_status == "Released"
		assert old_layout.is_active is True
		assert old_layout.save_calls == 0
		assert old_layout.db_set_calls == []

	def test_mr_release_records_mr_approval_snapshot(self) -> None:
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


class TestSaveTimeAudit(ReleaseServiceIsolatedTestCase):
	def test_save_time_audit_rejects_generated_bom_quantity_drift(self) -> None:
		from sheet_cutting_layout.services import validators

		layout = _audit_layout()

		with (
			patch.object(validators, "frappe", _audit_frappe_stub(bom_quantity=99)),
			patch.object(validators, "_", lambda message: message),
			self.assertRaisesRegex(ValueError, "BOM quantity mismatch"),
		):
			validators.validate_sheet_cutting_layout(layout)

	def test_save_time_audit_rejects_missing_reuse_end_piece_byproduct_row(self) -> None:
		from sheet_cutting_layout.services import validators

		layout = _audit_layout(end_piece_fields=_AUDIT_REUSE_END_PIECE, sheet_thickness_mm=1.6)

		with (
			patch.object(
				validators, "frappe", _audit_frappe_stub(bom_quantity=77, include_end_piece_scrap_row=False)
			),
			patch.object(validators, "_", lambda message: message),
			self.assertRaisesRegex(ValueError, "BOM scrap item mismatch"),
		):
			validators.validate_sheet_cutting_layout(layout)

	def test_save_time_audit_accepts_secondary_scrap_rows(self) -> None:
		from sheet_cutting_layout.services import validators

		layout = _audit_layout(end_piece_fields=_AUDIT_REUSE_END_PIECE, sheet_thickness_mm=1.6)

		with (
			patch.object(
				validators,
				"frappe",
				_audit_frappe_stub(
					bom_quantity=77,
					end_piece_item_code="FG01SHR-EP-1.6x1250x179",
					use_secondary_items=True,
				),
			),
			patch.object(validators, "_", lambda message: message),
		):
			validators.validate_sheet_cutting_layout(layout)

	def test_save_time_audit_rejects_fractional_generated_bom_quantity(self) -> None:
		from sheet_cutting_layout.services import validators

		layout = _audit_layout()

		with (
			patch.object(validators, "frappe", _audit_frappe_stub(bom_quantity=11.5)),
			patch.object(validators, "_", lambda message: message),
			self.assertRaisesRegex(ValueError, "BOM quantity mismatch"),
		):
			validators.validate_sheet_cutting_layout(layout)


class TestControllerWorkflow(ReleaseServiceIsolatedTestCase):
	def test_controller_before_insert_clears_copied_release_artifacts(self) -> None:
		from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import (
			sheet_cutting_layout,
		)

		doc = object.__new__(sheet_cutting_layout.SheetCuttingLayout)
		doc.generated_bom = "BOM-OLD"
		doc.finished_parts = [SimpleNamespace(generated_bom="BOM-OLD")]
		doc.approval_snapshot = [SimpleNamespace(step_name="MR Approval")]
		doc.workflow_status = "Released"
		doc.is_active = True
		doc.end_piece_bom_status = "Generated"
		doc.end_pieces = [EndPiece(weight_kg=2.5, end_piece_item_code="FG01SHR-EP-1x1250x260")]

		doc.before_insert()

		assert doc.generated_bom is None
		assert doc.finished_parts == []
		assert doc.approval_snapshot == []
		assert doc.workflow_status == "Draft"
		assert doc.is_active is False
		assert doc.end_piece_bom_status == "Pending"
		assert doc.end_pieces[0].end_piece_item_code is None

	def test_controller_mr_release_action_calls_release_service(self) -> None:
		from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import (
			sheet_cutting_layout,
		)

		calls: list[object] = []

		def fake_release_layout(layout: object, **kwargs: object) -> None:
			calls.append((layout, kwargs))
			return type("ReleaseResult", (), {"status": "Released"})()

		self.start_patcher(patch.object(sheet_cutting_layout, "release_layout", fake_release_layout))
		snapshot = self.start_patcher(patch.object(sheet_cutting_layout, "record_approval_snapshot"))
		self.start_patcher(patch.object(sheet_cutting_layout, "_get_session_user", lambda: "mr@example.com"))
		self.start_patcher(
			patch.object(
				sheet_cutting_layout,
				"_get_now_datetime",
				lambda: datetime(2026, 5, 15, 12, 30, 0),
			)
		)

		doc = _new_sheet_cutting_layout_doc(sheet_cutting_layout)
		doc.workflow_status = "Released"
		doc.on_submit()

		assert calls == [(doc, {})]
		snapshot.assert_called_once_with(
			doc,
			action="MR Release",
			approver="mr@example.com",
			decision_time=datetime(2026, 5, 15, 12, 30, 0),
		)

	def test_controller_on_submit_ignores_non_released_status(self) -> None:
		from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import (
			sheet_cutting_layout,
		)

		calls: list[object] = []

		self.start_patcher(
			patch.object(sheet_cutting_layout, "release_layout", lambda layout: calls.append(layout))
		)
		snapshot = self.start_patcher(patch.object(sheet_cutting_layout, "record_approval_snapshot"))

		doc = _new_sheet_cutting_layout_doc(sheet_cutting_layout)
		doc.workflow_status = "Approved by Purchase"

		doc.on_submit()

		assert calls == []
		snapshot.assert_not_called()

	def test_controller_validate_only_runs_validator(self) -> None:
		from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import (
			sheet_cutting_layout,
		)

		validate = self.start_patcher(patch.object(sheet_cutting_layout, "validate_sheet_cutting_layout"))
		snapshot = self.start_patcher(patch.object(sheet_cutting_layout, "record_approval_snapshot"))

		doc = _new_sheet_cutting_layout_doc(sheet_cutting_layout)

		doc.validate()

		validate.assert_called_once_with(doc)
		snapshot.assert_not_called()

	def test_rejected_layout_on_trash_removes_workflow_action_links(self) -> None:
		from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import (
			sheet_cutting_layout,
		)

		deletions: list[tuple[str, dict[str, str]]] = []
		unlinked_bom_filters: list[dict[str, object]] = []

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

			@staticmethod
			def set_value(
				doctype: str,
				filters: dict[str, object],
				fieldname: str,
				value: object,
				**kwargs: object,
			) -> None:
				assert doctype == "BOM"
				assert fieldname == "sheet_cutting_layout"
				assert value is None
				assert kwargs == {"update_modified": False}
				unlinked_bom_filters.append(filters)

		class FrappeStub:
			db = DbStub()

		self.start_patcher(patch.object(sheet_cutting_layout, "frappe", FrappeStub))

		doc = _new_sheet_cutting_layout_doc(sheet_cutting_layout)
		doc.name = "SCL-REJECTED"
		doc.workflow_status = "Draft"

		doc.on_trash()

		assert unlinked_bom_filters == [{"sheet_cutting_layout": "SCL-REJECTED", "docstatus": 2}]
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

	def test_non_rejected_layout_on_trash_removes_workflow_action_links(self) -> None:
		from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import (
			sheet_cutting_layout,
		)

		deletions: list[object] = []
		unlinked_bom_filters: list[dict[str, object]] = []

		class DbStub:
			@staticmethod
			def get_all(doctype: str, **kwargs: object) -> list[str]:
				assert doctype == "Workflow Action"
				assert kwargs == {
					"filters": {
						"reference_doctype": "Sheet Cutting Layout",
						"reference_name": "SCL-RELEASED",
					},
					"pluck": "name",
				}
				return ["WF-ACTION-1"]

			@staticmethod
			def delete(doctype: str, filters: dict[str, str]) -> None:
				deletions.append((doctype, filters))

			@staticmethod
			def set_value(
				doctype: str,
				filters: dict[str, object],
				fieldname: str,
				value: object,
				**kwargs: object,
			) -> None:
				assert doctype == "BOM"
				assert fieldname == "sheet_cutting_layout"
				assert value is None
				assert kwargs == {"update_modified": False}
				unlinked_bom_filters.append(filters)

		class FrappeStub:
			db = DbStub()

		self.start_patcher(patch.object(sheet_cutting_layout, "frappe", FrappeStub))

		doc = _new_sheet_cutting_layout_doc(sheet_cutting_layout)
		doc.name = "SCL-RELEASED"
		doc.workflow_status = "Released"

		doc.on_trash()

		assert unlinked_bom_filters == [{"sheet_cutting_layout": "SCL-RELEASED", "docstatus": 2}]
		assert deletions == [
			(
				"Workflow Action Permitted Role",
				{"parenttype": "Workflow Action", "parent": ["in", ["WF-ACTION-1"]]},
			),
			(
				"Workflow Action",
				{"reference_doctype": "Sheet Cutting Layout", "reference_name": "SCL-RELEASED"},
			),
		]

	def test_controller_before_cancel_records_supersede_snapshot(self) -> None:
		from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import (
			sheet_cutting_layout,
		)

		snapshot = self.start_patcher(patch.object(sheet_cutting_layout, "record_approval_snapshot"))
		self.start_patcher(patch.object(sheet_cutting_layout, "_get_session_user", lambda: "mr@example.com"))
		self.start_patcher(
			patch.object(
				sheet_cutting_layout,
				"_get_now_datetime",
				lambda: datetime(2026, 5, 15, 12, 30, 0),
			)
		)

		doc = _new_sheet_cutting_layout_doc(sheet_cutting_layout)
		doc.workflow_status = "Superseded"
		doc.generated_bom = "BOM-PART001SHR-001"
		doc.before_cancel()

		assert doc.ignore_linked_doctypes == ["BOM", "Sheet Cutting Layout"]
		snapshot.assert_called_once_with(
			doc,
			action="Supersede",
			approver="mr@example.com",
			decision_time=datetime(2026, 5, 15, 12, 30, 0),
		)

	def test_controller_on_cancel_retires_layout(self) -> None:
		from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import (
			sheet_cutting_layout,
		)

		calls: list[object] = []

		self.start_patcher(
			patch.object(sheet_cutting_layout, "retire_layout", lambda layout: calls.append(layout))
		)
		snapshot = self.start_patcher(patch.object(sheet_cutting_layout, "record_approval_snapshot"))

		doc = _new_sheet_cutting_layout_doc(sheet_cutting_layout)
		doc.generated_bom = "BOM-PART001SHR-001"
		doc.on_cancel()

		assert calls == [doc]
		snapshot.assert_not_called()

	def test_controller_on_cancel_does_not_force_cancel_status(self) -> None:
		from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import (
			sheet_cutting_layout,
		)

		calls: list[object] = []
		self.start_patcher(
			patch.object(sheet_cutting_layout, "retire_layout", lambda layout: calls.append(layout))
		)
		self.start_patcher(patch.object(sheet_cutting_layout, "record_approval_snapshot"))

		doc = _new_sheet_cutting_layout_doc(sheet_cutting_layout)
		doc.workflow_status = "Superseded"
		doc.generated_bom = "BOM-PART001SHR-001"
		doc.on_cancel()

		assert calls == [doc]
		assert doc.workflow_status == "Superseded"

	def test_form_cancel_lets_layout_controller_cancel_linked_bom(self) -> None:
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

	def test_form_recalculates_reuse_strip_fields(self) -> None:
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

		assert "function updateEndPieceStripWeights(frm)" in content
		assert "endPieces.reduce((total, row) => total + endPieceConsumedWeight(row), 0)" in content
		assert "strip_width_mm: updateEndPieceWeightsAndConsumption" in content
		assert "strip_length_mm: updateEndPieceWeightsAndConsumption" in content
		assert "strip_weight_kg: updateEndPieceReuseWeightsAndConsumption" in content
		assert 'frappe.model.set_value(cdt, cdn, "strip_width_mm", null)' in content
		assert 'frappe.model.set_value(cdt, cdn, "strip_length_mm", null)' in content
		assert 'frappe.model.set_value(cdt, cdn, "strip_weight_kg", null)' in content


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


def _audit_frappe_stub(
	*,
	bom_quantity: float,
	include_end_piece_scrap_row: bool = True,
	end_piece_item_code: str = "ENDSCRAP001",
	use_secondary_items: bool = False,
) -> type:
	scrap_items = [
		type(
			"ScrapItem",
			(),
			{"item_code": "PROCESSSCRAP001", "stock_qty": 14.233142, "qty": 14.233142},
		)(),
	]
	if include_end_piece_scrap_row:
		scrap_items.append(
			type(
				"ScrapItem",
				(),
				{"item_code": end_piece_item_code, "stock_qty": 2.81388, "qty": 2.81388},
			)()
		)
	secondary_items = [
		type(
			"SecondaryItem",
			(),
			{
				"type": "Scrap" if item.item_code == "PROCESSSCRAP001" else "By-Product",
				"item_code": item.item_code,
				"stock_qty": item.stock_qty,
				"qty": item.qty,
			},
		)()
		for item in scrap_items
	]

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
					"quantity": bom_quantity,
					"items": [type("BomItem", (), {"item_code": "RMSHEET001", "qty": 39.3})()],
					"scrap_items": [] if use_secondary_items else scrap_items,
					"secondary_items": secondary_items if use_secondary_items else [],
				},
			)()

		@staticmethod
		def throw(message: str) -> None:
			raise ValueError(message)

	return FrappeStub


_AUDIT_SCRAP_END_PIECE = {
	"weight_kg": 2.81388,
	"width_mm": 1250,
	"length_mm": 179,
	"disposition": "Scrap",
	"scrap_item": "ENDSCRAP001",
}

_AUDIT_REUSE_END_PIECE = {
	"idx": 1,
	"end_piece_item_code": None,
	"weight_kg": 2.81388,
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
}


def _audit_layout(
	*,
	end_piece_fields: dict[str, object] = _AUDIT_SCRAP_END_PIECE,
	sheet_thickness_mm: float | None = None,
) -> object:
	return type(
		"AuditLayout",
		(),
		{
			"finished_part_code": "FG01SHR",
			"net_weight_per_part_kg": 0.289,
			"generated_bom": "BOM-FG01SHR",
			"end_pieces": [type("EndPieceRow", (), dict(end_piece_fields))()],
			"raw_material_item": "RMSHEET001",
			"process_scrap_item": "PROCESSSCRAP001",
			"end_piece_bom_status": "",
			"sheet_thickness_mm": sheet_thickness_mm,
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


class TestFrappeBomInsertAndEndPieces(ReleaseServiceIsolatedTestCase):
	def test_frappe_bom_insert_sets_required_company_from_layout(self) -> None:
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
				assert not hasattr(self, "uom")
				assert not hasattr(self, "is_active")
				assert not hasattr(self, "disabled")
				assert not hasattr(self, "status")
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
		self.start_patcher(patch.object(release_service, "frappe", FrappeStub))

		inserted = release_service._insert_frappe_bom(bom)

		assert inserted.name == "BOM-PART001SHR"

	def test_frappe_bom_insert_appends_scrap_without_rate_resolution(self) -> None:
		from sheet_cutting_layout.services import release_service
		from sheet_cutting_layout.services.bom_service import BomDocument, BomItemRow

		created_boms: list[object] = []

		class FrappeBom:
			def __init__(self) -> None:
				self.name = ""
				self.items: list[dict[str, object]] = []
				self.scrap_items: list[dict[str, object]] = []

			def append(self, fieldname: str, row: dict[str, object]) -> None:
				getattr(self, fieldname).append(row)

			def insert(self) -> None:
				self.name = self.name or "BOM-PERSISTED"
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

		bom = BomDocument(item="PART001SHR", name="BOM-PART001SHR")
		bom._layout = type("LayoutWithCompany", (), {"company": "Test Company", "name": "SCL-001"})()
		bom.scrap_items.append(BomItemRow(item_code="SCRAP-ITEM", qty=1.0, row_type="process_scrap"))
		self.start_patcher(patch.object(release_service, "frappe", FrappeStub))

		release_service._insert_frappe_bom(bom)

		self.assertEqual(
			created_boms[0].scrap_items,
			[{"item_code": "SCRAP-ITEM", "stock_qty": 1.0, "stock_uom": "Kg"}],
		)

	def test_frappe_bom_insert_appends_scrap_to_secondary_items_when_required(self) -> None:
		from sheet_cutting_layout.services import release_service
		from sheet_cutting_layout.services.bom_service import BomDocument, BomItemRow

		created_boms: list[object] = []

		class FrappeBom:
			def __init__(self) -> None:
				self.name = ""
				self.items: list[dict[str, object]] = []
				self.secondary_items: list[dict[str, object]] = []

			def append(self, fieldname: str, row: dict[str, object]) -> None:
				getattr(self, fieldname).append(row)

			def insert(self) -> None:
				self.name = self.name or "BOM-PERSISTED"
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

		bom = BomDocument(item="PART001SHR", name="BOM-PART001SHR")
		bom._layout = type("LayoutWithCompany", (), {"company": "Test Company", "name": "SCL-001"})()
		bom.scrap_items.append(BomItemRow(item_code="SCRAP-ITEM", qty=1.0, row_type="process_scrap"))
		bom.scrap_items.append(BomItemRow(item_code="BYP-ITEM", qty=2.0, row_type="end_piece_byproduct"))
		self.start_patcher(patch.object(release_service, "frappe", FrappeStub))

		release_service._insert_frappe_bom(bom)

		self.assertEqual(
			created_boms[0].secondary_items,
			[
				{
					"type": "Scrap",
					"item_code": "SCRAP-ITEM",
					"stock_qty": 1.0,
					"qty": 1.0,
					"uom": "Kg",
					"stock_uom": "Kg",
					"conversion_factor": 1,
					"cost_allocation_per": 0,
					"process_loss_per": 0,
					"process_loss_qty": 0,
					"cost": 0,
					"base_cost": 0,
				},
				{
					"type": "By-Product",
					"item_code": "BYP-ITEM",
					"stock_qty": 2.0,
					"qty": 2.0,
					"uom": "Kg",
					"stock_uom": "Kg",
					"conversion_factor": 1,
					"cost_allocation_per": 0,
					"process_loss_per": 0,
					"process_loss_qty": 0,
					"cost": 0,
					"base_cost": 0,
				},
			],
		)

	def test_default_release_creates_reuse_end_piece_byproduct_row(self) -> None:
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
					strip_weight_kg=2.81388,
					disposition="Reuse",
					used_for_finished_part="FG002SHR",
					width_mm=1250,
					length_mm=179,
				)
			],
		)
		layout.company = "Test Company"
		layout.sheet_thickness_mm = 1.6

		def fake_ensure(_layout: object, _row: object, *, source_finished_part: str | None = None) -> str:
			return f"{source_finished_part}-EP-1.6x1250x179"

		self.start_patcher(patch.object(release_service, "frappe", FrappeStub))
		self.start_patcher(patch.object(release_service, "ensure_end_piece_item", fake_ensure))

		result = release_service.release_layout(
			layout,
			validators=[lambda _layout: None],
			release_context=release_service.ReleaseContext(layouts=(), boms=[]),
		)

		assert result.generated_boms[0].name == "BOM-002-R2-001-FG01SHR"
		assert layout.end_pieces[0].end_piece_item_code == "FG01SHR-EP-1.6x1250x179"
		assert len(created_boms) == 1
		assert created_boms[0].scrap_items == [
			{
				"item_code": "PROCESSSCRAP001",
				"stock_qty": 14.233142,
				"stock_uom": "Kg",
			},
			{
				"item_code": "FG01SHR-EP-1.6x1250x179",
				"stock_qty": 2.81388,
				"stock_uom": "Kg",
			},
		]
		assert round(layout.finished_parts[0].scrap_weight_kg, 6) == 14.233142
		assert layout.finished_parts[0].raw_material_weight_kg == 39.3

	def test_default_release_persists_generated_end_piece_item_code_on_saved_layout(self) -> None:
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

		layout = SavableLayout(
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

		def fake_ensure(_layout: object, _row: object, *, source_finished_part: str | None = None) -> str:
			return f"{source_finished_part}-EP-1.6x1250x179"

		self.start_patcher(patch.object(release_service, "frappe", FrappeStub))
		self.start_patcher(patch.object(release_service, "ensure_end_piece_item", fake_ensure))

		release_service.release_layout(
			layout,
			validators=[lambda _layout: None],
			release_context=release_service.ReleaseContext(layouts=(persisted_layout,), boms=[]),
		)

		assert layout.end_pieces[0].end_piece_item_code == "FG01SHR-EP-1.6x1250x179"
		# The in-memory layout being released is the record that gets persisted; the
		# re-fetched context copy must not be saved (it would write stale state back).
		assert layout.save_calls == 1
		assert persisted_layout.save_calls == 0

	def test_lh_rh_release_uses_primary_and_twin_for_shared_end_piece_item_code(self) -> None:
		from sheet_cutting_layout.services import release_service

		created_for: list[str | None] = []

		class FrappeBom:
			def __init__(self) -> None:
				self.name = ""
				self.items: list[dict[str, object]] = []
				self.scrap_items: list[dict[str, object]] = []
				self.flags = type("Flags", (), {})()

			def append(self, fieldname: str, row: dict[str, object]) -> None:
				getattr(self, fieldname).append(row)

			def insert(self) -> None:
				self.name = self.name or f"BOM-{len(created_for)}"

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
			name="SCL-LHRH",
			weight_per_sheet_kg=39.3,
			parts_per_sheet=2,
			finished_part_code="FG01SHR",
			gross_weight_per_part_kg=10.0,
			scrap_weight_per_part_kg=1.0,
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
		layout.is_lh_rh = 1
		layout.orientation = "LH"
		layout.twin_finished_part = "FG01RHSHR"

		def fake_ensure(_layout: object, _row: object, *, source_finished_part: str | None = None) -> str:
			created_for.append(source_finished_part)
			return f"{source_finished_part}-EP-1.6x1250x179"

		self.start_patcher(patch.object(release_service, "frappe", FrappeStub))
		self.start_patcher(patch.object(release_service, "ensure_end_piece_item", fake_ensure))

		release_service.release_layout(
			layout,
			validators=[lambda _layout: None],
			release_context=release_service.ReleaseContext(layouts=(), boms=[]),
		)

		assert created_for == ["FG01SHR-FG01RHSHR"]
		assert layout.end_pieces[0].end_piece_item_code == "FG01SHR-FG01RHSHR-EP-1.6x1250x179"


class TestReleaseContextAndHelpers(ReleaseServiceIsolatedTestCase):
	def test_release_context_discovers_layouts_and_boms(self) -> None:
		from sheet_cutting_layout.services import release_service

		class FrappeStub:
			@staticmethod
			def get_all(doctype: str, **kwargs: object) -> list[object]:
				if doctype == "Sheet Cutting Layout":
					# Layout discovery uses lightweight name rows, not full documents.
					return [frappe._dict(name="SCL-OLD")]
				if doctype == "BOM":
					return ["BOM-OLD"]
				raise AssertionError(f"Unexpected doctype {doctype}")

			@staticmethod
			def get_doc(doctype: str, name: str) -> object:
				assert doctype == "BOM", f"only BOMs are fetched as full documents, got {doctype}"
				return type("Doc", (), {"doctype": doctype, "name": name})()

		layout = RevisionLayout(
			name="SCL-NEW",
			project="FAM-001",
			revision_no=2,
			workflow_status="Approved by Purchase",
			is_active=False,
			finished_parts=[FinishedPart("PART001SHR")],
		)
		self.start_patcher(patch.object(release_service, "frappe", FrappeStub))

		context = release_service.get_release_context(layout)

		assert [getattr(doc, "name", None) for doc in context.layouts] == ["SCL-OLD", "SCL-NEW"]
		assert [getattr(doc, "name", None) for doc in context.boms or []] == ["BOM-OLD"]

	def test_release_context_handles_layout_without_family_or_finished_parts(self) -> None:
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
		self.start_patcher(patch.object(release_service, "frappe", FrappeStub))

		context = release_service.get_release_context(layout)

		assert context.layouts == [layout]
		assert context.boms == []

	def test_company_for_layout_falls_back_to_erpnext_default(self) -> None:
		from sheet_cutting_layout.services import release_service

		layout = Layout()
		layout.company = None

		with patch("erpnext.get_default_company", return_value="Default Company") as spy:
			company = release_service._company_for_layout(layout)

		self.assertEqual(company, "Default Company")
		spy.assert_called_once()

	def test_company_for_layout_errors_when_default_company_is_missing(self) -> None:
		from sheet_cutting_layout.services import release_service

		class FrappeStub:
			class ValidationError(Exception):
				pass

			@staticmethod
			def throw(message: str) -> None:
				raise FrappeStub.ValidationError(message)

		with (
			patch.object(release_service, "frappe", FrappeStub),
			patch("erpnext.get_default_company", return_value=None),
		):
			with self.assertRaisesRegex(FrappeStub.ValidationError, "Company is required"):
				release_service._company_for_layout(None)

	def test_set_frappe_field_only_when_supported(self) -> None:
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

	def test_save_submitted_layout_record_db_set_persists_twin_generated_bom(self) -> None:
		from sheet_cutting_layout.services import release_service

		calls: list[tuple[dict[str, object], bool, bool]] = []

		class SubmittedLayout:
			workflow_status = "Released"
			is_active = True
			generated_bom = "BOM-PRIMARY-001"
			twin_generated_bom = "BOM-TWIN-002"

			def db_set(
				self,
				fieldname: dict[str, object],
				update_modified: bool = True,
				notify: bool = True,
			) -> None:
				calls.append((fieldname, update_modified, notify))

		release_service._save_submitted_layout_record(SubmittedLayout())

		self.assertEqual(
			calls,
			[
				(
					{
						"workflow_status": "Released",
						"is_active": True,
						"generated_bom": "BOM-PRIMARY-001",
						"twin_generated_bom": "BOM-TWIN-002",
					},
					True,
					False,
				)
			],
		)


class TestRevisioning(ReleaseServiceIsolatedTestCase):
	def test_revising_released_layout_clones_and_increments_revision(self) -> None:
		from sheet_cutting_layout.services.versioning import create_revision

		old_layout = frappe.get_doc(
			RevisionLayout(
				name="SCL-001",
				project="FAM-001",
				layout_code="SCL-001",
				revision_no=2,
				workflow_status="Released",
				is_active=True,
			).as_dict()
		)

		new_layout = create_revision(old_layout)

		assert new_layout is not old_layout
		assert new_layout.revision_no == 3
		assert new_layout.layout_code == "SCL-001-R3"
		assert new_layout.workflow_status == "Draft"
		assert new_layout.based_on_layout == "SCL-001"
		assert new_layout.is_active is False

	def test_revision_resets_approval_snapshot_and_generated_boms(self) -> None:
		from sheet_cutting_layout.services.versioning import create_revision

		old_layout = frappe.get_doc(
			RevisionLayout(
				name="SCL-001",
				project="FAM-001",
				revision_no=1,
				workflow_status="Released",
				is_active=True,
				approval_snapshot=["purchase-approved"],
				generated_bom="BOM-PARENT-001-001",
				twin_generated_bom="BOM-PARENT-001-002",
				finished_parts=[
					FinishedPart("PART001SHR", generated_bom="BOM-PART-001-001"),
					FinishedPart("PART002SHR", generated_bom="BOM-PART-002-001"),
				],
				end_pieces=[EndPiece(weight_kg=2.5, end_piece_item_code="PART001SHR-EP-1x1250x260")],
				end_piece_bom_status="Generated",
			).as_dict()
		)

		new_layout = create_revision(old_layout)

		assert new_layout.approval_snapshot == []
		assert new_layout.generated_bom is None
		assert new_layout.twin_generated_bom is None
		assert new_layout.end_piece_bom_status == "Pending"
		assert new_layout.finished_parts == []
		assert new_layout.end_pieces[0].end_piece_item_code is None
		assert new_layout.finished_part_code == "PART001SHR"
		assert new_layout.net_weight_per_part_kg == 1.0
		assert old_layout.generated_bom == "BOM-PARENT-001-001"
		assert old_layout.twin_generated_bom == "BOM-PARENT-001-002"
		assert [row.generated_bom for row in old_layout.finished_parts] == [
			"BOM-PART-001-001",
			"BOM-PART-002-001",
		]

	def test_finalizing_new_revision_marks_only_the_new_layout_released_and_active(self) -> None:
		from sheet_cutting_layout.services.versioning import finalize_new_revision_release

		old_layout = RevisionLayout(
			name="SCL-001",
			project="FAM-001",
			revision_no=1,
			workflow_status="Released",
			is_active=True,
			generated_bom="BOM-PART-001-OLD",
			finished_parts=[FinishedPart("PART001SHR", generated_bom="BOM-PART-001-OLD")],
		)
		new_layout = RevisionLayout(
			name="SCL-002",
			project="FAM-001",
			revision_no=2,
			workflow_status="Approved by Purchase",
			is_active=False,
			generated_bom="BOM-PART-001-NEW",
			finished_parts=[FinishedPart("PART001SHR", generated_bom="BOM-PART-001-NEW")],
		)

		finalize_new_revision_release(new_layout)

		assert new_layout.workflow_status == "Released"
		assert new_layout.is_active is True
		assert old_layout.workflow_status == "Released"
		assert old_layout.is_active is True

	def test_release_generates_one_bom_for_single_finished_part_and_keeps_existing_boms_active(self) -> None:
		from sheet_cutting_layout.services.release_service import release_layout

		old_layout = RevisionLayout(
			name="SCL-001",
			project="PROJECT-001",
			revision_no=1,
			workflow_status="Released",
			is_active=True,
			finished_parts=[FinishedPart("PART001SHR", generated_bom="BOM-PART001SHR-OLD")],
		)
		new_layout = RevisionLayout(
			name="SCL-002",
			project="PROJECT-001",
			revision_no=2,
			workflow_status="Approved by Purchase",
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
		assert old_layout.workflow_status == "Released"
		assert old_layout.is_active is True
		assert old_bom.is_active is True
		assert all(bom.is_active is True for bom in result.generated_boms)


class TestBomLifecycle(ReleaseServiceIsolatedTestCase):
	def test_retire_layout_cancels_unused_bom(self) -> None:
		from sheet_cutting_layout.services import release_service

		cancelled: list[str] = []

		class BomDoc:
			def __init__(self, name: str) -> None:
				self.name = name
				self.docstatus = 1
				self.is_active = 1

			def cancel(self) -> None:
				cancelled.append(self.name)
				self.docstatus = 2
				self.is_active = 0

		fake_boms = {"BOM-X": BomDoc("BOM-X")}

		class FrappeStub:
			class db:
				@staticmethod
				def get_all(doctype, filters=None, pluck=None):
					return []

				@staticmethod
				def savepoint(save_point):
					pass

				@staticmethod
				def rollback(save_point=None):
					pass

			@staticmethod
			def get_doc(doctype, name):
				return fake_boms[name]

			class LinkExistsError(Exception):
				pass

		layout = Layout()
		layout.generated_bom = "BOM-X"

		with patch.object(release_service, "frappe", FrappeStub):
			release_service.retire_layout(layout)

		self.assertEqual(cancelled, ["BOM-X"])
		self.assertEqual(fake_boms["BOM-X"].docstatus, 2)
		self.assertEqual(fake_boms["BOM-X"].is_active, 0)

	def test_retire_layout_deactivates_when_cancel_blocked(self) -> None:
		from sheet_cutting_layout.services import release_service

		deactivated: list[tuple[str, int, bool]] = []
		rollbacks: list[str] = []

		class FrappeStub:
			class db:
				@staticmethod
				def get_all(doctype, filters=None, pluck=None):
					return []

				@staticmethod
				def savepoint(save_point):
					pass

				@staticmethod
				def rollback(save_point=None):
					rollbacks.append(save_point)

			class LinkExistsError(Exception):
				pass

			@staticmethod
			def get_doc(doctype, name):
				return fresh_bom if rollbacks else mutating_bom

		class BomDoc:
			def __init__(self) -> None:
				self.name = "BOM-USED"
				self.docstatus = 1
				self.is_active = 1
				self.flags = type("Flags", (), {})()

			def cancel(self) -> None:
				self.docstatus = 2
				self.is_active = 0
				raise FrappeStub.LinkExistsError("used by Work Order")

			def db_set(self, fieldname: str, value: int, update_modified: bool = True) -> None:
				deactivated.append((fieldname, value, update_modified))
				self.is_active = value

		mutating_bom = BomDoc()
		fresh_bom = BomDoc()
		layout = Layout()
		layout.generated_bom = "BOM-USED"

		with patch.object(release_service, "frappe", FrappeStub):
			release_service.retire_layout(layout)

		self.assertEqual(rollbacks, ["scl_retire_bom_1"])
		self.assertEqual(mutating_bom.docstatus, 2)
		self.assertEqual(fresh_bom.docstatus, 1)
		self.assertEqual(fresh_bom.is_active, 0)
		self.assertEqual(deactivated, [("is_active", 0, False)])


class TestReleaseServiceIntegration(SheetCuttingLayoutTestCase):
	def _release_ready_layout(self):
		return make_release_ready_layout()

	def _release(self, layout):
		from sheet_cutting_layout.services.release_service import release_layout

		result = release_layout(layout)
		return result

	def test_release_layout_creates_active_bom_with_sheet_weight_raw_row(self) -> None:
		layout = self._release_ready_layout()

		self._release(layout)

		self.assertEqual(layout.workflow_status, "Released")
		self.assertTrue(layout.generated_bom)
		bom = frappe.get_doc("BOM", layout.generated_bom)
		self.assertEqual(bom.item, layout.finished_part_code)
		self.assertEqual(bom.is_active, 1)
		self.assertFloatAlmostEqual(bom.quantity, layout.parts_per_sheet)
		raw_rows = [row for row in bom.items if row.item_code == layout.raw_material_item]
		self.assertEqual(len(raw_rows), 1)
		self.assertFloatAlmostEqual(raw_rows[0].qty, layout.weight_per_sheet_kg)
		self.assertEqual(raw_rows[0].uom, "Kg")

	def test_generated_bom_lets_controller_compute_uom_and_status(self) -> None:
		import frappe

		from sheet_cutting_layout.tests.factories import make_release_ready_layout

		layout = make_release_ready_layout()
		# Direct submit setup mirrors the current D-1 path until D-5 aligns the
		# user-facing workflow with native submit.
		layout.workflow_status = "Released"
		layout.submit()

		layout.reload()
		self.assertEqual(layout.workflow_status, "Released")
		self.assertTrue(layout.generated_bom)
		bom = frappe.get_doc("BOM", layout.generated_bom)
		self.assertEqual(bom.is_active, 1)
		self.assertEqual(bom.uom, frappe.db.get_value("Item", layout.finished_part_code, "stock_uom"))

	def test_native_submit_release_persists_release_artifacts(self) -> None:
		layout = self._release_ready_layout()

		layout.workflow_status = "Released"
		layout.submit()
		generated_bom = layout.generated_bom

		layout.reload()

		self.assertEqual(
			frappe.db.get_value("Sheet Cutting Layout", layout.name, "workflow_status"),
			"Released",
		)
		self.assertEqual(layout.generated_bom, generated_bom)
		self.assertEqual(len(layout.finished_parts), 1)
		self.assertEqual(layout.finished_parts[0].generated_bom, generated_bom)
		self.assertEqual(len(layout.approval_snapshot), 1)
		self.assertEqual(layout.approval_snapshot[0].step_name, "MR Approval")

	def test_release_layout_persists_released_status_and_bom_link(self) -> None:
		layout = self._release_ready_layout()

		self._release(layout)

		self.assertEqual(
			frappe.db.get_value("Sheet Cutting Layout", layout.name, "workflow_status"),
			"Released",
		)
		self.assertEqual(
			frappe.db.get_value("Sheet Cutting Layout", layout.name, "generated_bom"),
			layout.generated_bom,
		)

	def test_controller_revision_clones_real_released_layout(self) -> None:
		from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.sheet_cutting_layout import (
			create_sheet_cutting_layout_revision,
		)

		layout = self._release_ready_layout()
		self._release(layout)

		revision_name = create_sheet_cutting_layout_revision(layout.name)

		revision = frappe.get_doc("Sheet Cutting Layout", revision_name)
		self.assertEqual(revision.workflow_status, "Draft")
		self.assertEqual(revision.based_on_layout, layout.name)
		self.assertEqual(revision.revision_no, layout.revision_no + 1)
		self.assertFalse(revision.generated_bom)
		self.assertFalse(revision.twin_generated_bom)
		self.assertFalse(revision.is_active)

	def test_get_release_context_discovers_real_family_layouts_and_boms(self) -> None:
		from sheet_cutting_layout.services.release_service import get_release_context

		layout = self._release_ready_layout()
		self._release(layout)
		layout.reload()
		self.assertTrue(layout.generated_bom)

		context = get_release_context(layout)

		context_layout_names = [getattr(row, "name", None) for row in context.layouts]
		self.assertIn(layout.name, context_layout_names)
		context_bom_names = [getattr(row, "name", None) for row in context.boms]
		self.assertIn(layout.generated_bom, context_bom_names)
