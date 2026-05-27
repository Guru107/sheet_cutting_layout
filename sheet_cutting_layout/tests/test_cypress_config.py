from __future__ import annotations

from pathlib import Path

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestCypressConfig(SheetCuttingLayoutTestCase):
	def test_cypress_defaults_target_local_bench_and_administrator_password(self) -> None:
		config = (REPO_ROOT / "cypress.config.js").read_text(encoding="utf-8")
		support = (REPO_ROOT / "cypress" / "support" / "e2e.js").read_text(encoding="utf-8")

		self.assertIn('baseUrl: "http://localhost:8002"', config)
		self.assertIn("testIsolation: true", config)
		self.assertIn("env:", config)
		self.assertIn('adminPassword: "123"', config)
		self.assertIn('usr: "Administrator"', support)
		self.assertIn('pwd: Cypress.env("adminPassword")', support)
		self.assertNotIn('|| "admin"', support)

	def test_cypress_seed_items_include_hsn_code_for_india_compliance(self) -> None:
		support = (REPO_ROOT / "cypress" / "support" / "e2e.js").read_text(encoding="utf-8")

		self.assertIn('Cypress.Commands.add("ensureHsnCode"', support)
		self.assertIn('doctype: "GST HSN Code"', support)
		self.assertIn("hsn_code: hsnCode", support)

		for spec_path in (
			REPO_ROOT / "cypress" / "integration" / "sheet_cutting_layout_consumption.js",
			REPO_ROOT / "cypress" / "integration" / "sheet_cutting_layout_release.js",
		):
			with self.subTest(spec_path=str(spec_path)):
				spec = spec_path.read_text(encoding="utf-8")
				self.assertIn('cy.ensureHsnCode("720890")', spec)
				self.assertIn("gst_hsn_code", spec)
