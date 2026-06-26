from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_release_metadata import (
	extract_version,
	is_semver,
	require_changelog_heading,
	require_unreleased_section,
)


class ReleaseMetadataTests(unittest.TestCase):
	def test_extract_version_reads_init_file(self) -> None:
		with tempfile.TemporaryDirectory() as tmp:
			init_file = Path(tmp) / "__init__.py"
			init_file.write_text('__version__ = "1.2.3"\n', encoding="utf-8")
			self.assertEqual(extract_version(init_file), "1.2.3")

	def test_is_semver_accepts_three_part_version(self) -> None:
		self.assertTrue(is_semver("1.0.0"))
		self.assertFalse(is_semver("1.0"))

	def test_require_unreleased_section_fails_when_missing(self) -> None:
		with tempfile.TemporaryDirectory() as tmp:
			changelog = Path(tmp) / "CHANGELOG.md"
			changelog.write_text("# Changelog\n", encoding="utf-8")
			with self.assertRaisesRegex(ValueError, "Unreleased"):
				require_unreleased_section(changelog)

	def test_require_changelog_heading_finds_version_heading(self) -> None:
		with tempfile.TemporaryDirectory() as tmp:
			changelog = Path(tmp) / "CHANGELOG.md"
			changelog.write_text(
				"# Changelog\n\n## [Unreleased]\n\n## [1.0.0] - 2026-06-26\n",
				encoding="utf-8",
			)
			require_changelog_heading(changelog, "1.0.0")


if __name__ == "__main__":
	unittest.main()
