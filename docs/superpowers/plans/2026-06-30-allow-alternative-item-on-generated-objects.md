# Allow Alternative Item on Generated Objects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Newly generated Sheet Cutting Layout Items, BOMs, BOM raw-material rows, and raw-material Item masters touched by new generation have `allow_alternative_item = 1` when the target schema supports that field.

**Architecture:** Add one schema-driven helper module for the alternative-item flag and use it from the existing generated Item, main release BOM, and end-piece BOM paths. Do not branch on Frappe or ERPNext version numbers; verify v15/v16 schema first, then use metadata checks at runtime so unknown schema variants skip the field instead of breaking generation.

**Tech Stack:** Frappe/ERPNext v15 and v16, Python services, Frappe DocType metadata, Frappe native tests, pre-commit.

---

## File Structure

- Create: `sheet_cutting_layout/services/alternative_item.py`
  - Owns the `allow_alternative_item` field name, metadata checks, generated-doc setter, BOM child-row dict decorator, and Item master setter.
- Create: `sheet_cutting_layout/tests/test_alternative_item_service.py`
  - Tests metadata-driven guard behavior without depending on a live ERPNext schema.
- Modify: `sheet_cutting_layout/services/end_piece_item_service.py`
  - Sets the flag on newly created end-piece `Item` documents before insert.
- Modify: `sheet_cutting_layout/services/end_piece_bom_service.py`
  - Sets the flag on generated end-piece `BOM` headers, raw-material child rows, and referenced Item masters.
- Modify: `sheet_cutting_layout/services/release_service.py`
  - Sets the flag on generated main release `BOM` headers, raw-material child rows, and referenced raw-material Item masters.
- Modify: `sheet_cutting_layout/tests/test_end_piece_bom_service.py`
  - Extends fake metadata and asserts generated end-piece Items/BOMs/rows/touched Items are flagged.
- Modify: `sheet_cutting_layout/tests/test_release_service.py`
  - Adds release BOM insertion assertions for header, row, and touched Item master behavior.

## Trade-offs

- Schema detection is preferred over `frappe.get_versions()` because the requirement depends on DocType fields, not semantic app versions. This costs small metadata lookups but avoids brittle version branching.
- `frappe.db.set_value` is used for existing RM Item masters touched by generation. This makes the required master-data mutation explicit and auditable, but it can update the Item modified timestamp.
- A tiny shared helper file adds one module, but prevents duplicated metadata logic and avoids importing release-service internals into end-piece services.

## Task 1: Verify v15/v16 Schema Before Tests

**Files:**
- No file changes.

- [ ] **Step 1: Confirm the branch is not `develop`**

Run:

```bash
cd /root/workspace/sheet_cutting_layout
git branch --show-current
```

Expected:

```text
codex/allow-alternative-item-spec
```

- [ ] **Step 2: Verify bench15 schema**

Run:

```bash
cd /root/workspace/bench15
bench --site development.localhost mariadb -e "select parent, fieldname from tabDocField where parent in ('Item','BOM','BOM Item') and fieldname='allow_alternative_item' order by parent;"
```

Expected:

```text
parent	fieldname
BOM	allow_alternative_item
BOM Item	allow_alternative_item
Item	allow_alternative_item
```

- [ ] **Step 3: Verify bench16 schema**

Run:

```bash
cd /root/workspace/bench16
bench --site frappe16.localhost mariadb -e "select parent, fieldname from tabDocField where parent in ('Item','BOM','BOM Item') and fieldname='allow_alternative_item' order by parent;"
```

Expected:

```text
parent	fieldname
BOM	allow_alternative_item
BOM Item	allow_alternative_item
Item	allow_alternative_item
```

- [ ] **Step 4: Record the schema decision locally**

No code change is needed. Use field name `allow_alternative_item` for `Item`, `BOM`, and `BOM Item`, and keep runtime checks metadata-based rather than version-based.

## Task 2: Add RED Tests for the Shared Helper

