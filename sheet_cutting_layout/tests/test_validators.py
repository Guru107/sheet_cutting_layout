from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import patch

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


class ValidationError(Exception):
	pass


class FakeFrappe:
	ValidationError = ValidationError

	def __init__(self) -> None:
		self.float_precision: str | None = None
		self.generated_bom_doc: object | None = None

	def get_system_settings(self, fieldname: str) -> str | None:
		if fieldname == "float_precision":
			return self.float_precision
		return None

	def get_doc(self, doctype: str, name: str) -> object:
		if (doctype, name) == ("BOM", "BOM-FG01SHR"):
			return self.generated_bom_doc
		raise AssertionError(f"unexpected get_doc({doctype!r}, {name!r})")

	def throw(self, message: str) -> None:
		raise ValidationError(message)


@dataclass
class FinishedPart:
	finished_part_item: str
	parts_per_sheet: int
	gross_weight_per_part_kg: float
	scrap_weight_per_part_kg: float = 0
	net_weight_per_part_kg: float | None = None


@dataclass
class EndPiece:
	end_piece_item_code: str | None = None
	generated_end_piece_item: str | None = None
	generated_end_piece_bom: str | None = None
	child_layout: str | None = None
	weight_kg: float | None = 2.5545
	width_mm: float | None = 1250
	length_mm: float | None = 260
	disposition: str | None = "Reuse"
	used_for_finished_part: str | None = "FG01SHR"
	bom_quantity: float | None = 1
	net_weight_per_part_kg: float | None = 2.0
	gross_weight_per_part_kg: float | None = None
	scrap_weight_per_part_kg: float | None = None
	bom_scrap_quantity_kg: float | None = 0
	scrap_item: str | None = ""


class ExistingEndPiece(EndPiece):
	def __init__(
		self,
		*,
		previous_code: str | None,
		current_code: str | None,
		changed: bool = True,
		**kwargs: object,
	) -> None:
		super().__init__(end_piece_item_code=current_code, **kwargs)
		self._previous_code = previous_code
		self._changed = changed

	def has_value_changed(self, fieldname: str) -> bool:
		return fieldname == "end_piece_item_code" and self._changed

	def get_db_value(self, fieldname: str) -> str | None:
		if fieldname == "end_piece_item_code":
			return self._previous_code
		return None


@dataclass
class Layout:
	finished_part_code: str | None = "AB12SHR"
	is_lh_rh: int = 0
	twin_finished_part: str | None = None
	net_weight_per_part_kg: float | None = 11.004
	generated_bom: str | None = None
	finished_parts: list[FinishedPart] = field(default_factory=list)
	end_pieces: list[EndPiece] = field(default_factory=list)
	raw_material_item: str = "RM001"
	process_scrap_item: str = "PROCESSSCRAP001"
	end_piece_bom_status: str = ""
	sheet_thickness_mm: float = 1
	sheet_width_mm: float = 1250
	sheet_length_mm: float = 2500
	weight_per_sheet_kg: float = 0
	strip_thickness_mm: float = 1
	strip_width_mm: float = 1250
	strip_length_mm: float = 260
	weight_of_strip_kg: float = 0
	gross_weight_per_part_kg: float = 0
	scrap_weight_per_part_kg: float = 0
	parts_per_strip: int = 2
	no_of_strips: int | None = 1
	parts_per_sheet: int = 0
	consumed_weight_kg: float = 0
	leftover_weight_kg: float = 0
	consumption_status: str = ""


