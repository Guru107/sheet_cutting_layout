from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


class TestAlternativeItemService(SheetCuttingLayoutTestCase):
	def _meta(self, fields: set[str], *, table_options: dict[str, str] | None = None) -> object:
		table_options = table_options or {}

		def get_field(fieldname: str) -> object | None:
			child_doctype = table_options.get(fieldname)
			if child_doctype is None:
				return None
			return SimpleNamespace(options=child_doctype)

		return SimpleNamespace(
			has_field=lambda fieldname: fieldname in fields,
			get_field=get_field,
		)

	def test_set_allow_alternative_item_if_supported_sets_doc_field(self) -> None:
		from sheet_cutting_layout.services.alternative_item import (
			set_allow_alternative_item_if_supported,
		)

		doc = SimpleNamespace(doctype="BOM", meta=self._meta({"allow_alternative_item"}))

		assert set_allow_alternative_item_if_supported(doc) is True
		assert doc.allow_alternative_item == 1

	def test_set_allow_alternative_item_if_supported_skips_missing_field(self) -> None:
		from sheet_cutting_layout.services.alternative_item import (
			set_allow_alternative_item_if_supported,
		)

		doc = SimpleNamespace(doctype="BOM", meta=self._meta(set()))

		assert set_allow_alternative_item_if_supported(doc) is False
		assert not hasattr(doc, "allow_alternative_item")

	def test_bom_item_values_adds_flag_when_child_schema_supports_field(self) -> None:
		from sheet_cutting_layout.services import alternative_item

		bom = SimpleNamespace(
			doctype="BOM",
			meta=self._meta({"items"}, table_options={"items": "BOM Item"}),
		)
		fake_frappe = SimpleNamespace(
			get_meta=lambda doctype: self._meta({"allow_alternative_item"})
			if doctype == "BOM Item"
			else self._meta(set())
		)

		with patch.object(alternative_item, "frappe", fake_frappe):
			values = alternative_item.with_bom_item_allow_alternative_item(
				bom,
				"items",
				{"item_code": "RM-001", "qty": 1, "uom": "Kg"},
			)

		assert values == {
			"item_code": "RM-001",
			"qty": 1,
			"uom": "Kg",
			"allow_alternative_item": 1,
		}

	def test_bom_item_values_skips_flag_when_child_schema_does_not_support_field(self) -> None:
		from sheet_cutting_layout.services import alternative_item

		bom = SimpleNamespace(
			doctype="BOM",
			meta=self._meta({"items"}, table_options={"items": "BOM Item"}),
		)
		fake_frappe = SimpleNamespace(get_meta=lambda _doctype: self._meta(set()))

		with patch.object(alternative_item, "frappe", fake_frappe):
			values = alternative_item.with_bom_item_allow_alternative_item(
				bom,
				"items",
				{"item_code": "RM-001", "qty": 1, "uom": "Kg"},
			)

		assert values == {"item_code": "RM-001", "qty": 1, "uom": "Kg"}

	def test_ensure_item_allows_alternatives_updates_item_when_schema_supports_field(self) -> None:
		from sheet_cutting_layout.services import alternative_item

		db = SimpleNamespace(set_value_calls=[])

		def set_value(
			doctype: str,
			name: str,
			fieldname: str,
			value: object,
			**kwargs: object,
		) -> None:
			db.set_value_calls.append((doctype, name, fieldname, value, kwargs))

		db.set_value = set_value
		fake_frappe = SimpleNamespace(
			db=db,
			get_meta=lambda doctype: self._meta({"allow_alternative_item"})
			if doctype == "Item"
			else self._meta(set()),
		)

		with patch.object(alternative_item, "frappe", fake_frappe):
			assert alternative_item.ensure_item_allows_alternatives(" RM-001 ") is True

		assert db.set_value_calls == [
			("Item", "RM-001", "allow_alternative_item", 1, {}),
		]

	def test_ensure_item_allows_alternatives_skips_blank_item_code(self) -> None:
		from sheet_cutting_layout.services import alternative_item

		db = SimpleNamespace(set_value_calls=[])

		def set_value(*args: object, **kwargs: object) -> None:
			db.set_value_calls.append((args, kwargs))

		db.set_value = set_value
		fake_frappe = SimpleNamespace(db=db, get_meta=lambda _doctype: self._meta({"allow_alternative_item"}))

		with patch.object(alternative_item, "frappe", fake_frappe):
			assert alternative_item.ensure_item_allows_alternatives("  ") is False

		assert db.set_value_calls == []
