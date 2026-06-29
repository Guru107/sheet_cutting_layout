from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from sheet_cutting_layout.overrides.bom import validate_shearing_bom_source
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase
from sheet_cutting_layout.tests.factories import ensure_item


@dataclass
class EndPiece:
	idx: int = 1
	disposition: str = "Reuse"
	end_piece_item_code: str | None = None
	generated_end_piece_bom: str | None = None
	width_mm: float | None = 100
	length_mm: float | None = 200
	weight_kg: float | None = 2.5
	strip_width_mm: float | None = None
	strip_length_mm: float | None = None
	strip_weight_kg: float | None = 2.5
	used_for_finished_part: str | None = "FG01SHR"
	bom_quantity: float | None = 1
	net_weight_per_part_kg: float | None = 2.5
	gross_weight_per_part_kg: float | None = 2.5
	scrap_weight_per_part_kg: float | None = 0
	bom_scrap_quantity_kg: float | None = 0
	scrap_item: str | None = None
	db_set_calls: list[tuple[object, object, dict[str, object]]] = field(default_factory=list)

	def db_set(self, fieldname: object, value: object = None, **kwargs: object) -> None:
		self.db_set_calls.append((fieldname, value, kwargs))


@dataclass
class Layout:
	name: str = "SCL-001"
	doctype: str = "Sheet Cutting Layout"
	workflow_status: str = "Released"
	company: str | None = "Test Company"
	finished_part_code: str | None = "FG01SHR"
	raw_material_item: str = "RAW-001"
	sheet_thickness_mm: float = 2
	process_scrap_item: str | None = "PROCESS-SCRAP"
	end_piece_bom_status: str | None = None
	end_pieces: list[EndPiece] = field(default_factory=list)
	save_calls: list[dict[str, object]] = field(default_factory=list)
	db_set_calls: list[tuple[object, object, dict[str, object]]] = field(default_factory=list)

	def save(self, **kwargs: object) -> None:
		self.save_calls.append(kwargs)

	def db_set(self, fieldname: object, value: object = None, **kwargs: object) -> None:
		self.db_set_calls.append((fieldname, value, kwargs))


@dataclass
class SubmittedLayout(Layout):
	docstatus: int = 1

	def save(self, **kwargs: object) -> None:
		raise AssertionError("Submitted layouts must not call save() during generated-link persistence")


class FakeDoc:
	def __init__(self, doctype: str) -> None:
		self.doctype = doctype
		self.name = ""
		self.items: list[dict[str, object]] = []
		self.scrap_items: list[dict[str, object]] = []
		self.uoms: list[dict[str, object]] = []
		self.insert_calls = 0
		self.submit_calls = 0
		self.save_calls: list[dict[str, object]] = []

	def append(self, fieldname: str, row: dict[str, object]) -> None:
		getattr(self, fieldname).append(row)

	def insert(self, ignore_permissions: bool = False) -> FakeDoc:
		self.insert_calls += 1
		self.ignore_permissions = ignore_permissions
		if self.doctype == "Item" and not any(row.get("uom") == self.stock_uom for row in self.uoms):
			self.uoms.insert(0, {"uom": self.stock_uom, "conversion_factor": 1})
		if self.doctype == "BOM":
			validate_shearing_bom_source(self, "before_insert")
		if self.doctype == "BOM" and not getattr(self, "company", None):
			raise ValueError("Company is required")
		if not self.name:
			self.name = f"{self.doctype}-{id(self)}"
		return self

	def submit(self) -> FakeDoc:
		self.submit_calls += 1
		return self

	def save(self, **kwargs: object) -> FakeDoc:
		self.save_calls.append(kwargs)
		return self


class FakeDB:
	def __init__(
		self,
		*,
		existing_items: set[str] | None = None,
		raw_item_groups: dict[str, str] | None = None,
		item_hsn_codes: dict[str, str] | None = None,
		raw_item_valuation_rates: dict[str, float] | None = None,
	) -> None:
		self.existing_items = set(existing_items or set())
		self.raw_item_groups = raw_item_groups or {"RAW-001": "Raw Material"}
		self.item_hsn_codes = item_hsn_codes or {}
		self.raw_item_valuation_rates = raw_item_valuation_rates or {}
		self.set_value_calls: list[tuple[str, str, str, object, dict[str, object]]] = []

	def exists(self, doctype: str, name: str) -> bool:
		return doctype == "Item" and name in self.existing_items

	def get_value(self, doctype: str, name: str, fieldname: str) -> object:
		if doctype == "Item" and fieldname == "item_group":
			return self.raw_item_groups.get(name)
		if doctype == "Item" and fieldname == "gst_hsn_code":
			return self.item_hsn_codes.get(name)
		if doctype == "Item" and fieldname == "valuation_rate":
			return self.raw_item_valuation_rates.get(name)
		return None

	def set_value(
		self,
		doctype: str,
		name: str,
		fieldname: str,
		value: object,
		**kwargs: object,
	) -> None:
		self.set_value_calls.append((doctype, name, fieldname, value, kwargs))
		if doctype == "Item" and fieldname == "valuation_rate":
			self.raw_item_valuation_rates[name] = value  # type: ignore[assignment]

	def get_default(self, key: str) -> str | None:
		if key == "company":
			return "DB Default Company"
		return None


