from __future__ import annotations

import importlib
import re
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path

import pytest


class ValidationError(Exception):
	pass


class FakeFrappe:
	ValidationError = ValidationError

	def __init__(self) -> None:
		self.float_precision: str | None = None

	def get_system_settings(self, fieldname: str) -> str | None:
		assert fieldname == "float_precision"
		return self.float_precision

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
	end_piece_item: str | None
	weight_kg: float | None
	qty_per_sheet: float | None
	width_mm: float | None = None
	length_mm: float | None = None

	def __post_init__(self) -> None:
		if self.weight_kg is not None and self.width_mm is None and self.length_mm is None:
			self.width_mm = 1000
			self.length_mm = self.weight_kg * 1_000_000 / (7.86 * self.width_mm)


@dataclass
class Layout:
	finished_parts: list[FinishedPart] = field(default_factory=list)
	end_pieces: list[EndPiece] = field(default_factory=list)
	process_scrap_item: str = "PROCESSSCRAP001"
	sheet_thickness_mm: float = 1
	sheet_width_mm: float = 1250
	sheet_length_mm: float = 2500
	weight_per_sheet_kg: float = 0
	strip_thickness_mm: float = 1
	strip_width_mm: float = 1250
	strip_length_mm: float = 242
	weight_of_strip_kg: float = 0
	parts_per_strip: int = 5
	no_of_strips: int | None = None
	parts_per_sheet: int = 0
	consumed_weight_kg: float = 0
	leftover_weight_kg: float = 0
	consumption_status: str = ""


