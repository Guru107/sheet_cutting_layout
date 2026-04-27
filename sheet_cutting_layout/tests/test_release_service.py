import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import sheet_cutting_layout.hooks as hooks
from sheet_cutting_layout.services.release_service import LayoutImpactResolution, LayoutReleaseStatus


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
