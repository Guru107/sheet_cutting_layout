from __future__ import annotations

from types import SimpleNamespace

from sheet_cutting_layout.tests import unittest_adapter
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


class FakeMark:
	def __init__(self, name: str, args: tuple[object, object]) -> None:
		self.name = name
		self.args = args


class TestUnittestAdapter(SheetCuttingLayoutTestCase):
	def test_parametrized_cases_recreate_autouse_fixture_context(self) -> None:
		counter = {"count": 0}
		observed_counts: list[int] = []

		def autouse_counter() -> None:
			counter["count"] += 1
			return None

		autouse_counter._fixture_function_marker = SimpleNamespace(autouse=True)

		def test_fn(case_index: int) -> None:
			_ = case_index
			observed_counts.append(counter["count"])

		test_fn.pytestmark = [FakeMark("parametrize", ("case_index", [0, 1, 2]))]

		test_method = unittest_adapter._build_test_method(
			{"autouse_counter": autouse_counter, "test_fn": test_fn},
			test_fn,
		)

		test_method(self)

		self.assertEqual(observed_counts, [1, 2, 3])

	def test_parametrized_cases_honor_pytestfixturefunction_autouse_marker(self) -> None:
		counter = {"count": 0}
		observed_counts: list[int] = []

		def autouse_counter() -> None:
			counter["count"] += 1
			return None

		autouse_counter._pytestfixturefunction = SimpleNamespace(autouse=True)

		def test_fn(case_index: int) -> None:
			_ = case_index
			observed_counts.append(counter["count"])

		test_fn.pytestmark = [FakeMark("parametrize", ("case_index", [0, 1, 2]))]

		test_method = unittest_adapter._build_test_method(
			{"autouse_counter": autouse_counter, "test_fn": test_fn},
			test_fn,
		)

		test_method(self)

		self.assertEqual(observed_counts, [1, 2, 3])

	def test_parametrized_cases_recreate_regular_fixture_values(self) -> None:
		def box_fixture() -> dict[str, list[str]]:
			return {"values": []}

		def test_fn(label: str, box_fixture: dict[str, list[str]]) -> None:
			box_fixture["values"].append(label)
			self.assertEqual(box_fixture["values"], [label])

		test_fn.pytestmark = [FakeMark("parametrize", ("label", ["A", "B", "C"]))]

		test_method = unittest_adapter._build_test_method(
			{"box_fixture": box_fixture, "test_fn": test_fn},
			test_fn,
		)

		test_method(self)
