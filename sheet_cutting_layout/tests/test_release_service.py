import json
from pathlib import Path

import sheet_cutting_layout.hooks as hooks


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