**Files:**
- Create: `sheet_cutting_layout/tests/test_alternative_item_service.py`
- Implementation target for Task 3: `sheet_cutting_layout/services/alternative_item.py`

- [ ] **Step 1: Write the failing helper tests**

Create `sheet_cutting_layout/tests/test_alternative_item_service.py` with:

```python
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

		db = SimpleNamespace(set_value=lambda *args, **kwargs: None)
		fake_frappe = SimpleNamespace(db=db, get_meta=lambda _doctype: self._meta({"allow_alternative_item"}))

		with patch.object(alternative_item, "frappe", fake_frappe):
			assert alternative_item.ensure_item_allows_alternatives("  ") is False
```

- [ ] **Step 2: Run helper tests to verify RED**

Run:

```bash
cd /root/workspace/bench16
bench --site frappe16.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_alternative_item_service
```

Expected: FAIL with an import error for `sheet_cutting_layout.services.alternative_item`.

## Task 3: Implement the Shared Helper

**Files:**
- Create: `sheet_cutting_layout/services/alternative_item.py`
- Test: `sheet_cutting_layout/tests/test_alternative_item_service.py`

- [ ] **Step 1: Add the helper module**

Create `sheet_cutting_layout/services/alternative_item.py` with:

```python
from __future__ import annotations

import frappe

ALLOW_ALTERNATIVE_ITEM_FIELD = "allow_alternative_item"


def set_allow_alternative_item_if_supported(doc: object) -> bool:
	if not _field_is_supported(doc, ALLOW_ALTERNATIVE_ITEM_FIELD):
		return False
	setattr(doc, ALLOW_ALTERNATIVE_ITEM_FIELD, 1)
	return True


def with_bom_item_allow_alternative_item(
	bom_doc: object,
	table_fieldname: str,
	values: dict[str, object],
) -> dict[str, object]:
	row = dict(values)
	if _child_table_field_is_supported(
		bom_doc,
		table_fieldname,
		ALLOW_ALTERNATIVE_ITEM_FIELD,
	):
		row[ALLOW_ALTERNATIVE_ITEM_FIELD] = 1
	return row


def ensure_item_allows_alternatives(item_code: object) -> bool:
	clean_item_code = _clean(item_code)
	if clean_item_code is None:
		return False
	if not _doctype_field_is_supported("Item", ALLOW_ALTERNATIVE_ITEM_FIELD):
		return False
	frappe.db.set_value("Item", clean_item_code, ALLOW_ALTERNATIVE_ITEM_FIELD, 1)
	return True


def _field_is_supported(doc: object, fieldname: str) -> bool:
	meta = getattr(doc, "meta", None)
	has_field = getattr(meta, "has_field", None)
	if callable(has_field):
		return bool(has_field(fieldname))

	doctype = _clean(getattr(doc, "doctype", None))
	if doctype is not None:
		return _doctype_field_is_supported(doctype, fieldname)

	return hasattr(doc, fieldname)


def _child_table_field_is_supported(
	parent_doc: object,
	table_fieldname: str,
	child_fieldname: str,
) -> bool:
	parent_meta = getattr(parent_doc, "meta", None)
	get_field = getattr(parent_meta, "get_field", None)
	if not callable(get_field):
		return False

	table_field = get_field(table_fieldname)
	child_doctype = _clean(getattr(table_field, "options", None))
	if child_doctype is None:
		return False

	return _doctype_field_is_supported(child_doctype, child_fieldname)


def _doctype_field_is_supported(doctype: str, fieldname: str) -> bool:
	try:
		meta = frappe.get_meta(doctype)
	except Exception:
		return False
	has_field = getattr(meta, "has_field", None)
	return bool(callable(has_field) and has_field(fieldname))


def _clean(value: object) -> str | None:
	if value is None:
		return None
	if isinstance(value, str):
		value = value.strip()
		return value or None
	return str(value)
```

