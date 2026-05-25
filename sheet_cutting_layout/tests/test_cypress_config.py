from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_cypress_defaults_target_local_bench_and_administrator_password() -> None:
	config = (REPO_ROOT / "cypress.config.js").read_text(encoding="utf-8")
	support = (REPO_ROOT / "cypress" / "support" / "e2e.js").read_text(encoding="utf-8")

	assert 'baseUrl: "http://localhost:8002"' in config
	assert "testIsolation: true" in config
	assert "env:" in config
	assert 'adminPassword: "123"' in config
	assert 'usr: "Administrator"' in support
	assert 'pwd: Cypress.env("adminPassword")' in support
	assert '|| "admin"' not in support


def test_cypress_seed_items_include_hsn_code_for_india_compliance() -> None:
	support = (REPO_ROOT / "cypress" / "support" / "e2e.js").read_text(encoding="utf-8")

	assert 'Cypress.Commands.add("ensureHsnCode"' in support
	assert 'doctype: "GST HSN Code"' in support
	assert "hsn_code: hsnCode" in support

	for spec_path in (
		REPO_ROOT / "cypress" / "integration" / "sheet_cutting_layout_consumption.js",
		REPO_ROOT / "cypress" / "integration" / "sheet_cutting_layout_release.js",
	):
		spec = spec_path.read_text(encoding="utf-8")
		assert 'cy.ensureHsnCode("720890")' in spec
		assert "gst_hsn_code" in spec
