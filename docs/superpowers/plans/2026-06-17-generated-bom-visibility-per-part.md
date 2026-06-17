# Generated-BOM Visibility Per Part Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show each generated BOM on the Sheet Cutting Layout form — a new read-only `twin_generated_bom` field for the LH/RH twin part, and the existing end-piece BOM link — each visible only once its BOM exists.

**Architecture:** Add one new parent Link→BOM field (`twin_generated_bom`) populated during release symmetrically with the existing primary `generated_bom`; gate the already-populated, currently-hidden child field `generated_end_piece_bom` so it appears once set. Pure schema + a two-line release-service addition; no change to BOM generation, the `finished_parts` mirror, or the IATF export.

**Tech Stack:** Frappe v15 / ERPNext (Python services + DocType JSON), bench-native `FrappeTestCase`, Cypress E2E.

**Spec:** `docs/superpowers/specs/2026-06-17-generated-bom-visibility-per-part-design.md`

**Test commands (bench-native):**
- LH/RH module: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_lh_rh_release`
- End-piece visibility module: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_visibility`
- E2E: `bench --site development.localhost run-ui-tests sheet_cutting_layout --headless --spec cypress/integration/sheet_cutting_layout_lh_rh.js`

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json` | Add `twin_generated_bom` field + field_order entry | **Modify** (Task 1) |
| `sheet_cutting_layout/services/release_service.py` | Populate `twin_generated_bom` on release | **Modify** (Task 2) |
| `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json` | Un-hide + gate `generated_end_piece_bom` | **Modify** (Task 3) |
| `sheet_cutting_layout/tests/test_lh_rh_release.py` | Twin field schema + release-population tests | **Modify** (Tasks 1, 2) |
| `sheet_cutting_layout/tests/test_end_piece_bom_visibility.py` | End-piece field visibility test | **Create** (Task 3) |
| `cypress/integration/sheet_cutting_layout_lh_rh.js` | E2E: assert twin BOM populated after release | **Modify** (Task 4) |

---

## Task 1: Add `twin_generated_bom` field to Sheet Cutting Layout

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json`
- Test: `sheet_cutting_layout/tests/test_lh_rh_release.py` (extend `TestLhRhSchema`)

- [ ] **Step 1: Write the failing test** — add this method to the existing `TestLhRhSchema` class in `sheet_cutting_layout/tests/test_lh_rh_release.py` (after `test_finished_part_orientation_field_exists`):

```python
	def test_twin_generated_bom_field_exists_and_is_gated(self) -> None:
		field = frappe.get_meta("Sheet Cutting Layout").get_field("twin_generated_bom")
		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "BOM")
		self.assertEqual(field.read_only, 1)
		self.assertEqual(field.depends_on, "eval:doc.twin_generated_bom")
```

- [ ] **Step 2: Run the test and verify it FAILS**

Run: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_lh_rh_release`
Expected: FAIL — `AttributeError: 'NoneType' object has no attribute 'fieldtype'` (field not defined yet).

- [ ] **Step 3: Add the field to the doctype JSON.** In `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json`, add this object to the `fields` array immediately after the existing `generated_bom` field object:

```json
		{
			"depends_on": "eval:doc.twin_generated_bom",
			"fieldname": "twin_generated_bom",
			"fieldtype": "Link",
			"label": "Twin Part BOM",
			"no_copy": 1,
			"options": "BOM",
			"read_only": 1
		},
```

- [ ] **Step 4: Add it to `field_order`.** In the same file, in the `field_order` array, insert `"twin_generated_bom"` immediately after `"generated_bom"`:

```json
		"generated_bom",
		"twin_generated_bom",
		"workflow_section",