- [ ] **Step 2: Run helper tests to verify GREEN**

Run:

```bash
cd /root/workspace/bench16
bench --site frappe16.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_alternative_item_service
```

Expected: PASS.

- [ ] **Step 3: Commit helper tests and helper implementation**

Run:

```bash
cd /root/workspace/sheet_cutting_layout
git add sheet_cutting_layout/services/alternative_item.py sheet_cutting_layout/tests/test_alternative_item_service.py
git commit -m "test: cover alternative item schema helper"
```

Expected: commit succeeds on `codex/allow-alternative-item-spec`.

## Task 4: Add RED Tests for End-Piece Item and BOM Generation

**Files:**
- Modify: `sheet_cutting_layout/tests/test_end_piece_bom_service.py`
- Implementation target for Task 5: `sheet_cutting_layout/services/end_piece_item_service.py`
- Implementation target for Task 5: `sheet_cutting_layout/services/end_piece_bom_service.py`

- [ ] **Step 1: Extend fake metadata in the test file**

In `sheet_cutting_layout/tests/test_end_piece_bom_service.py`, add this helper near the fake classes:

```python
def _meta(fields: set[str], *, table_options: dict[str, str] | None = None) -> object:
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
```

In `FakeDoc.__init__`, add metadata without adding the actual flag value:

```python
		if doctype == "Item":
			self.meta = _meta({"allow_alternative_item"})
		if doctype == "BOM":
			self.meta = _meta(
				{"allow_alternative_item", "items", "scrap_items"},
				table_options={"items": "BOM Item", "scrap_items": "BOM Scrap Item"},
			)
```

In `FakeFrappe`, add a metadata method:

```python
	def get_meta(self, doctype: str) -> object:
		if doctype in {"Item", "BOM", "BOM Item"}:
			return _meta({"allow_alternative_item"})
		return _meta(set())
```

- [ ] **Step 2: Assert generated end-piece Item and BOM fields**

In `test_generation_creates_missing_item_with_kg_stock_uom_alternate_nos_and_rm_valuation`, add:

```python
		self.assertEqual(item.allow_alternative_item, 1)

		bom = self._created_doc(fake_frappe, "BOM")
		self.assertEqual(bom.allow_alternative_item, 1)
		self.assertEqual(bom.items[0]["allow_alternative_item"], 1)
		self.assertIn(
			("Item", "FG01SHR-EP-2x100x200", "allow_alternative_item", 1, {}),
			fake_frappe.db.set_value_calls,
		)
```

- [ ] **Step 3: Update strict end-piece BOM row expectations**

In every expected `bom.items` dictionary in `sheet_cutting_layout/tests/test_end_piece_bom_service.py`, include:

```python
					"allow_alternative_item": 1,
```

The strict expectations currently include generated raw-material rows around the tests that assert `bom.items` equals a list of dictionaries. Leave `scrap_items` and `secondary_items` expectations unchanged because the requirement is only for raw-material `items` rows.

- [ ] **Step 4: Add a guard test for missing BOM Item field**

Add this test to `TestEndPieceBomService`:

```python
	def test_generation_skips_bom_item_flag_when_child_schema_does_not_support_field(self) -> None:
		existing_code = "FG01SHR-EP-2x100x200"
		fake_frappe = self._install_fakes(existing_items={existing_code})
		layout = Layout(end_pieces=[EndPiece()])
		new_doc = fake_frappe.new_doc

		def new_doc_without_bom_item_flag(doctype: str) -> FakeDoc:
			doc = new_doc(doctype)
			if doctype == "BOM":
				doc.meta = _meta(
					{"allow_alternative_item", "items", "scrap_items"},
					table_options={"items": "BOM Item", "scrap_items": "BOM Scrap Item"},
				)
			return doc

		def get_meta_without_bom_item_flag(doctype: str) -> object:
			if doctype == "BOM Item":
				return _meta(set())
			if doctype in {"Item", "BOM"}:
				return _meta({"allow_alternative_item"})
			return _meta(set())

		with (
			patch.object(fake_frappe, "new_doc", side_effect=new_doc_without_bom_item_flag),
			patch.object(fake_frappe, "get_meta", side_effect=get_meta_without_bom_item_flag),
		):
			self.service.generate_end_piece_boms(layout)

		bom = self._created_doc(fake_frappe, "BOM")
		self.assertEqual(bom.allow_alternative_item, 1)
		self.assertNotIn("allow_alternative_item", bom.items[0])
```

