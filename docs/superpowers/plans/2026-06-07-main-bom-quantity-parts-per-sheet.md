# Main BOM Quantity Uses Parts Per Sheet Implementation Plan

> **For agentic workers:** REQUIRED: Use `superpowers:subagent-driven-development` (if subagents are available) or `superpowers:executing-plans` to implement this plan. Steps use checkbox syntax and should be updated as work completes.

**Goal:** Change the main BOM created from `Sheet Cutting Layout` so its quantity equals
`parts_per_sheet` instead of `no_of_strips`, remove `qty_per_sheet` from active end-piece logic,
and perform one-time local cleanup for affected released layouts/BOMs on bench15.

**Architecture:** Keep the existing parent-driven layout model, released submitted BOM lifecycle, and
BOM-backed `finished_parts` projection. Only the main BOM quantity rule changes. End-piece BOM
quantity remains row-driven. `qty_per_sheet` becomes hidden dead data at the DocType layer and is
ignored by client/server logic. Existing released layout/BOM pairs created under the old strip-count
rule are corrected locally after the code change, then resynchronized through the BOM-backed
projection path.

**Tech Stack:** Frappe/ERPNext 15 app code in `sheet_cutting_layout/services`, DocType JSON and JS,
bench-native unittest modules run through `bench --site ... run-tests`, and direct local bench15
cleanup after code changes.

---

## Reference Documents

- Approved spec:
  - `docs/superpowers/specs/2026-06-07-main-bom-quantity-parts-per-sheet-design.md`
- Earlier designs still in force for adjacent behavior:
  - `docs/superpowers/specs/2026-06-02-sheet-cutting-layout-bom-reference-and-versioning-design.md`
  - `docs/superpowers/specs/2026-06-03-sheet-cutting-layout-submitted-derived-bom-lifecycle-design.md`
- Core implementation files:
  - `sheet_cutting_layout/services/bom_service.py`
  - `sheet_cutting_layout/services/release_service.py`
  - `sheet_cutting_layout/services/validators.py`
  - `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`
  - `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`
  - `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json`
- Primary tests to update:
  - `sheet_cutting_layout/tests/test_bom_service.py`
  - `sheet_cutting_layout/tests/test_validators.py`
  - `sheet_cutting_layout/tests/test_release_service.py`
  - `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`

## File Structure

Modify:

- `sheet_cutting_layout/services/bom_service.py`
  - switch main BOM quantity from `no_of_strips` to `parts_per_sheet`
  - keep end-piece BOM quantity behavior unchanged
- `sheet_cutting_layout/services/release_service.py`
  - keep BOM-backed finished-part projection aligned with the new quantity
  - expose or reuse a sync path for local cleanup if needed
- `sheet_cutting_layout/services/validators.py`
  - expect `parts_per_sheet` in save-time BOM audit
  - ignore `qty_per_sheet` in active logic
  - block unreleased legacy layouts that still use `qty_per_sheet > 1`
- `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`
  - make `qty_per_sheet` hidden and non-required
- `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`
  - remove any client dependency on `qty_per_sheet`
- `README.md`
  - update the current main BOM quantity statement

Optional helper if needed:

- add a narrow local cleanup helper under `scripts/` or a bench-executable developer-only path
  only if that is the clearest way to resync released bench15 data

## Chunk 1: Change Main BOM Quantity Rule

### Task 1: Make the main BOM quantity equal `parts_per_sheet`

**Files:**
- Modify: `sheet_cutting_layout/tests/test_bom_service.py`
- Modify: `sheet_cutting_layout/services/bom_service.py`

- [ ] **Step 1: Add failing BOM-service tests for main BOM quantity**

Add or update tests that assert:

```python
def test_generated_bom_uses_parts_per_sheet_quantity() -> None:
    layout = Layout(no_of_strips=11, parts_per_sheet=77)
    bom = bom_service.build_bom_from_layout_row(layout, FinishedPart(parts_per_sheet=77))
    assert bom.quantity == 77
```

Also keep or add a test that end-piece BOM quantity remains row-driven elsewhere and is unaffected.

- [ ] **Step 2: Run the focused BOM-service module and confirm failure**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_service
```

Expected: failure because the current code still uses `no_of_strips`.

- [ ] **Step 3: Update `bom_service.py`**

Change the main BOM quantity helper so:

1. parent finished-part BOM quantity uses `parts_per_sheet`
2. end-piece BOM quantity behavior stays unchanged
3. any helper that derives expected BOM consumption from the layout reflects the new quantity rule

- [ ] **Step 4: Re-run the focused BOM-service module and confirm pass**

Run the same module again. Expect the quantity tests to pass.

- [ ] **Step 5: Commit the quantity-rule change**

```bash
git add \
  sheet_cutting_layout/services/bom_service.py \
  sheet_cutting_layout/tests/test_bom_service.py
git commit -m "feat: use parts per sheet for main bom quantity"
```

## Chunk 2: Update Audit and BOM-Backed Projection

### Task 2: Align release projection and save-time audit with `parts_per_sheet`

**Files:**
- Modify: `sheet_cutting_layout/tests/test_release_service.py`
- Modify: `sheet_cutting_layout/tests/test_validators.py`
- Modify: `sheet_cutting_layout/services/release_service.py`
- Modify: `sheet_cutting_layout/services/validators.py`

- [ ] **Step 1: Add failing release/audit tests**

Cover these behaviors:

```python
def test_release_syncs_finished_part_reference_bom_quantity_from_parts_per_sheet():
    ...
    assert layout.finished_parts[0].bom_quantity == 77
