# Sheet Cutting Layout BOM Reference and Versioning Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move finished-part inputs to the parent Sheet Cutting Layout, make the child finished-parts table a BOM-backed read-only reference view, lock layout-derived BOMs against manual edits, continuously audit generated BOMs on save, and keep BOM versioning driven only by Sheet Cutting Layout `New Version` and `Supersede`.

**Architecture:** Keep the layout parent as the only editable source of finished-part design inputs and keep the main shearing BOM as the only released manufacturing source of truth. Rework validators, release/versioning services, and BOM override hooks so parent fields drive formulas and BOM creation, the `finished_parts` table becomes a synchronized projection only, and save-time audit detects drift instead of silently rewriting BOM state.

**Tech Stack:** Frappe/ERPNext 15 DocType JSON + Desk Form JS, Python service modules (`validators.py`, `bom_service.py`, `release_service.py`, `versioning.py`, `workflow.py`, `overrides/bom.py`), bench-native `unittest` tests only via `bench --site ... run-tests`, pre-commit.

---

## Reference Documents

- Spec: `docs/superpowers/specs/2026-06-02-sheet-cutting-layout-bom-reference-and-versioning-design.md`
- Parent doctype metadata:
  - `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json`
  - `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`
  - `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`
- Child doctype metadata:
  - `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_finished_part/layout_finished_part.json`
- Core services:
  - `sheet_cutting_layout/services/validators.py`
  - `sheet_cutting_layout/services/bom_service.py`
  - `sheet_cutting_layout/services/release_service.py`
  - `sheet_cutting_layout/services/versioning.py`
  - `sheet_cutting_layout/services/workflow.py`
  - `sheet_cutting_layout/overrides/bom.py`
  - `sheet_cutting_layout/hooks.py`
- Existing tests to update:
  - `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`
  - `sheet_cutting_layout/tests/test_validators.py`
  - `sheet_cutting_layout/tests/test_bom_service.py`
  - `sheet_cutting_layout/tests/test_release_service.py`
  - `sheet_cutting_layout/tests/test_model_workflow_state_machine.py`
  - `sheet_cutting_layout/tests/test_bom_overrides.py`
  - `sheet_cutting_layout/tests/test_property_layout_invariants.py`
- Current product doc to refresh:
  - `README.md`

## File Structure

Modify:

- `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json`
  - Add parent finished-part input fields and `generated_bom`.
  - Change the `finished_parts` child table from editable input to hidden-until-generated, read-only reference view.
- `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_finished_part/layout_finished_part.json`
  - Reduce the child row contract to BOM-reference columns only.
- `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`
  - Drive formulas from parent fields only.
  - Stop using child rows as calculation inputs.
  - Keep the BOM-backed child table synchronized for display only.
- `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`
  - Keep validate/release hooks thin, but add any required orchestration for save-time BOM audit or post-release synchronization.
- `sheet_cutting_layout/services/validators.py`
  - Move finished-part validation and consumption formulas to the parent layout fields.
  - Add save-time BOM audit entry points.
- `sheet_cutting_layout/services/bom_service.py`
  - Build the main shearing BOM from parent-level finished-part fields.
  - Add helper(s) to calculate expected BOM rows and totals for audit.
- `sheet_cutting_layout/services/release_service.py`
  - Generate and persist the main BOM from parent fields.
  - Write `generated_bom` back to the layout and synchronize the child reference rows.
  - Remove old behavior that deactivates previous BOMs on release.
- `sheet_cutting_layout/services/versioning.py`
  - Copy the new parent input fields into revisions.
  - Clear `approval_snapshot`, `generated_bom`, and BOM-backed child rows for the new draft.
- `sheet_cutting_layout/services/workflow.py`
  - Ensure `Supersede` remains the explicit release-lifecycle action that can drive BOM deactivation.
- `sheet_cutting_layout/overrides/bom.py`
  - Expand from “block manual shearing BOM creation without source layout” to “block manual edits and ERPNext-native versioning for any layout-derived BOM.”