@pytest.fixture
def validators(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
	fake_frappe = FakeFrappe()
	monkeypatch.setitem(sys.modules, "frappe", fake_frappe)

	module = importlib.import_module("sheet_cutting_layout.services.validators")
	monkeypatch.setattr(module, "frappe", fake_frappe)
	return module


def test_finished_part_item_must_end_with_shr_and_be_alnum(validators: types.ModuleType) -> None:
	with pytest.raises(ValidationError, match="alphanumeric"):
		validators.validate_finished_part_code("AB-12SHR")

	with pytest.raises(ValidationError, match="end with SHR"):
		validators.validate_finished_part_code("AB12")

	validators.validate_finished_part_code("AB12SHR")


def test_layout_requires_exactly_one_finished_part(validators: types.ModuleType) -> None:
	with pytest.raises(ValidationError, match="exactly one finished part"):
		validators.validate_sheet_cutting_layout(Layout())

	with pytest.raises(ValidationError, match="exactly one finished part"):
		validators.validate_sheet_cutting_layout(
			Layout(
				finished_parts=[
					FinishedPart("AB12SHR", 1, 12.28125, 0),
					FinishedPart("CD34SHR", 1, 12.28125, 0),
				]
			)
		)


def test_finished_part_weights_must_be_non_negative(validators: types.ModuleType) -> None:
	with pytest.raises(ValidationError, match="Gross weight"):
		validators.validate_sheet_cutting_layout(Layout(finished_parts=[FinishedPart("AB12SHR", 1, -0.1, 0)]))

	with pytest.raises(ValidationError, match="Scrap weight"):
		validators.validate_sheet_cutting_layout(Layout(finished_parts=[FinishedPart("AB12SHR", 1, 1, -0.1)]))


def test_process_scrap_item_required_when_process_scrap_weight_is_positive(
	validators: types.ModuleType,
) -> None:
	with pytest.raises(ValidationError, match="Process scrap item"):
		validators.validate_sheet_cutting_layout(
			Layout(
				finished_parts=[FinishedPart("AB12SHR", 2, 5, 1)],
				process_scrap_item="",
			)
		)


def test_sheet_weight_is_calculated_from_dimensions_to_six_decimals(
	validators: types.ModuleType,
) -> None:
	assert (
		validators.calculate_sheet_weight_kg(
			thickness_mm=1,
			width_mm=1250,
			length_mm=2500,
		)
		== 24.5625
	)


def test_validation_overwrites_manual_sheet_weight_with_formula(
	validators: types.ModuleType,
) -> None:
	layout = Layout(
		finished_parts=[FinishedPart("AB12SHR", 2, 12.28125, 0)],
		weight_per_sheet_kg=999,
	)

	validators.apply_sheet_weight_formula(layout)

	assert layout.weight_per_sheet_kg == 24.5625


def test_sheet_weight_keeps_minimum_calculation_precision(
	validators: types.ModuleType,
) -> None:
	validators.frappe.float_precision = "3"

	assert (
		validators.calculate_sheet_weight_kg(
			thickness_mm=1,
			width_mm=1250,
			length_mm=2500,
		)
		== 24.5625
	)


def test_density_constant_is_7_86_only() -> None:
	validator_source = (Path(__file__).parents[1] / "services" / "validators.py").read_text(encoding="utf-8")

	assert "STEEL_DENSITY_G_PER_CM3 = 7.86" in validator_source
	assert "STEEL_DENSITY_G_PER_CM3 = 7.850000" not in validator_source


def test_sheet_weight_rounds_density_to_system_float_precision_before_calculation(
	validators: types.ModuleType,
) -> None:
	validators.frappe.float_precision = "1"

	assert (
		validators.calculate_sheet_weight_kg(
			thickness_mm=10,
			width_mm=1000,
			length_mm=1000,
		)
		== 79.0
	)


def test_strip_weight_is_calculated_from_dimensions_to_six_decimals(
	validators: types.ModuleType,
) -> None:
	assert (
		validators.calculate_sheet_weight_kg(
			thickness_mm=1,
			width_mm=1250,
			length_mm=242,
		)
		== 2.37765
	)


def test_validation_overwrites_manual_strip_weight_with_formula(
	validators: types.ModuleType,
) -> None:
	layout = Layout(
		finished_parts=[FinishedPart("AB12SHR", 2, 12.28125, 0)],
		weight_of_strip_kg=999,
	)

	validators.apply_strip_weight_formula(layout)
	validators.apply_finished_part_weight_formulas(layout, layout.finished_parts)

	assert layout.weight_of_strip_kg == 2.37765


def test_validation_calculates_part_gross_and_scrap_from_strip_weight_and_net_weight(
	validators: types.ModuleType,
) -> None:
	layout = Layout(
		finished_parts=[
			FinishedPart("AB12SHR", 10, gross_weight_per_part_kg=99, net_weight_per_part_kg=0.185)
		],
		parts_per_strip=5,
		strip_length_mm=242,
	)

	validators.apply_strip_weight_formula(layout)
	validators.apply_finished_part_weight_formulas(layout, layout.finished_parts)

	assert layout.finished_parts[0].gross_weight_per_part_kg == 0.47553
	assert layout.finished_parts[0].scrap_weight_per_part_kg == 0.29053


def test_validation_calculates_parent_and_child_parts_per_sheet_from_strip_counts(
	validators: types.ModuleType,
) -> None:
	layout = Layout(
		finished_parts=[FinishedPart("AB12SHR", parts_per_sheet=999, gross_weight_per_part_kg=1)],
		parts_per_strip=7,
		no_of_strips=11,
		parts_per_sheet=999,
	)

	validators.apply_parts_per_sheet_formula(layout, layout.finished_parts)

	assert layout.parts_per_sheet == 77
	assert layout.finished_parts[0].parts_per_sheet == 77


def test_part_scrap_must_not_be_negative_after_net_weight_calculation(
	validators: types.ModuleType,
) -> None:
	with pytest.raises(ValidationError, match="Net weight per part cannot exceed gross weight"):
		validators.validate_sheet_cutting_layout(
			Layout(
				finished_parts=[FinishedPart("AB12SHR", 10, gross_weight_per_part_kg=0, net_weight_per_part_kg=9)],
				parts_per_strip=5,
			)
		)


def test_validation_calculates_end_piece_weight_from_dimensions_and_sheet_thickness(
	validators: types.ModuleType,
) -> None:
	layout = Layout(
		finished_parts=[FinishedPart("AB12SHR", 10, gross_weight_per_part_kg=0, net_weight_per_part_kg=2)],
		end_pieces=[EndPiece("EP1", weight_kg=999, qty_per_sheet=1, width_mm=1250, length_mm=211)],
		sheet_thickness_mm=1.6,
		parts_per_strip=5,
	)

	with pytest.raises(ValidationError):
		validators.validate_sheet_cutting_layout(layout)

	assert layout.end_pieces[0].weight_kg == 3.31692


def test_sheet_consumption_must_account_for_full_sheet_weight(validators: types.ModuleType) -> None:
	with pytest.raises(
		ValidationError,
		match=re.escape("no accounting for 12.562 kg of sheet consumption"),
	):
		validators.validate_sheet_cutting_layout(
			Layout(
				finished_parts=[FinishedPart("AB12SHR", 2, 5, 1)],
				end_pieces=[EndPiece("EP1", 2, 1)],
			)
		)


def test_sheet_consumption_must_not_exceed_sheet_weight(validators: types.ModuleType) -> None:
	with pytest.raises(ValidationError, match=re.escape("exceeds sheet weight by 2.000 kg")):
		validators.validate_sheet_cutting_layout(
			Layout(
				finished_parts=[FinishedPart("AB12SHR", 2, 10, 1)],
				end_pieces=[EndPiece("EP1", 6.5625, 1)],
			)
		)


def test_sheet_consumption_accepts_balance_difference_below_two_decimal_precision(
	validators: types.ModuleType,
) -> None:
	validators.validate_sheet_cutting_layout(
		Layout(
			finished_parts=[FinishedPart("AB12SHR", 2, 11, 1)],
			end_pieces=[EndPiece("EP1", 2.558, 1)],
		)
	)


def test_validation_updates_consumption_tracking_fields(validators: types.ModuleType) -> None:
	layout = Layout(
		finished_parts=[FinishedPart("AB12SHR", 2, 11, 1)],
		end_pieces=[EndPiece("EP1", 2.5625, 1)],
	)

	validators.validate_sheet_cutting_layout(layout)

	assert layout.consumed_weight_kg == 24.562
	assert layout.leftover_weight_kg == 0.0
	assert layout.consumption_status == "Balanced"


def test_consumption_tracking_ignores_blank_finished_part_rows(validators: types.ModuleType) -> None:
	layout = Layout(
		finished_parts=[
			FinishedPart("", 2, 99, 0),
			FinishedPart("AB12SHR", 2, 11, 1),
		],
		end_pieces=[EndPiece("EP1", 2.5625, 1)],
	)

	validators.validate_sheet_cutting_layout(layout)

	assert layout.consumed_weight_kg == 24.562
	assert layout.leftover_weight_kg == 0
	assert layout.consumption_status == "Balanced"


def test_consumption_tracking_marks_short_and_excess_with_tolerance(validators: types.ModuleType) -> None:
	short_layout = Layout(
		finished_parts=[FinishedPart("AB12SHR", 2, 11, 1)],
		end_pieces=[EndPiece("EP1", 2.556, 1)],
	)

	with pytest.raises(ValidationError):
		validators.validate_sheet_cutting_layout(short_layout)

	assert short_layout.consumed_weight_kg == 24.556
	assert short_layout.leftover_weight_kg == 0.006
	assert short_layout.consumption_status == "Short"

	excess_layout = Layout(
		finished_parts=[FinishedPart("AB12SHR", 2, 11, 1)],
		end_pieces=[EndPiece("EP1", 2.568, 1)],
	)

	with pytest.raises(ValidationError):
		validators.validate_sheet_cutting_layout(excess_layout)

	assert excess_layout.consumed_weight_kg == 24.568
	assert excess_layout.leftover_weight_kg == -0.006
	assert excess_layout.consumption_status == "Excess"


def test_sheet_consumption_accepts_gross_weight_and_end_pieces_without_adding_process_scrap(
	validators: types.ModuleType,
) -> None:
	validators.validate_sheet_cutting_layout(
		Layout(
			finished_parts=[FinishedPart("AB12SHR", 2, 11, 1)],
			end_pieces=[EndPiece("EP1", 2.5625, 1)],
		)
	)


def test_end_piece_rows_require_item_dimensions_and_qty(validators: types.ModuleType) -> None:
	with pytest.raises(ValidationError, match="End piece item"):
		validators.validate_sheet_cutting_layout(
			Layout(
				finished_parts=[FinishedPart("AB12SHR", 2, 5, 1)],
				end_pieces=[EndPiece(None, 1, 1)],
			)
		)

	with pytest.raises(ValidationError, match="End piece width"):
		validators.validate_sheet_cutting_layout(
			Layout(
				finished_parts=[FinishedPart("AB12SHR", 2, 5, 1)],
				end_pieces=[EndPiece("EP1", None, 1)],
			)
		)

	with pytest.raises(ValidationError, match="End piece length"):
		validators.validate_sheet_cutting_layout(
			Layout(
				finished_parts=[FinishedPart("AB12SHR", 2, 5, 1)],
				end_pieces=[EndPiece("EP1", None, 1, width_mm=1000)],
			)
		)

	with pytest.raises(ValidationError, match="End piece quantity"):
		validators.validate_sheet_cutting_layout(
			Layout(
				finished_parts=[FinishedPart("AB12SHR", 2, 5, 1)],
				end_pieces=[EndPiece("EP1", 1, None)],
			)
		)


def test_parts_per_sheet_must_be_positive_for_end_piece_distribution(validators: types.ModuleType) -> None:
	with pytest.raises(ValidationError, match="Parts per sheet"):
		validators.validate_sheet_cutting_layout(
			Layout(
				finished_parts=[FinishedPart("AB12SHR", 0, 5, 1)],
				end_pieces=[EndPiece("EP1", 1, 1)],
			)
		)


def test_derived_finished_goods_weight_must_not_be_negative(validators: types.ModuleType) -> None:
	with pytest.raises(ValidationError, match="Derived finished goods weight"):
		validators.validate_sheet_cutting_layout(
			Layout(
				finished_parts=[FinishedPart("AB12SHR", 2, 2, 1)],
				end_pieces=[EndPiece("EP1", 4, 1)],
			)
		)

	validators.validate_sheet_cutting_layout(
		Layout(
			finished_parts=[FinishedPart("AB12SHR", 2, 11, 1)],
			end_pieces=[EndPiece("EP1", 2.5625, 1)],
		)
	)


def test_controller_validate_delegates_to_service(monkeypatch: pytest.MonkeyPatch) -> None:
	from sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout import sheet_cutting_layout

	called_with: list[object] = []

	def fake_validate(layout: object) -> None:
		called_with.append(layout)

	monkeypatch.setattr(sheet_cutting_layout, "validate_sheet_cutting_layout", fake_validate)

	doc = sheet_cutting_layout.SheetCuttingLayout()
	doc.validate()

	assert called_with == [doc]


def test_revision_and_workflow_invalid_transitions_raise() -> None:
	from sheet_cutting_layout.services.versioning import create_revision
	from sheet_cutting_layout.services.workflow import LayoutWorkflowModel

	with pytest.raises(ValueError, match="Only released"):
		create_revision(type("Layout", (), {"status": "Draft"})())

	with pytest.raises(AssertionError, match="Expected layout state"):
		LayoutWorkflowModel().supersede()
