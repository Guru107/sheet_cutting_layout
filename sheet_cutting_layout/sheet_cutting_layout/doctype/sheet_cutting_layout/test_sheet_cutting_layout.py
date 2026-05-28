from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import patch

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase

from . import sheet_cutting_layout as controller


@dataclass
class _FakeLayoutDoc:
	name: str = "SCL-TEST-001"
	doctype: str = "Sheet Cutting Layout"
	check_permission_calls: list[str] | None = None
	inserted: bool = False

	def check_permission(self, permission_type: str) -> None:
		if self.check_permission_calls is None:
			self.check_permission_calls = []
		self.check_permission_calls.append(permission_type)

	def insert(self) -> None:
		self.inserted = True


class TestSheetCuttingLayoutController(SheetCuttingLayoutTestCase):
	def test_validate_delegates_to_validator(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"

		with (
			patch.object(controller, "_get_selected_workflow_action", return_value=None),
			patch.object(controller, "validate_sheet_cutting_layout") as validate_sheet_cutting_layout,
		):
			doc.validate()

		validate_sheet_cutting_layout.assert_called_once_with(doc)

	def test_validate_mr_release_triggers_checker_snapshot_and_release_once(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"

		with (
			patch.object(controller, "_get_selected_workflow_action", return_value="MR Release"),
			patch.object(controller, "apply_checker_action") as apply_checker_action,
			patch.object(controller, "record_approval_snapshot") as record_approval_snapshot,
			patch.object(controller, "get_release_context", return_value="CTX") as get_release_context,
			patch.object(controller, "release_layout") as release_layout,
			patch.object(controller, "validate_sheet_cutting_layout") as validate_sheet_cutting_layout,
			patch.object(controller, "_get_session_user", return_value="Administrator"),
			patch.object(controller, "_get_now_datetime", return_value="2026-05-28T12:00:00"),
		):
			doc.validate()

		apply_checker_action.assert_called_once_with(doc, "MR Release")
		record_approval_snapshot.assert_called_once()
		get_release_context.assert_called_once_with(doc)
		release_layout.assert_called_once_with(doc, release_context="CTX")
		validate_sheet_cutting_layout.assert_called_once_with(doc)

	def test_generate_end_piece_boms_checks_write_permission_and_calls_service(self) -> None:
		doc = _FakeLayoutDoc(name="SCL-TEST-002")
		calls: list[tuple[str, str]] = []

		class _FakeFrappe:
			@staticmethod
			def get_doc(doctype: str, name: str) -> _FakeLayoutDoc:
				calls.append((doctype, name))
				return doc

		with (
			patch.object(controller, "frappe", _FakeFrappe),
			patch.object(
				controller,
				"generate_end_piece_boms",
				return_value={"items": ["FG001SHR-EP-1x1250x260"], "boms": ["BOM-EP-001"]},
			) as generate_end_piece_boms,
		):
			result = controller.generate_sheet_cutting_layout_end_piece_boms("SCL-TEST-002")

		self.assertEqual(result["items"], ["FG001SHR-EP-1x1250x260"])
		self.assertEqual(result["boms"], ["BOM-EP-001"])
		self.assertEqual(calls, [("Sheet Cutting Layout", "SCL-TEST-002")])
		self.assertEqual(doc.check_permission_calls, ["write"])
		generate_end_piece_boms.assert_called_once_with(doc)

	def test_create_revision_inserts_new_doc_and_returns_name(self) -> None:
		old_doc = _FakeLayoutDoc(name="SCL-TEST-003")
		new_doc = _FakeLayoutDoc(name="SCL-TEST-003-R1")

		class _FakeFrappe:
			@staticmethod
			def get_doc(doctype: str, name: str) -> _FakeLayoutDoc:
				self.assertEqual(doctype, "Sheet Cutting Layout")
				self.assertEqual(name, "SCL-TEST-003")
				return old_doc

		with (
			patch.object(controller, "frappe", _FakeFrappe),
			patch.object(controller, "create_revision", return_value=new_doc) as create_revision,
		):
			revision_name = controller.create_sheet_cutting_layout_revision("SCL-TEST-003")

		self.assertTrue(new_doc.inserted)
		self.assertEqual(revision_name, "SCL-TEST-003-R1")
		create_revision.assert_called_once_with(old_doc)

	def test_apply_workflow_sets_selected_action_only_for_sheet_cutting_layout(self) -> None:
		flags = SimpleNamespace()
		parsed_doc = {"doctype": "Sheet Cutting Layout", "name": "SCL-TEST-004"}
		apply_workflow_calls: list[tuple[object, str, str | None]] = []

		def _fake_apply_workflow(doc: object, action: str) -> str:
			apply_workflow_calls.append((doc, action, getattr(flags, "selected_workflow_action", None)))
			return "ok"

		fake_frappe = SimpleNamespace(
			flags=flags,
			parse_json=lambda _doc: parsed_doc,
		)

		with (
			patch.object(controller, "frappe", fake_frappe),
			patch.object(
				controller, "import_module", return_value=SimpleNamespace(apply_workflow=_fake_apply_workflow)
			),
		):
			result = controller.apply_sheet_cutting_layout_workflow(
				{"doctype": "Sheet Cutting Layout"}, "MR Release"
			)

		self.assertEqual(result, "ok")
		self.assertEqual(
			apply_workflow_calls, [({"doctype": "Sheet Cutting Layout"}, "MR Release", "MR Release")]
		)
		self.assertFalse(hasattr(flags, "selected_workflow_action"))
