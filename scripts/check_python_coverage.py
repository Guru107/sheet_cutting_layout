#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

DEFAULT_THRESHOLD = 96.0
DEFAULT_FILE_THRESHOLD = 90.0
APP_ROOT = Path(__file__).resolve().parents[1]

EXCLUDED_PATTERNS = (
	"scripts/*.py",
	"scripts/tests/*",
	"sheet_cutting_layout/__init__.py",
	"sheet_cutting_layout/**/__init__.py",
	"sheet_cutting_layout/config/*",
	"sheet_cutting_layout/patches/*",
	"sheet_cutting_layout/tests/*",
	"sheet_cutting_layout/**/doctype/*/*_dashboard.py",
)

PASS_THROUGH_DOCTYPES = (
	"sheet_cutting_layout/sheet_cutting_layout/doctype/layout_approval_snapshot/layout_approval_snapshot.py",
	"sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.py",
	"sheet_cutting_layout/sheet_cutting_layout/doctype/layout_finished_part/layout_finished_part.py",
	"sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout_settings/sheet_cutting_layout_settings.py",
)


def _matches(filename: str, patterns: tuple[str, ...]) -> bool:
	return any(fnmatch.fnmatch(filename, pattern) for pattern in patterns)


def _is_pass_only_file(filename: str) -> bool:
	path = Path(filename)
	if not path.is_absolute():
		path = APP_ROOT / path
	try:
		tree = ast.parse(path.read_text())
	except (OSError, SyntaxError):
		return False

	body = [
		node
		for node in tree.body
		if not isinstance(node, ast.Import | ast.ImportFrom)
		and not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
	]
	return bool(body) and all(
		isinstance(node, ast.ClassDef) and len(node.body) == 1 and isinstance(node.body[0], ast.Pass)
		for node in body
	)


def _is_excluded(filename: str) -> bool:
	return _matches(filename, EXCLUDED_PATTERNS) or (
		filename in PASS_THROUGH_DOCTYPES and _is_pass_only_file(filename)
	)


def _line_numbers(class_node: ET.Element) -> tuple[int, int, list[int]]:
	valid = 0
	covered = 0
	missing: list[int] = []
	lines = class_node.find("lines")
	for line in lines.findall("line") if lines is not None else []:
		valid += 1
		number = int(line.attrib["number"])
		if int(line.attrib.get("hits", "0")) > 0:
			covered += 1
		else:
			missing.append(number)
	return valid, covered, missing


def summarize(xml_path: Path) -> dict[str, object]:
	root = ET.parse(xml_path).getroot()
	files: list[dict[str, object]] = []
	total_valid = 0
	total_covered = 0

	for class_node in root.findall(".//class"):
		filename = class_node.attrib["filename"]
		if _is_excluded(filename):
			continue
		valid, covered, missing = _line_numbers(class_node)
		if valid == 0:
			continue
		total_valid += valid
		total_covered += covered
		files.append(
			{
				"file": filename,
				"valid": valid,
				"covered": covered,
				"missing": missing,
				"percent": round(covered / valid * 100, 2),
			}
		)

	percent = 0.0 if total_valid == 0 else total_covered / total_valid * 100
	return {
		"percent": round(percent, 2),
		"covered": total_covered,
		"valid": total_valid,
		"files": sorted(files, key=lambda item: (item["percent"], item["file"])),
	}


def main() -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--xml", required=True, type=Path)
	parser.add_argument("--threshold", default=DEFAULT_THRESHOLD, type=float)
	parser.add_argument("--file-threshold", default=DEFAULT_FILE_THRESHOLD, type=float)
	parser.add_argument("--report", type=Path)
	args = parser.parse_args()

	if not args.xml.exists():
		print(f"coverage XML not found: {args.xml}", file=sys.stderr)
		return 2

	summary = summarize(args.xml)
	if args.report:
		args.report.parent.mkdir(parents=True, exist_ok=True)
		args.report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

	print(f"Python coverage: {summary['percent']}% ({summary['covered']}/{summary['valid']} lines)")
	if int(summary["valid"]) == 0:
		print("No project-owned Python lines found in coverage XML", file=sys.stderr)
		return 2
	if float(summary["percent"]) <= args.threshold:
		print(f"Coverage must be above {args.threshold}%. Lowest files:", file=sys.stderr)
		for item in summary["files"][:10]:
			missing = ",".join(str(line) for line in item["missing"][:20])
			print(f"  {item['percent']}% {item['file']} missing {missing}", file=sys.stderr)
		return 1
	low_files = [item for item in summary["files"] if float(item["percent"]) < args.file_threshold]
	if low_files:
		print(f"Each included file must be at least {args.file_threshold}% covered:", file=sys.stderr)
		for item in low_files[:10]:
			missing = ",".join(str(line) for line in item["missing"][:20])
			print(f"  {item['percent']}% {item['file']} missing {missing}", file=sys.stderr)
		return 1
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