- `sheet_cutting_layout/hooks.py`
  - Keep BOM override hooks aligned if additional validate/before_save/before_submit coverage is needed.
- `README.md`
  - Update the current workflow description to match parent-driven BOM generation, BOM locking, `New Version`, and `Supersede`.

Tests:

- `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`
  - End-to-end doctype behavior and UI-contract-adjacent server behavior.
- `sheet_cutting_layout/tests/test_validators.py`
  - Parent formula and consumption validation.
- `sheet_cutting_layout/tests/test_bom_service.py`
  - BOM row derivation from parent fields.
- `sheet_cutting_layout/tests/test_release_service.py`
  - MR Release, BOM creation, sync, and audit behavior.
- `sheet_cutting_layout/tests/test_model_workflow_state_machine.py`
  - `New Version` and `Supersede` behavior.
- `sheet_cutting_layout/tests/test_bom_overrides.py`
  - Locking manual BOM edits and blocking ERPNext-native versioning for layout-derived BOMs.
- `sheet_cutting_layout/tests/test_property_layout_invariants.py`
  - Do not extend this file with new pytest/hypothesis coverage.
  - Replace needed invariant coverage with bench-native tests, then delete or retire this file as part of the change.

No migration files are planned. This is an under-development app and the approved design explicitly avoids compatibility fallbacks.

## Chunk 1: Parent Inputs and Child Reference Surface

### Task 1: Add failing tests for the new doctype contract

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`
- Modify: `sheet_cutting_layout/tests/test_validators.py`

- [x] **Step 1: Add failing doctype behavior tests**

Add bench-native tests that describe the new contract:

```python
layout = make_layout(
    finished_part_code="FG01SHR",
    net_weight_per_part_kg=0.289,
    generated_bom=None,
)
layout.insert()
layout.reload()

self.assertEqual(layout.finished_part_code, "FG01SHR")
self.assertEqual(layout.net_weight_per_part_kg, 0.289)
self.assertFalse(layout.finished_parts)
```

```python
layout.parts_per_strip = 7
layout.no_of_strips = 11
layout.weight_of_strip_kg = 3.31692
layout.net_weight_per_part_kg = 0.289
layout.save()

self.assertEqual(layout.parts_per_sheet, 77)
self.assertAlmostEqual(layout.gross_weight_per_part_kg, 3.31692 / 7, places=6)
self.assertAlmostEqual(
    layout.scrap_weight_per_part_kg,
    layout.gross_weight_per_part_kg - 0.289,
    places=6,
)
```

- [x] **Step 2: Run the focused test modules and confirm failure**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
```

Expected: failures because parent fields and parent-driven formulas are not implemented yet.

- [x] **Step 3: Update parent and child DocType JSON metadata**

In `sheet_cutting_layout.json`:

1. Add parent fields:
   - `finished_part_code`
   - `net_weight_per_part_kg`
   - `generated_bom`
1. Keep `gross_weight_per_part_kg` and `scrap_weight_per_part_kg` as read-only derived parent fields.
1. Make `finished_parts` hidden until `generated_bom` exists.
1. Make `finished_parts` read-only.

In `layout_finished_part.json`:

1. Remove input-only fields from the effective child-row contract:
   - `net_weight_per_part_kg`
   - `gross_weight_per_part_kg`
   - `scrap_weight_per_part_kg`
   - row-level `generated_bom`
1. Keep only BOM-reference columns:
   - `finished_part_item`
   - `bom_quantity`
   - `scrap_weight_kg`
   - `raw_material_weight_kg`

- [x] **Step 4: Update the form script for parent-driven calculations**

In `sheet_cutting_layout.js`:

1. Stop reading `finished_parts` as the source of finished-part math.
1. Recompute:
   - `parts_per_sheet`
   - `gross_weight_per_part_kg`
   - `scrap_weight_per_part_kg`
   - consumption fields
   from parent fields only.
1. Keep `finished_parts` as display-only sync data once `generated_bom` exists.