- [ ] **Step 5: Run end-piece tests to verify RED**

Run:

```bash
cd /root/workspace/bench16
bench --site frappe16.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
```

Expected: FAIL with missing `allow_alternative_item` on the created Item, BOM header, and/or BOM item row.

## Task 5: Implement End-Piece Item and BOM Flagging

**Files:**
- Modify: `sheet_cutting_layout/services/end_piece_item_service.py`
- Modify: `sheet_cutting_layout/services/end_piece_bom_service.py`
- Test: `sheet_cutting_layout/tests/test_end_piece_bom_service.py`

- [ ] **Step 1: Set the flag on newly created end-piece Items**

In `sheet_cutting_layout/services/end_piece_item_service.py`, add the import:

```python
from sheet_cutting_layout.services.alternative_item import set_allow_alternative_item_if_supported
```

Then in `ensure_end_piece_item`, immediately after:

```python
		item.disabled = 0
```

add:

```python
		set_allow_alternative_item_if_supported(item)
```

- [ ] **Step 2: Set the flag in generated end-piece BOMs**

In `sheet_cutting_layout/services/end_piece_bom_service.py`, add the import:

```python
from sheet_cutting_layout.services.alternative_item import (
	ensure_item_allows_alternatives,
	set_allow_alternative_item_if_supported,
	with_bom_item_allow_alternative_item,
)
```

In `_create_end_piece_bom`, immediately after:

```python
	bom.sheet_cutting_layout = getattr(layout, "name", None)
```

add:

```python
	set_allow_alternative_item_if_supported(bom)
```

Replace the raw-material item append block with:

```python
	for item_row in weight_rows.items:
		ensure_item_allows_alternatives(item_row.item_code)
		bom.append(
			"items",
			with_bom_item_allow_alternative_item(
				bom,
				"items",
				{
					"item_code": item_row.item_code,
					"qty": item_row.qty,
					"uom": item_row.uom,
				},
			),
		)
```

- [ ] **Step 3: Run end-piece tests to verify GREEN**

Run:

```bash
cd /root/workspace/bench16
bench --site frappe16.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
```

Expected: PASS.

- [ ] **Step 4: Commit end-piece tests and implementation**

Run:

```bash
cd /root/workspace/sheet_cutting_layout
git add sheet_cutting_layout/services/end_piece_item_service.py sheet_cutting_layout/services/end_piece_bom_service.py sheet_cutting_layout/tests/test_end_piece_bom_service.py
git commit -m "feat: allow alternatives on generated end-piece artifacts"
```

Expected: commit succeeds on `codex/allow-alternative-item-spec`.

## Task 6: Add RED Tests for Main Release BOM Generation

**Files:**
- Modify: `sheet_cutting_layout/tests/test_release_service.py`
- Implementation target for Task 7: `sheet_cutting_layout/services/release_service.py`

- [ ] **Step 1: Add a release BOM insertion test**

In `TestFrappeBomInsertAndEndPieces`, add:

