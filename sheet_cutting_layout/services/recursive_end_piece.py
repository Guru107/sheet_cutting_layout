from __future__ import annotations

from collections.abc import Callable

ItemExists = Callable[[str], bool]


def end_piece_has_child_layout(child_layout: object) -> bool:
	"""True when an end-piece row has a non-blank child layout link."""
	return bool(_clean(child_layout))


def child_raw_material_matches_end_piece_item(
	*,
	child_raw_material_item: object,
	end_piece_item_code: object,
) -> bool:
	child = _clean(child_raw_material_item)
	parent = _clean(end_piece_item_code)
	if child is None or parent is None:
		return False
	return child.casefold() == parent.casefold()


def child_release_blocked_until_parent_item_exists(
	*,
	raw_material_item: object,
	item_exists: ItemExists,
) -> bool:
	item = _clean(raw_material_item)
	if item is None:
		return False
	return not item_exists(item)


def _clean(value: object) -> str | None:
	if value is None:
		return None
	if isinstance(value, str):
		value = value.strip()
		return value or None
	return str(value)
