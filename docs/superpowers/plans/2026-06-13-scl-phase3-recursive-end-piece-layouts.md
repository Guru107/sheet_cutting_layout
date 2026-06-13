# Phase 3 — Recursive End-Piece Layouts Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
**Goal:** Let a reused end piece carry its own full Sheet Cutting Layout (`child_layout`), so the end piece's generated item becomes the child layout's raw material and the child owns the real BOM, with a native depth-first cancel cascade that retires every descendant layout and BOM.
**Architecture:** Add an optional `child_layout` link on `Layout End Piece` with hybrid semantics (unset = today's simple end-piece item+BOM; set = the end piece's generated item feeds a child Sheet Cutting Layout that owns the BOM while the parent BOM still carries the end piece as a byproduct row). A new frappe-free `services/cascade_graph.py` collects descendant layouts depth-first leaves-first with cycle detection; native `validate`/`on_cancel`/`on_trash` enforce the guards and drive the cascade, relying on Frappe link validation to block cancel/delete when a descendant BOM is consumed by a Manufacture Stock Entry.
**Tech Stack:** Frappe v15 / ERPNext v15.101, Python, openpyxl, Cypress
---

## Dependencies

This phase **must land after** these phases (do not start until both are merged to the
`feature/scl-iatf-export-lhrh-recursion` branch):

- **Phase 0** — the native lifecycle spine. Phase 0 removes the `apply_workflow` override,
  `before_workflow_action`, the `frappe.flags.selected_workflow_action` plumbing,
  `_suppress_workflow_side_effects`, and the `_apply_workflow_action_effects` method from the
  `SheetCuttingLayout` controller
  (`sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`).
  After Phase 0 the controller exposes:
  - `on_submit(self)` — calls `release_layout(self)` when the workflow `status == "Released"` and the
    document reaches `docstatus == 1`.
  - `on_cancel(self)` — calls a single retirement+cascade entry point (below) instead of the legacy
    `before_cancel`/`cancel_generated_bom` path.
  - `on_trash(self)` — framework-gated delete (no custom "is it used?" query).
  - class attribute `ignore_linked_doctypes = ["BOM"]`.
  - `release_service` retires a layout's own BOMs via native `bom.cancel()` (falling back to native
    `is_active=0` deactivate on `LinkExistsError`), **not** via raw `db_set` of
    `is_active/disabled/is_default/status`. This Phase 3 plan calls the Phase 0 retirement helper by the
    name **`retire_layout_boms(layout)`** (defined in `services/release_service.py` by Phase 0). If
    Phase 0 named it differently, treat `retire_layout_boms` throughout this plan as an alias and
    rename in one place — **Task 6, Step 4**.
- **Phase 1** — multi-BOM release. Phase 1 adds the `generated_bom` (Link → BOM) column to
  `Layout Finished Part` and makes `_generate_boms` emit one BOM per finished part. This plan reuses
  that multi-BOM release loop unchanged; it only adds child-layout cascade on top.

This phase **lands in parallel with Phase 2** (export) and is merged independently. The final
integration PR (out of scope here) teaches the exporter to render the recursive child tree.

The frappe-less test mode and the in-app pytest emulation
(`sheet_cutting_layout/tests/unittest_adapter.py`, `MonkeyPatch`, `add_pytest_style_tests`, `raises`,
`fixture`) are removed in Phase 0. **All tests in this plan use plain `unittest`/`FrappeTestCase`
primitives via `SheetCuttingLayoutTestCase` (`sheet_cutting_layout/tests/base.py`).** Do not import
from `unittest_adapter`.

## File structure

| File | Create/Modify | One responsibility |
|---|---|---|
| `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json` | Modify | Add `child_layout` (Link → Sheet Cutting Layout, `depends_on disposition==Reuse`, `no_copy`). |
| `sheet_cutting_layout/services/cascade_graph.py` | Create | Frappe-free: collect descendant layouts depth-first leaves-first via `child_layout`, with cycle/self-reference detection. |
| `sheet_cutting_layout/services/recursive_end_piece.py` | Create | Frappe-free guards: child `raw_material_item == parent end-piece item`; release-order guard helpers. |
| `sheet_cutting_layout/services/validators.py` | Modify | Wire the new child-layout guards into `validate_sheet_cutting_layout`. |
| `sheet_cutting_layout/services/release_service.py` | Modify | Skip the simple end-piece item/BOM path for rows with a `child_layout`; cancel-cascade walks `child_layout`. |
| `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py` | Modify | `on_cancel` walks descendants depth-first, cancels each child layout, retires its BOMs. |
| `sheet_cutting_layout/tests/test_cascade_graph.py` | Create | Unit tests: traversal order, cycle detection, raw-material equality. |
| `sheet_cutting_layout/tests/test_recursive_end_piece.py` | Create | Unit tests: child-layout guard helpers. |
| `sheet_cutting_layout/tests/test_recursive_end_piece_release.py` | Create | Integration: 2-level release builds all BOMs; cascade cancel; native block on Manufacture; gated delete. |
| `cypress/integration/sheet_cutting_layout_recursive_end_piece.js` | Create | E2E: link a child layout, release, supersede parent, assert child + all BOMs retired. |

---

## Task group A — Data model and frappe-free domain logic

### Task 1: Add `child_layout` link to Layout End Piece

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json` (field_order lines 8-23; fields array lines 24-126)
- Test path: `sheet_cutting_layout/tests/test_recursive_end_piece.py` (new)

The new field is a child-table-only Link. The doctype is `istable: 1` so there are no permissions to
edit. `no_copy: 1` ensures a `create_revision` of the parent layout does not copy a stale child link.

- [ ] Write the failing test. Create `sheet_cutting_layout/tests/test_recursive_end_piece.py` with this exact content (it asserts the doctype meta exposes the new field):

```python
from __future__ import annotations

import frappe

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


class TestLayoutEndPieceChildLayoutField(SheetCuttingLayoutTestCase):
	def test_child_layout_field_exists_on_layout_end_piece(self) -> None:
		meta = frappe.get_meta("Layout End Piece")
		field = meta.get_field("child_layout")
		self.assertIsNotNone(field, "Layout End Piece must define a child_layout field")
		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "Sheet Cutting Layout")
		self.assertEqual(field.depends_on, 'eval:doc.disposition=="Reuse"')
		self.assertEqual(field.no_copy, 1)
```

- [ ] Run it and see it FAIL. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_recursive_end_piece`
  Expected failure: `AssertionError: Layout End Piece must define a child_layout field` (the field does
  not exist yet, so `meta.get_field("child_layout")` returns `None`).

- [ ] Implement: add the field to the field_order. In `layout_end_piece.json`, change the `field_order` array so `child_layout` follows `used_for_finished_part`:

```json
 "field_order": [
  "end_piece_item_code",
  "width_mm",
  "length_mm",
  "weight_kg",
  "qty_per_sheet",
  "disposition",
  "scrap_item",
  "used_for_finished_part",
  "child_layout",
  "bom_quantity",
  "net_weight_per_part_kg",
  "gross_weight_per_part_kg",
  "scrap_weight_per_part_kg",
  "bom_scrap_quantity_kg",
  "generated_end_piece_bom"
 ],
```

- [ ] Implement: add the field definition. In `layout_end_piece.json`, insert this object into the `fields` array immediately after the `used_for_finished_part` field object (after its closing `},` near line 83) and before the `bom_quantity` field object:

```json
  {
   "depends_on": "eval:doc.disposition==\"Reuse\"",
   "fieldname": "child_layout",
   "fieldtype": "Link",
   "label": "Child Layout",
   "no_copy": 1,
   "options": "Sheet Cutting Layout"
  },
```

- [ ] Run the migration so the meta reflects the new field. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost migrate`
  Expected: completes without error; `Layout End Piece` schema updated.

- [ ] Run the test and see it PASS. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_recursive_end_piece`
  Expected: 1 test, OK.

