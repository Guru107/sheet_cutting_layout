from __future__ import annotations

import json
from dataclasses import dataclass, field
from math import inf, isfinite, nan
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
	end_piece_item: str
	weight_kg: float
	qty_per_sheet: float
	disposition: str = "Scrap"
	used_for_finished_part: str | None = None


@dataclass
class Layout:
	raw_material_item: str = "RAW-SHEET"
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


def test_canvas_payload_builder_returns_end_piece_zones_for_all_rows() -> None:
	from sheet_cutting_layout.services.canvas_payload import build_canvas_payload

	layout = Layout(
		end_pieces=[
			EndPiece("END-001", 0.5, 1),
			EndPiece("END-002", 0.25, 2),
		],
	)

	payload = build_canvas_payload(layout)

	assert len(payload["end_piece_zones"]) == len(layout.end_pieces)


def test_canvas_payload_builder_marks_invalid_dimensions_without_crashing() -> None:
	from sheet_cutting_layout.services.canvas_payload import build_canvas_payload

	layout = Layout(
		sheet_width_mm=0,
		no_of_strips=-1,
		finished_parts=[FinishedPart("PART001SHR", 0, 1, 0)],
		end_pieces=[EndPiece("END-001", 0.5, 0)],
	)

	payload = build_canvas_payload(layout)

	marked_fields = {marker["field"] for marker in payload["invalid_markers"]}
	assert "sheet_width_mm" in marked_fields
	assert "no_of_strips" in marked_fields
	assert "finished_parts[0].parts_per_sheet" in marked_fields
	assert "end_pieces[0].qty_per_sheet" in marked_fields


def test_canvas_payload_builder_rejects_non_finite_numbers() -> None:
	from sheet_cutting_layout.services.canvas_payload import build_canvas_payload

	layout = Layout(
		sheet_width_mm=nan,
		finished_parts=[FinishedPart("PART001SHR", 4, inf, 0)],
		end_pieces=[EndPiece("END-001", inf, nan)],
	)

	payload = build_canvas_payload(layout)

	marked_fields = {marker["field"] for marker in payload["invalid_markers"]}
	assert "sheet_width_mm" in marked_fields
	assert "finished_parts[0].gross_weight_per_part_kg" in marked_fields
	assert "end_pieces[0].weight_kg" in marked_fields
	assert "end_pieces[0].qty_per_sheet" in marked_fields
	assert payload["sheet_dimensions"]["width_mm"] is None
	assert payload["end_piece_zones"][0]["weight_kg"] is None
	assert payload["end_piece_zones"][0]["qty_per_sheet"] is None
	assert payload["summary"]["total_gross_weight_kg"] == 0
	assert payload["summary"]["total_end_piece_weight_kg"] == 0


def test_canvas_payload_builder_reports_one_marker_for_invalid_finished_part_count() -> None:
	from sheet_cutting_layout.services.canvas_payload import build_canvas_payload

	layout = Layout(finished_parts=[FinishedPart("PART001SHR", 0, 1, 0)])

	payload = build_canvas_payload(layout)

	markers = [
		marker
		for marker in payload["invalid_markers"]
		if marker["field"] == "finished_parts[0].parts_per_sheet"
	]
	assert len(markers) == 1


def test_canvas_payload_builder_marks_non_finite_integer_fields_without_crashing() -> None:
	from sheet_cutting_layout.services.canvas_payload import build_canvas_payload

	layout = Layout(
		no_of_strips=inf,
		finished_parts=[FinishedPart("PART001SHR", inf, 1, 0)],
	)

	payload = build_canvas_payload(layout)

	marked_fields = {marker["field"] for marker in payload["invalid_markers"]}
	assert "no_of_strips" in marked_fields
	assert "finished_parts[0].parts_per_sheet" in marked_fields