- [x] **Step 5: Re-run the focused modules and confirm pass**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
```

Expected: the new parent-field contract passes, though release-related tests will still fail until later chunks are implemented.

- [x] **Step 6: Commit the schema/UI contract change**

```bash
git add \
  sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json \
  sheet_cutting_layout/sheet_cutting_layout/doctype/layout_finished_part/layout_finished_part.json \
  sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js \
  sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py \
  sheet_cutting_layout/tests/test_validators.py
git commit -m "feat: move finished part inputs to parent layout"
```

## Chunk 2: Parent-Driven Validation and Bench-Native Invariant Coverage

### Task 2: Refactor validators to use only parent finished-part fields

**Files:**
- Modify: `sheet_cutting_layout/services/validators.py`
- Modify: `sheet_cutting_layout/tests/test_validators.py`

- [x] **Step 1: Add failing validator tests for the parent-only model**

Add or update tests like:

```python
layout = make_layout(
    finished_part_code="FG01SHR",
    net_weight_per_part_kg=0.289,
    parts_per_strip=7,
    no_of_strips=11,
    weight_of_strip_kg=3.31692,
)
validators.validate_sheet_cutting_layout(layout)

self.assertEqual(layout.parts_per_sheet, 77)
self.assertAlmostEqual(layout.gross_weight_per_part_kg, 3.31692 / 7, places=6)
self.assertAlmostEqual(
    layout.scrap_weight_per_part_kg,
    layout.gross_weight_per_part_kg - 0.289,
    places=6,
)
```

```python
layout.net_weight_per_part_kg = layout.gross_weight_per_part_kg + 0.001
with self.assertRaisesRegex(frappe.ValidationError, "Scrap weight per part cannot be negative"):
    validators.validate_sheet_cutting_layout(layout)
```

- [x] **Step 2: Run the validator module and confirm failure**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
```

Expected: failures because validators still read child finished-part rows.

- [x] **Step 3: Refactor `validators.py`**

Implement these changes:

1. Remove authoritative dependence on `finished_parts` rows for:
   - finished-part code validation
   - net/gross/scrap validation
   - parts-per-sheet calculation
   - consumption tracking
1. Add parent-field validation for:
   - `finished_part_code`
   - `finished_part_code` must continue to satisfy the shearing suffix rule (`SHR`)
   - `net_weight_per_part_kg`
   - derived `gross_weight_per_part_kg`
   - derived `scrap_weight_per_part_kg`
1. Keep end-piece validation unchanged where still correct.
1. Keep tolerance-based sheet-consumption validation, but compute from parent fields plus end pieces only.

- [x] **Step 4: Replace pytest/hypothesis invariant coverage with bench-native coverage**

Do not extend `test_property_layout_invariants.py`.

Instead:

1. Move the useful formula and mass-balance invariants into `test_validators.py` or `test_bom_service.py`.
1. Add table-driven bench-native cases covering:
   - balanced layout with scrap end piece
   - balanced layout with reuse end piece
   - negative scrap
   - tolerance-edge values near `+0.005 / -0.005`
1. Delete `test_property_layout_invariants.py` once its useful coverage has been replaced.

- [x] **Step 5: Re-run the validator and BOM service modules and confirm pass**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_service
```

Expected: parent-driven formulas and mass-balance invariants pass without pytest or hypothesis.

- [x] **Step 6: Commit the validator and invariant-test migration**

```bash
git add \
  sheet_cutting_layout/services/validators.py \
  sheet_cutting_layout/tests/test_validators.py \
  sheet_cutting_layout/tests/test_bom_service.py \
  sheet_cutting_layout/tests/test_property_layout_invariants.py
git commit -m "refactor: move finished part validation to parent fields"
```

## Chunk 3: Main BOM Generation, Reference Sync, Audit, and Locking

### Task 3: Add failing release and BOM override tests for the new source-of-truth model

**Files:**
- Modify: `sheet_cutting_layout/tests/test_bom_service.py`
- Modify: `sheet_cutting_layout/tests/test_release_service.py`
- Modify: `sheet_cutting_layout/tests/test_bom_overrides.py`

- [x] **Step 1: Add failing BOM generation tests**

Add or update release/BOM tests such as:

```python
layout = make_layout(
    finished_part_code="FG01SHR",
    net_weight_per_part_kg=0.289,
    parts_per_strip=7,
    no_of_strips=11,
    parts_per_sheet=77,
    weight_per_sheet_kg=39.3,
    gross_weight_per_part_kg=0.473846,
    scrap_weight_per_part_kg=0.184846,
)
bom = build_bom_from_layout(layout)

