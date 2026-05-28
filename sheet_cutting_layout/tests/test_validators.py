from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from unittest.mock import patch

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


class ValidationError(Exception):
	pass


class FakeFrappe:
	ValidationError = ValidationError

	def __init__(self) -> None:
		self.float_precision: str | None = None

	def get_system_settings(self, fieldname: str) -> str | None:
		if fieldname == "float_precision":
			return self.float_precision
		return None

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
	weight_kg: float | None = 2.5545
	qty_per_sheet: float | None = 1
	width_mm: float | None = 1250
	length_mm: float | None = 260
	disposition: str | None = "Reuse"
	used_for_finished_part: str | None = "FG01SHR"
	bom_quantity: float | None = 1
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

	def _balanced_layout(
		self,
		*,
		finished_part: FinishedPart | None = None,
		end_piece: EndPiece | None = None,
	) -> Layout:
		return Layout(
			finished_parts=[finished_part or FinishedPart("AB12SHR", 2, 11.004, 0)],
			end_pieces=[end_piece or EndPiece()],
		)

	def test_finished_part_item_code_validation_rules(self) -> None:
		with self.assertRaisesRegex(ValidationError, "alphanumeric"):
			self.validators.validate_finished_part_code("AB-12SHR")
		with self.assertRaisesRegex(ValidationError, "end with SHR"):
			self.validators.validate_finished_part_code("AB12")

		self.validators.validate_finished_part_code("AB12SHR")

	def test_layout_requires_exactly_one_finished_part(self) -> None:
		with self.assertRaisesRegex(ValidationError, "exactly one finished part"):
			self.validators.validate_sheet_cutting_layout(Layout())
		with self.assertRaisesRegex(ValidationError, "exactly one finished part"):
			self.validators.validate_sheet_cutting_layout(
				Layout(
					finished_parts=[
						FinishedPart("AB12SHR", 2, 11.004, 0),
						FinishedPart("CD34SHR", 2, 11.004, 0),
					],
					end_pieces=[EndPiece(disposition="Scrap", scrap_item="MS", used_for_finished_part=None)],
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

	def test_strip_and_parts_formulas_derive_parent_and_child_fields(self) -> None:
		layout = self._balanced_layout(
			finished_part=FinishedPart(
				finished_part_item="AB12SHR",
				parts_per_sheet=99,
				gross_weight_per_part_kg=0,
				net_weight_per_part_kg=0.5,
			)
		)

		self.validators.apply_strip_weight_formula(layout)
		self.validators.apply_parent_gross_weight_per_part_formula(layout)
		self.validators.apply_parts_per_sheet_formula(layout, layout.finished_parts)
		self.validators.apply_finished_part_weight_formulas(layout, layout.finished_parts)

		self.assertEqual(layout.parts_per_sheet, 2)
		self.assertEqual(layout.finished_parts[0].parts_per_sheet, 2)
		self.assertGreater(layout.weight_of_strip_kg, 0)
		self.assertGreater(layout.gross_weight_per_part_kg, 0)
		self.assertEqual(
			layout.finished_parts[0].gross_weight_per_part_kg,
			layout.gross_weight_per_part_kg,
		)

	def test_derive_end_piece_item_code_uses_used_for_finished_part_and_trimmed_numbers(self) -> None:
		derived = self.validators.derive_end_piece_item_code(
			used_for_finished_part="fg01shr",
			thickness_mm=1.6,
			width_mm=1250.0,
			length_mm=179.000000,
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
		self.assertIsNone(
			self.validators.calculate_sheet_weight_kg(
				thickness_mm="abc",
				width_mm=1250,
				length_mm=179,
			)
		)

	def test_end_piece_disposition_accepts_only_reuse_or_scrap(self) -> None:
		layout = self._balanced_layout(end_piece=EndPiece(disposition="Invalid", used_for_finished_part=None))
		with self.assertRaisesRegex(ValidationError, "Disposition must be either Reuse or Scrap"):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_reuse_requires_used_for_finished_part_suffix(self) -> None:
		for suffix in ("SHR", "BLK", "DR"):
			with self.subTest(suffix=suffix):
				layout = self._balanced_layout(end_piece=EndPiece(used_for_finished_part=f"FG01{suffix}"))
				self.validators.validate_sheet_cutting_layout(layout)

		layout = self._balanced_layout(end_piece=EndPiece(used_for_finished_part="FG01XX"))
		with self.assertRaisesRegex(ValidationError, "must end with SHR, BLK, or DR"):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_reuse_rejects_scrap_item_value(self) -> None:
		layout = self._balanced_layout(end_piece=EndPiece(disposition="Reuse", scrap_item="MS-SCRAP"))
		with self.assertRaisesRegex(ValidationError, "allowed only for scrap end pieces"):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_scrap_requires_scrap_item_and_rejects_reuse_only_fields(self) -> None:
		layout = self._balanced_layout(
			end_piece=EndPiece(
				disposition="Scrap",
				scrap_item="",
				used_for_finished_part=None,
				bom_quantity=0,
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
					bom_scrap_quantity_kg=0.1,
				),
				"BOM scrap quantity",
			),
		]
		for end_piece, message in reuse_only_cases:
			with self.subTest(message=message):
				with self.assertRaisesRegex(ValidationError, message):
					self.validators.validate_sheet_cutting_layout(self._balanced_layout(end_piece=end_piece))

	def test_process_scrap_item_required_when_reuse_bom_scrap_quantity_positive(self) -> None:
		layout = self._balanced_layout(end_piece=EndPiece(bom_scrap_quantity_kg=0.25))
		layout.process_scrap_item = ""

		with self.assertRaisesRegex(ValidationError, "Process scrap item"):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_apply_end_piece_bom_status_uses_end_piece_item_code_presence(self) -> None:
		no_reuse = self._balanced_layout(
			end_piece=EndPiece(
				disposition="Scrap",
				scrap_item="MS-SCRAP",
				used_for_finished_part=None,
				bom_quantity=0,
				bom_scrap_quantity_kg=0,
			)
		)
		pending = self._balanced_layout(end_piece=EndPiece(end_piece_item_code=None))
		generated = self._balanced_layout(end_piece=EndPiece(end_piece_item_code="FG01SHR-EP-1x1250x260"))

		self.validators.apply_end_piece_bom_status(no_reuse, no_reuse.end_pieces)
		self.validators.apply_end_piece_bom_status(pending, pending.end_pieces)
		self.validators.apply_end_piece_bom_status(generated, generated.end_pieces)

		self.assertEqual(no_reuse.end_piece_bom_status, "Not Required")
		self.assertEqual(pending.end_piece_bom_status, "Pending")
		self.assertEqual(generated.end_piece_bom_status, "Generated")

	def test_end_piece_item_code_cannot_change_after_generation(self) -> None:
		end_piece = ExistingEndPiece(
			previous_code="FG01SHR-EP-1x1250x260",
			current_code="FG01SHR-EP-1x1250x261",
			weight_kg=2.5545,
			qty_per_sheet=1,
			width_mm=1250,
			length_mm=260,
			disposition="Reuse",
			used_for_finished_part="FG01SHR",
			bom_quantity=1,
			bom_scrap_quantity_kg=0,
			scrap_item="",
		)
		layout = self._balanced_layout(end_piece=end_piece)

		with self.assertRaisesRegex(ValidationError, "End piece item code cannot be changed"):
			self.validators.validate_sheet_cutting_layout(layout)

	def test_consumption_tracking_uses_gross_plus_end_piece_weight_and_sets_balanced(self) -> None:
		layout = self._balanced_layout()
		self.validators.validate_sheet_cutting_layout(layout)

		self.assertEqual(layout.consumed_weight_kg, 24.562)
		self.assertEqual(layout.leftover_weight_kg, 0.0)
		self.assertEqual(layout.consumption_status, "Balanced")

	def test_consumption_tracking_raises_for_short_and_excess_outside_tolerance(self) -> None:
		short_layout = self._balanced_layout(
			end_piece=EndPiece(length_mm=259.338, used_for_finished_part="FG01SHR")
		)
		with self.assertRaisesRegex(ValidationError, "no accounting for 0.006 kg"):
			self.validators.validate_sheet_cutting_layout(short_layout)
		self.assertEqual(short_layout.consumption_status, "Short")

		excess_layout = self._balanced_layout(
			end_piece=EndPiece(length_mm=260.560, used_for_finished_part="FG01SHR")
		)
		with self.assertRaisesRegex(ValidationError, "exceeds sheet weight by 0.006 kg"):
			self.validators.validate_sheet_cutting_layout(excess_layout)
		self.assertEqual(excess_layout.consumption_status, "Excess")

	def test_consumed_weight_calculation_does_not_add_process_scrap(self) -> None:
		consumed = self.validators.calculate_consumed_weight_kg(
			[
				FinishedPart(
					"AB12SHR",
					parts_per_sheet=2,
					gross_weight_per_part_kg=11.004,
					scrap_weight_per_part_kg=0.5,
				)
			],
			[EndPiece(weight_kg=2.5545)],
		)
		self.assertEqual(consumed, 24.562)
