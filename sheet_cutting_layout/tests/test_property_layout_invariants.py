from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from math import inf, isfinite, nan
from pathlib import Path
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


def test_canvas_payload_places_full_width_strips_down_sheet_length() -> None:
	from sheet_cutting_layout.services.canvas_payload import build_canvas_payload

	layout = Layout(
		sheet_width_mm=1250,
		sheet_length_mm=2500,
		strip_width_mm=1250,
		strip_length_mm=211,
		no_of_strips=11,
		parts_per_strip=7,
		parts_per_sheet=77,
		finished_parts=[FinishedPart("0101BW503230NSHR", 77, 0.47, 0.18)],
		end_pieces=[EndPiece("HSLA34016MM", 2.81, 1, "Reuse")],
	)

	payload = build_canvas_payload(layout)
	strips = payload["strips"]
	part_zones = payload["part_zones"]
	end_piece_zones = payload["end_piece_zones"]

	assert len(strips) == 11
	assert strips[0] == {
		"index": 1,
		"x_mm": 0,
		"y_mm": 0,
		"width_mm": 1250,
		"length_mm": 211,
	}
	assert strips[1]["x_mm"] == 0
	assert strips[1]["y_mm"] == 211
	assert strips[-1]["x_mm"] == 0
	assert strips[-1]["y_mm"] == 2110

	assert len(part_zones) == 77
	assert part_zones[0]["x_mm"] == 0
	assert part_zones[0]["y_mm"] == 0
	assert part_zones[6]["x_mm"] == pytest.approx(1250 * 6 / 7)
	assert part_zones[6]["y_mm"] == 0
	assert part_zones[7]["x_mm"] == 0
	assert part_zones[7]["y_mm"] == 211
	assert part_zones[-1]["x_mm"] == pytest.approx(1250 * 6 / 7)
	assert part_zones[-1]["y_mm"] == 2110

	assert end_piece_zones == [
		{
			"end_piece_item_code": "HSLA34016MM",
			"weight_kg": 2.81,
			"qty_per_sheet": 1.0,
			"disposition": "Reuse",
			"used_for_finished_part": None,
			"x_mm": 0,
			"y_mm": 2321,
			"width_mm": 1250,
			"length_mm": 179,
		}
	]


def test_browser_canvas_payload_places_full_width_strips_down_sheet_length() -> None:
	script_path = Path("sheet_cutting_layout/public/js/sheet_layout_canvas.js")
	node_script = f"""
const fs = require("node:fs");
const vm = require("node:vm");
const code = fs.readFileSync({str(script_path)!r}, "utf8");
const context = {{ window: {{ clearTimeout, setTimeout, devicePixelRatio: 1 }}, console }};
context.window.window = context.window;
vm.createContext(context);
vm.runInContext(code, context);
const payload = context.window.SheetLayoutCanvas.buildPayloadFromDoc({{
  sheet_width_mm: 1250,
  sheet_length_mm: 2500,
  sheet_thickness_mm: 1.2,
  strip_width_mm: 1250,
  strip_length_mm: 211,
  no_of_strips: 11,
  parts_per_strip: 7,
  parts_per_sheet: 77,
  finished_parts: [
    {{
      finished_part_item: "0101BW503230NSHR",
      parts_per_sheet: 77,
      gross_weight_per_part_kg: 0.47,
      scrap_weight_per_part_kg: 0.18,
    }},
  ],
  end_pieces: [
    {{
      end_piece_item_code: "HSLA34016MM",
      weight_kg: 2.81,
      qty_per_sheet: 1,
      disposition: "Reuse",
    }},
  ],
}});
const actual = {{
 secondStripX: payload.strips[1].x_mm,
 secondStripY: payload.strips[1].y_mm,
 eighthPartX: payload.part_zones[7].x_mm,
 eighthPartY: payload.part_zones[7].y_mm,
 lastPartX: payload.part_zones[76].x_mm,
 lastPartY: payload.part_zones[76].y_mm,
  remnantX: payload.end_piece_zones[0].x_mm,
  remnantY: payload.end_piece_zones[0].y_mm,
  remnantWidth: payload.end_piece_zones[0].width_mm,
  remnantLength: payload.end_piece_zones[0].length_mm,
}};
console.log(JSON.stringify(actual));
"""
	result = subprocess.run(["node", "-e", node_script], check=True, capture_output=True, text=True)
	actual = json.loads(result.stdout)

	assert actual["secondStripX"] == 0
	assert actual["secondStripY"] == 211
	assert actual["eighthPartX"] == 0
	assert actual["eighthPartY"] == 211
	assert actual["lastPartX"] == pytest.approx(1250 * 6 / 7)
	assert actual["lastPartY"] == 2110
	assert actual["remnantX"] == 0
	assert actual["remnantY"] == 2321
	assert actual["remnantWidth"] == 1250
	assert actual["remnantLength"] == 179