self.assertEqual(bom.item, "FG01SHR")
self.assertEqual(bom.quantity, 11)
self.assertEqual(find_raw_material_qty(bom, "RM001"), 39.3)
self.assertAlmostEqual(find_total_scrap_qty(bom), expected_total_scrap, places=6)
```

Add save-time drift tests:

```python
layout = release_layout_and_reload(...)
tamper_bom_quantity(layout.generated_bom, 99)
with self.assertRaisesRegex(frappe.ValidationError, "BOM quantity mismatch"):
    layout.save()
```

Add BOM-lock tests:

```python
bom = frappe.get_doc("BOM", generated_bom_name)
bom.quantity = 99
with self.assertRaisesRegex(frappe.ValidationError, "create a new Sheet Cutting Layout version"):
    bom.save()
```

- [x] **Step 2: Run the service and override modules and confirm failure**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_overrides
```

Expected: failures because release still reads child rows and BOM override only blocks creation without a source layout.

- [x] **Step 3: Refactor `bom_service.py` for parent-driven BOM derivation**

Implement:

1. A parent-level finished-part input protocol.
1. BOM derivation from:
   - `finished_part_code`
   - `gross_weight_per_part_kg`
   - `scrap_weight_per_part_kg`
   - `parts_per_sheet`
   - `no_of_strips`
1. Helper(s) that return expected raw material rows, scrap rows, and total consumption for audit.

- [x] **Step 4: Refactor `release_service.py` for generation and sync**

Implement:

1. Generate one main shearing BOM from parent fields.
1. Persist `generated_bom` on the layout.
1. Synchronize the `finished_parts` child table from the saved BOM.
1. Remove the old behavior that deactivates earlier BOMs on release.
1. Keep the BOM active after release unless a later explicit `Supersede` deactivates it.

- [x] **Step 5: Add save-time BOM audit**

Implement audit entry points in `validators.py` and/or `release_service.py` so that:

1. Save without `generated_bom` runs normal layout validation only.
1. Save with `generated_bom` compares all derived BOM fields against layout expectations.
1. Drift throws category-specific errors instead of silently resyncing the BOM.

- [x] **Step 6: Expand BOM override locking**

In `overrides/bom.py` and `hooks.py`:

1. Keep blocking manual creation of `custom_operation = "Shearing"` BOMs without `sheet_cutting_layout`.
1. Also block manual edits to any BOM linked to `sheet_cutting_layout`.
1. Also block ERPNext-native BOM “New Version” or copy flows for layout-derived BOMs.
1. Allow app-controlled changes for:
   - initial MR Release creation
   - explicit BOM deactivation on layout supersede

- [x] **Step 7: Re-run the focused modules and confirm pass**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_overrides
```

Expected: parent-driven BOM creation, sync, audit, and lock behavior all pass.

- [x] **Step 8: Commit BOM generation and locking changes**

```bash
git add \
  sheet_cutting_layout/services/bom_service.py \
  sheet_cutting_layout/services/release_service.py \
  sheet_cutting_layout/services/validators.py \
  sheet_cutting_layout/overrides/bom.py \
  sheet_cutting_layout/hooks.py \
  sheet_cutting_layout/tests/test_bom_service.py \
  sheet_cutting_layout/tests/test_release_service.py \
  sheet_cutting_layout/tests/test_bom_overrides.py
git commit -m "feat: generate and audit layout-driven shearing BOMs"
```

## Chunk 4: Revisioning, Supersede, and Final Verification

### Task 4: Add failing revision and supersede tests

**Files:**
- Modify: `sheet_cutting_layout/tests/test_model_workflow_state_machine.py`
- Modify: `sheet_cutting_layout/tests/test_release_service.py`

- [x] **Step 1: Add failing versioning and supersede tests**

Add or update tests like:

```python
new_layout = create_revision(old_layout)