- [ ] Lint. From `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `python -m ruff check sheet_cutting_layout/tests/test_recursive_end_piece.py && python -m ruff format --check sheet_cutting_layout/tests/test_recursive_end_piece.py`
  Expected: no errors.

- [ ] Commit:
  `git add sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json sheet_cutting_layout/tests/test_recursive_end_piece.py && git commit -m "$(printf 'feat: add child_layout link to Layout End Piece\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"`

---

### Task 2: Frappe-free cascade-graph traversal (depth-first, leaves-first)

**Files:**
- Create: `sheet_cutting_layout/services/cascade_graph.py`
- Create: `sheet_cutting_layout/tests/test_cascade_graph.py`
- Test path: `sheet_cutting_layout/tests/test_cascade_graph.py`

The cascade graph is the spine of the §4.3 cancel cascade. It must be frappe-free: it takes a
`child_links` callable that, given a layout name, returns the names of the layouts linked by that
layout's end-piece `child_layout` rows. The traversal returns descendants in **leaves-first** order
(deepest children before their parents), which is the order in which they must be cancelled so a
parent at `docstatus=2` never blocks its child. It detects cycles (a layout reachable from itself) and
raises `CascadeCycleError` so the §9.3 no-cycle guarantee is enforced even if the data is corrupt.

- [ ] Write the failing test. Create `sheet_cutting_layout/tests/test_cascade_graph.py` with this exact content:

```python
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
		child_links = _links_from_map({"ROOT": []})
		self.assertEqual(collect_descendant_layouts("ROOT", child_links), [])

	def test_returns_single_child(self) -> None:
		child_links = _links_from_map({"ROOT": ["CHILD"], "CHILD": []})
		self.assertEqual(collect_descendant_layouts("ROOT", child_links), ["CHILD"])

	def test_two_levels_are_returned_leaves_first(self) -> None:
		child_links = _links_from_map(
			{"ROOT": ["CHILD"], "CHILD": ["GRANDCHILD"], "GRANDCHILD": []}
		)
		self.assertEqual(
			collect_descendant_layouts("ROOT", child_links),
			["GRANDCHILD", "CHILD"],
		)

	def test_multiple_children_are_each_expanded_before_their_parent(self) -> None:
		child_links = _links_from_map(
			{
				"ROOT": ["A", "B"],
				"A": ["A1"],
				"A1": [],
				"B": [],
			}
		)
		result = collect_descendant_layouts("ROOT", child_links)
		self.assertEqual(result, ["A1", "A", "B"])

	def test_shared_descendant_is_listed_once(self) -> None:
		child_links = _links_from_map(
			{"ROOT": ["A", "B"], "A": ["SHARED"], "B": ["SHARED"], "SHARED": []}
		)
		result = collect_descendant_layouts("ROOT", child_links)
		self.assertEqual(result.count("SHARED"), 1)
		self.assertEqual(result, ["SHARED", "A", "B"])

	def test_root_is_never_in_its_own_descendant_list(self) -> None:
		child_links = _links_from_map({"ROOT": ["CHILD"], "CHILD": []})
		self.assertNotIn("ROOT", collect_descendant_layouts("ROOT", child_links))

	def test_direct_self_reference_raises_cycle_error(self) -> None:
		child_links = _links_from_map({"ROOT": ["ROOT"]})
		with self.assertRaises(CascadeCycleError):
			collect_descendant_layouts("ROOT", child_links)

	def test_indirect_cycle_raises_cycle_error(self) -> None:
		child_links = _links_from_map(
			{"ROOT": ["CHILD"], "CHILD": ["ROOT"]}
		)
		with self.assertRaises(CascadeCycleError):
			collect_descendant_layouts("ROOT", child_links)
```

- [ ] Run it and see it FAIL. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_cascade_graph`
  Expected failure: `ModuleNotFoundError: No module named 'sheet_cutting_layout.services.cascade_graph'`.

- [ ] Implement. Create `sheet_cutting_layout/services/cascade_graph.py` with this exact content:

```python
from __future__ import annotations

from collections.abc import Callable

ChildLinks = Callable[[str], list[str]]


class CascadeCycleError(Exception):
	"""Raised when a child_layout chain forms a cycle (a layout is its own ancestor)."""


def collect_descendant_layouts(root: str, child_links: ChildLinks) -> list[str]:
	"""Return every layout reachable from ``root`` via ``child_links``, leaves-first.

	The result excludes ``root`` itself, lists each descendant exactly once, and orders
	deeper descendants before the layouts that link to them so a depth-first cancel walk
	never tries to cancel a parent before its child. Raises :class:`CascadeCycleError`
	if any layout is reachable from itself.
	"""
	ordered: list[str] = []
	seen: set[str] = set()

	def visit(layout_name: str, ancestors: tuple[str, ...]) -> None:
		if layout_name in ancestors:
			raise CascadeCycleError(
				f"child_layout cycle detected at {layout_name}: "
				f"{' -> '.join((*ancestors, layout_name))}"
			)
		next_ancestors = (*ancestors, layout_name)
		for child in child_links(layout_name):
			if not child:
				continue
			visit(child, next_ancestors)
			if child not in seen:
				seen.add(child)
				ordered.append(child)

	visit(root, ())
	return ordered
```

- [ ] Run the test and see it PASS. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_cascade_graph`
  Expected: 8 tests, OK.

- [ ] Lint. From `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `python -m ruff check sheet_cutting_layout/services/cascade_graph.py sheet_cutting_layout/tests/test_cascade_graph.py && python -m ruff format --check sheet_cutting_layout/services/cascade_graph.py sheet_cutting_layout/tests/test_cascade_graph.py`
  Expected: no errors.

- [ ] Commit:
  `git add sheet_cutting_layout/services/cascade_graph.py sheet_cutting_layout/tests/test_cascade_graph.py && git commit -m "$(printf 'feat: add frappe-free cascade-graph traversal with cycle detection\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"`

---

### Task 3: Frappe-free child-layout guard helpers

**Files:**
- Create: `sheet_cutting_layout/services/recursive_end_piece.py`
- Modify: `sheet_cutting_layout/tests/test_recursive_end_piece.py` (append a unit-test class)
- Test path: `sheet_cutting_layout/tests/test_recursive_end_piece.py`

Pure helpers that decide, for a single end-piece row, whether it owns a child layout, whether the
child's `raw_material_item` matches the parent end-piece's generated item code, and whether a child
layout is still blocked from release because the parent has not yet created the end-piece item it
consumes (§9.3 guard 3 — the "release-order guard helpers" promised by the File-structure table). These
are frappe-free (operate on the already-derived item code string plus an injected `item_exists`
predicate) so they can be unit-tested without a DB and reused by the validator (Task 4) and the release
loop (Task 5).

- [ ] Write the failing test. Append this class to the **end** of `sheet_cutting_layout/tests/test_recursive_end_piece.py`:

```python
from sheet_cutting_layout.services.recursive_end_piece import (
	child_raw_material_matches_end_piece_item,
	child_release_blocked_until_parent_item_exists,
	end_piece_has_child_layout,
)


class TestRecursiveEndPieceGuards(SheetCuttingLayoutTestCase):
	def test_end_piece_has_child_layout_true_when_set(self) -> None:
		self.assertTrue(end_piece_has_child_layout("SCL-CHILD-001"))

	def test_end_piece_has_child_layout_false_when_blank(self) -> None:
		self.assertFalse(end_piece_has_child_layout(None))
		self.assertFalse(end_piece_has_child_layout(""))
		self.assertFalse(end_piece_has_child_layout("   "))

	def test_raw_material_matches_is_case_insensitive_and_trimmed(self) -> None:
		self.assertTrue(
			child_raw_material_matches_end_piece_item(
				child_raw_material_item=" part001shr-ep-2x1250x179 ",
				end_piece_item_code="PART001SHR-EP-2x1250x179",
			)
		)

	def test_raw_material_mismatch_is_detected(self) -> None:
		self.assertFalse(
			child_raw_material_matches_end_piece_item(
				child_raw_material_item="SOMETHING-ELSE",
				end_piece_item_code="PART001SHR-EP-2x1250x179",
			)
		)

	def test_raw_material_match_false_when_either_side_missing(self) -> None:
		self.assertFalse(
			child_raw_material_matches_end_piece_item(
				child_raw_material_item=None,
				end_piece_item_code="PART001SHR-EP-2x1250x179",
			)
		)
		self.assertFalse(
			child_raw_material_matches_end_piece_item(
				child_raw_material_item="PART001SHR-EP-2x1250x179",
				end_piece_item_code=None,
			)
		)

	def test_child_release_blocked_when_parent_item_missing(self) -> None:
		# The end-piece item the child consumes does not exist yet (parent not released).
		self.assertTrue(
			child_release_blocked_until_parent_item_exists(
				raw_material_item="PART001SHR-EP-2x1250x179",
				item_exists=lambda _code: False,
			)
		)

	def test_child_release_not_blocked_when_parent_item_exists(self) -> None:
		# The end-piece item exists (parent already released and created it).
		self.assertFalse(
			child_release_blocked_until_parent_item_exists(
				raw_material_item="PART001SHR-EP-2x1250x179",
				item_exists=lambda _code: True,
			)
		)

	def test_child_release_blocked_passes_trimmed_code_to_predicate(self) -> None:
		seen: list[str] = []

		def item_exists(code: str) -> bool:
			seen.append(code)
			return True

		child_release_blocked_until_parent_item_exists(
			raw_material_item="  PART001SHR-EP-2x1250x179  ",
			item_exists=item_exists,
		)
		self.assertEqual(seen, ["PART001SHR-EP-2x1250x179"])

	def test_child_release_not_blocked_when_raw_material_blank(self) -> None:
		# A blank raw material is a different validation error; this guard stays out of it.
		self.assertFalse(
			child_release_blocked_until_parent_item_exists(
				raw_material_item=None,
				item_exists=lambda _code: False,
			)
		)
		self.assertFalse(
			child_release_blocked_until_parent_item_exists(
				raw_material_item="   ",
				item_exists=lambda _code: False,
			)
		)
```

- [ ] Run it and see it FAIL. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_recursive_end_piece`
  Expected failure: `ModuleNotFoundError: No module named 'sheet_cutting_layout.services.recursive_end_piece'`.

- [ ] Implement. Create `sheet_cutting_layout/services/recursive_end_piece.py` with this exact content:

```python
from __future__ import annotations