def test_canvas_payload_is_strict_json_serializable_for_non_finite_inputs() -> None:
	from sheet_cutting_layout.services.canvas_payload import build_canvas_payload

	layout = Layout(
		sheet_width_mm=nan,
		no_of_strips=inf,
		finished_parts=[FinishedPart("PART001SHR", inf, inf, nan)],
		end_pieces=[EndPiece("END-001", inf, nan)],
	)

	payload = build_canvas_payload(layout)

	assert _non_finite_float_paths(payload) == []
	json.dumps(payload, allow_nan=False)


@dataclass
class LayoutCase:
	layout: Layout
	finished_part: FinishedPart
	expected_derived_fg_weight_kg: float


@st.composite
def layout_case_strategy(draw: st.DrawFn) -> LayoutCase:
	parts_per_sheet = draw(st.integers(min_value=1, max_value=200))
	end_pieces = draw(end_pieces_strategy())
	process_scrap = draw(finite_weight_strategy())
	derived_fg_weight = draw(finite_weight_strategy())
	distributed_end_piece_scrap = sum(
		(end_piece.weight_kg * end_piece.qty_per_sheet) / parts_per_sheet for end_piece in end_pieces
	)
	gross_weight = process_scrap + distributed_end_piece_scrap + derived_fg_weight

	return LayoutCase(
		layout=Layout(end_pieces=end_pieces),
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
			end_piece_item=st.text(alphabet=ascii_letters + digits, min_size=1, max_size=24).map(
				lambda code: f"END{code}"
			),
			weight_kg=finite_weight_strategy(),
			qty_per_sheet=positive_finite_weight_strategy(),
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
	process_scrap_qty = _sum_bom_qty(bom.items, "process_scrap")
	end_piece_scrap_qty = _sum_bom_qty(bom.items, "end_piece_scrap")
	expected_end_piece_scrap_qty = sum(
		(end_piece.weight_kg * end_piece.qty_per_sheet) / layout_case.finished_part.parts_per_sheet
		for end_piece in layout_case.layout.end_pieces
	)
	total_scrap_qty = process_scrap_qty + end_piece_scrap_qty
	derived_fg_qty = layout_case.finished_part.gross_weight_per_part_kg - total_scrap_qty

	assert bom.quantity == 1
	assert _sum_bom_qty(bom.items, "raw_material") == pytest.approx(
		layout_case.finished_part.gross_weight_per_part_kg
	)
	assert process_scrap_qty == pytest.approx(layout_case.finished_part.scrap_weight_per_part_kg)
	assert end_piece_scrap_qty == pytest.approx(expected_end_piece_scrap_qty)
	assert total_scrap_qty == pytest.approx(
		layout_case.finished_part.scrap_weight_per_part_kg + expected_end_piece_scrap_qty
	)
	assert derived_fg_qty == pytest.approx(layout_case.expected_derived_fg_weight_kg)


def test_canvas_payload_summary_distributes_gross_scrap_and_end_pieces_consistently() -> None:
	from sheet_cutting_layout.services.canvas_payload import build_canvas_payload

	layout = Layout(
		finished_parts=[FinishedPart("PART001SHR", 4, 10, 1)],
		end_pieces=[EndPiece("END-001", 1.5, 2)],
	)

	payload = build_canvas_payload(layout)
	summary = payload["summary"]

	assert summary["total_gross_weight_kg"] == 40
	assert summary["total_process_scrap_weight_kg"] == 4
	assert summary["total_end_piece_weight_kg"] == 3
	assert summary["total_scrap_weight_kg"] == 7
	assert summary["derived_fg_estimate_kg"] == 33


def _sum_bom_qty(items: list[object], row_type: str) -> float:
	return sum(item.qty for item in items if item.row_type == row_type)


def _non_finite_float_paths(value: object, path: str = "payload") -> list[str]:
	if isinstance(value, float):
		return [] if isfinite(value) else [path]
	if isinstance(value, dict):
		paths: list[str] = []
		for key, child in value.items():
			paths.extend(_non_finite_float_paths(child, f"{path}.{key}"))
		return paths
	if isinstance(value, list):
		paths = []
		for index, child in enumerate(value):
			paths.extend(_non_finite_float_paths(child, f"{path}[{index}]"))
		return paths
	return []
