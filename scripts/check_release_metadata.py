#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = APP_ROOT / "sheet_cutting_layout" / "__init__.py"
CHANGELOG_FILE = APP_ROOT / "CHANGELOG.md"
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
UNRELEASED_HEADING_RE = re.compile(r"^[ \t]{0,3}##\s+\[Unreleased\]\s*$", re.MULTILINE)


def extract_version(path: Path) -> str:
	for line in path.read_text(encoding="utf-8").splitlines():
		if line.startswith("__version__ = "):
			return line.split("=", 1)[1].strip().strip('"')
	raise ValueError(f"__version__ not found in {path}")


def is_semver(value: str) -> bool:
	return bool(SEMVER_RE.fullmatch(value))


def require_unreleased_section(path: Path) -> None:
	content = path.read_text(encoding="utf-8")
	if not UNRELEASED_HEADING_RE.search(content):
		raise ValueError("CHANGELOG.md must contain an Unreleased section")


def require_changelog_heading(path: Path, version: str) -> None:
	content = path.read_text(encoding="utf-8")
	heading_re = re.compile(
		rf"^[ \t]{{0,3}}##\s+\[{re.escape(version)}\]\s+-\s+.+$",
		re.MULTILINE,
	)
	if not heading_re.search(content):
		raise ValueError(f"CHANGELOG.md must contain a heading for version {version}")


def normalize_tag(tag: str) -> str:
	return tag[1:] if tag.startswith("v") else tag


def main() -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--tag", help="Release tag such as v1.0.0")
	args = parser.parse_args()

	version = extract_version(VERSION_FILE)
	if not is_semver(version):
		print(f"Version is not semantic: {version}", file=sys.stderr)
		return 1

	try:
		require_unreleased_section(CHANGELOG_FILE)
		require_changelog_heading(CHANGELOG_FILE, version)
	except (FileNotFoundError, ValueError) as exc:
		print(str(exc), file=sys.stderr)
		return 1

	if args.tag:
		tag_version = normalize_tag(args.tag)
		if not is_semver(tag_version):
			print(f"Tag is not semantic: {args.tag}", file=sys.stderr)
			return 1
		if tag_version != version:
			print(
				f"Version mismatch: tag {args.tag} does not match __version__ {version}",
				file=sys.stderr,
			)
			return 1

	print(f"Release metadata OK for version {version}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