from collections.abc import Callable

ItemExists = Callable[[str], bool]


def end_piece_has_child_layout(child_layout: object) -> bool:
	"""True when an end-piece row carries a non-blank child_layout link."""
	return bool(_clean(child_layout))


def child_raw_material_matches_end_piece_item(
	*,
	child_raw_material_item: object,
	end_piece_item_code: object,
) -> bool:
	"""True when the child layout consumes exactly the parent end-piece's generated item.

	Comparison is trimmed and case-insensitive to mirror Frappe Item naming, which is
	case-insensitive. Returns False when either side is missing.
	"""
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
	"""True when a child layout may not be released yet (§9.3 guard 3).

	A child layout consumes the parent end-piece's generated item as its
	``raw_material_item``. That item is created lazily by the parent's release, so the
	child cannot be released before it exists. ``item_exists`` is injected (it maps an
	item code to a bool) so the rule is frappe-free and unit-testable. A blank
	``raw_material_item`` is left to the ordinary required-field validation and is not
	blocked here.
	"""
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
```

- [ ] Run the test and see it PASS. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_recursive_end_piece`
  Expected: all `test_recursive_end_piece` tests OK (Task 1's field test plus the 9 new guard tests).

- [ ] Lint. From `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `python -m ruff check sheet_cutting_layout/services/recursive_end_piece.py sheet_cutting_layout/tests/test_recursive_end_piece.py && python -m ruff format --check sheet_cutting_layout/services/recursive_end_piece.py sheet_cutting_layout/tests/test_recursive_end_piece.py`
  Expected: no errors.

- [ ] Commit:
  `git add sheet_cutting_layout/services/recursive_end_piece.py sheet_cutting_layout/tests/test_recursive_end_piece.py && git commit -m "$(printf 'feat: add frappe-free child-layout guard helpers\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"`

---

## Task group B — Validation guards

### Task 4: Wire child-layout guards into layout validation

**Files:**
- Modify: `sheet_cutting_layout/services/validators.py` (add a `child_layout` field to the `EndPieceRow` Protocol at lines 35-48; add the `_validate_child_layouts` and `_validate_child_release_order` validator functions and call them from `validate_sheet_cutting_layout` after the `for end_piece in end_pieces:` loop at lines 103-105, before the `if end_pieces:` at line 107)
- Modify: `sheet_cutting_layout/tests/test_recursive_end_piece.py` (append an integration-style validator test class covering raw-material match, self-reference, and the release-order guard)
- Test path: `sheet_cutting_layout/tests/test_recursive_end_piece.py`

`validate_sheet_cutting_layout` runs on every save. When an end-piece row has a `child_layout`, these
§9.3 guards must hold:

1. The child layout's `raw_material_item` must equal the parent end-piece's generated item code
   (derived via the existing `derive_end_piece_item_code_from_row`).
2. The child layout must not be the layout itself (self-reference) and must not be an ancestor — a
   cycle. Ancestry is resolved with the Task 2 traversal over the saved data.
3. A child layout cannot be linked unless `disposition == "Reuse"` (the field is gated in the UI, but
   the server must also reject it — a Scrap row with a `child_layout` is invalid data).
4. **§9.3 guard 3 (release order):** a child layout cannot be *released* before the parent has created
   the end-piece item it consumes. The parent creates that item lazily during the parent's own release
   (`ensure_end_piece_item`), so a child whose `raw_material_item` does not yet exist as an `Item`
   cannot reach `Released`. This is gated on `status == "Released"` (a Draft child is allowed) and uses
   the frappe-free `child_release_blocked_until_parent_item_exists` helper (Task 3) with a
   `frappe.db.exists("Item", ...)` predicate.

The validator reads sibling/child rows via `frappe.get_all`/`frappe.db.get_value`; the cycle check
calls `collect_descendant_layouts` with a `child_links` closure that queries `Layout End Piece` rows.
Self/ancestor detection: the layout under validation is a cycle iff it appears in the descendant set of
its own child (or equals the child). The release-order guard (4) is keyed off the layout's own
`raw_material_item` and `status`, so it is checked on the **child** layout as it is released, not on the
parent.

- [ ] Write the failing test. Append this class to the **end** of `sheet_cutting_layout/tests/test_recursive_end_piece.py`. It builds two real persisted layouts and asserts the validator behaviour through `doc.save()`. It reuses the integration fixture builder defined in Task 7 — **but Task 7 lands later**, so this test instead defines a small local helper inline so it is self-contained:

```python
import frappe

from sheet_cutting_layout.tests.factories import register_test_doc


def _make_item(item_code: str) -> str:
	if not frappe.db.exists("Item", item_code):
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": item_code,
				"item_group": "All Item Groups",
				"stock_uom": "Kg",
				"is_stock_item": 1,
				"valuation_rate": 50,
			}
		)
		item.insert(ignore_permissions=True)
		register_test_doc("Item", item.name)
	return item_code


def _make_project(name: str) -> str:
	if not frappe.db.exists("Project", name):
		project = frappe.get_doc({"doctype": "Project", "project_name": name})
		project.insert(ignore_permissions=True)
		register_test_doc("Project", project.name)
		return project.name
	return name


class TestChildLayoutValidation(SheetCuttingLayoutTestCase):
	def setUp(self) -> None:
		super().setUp()
		self.project = _make_project("SCL-TEST-CHILDVAL")
		self.raw_material = _make_item("SCLTESTCHILDRM")
		self.scrap_item = _make_item("SCLTESTCHILDSCRAP")
		self.finished_part = _make_item("SCLTESTCHILDFGSHR")
		# The end-piece generated item code that the child must consume.
		self.end_piece_item = _make_item("SCLTESTCHILDFGSHR-EP-2x500x500")

	def _new_parent(self, layout_code: str, child_layout: str | None) -> object:
		return frappe.get_doc(
			{
				"doctype": "Sheet Cutting Layout",
				"layout_code": layout_code,
				"project": self.project,
				"revision_no": 1,
				"status": "Draft",
				"raw_material_item": self.raw_material,
				"process_scrap_item": self.scrap_item,
				"sheet_thickness_mm": 2,
				"sheet_width_mm": 1000,
				"sheet_length_mm": 1000,
				"strip_thickness_mm": 2,
				"strip_width_mm": 1000,
				"strip_length_mm": 1000,
				"parts_per_strip": 1,
				"no_of_strips": 1,
				"finished_part_code": self.finished_part,
				"net_weight_per_part_kg": 9.715,
				"end_pieces": [
					{
						"width_mm": 500,
						"length_mm": 500,
						"disposition": "Reuse",
						"used_for_finished_part": self.finished_part,
						"child_layout": child_layout,
						"bom_quantity": 1,
						"net_weight_per_part_kg": 3.93,
					}
				],
			}
		)

	def test_child_raw_material_must_match_end_piece_item(self) -> None:
		child = frappe.get_doc(
			{
				"doctype": "Sheet Cutting Layout",
				"layout_code": "SCL-TEST-CHILDVAL-CHILD-BAD",
				"project": self.project,
				"revision_no": 1,
				"status": "Draft",
				"raw_material_item": self.raw_material,  # WRONG: should be end_piece_item
				"sheet_thickness_mm": 2,
				"sheet_width_mm": 500,
				"sheet_length_mm": 500,
				"strip_thickness_mm": 2,
				"strip_width_mm": 500,
				"strip_length_mm": 500,
				"parts_per_strip": 1,
				"no_of_strips": 1,
				"finished_part_code": self.finished_part,
				"net_weight_per_part_kg": 3.93,
			}
		)
		child.insert(ignore_permissions=True)
		register_test_doc("Sheet Cutting Layout", child.name)

		parent = self._new_parent("SCL-TEST-CHILDVAL-PARENT-BAD", child.name)
		with self.assertRaises(frappe.ValidationError):
			parent.insert(ignore_permissions=True)

	def test_child_with_matching_raw_material_validates(self) -> None:
		child = frappe.get_doc(
			{
				"doctype": "Sheet Cutting Layout",
				"layout_code": "SCL-TEST-CHILDVAL-CHILD-OK",
				"project": self.project,
				"revision_no": 1,
				"status": "Draft",
				"raw_material_item": self.end_piece_item,  # matches parent end-piece item
				"sheet_thickness_mm": 2,
				"sheet_width_mm": 500,
				"sheet_length_mm": 500,
				"strip_thickness_mm": 2,
				"strip_width_mm": 500,
				"strip_length_mm": 500,
				"parts_per_strip": 1,
				"no_of_strips": 1,
				"finished_part_code": self.finished_part,
				"net_weight_per_part_kg": 3.93,
			}
		)
		child.insert(ignore_permissions=True)
		register_test_doc("Sheet Cutting Layout", child.name)

		parent = self._new_parent("SCL-TEST-CHILDVAL-PARENT-OK", child.name)
		parent.insert(ignore_permissions=True)
		register_test_doc("Sheet Cutting Layout", parent.name)
		self.assertEqual(parent.end_pieces[0].child_layout, child.name)

	def test_self_reference_is_rejected(self) -> None:
		parent = self._new_parent("SCL-TEST-CHILDVAL-SELF", "SCL-TEST-CHILDVAL-SELF")
		with self.assertRaises(frappe.ValidationError):
			parent.insert(ignore_permissions=True)

	def test_child_cannot_be_released_before_parent_end_piece_item_exists(self) -> None:
		# Build a child that consumes the parent end-piece item, then DELETE that item so
		# it no longer exists (simulating a child released before the parent produced it).
		child = frappe.get_doc(
			{
				"doctype": "Sheet Cutting Layout",
				"layout_code": "SCL-TEST-CHILDVAL-RELORDER",
				"project": self.project,
				"revision_no": 1,
				"status": "Draft",
				"raw_material_item": self.end_piece_item,
				"process_scrap_item": self.scrap_item,
				"sheet_thickness_mm": 2,
				"sheet_width_mm": 500,
				"sheet_length_mm": 500,
				"strip_thickness_mm": 2,
				"strip_width_mm": 500,
				"strip_length_mm": 500,
				"parts_per_strip": 1,
				"no_of_strips": 1,
				"finished_part_code": self.finished_part,
				"net_weight_per_part_kg": 3.93,
			}
		)
		child.insert(ignore_permissions=True)
		register_test_doc("Sheet Cutting Layout", child.name)

		# Drop the end-piece item so the release-order guard sees it as missing.
		frappe.delete_doc("Item", self.end_piece_item, force=True, ignore_permissions=True)
		self.assertFalse(frappe.db.exists("Item", self.end_piece_item))

		child.reload()
		child.status = "Released"
		with self.assertRaises(frappe.ValidationError):
			child.save(ignore_permissions=True)

	def test_child_release_allowed_once_parent_end_piece_item_exists(self) -> None:
		# The end-piece item exists (parent already created it), so the guard passes; a
		# plain save with status Released is accepted by validation.
		child = frappe.get_doc(
			{
				"doctype": "Sheet Cutting Layout",
				"layout_code": "SCL-TEST-CHILDVAL-RELOK",
				"project": self.project,
				"revision_no": 1,
				"status": "Draft",
				"raw_material_item": self.end_piece_item,
				"process_scrap_item": self.scrap_item,
				"sheet_thickness_mm": 2,
				"sheet_width_mm": 500,
				"sheet_length_mm": 500,
				"strip_thickness_mm": 2,
				"strip_width_mm": 500,
				"strip_length_mm": 500,
				"parts_per_strip": 1,
				"no_of_strips": 1,
				"finished_part_code": self.finished_part,
				"net_weight_per_part_kg": 3.93,
			}
		)
		child.insert(ignore_permissions=True)
		register_test_doc("Sheet Cutting Layout", child.name)

		self.assertTrue(frappe.db.exists("Item", self.end_piece_item))
		child.status = "Released"
		child.save(ignore_permissions=True)  # must not raise
		self.assertEqual(child.status, "Released")
