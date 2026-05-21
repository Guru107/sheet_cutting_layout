from __future__ import annotations

import importlib
import types
from dataclasses import dataclass, field

import pytest


PREVIEW_ROW_KEYS = {
	"idx",
	"end_piece_item_code",
	"suggested_item_code",
	"item_status",
	"used_for_finished_part",
	"bom_quantity",
	"raw_material_qty_kg",
	"bom_scrap_quantity_kg",
	"bom_status",
	"generated_end_piece_bom",
}


@dataclass
class EndPiece:
	idx: int = 1
	disposition: str = "Reuse"
	end_piece_item_code: str | None = "END-001"
	width_mm: float | None = 100
	length_mm: float | None = 200
	weight_kg: float | None = 2.5
	used_for_finished_part: str | None = "PART-SHR"
	bom_quantity: float | None = 1
	bom_scrap_quantity_kg: float | None = 0
	generated_end_piece_item: str | None = None
	generated_end_piece_bom: str | None = None
	db_set_calls: list[tuple[object, object, dict[str, object]]] = field(default_factory=list)

	def db_set(self, fieldname: object, value: object = None, **kwargs: object) -> None:
		self.db_set_calls.append((fieldname, value, kwargs))


@dataclass
class Layout:
	name: str = "SCL-001"
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
		raise AssertionError("submitted layouts must persist generated BOM fields with db_set")


class FakeDoc:
	def __init__(self, doctype: str) -> None:
		self.doctype = doctype
		self.name = ""
		self.items: list[dict[str, object]] = []
		self.scrap_items: list[dict[str, object]] = []

	def append(self, fieldname: str, row: dict[str, object]) -> None:
		getattr(self, fieldname).append(row)

	def insert(self, ignore_permissions: bool = False) -> FakeDoc:
		self.ignore_permissions = ignore_permissions
		if self.doctype == "BOM" and not getattr(self, "company", None):
			raise ValueError("BOM company is mandatory")
		if not self.name:
			self.name = f"{self.doctype}-{id(self)}"
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
		self.ValidationError = ValueError
		self._ = lambda message: message
		self.defaults = types.SimpleNamespace(get_user_default=lambda _key: "")

	def new_doc(self, doctype: str) -> FakeDoc:
		doc = FakeDoc(doctype)
		self.created_docs.append(doc)
		return doc

	def throw(self, message: str) -> None:
		raise self.ValidationError(message)


@pytest.fixture()
def service() -> types.ModuleType:
	try:
		module = importlib.import_module("sheet_cutting_layout.services.end_piece_bom_service")
	except ModuleNotFoundError as error:
		pytest.fail(f"End-piece BOM service module is not implemented: {error}")
	return module


def install_fakes(
	monkeypatch: pytest.MonkeyPatch,
	service: types.ModuleType,
	*,
	existing_items: set[str] | None = None,
	raw_item_groups: dict[str, str] | None = None,
) -> FakeFrappe:
	fake_frappe = FakeFrappe(existing_items=existing_items, raw_item_groups=raw_item_groups)
	monkeypatch.setattr(service, "frappe", fake_frappe)
	return fake_frappe


