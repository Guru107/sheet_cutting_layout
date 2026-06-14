from __future__ import annotations

from sheet_cutting_layout.services.cascade_graph import (
	CascadeCycleError,
	collect_descendant_layouts,
)
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


def _links_from_map(graph: dict[str, list[str]]):
	def child_links(layout_name: str) -> list[str]:
		return list(graph.get(layout_name, []))

	return child_links


class TestCascadeGraph(SheetCuttingLayoutTestCase):
	def test_returns_empty_for_layout_without_children(self) -> None:
		self.assertEqual(collect_descendant_layouts("ROOT", _links_from_map({"ROOT": []})), [])

	def test_two_levels_are_returned_leaves_first(self) -> None:
		child_links = _links_from_map({"ROOT": ["CHILD"], "CHILD": ["GRANDCHILD"]})
		self.assertEqual(collect_descendant_layouts("ROOT", child_links), ["GRANDCHILD", "CHILD"])

	def test_multiple_children_are_each_expanded_before_parent(self) -> None:
		child_links = _links_from_map({"ROOT": ["A", "B"], "A": ["A1"], "A1": [], "B": []})
		self.assertEqual(collect_descendant_layouts("ROOT", child_links), ["A1", "A", "B"])

	def test_shared_descendant_is_listed_once(self) -> None:
		child_links = _links_from_map(
			{"ROOT": ["A", "B"], "A": ["SHARED"], "B": ["SHARED"], "SHARED": []}
		)
		self.assertEqual(collect_descendant_layouts("ROOT", child_links), ["SHARED", "A", "B"])

	def test_direct_self_reference_raises_cycle_error(self) -> None:
		with self.assertRaises(CascadeCycleError):
			collect_descendant_layouts("ROOT", _links_from_map({"ROOT": ["ROOT"]}))

	def test_indirect_cycle_raises_cycle_error(self) -> None:
		child_links = _links_from_map({"ROOT": ["CHILD"], "CHILD": ["ROOT"]})
		with self.assertRaises(CascadeCycleError):
			collect_descendant_layouts("ROOT", child_links)