class FakeFrappe:
	def __init__(
		self,
		*,
		existing_items: set[str] | None = None,
		raw_item_groups: dict[str, str] | None = None,
		item_hsn_codes: dict[str, str] | None = None,
		raw_item_valuation_rates: dict[str, float] | None = None,
	) -> None:
		self.db = FakeDB(
			existing_items=existing_items,
			raw_item_groups=raw_item_groups,
			item_hsn_codes=item_hsn_codes,
			raw_item_valuation_rates=raw_item_valuation_rates,
		)
		self.created_docs: list[FakeDoc] = []
		self.defaults = SimpleNamespace(get_user_default=lambda _key: "")
		self.ValidationError = ValueError
		self.DuplicateEntryError = ValueError
		self.logged_errors: list[dict[str, str | None]] = []
		self._ = lambda message: message

	def new_doc(self, doctype: str) -> FakeDoc:
		doc = FakeDoc(doctype)
		self.created_docs.append(doc)
		return doc

	def get_cached_value(self, doctype: str, name: str, fieldname: str) -> object:
		return self.db.get_value(doctype, name, fieldname)

	def get_doc(self, doctype: str, name: str) -> FakeDoc:
		doc = FakeDoc(doctype)
		doc.name = name
		self.created_docs.append(doc)
		return doc

	def throw(self, message: str) -> None:
		raise ValueError(message)

	def log_error(self, message: str | None = None, title: str | None = None) -> None:
		self.logged_errors.append({"message": message, "title": title})

	def get_traceback(self) -> str:
		return "traceback"