def test_preview_existing_item_and_linked_bom_returns_exact_row_shape(
	service: types.ModuleType,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	fake_frappe = install_fakes(monkeypatch, service, existing_items={"END-001"})
	layout = Layout(
		end_pieces=[
			EndPiece(
				idx=3,
				disposition=" reuse ",
				generated_end_piece_bom="BOM-END-001",
			)
		]
	)

	rows = service.preview_end_piece_boms(layout)

	assert rows == [
		{
			"idx": 3,
			"end_piece_item_code": "END-001",
			"suggested_item_code": "RAW-001-EP-2x100x200",
			"item_status": "Exists",
			"used_for_finished_part": "PART-SHR",
			"bom_quantity": 1,
			"raw_material_qty_kg": 2.5,
			"bom_scrap_quantity_kg": 0,
			"bom_status": "Already linked",
			"generated_end_piece_bom": "BOM-END-001",
		}
	]
	assert set(rows[0]) == PREVIEW_ROW_KEYS
	assert fake_frappe.created_docs == []


def test_preview_creates_no_records(service: types.ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
	fake_frappe = install_fakes(monkeypatch, service)
	layout = Layout(end_pieces=[EndPiece(end_piece_item_code="END-NEW")])

	service.preview_end_piece_boms(layout)

	assert fake_frappe.created_docs == []


def test_preview_missing_item_reports_will_be_created(
	service: types.ModuleType,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	install_fakes(monkeypatch, service)
	layout = Layout(end_pieces=[EndPiece(end_piece_item_code="END-NEW")])

	row = service.preview_end_piece_boms(layout)[0]

	assert row["item_status"] == "Will be created"
	assert row["bom_status"] == "Will be created"


def test_preview_filters_only_reusable_end_piece_rows(
	service: types.ModuleType,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	install_fakes(monkeypatch, service)
	layout = Layout(
		end_pieces=[
			EndPiece(idx=1, disposition="Scrap"),
			EndPiece(idx=2, disposition=" ReUse "),
			EndPiece(idx=3, disposition=""),
		]
	)

	rows = service.preview_end_piece_boms(layout)

	assert [row["idx"] for row in rows] == [2]


def test_generation_reuses_existing_item_and_creates_bom(
	service: types.ModuleType,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	fake_frappe = install_fakes(monkeypatch, service, existing_items={"END-001"})
	layout = Layout(end_pieces=[EndPiece()])

	result = service.generate_end_piece_boms(layout)

	assert result == {"items": ["END-001"], "boms": [layout.end_pieces[0].generated_end_piece_bom]}
	assert [doc.doctype for doc in fake_frappe.created_docs] == ["BOM"]
	bom = fake_frappe.created_docs[0]
	assert bom.item == "PART-SHR"
	assert bom.quantity == 1
	assert bom.uom == "Kg"
	assert bom.company == "Test Company"
	assert bom.custom_operation == "Shearing"
	assert bom.sheet_cutting_layout == "SCL-001"
	assert bom.items == [{"item_code": "END-001", "qty": 2.5, "uom": "Kg"}]
	assert bom.scrap_items == []
	assert layout.end_pieces[0].generated_end_piece_item == "END-001"
	assert layout.save_calls == [{"ignore_permissions": True}]


def test_generation_uses_default_company_when_layout_has_no_company(
	service: types.ModuleType,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	fake_frappe = install_fakes(monkeypatch, service, existing_items={"END-001"})
	layout = Layout(company=None, end_pieces=[EndPiece()])

	service.generate_end_piece_boms(layout)

	bom = fake_frappe.created_docs[0]
	assert bom.company == "DB Default Company"


def test_generation_persists_submitted_layout_links_with_db_set(
	service: types.ModuleType,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	install_fakes(monkeypatch, service, existing_items={"END-001"})
	row = EndPiece()
	layout = SubmittedLayout(end_pieces=[row])

	result = service.generate_end_piece_boms(layout)

	assert row.generated_end_piece_item == "END-001"
	assert row.generated_end_piece_bom == result["boms"][0]
	assert layout.end_piece_bom_status == "Generated"
	assert row.db_set_calls == [
		(
			{
				"generated_end_piece_item": "END-001",
				"generated_end_piece_bom": result["boms"][0],
			},
			None,
			{"update_modified": False, "notify": False},
		)
	]
	assert layout.db_set_calls == [
		(
			"end_piece_bom_status",
			"Generated",
			{"update_modified": True, "notify": False},
		)
	]


def test_generation_creates_missing_item_from_raw_material_item_group(
	service: types.ModuleType,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	fake_frappe = install_fakes(
		monkeypatch,
		service,
		raw_item_groups={"RAW-001": "Sheet Steel"},
	)
	layout = Layout(end_pieces=[EndPiece(end_piece_item_code="END-NEW")])

	result = service.generate_end_piece_boms(layout)

	item = fake_frappe.created_docs[0]
	assert result["items"] == ["END-NEW"]
	assert item.doctype == "Item"
	assert item.item_code == "END-NEW"
	assert item.item_name == "END-NEW"
	assert item.item_group == "Sheet Steel"
	assert item.stock_uom == "Kg"
	assert item.is_stock_item == 1
	assert item.disabled == 0
	assert item.ignore_permissions is True


def test_generation_zero_scrap_quantity_creates_no_scrap_row(
	service: types.ModuleType,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	fake_frappe = install_fakes(monkeypatch, service, existing_items={"END-001"})
	layout = Layout(end_pieces=[EndPiece(bom_scrap_quantity_kg=0)])

	service.generate_end_piece_boms(layout)

	bom = fake_frappe.created_docs[0]
	assert bom.scrap_items == []


def test_generation_positive_scrap_quantity_requires_process_scrap_item(
	service: types.ModuleType,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	install_fakes(monkeypatch, service, existing_items={"END-001"})
	layout = Layout(process_scrap_item=None, end_pieces=[EndPiece(bom_scrap_quantity_kg=0.5)])

	with pytest.raises(ValueError, match="Row 1: Process scrap item is required"):
		service.generate_end_piece_boms(layout)


@pytest.mark.parametrize(
	"field_update, message",
	[
		({"end_piece_item_code": " "}, "Row 1: End piece item code is required"),
		({"used_for_finished_part": ""}, "Row 1: Used for finished part is required"),
		({"bom_quantity": 0}, "Row 1: BOM quantity must be greater than zero"),
		({"bom_scrap_quantity_kg": None}, "Row 1: BOM scrap quantity must be non-negative"),
		({"bom_scrap_quantity_kg": -0.1}, "Row 1: BOM scrap quantity must be non-negative"),
		({"weight_kg": 0}, "Row 1: End piece weight must be greater than zero"),
	],
)
def test_generation_reports_row_numbered_validation_errors(
	service: types.ModuleType,
	monkeypatch: pytest.MonkeyPatch,
	field_update: dict[str, object],
	message: str,
) -> None:
	install_fakes(monkeypatch, service, existing_items={"END-001"})
	end_piece = EndPiece(**field_update)
	layout = Layout(end_pieces=[end_piece])

	with pytest.raises(ValueError, match=message):
		service.generate_end_piece_boms(layout)


def test_generation_skips_linked_rows_and_generates_pending_rows(
	service: types.ModuleType,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	fake_frappe = install_fakes(monkeypatch, service, existing_items={"END-001", "END-002"})
	linked = EndPiece(idx=1, end_piece_item_code="END-001", generated_end_piece_bom="BOM-EXISTING")
	pending = EndPiece(idx=2, end_piece_item_code="END-002")
	layout = Layout(end_pieces=[linked, pending])

	result = service.generate_end_piece_boms(layout)

	assert result["items"] == ["END-002"]
	assert len(result["boms"]) == 1
	assert linked.generated_end_piece_bom == "BOM-EXISTING"
	assert pending.generated_end_piece_bom == result["boms"][0]
	assert [doc.doctype for doc in fake_frappe.created_docs] == ["BOM"]


def test_generation_all_linked_rows_is_noop(
	service: types.ModuleType,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	fake_frappe = install_fakes(monkeypatch, service, existing_items={"END-001"})
	layout = Layout(end_pieces=[EndPiece(generated_end_piece_bom="BOM-EXISTING")])

	result = service.generate_end_piece_boms(layout)

	assert result == {"items": [], "boms": []}
	assert fake_frappe.created_docs == []
	assert layout.save_calls == []


def test_generation_requires_released_layout(
	service: types.ModuleType,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	install_fakes(monkeypatch, service, existing_items={"END-001"})
	layout = Layout(status="Draft", end_pieces=[EndPiece()])

	with pytest.raises(ValueError, match="End-piece BOMs can be generated only after release"):
		service.generate_end_piece_boms(layout)


def test_generation_adds_positive_scrap_row(
	service: types.ModuleType,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	fake_frappe = install_fakes(monkeypatch, service, existing_items={"END-001"})
	layout = Layout(end_pieces=[EndPiece(bom_scrap_quantity_kg=0.75)])

	service.generate_end_piece_boms(layout)

	bom = fake_frappe.created_docs[0]
	assert bom.scrap_items == [
		{"item_code": "PROCESS-SCRAP", "qty": 0.75, "stock_qty": 0.75, "uom": "Kg"}
	]
