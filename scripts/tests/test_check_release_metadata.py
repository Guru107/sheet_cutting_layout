from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import check_release_metadata
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

	def test_require_unreleased_section_ignores_plain_text_mentions(self) -> None:
		with tempfile.TemporaryDirectory() as tmp:
			changelog = Path(tmp) / "CHANGELOG.md"
			changelog.write_text(
				"# Changelog\n\nNotes about ## [Unreleased] without a heading\n",
				encoding="utf-8",
			)
			with self.assertRaisesRegex(ValueError, "Unreleased"):
				require_unreleased_section(changelog)

	def test_require_changelog_heading_ignores_plain_text_mentions(self) -> None:
		with tempfile.TemporaryDirectory() as tmp:
			changelog = Path(tmp) / "CHANGELOG.md"
			changelog.write_text(
				"# Changelog\n\n## [Unreleased]\n\nMentioned here: ## [1.0.0] - 2026-06-26\n",
				encoding="utf-8",
			)
			with self.assertRaisesRegex(ValueError, "1.0.0"):
				require_changelog_heading(changelog, "1.0.0")

	def test_main_returns_clean_error_for_validation_failure(self) -> None:
		with (
			mock.patch.object(check_release_metadata, "extract_version", return_value="1.0.0"),
			mock.patch.object(
				check_release_metadata,
				"require_unreleased_section",
				side_effect=ValueError("missing unreleased heading"),
			),
			mock.patch("sys.argv", ["check_release_metadata.py"]),
			mock.patch("sys.stderr") as stderr,
		):
			self.assertEqual(check_release_metadata.main(), 1)
			stderr.write.assert_any_call("missing unreleased heading")
			stderr.write.assert_any_call("\n")

	def test_main_returns_clean_error_for_missing_file(self) -> None:
		with (
			mock.patch.object(check_release_metadata, "extract_version", return_value="1.0.0"),
			mock.patch.object(
				check_release_metadata,
				"require_unreleased_section",
				side_effect=FileNotFoundError("CHANGELOG.md not found"),
			),
			mock.patch("sys.argv", ["check_release_metadata.py"]),
			mock.patch("sys.stderr") as stderr,
		):
			self.assertEqual(check_release_metadata.main(), 1)
			stderr.write.assert_any_call("CHANGELOG.md not found")
			stderr.write.assert_any_call("\n")


if __name__ == "__main__":
	unittest.main()