```

- [ ] Run it and see it FAIL. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_recursive_end_piece`
  Expected failure: `test_child_raw_material_must_match_end_piece_item`, `test_self_reference_is_rejected`, and `test_child_cannot_be_released_before_parent_end_piece_item_exists` FAIL because no `frappe.ValidationError` is raised yet (the validator does not check `child_layout` or release order); `test_child_with_matching_raw_material_validates` and `test_child_release_allowed_once_parent_end_piece_item_exists` may pass incidentally.

- [ ] Implement: extend the Protocol. In `sheet_cutting_layout/services/validators.py`, add a `child_layout` attribute to the `EndPieceRow` Protocol. Change the block at lines 35-48 so it reads:

```python
class EndPieceRow(Protocol):
	end_piece_item_code: str | None
	width_mm: float | None
	length_mm: float | None
	weight_kg: float | None
	qty_per_sheet: float | None
	disposition: str | None
	used_for_finished_part: str | None
	child_layout: str | None
	bom_quantity: float | None
	net_weight_per_part_kg: float | None
	gross_weight_per_part_kg: float | None
	scrap_weight_per_part_kg: float | None
	bom_scrap_quantity_kg: float | None
	scrap_item: str | None
```

- [ ] Implement: add the imports. In `sheet_cutting_layout/services/validators.py`, add to the import block (after the existing `from sheet_cutting_layout.services.end_piece_item_service import (...)` block at lines 11-14):

```python
from sheet_cutting_layout.services.cascade_graph import (
	CascadeCycleError,
	collect_descendant_layouts,
)
from sheet_cutting_layout.services.end_piece_item_service import (
	derive_end_piece_item_code_from_row,
)
from sheet_cutting_layout.services.recursive_end_piece import (
	child_raw_material_matches_end_piece_item,
	child_release_blocked_until_parent_item_exists,
	end_piece_has_child_layout,
)
```

- [ ] Implement: call the new validators. In `validate_sheet_cutting_layout`, immediately after the existing `for end_piece in end_pieces:` loop body that ends at line 105 (`_validate_end_piece_required_fields(layout, end_piece)`), keep that loop and add two new calls right after the loop closes and before `if end_pieces:` at line 107. Insert these lines:

```python
		_validate_child_layouts(layout, end_pieces)
		_validate_child_release_order(layout)
```

  so the region reads:

```python
	for end_piece in end_pieces:
		_validate_end_piece_item_code_is_locked(end_piece)
		_validate_end_piece_required_fields(layout, end_piece)

	_validate_child_layouts(layout, end_pieces)
	_validate_child_release_order(layout)

	if end_pieces:
		_validate_end_piece_distribution(layout, end_pieces)
```

- [ ] Implement: add the validator function. Append this function to `sheet_cutting_layout/services/validators.py` (place it directly after `_validate_end_piece_required_fields`, before `_validate_unreleased_legacy_end_piece_multiplicity`):

```python
def _validate_child_layouts(
	layout: SheetCuttingLayoutDocument,
	end_pieces: Sequence[EndPieceRow],
) -> None:
	layout_name = str(getattr(layout, "name", "") or "").strip()
	for end_piece in end_pieces:
		child_layout = getattr(end_piece, "child_layout", None)
		if not end_piece_has_child_layout(child_layout):
			continue
		child_layout = str(child_layout).strip()
		if not _is_reuse_end_piece(end_piece):
			frappe.throw(_("A child layout can only be linked on a reuse end piece"))
		if layout_name and child_layout == layout_name:
			frappe.throw(_("A layout cannot be its own child layout"))
		_validate_child_raw_material(layout, end_piece, child_layout)
		_validate_no_child_layout_cycle(layout_name, child_layout)


def _validate_child_raw_material(
	layout: SheetCuttingLayoutDocument,
	end_piece: EndPieceRow,
	child_layout: str,
) -> None:
	end_piece_item_code = derive_end_piece_item_code_from_row(layout, end_piece)  # type: ignore[arg-type]
	get_value = getattr(getattr(frappe, "db", None), "get_value", None)
	if not callable(get_value):
		return
	child_raw_material_item = get_value("Sheet Cutting Layout", child_layout, "raw_material_item")
	if not child_raw_material_matches_end_piece_item(
		child_raw_material_item=child_raw_material_item,
		end_piece_item_code=end_piece_item_code,
	):
		frappe.throw(
			_(
				"Child layout {0} must use the end-piece item {1} as its raw material, found {2}"
			).format(child_layout, end_piece_item_code, child_raw_material_item or "none")
		)


def _validate_no_child_layout_cycle(layout_name: str, child_layout: str) -> None:
	if not layout_name:
		return
	try:
		descendants = collect_descendant_layouts(child_layout, _child_links_provider())
	except CascadeCycleError:
		frappe.throw(_("Child layout chain contains a cycle and cannot be saved"))
	if layout_name == child_layout or layout_name in descendants:
		frappe.throw(_("Linking child layout {0} would create a cycle").format(child_layout))


def _child_links_provider():
	def child_links(layout_name: str) -> list[str]:
		get_all = getattr(getattr(frappe, "db", None), "get_all", None)
		if not callable(get_all):
			return []
		rows = get_all(
			"Layout End Piece",
			filters={"parent": layout_name, "parenttype": "Sheet Cutting Layout"},
			pluck="child_layout",
		)
		return [str(row).strip() for row in rows if row and str(row).strip()]

	return child_links


def _validate_child_release_order(layout: SheetCuttingLayoutDocument) -> None:
	"""§9.3 guard 3: a child layout cannot be released before its end-piece item exists.

	The child consumes the parent end-piece's generated item as ``raw_material_item``;
	the parent creates that item lazily during its own release. Only enforced when this
	layout is being released (``status == "Released"``) — a Draft child is allowed to
	reference an item the parent has not produced yet.
	"""
	status = str(getattr(layout, "status", "") or "").strip()
	if status != "Released":
		return
	raw_material_item = getattr(layout, "raw_material_item", None)
	exists = getattr(getattr(frappe, "db", None), "exists", None)
	if not callable(exists):
		return
	if child_release_blocked_until_parent_item_exists(
		raw_material_item=raw_material_item,
		item_exists=lambda code: bool(exists("Item", code)),
	):
		frappe.throw(
			_(
				"Raw material item {0} does not exist yet; release the parent layout that "
				"produces this end-piece item before releasing this child layout"
			).format(str(raw_material_item).strip())
		)
```

