from __future__ import annotations

from collections.abc import Callable

ChildLinks = Callable[[str], list[str]]


class CascadeCycleError(Exception):
	"""Raised when a child_layout chain forms a cycle."""


def collect_descendant_layouts(root: str, child_links: ChildLinks) -> list[str]:
	"""Return layouts reachable from root through child links, leaves first."""
	ordered: list[str] = []
	seen: set[str] = set()

	def visit(layout_name: str, ancestors: tuple[str, ...]) -> None:
		if layout_name in ancestors:
			raise CascadeCycleError(
				f"child_layout cycle detected at {layout_name}: " f"{' -> '.join((*ancestors, layout_name))}"
			)
		next_ancestors = (*ancestors, layout_name)
		for child in child_links(layout_name):
			if not child or child in seen:
				continue
			visit(child, next_ancestors)
			seen.add(child)
			ordered.append(child)

	visit(root, ())
	return ordered