```

- [ ] **Step 5: Sync the schema to the site so meta reflects the new field**

Run: `bench --site development.localhost migrate`
Expected: completes without error (it picks up the changed doctype JSON).

- [ ] **Step 6: Run the test and verify it PASSES**

Run: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_lh_rh_release`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json sheet_cutting_layout/tests/test_lh_rh_release.py
git commit -m "feat: add gated twin_generated_bom field to Sheet Cutting Layout"
```

---

## Task 2: Populate `twin_generated_bom` on release

The release loop `_generate_boms` already iterates the parent finished-part rows (`[primary]`, or `[primary, twin]` when `is_lh_rh`) and writes the primary's BOM to `generated_bom` for `index == 1`. Add the symmetric write for the twin (`index == 2`). The twin row only exists when `is_lh_rh`, so a non-LH/RH release never sets it.

**Files:**
- Modify: `sheet_cutting_layout/services/release_service.py` (`_generate_boms`, the `if index == 1:` block — currently around line 258-259)
- Test: `sheet_cutting_layout/tests/test_lh_rh_release.py` (extend `TestLhRhReleaseIntegration`)

- [ ] **Step 1: Write the failing tests.** In `sheet_cutting_layout/tests/test_lh_rh_release.py`, add this assertion inside the existing `test_lh_rh_release_creates_two_boms_and_mirror_rows`, immediately after the line `self.assertEqual(layout.generated_bom, bom_names[0])`:

```python
		self.assertEqual(layout.twin_generated_bom, bom_names[1])
```

Then add this new method to the `TestLhRhReleaseIntegration` class:

```python
	def test_non_lh_rh_release_leaves_twin_generated_bom_empty(self) -> None:
		layout = make_release_ready_layout()

		layout.status = "Released"
		layout.submit()
		layout.reload()

		self.assertEqual(layout.status, "Released")
		self.assertTrue(layout.generated_bom)
		self.assertFalse(layout.twin_generated_bom)
```

- [ ] **Step 2: Run the tests and verify they FAIL**

Run: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_lh_rh_release`
Expected: `test_lh_rh_release_creates_two_boms_and_mirror_rows` FAILS — `twin_generated_bom` is empty (`None != "BOM-..."`). (`test_non_lh_rh_release_leaves_twin_generated_bom_empty` passes already, since the field is never written.)

- [ ] **Step 3: Implement the population.** In `sheet_cutting_layout/services/release_service.py`, in `_generate_boms`, change the primary-only write:

```python
		if index == 1:
			_set_frappe_field_if_supported(layout, "generated_bom", bom.name)
		generated_boms.append(bom)
```

to also write the twin's BOM:

```python
		if index == 1:
			_set_frappe_field_if_supported(layout, "generated_bom", bom.name)
		elif index == 2:
			_set_frappe_field_if_supported(layout, "twin_generated_bom", bom.name)
		generated_boms.append(bom)
```

- [ ] **Step 4: Run the tests and verify they PASS**

Run: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_lh_rh_release`
Expected: PASS (both the extended release test and the non-LH/RH test).

- [ ] **Step 5: Commit**

```bash
git add sheet_cutting_layout/services/release_service.py sheet_cutting_layout/tests/test_lh_rh_release.py
git commit -m "feat: populate twin_generated_bom from the twin part's BOM on release"
```

---

## Task 3: Un-hide and gate the end-piece BOM field

`generated_end_piece_bom` on Layout End Piece is already a read-only `Link→BOM` and is already written by `generate_end_piece_boms`. It is currently `"hidden": 1`, so it never shows. Replace the unconditional hide with a `depends_on` gate (show once populated) and make it a grid column.

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`
- Test: `sheet_cutting_layout/tests/test_end_piece_bom_visibility.py` (Create)

- [ ] **Step 1: Write the failing test.** Create `sheet_cutting_layout/tests/test_end_piece_bom_visibility.py`:

```python
from __future__ import annotations

import frappe

from sheet_cutting_layout.tests.base import SheetCuttingLayoutTestCase


class TestEndPieceBomVisibility(SheetCuttingLayoutTestCase):
	def test_generated_end_piece_bom_is_gated_not_hidden(self) -> None:
		field = frappe.get_meta("Layout End Piece").get_field("generated_end_piece_bom")
		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "BOM")
		self.assertEqual(field.read_only, 1)
		# Shown as a grid column, revealed only once the BOM is generated.
		self.assertFalse(field.hidden)
		self.assertEqual(field.in_list_view, 1)
		self.assertEqual(field.depends_on, "eval:doc.generated_end_piece_bom")
```