- [ ] Run the test and see it PASS. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_recursive_end_piece`
  Expected: all tests OK, including the new raw-material-match, self-reference, and release-order validation cases.

- [ ] Run the full validator suite to confirm no regression. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators`
  Expected: all existing validator tests still OK.

- [ ] Lint. From `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `python -m ruff check sheet_cutting_layout/services/validators.py sheet_cutting_layout/tests/test_recursive_end_piece.py && python -m ruff format --check sheet_cutting_layout/services/validators.py sheet_cutting_layout/tests/test_recursive_end_piece.py`
  Expected: no errors.

- [ ] Commit:
  `git add sheet_cutting_layout/services/validators.py sheet_cutting_layout/tests/test_recursive_end_piece.py && git commit -m "$(printf 'feat: validate child-layout raw material match, no cycles, and release order\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"`

---

## Task group C — Hybrid release and cascade

### Task 5: Skip the simple end-piece item/BOM path when a child layout owns it

**Files:**
- Modify: `sheet_cutting_layout/services/release_service.py` (the `_ensure_and_link_end_piece_item` helper and the `_default_bom_document_factory` helper — Phase 0 shifts their line numbers, so locate them by symbol name)
- Modify: `sheet_cutting_layout/services/end_piece_bom_service.py` (`_reuse_end_pieces` at lines 158-159)
- Test path: `sheet_cutting_layout/tests/test_recursive_end_piece_release.py` (new — see Task 7 for the integration tests; this task adds a focused unit-level assertion)

§9.2 hybrid semantics: when an end-piece row has a `child_layout`, the **child** owns the real BOM. The
parent must still:
- derive and link the end-piece generated item (so the parent BOM can carry the byproduct row and so
  the child can consume that exact item as raw material — the §9.3 guard depends on the item existing),
- **not** generate a *simple* end-piece BOM for that row via `end_piece_bom_service`.

So the parent's main-BOM build still calls `_ensure_and_link_end_piece_item` (it creates the item),
but the simple end-piece-BOM generation path (`generate_end_piece_boms`, driven by
`_reuse_end_pieces`) must **exclude** rows that have a `child_layout`. The byproduct row in the parent
BOM is already produced by the Phase-"main-bom-end-piece-byproduct" work and is unaffected.

- [ ] Write the failing test. Create `sheet_cutting_layout/tests/test_recursive_end_piece_release.py` with this exact content (the integration fixtures arrive in Task 7; this first test exercises only the frappe-free row filter):

```python
from __future__ import annotations

from types import SimpleNamespace

from sheet_cutting_layout.services.end_piece_bom_service import _reuse_end_pieces
from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


class TestReuseEndPieceFilterSkipsChildLayouts(SheetCuttingLayoutTestCase):
	def test_rows_with_child_layout_are_excluded_from_simple_bom_generation(self) -> None:
		simple_row = SimpleNamespace(disposition="Reuse", child_layout=None)
		child_owned_row = SimpleNamespace(disposition="Reuse", child_layout="SCL-CHILD-001")
		scrap_row = SimpleNamespace(disposition="Scrap", child_layout=None)
		layout = SimpleNamespace(end_pieces=[simple_row, child_owned_row, scrap_row])

		result = _reuse_end_pieces(layout)

		self.assertIn(simple_row, result)
		self.assertNotIn(child_owned_row, result)
		self.assertNotIn(scrap_row, result)
```

- [ ] Run it and see it FAIL. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_recursive_end_piece_release`
  Expected failure: `AssertionError: SimpleNamespace(...child_layout='SCL-CHILD-001') unexpectedly found in [...]` — `_reuse_end_pieces` does not yet skip child-owned rows.

- [ ] Implement: filter child-owned rows out of simple BOM generation. In `sheet_cutting_layout/services/end_piece_bom_service.py`, change `_reuse_end_pieces` (lines 158-159) to:

```python
def _reuse_end_pieces(layout: LayoutDocument) -> list[EndPieceRow]:
	return [
		row
		for row in getattr(layout, "end_pieces", []) or []
		if _is_reuse(row) and not _row_has_child_layout(row)
	]


def _row_has_child_layout(row: EndPieceRow) -> bool:
	value = getattr(row, "child_layout", None)
	return bool(str(value or "").strip())
```

- [ ] Implement: add `child_layout` to the `EndPieceRow` Protocol in `end_piece_bom_service.py`. In the `EndPieceRow` Protocol (lines 33-47), add the line after `used_for_finished_part: str | None`:

```python
	child_layout: str | None
```

- [ ] Run the test and see it PASS. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_recursive_end_piece_release`
  Expected: 1 test, OK.

- [ ] Run the end-piece BOM suite to confirm no regression. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service`
  Expected: all existing tests OK (rows without `child_layout` still pass `_row_has_child_layout` → False).

- [ ] Lint. From `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `python -m ruff check sheet_cutting_layout/services/end_piece_bom_service.py sheet_cutting_layout/tests/test_recursive_end_piece_release.py && python -m ruff format --check sheet_cutting_layout/services/end_piece_bom_service.py sheet_cutting_layout/tests/test_recursive_end_piece_release.py`
  Expected: no errors.

- [ ] Commit:
  `git add sheet_cutting_layout/services/end_piece_bom_service.py sheet_cutting_layout/tests/test_recursive_end_piece_release.py && git commit -m "$(printf 'feat: child-owned end pieces skip simple end-piece BOM generation\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"`

---

### Task 6: Extend the native `on_cancel` cascade to walk `child_layout`

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py` (`on_cancel` — added in Phase 0)
- Modify: `sheet_cutting_layout/services/release_service.py` (add a cascade helper next to the Phase-0 `retire_layout_boms` retirement helper — Phase 0 changes the line layout, so locate it by symbol name)
- Test path: `sheet_cutting_layout/tests/test_recursive_end_piece_release.py` (integration cascade tests land in Task 7; this task adds the wiring + a frappe-free ordering test)

§9.4 / §4.3: when a parent layout is cancelled, every descendant layout (linked via end-piece
`child_layout`, transitively) must be cancelled **leaves-first**, and each descendant's BOMs
deactivated. Because `collect_descendant_layouts` returns leaves-first order, we cancel each descendant
layout's document via native `doc.cancel()` — which fires *its own* `on_cancel`, recursing through
`retire_layout_boms` and `ignore_linked_doctypes=["BOM"]`. The parent's own BOM retirement is already
handled by the Phase 0 `on_cancel` (`retire_layout_boms`). This task adds the descendant walk **before**
the parent retires its own BOMs, so the children are gone before the parent.

If any descendant BOM is consumed by a submitted Manufacture Stock Entry, Frappe's native
`check_if_doc_is_linked(method="Cancel")` raises `LinkExistsError` when that BOM is cancelled; the
Phase 0 `retire_layout_boms` catches it and falls back to native deactivate (`is_active=0`). The layout
cancel itself is blocked natively only if a *submitted* Stock Entry links the **layout** — which it does
not; Stock Entries link BOMs, and BOMs are exempted on the layout via `ignore_linked_doctypes`. The
descendant **BOM** cancel is what is gated, and `retire_layout_boms` resolves it by deactivating. (See
Task 7 for the integration test that asserts the Manufacture-Stock-Entry case ends with the BOM
deactivated, not cancelled.)

- [ ] Write the failing test. Append this class to `sheet_cutting_layout/tests/test_recursive_end_piece_release.py`:

```python
from sheet_cutting_layout.services.release_service import collect_descendant_layout_names


class TestCollectDescendantLayoutNames(SheetCuttingLayoutTestCase):
	def test_walks_child_layout_links_leaves_first(self) -> None:
		grandchild = SimpleNamespace(end_pieces=[])
		child = SimpleNamespace(
			end_pieces=[SimpleNamespace(child_layout="SCL-GRANDCHILD")]
		)
		root = SimpleNamespace(
			name="SCL-ROOT",
			end_pieces=[SimpleNamespace(child_layout="SCL-CHILD")],
		)
		registry = {"SCL-CHILD": child, "SCL-GRANDCHILD": grandchild}

		def loader(layout_name: str) -> object:
			return registry[layout_name]

		names = collect_descendant_layout_names(root, loader)

		self.assertEqual(names, ["SCL-GRANDCHILD", "SCL-CHILD"])
```

