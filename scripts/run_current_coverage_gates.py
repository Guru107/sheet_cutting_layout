#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

APP = "sheet_cutting_layout"
APP_ROOT = Path(__file__).resolve().parents[1]
THRESHOLD = "96"


@dataclass(frozen=True)
class BenchTarget:
	label: str
	root: Path
	site: str


BENCHES = (
	BenchTarget("bench15", Path("/root/workspace/bench15"), "development.localhost"),
	BenchTarget("bench16", Path("/root/workspace/bench16"), "frappe16.localhost"),
)


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> int:
	print(f"\n$ cd {cwd} && {' '.join(command)}")
	completed = subprocess.run(command, cwd=cwd, env=env)
	return completed.returncode


def preflight(bench: BenchTarget) -> list[str]:
	errors: list[str] = []
	if not bench.root.exists():
		errors.append(f"{bench.label}: bench root not found: {bench.root}")
	if not (bench.root / "sites" / bench.site).exists():
		errors.append(f"{bench.label}: site not found: {bench.site}")
	if not (bench.root / "apps" / APP).exists():
		errors.append(f"{bench.label}: app is not linked under {bench.root / 'apps' / APP}")
	return errors


def coverage_xml_candidates(bench: BenchTarget) -> tuple[Path, Path]:
	return (
		bench.root / "sites" / "coverage.xml",
		bench.root / "coverage.xml",
	)


def coverage_xml_path(bench: BenchTarget) -> Path:
	candidates = coverage_xml_candidates(bench)
	for candidate in candidates:
		if candidate.exists():
			return candidate
	return candidates[0]


def run_python_gate(bench: BenchTarget) -> int:
	result_dir = APP_ROOT / "coverage-results" / "python"
	result_dir.mkdir(parents=True, exist_ok=True)
	xml_copy = result_dir / f"{bench.label}-coverage.xml"
	summary = result_dir / f"{bench.label}-summary.json"

	for candidate in coverage_xml_candidates(bench):
		if candidate.exists():
			candidate.unlink()

	code = run(
		["bench", "--site", bench.site, "run-tests", "--app", APP, "--coverage"],
		cwd=bench.root,
	)
	if code != 0:
		print(f"{bench.label}: Python tests failed before coverage could be checked", file=sys.stderr)
		return code

	xml_path = coverage_xml_path(bench)
	if not xml_path.exists():
		print(f"{bench.label}: expected coverage XML not found at {xml_path}", file=sys.stderr)
		return 2
	shutil.copyfile(xml_path, xml_copy)
	return run(
		[
			sys.executable,
			str(APP_ROOT / "scripts" / "check_python_coverage.py"),
			"--xml",
			str(xml_copy),
			"--threshold",
			THRESHOLD,
			"--report",
			str(summary),
		],
		cwd=APP_ROOT,
	)


def run_e2e_gate(bench: BenchTarget) -> int:
	result_dir = APP_ROOT / "coverage-results" / "e2e"
	result_dir.mkdir(parents=True, exist_ok=True)
	report = result_dir / f"{bench.label}-flow-coverage.json"
	env = os.environ.copy()
	env["SCL_FLOW_COVERAGE_OUTPUT"] = str(report)

	code = run(
		["bench", "--site", bench.site, "run-ui-tests", "--headless", APP],
		cwd=bench.root,
		env=env,
	)
	if code != 0:
		print(f"{bench.label}: Cypress tests failed before flow coverage could be checked", file=sys.stderr)
		return code

	return run(
		[
			sys.executable,
			str(APP_ROOT / "scripts" / "check_e2e_flow_coverage.py"),
			"--report",
			str(report),
			"--threshold",
			THRESHOLD,
		],
		cwd=APP_ROOT,
	)


def selected_benches(name: str) -> tuple[BenchTarget, ...]:
	if name == "all":
		return BENCHES
	return tuple(bench for bench in BENCHES if bench.label == name)


def main() -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--bench", choices=("all", "bench15", "bench16"), default="all")
	parser.add_argument("--skip-python", action="store_true")
	parser.add_argument("--skip-e2e", action="store_true")
	args = parser.parse_args()

	if args.skip_python and args.skip_e2e:
		print("At least one coverage gate must run; do not pass both --skip-python and --skip-e2e", file=sys.stderr)
		return 2

	targets = selected_benches(args.bench)
	errors = [error for bench in targets for error in preflight(bench)]
	if errors:
		for error in errors:
			print(error, file=sys.stderr)
		return 2

	results: list[tuple[str, str, int]] = []
	for bench in targets:
		if not args.skip_python:
			results.append((bench.label, "python", run_python_gate(bench)))
		if not args.skip_e2e:
			results.append((bench.label, "e2e", run_e2e_gate(bench)))

	print("\nCoverage gate summary")
	for bench_label, gate, code in results:
		status = "PASS" if code == 0 else f"FAIL({code})"
		print(f"{bench_label:7} {gate:6} {status}")

	if any(code == 2 for _bench, _gate, code in results):
		return 2
	if any(code != 0 for _bench, _gate, code in results):
		return 1
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