- [ ] **Step 2: Run the test and verify it FAILS**

Run: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_visibility`
Expected: FAIL — `field.hidden` is `1` (truthy) and `depends_on`/`in_list_view` are unset.

- [ ] **Step 3: Edit the field in the doctype JSON.** In `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`, replace the existing `generated_end_piece_bom` field object:

```json
		{
			"fieldname": "generated_end_piece_bom",
			"fieldtype": "Link",
			"hidden": 1,
			"label": "Generated End Piece BOM",
			"no_copy": 1,
			"options": "BOM",
			"read_only": 1
		}
```

with (remove `"hidden": 1`; add `depends_on` + `in_list_view`):

```json
		{
			"depends_on": "eval:doc.generated_end_piece_bom",
			"fieldname": "generated_end_piece_bom",
			"fieldtype": "Link",
			"in_list_view": 1,
			"label": "Generated End Piece BOM",
			"no_copy": 1,
			"options": "BOM",
			"read_only": 1
		}
```

- [ ] **Step 4: Sync the schema to the site**

Run: `bench --site development.localhost migrate`
Expected: completes without error.

- [ ] **Step 5: Run the test and verify it PASSES**

Run: `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_visibility`
Expected: PASS.

> **Recursive end pieces:** a reuse end piece with a `child_layout` has no simple end-piece BOM (the real BOM lives on the child layout), so `generated_end_piece_bom` stays empty for that row and the gated field simply does not show — no extra handling needed. This matches spec §6.

- [ ] **Step 6: Commit**

```bash
git add sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json sheet_cutting_layout/tests/test_end_piece_bom_visibility.py
git commit -m "feat: reveal end-piece BOM once generated instead of always hiding it"
```

---

## Task 4: E2E — assert the twin BOM is populated after release

Extend the existing LH/RH spec (which already releases an LH/RH layout via the workflow API and re-reads it) to assert `twin_generated_bom` is set to the twin part's BOM.

**Files:**
- Modify: `cypress/integration/sheet_cutting_layout_lh_rh.js` (the `releases an LH/RH layout ...` test, inside the `fetchReleasedLhRhLayout().then((layout) => { ... })` block)

- [ ] **Step 1: Add the assertion.** In `cypress/integration/sheet_cutting_layout_lh_rh.js`, inside the `fetchReleasedLhRhLayout().then((layout) => {` block, immediately after the line `expect(layout.generated_bom).to.equal(bomNames[0]);`, add:

```javascript
				// The twin part's BOM is surfaced on the parent (spec 2026-06-17).
				expect(layout.twin_generated_bom).to.equal(bomNames[1]);
```

- [ ] **Step 2: Run the E2E spec and verify it PASSES** (bench15 dev server must be running on `localhost:8002`)

Run: `bench --site development.localhost run-ui-tests sheet_cutting_layout --headless --spec cypress/integration/sheet_cutting_layout_lh_rh.js`
Expected: `2 passing` — both the toggle test and the release test (now also asserting `twin_generated_bom`).

- [ ] **Step 3: Commit**

```bash
git add cypress/integration/sheet_cutting_layout_lh_rh.js
git commit -m "test: assert twin_generated_bom is surfaced after LH/RH release (E2E)"
```

---

## Notes for the executor

- **Migrate is required** after each doctype-JSON change (Tasks 1 and 3) so `frappe.get_meta(...)` and the form reflect the new/changed fields, and so `_set_frappe_field_if_supported` recognises `twin_generated_bom` in Task 2.
- **No change** to BOM generation, the `finished_parts` mirror table, the primary `generated_bom`, the supersede/cancel BOM-gathering, or the IATF export (the new field is a display-only pointer — `no_copy: 1` means a new revision starts blank and the next release repopulates it, matching `generated_bom`).
- Keep the `finished_parts` mirror as-is; it remains the per-row BOM source and is out of scope (spec §9).
