from __future__ import annotations

import math

STEEL_DENSITY_G_PER_CM3 = 7.86
DEFAULT_PRECISION = 6


def _round(value: float, precision: int = DEFAULT_PRECISION) -> float:
	return round(float(value), precision)


def _positive_int(value: float | int | str | None) -> int | None:
	if value is None or isinstance(value, bool):
		return None
	if isinstance(value, int):
		integer = value
	elif isinstance(value, str):
		if not value.isdecimal():
			return None
		integer = int(value)
	else:
		return None
	if integer <= 0:
		return None
	return integer


def sheet_weight_kg(
	*,
	thickness_mm: float | int | str | None,
	width_mm: float | int | str | None,
	length_mm: float | int | str | None,
	precision: int = DEFAULT_PRECISION,
) -> float | None:
	"""Steel weight of a rectangular sheet/strip/part in kg.

	weight = thickness_mm * width_mm * length_mm * 0.786 / 100000
	       = thickness * width * length * 7.86 / 1_000_000
	"""
	try:
		thickness = float(thickness_mm)
		width = float(width_mm)
		length = float(length_mm)
	except (TypeError, ValueError):
		return None
	if not math.isfinite(thickness) or not math.isfinite(width) or not math.isfinite(length):
		return None
	if thickness <= 0 or width <= 0 or length <= 0:
		return None
	weight = length * width * thickness * STEEL_DENSITY_G_PER_CM3 / 1_000_000
	return _round(weight, precision)


def gross_weight_per_part_kg(
	*,
	weight_of_strip_kg: float | int | str | None,
	parts_per_strip: float | int | str | None,
	precision: int = DEFAULT_PRECISION,
) -> float | None:
	if weight_of_strip_kg is None or parts_per_strip is None:
		return None
	parts = _positive_int(parts_per_strip)
	if parts is None:
		return None
	try:
		weight = float(weight_of_strip_kg)
	except (TypeError, ValueError):
		return None
	if not math.isfinite(weight):
		return None
	if weight <= 0:
		return None
	return _round(weight / parts, precision)


def parts_per_sheet(
	*,
	parts_per_strip: float | int | str | None,
	no_of_strips: float | int | str | None,
) -> int | None:
	if parts_per_strip is None or no_of_strips is None:
		return None
	parts = _positive_int(parts_per_strip)
	strips = _positive_int(no_of_strips)
	if parts is None or strips is None:
		return None
	return parts * strips