```

```python
def test_save_time_audit_rejects_legacy_strip_count_quantity():
    ...
    with pytest.raises(..., match="BOM quantity mismatch"):
        validate_sheet_cutting_layout(layout)
```

```python
def test_save_time_audit_accepts_corrected_parts_per_sheet_quantity():
    ...
```

- [ ] **Step 2: Run the focused release/validator modules and confirm failure**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
```

- [ ] **Step 3: Update projection and audit logic**

Implement:

1. `finished_parts.bom_quantity` mirrors the main BOM quantity derived from `parts_per_sheet`
2. save-time audit expects `parts_per_sheet`
3. old released BOMs with strip-count quantity fail until corrected

- [ ] **Step 4: Re-run the focused modules and confirm pass**

- [ ] **Step 5: Commit the projection/audit alignment**

```bash
git add \
  sheet_cutting_layout/services/release_service.py \
  sheet_cutting_layout/services/validators.py \
  sheet_cutting_layout/tests/test_release_service.py \
  sheet_cutting_layout/tests/test_validators.py
git commit -m "fix: align shearing bom audit with parts per sheet"
```

## Chunk 3: Remove `qty_per_sheet` From Active Logic

### Task 3: Treat `qty_per_sheet` as hidden dead data and block unreleased legacy multiplicity

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`
- Modify: `sheet_cutting_layout/services/validators.py`
- Modify: `sheet_cutting_layout/tests/test_validators.py`
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`

- [ ] **Step 1: Add failing tests for `qty_per_sheet` removal behavior**

Cover:

```python
def test_qty_per_sheet_is_not_required_for_end_piece_validation():
    ...
```

```python
def test_stale_qty_per_sheet_payload_is_ignored_for_weight_and_consumption():
    ...
```

```python
def test_unreleased_layout_with_qty_per_sheet_gt_one_is_blocked_until_rows_are_split():
    ...
```

- [ ] **Step 2: Run the focused validator/controller tests and confirm failure**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout
```

- [ ] **Step 3: Update metadata, client, and server behavior**

Implement:

1. `qty_per_sheet` becomes hidden and non-required in DocType metadata
2. client script no longer depends on `qty_per_sheet`
3. server logic ignores stale `qty_per_sheet` values
4. pre-release legacy layouts with `qty_per_sheet > 1` are blocked until split into duplicate rows

- [ ] **Step 4: Re-run focused tests and confirm pass**

- [ ] **Step 5: Commit the end-piece cleanup**

```bash
git add \
  sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json \
  sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js \
  sheet_cutting_layout/services/validators.py \
  sheet_cutting_layout/tests/test_validators.py \
  sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py
git commit -m "fix: remove qty per sheet from end piece logic"
```

## Chunk 4: Update Docs and Perform Local bench15 Cleanup

### Task 4: Correct current docs and clean affected released bench15 data

**Files:**
- Modify: `README.md`
- Optional add: developer cleanup helper if needed for repeatable local correction

- [ ] **Step 1: Update docs**

Change README to reflect:

- main BOM quantity = `parts_per_sheet`
- end-piece `qty_per_sheet` is no longer active input

- [ ] **Step 2: Identify affected bench15 released records**

Use bench15 to find released layouts where:

1. `generated_bom` is set
2. linked BOM item matches `finished_part_code`
3. linked BOM quantity equals legacy strip-count quantity rather than `parts_per_sheet`

- [ ] **Step 3: Perform one-time local correction on bench15**

For each affected record:

1. update parent generated BOM quantity to `parts_per_sheet`
2. resynchronize BOM-backed `finished_parts` projection rows from the corrected BOM
3. verify the released layout/BOM pair satisfies the new audit

For the known example:

- layout `001`
- BOM `BOM-FG01SHR-001`

expected final state:

- BOM quantity = `77`
- layout `finished_parts[0].bom_quantity = 77`

- [ ] **Step 4: Record the exact bench commands or helper used**

The final implementation notes must include the concrete developer command path used for local
cleanup verification on bench15.

- [ ] **Step 5: Commit docs and any cleanup helper**

```bash
git add README.md [optional-helper-path]
git commit -m "docs: update main bom quantity behavior"
```

## Verification

- [ ] `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_service`
- [ ] `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators`
- [ ] `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service`
- [ ] `bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout`
- [ ] `bench --site development.localhost run-tests --app sheet_cutting_layout`
- [ ] `bench --site frappe16.localhost run-tests --app sheet_cutting_layout`
- [ ] `pre-commit run --all-files`
- [ ] Bench15 local data verification for layout `001` and `BOM-FG01SHR-001`

## Completion Checklist

- [ ] Main BOM quantity uses `parts_per_sheet`
- [ ] End-piece BOM quantity still uses row-level `bom_quantity`
- [ ] `qty_per_sheet` is hidden, non-required, and ignored by active logic
- [ ] unreleased legacy layouts with `qty_per_sheet > 1` are blocked until split into duplicate rows
- [ ] save-time audit expects `parts_per_sheet`
- [ ] read-only `finished_parts.bom_quantity` mirrors corrected main BOM quantity
- [ ] bench15 released local data is corrected for affected layouts/BOMs
- [ ] full tests pass on bench15 and bench16
- [ ] pre-commit passes
