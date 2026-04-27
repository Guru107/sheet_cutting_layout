import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

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


@dataclass
class FinishedPart:
	finished_part_item: str
	generated_bom: str | None = None


@dataclass
class RevisionLayout:
	name: str
	layout_family: str
	revision_no: int
	status: LayoutVersionStatus
	is_active: bool
	based_on_layout: str | None = None
	approval_snapshot: list[str] = field(default_factory=list)
	impact_resolutions: list[str] = field(default_factory=list)
	finished_parts: list[FinishedPart] = field(default_factory=list)


@dataclass
class Bom:
	name: str
	item: str
	is_active: bool = True
	disabled: bool = False
	status: str = "Active"


def test_hooks_exposes_required_fixtures() -> None:
	expected_fixtures = [
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
	for fixture_file_name in ("workflow.json", "custom_field.json"):
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
			FinishedPart("PART-001SHR", generated_bom="BOM-PART-001-001"),
			FinishedPart("PART-002SHR", generated_bom="BOM-PART-002-001"),
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
			FinishedPart("PART-001SHR", generated_bom="BOM-PART-001-OLD"),
			FinishedPart("PART-UNTOUCHEDSHR", generated_bom="BOM-UNTOUCHED-OLD"),
		],
	)
	new_layout = RevisionLayout(
		name="SCL-002",
		layout_family="FAM-001",
		revision_no=2,
		status="Approved by Purchase",
		is_active=False,
		finished_parts=[FinishedPart("PART-001SHR", generated_bom="BOM-PART-001-NEW")],
	)
	old_bom = Bom("BOM-PART-001-OLD", item="PART-001SHR")
	new_bom = Bom("BOM-PART-001-NEW", item="PART-001SHR")
	unaffected_bom = Bom("BOM-UNTOUCHED-OLD", item="PART-UNTOUCHEDSHR")

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
		finished_parts=[FinishedPart("PART-001SHR", generated_bom="BOM-PART-001-OLD")],
	)
	new_layout = RevisionLayout(
		name="SCL-002",
		layout_family="FAM-001",
		revision_no=2,
		status="Approved by Purchase",
		is_active=False,
		finished_parts=[FinishedPart("PART-001SHR", generated_bom="BOM-PART-001-NEW")],
	)
	old_linked_bom = Bom("BOM-PART-001-OLD", item="PART-001SHR")
	unlinked_same_item_bom = Bom("BOM-PART-001-UNRELATED", item="PART-001SHR")
	new_bom = Bom("BOM-PART-001-NEW", item="PART-001SHR")

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
