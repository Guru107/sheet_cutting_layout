from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import patch

from sheet_cutting_layout.overrides.bom import validate_shearing_bom_source
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


@dataclass
class EndPiece:
	idx: int = 1
	disposition: str = "Reuse"
	end_piece_item_code: str | None = None
	width_mm: float | None = 100
	length_mm: float | None = 200
	weight_kg: float | None = 2.5
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
	status: str = "Released"
	company: str | None = "Test Company"
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

	def append(self, fieldname: str, row: dict[str, object]) -> None:
		getattr(self, fieldname).append(row)

	def insert(self, ignore_permissions: bool = False) -> FakeDoc:
		self.insert_calls += 1
		self.ignore_permissions = ignore_permissions
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


class FakeDB:
	def __init__(
		self,
		*,
		existing_items: set[str] | None = None,
		raw_item_groups: dict[str, str] | None = None,
	) -> None:
		self.existing_items = set(existing_items or set())
		self.raw_item_groups = raw_item_groups or {"RAW-001": "Raw Material"}

	def exists(self, doctype: str, name: str) -> bool:
		return doctype == "Item" and name in self.existing_items

	def get_value(self, doctype: str, name: str, fieldname: str) -> object:
		if doctype == "Item" and fieldname == "item_group":
			return self.raw_item_groups.get(name)
		return None

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
	) -> None:
		self.db = FakeDB(existing_items=existing_items, raw_item_groups=raw_item_groups)
		self.created_docs: list[FakeDoc] = []
		self.defaults = SimpleNamespace(get_user_default=lambda _key: "")
		self.ValidationError = ValueError
		self._ = lambda message: message

	def new_doc(self, doctype: str) -> FakeDoc:
		doc = FakeDoc(doctype)
		self.created_docs.append(doc)
		return doc

	def throw(self, message: str) -> None:
		raise ValueError(message)


