from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
TEST_PATHS = (
	"sheet_cutting_layout/tests/test_bom_overrides.py",
	"sheet_cutting_layout/tests/test_bom_service.py",
	"sheet_cutting_layout/tests/test_cypress_config.py",
	"sheet_cutting_layout/tests/test_end_piece_bom_service.py",
	"sheet_cutting_layout/tests/test_model_workflow_state_machine.py",
	"sheet_cutting_layout/tests/test_property_layout_invariants.py",
	"sheet_cutting_layout/tests/test_release_service.py",
	"sheet_cutting_layout/tests/test_validators.py",
	"sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py",
)


def make_bench_pytest_case() -> type[unittest.TestCase]:
	python = _standalone_python()
	nodeids = _collect_pytest_nodeids(python)

	class BenchPytestCase(unittest.TestCase):
		__test__ = False
		maxDiff = None

	def make_test(nodeid: str):
		def test(self: unittest.TestCase) -> None:
			result = subprocess.run(
				[python, "-m", "pytest", "-q", nodeid],
				cwd=APP_ROOT,
				env=_standalone_env(),
				text=True,
				stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT,
			)
			if result.returncode:
				self.fail(result.stdout)

		return test

	for nodeid in nodeids:
		setattr(BenchPytestCase, _method_name(nodeid), make_test(nodeid))

	return BenchPytestCase


def _standalone_python() -> str:
	configured_python = os.environ.get("SHEET_CUTTING_LAYOUT_PYTEST_PYTHON")
	if configured_python:
		return configured_python

	python = shutil.which("python3.11")
	if python:
		return python

	return sys.executable


def _standalone_env() -> dict[str, str]:
	env = os.environ.copy()
	env.pop("PYTHONPATH", None)
	return env


def _collect_pytest_nodeids(python: str) -> list[str]:
	result = subprocess.run(
		[python, "-m", "pytest", "--collect-only", "-q", *TEST_PATHS],
		cwd=APP_ROOT,
		env=_standalone_env(),
		text=True,
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT,
	)
	if result.returncode:
		raise RuntimeError(result.stdout)

	return [line.strip() for line in result.stdout.splitlines() if "::" in line]


def _method_name(nodeid: str) -> str:
	name = re.sub(r"\W+", "_", nodeid).strip("_")
	return f"test_{name}"
