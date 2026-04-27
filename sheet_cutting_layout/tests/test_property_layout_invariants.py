from __future__ import annotations

import json
from dataclasses import dataclass, field
from math import inf, isfinite, nan


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
