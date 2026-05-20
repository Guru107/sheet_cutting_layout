import unittest
from pathlib import Path

import sheet_cutting_layout
from sheet_cutting_layout import hooks


class TestBootstrapContracts(unittest.TestCase):
    def test_package_exposes_semver_version(self):
        version = sheet_cutting_layout.__version__

        self.assertRegex(version, r"^\d+\.\d+\.\d+$")

    def test_hooks_metadata_matches_package_identity(self):
        self.assertEqual(hooks.app_name, "sheet_cutting_layout")
        self.assertEqual(hooks.app_title, "Sheet Cutting Layout")
        self.assertEqual(hooks.app_license, "mit")

    def test_patch_registry_contains_required_sections(self):
        package_root = Path(sheet_cutting_layout.__file__).resolve().parent
        patch_file = package_root / "patches.txt"
        content = patch_file.read_text(encoding="utf-8")

        self.assertIn("[pre_model_sync]", content)
        self.assertIn("[post_model_sync]", content)


if __name__ == "__main__":
    unittest.main()