def test_browser_canvas_renderer_does_not_draw_part_grid_over_cutting_layout() -> None:
	script_path = Path("sheet_cutting_layout/public/js/sheet_layout_canvas.js")
	node_script = f"""
const fs = require("node:fs");
const vm = require("node:vm");
const code = fs.readFileSync({str(script_path)!r}, "utf8");
const calls = [];
const context = {{
  window: {{ clearTimeout, setTimeout, devicePixelRatio: 1 }},
  console,
}};
context.window.window = context.window;
vm.createContext(context);
vm.runInContext(code, context);
const canvas = {{
  clientWidth: 860,
  clientHeight: 420,
  width: 0,
  height: 0,
  getContext() {{
    return {{
      setTransform() {{}},
      clearRect() {{}},
      beginPath() {{}},
      moveTo() {{}},
      lineTo() {{}},
      closePath() {{}},
      fill() {{}},
      stroke() {{}},
      save() {{}},
      restore() {{}},
      translate() {{}},
      rotate() {{}},
      fillText() {{}},
      fillRect(x, y, width, height) {{ calls.push({{ type: "fillRect", x, y, width, height }}); }},
      strokeRect(x, y, width, height) {{ calls.push({{ type: "strokeRect", x, y, width, height }}); }},
      set fillStyle(value) {{}},
      set strokeStyle(value) {{}},
      set lineWidth(value) {{}},
      set font(value) {{}},
      set textAlign(value) {{}},
      set textBaseline(value) {{}},
    }};
  }},
}};
const payload = context.window.SheetLayoutCanvas.buildPayloadFromDoc({{
  sheet_width_mm: 1250,
  sheet_length_mm: 2500,
  sheet_thickness_mm: 1.2,
  strip_width_mm: 1250,
  strip_length_mm: 211,
  no_of_strips: 11,
  parts_per_strip: 7,
  parts_per_sheet: 77,
  finished_parts: [
    {{
      finished_part_item: "0101BW503230NSHR",
      parts_per_sheet: 77,
      gross_weight_per_part_kg: 0.47,
      scrap_weight_per_part_kg: 0.18,
    }},
  ],
  end_pieces: [
    {{
      end_piece_item_code: "HSLA34016MM",
      weight_kg: 2.81,
      qty_per_sheet: 1,
      disposition: "Reuse",
    }},
  ],
}});
context.window.SheetLayoutCanvas.render(canvas, payload);
const narrowVerticalOverlays = calls.filter((call) => call.width > 2 && call.width < 100 && call.height > 20);
console.log(JSON.stringify({{ narrowVerticalOverlayCount: narrowVerticalOverlays.length }}));
"""
	result = subprocess.run(["node", "-e", node_script], check=True, capture_output=True, text=True)
	actual = json.loads(result.stdout)

	assert actual["narrowVerticalOverlayCount"] == 0


def test_browser_canvas_renderer_uses_subtle_pseudo_depth() -> None:
	script_path = Path("sheet_cutting_layout/public/js/sheet_layout_canvas.js")
	node_script = f"""
const fs = require("node:fs");
const vm = require("node:vm");
const code = fs.readFileSync({str(script_path)!r}, "utf8");
const calls = [];
const context = {{
  window: {{ clearTimeout, setTimeout, devicePixelRatio: 1 }},
  console,
}};
context.window.window = context.window;
vm.createContext(context);
vm.runInContext(code, context);
const canvas = {{
  clientWidth: 860,
  clientHeight: 420,
  width: 0,
  height: 0,
  getContext() {{
    return {{
      setTransform() {{}},
      clearRect() {{}},
      beginPath() {{}},
      moveTo(x, y) {{ calls.push({{ type: "moveTo", x, y }}); }},
      lineTo(x, y) {{ calls.push({{ type: "lineTo", x, y }}); }},
      closePath() {{}},
      fill() {{}},
      stroke() {{}},
      save() {{}},
      restore() {{}},
      translate() {{}},
      rotate() {{}},
      fillText() {{}},
      fillRect(x, y, width, height) {{ calls.push({{ type: "fillRect", x, y, width, height }}); }},
      strokeRect() {{}},
      set fillStyle(value) {{}},
      set strokeStyle(value) {{}},
      set lineWidth(value) {{}},
      set font(value) {{}},
      set textAlign(value) {{}},
      set textBaseline(value) {{}},
    }};
  }},
}};
const payload = context.window.SheetLayoutCanvas.buildPayloadFromDoc({{
  sheet_width_mm: 1250,
  sheet_length_mm: 2500,
  sheet_thickness_mm: 1,
  strip_width_mm: 1250,
  strip_length_mm: 242,
  no_of_strips: 10,
  parts_per_strip: 8,
  parts_per_sheet: 80,
  finished_parts: [],
  end_pieces: [{{ end_piece_item_code: "RM1", weight_kg: 2.814, qty_per_sheet: 1, disposition: "Reuse" }}],
}});
context.window.SheetLayoutCanvas.render(canvas, payload);
const sheetFaceIndex = calls.findIndex((call) => call.type === "fillRect");
const sheetFace = calls[sheetFaceIndex];
const minLineY = Math.min(...calls.slice(0, sheetFaceIndex).filter((call) => call.type === "lineTo").map((call) => call.y));
console.log(JSON.stringify({{ pseudoDepth: sheetFace.y - minLineY }}));
"""
	result = subprocess.run(["node", "-e", node_script], check=True, capture_output=True, text=True)
	actual = json.loads(result.stdout)

	assert actual["pseudoDepth"] <= 8


