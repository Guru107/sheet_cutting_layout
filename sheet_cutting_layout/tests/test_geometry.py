from __future__ import annotations

import math
import unittest

from sheet_cutting_layout.services import geometry


class TestGeometry(unittest.TestCase):
	def test_sheet_weight_uses_steel_density_factor(self) -> None:
		# 1mm x 1250mm x 2500mm sheet: 1 * 1250 * 2500 * 0.786 / 100000 = 24.5625
		self.assertAlmostEqual(
			geometry.sheet_weight_kg(thickness_mm=1, width_mm=1250, length_mm=2500),
			24.5625,
			places=6,
		)

	def test_sheet_weight_precision_rounds_final_result(self) -> None:
		self.assertEqual(
			geometry.sheet_weight_kg(thickness_mm=1, width_mm=1234, length_mm=2345, precision=3),
			22.745,
		)

	def test_sheet_weight_can_round_density_separately_for_legacy_callers(self) -> None:
		self.assertEqual(
			geometry.sheet_weight_kg(
				thickness_mm=10,
				width_mm=1000,
				length_mm=1000,
				precision=6,
				density_precision=1,
			),
			79.0,
		)

	def test_sheet_weight_returns_none_for_nonpositive_or_invalid(self) -> None:
		self.assertIsNone(geometry.sheet_weight_kg(thickness_mm=None, width_mm=1250, length_mm=2500))
		self.assertIsNone(geometry.sheet_weight_kg(thickness_mm=0, width_mm=1250, length_mm=2500))
		self.assertIsNone(geometry.sheet_weight_kg(thickness_mm=1, width_mm=-1, length_mm=2500))
		self.assertIsNone(geometry.sheet_weight_kg(thickness_mm="x", width_mm=1250, length_mm=2500))

	def test_sheet_weight_returns_none_for_nonfinite_inputs(self) -> None:
		self.assertIsNone(geometry.sheet_weight_kg(thickness_mm=math.nan, width_mm=1250, length_mm=2500))
		self.assertIsNone(geometry.sheet_weight_kg(thickness_mm=1, width_mm=math.inf, length_mm=2500))

	def test_gross_weight_per_part_divides_strip_weight(self) -> None:
		self.assertAlmostEqual(
			geometry.gross_weight_per_part_kg(weight_of_strip_kg=10.0, parts_per_strip=4),
			2.5,
			places=6,
		)
		self.assertAlmostEqual(
			geometry.gross_weight_per_part_kg(weight_of_strip_kg="10.0", parts_per_strip="4"),
			2.5,
			places=6,
		)

	def test_gross_weight_per_part_guards_zero_parts(self) -> None:
		self.assertIsNone(geometry.gross_weight_per_part_kg(weight_of_strip_kg=10.0, parts_per_strip=0))
		self.assertIsNone(geometry.gross_weight_per_part_kg(weight_of_strip_kg=10.0, parts_per_strip=None))
		self.assertIsNone(geometry.gross_weight_per_part_kg(weight_of_strip_kg=10.0, parts_per_strip="x"))
		self.assertIsNone(geometry.gross_weight_per_part_kg(weight_of_strip_kg=None, parts_per_strip=4))

	def test_gross_weight_per_part_guards_invalid_or_nonpositive_strip_weight(self) -> None:
		self.assertIsNone(geometry.gross_weight_per_part_kg(weight_of_strip_kg="x", parts_per_strip=4))
		self.assertIsNone(geometry.gross_weight_per_part_kg(weight_of_strip_kg=0, parts_per_strip=4))
		self.assertIsNone(geometry.gross_weight_per_part_kg(weight_of_strip_kg=-1, parts_per_strip=4))

	def test_gross_weight_per_part_guards_nonfinite_inputs(self) -> None:
		self.assertIsNone(geometry.gross_weight_per_part_kg(weight_of_strip_kg=math.inf, parts_per_strip=4))
		self.assertIsNone(geometry.gross_weight_per_part_kg(weight_of_strip_kg=10.0, parts_per_strip=math.inf))

	def test_gross_weight_per_part_rejects_nonintegral_part_counts(self) -> None:
		self.assertIsNone(geometry.gross_weight_per_part_kg(weight_of_strip_kg=10.0, parts_per_strip=4.5))
		self.assertIsNone(geometry.gross_weight_per_part_kg(weight_of_strip_kg=10.0, parts_per_strip="4.0"))

	def test_parts_per_sheet_multiplies_strip_count(self) -> None:
		self.assertEqual(geometry.parts_per_sheet(parts_per_strip=7, no_of_strips=11), 77)
		self.assertEqual(geometry.parts_per_sheet(parts_per_strip="7", no_of_strips="11"), 77)
		self.assertIsNone(geometry.parts_per_sheet(parts_per_strip=None, no_of_strips=11))
		self.assertIsNone(geometry.parts_per_sheet(parts_per_strip=0, no_of_strips=11))
		self.assertIsNone(geometry.parts_per_sheet(parts_per_strip=7, no_of_strips=0))
		self.assertIsNone(geometry.parts_per_sheet(parts_per_strip=7, no_of_strips=None))

	def test_parts_per_sheet_guards_invalid_inputs(self) -> None:
		self.assertIsNone(geometry.parts_per_sheet(parts_per_strip="x", no_of_strips=11))
		self.assertIsNone(geometry.parts_per_sheet(parts_per_strip=7, no_of_strips="x"))

	def test_parts_per_sheet_guards_nonfinite_inputs(self) -> None:
		self.assertIsNone(geometry.parts_per_sheet(parts_per_strip=math.nan, no_of_strips=11))
		self.assertIsNone(geometry.parts_per_sheet(parts_per_strip=7, no_of_strips=math.inf))

	def test_parts_per_sheet_rejects_nonintegral_counts(self) -> None:
		self.assertIsNone(geometry.parts_per_sheet(parts_per_strip=4.5, no_of_strips=11))
		self.assertIsNone(geometry.parts_per_sheet(parts_per_strip="4.0", no_of_strips=11))
		self.assertIsNone(geometry.parts_per_sheet(parts_per_strip=7, no_of_strips=11.5))
		self.assertIsNone(geometry.parts_per_sheet(parts_per_strip=7, no_of_strips="11.0"))