self.assertEqual(new_layout.finished_part_code, old_layout.finished_part_code)
self.assertEqual(new_layout.net_weight_per_part_kg, old_layout.net_weight_per_part_kg)
self.assertFalse(new_layout.approval_snapshot)
self.assertFalse(new_layout.generated_bom)
self.assertFalse(new_layout.finished_parts)
```

```python
released_layout = release_layout_and_reload(...)
linked_bom = frappe.get_doc("BOM", released_layout.generated_bom)

supersede_layout(released_layout)
linked_bom.reload()

self.assertFalse(linked_bom.is_active)
self.assertTrue(linked_bom.disabled)
```

Add “old BOM unchanged after new revision release” coverage:

```python
old_bom = frappe.get_doc("BOM", old_layout.generated_bom)
new_layout = create_and_release_revision(old_layout)
old_bom.reload()

self.assertEqual(old_bom.name, old_layout.generated_bom)
self.assertTrue(old_bom.is_active)
self.assertNotEqual(new_layout.generated_bom, old_bom.name)
```

- [x] **Step 2: Run the revision/workflow modules and confirm failure**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_model_workflow_state_machine
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
```

Expected: failures because revisioning still copies old child BOM linkage assumptions and release tests still reflect the older deactivation behavior.

- [x] **Step 3: Refactor `versioning.py`, `workflow.py`, and any release wiring**

Implement:

1. `create_revision()` copies parent finished-part inputs.
1. `create_revision()` clears:
   - `approval_snapshot`
   - `generated_bom`
   - BOM-backed `finished_parts` rows
1. Release of the new revision creates a new BOM without editing or deactivating the old BOM.
1. `Supersede` deactivates only the BOM linked to the superseded layout.

- [x] **Step 4: Refresh current product documentation**

Update `README.md` to describe:

1. parent-driven finished-part inputs
1. hidden/read-only BOM-backed `finished_parts`
1. layout-only change path for shearing BOMs
1. `New Version` creates the next BOM version
1. `Supersede` deactivates the linked BOM

- [x] **Step 5: Run the full app test suite on development bench**

Run:

```bash
bench --site development.localhost migrate
bench --site development.localhost run-tests --app sheet_cutting_layout
```

Expected: full suite passes with no pytest dependency added back.

- [x] **Step 6: Run the full app test suite on bench16**

Run:

```bash
bench --site frappe16.localhost migrate
bench --site frappe16.localhost run-tests --app sheet_cutting_layout
```

Expected: same behavior on the second local bench.

- [x] **Step 7: Run repository checks**

Run:

```bash
pre-commit run --all-files
```

Expected: all hooks pass.

- [x] **Step 8: Commit revisioning and doc updates**

```bash
git add \
  sheet_cutting_layout/services/versioning.py \
  sheet_cutting_layout/services/workflow.py \
  sheet_cutting_layout/tests/test_model_workflow_state_machine.py \
  sheet_cutting_layout/tests/test_release_service.py \
  README.md
git commit -m "feat: version shearing BOMs through sheet cutting layouts"
```

## Completion Checklist

- [x] Parent finished-part inputs are the only editable finished-part source on the layout.
- [x] `finished_parts` is hidden until `generated_bom` exists and then acts as a read-only BOM reference table.
- [x] Layout validation and sheet-consumption checks use parent fields plus end pieces only.
- [x] MR Release creates the main shearing BOM from parent fields and writes `generated_bom`.
- [x] Any layout-derived BOM rejects manual edits and ERPNext-native versioning.
- [x] Save-time audit fails on any derived BOM drift.
- [x] `New Version` creates a clean new draft layout revision and a new BOM on release.
- [x] `Supersede` deactivates the linked BOM and does not affect other released BOMs.
- [x] Bench-native tests pass on both local benches.
- [x] `pre-commit run --all-files` passes.