class TestEndPieceBomService(SheetCuttingLayoutTestCase):
	def setUp(self) -> None:
		super().setUp()
		self.service = importlib.import_module("sheet_cutting_layout.services.end_piece_bom_service")
		self.item_service = importlib.import_module("sheet_cutting_layout.services.end_piece_item_service")

	def _created_doc(self, fake_frappe: FakeFrappe, doctype: str) -> FakeDoc:
		return next(doc for doc in fake_frappe.created_docs if doc.doctype == doctype)

	def _install_fakes(
		self,
		*,
		existing_items: set[str] | None = None,
		raw_item_groups: dict[str, str] | None = None,
		item_hsn_codes: dict[str, str] | None = None,
		raw_item_valuation_rates: dict[str, float] | None = None,
	) -> FakeFrappe:
		fake_frappe = FakeFrappe(
			existing_items=existing_items,
			raw_item_groups=raw_item_groups,
			item_hsn_codes=item_hsn_codes,
			raw_item_valuation_rates=raw_item_valuation_rates,
		)
		self.frappe_patch = patch.object(self.service, "frappe", fake_frappe)
		self.translation_patch = patch.object(self.service, "_", lambda message: message)
		self.item_frappe_patch = patch.object(self.item_service, "frappe", fake_frappe)
		self.item_translation_patch = patch.object(self.item_service, "_", lambda message: message)
		self.frappe_patch.start()
		self.translation_patch.start()
		self.item_frappe_patch.start()
		self.item_translation_patch.start()
		self.addCleanup(self.frappe_patch.stop)
		self.addCleanup(self.translation_patch.stop)
		self.addCleanup(self.item_frappe_patch.stop)
		self.addCleanup(self.item_translation_patch.stop)
		return fake_frappe

	def test_get_value_returns_none_for_missing_name_without_query(self) -> None:
		from sheet_cutting_layout.services import end_piece_item_service

		with patch("frappe.get_cached_value") as spy:
			self.assertIsNone(end_piece_item_service._get_value("Item", None, "item_group"))
			self.assertIsNone(end_piece_item_service._get_value("Item", "", "item_group"))
			self.assertIsNone(end_piece_item_service._get_value("Item", "   ", "item_group"))

		spy.assert_not_called()

	def test_get_value_uses_get_cached_value(self) -> None:
		from sheet_cutting_layout.services import end_piece_item_service

		with patch("frappe.get_cached_value", return_value="GRP") as spy:
			result = end_piece_item_service._get_value("Item", "SOME-ITEM", "item_group")

		self.assertEqual(result, "GRP")
		spy.assert_called_once_with("Item", "SOME-ITEM", "item_group")

	def test_append_app_created_item_uoms_supports_nos_and_rejects_other_stock_uoms(self) -> None:
		from sheet_cutting_layout.services import end_piece_item_service

		item = FakeDoc("Item")
		end_piece_item_service._append_app_created_item_uoms(item, stock_uom="Nos", weight_kg=2)

		self.assertEqual(item.uoms, [{"uom": "Kg", "conversion_factor": 0.5}])

		end_piece_item_service._append_app_created_item_uoms(item, stock_uom="Nos", weight_kg=4)
		self.assertEqual(item.uoms, [{"uom": "Kg", "conversion_factor": 0.25}])

		with (
			patch.object(end_piece_item_service, "_", lambda message: message),
			self.assertRaisesRegex(Exception, "Unsupported stock UOM"),
		):
			end_piece_item_service._append_app_created_item_uoms(item, stock_uom="Box", weight_kg=2)

	def test_item_exists_uses_db_exists_fallback(self) -> None:
		from sheet_cutting_layout.services import end_piece_item_service

		fake_frappe = SimpleNamespace(
			db=object(),
			db_exists=lambda doctype, name: doctype == "Item" and name == "FG01SHR-EP-2x100x200",
		)

		with patch.object(end_piece_item_service, "frappe", fake_frappe):
			self.assertTrue(end_piece_item_service._item_exists("FG01SHR-EP-2x100x200"))
			self.assertFalse(end_piece_item_service._item_exists("MISSING"))

	def test_item_exists_returns_false_when_no_lookup_api_is_available(self) -> None:
		from sheet_cutting_layout.services import end_piece_item_service

		with patch.object(end_piece_item_service, "frappe", SimpleNamespace(db=object())):
			self.assertFalse(end_piece_item_service._item_exists("FG01SHR-EP-2x100x200"))

	def test_clean_converts_non_string_values(self) -> None:
		from sheet_cutting_layout.services import end_piece_item_service

		self.assertIsNone(end_piece_item_service._clean(None))
		self.assertEqual(end_piece_item_service._clean("  FG01SHR  "), "FG01SHR")
		self.assertIsNone(end_piece_item_service._clean("   "))
		self.assertEqual(end_piece_item_service._clean(123), "123")

	def test_existing_item_valuation_repair_skips_when_raw_material_rate_is_not_positive(self) -> None:
		fake_frappe = self._install_fakes(
			existing_items={"FG01SHR-EP-2x100x200"},
			raw_item_valuation_rates={
				"FG01SHR-EP-2x100x200": 0,
				"RAW-001": 0,
			},
		)

		item_code = self.item_service.ensure_end_piece_item(Layout(), EndPiece())

		self.assertEqual(item_code, "FG01SHR-EP-2x100x200")
		self.assertEqual(
			self._created_doc(fake_frappe, "Item").uoms, [{"uom": "Nos", "conversion_factor": 2.5}]
		)
		self.assertEqual(self._created_doc(fake_frappe, "Item").save_calls, [{"ignore_permissions": True}])

	def test_generation_requires_released_layout(self) -> None:
		self._install_fakes()
		layout = Layout(workflow_status="Draft", end_pieces=[EndPiece()])

		with self.assertRaisesRegex(ValueError, "only after release"):
			self.service.generate_end_piece_boms(layout)

	def test_generation_reuses_existing_item_and_creates_bom(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		fake_frappe = self._install_fakes(existing_items={existing_code})
		layout = Layout(end_pieces=[EndPiece()])

		result = self.service.generate_end_piece_boms(layout)

		self.assertEqual(result["items"], [existing_code])
		self.assertEqual(len(result["boms"]), 1)
		self.assertEqual([doc.doctype for doc in fake_frappe.created_docs], ["Item", "BOM"])
		self.assertEqual(layout.end_pieces[0].end_piece_item_code, existing_code)
		self.assertEqual(layout.end_pieces[0].generated_end_piece_bom, result["boms"][0])
		self.assertEqual(layout.end_piece_bom_status, "Generated")
		self.assertEqual(layout.save_calls, [{"ignore_permissions": True}])

		bom = self._created_doc(fake_frappe, "BOM")
		self.assertEqual(bom.insert_calls, 1)
		self.assertEqual(bom.submit_calls, 1)
		self.assertEqual(bom.item, "FG01SHR")
		self.assertEqual(bom.quantity, 1)
		self.assertEqual(bom.company, "Test Company")
		self.assertEqual(bom.custom_operation, "Shearing")
		self.assertEqual(bom.sheet_cutting_layout, "SCL-001")
		self.assertFalse(hasattr(bom, "uom"))
		self.assertFalse(hasattr(bom, "is_active"))
		self.assertFalse(hasattr(bom, "disabled"))
		self.assertFalse(hasattr(bom, "status"))
		self.assertEqual(
			bom.items,
			[
				{
					"item_code": existing_code,
					"qty": 2.5,
					"uom": "Kg",
				}
			],
		)
		self.assertEqual(bom.scrap_items, [])

	def test_generated_end_piece_bom_uses_strip_weight_as_raw_material_qty(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		fake_frappe = self._install_fakes(existing_items={existing_code})
		layout = Layout(end_pieces=[EndPiece(strip_weight_kg=1.75, weight_kg=2.5)])

		result = self.service.generate_end_piece_boms(layout)
		bom = self._created_doc(fake_frappe, "BOM")

		assert result["boms"]
		assert bom.items[0]["qty"] == 1.75

	def test_generated_end_piece_bom_derives_missing_strip_weight_for_old_rows(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		fake_frappe = self._install_fakes(existing_items={existing_code})
		layout = Layout(end_pieces=[EndPiece(strip_weight_kg=None)])

		self.service.generate_end_piece_boms(layout)
		bom = self._created_doc(fake_frappe, "BOM")

		self.assertEqual(layout.end_pieces[0].strip_width_mm, 100)
		self.assertEqual(layout.end_pieces[0].strip_length_mm, 200)
		self.assertEqual(bom.items[0]["qty"], 0.3144)

	def test_generation_uses_linked_item_when_end_piece_bom_is_missing(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		fake_frappe = self._install_fakes(existing_items={existing_code})
		row = EndPiece(end_piece_item_code=existing_code, generated_end_piece_bom=None)
		layout = Layout(end_pieces=[row])

		with patch.object(self.service, "ensure_end_piece_item") as ensure_item:
			result = self.service.generate_end_piece_boms(layout)

		ensure_item.assert_not_called()
		self.assertEqual(result["items"], [])
		self.assertEqual(len(result["boms"]), 1)
		self.assertEqual([doc.doctype for doc in fake_frappe.created_docs], ["BOM"])
		self.assertEqual(row.end_piece_item_code, existing_code)
		self.assertEqual(row.generated_end_piece_bom, result["boms"][0])
		self.assertEqual(layout.end_piece_bom_status, "Generated")
		self.assertEqual(layout.save_calls, [{"ignore_permissions": True}])

	def test_generation_includes_all_reuse_rows_missing_item_or_used_for_part_bom(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		self._install_fakes(existing_items={existing_code})
		missing_item = EndPiece(idx=1, end_piece_item_code=None, generated_end_piece_bom="BOM-STALE")
		missing_used_for_part_bom = EndPiece(
			idx=2,
			end_piece_item_code=existing_code,
			generated_end_piece_bom=None,
		)
		layout = Layout(end_pieces=[missing_item, missing_used_for_part_bom])

		with patch.object(self.service, "ensure_end_piece_item", return_value=existing_code) as ensure_item:
			result = self.service.generate_end_piece_boms(layout)

		self.assertEqual(result["items"], [existing_code])
		self.assertEqual(len(result["boms"]), 2)
		ensure_item.assert_called_once()
		self.assertEqual(missing_item.end_piece_item_code, existing_code)
		self.assertEqual(missing_item.generated_end_piece_bom, result["boms"][0])
		self.assertEqual(missing_used_for_part_bom.end_piece_item_code, existing_code)
		self.assertEqual(missing_used_for_part_bom.generated_end_piece_bom, result["boms"][1])

	def test_generation_uses_layout_finished_part_in_generated_item_code(self) -> None:
		existing_code = "AB12SHR-EP-2x100x200"
		fake_frappe = self._install_fakes(existing_items={existing_code})
		layout = Layout(
			finished_part_code=" ab12shr ",
			end_pieces=[EndPiece(used_for_finished_part="FG01SHR")],
		)

		result = self.service.generate_end_piece_boms(layout)

		self.assertEqual(result["items"], [existing_code])
		self.assertEqual([doc.doctype for doc in fake_frappe.created_docs], ["Item", "BOM"])
		self.assertEqual(layout.end_pieces[0].end_piece_item_code, existing_code)

	def test_reuse_end_piece_item_code_uses_strip_dimensions(self) -> None:
		existing_code = "FG01SHR-EP-2x80x150"
		self._install_fakes(existing_items={existing_code})
		row = EndPiece(width_mm=100, length_mm=200, strip_width_mm=80, strip_length_mm=150)

		item_code = self.item_service.ensure_end_piece_item(Layout(), row)

		self.assertEqual(item_code, existing_code)

	def test_generation_creates_missing_item_with_kg_stock_uom_alternate_nos_and_rm_valuation(
		self,
	) -> None:
		fake_frappe = self._install_fakes(
			raw_item_groups={"RAW-001": "Sheet Steel"},
			item_hsn_codes={"FG01SHR": "7208"},
			raw_item_valuation_rates={"RAW-001": 82.75},
		)
		layout = Layout(end_pieces=[EndPiece(strip_weight_kg=1.75)])

		result = self.service.generate_end_piece_boms(layout)

		self.assertEqual([doc.doctype for doc in fake_frappe.created_docs], ["Item", "BOM"])
		self.assertEqual(result["items"], ["FG01SHR-EP-2x100x200"])

		item = fake_frappe.created_docs[0]
		self.assertEqual(item.item_code, "FG01SHR-EP-2x100x200")
		self.assertEqual(item.item_name, "FG01SHR-EP-2x100x200")
		self.assertEqual(item.item_group, "Sheet Steel")
		self.assertEqual(item.gst_hsn_code, "7208")
		self.assertEqual(item.valuation_rate, 82.75)
		self.assertEqual(item.stock_uom, "Kg")
		self.assertEqual(item.is_stock_item, 1)
		self.assertEqual(item.disabled, 0)
		self.assertEqual(
			item.uoms,
			[
				{"uom": "Kg", "conversion_factor": 1},
				{"uom": "Nos", "conversion_factor": 1.75},
			],
		)
		self.assertEqual(self._created_doc(fake_frappe, "BOM").submit_calls, 1)

	def test_generation_uses_effective_raw_material_valuation_for_created_item(self) -> None:
		fake_frappe = self._install_fakes(
			raw_item_groups={"RAW-001": "Sheet Steel"},
			raw_item_valuation_rates={"RAW-001": 0},
		)
		layout = Layout(end_pieces=[EndPiece(strip_weight_kg=1.75)])

		with patch(
			"erpnext.manufacturing.doctype.bom.bom.get_valuation_rate",
			return_value=82.75,
		):
			self.service.generate_end_piece_boms(layout)

		item = fake_frappe.created_docs[0]
		self.assertEqual(item.item_code, "FG01SHR-EP-2x100x200")
		self.assertEqual(item.valuation_rate, 82.75)

	def test_created_end_piece_item_has_single_stock_and_alternate_uom_rows(self) -> None:
		from sheet_cutting_layout.services.end_piece_item_service import ensure_end_piece_item

		suffix = frappe.generate_hash(length=8).upper()
		raw_item = ensure_item(f"SCLTESTRM{suffix}", stock_uom="Kg", valuation_rate=82.75)
		finished_item = ensure_item(f"SCLTESTFG{suffix}SHR", stock_uom="Nos")
		layout = Layout(finished_part_code=finished_item, raw_material_item=raw_item, sheet_thickness_mm=2)
		row = EndPiece(used_for_finished_part=finished_item, width_mm=100, length_mm=200, weight_kg=2.5)

		item_code = ensure_end_piece_item(layout, row)

		item = frappe.get_doc("Item", item_code)
		uom_rows = [(row.uom, row.conversion_factor) for row in item.uoms]
		self.assertEqual([uom for uom, _factor in uom_rows].count("Kg"), 1)
		self.assertEqual([uom for uom, _factor in uom_rows].count("Nos"), 1)
		self.assertIn(("Kg", 1.0), uom_rows)
		self.assertIn(("Nos", 2.5), uom_rows)

	def test_existing_generated_item_with_zero_valuation_is_repaired_from_raw_material(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		fake_frappe = self._install_fakes(
			existing_items={existing_code},
			raw_item_valuation_rates={
				"RAW-001": 82.75,
				existing_code: 0,
			},
		)

		item_code = self.item_service.ensure_end_piece_item(Layout(), EndPiece())

		self.assertEqual(item_code, existing_code)
		repaired_item = fake_frappe.created_docs[0]
		self.assertEqual(repaired_item.doctype, "Item")
		self.assertEqual(repaired_item.name, existing_code)
		self.assertEqual(repaired_item.valuation_rate, 82.75)
		self.assertEqual(repaired_item.save_calls, [{"ignore_permissions": True}])
		self.assertEqual(fake_frappe.db.set_value_calls, [])

	def test_existing_generated_item_repairs_zero_valuation_from_effective_raw_material_rate(
		self,
	) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		fake_frappe = self._install_fakes(
			existing_items={existing_code},
			raw_item_valuation_rates={
				"RAW-001": 0,
				existing_code: 0,
			},
		)

		with patch(
			"erpnext.manufacturing.doctype.bom.bom.get_valuation_rate",
			return_value=82.75,
		):
			item_code = self.item_service.ensure_end_piece_item(Layout(), EndPiece())

		self.assertEqual(item_code, existing_code)
		repaired_item = fake_frappe.created_docs[0]
		self.assertEqual(repaired_item.name, existing_code)
		self.assertEqual(repaired_item.valuation_rate, 82.75)
		self.assertEqual(repaired_item.save_calls, [{"ignore_permissions": True}])

	def test_existing_generated_item_missing_alt_uom_is_repaired(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		fake_frappe = self._install_fakes(existing_items={existing_code})

		item_code = self.item_service.ensure_end_piece_item(Layout(), EndPiece())

		self.assertEqual(item_code, existing_code)
		repaired_item = fake_frappe.created_docs[0]
		self.assertEqual(repaired_item.doctype, "Item")
		self.assertEqual(repaired_item.name, existing_code)
		self.assertEqual(repaired_item.uoms, [{"uom": "Nos", "conversion_factor": 2.5}])
		self.assertEqual(repaired_item.save_calls, [{"ignore_permissions": True}])

	def test_existing_generated_reuse_item_repairs_alt_uom_to_strip_weight(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		fake_frappe = self._install_fakes(existing_items={existing_code})
		existing_item = FakeDoc("Item")
		existing_item.name = existing_code
		existing_item.uoms = [{"uom": "Nos", "conversion_factor": 2.5}]

		with patch.object(fake_frappe, "get_doc", return_value=existing_item):
			item_code = self.item_service.ensure_end_piece_item(Layout(), EndPiece(strip_weight_kg=1.75))

		self.assertEqual(item_code, existing_code)
		self.assertEqual(existing_item.uoms, [{"uom": "Nos", "conversion_factor": 1.75}])
		self.assertEqual(existing_item.save_calls, [{"ignore_permissions": True}])

	def test_generation_keeps_fractional_end_piece_stock_qty_in_kg(self) -> None:
		existing_code = "FG01SHR-EP-2x1250x179"
		fake_frappe = self._install_fakes(existing_items={existing_code})
		layout = Layout(
			end_pieces=[EndPiece(width_mm=1250, length_mm=179, weight_kg=2.814, strip_weight_kg=2.814)]
		)

		self.service.generate_end_piece_boms(layout)

		bom = self._created_doc(fake_frappe, "BOM")
		self.assertEqual(len(bom.items), 1)
		self.assertEqual(bom.items[0]["item_code"], existing_code)
		self.assertEqual(bom.items[0]["qty"], 2.814)
		self.assertEqual(bom.items[0]["uom"], "Kg")
		self.assertNotIn("stock_uom", bom.items[0])
		self.assertNotIn("stock_qty", bom.items[0])
		self.assertNotIn("conversion_factor", bom.items[0])

	def test_generation_uses_default_company_when_layout_company_is_missing(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		fake_frappe = self._install_fakes(
			existing_items={existing_code},
			raw_item_valuation_rates={existing_code: 60.03},
		)
		layout = Layout(company=None, end_pieces=[EndPiece()])

		with patch("erpnext.get_default_company", return_value="ERPNext Default Company") as spy:
			self.service.generate_end_piece_boms(layout)

		self.assertEqual(self._created_doc(fake_frappe, "BOM").company, "ERPNext Default Company")
		spy.assert_called_once()

	def test_generation_persists_submitted_links_with_db_set(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		self._install_fakes(existing_items={existing_code})
		row = EndPiece()
		layout = SubmittedLayout(end_pieces=[row])

		result = self.service.generate_end_piece_boms(layout)

		self.assertEqual(result["items"], [existing_code])
		self.assertEqual(row.end_piece_item_code, existing_code)
		self.assertEqual(row.generated_end_piece_bom, result["boms"][0])
		self.assertEqual(
			row.db_set_calls,
			[
				("end_piece_item_code", existing_code, {"update_modified": False}),
				("strip_weight_kg", 2.5, {"update_modified": False}),
				("generated_end_piece_bom", result["boms"][0], {"update_modified": False}),
			],
		)
		self.assertEqual(
			layout.db_set_calls,
			[("end_piece_bom_status", "Generated", {"update_modified": True})],
		)

	def test_generation_persists_derived_strip_fields_for_submitted_old_rows(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		self._install_fakes(existing_items={existing_code})
		row = EndPiece(strip_weight_kg=None)
		layout = SubmittedLayout(end_pieces=[row])

		self.service.generate_end_piece_boms(layout)

		self.assertEqual(row.strip_width_mm, 100)
		self.assertEqual(row.strip_length_mm, 200)
		self.assertEqual(row.strip_weight_kg, 0.3144)
		self.assertIn(("strip_width_mm", 100, {"update_modified": False}), row.db_set_calls)
		self.assertIn(("strip_length_mm", 200, {"update_modified": False}), row.db_set_calls)
		self.assertIn(("strip_weight_kg", 0.3144, {"update_modified": False}), row.db_set_calls)

	def test_generation_handles_scrap_rows_with_input_fields_only(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		fake_frappe = self._install_fakes(existing_items={existing_code})
		layout = Layout(
			end_pieces=[
				EndPiece(
					weight_kg=12.0,
					strip_weight_kg=12.0,
					bom_quantity=3,
					net_weight_per_part_kg=3.25,
					gross_weight_per_part_kg=4.0,
					scrap_weight_per_part_kg=0.75,
					bom_scrap_quantity_kg=2.25,
					scrap_item="EP-SCRAP",
				)
			]
		)

		self.service.generate_end_piece_boms(layout)

		bom = self._created_doc(fake_frappe, "BOM")
		self.assertEqual(
			bom.scrap_items,
			[
				{
					"item_code": "EP-SCRAP",
					"qty": 2.25,
					"stock_qty": 2.25,
					"uom": "Kg",
				}
			],
		)

	def test_generation_wraps_end_piece_item_insert_error_with_row_context(self) -> None:
		self._install_fakes()
		layout = Layout(end_pieces=[EndPiece()])

		with patch.object(FakeDoc, "insert", side_effect=ValueError("duplicate item")):
			with self.assertRaisesRegex(
				ValueError,
				"Row 1: Failed to create end piece item 'FG01SHR-EP-2x100x200': duplicate item",
			):
				self.service.generate_end_piece_boms(layout)

	def test_generation_propagates_unexpected_end_piece_item_insert_error(self) -> None:
		self._install_fakes()
		layout = Layout(end_pieces=[EndPiece()])

		with patch.object(FakeDoc, "insert", side_effect=RuntimeError("unexpected insert failure")):
			with self.assertRaisesRegex(RuntimeError, "unexpected insert failure"):
				self.service.generate_end_piece_boms(layout)

	def test_generation_requires_row_scrap_item_for_positive_bom_scrap_qty(self) -> None:
		self._install_fakes(existing_items={"FG01SHR-EP-2x100x200"})
		layout = Layout(
			process_scrap_item="PROCESS-SCRAP",
			end_pieces=[EndPiece(bom_scrap_quantity_kg=0.75, scrap_item=None)],
		)

		with self.assertRaisesRegex(
			ValueError,
			"Row 1: Scrap item is required when BOM scrap quantity is positive",
		):
			self.service.generate_end_piece_boms(layout)

	def test_generation_uses_row_scrap_item_for_reuse_bom_scrap(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		fake_frappe = self._install_fakes(existing_items={existing_code})
		layout = Layout(
			process_scrap_item=None,
			end_pieces=[
				EndPiece(
					weight_kg=12.0,
					strip_weight_kg=12.0,
					bom_quantity=3,
					net_weight_per_part_kg=3.25,
					gross_weight_per_part_kg=4.0,
					scrap_weight_per_part_kg=0.75,
					bom_scrap_quantity_kg=2.25,
					scrap_item="EP-SCRAP",
				)
			],
		)

		result = self.service.generate_end_piece_boms(layout)

		self.assertEqual(result["items"], [existing_code])
		bom = self._created_doc(fake_frappe, "BOM")
		self.assertEqual(bom.quantity, 3)
		self.assertEqual(
			bom.items,
			[
				{
					"item_code": existing_code,
					"qty": 12.0,
					"uom": "Kg",
				}
			],
		)
		self.assertEqual(
			bom.scrap_items,
			[
				{
					"item_code": "EP-SCRAP",
					"qty": 2.25,
					"stock_qty": 2.25,
					"uom": "Kg",
				}
			],
		)

	def test_generation_uses_secondary_items_when_bom_has_no_scrap_table(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		fake_frappe = self._install_fakes(existing_items={existing_code})
		layout = Layout(
			end_pieces=[
				EndPiece(
					weight_kg=12.0,
					strip_weight_kg=12.0,
					bom_quantity=3,
					bom_scrap_quantity_kg=2.25,
					scrap_item="EP-SCRAP",
				)
			],
		)
		new_doc = fake_frappe.new_doc

		def new_doc_without_scrap_items(doctype: str) -> FakeDoc:
			doc = new_doc(doctype)
			if doctype == "BOM":
				delattr(doc, "scrap_items")
				doc.secondary_items = []
			return doc

		with patch.object(fake_frappe, "new_doc", side_effect=new_doc_without_scrap_items):
			self.service.generate_end_piece_boms(layout)

		bom = self._created_doc(fake_frappe, "BOM")
		self.assertEqual(
			bom.secondary_items,
			[
				{
					"type": "Scrap",
					"item_code": "EP-SCRAP",
					"qty": 2.25,
					"stock_qty": 2.25,
					"uom": "Kg",
					"stock_uom": "Kg",
				}
			],
		)

	def test_generation_validates_pending_rows_with_row_numbered_messages(self) -> None:
		self._install_fakes()
		cases = [
			(
				Layout(end_pieces=[EndPiece(idx=1, used_for_finished_part="")]),
				"Row 1: Used for finished part is required",
			),
			(
				Layout(end_pieces=[EndPiece(idx=2, bom_quantity=0)]),
				"Row 2: BOM quantity must be greater than zero",
			),
			(
				Layout(end_pieces=[EndPiece(idx=3, bom_scrap_quantity_kg=None)]),
				"Row 3: BOM scrap quantity must be non-negative",
			),
			(
				Layout(end_pieces=[EndPiece(idx=4, bom_scrap_quantity_kg=-0.1)]),
				"Row 4: BOM scrap quantity must be non-negative",
			),
			(
				Layout(sheet_thickness_mm=None, end_pieces=[EndPiece(idx=5, strip_weight_kg=0)]),
				"Row 5: Strip weight must be greater than zero",
			),
			(
				Layout(end_pieces=[EndPiece(idx=6, width_mm=0)]),
				"Row 6: End piece width must be greater than zero",
			),
		]
		for layout, expected_message in cases:
			with self.subTest(expected_message=expected_message):
				with self.assertRaisesRegex(ValueError, expected_message):
					self.service.generate_end_piece_boms(layout)

	def test_generation_skips_non_reuse_and_already_generated_rows(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		self._install_fakes(existing_items={existing_code})
		layout = Layout(
			end_pieces=[
				EndPiece(
					idx=1,
					disposition="Scrap",
					used_for_finished_part=None,
					bom_quantity=0,
					bom_scrap_quantity_kg=0,
				),
				EndPiece(
					idx=2,
					disposition="Reuse",
					end_piece_item_code=existing_code,
					generated_end_piece_bom="BOM-EXISTING",
				),
				EndPiece(idx=3, disposition="Reuse", end_piece_item_code=None),
			]
		)

		result = self.service.generate_end_piece_boms(layout)

		self.assertEqual(result["items"], [existing_code])
		self.assertEqual(len(result["boms"]), 1)
		self.assertEqual(layout.end_pieces[1].end_piece_item_code, existing_code)
		self.assertEqual(layout.end_pieces[1].generated_end_piece_bom, "BOM-EXISTING")
		self.assertEqual(layout.end_pieces[2].end_piece_item_code, existing_code)
		self.assertEqual(layout.end_pieces[2].generated_end_piece_bom, result["boms"][0])

	def test_generation_is_noop_when_all_reuse_rows_already_have_boms(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		self._install_fakes(existing_items={existing_code})
		layout = Layout(
			end_pieces=[EndPiece(end_piece_item_code=existing_code, generated_end_piece_bom="BOM-EXISTING")]
		)

		result = self.service.generate_end_piece_boms(layout)

		self.assertEqual(result, {"items": [], "boms": []})
		self.assertEqual(layout.save_calls, [])
