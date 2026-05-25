from __future__ import annotations

from dataclasses import dataclass, field
from string import ascii_letters, digits

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


@dataclass
class FinishedPart:
	finished_part_item: str
	parts_per_sheet: int
	gross_weight_per_part_kg: float
	scrap_weight_per_part_kg: float


@dataclass
class EndPiece:
	end_piece_item_code: str
	weight_kg: float
	qty_per_sheet: float
	disposition: str = "Scrap"
	scrap_item: str | None = None
	used_for_finished_part: str | None = None


@dataclass
class Layout:
	raw_material_item: str = "RAW-SHEET"
	process_scrap_item: str = "PROCESS-SCRAP"
	weight_per_sheet_kg: float | None = None
	sheet_width_mm: float = 1000
	sheet_length_mm: float = 2000
	sheet_thickness_mm: float = 1.2
	strip_width_mm: float = 250
	strip_length_mm: float = 2000
	no_of_strips: int = 4
	parts_per_strip: int = 2
	parts_per_sheet: int = 8
	finished_parts: list[FinishedPart] = field(default_factory=list)
	end_pieces: list[EndPiece] = field(default_factory=list)


@dataclass
class LayoutCase:
	layout: Layout
	finished_part: FinishedPart
	expected_derived_fg_weight_kg: float


@st.composite
def layout_case_strategy(draw: st.DrawFn) -> LayoutCase:
	parts_per_sheet = draw(st.integers(min_value=1, max_value=200))
	no_of_strips = draw(st.integers(min_value=1, max_value=20))
	end_pieces = draw(end_pieces_strategy())
	process_scrap = draw(finite_weight_strategy())
	derived_fg_weight = draw(finite_weight_strategy())
	gross_weight = process_scrap + derived_fg_weight
	weight_per_sheet = gross_weight * parts_per_sheet + sum(end_piece.weight_kg for end_piece in end_pieces)

	return LayoutCase(
		layout=Layout(
			end_pieces=end_pieces,
			no_of_strips=no_of_strips,
			weight_per_sheet_kg=weight_per_sheet,
		),
		finished_part=FinishedPart(
			finished_part_item=draw(finished_part_code_strategy()),
			parts_per_sheet=parts_per_sheet,
			gross_weight_per_part_kg=gross_weight,
			scrap_weight_per_part_kg=process_scrap,
		),
		expected_derived_fg_weight_kg=derived_fg_weight,
	)


def finished_part_code_strategy() -> st.SearchStrategy[str]:
	return st.text(alphabet=ascii_letters + digits, min_size=1, max_size=24).map(lambda code: f"{code}SHR")


def end_pieces_strategy() -> st.SearchStrategy[list[EndPiece]]:
	return st.lists(
		st.builds(
			EndPiece,
			end_piece_item_code=st.text(alphabet=ascii_letters + digits, min_size=1, max_size=24).map(
				lambda code: f"END{code}"
			),
			weight_kg=finite_weight_strategy(),
			qty_per_sheet=positive_finite_weight_strategy(),
			disposition=st.sampled_from(["Reuse", "Hold", "Scrap"]),
			scrap_item=st.text(alphabet=ascii_letters + digits, min_size=1, max_size=24).map(
				lambda code: f"SCRAP{code}"
			),
		),
		max_size=5,
	)


def finite_weight_strategy() -> st.SearchStrategy[float]:
	return st.floats(
		min_value=0,
		max_value=10_000,
		allow_nan=False,
		allow_infinity=False,
		width=32,
	)


def positive_finite_weight_strategy() -> st.SearchStrategy[float]:
	return st.floats(
		min_value=0,
		max_value=10_000,
		allow_nan=False,
		allow_infinity=False,
		width=32,
		exclude_min=True,
	)


@given(layout_case_strategy())
@settings(max_examples=40)
def test_bom_invariants_hold_for_random_valid_layouts(layout_case: LayoutCase) -> None:
	from sheet_cutting_layout.services.bom_service import build_bom_from_layout_row

	bom = build_bom_from_layout_row(layout_case.layout, layout_case.finished_part)
	process_scrap_qty = _sum_bom_qty(bom.scrap_items, "process_scrap")
	end_piece_scrap_qty = _sum_bom_qty(bom.scrap_items, "end_piece_scrap")
	expected_end_piece_scrap_qty = sum(
		end_piece.weight_kg for end_piece in layout_case.layout.end_pieces if end_piece.disposition == "Scrap"
	)
	total_scrap_qty = process_scrap_qty + end_piece_scrap_qty
	derived_fg_qty = (
		layout_case.finished_part.gross_weight_per_part_kg
		- layout_case.finished_part.scrap_weight_per_part_kg
	)

	assert bom.quantity == layout_case.layout.no_of_strips
	assert _sum_bom_qty(bom.items, "raw_material") == pytest.approx(layout_case.layout.weight_per_sheet_kg)
	assert process_scrap_qty == pytest.approx(
		layout_case.finished_part.scrap_weight_per_part_kg * layout_case.finished_part.parts_per_sheet
	)
	assert end_piece_scrap_qty == pytest.approx(expected_end_piece_scrap_qty)
	assert total_scrap_qty == pytest.approx(
		layout_case.finished_part.scrap_weight_per_part_kg * layout_case.finished_part.parts_per_sheet
		+ expected_end_piece_scrap_qty
	)
	assert derived_fg_qty == pytest.approx(layout_case.expected_derived_fg_weight_kg, rel=1e-6, abs=1e-6)


def _sum_bom_qty(items: list[object], row_type: str) -> float:
	return sum(item.qty for item in items if item.row_type == row_type)