class TestValidators(SheetCuttingLayoutTestCase):
	def setUp(self) -> None:
		super().setUp()
		self.fake_frappe = FakeFrappe()
		self.validators = importlib.import_module("sheet_cutting_layout.services.validators")
		self._frappe_patch = patch.object(self.validators, "frappe", self.fake_frappe)
		self._translation_patch = patch.object(self.validators, "_", lambda message: message)
		self._frappe_patch.start()
		self._translation_patch.start()
		self.addCleanup(self._frappe_patch.stop)
		self.addCleanup(self._translation_patch.stop)

	def test_legacy_end_piece_multiplicity_guard_is_removed(self) -> None:
		import inspect
		from pathlib import Path

		from sheet_cutting_layout.services import bom_service, release_service, validators

		legacy_field = "qty" + "_per_sheet"
		repo_root = Path(__file__).resolve().parents[2]
		layout_end_piece_json = repo_root / (
			"sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json"
		)
		consumption_spec = repo_root / "cypress/integration/sheet_cutting_layout_consumption.js"

		validators_source = inspect.getsource(validators)
		self.assertNotIn(legacy_field, validators_source)
		self.assertNotIn("_validate_unreleased_legacy_end_piece_multiplicity", validators_source)
		self.assertNotIn(legacy_field, inspect.getsource(bom_service))
		self.assertNotIn(legacy_field, inspect.getsource(release_service))
		self.assertNotIn(legacy_field, layout_end_piece_json.read_text())
		self.assertNotIn(legacy_field, consumption_spec.read_text())

	def _balanced_layout(
		self,
		*,
		finished_part: FinishedPart | None = None,
		end_piece: EndPiece | None = None,
	) -> Layout:
		accounted_finished_part = finished_part or FinishedPart("AB12SHR", 2, 11.004, 0)
		strip_weight = (
			accounted_finished_part.gross_weight_per_part_kg * accounted_finished_part.parts_per_sheet
		)
		net_weight = (
			accounted_finished_part.net_weight_per_part_kg
			if accounted_finished_part.net_weight_per_part_kg is not None
			else accounted_finished_part.gross_weight_per_part_kg
			- accounted_finished_part.scrap_weight_per_part_kg
		)
		return Layout(
			finished_part_code=accounted_finished_part.finished_part_item,
			net_weight_per_part_kg=net_weight,
			strip_length_mm=strip_weight * 1_000_000 / (1 * 1250 * 7.86),
			weight_of_strip_kg=strip_weight,
			gross_weight_per_part_kg=accounted_finished_part.gross_weight_per_part_kg,
			scrap_weight_per_part_kg=accounted_finished_part.scrap_weight_per_part_kg,
			parts_per_sheet=accounted_finished_part.parts_per_sheet,
			finished_parts=[],
			end_pieces=[end_piece or EndPiece()],
		)

	def _layout_with_generated_bom(self, *, bom_quantity: int) -> Layout:
		self.fake_frappe.generated_bom_doc = type(
			"Bom",
			(),
			{
				"item": "FG01SHR",
				"quantity": bom_quantity,
				"items": [type("BomItem", (), {"item_code": "RM001", "qty": 77.0})()],
				"scrap_items": [],
			},
		)()
		return Layout(
			finished_part_code="FG01SHR",
			net_weight_per_part_kg=1.0,
			generated_bom="BOM-FG01SHR",
			finished_parts=[],
			end_pieces=[],
			sheet_thickness_mm=None,
			sheet_width_mm=None,
			sheet_length_mm=None,
			weight_per_sheet_kg=77.0,
			strip_thickness_mm=None,
			strip_width_mm=None,
			strip_length_mm=None,
			weight_of_strip_kg=7.0,
			gross_weight_per_part_kg=1.0,
			scrap_weight_per_part_kg=0.0,
			parts_per_strip=7,
			no_of_strips=11,
			parts_per_sheet=77,
			consumed_weight_kg=0,
			leftover_weight_kg=0,
			consumption_status="",
		)

	def test_finished_part_item_code_validation_rules(self) -> None:
		with self.assertRaisesRegex(ValidationError, "alphanumeric"):
			self.validators.validate_finished_part_code("AB-12SHR")
		with self.assertRaisesRegex(ValidationError, "end with SHR"):
			self.validators.validate_finished_part_code("AB12")

		self.validators.validate_finished_part_code("AB12SHR")

	def test_layout_requires_parent_finished_part_code_even_when_child_rows_exist(self) -> None:
		with self.assertRaisesRegex(ValidationError, "Finished part code is required"):
			self.validators.validate_sheet_cutting_layout(Layout(finished_part_code="", finished_parts=[]))

		with self.assertRaisesRegex(ValidationError, "Finished part code is required"):
			self.validators.validate_sheet_cutting_layout(
				Layout(
					finished_part_code="",
					finished_parts=[
						FinishedPart("AB12SHR", 2, 11.004, 0),
					],
				)
			)

	def test_sheet_weight_uses_density_with_system_precision(self) -> None:
		self.assertEqual(
			self.validators.calculate_sheet_weight_kg(
				thickness_mm=1,
				width_mm=1250,
				length_mm=2500,
			),
			24.5625,
		)

		self.fake_frappe.float_precision = "1"
		self.assertEqual(
			self.validators.calculate_sheet_weight_kg(
				thickness_mm=10,
				width_mm=1000,
				length_mm=1000,
			),
			79.0,
		)

	def test_validators_sheet_weight_delegates_to_geometry(self) -> None:
		from sheet_cutting_layout.services import validators

		with patch(
			"sheet_cutting_layout.services.validators.geometry.sheet_weight_kg", return_value=99.0
		) as spy:
			result = validators.calculate_sheet_weight_kg(thickness_mm=1, width_mm=2, length_mm=3)

		self.assertEqual(result, 99.0)
		spy.assert_called_once_with(
			thickness_mm=1,
			width_mm=2,
			length_mm=3,
			precision=validators._calculation_precision(),
			density_precision=validators._float_precision(),
		)

	def test_strip_thickness_mirror_drives_strip_weight_formula(self) -> None:
		layout = self._balanced_layout()
		layout.sheet_thickness_mm = 2
		layout.strip_thickness_mm = 9
		layout.strip_width_mm = 1250
		layout.strip_length_mm = 260

		self.validators.apply_strip_thickness_mirror(layout)
		self.validators.apply_strip_weight_formula(layout)

		self.assertEqual(layout.strip_thickness_mm, 2)
		self.assertEqual(layout.weight_of_strip_kg, 5.109)

	def test_reuse_strip_fields_default_and_drive_weight(self) -> None:
		layout = SimpleNamespace(sheet_thickness_mm=2.0)
		row = SimpleNamespace(
			disposition="Reuse",
			width_mm=200.0,
			length_mm=300.0,
			strip_width_mm=None,
			strip_length_mm=None,
			strip_weight_kg=None,
		)

		self.validators.apply_end_piece_strip_weight_formulas(layout, [row])

		self.assertEqual(row.strip_width_mm, 200.0)
		self.assertEqual(row.strip_length_mm, 300.0)
		self.assertEqual(row.strip_weight_kg, 0.9432)

	def test_reuse_strip_dimensions_cannot_exceed_end_piece_dimensions(self) -> None:
		layout = SimpleNamespace(sheet_thickness_mm=2.0)
		row = SimpleNamespace(
			disposition="Reuse",
			width_mm=200.0,
			length_mm=300.0,
			strip_width_mm=201.0,
			strip_length_mm=300.0,
			strip_weight_kg=None,
		)

		with self.assertRaises(ValidationError):
			self.validators.apply_end_piece_strip_weight_formulas(layout, [row])

	def test_reuse_strip_length_cannot_exceed_end_piece_length(self) -> None:
		layout = SimpleNamespace(sheet_thickness_mm=2.0)
		row = SimpleNamespace(
			disposition="Reuse",
			width_mm=200.0,
			length_mm=300.0,
			strip_width_mm=200.0,
			strip_length_mm=301.0,
			strip_weight_kg=None,
		)

		with self.assertRaises(ValidationError):
			self.validators.apply_end_piece_strip_weight_formulas(layout, [row])

	def test_consumed_weight_uses_strip_for_reuse_and_total_weight_for_scrap(self) -> None:
		layout = SimpleNamespace(
			finished_part_code="FG01SHR",
			gross_weight_per_part_kg=1.0,
			parts_per_sheet=2,
		)
		rows = [
			SimpleNamespace(disposition="Reuse", weight_kg=10.0, strip_weight_kg=6.0),
			SimpleNamespace(disposition="Scrap", weight_kg=4.0, strip_weight_kg=1.0),
		]

		self.assertEqual(self.validators.calculate_consumed_weight_kg(layout, rows), 12.0)

	def test_validators_parent_gross_weight_delegates_to_geometry(self) -> None:
		from sheet_cutting_layout.services import validators

		with patch(
			"sheet_cutting_layout.services.validators.geometry.gross_weight_per_part_kg",
			return_value=12.345,
		) as spy:
			result = validators.calculate_parent_gross_weight_per_part_kg(
				weight_of_strip_kg=10,
				parts_per_strip=2,
			)

		self.assertEqual(result, 12.345)
		spy.assert_called_once_with(
			weight_of_strip_kg=10,
			parts_per_strip=2,
			precision=validators._calculation_precision(),
		)

	def test_validators_parts_per_sheet_delegates_to_geometry(self) -> None:
		from sheet_cutting_layout.services import validators

		with patch(
			"sheet_cutting_layout.services.validators.geometry.parts_per_sheet", return_value=42
		) as spy:
			result = validators.calculate_parts_per_sheet(parts_per_strip=6, no_of_strips=7)

		self.assertEqual(result, 42)
		spy.assert_called_once_with(parts_per_strip=6, no_of_strips=7)

	def test_strip_and_parts_formulas_derive_parent_fields_from_parent_inputs(self) -> None:
		layout = Layout(
			finished_part_code="AB12SHR",
			net_weight_per_part_kg=0.289,
			finished_parts=[FinishedPart("CHILDSHR", parts_per_sheet=999, gross_weight_per_part_kg=9.9)],
			end_pieces=[],
			parts_per_strip=7,
			no_of_strips=11,
			weight_of_strip_kg=3.31692,
		)

		self.validators.apply_parent_gross_weight_per_part_formula(layout)
		self.validators.apply_parent_scrap_weight_per_part_formula(layout)
		self.validators.apply_parts_per_sheet_formula(layout)

		self.assertEqual(layout.parts_per_sheet, 77)
		self.assertAlmostEqual(layout.gross_weight_per_part_kg, 3.31692 / 7, places=6)
		self.assertAlmostEqual(
			layout.scrap_weight_per_part_kg,
			layout.gross_weight_per_part_kg - 0.289,
			places=6,
		)

	def test_validation_derives_parent_part_quantities_and_weights_from_parent_inputs(self) -> None:
		layout = Layout(
			finished_part_code="FG01SHR",
			net_weight_per_part_kg=0.289,
			sheet_thickness_mm=None,
			sheet_width_mm=None,
			sheet_length_mm=None,
			weight_per_sheet_kg=36.48612,
			parts_per_strip=7,
			no_of_strips=11,
			weight_of_strip_kg=3.31692,
			strip_thickness_mm=None,
			strip_width_mm=None,
			strip_length_mm=None,
			end_pieces=[],
		)

		self.validators.validate_sheet_cutting_layout(layout)

		self.assertEqual(layout.parts_per_sheet, 77)
		self.assertAlmostEqual(layout.gross_weight_per_part_kg, 3.31692 / 7, places=6)
		self.assertAlmostEqual(
			layout.scrap_weight_per_part_kg,
			layout.gross_weight_per_part_kg - 0.289,
			places=6,
		)

		layout.net_weight_per_part_kg = layout.gross_weight_per_part_kg + 0.001
		with self.assertRaisesRegex(ValidationError, "Scrap weight per part cannot be negative"):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_strip_weight_recomputes_from_dimensions_even_when_prefilled(self) -> None:
		layout = Layout(
			strip_thickness_mm=1,
			strip_width_mm=1250,
			strip_length_mm=260,
			weight_of_strip_kg=999,
		)

		self.validators.apply_strip_weight_formula(layout)

		self.assertEqual(layout.weight_of_strip_kg, 2.5545)

	def test_parent_only_consumption_tracking_counts_finished_part_without_end_pieces(self) -> None:
		layout = Layout(
			finished_part_code="AB12SHR",
			net_weight_per_part_kg=1.27725,
			gross_weight_per_part_kg=1.277,
			finished_parts=[],
			end_pieces=[],
			parts_per_strip=2,
			no_of_strips=1,
		)

		self.validators.apply_parts_per_sheet_formula(layout)
		self.validators.apply_sheet_weight_formula(layout)
		self.validators.apply_consumption_tracking(layout, layout.end_pieces)

		self.assertEqual(layout.parts_per_sheet, 2)
		self.assertEqual(layout.consumed_weight_kg, 2.554)
		self.assertEqual(layout.consumption_status, "Short")

	def test_layout_without_end_pieces_still_requires_complete_sheet_consumption(self) -> None:
		layout = Layout(
			finished_part_code="AB12SHR",
			net_weight_per_part_kg=1.27725,
			finished_parts=[],
			end_pieces=[],
			parts_per_strip=2,
			no_of_strips=1,
		)

		with self.assertRaisesRegex(ValidationError, "There is no accounting for"):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_validation_uses_parent_finished_part_contract_even_when_child_rows_exist(self) -> None:
		layout = Layout(
			finished_part_code="AB12SHR",
			net_weight_per_part_kg=0.289,
			sheet_thickness_mm=None,
			sheet_width_mm=None,
			sheet_length_mm=None,
			weight_per_sheet_kg=36.48612,
			parts_per_strip=7,
			no_of_strips=11,
			weight_of_strip_kg=3.31692,
			strip_thickness_mm=None,
			strip_width_mm=None,
			strip_length_mm=None,
			gross_weight_per_part_kg=0.473846,
			scrap_weight_per_part_kg=0.184846,
			finished_parts=[
				FinishedPart(
					finished_part_item="BAD-CHILD",
					parts_per_sheet=999,
					gross_weight_per_part_kg=9.9,
					scrap_weight_per_part_kg=9.8,
				)
			],
			end_pieces=[],
		)

		self.validators.validate_sheet_cutting_layout(layout)

	def test_save_time_audit_rejects_legacy_strip_count_bom_quantity(self) -> None:
		layout = self._layout_with_generated_bom(bom_quantity=11)

		with self.assertRaisesRegex(ValidationError, "BOM quantity mismatch"):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_save_time_audit_accepts_corrected_parts_per_sheet_bom_quantity(self) -> None:
		layout = self._layout_with_generated_bom(bom_quantity=77)

		self.validators.validate_sheet_cutting_layout(layout)

	def test_derive_end_piece_item_code_uses_used_for_finished_part_and_trimmed_numbers(self) -> None:
		derived = self.validators.derive_end_piece_item_code(
			used_for_finished_part=" fg01shr ",
			thickness_mm="1.600000",
			width_mm="1250.0",
			length_mm="179.000000",
		)
		self.assertEqual(derived, "FG01SHR-EP-1.6x1250x179")

	def test_derive_end_piece_item_code_rejects_missing_or_non_positive_components(self) -> None:
		cases = [
			(
				dict(used_for_finished_part="", thickness_mm=1.6, width_mm=1250, length_mm=179),
				"Used for finished part",
			),
			(
				dict(used_for_finished_part="FG01SHR", thickness_mm=0, width_mm=1250, length_mm=179),
				"thickness",
			),
			(dict(used_for_finished_part="FG01SHR", thickness_mm=1.6, width_mm=0, length_mm=179), "width"),
			(dict(used_for_finished_part="FG01SHR", thickness_mm=1.6, width_mm=1250, length_mm=0), "length"),
			(
				dict(used_for_finished_part="FG01SHR", thickness_mm="abc", width_mm=1250, length_mm=179),
				"thickness",
			),
			(
				dict(used_for_finished_part="FG01SHR", thickness_mm=1.6, width_mm="abc", length_mm=179),
				"width",
			),
			(
				dict(used_for_finished_part="FG01SHR", thickness_mm=1.6, width_mm=1250, length_mm="abc"),
				"length",
			),
		]
		for kwargs, message in cases:
			with self.subTest(kwargs=kwargs):
				with self.assertRaisesRegex(ValueError, message):
					self.validators.derive_end_piece_item_code(**kwargs)

	def test_calculate_sheet_weight_returns_none_for_non_numeric_dimensions(self) -> None:
		cases = [
			{"thickness_mm": "abc", "width_mm": 1250, "length_mm": 179},
			{"thickness_mm": 1.6, "width_mm": "abc", "length_mm": 179},
			{"thickness_mm": 1.6, "width_mm": 1250, "length_mm": "abc"},
		]
		for kwargs in cases:
			with self.subTest(kwargs=kwargs):
				self.assertIsNone(self.validators.calculate_sheet_weight_kg(**kwargs))

	def test_end_piece_disposition_accepts_only_reuse_or_scrap(self) -> None:
		layout = self._balanced_layout(end_piece=EndPiece(disposition="Invalid", used_for_finished_part=None))
		with self.assertRaisesRegex(ValidationError, "Disposition must be either Reuse or Scrap"):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_reuse_requires_used_for_finished_part_suffix(self) -> None:
		for suffix in ("SHR", "BLK", "DR"):
			with self.subTest(suffix=suffix):
				layout = self._balanced_layout(
					end_piece=EndPiece(used_for_finished_part=f"FG01{suffix}", scrap_item="EP-SCRAP")
				)
				self.validators.validate_sheet_cutting_layout(layout)

		layout = self._balanced_layout(end_piece=EndPiece(used_for_finished_part="FG01XX"))
		with self.assertRaisesRegex(ValidationError, "must end with SHR, BLK, or DR"):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_validation_derives_reuse_end_piece_weight_split_and_bom_scrap(self) -> None:
		end_piece = EndPiece(
			weight_kg=2.5545,
			bom_quantity=3,
			net_weight_per_part_kg=0.75,
			scrap_item="EP-SCRAP",
		)
		layout = self._balanced_layout(end_piece=end_piece)

		self.validators.validate_sheet_cutting_layout(layout)

		self.assertEqual(end_piece.gross_weight_per_part_kg, 0.8515)
		self.assertEqual(end_piece.scrap_weight_per_part_kg, 0.1015)
		self.assertEqual(end_piece.bom_scrap_quantity_kg, 0.3045)

	def test_validation_allows_positive_reuse_bom_scrap_without_process_scrap_item(self) -> None:
		end_piece = EndPiece(
			weight_kg=2.5545,
			bom_quantity=3,
			net_weight_per_part_kg=0.75,
			scrap_item="EP-SCRAP",
		)
		layout = self._balanced_layout(end_piece=end_piece)
		layout.process_scrap_item = ""

		self.validators.validate_sheet_cutting_layout(layout)

		self.assertEqual(end_piece.gross_weight_per_part_kg, 0.8515)
		self.assertEqual(end_piece.scrap_weight_per_part_kg, 0.1015)
		self.assertEqual(end_piece.bom_scrap_quantity_kg, 0.3045)

	def test_validation_overrides_stale_manual_reuse_end_piece_scrap_values(self) -> None:
		end_piece = EndPiece(
			weight_kg=2.5545,
			bom_quantity=3,
			net_weight_per_part_kg=0.75,
			gross_weight_per_part_kg=99,
			scrap_weight_per_part_kg=99,
			bom_scrap_quantity_kg=99,
			scrap_item="EP-SCRAP",
		)
		layout = self._balanced_layout(end_piece=end_piece)

		self.validators.validate_sheet_cutting_layout(layout)

		self.assertEqual(end_piece.gross_weight_per_part_kg, 0.8515)
		self.assertEqual(end_piece.scrap_weight_per_part_kg, 0.1015)
		self.assertEqual(end_piece.bom_scrap_quantity_kg, 0.3045)

	def test_reuse_end_piece_requires_net_weight(self) -> None:
		layout = self._balanced_layout(end_piece=EndPiece(net_weight_per_part_kg=None))

		with self.assertRaisesRegex(ValidationError, "Net weight per part is required"):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_reuse_end_piece_rejects_net_weight_above_gross_weight(self) -> None:
		layout = self._balanced_layout(
			end_piece=EndPiece(
				weight_kg=2.5545,
				bom_quantity=3,
				net_weight_per_part_kg=0.86,
			)
		)

		with self.assertRaisesRegex(ValidationError, "Scrap weight per part cannot be negative"):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_reuse_end_piece_replaces_stale_bom_scrap_when_net_weight_exceeds_gross_weight(
		self,
	) -> None:
		end_piece = EndPiece(
			weight_kg=2.5545,
			bom_quantity=3,
			net_weight_per_part_kg=0.86,
			bom_scrap_quantity_kg=99,
		)
		layout = self._balanced_layout(end_piece=end_piece)

		with self.assertRaisesRegex(ValidationError, "Scrap weight per part cannot be negative"):
			self.validators.validate_sheet_cutting_layout(layout)

		self.assertEqual(end_piece.scrap_weight_per_part_kg, -0.0085)
		self.assertEqual(end_piece.bom_scrap_quantity_kg, -0.0255)

	def test_reuse_end_piece_requires_row_scrap_item_for_positive_derived_scrap(self) -> None:
		layout = self._balanced_layout(
			end_piece=EndPiece(
				weight_kg=2.5545,
				bom_quantity=3,
				net_weight_per_part_kg=0.75,
				scrap_item="",
			)
		)

		with self.assertRaisesRegex(ValidationError, "Scrap item is required for reuse end pieces"):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_reuse_end_piece_rejects_scrap_item_matching_used_for_finished_part(self) -> None:
		layout = self._balanced_layout(
			end_piece=EndPiece(
				weight_kg=2.5545,
				bom_quantity=3,
				net_weight_per_part_kg=0.75,
				scrap_item="FG01SHR",
			)
		)

		with self.assertRaisesRegex(ValidationError, "Scrap item cannot be the used-for finished part"):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_reuse_end_piece_rejects_used_for_finished_part_scrap_item_when_derived_scrap_is_zero(
		self,
	) -> None:
		layout = self._balanced_layout(
			end_piece=EndPiece(
				weight_kg=2.5545,
				bom_quantity=3,
				net_weight_per_part_kg=0.8515,
				scrap_item="FG01SHR",
			)
		)

		with self.assertRaisesRegex(ValidationError, "Scrap item cannot be the used-for finished part"):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_reuse_end_piece_rejects_generated_end_piece_scrap_item_when_derived_scrap_is_zero(
		self,
	) -> None:
		layout = self._balanced_layout(
			end_piece=EndPiece(
				weight_kg=2.5545,
				bom_quantity=3,
				net_weight_per_part_kg=0.8515,
				scrap_item="AB12SHR-EP-1x1250x260",
			)
		)

		with self.assertRaisesRegex(ValidationError, "Scrap item cannot be the generated end-piece item"):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_reuse_end_piece_rejects_parent_derived_generated_end_piece_scrap_item(self) -> None:
		layout = self._balanced_layout(
			finished_part=FinishedPart("PARENTSHR", 2, 11.004, 0),
			end_piece=EndPiece(
				used_for_finished_part="CHILDSHR",
				weight_kg=2.5545,
				bom_quantity=3,
				net_weight_per_part_kg=0.8515,
				scrap_item="PARENTSHR-EP-1x1250x260",
			),
		)

		with self.assertRaisesRegex(ValidationError, "Scrap item cannot be the generated end-piece item"):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_reuse_end_piece_ignores_generated_scrap_check_when_dimensions_are_invalid(
		self,
	) -> None:
		layout = self._balanced_layout(
			end_piece=EndPiece(
				width_mm="abc",
				weight_kg=2.5545,
				bom_quantity=3,
				net_weight_per_part_kg=0.8515,
				scrap_item="EP-SCRAP",
			)
		)

		with self.assertRaises(ValidationError):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_scrap_requires_scrap_item_and_rejects_reuse_only_fields(self) -> None:
		layout = self._balanced_layout(
			end_piece=EndPiece(
				disposition="Scrap",
				scrap_item="",
				used_for_finished_part=None,
				bom_quantity=0,
				net_weight_per_part_kg=None,
				bom_scrap_quantity_kg=0,
			)
		)
		with self.assertRaisesRegex(ValidationError, "Scrap item is required"):
			self.validators.validate_sheet_cutting_layout(layout)

		reuse_only_cases = [
			(
				EndPiece(
					disposition="Scrap",
					scrap_item="MS",
					used_for_finished_part="FG01SHR",
					bom_quantity=0,
					net_weight_per_part_kg=None,
					bom_scrap_quantity_kg=0,
				),
				"Used for finished part",
			),
			(
				EndPiece(
					disposition="Scrap",
					scrap_item="MS",
					used_for_finished_part=None,
					bom_quantity=1,
					net_weight_per_part_kg=None,
					bom_scrap_quantity_kg=0,
				),
				"BOM quantity",
			),
			(
				EndPiece(
					disposition="Scrap",
					scrap_item="MS",
					used_for_finished_part=None,
					bom_quantity=0,
					net_weight_per_part_kg=1,
					bom_scrap_quantity_kg=0,
				),
				"Net weight per part",
			),
			(
				EndPiece(
					disposition="Scrap",
					scrap_item="MS",
					used_for_finished_part=None,
					bom_quantity=0,
					net_weight_per_part_kg=None,
					gross_weight_per_part_kg=1,
					bom_scrap_quantity_kg=0,
				),
				"Gross weight per part",
			),
			(
				EndPiece(
					disposition="Scrap",
					scrap_item="MS",
					used_for_finished_part=None,
					bom_quantity=0,
					net_weight_per_part_kg=None,
					scrap_weight_per_part_kg=0.1,
					bom_scrap_quantity_kg=0,
				),
				"Scrap weight per part",
			),
			(
				EndPiece(
					disposition="Scrap",
					scrap_item="MS",
					used_for_finished_part=None,
					bom_quantity=0,
					net_weight_per_part_kg=None,
					bom_scrap_quantity_kg=0.1,
				),
				"BOM scrap quantity",
			),
		]
		for end_piece, message in reuse_only_cases:
			with self.subTest(message=message):
				with self.assertRaisesRegex(ValidationError, message):
					self.validators.validate_sheet_cutting_layout(self._balanced_layout(end_piece=end_piece))

	def test_process_scrap_item_cannot_be_finished_part_item(self) -> None:
		layout = Layout(
			finished_part_code="FG01SHR",
			net_weight_per_part_kg=0.289,
			sheet_thickness_mm=None,
			sheet_width_mm=None,
			sheet_length_mm=None,
			weight_per_sheet_kg=39.3,
			parts_per_strip=7,
			no_of_strips=11,
			weight_of_strip_kg=3.316922,
			strip_thickness_mm=None,
			strip_width_mm=None,
			strip_length_mm=None,
			process_scrap_item="FG01SHR",
			end_pieces=[
				EndPiece(
					weight_kg=2.813858,
					disposition="Scrap",
					used_for_finished_part=None,
					bom_quantity=0,
					net_weight_per_part_kg=None,
					bom_scrap_quantity_kg=0,
					scrap_item="MSScrap",
				)
			],
		)

		with self.assertRaisesRegex(ValidationError, "Process scrap item cannot be the finished part item"):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_apply_end_piece_bom_status_uses_generated_bom_presence(self) -> None:
		no_reuse = self._balanced_layout(
			end_piece=EndPiece(
				disposition="Scrap",
				scrap_item="MS-SCRAP",
				used_for_finished_part=None,
				bom_quantity=0,
				bom_scrap_quantity_kg=0,
			)
		)
		pending = self._balanced_layout(end_piece=EndPiece(end_piece_item_code="FG01SHR-EP-1x1250x260"))
		generated = self._balanced_layout(
			end_piece=EndPiece(
				end_piece_item_code="FG01SHR-EP-1x1250x260",
				generated_end_piece_bom="BOM-EP-001",
			)
		)

		self.validators.apply_end_piece_bom_status(no_reuse, no_reuse.end_pieces)
		self.validators.apply_end_piece_bom_status(pending, pending.end_pieces)
		self.validators.apply_end_piece_bom_status(generated, generated.end_pieces)

		self.assertEqual(no_reuse.end_piece_bom_status, "Not Required")
		self.assertEqual(pending.end_piece_bom_status, "Pending")
		self.assertEqual(generated.end_piece_bom_status, "Generated")

	def test_apply_end_piece_bom_status_ignores_child_layout_reuse_rows(self) -> None:
		layout = self._balanced_layout(
			end_piece=EndPiece(
				end_piece_item_code="FG01SHR-EP-1x1250x260",
				child_layout="SCL-CHILD",
			)
		)

		self.validators.apply_end_piece_bom_status(layout, layout.end_pieces)

		self.assertEqual(layout.end_piece_bom_status, "Not Required")

	def test_end_piece_item_code_cannot_change_after_generation(self) -> None:
		end_piece = ExistingEndPiece(
			previous_code="FG01SHR-EP-1x1250x260",
			current_code="FG01SHR-EP-1x1250x261",
			generated_end_piece_item="FG01SHR-EP-1x1250x260",
			weight_kg=2.5545,
			width_mm=1250,
			length_mm=260,
			disposition="Reuse",
			used_for_finished_part="FG01SHR",
			bom_quantity=1,
			net_weight_per_part_kg=2.5545,
			bom_scrap_quantity_kg=0,
			scrap_item="",
		)
		layout = self._balanced_layout(end_piece=end_piece)

		with self.assertRaisesRegex(ValidationError, "End piece item code cannot be changed"):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_end_piece_item_code_can_change_before_generation(self) -> None:
		end_piece = ExistingEndPiece(
			previous_code="FG01SHR-EP-1x1250x260",
			current_code="FG01SHR-EP-1x1250x261",
			weight_kg=2.5545,
			width_mm=1250,
			length_mm=260,
			disposition="Reuse",
			used_for_finished_part="FG01SHR",
			bom_quantity=1,
			net_weight_per_part_kg=2.5545,
			bom_scrap_quantity_kg=0,
			scrap_item="",
		)
		layout = self._balanced_layout(end_piece=end_piece)

		self.validators.validate_sheet_cutting_layout(layout)
		self.assertEqual(layout.end_piece_bom_status, "Pending")

	def test_end_piece_item_code_can_be_set_when_previous_value_is_empty(self) -> None:
		end_piece = ExistingEndPiece(
			previous_code=None,
			current_code="FG01SHR-EP-1x1250x260",
			weight_kg=2.5545,
			width_mm=1250,
			length_mm=260,
			disposition="Reuse",
			used_for_finished_part="FG01SHR",
			bom_quantity=1,
			net_weight_per_part_kg=2.5545,
			bom_scrap_quantity_kg=0,
			scrap_item="",
		)
		layout = self._balanced_layout(end_piece=end_piece)

		self.validators.validate_sheet_cutting_layout(layout)
		self.assertEqual(layout.end_piece_bom_status, "Pending")

	def test_child_layout_raw_material_guard_uses_finished_part_code(self) -> None:
		layout = Layout(finished_part_code="FG01SHR")
		end_piece = EndPiece(used_for_finished_part="FG02SHR")
		self.fake_frappe.db = SimpleNamespace(
			get_value=lambda doctype, name, fieldname: "FG01SHR-EP-1x1250x260"
		)

		with patch.object(
			self.validators,
			"derive_end_piece_item_code_from_row",
			return_value="FG01SHR-EP-1x1250x260",
		) as derive:
			self.validators._validate_child_raw_material(layout, end_piece, "SCL-CHILD")

		derive.assert_called_once_with(
			layout,
			end_piece,
			source_finished_part="FG01SHR",
		)

	def test_child_layout_raw_material_guard_uses_lh_rh_pair_code(self) -> None:
		layout = Layout(finished_part_code="FG01LHSHR", is_lh_rh=1, twin_finished_part="FG01RHSHR")
		end_piece = EndPiece(used_for_finished_part="FG02SHR")
		self.fake_frappe.db = SimpleNamespace(
			get_value=lambda doctype, name, fieldname: "FG01LHSHR-FG01RHSHR-EP-1x1250x260"
		)

		with patch.object(
			self.validators,
			"derive_end_piece_item_code_from_row",
			return_value="FG01LHSHR-FG01RHSHR-EP-1x1250x260",
		) as derive:
			self.validators._validate_child_raw_material(layout, end_piece, "SCL-CHILD")

		derive.assert_called_once_with(
			layout,
			end_piece,
			source_finished_part="FG01LHSHR-FG01RHSHR",
		)

	def test_consumption_tracking_uses_gross_plus_end_piece_weight_and_sets_balanced(self) -> None:
		layout = self._balanced_layout(end_piece=EndPiece(scrap_item="EP-SCRAP"))
		self.validators.validate_sheet_cutting_layout(layout)

		self.assertEqual(layout.consumed_weight_kg, 24.562)
		self.assertEqual(layout.leftover_weight_kg, 0.0)
		self.assertEqual(layout.consumption_status, "Balanced")

	def test_consumption_tracking_accepts_balanced_layout_with_scrap_end_piece(self) -> None:
		layout = self._balanced_layout(
			end_piece=EndPiece(
				disposition="Scrap",
				scrap_item="MS-SCRAP",
				used_for_finished_part=None,
				bom_quantity=0,
				net_weight_per_part_kg=None,
				bom_scrap_quantity_kg=0,
			)
		)

		self.validators.validate_sheet_cutting_layout(layout)

		self.assertEqual(layout.consumed_weight_kg, 24.562)
		self.assertEqual(layout.leftover_weight_kg, 0.0)
		self.assertEqual(layout.consumption_status, "Balanced")

	def test_consumption_tracking_accepts_balanced_layout_with_reuse_end_piece(self) -> None:
		layout = self._balanced_layout(end_piece=EndPiece(disposition="Reuse", scrap_item="EP-SCRAP"))

		self.validators.validate_sheet_cutting_layout(layout)

		self.assertEqual(layout.consumed_weight_kg, 24.562)
		self.assertEqual(layout.leftover_weight_kg, 0.0)
		self.assertEqual(layout.consumption_status, "Balanced")

	def test_consumption_tracking_raises_for_short_and_excess_outside_tolerance(self) -> None:
		short_layout = self._balanced_layout(
			end_piece=EndPiece(length_mm=259.338, used_for_finished_part="FG01SHR", scrap_item="EP-SCRAP")
		)
		with self.assertRaisesRegex(ValidationError, "no accounting for 0.006 kg"):
			self.validators.validate_sheet_cutting_layout(short_layout)
		self.assertEqual(short_layout.consumption_status, "Short")

		excess_layout = self._balanced_layout(
			end_piece=EndPiece(length_mm=260.560, used_for_finished_part="FG01SHR", scrap_item="EP-SCRAP")
		)
		with self.assertRaisesRegex(ValidationError, "exceeds sheet weight by 0.006 kg"):
			self.validators.validate_sheet_cutting_layout(excess_layout)
		self.assertEqual(excess_layout.consumption_status, "Excess")

	def test_consumption_tracking_accepts_sheet_consumption_at_tolerance_edge(self) -> None:
		cases = [
			("short_edge", 259.44, 0.005),
			("excess_edge", 260.458, -0.005),
		]
		for name, end_piece_length_mm, expected_leftover_weight in cases:
			with self.subTest(name=name):
				layout = self._balanced_layout(
					end_piece=EndPiece(
						length_mm=end_piece_length_mm,
						used_for_finished_part="FG01SHR",
						scrap_item="EP-SCRAP",
					)
				)

				self.validators.validate_sheet_cutting_layout(layout)

				self.assertEqual(layout.leftover_weight_kg, expected_leftover_weight)
				self.assertEqual(layout.consumption_status, "Balanced")

	def test_consumed_weight_calculation_does_not_add_process_scrap(self) -> None:
		layout = Layout(
			finished_part_code="AB12SHR",
			parts_per_sheet=2,
			gross_weight_per_part_kg=11.004,
			scrap_weight_per_part_kg=0.5,
		)
		consumed = self.validators.calculate_consumed_weight_kg(
			layout,
			[EndPiece(disposition="Scrap", weight_kg=2.5545)],
		)
		self.assertEqual(consumed, 24.562)