def test_browser_canvas_renderer_draws_sheet_strip_and_end_piece_dimension_labels() -> None:
	script_path = Path("sheet_cutting_layout/public/js/sheet_layout_canvas.js")
	node_script = f"""
const fs = require("node:fs");
const vm = require("node:vm");
const code = fs.readFileSync({str(script_path)!r}, "utf8");
const labels = [];
const context = {{
  window: {{ clearTimeout, setTimeout, devicePixelRatio: 1 }},
  console,
}};
context.window.window = context.window;
vm.createContext(context);
vm.runInContext(code, context);
const canvas = {{
  clientWidth: 860,
  clientHeight: 420,
  width: 0,
  height: 0,
  getContext() {{
    return {{
      setTransform() {{}},
      clearRect() {{}},
      beginPath() {{}},
      moveTo() {{}},
      lineTo() {{}},
      closePath() {{}},
      fill() {{}},
      stroke() {{}},
      save() {{}},
      restore() {{}},
      translate() {{}},
      rotate() {{}},
      fillRect() {{}},
      strokeRect() {{}},
      fillText(text) {{ labels.push(String(text)); }},
      set fillStyle(value) {{}},
      set strokeStyle(value) {{}},
      set lineWidth(value) {{}},
      set font(value) {{}},
      set textAlign(value) {{}},
      set textBaseline(value) {{}},
    }};
  }},
}};
const payload = context.window.SheetLayoutCanvas.buildPayloadFromDoc({{
  sheet_width_mm: 1250,
  sheet_length_mm: 2500,
  sheet_thickness_mm: 1,
  strip_width_mm: 1250,
  strip_length_mm: 242,
  no_of_strips: 10,
  parts_per_strip: 8,
  parts_per_sheet: 80,
  finished_parts: [{{ finished_part_item: "FG001SHR", parts_per_sheet: 80, gross_weight_per_part_kg: 0.474, scrap_weight_per_part_kg: 0.185 }}],
  end_pieces: [{{ end_piece_item_code: "RM1", weight_kg: 2.814, qty_per_sheet: 1, disposition: "Reuse" }}],
}});
context.window.SheetLayoutCanvas.render(canvas, payload);
console.log(JSON.stringify({{ labels }}));
"""
	result = subprocess.run(["node", "-e", node_script], check=True, capture_output=True, text=True)
	actual = json.loads(result.stdout)

	assert "1250" in actual["labels"]
	assert "242" in actual["labels"]
	assert "80" in actual["labels"]


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


def test_canvas_payload_marks_non_numeric_values_without_crashing() -> None:
	from sheet_cutting_layout.services.canvas_payload import build_canvas_payload

	layout = Layout(
		sheet_width_mm="wide",
		no_of_strips="2.5",
		finished_parts=[FinishedPart("PART001SHR", "many", "gross", "scrap")],
		end_pieces=[EndPiece("", "heavy", "qty")],
	)

	payload = build_canvas_payload(layout)
	marked_fields = {marker["field"] for marker in payload["invalid_markers"]}

	assert "sheet_width_mm" in marked_fields
	assert "no_of_strips" in marked_fields
	assert "finished_parts[0].gross_weight_per_part_kg" in marked_fields
	assert "finished_parts[0].scrap_weight_per_part_kg" in marked_fields
	assert "end_pieces[0].weight_kg" in marked_fields
	assert "end_pieces[0].qty_per_sheet" in marked_fields


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
	weight_per_sheet = gross_weight * parts_per_sheet + sum(
		end_piece.weight_kg for end_piece in end_pieces
	)

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
		end_piece.weight_kg
		for end_piece in layout_case.layout.end_pieces
		if end_piece.disposition == "Scrap"
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
	assert summary["total_end_piece_weight_kg"] == 1.5
	assert summary["total_scrap_weight_kg"] == 5.5
	assert summary["derived_fg_estimate_kg"] == 34.5


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