- [ ] Run it and see it FAIL. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_recursive_end_piece_release`
  Expected failure: `ImportError: cannot import name 'collect_descendant_layout_names' from 'sheet_cutting_layout.services.release_service'`.

- [ ] Implement: add the descendant-name collector. In `sheet_cutting_layout/services/release_service.py`, add this import to the top import block (after the import of `finalize_new_revision_release` from `sheet_cutting_layout.services.versioning`, keeping the `sheet_cutting_layout.services.*` imports alphabetically grouped):

```python
from sheet_cutting_layout.services.cascade_graph import collect_descendant_layouts
```

  Then append this function to `release_service.py` (place it directly after the `_layout_bom_names` helper):

```python
def collect_descendant_layout_names(
	layout: object,
	load_layout: Callable[[str], object],
) -> list[str]:
	"""Return descendant layout names (leaves-first) via end-piece child_layout links.

	``load_layout`` maps a layout name to a document exposing ``end_pieces``; it is
	injected so the traversal stays testable without a live database.
	"""

	def child_links(layout_name: str) -> list[str]:
		if layout_name == _layout_name(layout):
			source = layout
		else:
			source = load_layout(layout_name)
		return _child_layout_links(source)

	return collect_descendant_layouts(_layout_name(layout), child_links)


def _child_layout_links(source: object) -> list[str]:
	names: list[str] = []
	for row in getattr(source, "end_pieces", []) or []:
		_append_unique_clean(names, getattr(row, "child_layout", None))
	return names


def _layout_name(layout: object) -> str:
	return str(getattr(layout, "name", "") or "").strip()


def cancel_descendant_layouts(layout: object) -> list[str]:
	"""Cancel every descendant layout leaves-first via native ``doc.cancel()``.

	Each ``doc.cancel()`` fires the descendant's own ``on_cancel``, which retires its
	BOMs and recurses into its own children. Returns the names cancelled. Requires Frappe.
	"""
	if not frappe:
		return []

	def load_layout(layout_name: str) -> object:
		return frappe.get_doc("Sheet Cutting Layout", layout_name)

	cancelled: list[str] = []
	for descendant_name in collect_descendant_layout_names(layout, load_layout):
		descendant = frappe.get_doc("Sheet Cutting Layout", descendant_name)
		if _is_cancelled_document(descendant):
			continue
		descendant.cancel()
		cancelled.append(descendant_name)
	return cancelled
```

- [ ] Implement: call the cascade from `on_cancel`. Open `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`. Locate the Phase-0 `on_cancel` method. It should currently read approximately:

```python
	def on_cancel(self) -> None:
		retire_layout_boms(self)
```

  Change it to cancel descendants **first**, then retire the parent's own BOMs:

```python
	def on_cancel(self) -> None:
		cancel_descendant_layouts(self)
		retire_layout_boms(self)
```

  Update the import line at the top of the controller (the Phase-0 import block that pulls from
  `release_service`) to also import `cancel_descendant_layouts`:

```python
from sheet_cutting_layout.services.release_service import (
	cancel_descendant_layouts,
	release_layout,
	retire_layout_boms,
)
```

- [ ] If Phase 0 named the parent BOM-retirement helper something other than `retire_layout_boms`, rename it here. Confirm the exact symbol exported by `release_service` for parent BOM retirement:
  `python -c "import ast,sys;src=open('/Users/gurudattkulkarni/Workspace/sheet_cutting_layout/sheet_cutting_layout/services/release_service.py').read();print([n.name for n in ast.walk(ast.parse(src)) if isinstance(n,ast.FunctionDef) and 'retire' in n.name or (isinstance(n,ast.FunctionDef) and 'cancel_gen' in n.name)])"`
  Expected: prints the retirement function name(s). If it is not `retire_layout_boms`, substitute that
  name in the two edits above (the import and the `on_cancel` body), and only there.

- [ ] Run the test and see it PASS. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_recursive_end_piece_release`
  Expected: `test_walks_child_layout_links_leaves_first` OK plus the earlier filter test.

- [ ] Lint. From `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `python -m ruff check sheet_cutting_layout/services/release_service.py sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py && python -m ruff format --check sheet_cutting_layout/services/release_service.py sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`
  Expected: no errors.

- [ ] Commit:
  `git add sheet_cutting_layout/services/release_service.py sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py && git commit -m "$(printf 'feat: cancel descendant layouts leaves-first on parent cancel\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"`

---

## Task group D — End-to-end integration and recursion lifecycle

### Task 7: Integration — 2-level release, cascade cancel, native block, gated delete

**Files:**
- Modify: `sheet_cutting_layout/tests/test_recursive_end_piece_release.py` (append the integration class + a shared fixture builder)
- Test path: `sheet_cutting_layout/tests/test_recursive_end_piece_release.py`

This is the full §9.6 integration coverage against a real DB: a parent layout whose end piece links a
child layout, which itself has an end piece linking a grandchild layout (2 levels). It exercises:
release builds all BOMs; supersede/cancel the parent cascades (every descendant layout cancelled, every
BOM deactivated); cancel blocked natively when a descendant BOM is consumed by a submitted Manufacture
Stock Entry (ends deactivated, not cancelled); delete is framework-gated.

These tests drive the **real lifecycle** through the workflow: insert Draft → submit → release →
cancel. They rely on the Phase 0 `on_submit` release and `on_cancel` cascade. The fixture builder
constructs items, project, child, and parent layouts with weight-balanced numbers so the existing
consumption validator passes.

- [ ] Write the failing test. Append this class to `sheet_cutting_layout/tests/test_recursive_end_piece_release.py`:

```python
import frappe

from sheet_cutting_layout.tests.factories import register_test_doc


def _ensure_item(item_code: str, *, valuation_rate: float = 50.0) -> str:
	if not frappe.db.exists("Item", item_code):
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": item_code,
				"item_group": "All Item Groups",
				"stock_uom": "Kg",
				"is_stock_item": 1,
				"valuation_rate": valuation_rate,
			}
		)
		item.insert(ignore_permissions=True)
		register_test_doc("Item", item.name)
	return item_code


def _ensure_project(name: str) -> str:
	if frappe.db.exists("Project", name):
		return name
	project = frappe.get_doc({"doctype": "Project", "project_name": name})
	project.insert(ignore_permissions=True)
	register_test_doc("Project", project.name)
	return project.name


def _release(layout: object) -> None:
	"""Drive a Draft layout to Released through the native submit lifecycle."""
	layout.status = "Released"
	layout.submit()


