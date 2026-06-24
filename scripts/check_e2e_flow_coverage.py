#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_MANIFEST = Path("cypress/support/current_flows.json")
DEFAULT_THRESHOLD = 96.0


def _load_json(path: Path, label: str) -> object:
	if not path.exists():
		print(f"{label} not found: {path}", file=sys.stderr)
		raise SystemExit(2)
	try:
		return json.loads(path.read_text())
	except json.JSONDecodeError as exc:
		print(f"invalid {label} JSON: {path}: {exc}", file=sys.stderr)
		raise SystemExit(2) from exc


def _load_manifest(path: Path) -> list[dict[str, str]]:
	data = _load_json(path, "manifest")
	if not isinstance(data, list) or any(
		not isinstance(flow, dict)
		or set(flow) != {"id", "label"}
		or not isinstance(flow["id"], str)
		or not isinstance(flow["label"], str)
		for flow in data
	):
		print(f"invalid manifest shape: {path}", file=sys.stderr)
		raise SystemExit(2)
	return data


def _load_report(path: Path) -> dict[str, object]:
	data = _load_json(path, "report")
	if (
		not isinstance(data, dict)
		or "covered" not in data
		or not isinstance(data["covered"], list)
		or any(not isinstance(flow_id, str) for flow_id in data["covered"])
		or ("runId" in data and data["runId"] is not None and not isinstance(data["runId"], str))
	):
		print(f"invalid report shape: {path}", file=sys.stderr)
		raise SystemExit(2)
	return data


def main() -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--manifest", default=DEFAULT_MANIFEST, type=Path)
	parser.add_argument("--report", required=True, type=Path)
	parser.add_argument("--threshold", default=DEFAULT_THRESHOLD, type=float)
	parser.add_argument("--run-id")
	args = parser.parse_args()

	manifest = _load_manifest(args.manifest)
	manifest_ids = [flow["id"] for flow in manifest]
	if not manifest_ids:
		print("manifest must define at least one current E2E flow", file=sys.stderr)
		return 2
	manifest_id_set = set(manifest_ids)
	report = _load_report(args.report)
	if not args.run_id:
		print(
			"report run ID required; use run_current_coverage_gates.py for current E2E gates", file=sys.stderr
		)
		return 2
	if args.run_id and report.get("runId") != args.run_id:
		print("report run ID does not match current E2E run", file=sys.stderr)
		return 2
	covered_ids = report["covered"]
	unknown_ids = sorted(set(covered_ids) - manifest_id_set)
	if unknown_ids:
		print("Unknown covered flow IDs:", file=sys.stderr)
		for flow_id in unknown_ids:
			print(flow_id, file=sys.stderr)
		return 1

	covered_current_count = len({flow_id for flow_id in covered_ids if flow_id in manifest_id_set})
	total_current_flows = len(manifest_ids)
	percent = covered_current_count / total_current_flows * 100
	missing_ids = [flow_id for flow_id in manifest_ids if flow_id not in covered_ids]

	print(f"E2E flow coverage: {covered_current_count}/{total_current_flows} " f"({percent:.2f}%)")
	if missing_ids:
		for flow_id in missing_ids:
			print(flow_id)

	if percent <= args.threshold:
		return 1
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