class TestEndPieceBomService(SheetCuttingLayoutTestCase):
	def setUp(self) -> None:
		super().setUp()
		self.service = importlib.import_module("sheet_cutting_layout.services.end_piece_bom_service")

	def _install_fakes(
		self,
		*,
		existing_items: set[str] | None = None,
		raw_item_groups: dict[str, str] | None = None,
	) -> FakeFrappe:
		fake_frappe = FakeFrappe(
			existing_items=existing_items,
			raw_item_groups=raw_item_groups,
		)
		self.frappe_patch = patch.object(self.service, "frappe", fake_frappe)
		self.translation_patch = patch.object(self.service, "_", lambda message: message)
		self.frappe_patch.start()
		self.translation_patch.start()
		self.addCleanup(self.frappe_patch.stop)
		self.addCleanup(self.translation_patch.stop)
		return fake_frappe

	def test_generation_requires_released_layout(self) -> None:
		self._install_fakes()
		layout = Layout(status="Draft", end_pieces=[EndPiece()])

		with self.assertRaisesRegex(ValueError, "only after release"):
			self.service.generate_end_piece_boms(layout)

	def test_generation_reuses_existing_item_and_creates_bom(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		fake_frappe = self._install_fakes(existing_items={existing_code})
		layout = Layout(end_pieces=[EndPiece()])

		with patch.object(self.service, "resolve_scrap_item_rate", return_value=33.5) as resolve_rate:
			result = self.service.generate_end_piece_boms(layout)

		self.assertEqual(result["items"], [existing_code])
		self.assertEqual(len(result["boms"]), 1)
		self.assertEqual([doc.doctype for doc in fake_frappe.created_docs], ["BOM"])
		self.assertEqual(layout.end_pieces[0].end_piece_item_code, existing_code)
		self.assertEqual(layout.end_piece_bom_status, "Generated")
		self.assertEqual(layout.save_calls, [{"ignore_permissions": True}])

		bom = fake_frappe.created_docs[0]
		self.assertEqual(bom.insert_calls, 1)
		self.assertEqual(bom.submit_calls, 1)
		self.assertEqual(bom.item, "FG01SHR")
		self.assertEqual(bom.quantity, 1)
		self.assertEqual(bom.company, "Test Company")
		self.assertEqual(bom.custom_operation, "Shearing")
		self.assertEqual(bom.sheet_cutting_layout, "SCL-001")
		self.assertTrue(getattr(getattr(bom, "flags", None), "sheet_cutting_layout_allow_bom_update", False))
		self.assertEqual(bom.items, [{"item_code": existing_code, "qty": 2.5, "uom": "Kg"}])
		self.assertEqual(bom.scrap_items, [])
		resolve_rate.assert_not_called()

	def test_generation_creates_missing_item_with_nos_and_kg_uoms(self) -> None:
		fake_frappe = self._install_fakes(raw_item_groups={"RAW-001": "Sheet Steel"})
		layout = Layout(end_pieces=[EndPiece()])

		with patch.object(self.service, "resolve_scrap_item_rate", return_value=33.5):
			result = self.service.generate_end_piece_boms(layout)

		self.assertEqual([doc.doctype for doc in fake_frappe.created_docs], ["Item", "BOM"])
		self.assertEqual(result["items"], ["FG01SHR-EP-2x100x200"])

		item = fake_frappe.created_docs[0]
		self.assertEqual(item.item_code, "FG01SHR-EP-2x100x200")
		self.assertEqual(item.item_name, "FG01SHR-EP-2x100x200")
		self.assertEqual(item.item_group, "Sheet Steel")
		self.assertEqual(item.stock_uom, "Nos")
		self.assertEqual(item.is_stock_item, 1)
		self.assertEqual(item.disabled, 0)
		self.assertEqual(
			item.uoms, [{"uom": "Nos", "conversion_factor": 1}, {"uom": "Kg", "conversion_factor": 0.4}]
		)
		self.assertEqual(fake_frappe.created_docs[1].submit_calls, 1)

	def test_generation_uses_default_company_when_layout_company_is_missing(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		fake_frappe = self._install_fakes(existing_items={existing_code})
		layout = Layout(company=None, end_pieces=[EndPiece()])

		with patch.object(self.service, "resolve_scrap_item_rate", return_value=33.5):
			self.service.generate_end_piece_boms(layout)

		self.assertEqual(fake_frappe.created_docs[0].company, "DB Default Company")

	def test_generation_persists_submitted_links_with_db_set(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		self._install_fakes(existing_items={existing_code})
		row = EndPiece()
		layout = SubmittedLayout(end_pieces=[row])

		with patch.object(self.service, "resolve_scrap_item_rate", return_value=33.5):
			result = self.service.generate_end_piece_boms(layout)

		self.assertEqual(result["items"], [existing_code])
		self.assertEqual(row.end_piece_item_code, existing_code)
		self.assertEqual(
			row.db_set_calls,
			[("end_piece_item_code", existing_code, {"update_modified": False, "notify": False})],
		)
		self.assertEqual(
			layout.db_set_calls,
			[("end_piece_bom_status", "Generated", {"update_modified": True, "notify": False})],
		)

	def test_generation_handles_scrap_rows_and_uses_rate_fallback(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		fake_frappe = self._install_fakes(existing_items={existing_code})
		layout = Layout(
			end_pieces=[
				EndPiece(
					weight_kg=12.0,
					bom_quantity=3,
					net_weight_per_part_kg=3.25,
					gross_weight_per_part_kg=4.0,
					scrap_weight_per_part_kg=0.75,
					bom_scrap_quantity_kg=2.25,
					scrap_item="EP-SCRAP",
				)
			]
		)

		with patch.object(self.service, "resolve_scrap_item_rate", return_value=88.25) as resolve_rate:
			self.service.generate_end_piece_boms(layout)

		resolve_rate.assert_called_once_with(item_code="EP-SCRAP", company="Test Company")
		bom = fake_frappe.created_docs[0]
		self.assertEqual(
			bom.scrap_items,
			[
				{
					"item_code": "EP-SCRAP",
					"qty": 2.25,
					"stock_qty": 2.25,
					"uom": "Kg",
					"rate": 88.25,
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

	def test_generation_wraps_scrap_rate_resolution_error_with_row_context(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		self._install_fakes(existing_items={existing_code})
		layout = Layout(
			end_pieces=[
				EndPiece(
					weight_kg=12.0,
					bom_quantity=3,
					net_weight_per_part_kg=3.25,
					gross_weight_per_part_kg=4.0,
					scrap_weight_per_part_kg=0.75,
					bom_scrap_quantity_kg=2.25,
					scrap_item="EP-SCRAP",
				)
			]
		)

		with patch.object(
			self.service,
			"resolve_scrap_item_rate",
			side_effect=ValueError("Valuation rate is required for scrap item EP-SCRAP"),
		):
			with self.assertRaisesRegex(
				ValueError,
				"Row 1: Valuation rate is required for scrap item EP-SCRAP",
			):
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
					bom_quantity=3,
					net_weight_per_part_kg=3.25,
					gross_weight_per_part_kg=4.0,
					scrap_weight_per_part_kg=0.75,
					bom_scrap_quantity_kg=2.25,
					scrap_item="EP-SCRAP",
				)
			],
		)

		with patch.object(self.service, "resolve_scrap_item_rate", return_value=33.5) as resolve_rate:
			result = self.service.generate_end_piece_boms(layout)

		self.assertEqual(result["items"], [existing_code])
		bom = fake_frappe.created_docs[0]
		self.assertEqual(bom.quantity, 3)
		self.assertEqual(bom.items, [{"item_code": existing_code, "qty": 12.0, "uom": "Kg"}])
		self.assertEqual(
			bom.scrap_items,
			[
				{
					"item_code": "EP-SCRAP",
					"qty": 2.25,
					"stock_qty": 2.25,
					"uom": "Kg",
					"rate": 33.5,
				}
			],
		)
		resolve_rate.assert_called_once_with(item_code="EP-SCRAP", company="Test Company")

	def test_generation_validates_pending_rows_with_row_numbered_messages(self) -> None:
		self._install_fakes()
		cases = [
			(EndPiece(idx=1, used_for_finished_part=""), "Row 1: Used for finished part is required"),
			(EndPiece(idx=2, bom_quantity=0), "Row 2: BOM quantity must be greater than zero"),
			(EndPiece(idx=3, bom_scrap_quantity_kg=None), "Row 3: BOM scrap quantity must be non-negative"),
			(EndPiece(idx=4, bom_scrap_quantity_kg=-0.1), "Row 4: BOM scrap quantity must be non-negative"),
			(EndPiece(idx=5, weight_kg=0), "Row 5: End piece weight must be greater than zero"),
			(EndPiece(idx=6, width_mm=0), "Row 6: End piece width must be greater than zero"),
		]
		for row, expected_message in cases:
			with self.subTest(expected_message=expected_message):
				with self.assertRaisesRegex(ValueError, expected_message):
					self.service.generate_end_piece_boms(Layout(end_pieces=[row]))

	def test_generation_skips_non_reuse_and_already_linked_rows(self) -> None:
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
				EndPiece(idx=2, disposition="Reuse", end_piece_item_code=existing_code),
				EndPiece(idx=3, disposition="Reuse", end_piece_item_code=None),
			]
		)

		with patch.object(self.service, "resolve_scrap_item_rate", return_value=33.5):
			result = self.service.generate_end_piece_boms(layout)

		self.assertEqual(result["items"], [existing_code])
		self.assertEqual(len(result["boms"]), 1)
		self.assertEqual(layout.end_pieces[1].end_piece_item_code, existing_code)
		self.assertEqual(layout.end_pieces[2].end_piece_item_code, existing_code)

	def test_generation_is_noop_when_all_reuse_rows_are_already_linked(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		self._install_fakes(existing_items={existing_code})
		layout = Layout(end_pieces=[EndPiece(end_piece_item_code=existing_code)])

		result = self.service.generate_end_piece_boms(layout)

		self.assertEqual(result, {"items": [], "boms": []})
		self.assertEqual(layout.save_calls, [])