class TestRecursiveEndPieceLifecycle(SheetCuttingLayoutTestCase):
	def setUp(self) -> None:
		super().setUp()
		self.project = _ensure_project("SCL-TEST-RECUR")
		self.raw_material = _ensure_item("SCLTESTRECURRM")
		self.scrap_item = _ensure_item("SCLTESTRECURSCRAP")
		self.finished_part = _ensure_item("SCLTESTRECURFGSHR")
		# End-piece generated item for the parent: <FG>-EP-<t>x<w>x<l>
		self.parent_end_piece_item = _ensure_item("SCLTESTRECURFGSHR-EP-2x500x1000")
		# End-piece generated item for the child (grandchild raw material).
		self.child_end_piece_item = _ensure_item(
			"SCLTESTRECURFGSHR-EP-2x250x500"
		)

	def _build_grandchild(self) -> object:
		grandchild = frappe.get_doc(
			{
				"doctype": "Sheet Cutting Layout",
				"layout_code": "SCL-TEST-RECUR-GC",
				"project": self.project,
				"revision_no": 1,
				"status": "Draft",
				"raw_material_item": self.child_end_piece_item,
				"process_scrap_item": self.scrap_item,
				"sheet_thickness_mm": 2,
				"sheet_width_mm": 250,
				"sheet_length_mm": 500,
				"strip_thickness_mm": 2,
				"strip_width_mm": 250,
				"strip_length_mm": 500,
				"parts_per_strip": 1,
				"no_of_strips": 1,
				"finished_part_code": self.finished_part,
				"net_weight_per_part_kg": 1.965,
			}
		)
		grandchild.insert(ignore_permissions=True)
		register_test_doc("Sheet Cutting Layout", grandchild.name)
		return grandchild

	def _build_child(self, grandchild_name: str) -> object:
		child = frappe.get_doc(
			{
				"doctype": "Sheet Cutting Layout",
				"layout_code": "SCL-TEST-RECUR-CHILD",
				"project": self.project,
				"revision_no": 1,
				"status": "Draft",
				"raw_material_item": self.parent_end_piece_item,
				"process_scrap_item": self.scrap_item,
				"sheet_thickness_mm": 2,
				"sheet_width_mm": 500,
				"sheet_length_mm": 1000,
				"strip_thickness_mm": 2,
				"strip_width_mm": 250,
				"strip_length_mm": 1000,
				"parts_per_strip": 1,
				"no_of_strips": 1,
				"finished_part_code": self.finished_part,
				"net_weight_per_part_kg": 3.93,
				"end_pieces": [
					{
						"width_mm": 250,
						"length_mm": 500,
						"disposition": "Reuse",
						"used_for_finished_part": self.finished_part,
						"child_layout": grandchild_name,
						"bom_quantity": 1,
						"net_weight_per_part_kg": 1.965,
					}
				],
			}
		)
		child.insert(ignore_permissions=True)
		register_test_doc("Sheet Cutting Layout", child.name)
		return child

	def _build_parent(self, child_name: str) -> object:
		parent = frappe.get_doc(
			{
				"doctype": "Sheet Cutting Layout",
				"layout_code": "SCL-TEST-RECUR-PARENT",
				"project": self.project,
				"revision_no": 1,
				"status": "Draft",
				"raw_material_item": self.raw_material,
				"process_scrap_item": self.scrap_item,
				"sheet_thickness_mm": 2,
				"sheet_width_mm": 1000,
				"sheet_length_mm": 1000,
				"strip_thickness_mm": 2,
				"strip_width_mm": 500,
				"strip_length_mm": 1000,
				"parts_per_strip": 1,
				"no_of_strips": 1,
				"finished_part_code": self.finished_part,
				"net_weight_per_part_kg": 5.785,
				"end_pieces": [
					{
						"width_mm": 500,
						"length_mm": 1000,
						"disposition": "Reuse",
						"used_for_finished_part": self.finished_part,
						"child_layout": child_name,
						"bom_quantity": 1,
						"net_weight_per_part_kg": 3.93,
					}
				],
			}
		)
		parent.insert(ignore_permissions=True)
		register_test_doc("Sheet Cutting Layout", parent.name)
		return parent

	def _build_two_level_tree(self) -> tuple[object, object, object]:
		grandchild = self._build_grandchild()
		child = self._build_child(grandchild.name)
		parent = self._build_parent(child.name)
		return parent, child, grandchild

	def test_release_builds_a_bom_for_every_layout_in_the_tree(self) -> None:
		parent, child, grandchild = self._build_two_level_tree()
		_release(grandchild)
		_release(child)
		_release(parent)

		for layout in (parent, child, grandchild):
			layout.reload()
			self.assertTrue(
				frappe.db.exists("BOM", {"sheet_cutting_layout": layout.name}),
				f"{layout.name} should own a generated BOM",
			)

	def test_cancel_parent_cascades_and_deactivates_every_descendant_bom(self) -> None:
		parent, child, grandchild = self._build_two_level_tree()
		_release(grandchild)
		_release(child)
		_release(parent)

		parent.reload()
		parent.cancel()

		for layout in (child, grandchild):
			layout.reload()
			self.assertEqual(layout.docstatus, 2, f"{layout.name} should be cancelled")
			# Every BOM that this descendant layout owns must now be inactive.
			boms = frappe.get_all(
				"BOM",
				filters={"sheet_cutting_layout": layout.name},
				fields=["name", "is_active"],
			)
			self.assertTrue(boms, f"{layout.name} BOM should still exist after cancel")
			self.assertTrue(
				all(not bom.is_active for bom in boms),
				f"all BOMs for {layout.name} must be deactivated",
			)

	def test_descendant_bom_consumed_by_manufacture_is_deactivated_not_cancelled(self) -> None:
		parent, child, grandchild = self._build_two_level_tree()
		_release(grandchild)
		_release(child)
		_release(parent)

		grandchild.reload()
		grandchild_bom = frappe.db.get_value(
			"BOM", {"sheet_cutting_layout": grandchild.name}, "name"
		)
		self.assertIsNotNone(grandchild_bom)

		# A submitted Manufacture Stock Entry consuming the grandchild BOM blocks its cancel;
		# native fallback deactivates it (is_active=0) instead.
		stock_entry = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Manufacture",
				"from_bom": 1,
				"bom_no": grandchild_bom,
				"use_multi_level_bom": 0,
				"fg_completed_qty": grandchild.parts_per_sheet or 1,
				"company": frappe.defaults.get_user_default("Company")
				or frappe.db.get_single_value("Global Defaults", "default_company"),
			}
		)
		stock_entry.get_items()
		stock_entry.insert(ignore_permissions=True)
		register_test_doc("Stock Entry", stock_entry.name)
		stock_entry.submit()

		parent.reload()
		parent.cancel()

		grandchild.reload()
		self.assertEqual(
			grandchild.docstatus,
			2,
			"grandchild layout still cancels because BOM is exempted via ignore_linked_doctypes",
		)
		bom = frappe.get_doc("BOM", grandchild_bom)
		self.assertEqual(bom.docstatus, 1, "BOM stays submitted because a Stock Entry blocks cancel")
		self.assertFalse(bom.is_active, "BOM is deactivated via the native fallback")

	def test_delete_is_framework_gated_while_submitted_bom_links(self) -> None:
		parent, child, grandchild = self._build_two_level_tree()
		_release(grandchild)
		_release(child)
		_release(parent)

		parent.reload()
		with self.assertRaises(frappe.LinkExistsError):
			parent.delete()
```

- [ ] Run it and see it FAIL. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_recursive_end_piece_release`
  Expected failure: the lifecycle tests fail because the parent BOM's byproduct row / child consumption
  is not yet weight-balanced for the recursive case, or because a descendant BOM is not deactivated.
  Confirm each failing assertion message points at a real gap (cascade or balance), not a fixture typo.

- [ ] Diagnose and adjust the fixture weights if the consumption validator throws. The parent sheet
  weight is `2 * 1000 * 1000 * 0.786 / 100000 = 15.72 kg`. The parent end piece
  (`500 x 1000`) weighs `2 * 500 * 1000 * 0.786 / 100000 = 7.86 kg`. The finished part gross must
  consume the remainder. Verify the numbers balance with:
  `python -c "f=lambda t,w,l: t*w*l*0.786/100000; print('sheet',f(2,1000,1000),'ep',f(2,500,1000),'rem',f(2,1000,1000)-f(2,500,1000))"`
  Expected: `sheet 15.72 ep 7.86 rem 7.86`. Set the parent finished-part `net_weight_per_part_kg`
  and `gross` so that `gross_per_part * parts_per_sheet + end_piece_weight == sheet_weight` within the
  0.005 kg tolerance (`parts_per_sheet = 1` here, so gross_per_part = 7.86, net = 5.785 leaves
  scrap 2.075 — confirm the `process_scrap_item` is set, which it is). Adjust net weights in
  `_build_parent`/`_build_child`/`_build_grandchild` only if the validator complains, keeping the
  child/grandchild balanced the same way against their smaller sheets.

- [ ] Implement: confirm the cascade is wired (Task 6 already did the work). No new production code is
  expected here — this task is the integration gate. If `test_cancel_parent_cascades_...` still fails
  because a descendant layout is **not** cancelled, re-verify the `on_cancel` edit in Task 6 calls
  `cancel_descendant_layouts(self)` before `retire_layout_boms(self)` and that
  `ignore_linked_doctypes = ["BOM"]` is present on the controller class (Phase 0). If
  `test_descendant_bom_consumed_by_manufacture_...` fails because `retire_layout_boms` does **not**
  fall back to deactivate on `LinkExistsError`, fix the Phase-0 retirement helper to wrap
  `bom.cancel()` in `try/except frappe.LinkExistsError` and on the exception call
  `bom.db_set("is_active", 0)` via the submitted-BOM update path. (This is the §4.3 contract;
  if Phase 0 implemented it correctly the test passes as-is.)

- [ ] Run the test and see it PASS. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_recursive_end_piece_release`
  Expected: all classes in the module OK (filter, descendant-name ordering, and the four lifecycle tests).

- [ ] Run the full app suite to confirm no regression across release/validators/end-piece services. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-tests --app sheet_cutting_layout`
  Expected: entire suite OK.

