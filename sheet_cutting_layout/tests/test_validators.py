from __future__ import annotations

import importlib
import sys
import types
from dataclasses import dataclass, field

import pytest


class ValidationError(Exception):
	pass


class FakeFrappe:
	ValidationError = ValidationError

	def throw(self, message: str) -> None:
		raise ValidationError(message)


@dataclass
class FinishedPart:
	finished_part_item: str
	parts_per_sheet: int
	gross_weight_per_part_kg: float
	scrap_weight_per_part_kg: float = 0


@dataclass
class EndPiece:
	end_piece_item: str | None
	weight_kg: float | None
	qty_per_sheet: float | None


@dataclass
class Layout:
	finished_parts: list[FinishedPart] = field(default_factory=list)
	end_pieces: list[EndPiece] = field(default_factory=list)


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


def test_layout_requires_at_least_one_finished_part(validators: types.ModuleType) -> None:
	with pytest.raises(ValidationError, match="at least one finished part"):
		validators.validate_sheet_cutting_layout(Layout())


def test_finished_part_weights_must_be_non_negative(validators: types.ModuleType) -> None:
	with pytest.raises(ValidationError, match="Gross weight"):
		validators.validate_sheet_cutting_layout(Layout(finished_parts=[FinishedPart("AB12SHR", 1, -0.1, 0)]))

	with pytest.raises(ValidationError, match="Scrap weight"):
		validators.validate_sheet_cutting_layout(Layout(finished_parts=[FinishedPart("AB12SHR", 1, 1, -0.1)]))


def test_end_piece_rows_require_item_weight_and_qty(validators: types.ModuleType) -> None:
	with pytest.raises(ValidationError, match="End piece item"):
		validators.validate_sheet_cutting_layout(
			Layout(
				finished_parts=[FinishedPart("AB12SHR", 2, 5, 1)],
				end_pieces=[EndPiece(None, 1, 1)],
			)
		)

	with pytest.raises(ValidationError, match="End piece weight"):
		validators.validate_sheet_cutting_layout(
			Layout(
				finished_parts=[FinishedPart("AB12SHR", 2, 5, 1)],
				end_pieces=[EndPiece("EP1", None, 1)],
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
			finished_parts=[FinishedPart("AB12SHR", 2, 4, 1)],
			end_pieces=[EndPiece("EP1", 2, 1)],
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