```python
	def test_frappe_bom_insert_allows_alternatives_on_header_raw_row_and_item_master(self) -> None:
		from sheet_cutting_layout.services import release_service
		from sheet_cutting_layout.services.bom_service import BomDocument, BomItemRow

		created_boms: list[object] = []
		set_value_calls: list[tuple[str, str, str, object, dict[str, object]]] = []

		def meta(fields: set[str], *, table_options: dict[str, str] | None = None) -> object:
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

		class FrappeBom:
			def __init__(self) -> None:
				self.doctype = "BOM"
				self.name = ""
				self.items: list[dict[str, object]] = []
				self.meta = meta(
					{"allow_alternative_item", "items"},
					table_options={"items": "BOM Item"},
				)

			def append(self, fieldname: str, row: dict[str, object]) -> None:
				getattr(self, fieldname).append(row)

			def insert(self) -> None:
				self.name = self.name or "BOM-PERSISTED"
				created_boms.append(self)

			def submit(self) -> None:
				self.docstatus = 1

		class FakeDB:
			@staticmethod
			def set_value(
				doctype: str,
				name: str,
				fieldname: str,
				value: object,
				**kwargs: object,
			) -> None:
				set_value_calls.append((doctype, name, fieldname, value, kwargs))

		class FrappeStub:
			db = FakeDB()

			@staticmethod
			def new_doc(doctype: str) -> FrappeBom:
				assert doctype == "BOM"
				return FrappeBom()

			@staticmethod
			def get_meta(doctype: str) -> object:
				if doctype in {"Item", "BOM Item"}:
					return meta({"allow_alternative_item"})
				return meta(set())

			@staticmethod
			def throw(message: str) -> None:
				raise ValueError(message)

		bom = BomDocument(item="PART001SHR", name="BOM-PART001SHR")
		bom._layout = type("LayoutWithCompany", (), {"company": "Test Company", "name": "SCL-001"})()
		bom.items.append(BomItemRow(item_code="RMSHEET001", qty=39.3, row_type="raw_material"))
		self.start_patcher(patch.object(release_service, "frappe", FrappeStub))

		release_service._insert_frappe_bom(bom)

		self.assertEqual(created_boms[0].allow_alternative_item, 1)
		self.assertEqual(
			created_boms[0].items,
			[
				{
					"item_code": "RMSHEET001",
					"qty": 39.3,
					"uom": "Kg",
					"allow_alternative_item": 1,
				}
			],
		)
		self.assertEqual(
			set_value_calls,
			[("Item", "RMSHEET001", "allow_alternative_item", 1, {})],
		)
```

- [ ] **Step 2: Add a release guard test for missing BOM Item field**

In `TestFrappeBomInsertAndEndPieces`, add:

```python
	def test_frappe_bom_insert_skips_raw_row_flag_when_bom_item_schema_lacks_field(self) -> None:
		from sheet_cutting_layout.services import release_service
		from sheet_cutting_layout.services.bom_service import BomDocument, BomItemRow

		created_boms: list[object] = []

		def meta(fields: set[str], *, table_options: dict[str, str] | None = None) -> object:
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

		class FrappeBom:
			def __init__(self) -> None:
				self.doctype = "BOM"
				self.name = ""
				self.items: list[dict[str, object]] = []
				self.meta = meta(
					{"allow_alternative_item", "items"},
					table_options={"items": "BOM Item"},
				)

			def append(self, fieldname: str, row: dict[str, object]) -> None:
				getattr(self, fieldname).append(row)

			def insert(self) -> None:
				self.name = self.name or "BOM-PERSISTED"
				created_boms.append(self)

			def submit(self) -> None:
				self.docstatus = 1

		class FakeDB:
			@staticmethod
			def set_value(
				doctype: str,
				name: str,
				fieldname: str,
				value: object,
				**kwargs: object,
			) -> None:
				assert (doctype, name, fieldname, value, kwargs) == (
					"Item",
					"RMSHEET001",
					"allow_alternative_item",
					1,
					{},
				)

		class FrappeStub:
			db = FakeDB()

			@staticmethod
			def new_doc(doctype: str) -> FrappeBom:
				assert doctype == "BOM"
				return FrappeBom()

			@staticmethod
			def get_meta(doctype: str) -> object:
				if doctype == "Item":
					return meta({"allow_alternative_item"})
				if doctype == "BOM Item":
					return meta(set())
				return meta(set())

			@staticmethod
			def throw(message: str) -> None:
				raise ValueError(message)

		bom = BomDocument(item="PART001SHR", name="BOM-PART001SHR")
		bom._layout = type("LayoutWithCompany", (), {"company": "Test Company", "name": "SCL-001"})()
		bom.items.append(BomItemRow(item_code="RMSHEET001", qty=39.3, row_type="raw_material"))
		self.start_patcher(patch.object(release_service, "frappe", FrappeStub))

		release_service._insert_frappe_bom(bom)

		self.assertEqual(created_boms[0].allow_alternative_item, 1)
		self.assertNotIn("allow_alternative_item", created_boms[0].items[0])
```