- [ ] Lint. From `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `python -m ruff check sheet_cutting_layout/tests/test_recursive_end_piece_release.py && python -m ruff format --check sheet_cutting_layout/tests/test_recursive_end_piece_release.py`
  Expected: no errors.

- [ ] Commit:
  `git add sheet_cutting_layout/tests/test_recursive_end_piece_release.py && git commit -m "$(printf 'test: cover recursive end-piece release, cascade cancel, and gated delete\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"`

---

### Task 8: E2E — link a child layout, release, supersede parent, assert retired

**Files:**
- Create: `cypress/integration/sheet_cutting_layout_recursive_end_piece.js`
- Test path: `cypress/integration/sheet_cutting_layout_recursive_end_piece.js`

§9.6 E2E: build a parent layout whose reuse end piece links a child layout (created first), release
both through the desk workflow, supersede (cancel) the parent, then assert via the REST API that the
child layout is cancelled (`docstatus == 2`) and every BOM that referenced either layout is inactive.
This mirrors `cypress/integration/sheet_cutting_layout_release.js` conventions (login, `cy.call`
inserts, `runWorkflowAction`).

- [ ] Write the spec. Create `cypress/integration/sheet_cutting_layout_recursive_end_piece.js` with this exact content:

```javascript
describe("Sheet Cutting Layout recursive end-piece cascade", () => {
	const suffix = Date.now();
	const project = `SCLRECURPROJ${suffix}`;
	const rawMaterial = `SCLRECURRM${suffix}`;
	const scrapItem = `SCLRECURSCRAP${suffix}`;
	const finishedPart = `PART${suffix}SHR`;
	// Derived end-piece item the child consumes: <FG>-EP-<t>x<w>x<l>
	const endPieceItem = `${finishedPart}-EP-2x500x1000`;
	const parentCode = `SCLRECURP${suffix}`;
	const childCode = `SCLRECURC${suffix}`;
	let projectName;

	Cypress.on("uncaught:exception", () => false);

	function runWorkflowAction(action, expectedStatus) {
		cy.contains(".actions-btn-group button, button", "Actions").click();
		cy.contains(".dropdown-menu a, .dropdown-menu button", action).click();
		cy.get("body").then(($body) => {
			if ($body.find(".modal:visible").length) {
				cy.get(".modal:visible").within(() => {
					cy.contains("button", "Yes").click();
				});
			}
		});
		cy.get(".modal:visible").should("not.exist");
		cy.get(".freeze:visible").should("not.exist");
		if (expectedStatus) {
			cy.contains('[data-fieldname="status"]', expectedStatus);
		}
	}

	function releaseLayout(layoutCode) {
		cy.visit(`/app/sheet-cutting-layout/${layoutCode}`);
		runWorkflowAction("Submit for Check", "Submitted for Check");
		runWorkflowAction("Project Manager Approves", "PM Approved");
		runWorkflowAction("Purchase Approves", "Approved by Purchase");
		runWorkflowAction("MR Release", "Released");
		cy.contains('[data-fieldname="status"]', "Released");
	}

	before(() => {
		cy.login();
		cy.ensureHsnCode("720890");
		cy.call("frappe.client.insert", {
			doc: { doctype: "Project", name: project, project_name: project },
		}).then(({ message }) => {
			projectName = message.name;
		});
		[rawMaterial, scrapItem, finishedPart, endPieceItem].forEach((itemCode) => {
			cy.call("frappe.client.insert", {
				doc: {
					doctype: "Item",
					item_code: itemCode,
					item_name: itemCode,
					item_group: "All Item Groups",
					stock_uom: "Kg",
					is_stock_item: 1,
					valuation_rate: 50,
					gst_hsn_code: "720890",
				},
			});
		});
		// Child layout consumes the parent end-piece item as its raw material.
		cy.call("frappe.client.insert", {
			doc: {
				doctype: "Sheet Cutting Layout",
				layout_code: childCode,
				project: project,
				revision_no: 1,
				status: "Draft",
				raw_material_item: endPieceItem,
				process_scrap_item: scrapItem,
				sheet_thickness_mm: 2,
				sheet_width_mm: 500,
				sheet_length_mm: 1000,
				strip_thickness_mm: 2,
				strip_width_mm: 250,
				strip_length_mm: 1000,
				parts_per_strip: 1,
				no_of_strips: 1,
				finished_part_code: finishedPart,
				net_weight_per_part_kg: 5.86,
			},
		});
		// Parent layout: reuse end piece links the child layout.
		cy.call("frappe.client.insert", {
			doc: {
				doctype: "Sheet Cutting Layout",
				layout_code: parentCode,
				project: project,
				revision_no: 1,
				status: "Draft",
				raw_material_item: rawMaterial,
				process_scrap_item: scrapItem,
				sheet_thickness_mm: 2,
				sheet_width_mm: 1000,
				sheet_length_mm: 1000,
				strip_thickness_mm: 2,
				strip_width_mm: 500,
				strip_length_mm: 1000,
				parts_per_strip: 1,
				no_of_strips: 1,
				finished_part_code: finishedPart,
				net_weight_per_part_kg: 5.785,
				end_pieces: [
					{
						doctype: "Layout End Piece",
						width_mm: 500,
						length_mm: 1000,
						disposition: "Reuse",
						used_for_finished_part: finishedPart,
						child_layout: childCode,
						bom_quantity: 1,
						net_weight_per_part_kg: 3.93,
					},
				],
			},
		});
	});

	beforeEach(() => {
		cy.login();
	});

	it("cascades cancel to the child layout and deactivates all BOMs", { retries: 0 }, () => {
		releaseLayout(childCode);
		releaseLayout(parentCode);

		// Supersede the parent: cancel via the Actions menu.
		cy.visit(`/app/sheet-cutting-layout/${parentCode}`);
		runWorkflowAction("Supersede");
		cy.get("body").then(($body) => {
			if ($body.find('button:contains("Cancel")').length) {
				cy.contains("button", "Cancel").click({ force: true });
				cy.get("body").then(($confirm) => {
					if ($confirm.find(".modal:visible").length) {
						cy.get(".modal:visible").within(() => {
							cy.contains("button", "Yes").click();
						});
					}
				});
			}
		});

		// Child layout is cancelled.
		cy.request(
			"GET",
			`/api/method/frappe.client.get?doctype=Sheet%20Cutting%20Layout&name=${childCode}`
		).then(({ body }) => {
			expect(body.message.docstatus).to.equal(2);
		});

		// Every BOM referencing either layout is inactive.
		[parentCode, childCode].forEach((layoutCode) => {
			cy.request(
				"GET",
				`/api/method/frappe.client.get_list?doctype=BOM&filters=${encodeURIComponent(
					JSON.stringify([["sheet_cutting_layout", "=", layoutCode]])
				)}&fields=${encodeURIComponent(JSON.stringify(["name", "is_active"]))}`
			).then(({ body }) => {
				(body.message || []).forEach((bom) => {
					expect(Boolean(bom.is_active)).to.equal(false);
				});
			});
		});
	});
});
```

- [ ] Run it and see it FAIL (or confirm it exercises the path). From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-ui-tests sheet_cutting_layout --headless --spec cypress/integration/sheet_cutting_layout_recursive_end_piece.js`
  Expected: if the cascade wiring from Tasks 1-7 is merged on the same branch, this passes; if run
  before the controller/cascade edits are migrated, it FAILS at the child-`docstatus`/BOM-inactive
  assertions. Confirm the failure is a real assertion (cascade not applied), not a fixture insert error.

- [ ] If the spec fails on a fixture (e.g. consumption imbalance on insert), adjust the net weights so
  parent and child balance against their sheets exactly as in Task 7 (sheet 15.72 kg, end piece
  7.86 kg → parent gross_per_part 7.86, net 5.785). Re-run the single spec.

- [ ] Run the spec and see it PASS. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-ui-tests sheet_cutting_layout --headless --spec cypress/integration/sheet_cutting_layout_recursive_end_piece.js`
  Expected: 1 passing spec.

- [ ] Run the full UI suite to confirm no regression. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-ui-tests sheet_cutting_layout --headless`
  Expected: all specs pass.

- [ ] Commit:
  `git add cypress/integration/sheet_cutting_layout_recursive_end_piece.js && git commit -m "$(printf 'test: e2e recursive end-piece cascade cancel and BOM retirement\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"`

---

### Task 9: §9.5 decision — keep the simple end-piece BOM path; document the boundary

**Files:**
- Modify: `docs/superpowers/specs/2026-06-13-sheet-cutting-layout-iatf-export-lhrh-recursion-design.md` (§13 Open items — resolve the recursion open item)
- No test (docs-only).

§9.5 asks whether `end_piece_bom_service` (the simple complex-reuse path) is superseded by child
layouts. The build above keeps **both**: rows **without** `child_layout` keep the simple item+BOM path
(unchanged, fully tested); rows **with** `child_layout` route their BOM to the child. They never
overlap because Task 5 filters child-owned rows out of `_reuse_end_pieces`. Record this decision so the
open item is closed.

- [ ] Implement: resolve the open item. In `docs/superpowers/specs/2026-06-13-sheet-cutting-layout-iatf-export-lhrh-recursion-design.md`, change the §13 bullet:

```
- During Phase 3: whether `end_piece_bom_service` complex-reuse path is superseded by child layouts.
```

  to:

```
- ~~During Phase 3: whether `end_piece_bom_service` complex-reuse path is superseded by child
  layouts.~~ **Resolved (Phase 3):** keep both. End-piece rows without `child_layout` use the simple
  `end_piece_bom_service` item+BOM path unchanged; rows with `child_layout` route the real BOM to the
  child layout and are excluded from `_reuse_end_pieces`. The two paths are mutually exclusive per row,
  so neither is deprecated.
```

- [ ] Verify the doc still renders (no broken markdown). From `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `python -c "p='docs/superpowers/specs/2026-06-13-sheet-cutting-layout-iatf-export-lhrh-recursion-design.md'; t=open(p).read(); assert 'Resolved (Phase 3)' in t; print('ok')"`
  Expected: prints `ok`.

- [ ] Commit:
  `git add docs/superpowers/specs/2026-06-13-sheet-cutting-layout-iatf-export-lhrh-recursion-design.md && git commit -m "$(printf 'docs: resolve Phase 3 open item on simple vs child-layout end-piece BOMs\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"`

---

## Final verification

- [ ] Full Python suite green. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-tests --app sheet_cutting_layout`
  Expected: entire suite OK, coverage ≥ 96% (per `docs/development-philosophy.md`).

- [ ] Full E2E suite green. From `/Users/gurudattkulkarni/Workspace/bench15`:
  `bench --site development.localhost run-ui-tests sheet_cutting_layout --headless`
  Expected: all specs pass.

- [ ] Lint + format gates. From `/Users/gurudattkulkarni/Workspace/sheet_cutting_layout`:
  `python -m ruff check . && python -m ruff format --check .`
  Expected: no errors.
