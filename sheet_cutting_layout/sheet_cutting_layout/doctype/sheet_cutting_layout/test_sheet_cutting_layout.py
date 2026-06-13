from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase
from sheet_cutting_layout.tests.factories import (
	make_layout,
	make_release_ready_layout,
)

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
	def test_validate_only_runs_validator_no_workflow_side_effects(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"

		with patch.object(controller, "validate_sheet_cutting_layout") as validate:
			doc.validate()

		validate.assert_called_once_with(doc)
		self.assertFalse(hasattr(controller.SheetCuttingLayout, "before_workflow_action"))
		self.assertFalse(hasattr(controller, "apply_sheet_cutting_layout_workflow"))

	def test_on_submit_releases_and_snapshots_when_status_released(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"
		doc.status = "Released"

		with (
			patch.object(controller, "release_layout") as release,
			patch.object(controller, "record_approval_snapshot") as snapshot,
			patch.object(controller, "_get_session_user", return_value="Administrator"),
			patch.object(controller, "_get_now_datetime", return_value="2026-06-13T12:00:00"),
		):
			doc.on_submit()

		release.assert_called_once_with(doc)
		snapshot.assert_called_once_with(
			doc,
			action="MR Release",
			approver="Administrator",
			decision_time="2026-06-13T12:00:00",
		)

	def test_on_submit_does_not_snapshot_or_release_when_not_released(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"
		doc.status = "Approved by Purchase"

		with (
			patch.object(controller, "release_layout") as release,
			patch.object(controller, "record_approval_snapshot") as snapshot,
		):
			doc.on_submit()

		release.assert_not_called()
		snapshot.assert_not_called()

	def test_before_cancel_snapshots_supersede(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"

		with (
			patch.object(controller, "record_approval_snapshot") as snapshot,
			patch.object(controller, "_get_session_user", return_value="Administrator"),
			patch.object(controller, "_get_now_datetime", return_value="2026-06-13T12:00:00"),
		):
			doc.before_cancel()

		snapshot.assert_called_once_with(
			doc,
			action="Supersede",
			approver="Administrator",
			decision_time="2026-06-13T12:00:00",
		)

	def test_on_cancel_retires_layout_without_snapshot(self) -> None:
		doc = object.__new__(controller.SheetCuttingLayout)
		doc.doctype = "Sheet Cutting Layout"

		with (
			patch.object(controller, "retire_layout") as retire,
			patch.object(controller, "record_approval_snapshot") as snapshot,
		):
			doc.on_cancel()

		retire.assert_called_once_with(doc)
		snapshot.assert_not_called()

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

	def test_parent_finished_part_inputs_persist_without_child_rows(self) -> None:
		layout = make_layout(
			finished_part_code="FG01SHR",
			net_weight_per_part_kg=0.289,
			generated_bom=None,
		)
		layout.parts_per_strip = 1
		layout.no_of_strips = 1
		layout.strip_length_mm = 2500

		layout.insert()
		layout.reload()

		self.assertEqual(layout.finished_part_code, "FG01SHR")
		self.assertEqual(layout.net_weight_per_part_kg, 0.289)
		self.assertFalse(layout.finished_parts)

	def test_parent_formulas_derive_weights_without_child_inputs(self) -> None:
		layout = make_layout(
			finished_part_code="FG01SHR",
			net_weight_per_part_kg=0.289,
			generated_bom=None,
		)
		layout.parts_per_strip = 1
		layout.no_of_strips = 1
		layout.strip_length_mm = 2500
		layout.insert()

		layout.parts_per_strip = 7
		layout.no_of_strips = 11
		layout.sheet_length_mm = 3713.6
		layout.strip_thickness_mm = 1
		layout.strip_width_mm = 1250
		layout.strip_length_mm = 337.6
		layout.net_weight_per_part_kg = 0.289
		layout.save()

		self.assertEqual(layout.parts_per_sheet, 77)
		self.assertAlmostEqual(layout.gross_weight_per_part_kg, 3.31692 / 7, places=6)
		self.assertAlmostEqual(
			layout.scrap_weight_per_part_kg,
			layout.gross_weight_per_part_kg - 0.289,
			places=6,
		)

	def test_mr_release_generates_native_bom_with_test_uom_items(self) -> None:
		layout = make_release_ready_layout()

		layout.status = "Released"
		layout.on_submit()

		self.assertEqual(layout.status, "Released")
		self.assertTrue(layout.generated_bom)

	def test_native_submit_persists_release_artifacts_after_reload(self) -> None:
		layout = make_release_ready_layout()

		# D-1 moves side effects to native on_submit, while D-5 will align the
		# workflow fixture so user-facing MR Release reaches this status naturally.
		layout.status = "Released"
		layout.submit()
		generated_bom = layout.generated_bom

		layout.reload()

		self.assertEqual(layout.status, "Released")
		self.assertEqual(layout.generated_bom, generated_bom)
		self.assertEqual(len(layout.finished_parts), 1)
		self.assertEqual(layout.finished_parts[0].generated_bom, generated_bom)
		self.assertEqual(len(layout.approval_snapshot), 1)
		self.assertEqual(layout.approval_snapshot[0].step_name, "MR Approval")
		self.assertEqual(layout.approval_snapshot[0].decision, "Approved")

	def test_native_cancel_persists_supersession_snapshot_after_reload(self) -> None:
		layout = make_release_ready_layout()
		layout.status = "Released"
		layout.submit()

		layout.cancel()
		layout.reload()

		snapshot_steps = [row.step_name for row in layout.approval_snapshot]
		self.assertIn("Supersession", snapshot_steps)