- [ ] **Step 3: Run release tests to verify RED**

Run:

```bash
cd /root/workspace/bench16
bench --site frappe16.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
```

Expected: FAIL with missing `allow_alternative_item` on the created release BOM and/or raw-material row.

## Task 7: Implement Main Release BOM Flagging

**Files:**
- Modify: `sheet_cutting_layout/services/release_service.py`
- Test: `sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Import the helper in release service**

In `sheet_cutting_layout/services/release_service.py`, add:

```python
from sheet_cutting_layout.services.alternative_item import (
	ensure_item_allows_alternatives,
	set_allow_alternative_item_if_supported,
	with_bom_item_allow_alternative_item,
)
```

- [ ] **Step 2: Set the flag in `_insert_frappe_bom`**

In `_insert_frappe_bom`, immediately after setting `sheet_cutting_layout`, add:

```python
	set_allow_alternative_item_if_supported(bom_doc)
```

Replace the raw-material item append block with:

```python
	for row in bom.items:
		ensure_item_allows_alternatives(row.item_code)
		bom_doc.append(
			"items",
			with_bom_item_allow_alternative_item(
				bom_doc,
				"items",
				{
					"item_code": row.item_code,
					"qty": row.qty,
					"uom": row.uom,
				},
			),
		)
```

- [ ] **Step 3: Run release tests to verify GREEN**

Run:

```bash
cd /root/workspace/bench16
bench --site frappe16.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
```

Expected: PASS.

- [ ] **Step 4: Commit release tests and implementation**

Run:

```bash
cd /root/workspace/sheet_cutting_layout
git add sheet_cutting_layout/services/release_service.py sheet_cutting_layout/tests/test_release_service.py
git commit -m "feat: allow alternatives on generated release BOMs"
```

Expected: commit succeeds on `codex/allow-alternative-item-spec`.

## Task 8: Run Dual-Bench Verification and Pre-commit

**Files:**
- No source edits expected.

- [ ] **Step 1: Run focused bench15 tests**

Run:

```bash
cd /root/workspace/bench15
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_alternative_item_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
```

Expected: all three commands PASS.

- [ ] **Step 2: Run focused bench16 tests**

Run:

```bash
cd /root/workspace/bench16
bench --site frappe16.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_alternative_item_service
bench --site frappe16.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
bench --site frappe16.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
```

Expected: all three commands PASS.

- [ ] **Step 3: Run all pre-commit hooks**

Run:

```bash
cd /root/workspace/sheet_cutting_layout
pre-commit run --all-files
```

Expected: PASS. If hooks modify files, review the diff, stage the hook changes, and amend the relevant commit.

- [ ] **Step 4: Review final diff**

Run:

```bash
cd /root/workspace/sheet_cutting_layout
git status -sb
git diff --stat origin/develop...HEAD
git diff --check
```

Expected: `git status -sb` reports branch `codex/allow-alternative-item-spec`, and `git diff --check`
produces no output.

- [ ] **Step 5: Push the implementation branch**

Run:

```bash
cd /root/workspace/sheet_cutting_layout
git push
```

Expected: branch `codex/allow-alternative-item-spec` pushes successfully and updates PR #46.
