# Sheet Cutting Layout Submitted Derived BOM Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move every BOM created from `Sheet Cutting Layout` onto a submitted lifecycle, allow `Update Cost` for layout-derived BOMs, restrict `New Version` / `Cancel` / `Amend` on layout-derived BOMs, and make supersede operate on all layout-linked BOMs with reference-update warnings when replacement BOMs do not exist.

**Architecture:** Keep the June 2 layout-owned design intact: parent fields remain the source of BOM structure, the generated BOM remains the released manufacturing artifact, and the layout save audit remains the structural drift detector. Change the BOM lifecycle only where this app owns it: submit the main shearing BOM at `MR Release`, submit all end-piece BOMs at generation time, narrow BOM override logic to the real versioning escape hatches, and extend supersede to update/deactivate every BOM linked by `sheet_cutting_layout`.

**Tech Stack:** Frappe/ERPNext 15 Python services (`release_service.py`, `end_piece_bom_service.py`, `overrides/bom.py`, `validators.py`), DocType controller hooks, bench-native `unittest` modules run through `bench --site ... run-tests`, pre-commit.

---

## Reference Documents

- Spec: `docs/superpowers/specs/2026-06-03-sheet-cutting-layout-submitted-derived-bom-lifecycle-design.md`
- Prior design still in force:
  - `docs/superpowers/specs/2026-06-02-sheet-cutting-layout-bom-reference-and-versioning-design.md`
- Core implementation files:
  - `sheet_cutting_layout/services/release_service.py`
  - `sheet_cutting_layout/services/end_piece_bom_service.py`
  - `sheet_cutting_layout/overrides/bom.py`
  - `sheet_cutting_layout/services/validators.py`
  - `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`
  - `sheet_cutting_layout/hooks.py`
- Primary tests to update:
  - `sheet_cutting_layout/tests/test_release_service.py`
  - `sheet_cutting_layout/tests/test_end_piece_bom_service.py`
  - `sheet_cutting_layout/tests/test_bom_overrides.py`
  - `sheet_cutting_layout/tests/test_validators.py`
  - `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`
- Product docs:
  - `README.md`

## File Structure

Modify:

- `sheet_cutting_layout/services/release_service.py`
  - Submit the main BOM during `MR Release`.
  - Collect all BOMs linked to a superseded layout.
  - Deactivate every linked BOM on supersede.
  - Attempt replacement BOM mapping and reference updates.
  - Produce warning data for unmatched referenced BOMs.
- `sheet_cutting_layout/services/end_piece_bom_service.py`
  - Submit each generated end-piece BOM.
  - Preserve current item-generation behavior while tightening result/error handling around submitted BOM creation.
- `sheet_cutting_layout/overrides/bom.py`
  - Replace the broad layout-derived BOM lock with narrow restrictions:
    - allow `Update Cost`
    - block `New Version`
    - block `Cancel`
    - block `Amend`
  - Leave non-layout BOMs unchanged.
- `sheet_cutting_layout/services/validators.py`
  - Keep the structural drift audit.
  - Ensure allowed cost-refresh behavior does not trip the audit.
- `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`
  - If supersede warning payloads need controller/UI surfacing, keep that wiring here and nowhere else.
- `sheet_cutting_layout/hooks.py`
  - Narrow doc-event interception only if the new BOM restriction shape requires different hook coverage.
- `README.md`
  - Update current behavior docs for submitted derived BOMs, allowed `Update Cost`, and supersede warnings.

Test modules:

- `sheet_cutting_layout/tests/test_release_service.py`
  - Main BOM submission, supersede coverage, replacement mapping, warning behavior.
- `sheet_cutting_layout/tests/test_end_piece_bom_service.py`
  - End-piece BOM submission behavior.
- `sheet_cutting_layout/tests/test_bom_overrides.py`
  - Allow `Update Cost`, block `New Version` / `Cancel` / `Amend`, keep non-layout BOMs native.
- `sheet_cutting_layout/tests/test_validators.py`
  - Save-time audit tolerates cost updates but still rejects structural drift.
- `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`
  - Controller-level supersede/release integration if warning flow or submit-time hooks need coverage.

## Chunk 1: Submit Main Layout BOMs at Release

### Task 1: Make `MR Release` create and submit the main shearing BOM

**Files:**
- Modify: `sheet_cutting_layout/tests/test_release_service.py`
- Modify: `sheet_cutting_layout/services/release_service.py`

- [ ] **Step 1: Add failing release-service tests for submitted main BOM behavior**

Add bench-native tests that describe the new contract:

```python
def test_release_submits_generated_main_bom(self):
    layout = make_releasable_layout()
    fake_bom_doc = FakeFrappeBomDoc()
    install_frappe_bom_stub(fake_bom_doc)

    result = release_service.release_layout(layout)

    self.assertEqual(result.generated_boms[0].name, fake_bom_doc.name)
    self.assertEqual(fake_bom_doc.insert_calls, 1)
    self.assertEqual(fake_bom_doc.submit_calls, 1)
    self.assertEqual(layout.generated_bom, fake_bom_doc.name)
```

```python
def test_release_fails_when_generated_main_bom_submit_fails(self):
    layout = make_releasable_layout()
    fake_bom_doc = FakeFrappeBomDoc(submit_error="submit failed")
    install_frappe_bom_stub(fake_bom_doc)

    with self.assertRaisesRegex(Exception, "submit failed"):
        release_service.release_layout(layout)
```

- [ ] **Step 2: Run the focused release-service module and confirm failure**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
```

Expected: failure because release still inserts draft BOMs only.

- [ ] **Step 3: Change `release_service.py` to submit the generated main BOM**

Update the BOM persistence flow so:

1. `_insert_frappe_bom()` inserts the BOM.
1. The same flow then submits it before returning success.
1. The app-controlled flag is present for both insert and submit phases.
1. The returned in-memory BOM state reflects the submitted BOM.
1. No partially-created draft BOM is reported as a successful released BOM.

- [ ] **Step 4: Re-run the release-service module and confirm pass**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
```

Expected: the new submission tests pass; other supersede/override failures may remain for later chunks.

- [ ] **Step 5: Commit the release submission change**

```bash
git add \
  sheet_cutting_layout/services/release_service.py \
  sheet_cutting_layout/tests/test_release_service.py
git commit -m "feat: submit generated main layout boms"
```

## Chunk 2: Submit End-Piece BOMs at Generation Time

### Task 2: Make generated end-piece BOMs insert and submit immediately

**Files:**
- Modify: `sheet_cutting_layout/tests/test_end_piece_bom_service.py`
- Modify: `sheet_cutting_layout/services/end_piece_bom_service.py`

- [ ] **Step 1: Add failing end-piece BOM generation tests**

Add tests like:

```python
def test_generation_submits_end_piece_bom(self):
    layout = make_released_layout_with_reuse_end_piece()
    fake_bom_doc = FakeFrappeBomDoc()
    install_end_piece_generation_frappe_stub(fake_bom_doc)

    result = service.generate_end_piece_boms(layout)

    self.assertEqual(fake_bom_doc.insert_calls, 1)
    self.assertEqual(fake_bom_doc.submit_calls, 1)
    self.assertEqual(result["boms"], [fake_bom_doc.name])
```

```python
def test_generation_raises_when_end_piece_bom_submit_fails(self):
    layout = make_released_layout_with_reuse_end_piece()
    fake_bom_doc = FakeFrappeBomDoc(submit_error="submit failed")
    install_end_piece_generation_frappe_stub(fake_bom_doc)

    with self.assertRaisesRegex(Exception, "submit failed"):
        service.generate_end_piece_boms(layout)
```

- [ ] **Step 2: Run the focused end-piece BOM module and confirm failure**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
```

Expected: failure because end-piece BOMs are inserted but not submitted.

- [ ] **Step 3: Change `end_piece_bom_service.py` to submit generated end-piece BOMs**

Update `_create_end_piece_bom()` so:

1. Generated BOMs are inserted.
1. The same flow submits them immediately.
1. The app-controlled flag covers both insert and submit.
1. `end_piece_item_code` persistence remains unchanged.
1. Errors from submit abort generation cleanly and do not leave a false success result.

- [ ] **Step 4: Re-run the focused module and confirm pass**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
```

Expected: end-piece BOM generation now passes with submitted BOM behavior.

- [ ] **Step 5: Commit the end-piece submission change**

```bash
git add \
  sheet_cutting_layout/services/end_piece_bom_service.py \
  sheet_cutting_layout/tests/test_end_piece_bom_service.py
git commit -m "feat: submit generated end piece boms"
```

## Chunk 3: Narrow Layout-Derived BOM Restrictions

### Task 3: Allow `Update Cost` and block only layout-versioning escape hatches

**Files:**
- Modify: `sheet_cutting_layout/tests/test_bom_overrides.py`
- Modify: `sheet_cutting_layout/overrides/bom.py`
- Modify: `sheet_cutting_layout/hooks.py`

- [ ] **Step 1: Add failing override tests for the new restriction model**

Add tests that pin the allowed and blocked paths:

```python
def test_update_cost_is_allowed_for_layout_derived_bom(self):
    bom = fake_layout_derived_bom(method="update_cost")
    bom_overrides.validate_shearing_bom_source(bom, "update_cost")
```

```python
def test_new_version_is_blocked_for_layout_derived_bom(self):
    bom = fake_layout_derived_bom(method="before_insert", is_new=True)
    with self.assertRaisesRegex(frappe.ValidationError, "Sheet Cutting Layout version"):
        bom_overrides.validate_shearing_bom_source(bom, "before_insert")
```

```python
def test_cancel_is_blocked_for_layout_derived_bom(self):
    bom = fake_layout_derived_bom(method="before_cancel")
    with self.assertRaisesRegex(frappe.ValidationError, "Sheet Cutting Layout version"):
        bom_overrides.validate_shearing_bom_source(bom, "before_cancel")
```

```python
def test_non_layout_bom_keeps_native_behavior(self):
    bom = fake_non_layout_bom()
    bom_overrides.validate_shearing_bom_source(bom, "validate")
```

- [ ] **Step 2: Run the override module and confirm failure**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_overrides
```

Expected: failure because the current override is still a broad lock on layout-derived shearing BOMs.

- [ ] **Step 3: Refactor `overrides/bom.py` and hook coverage**

Implement the narrow rule set:

1. Allow `Update Cost` for layout-derived BOMs.
1. Block `New Version` for layout-derived BOMs.
1. Block `Cancel` for layout-derived BOMs.
1. Block `Amend` for layout-derived BOMs.
1. Leave non-layout BOMs untouched.
1. Reduce hook interception to the minimal event coverage needed for those paths.

- [ ] **Step 4: Re-run the override module and confirm pass**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_overrides
```

Expected: override behavior matches the approved narrow restriction model.

- [ ] **Step 5: Commit the BOM override narrowing**

```bash
git add \
  sheet_cutting_layout/overrides/bom.py \
  sheet_cutting_layout/hooks.py \
  sheet_cutting_layout/tests/test_bom_overrides.py
git commit -m "feat: narrow derived bom restrictions"
```

## Chunk 4: Preserve Structural Drift Audit but Allow Cost Refresh

### Task 4: Keep save-time audit strict on structure and tolerant on cost updates

**Files:**
- Modify: `sheet_cutting_layout/tests/test_validators.py`
- Modify: `sheet_cutting_layout/services/validators.py`

- [ ] **Step 1: Add failing validator tests for cost-refresh tolerance**

Add tests such as:

```python
def test_generated_bom_audit_ignores_allowed_cost_field_changes(self):
    layout = make_layout_with_generated_bom()
    bom = fake_generated_bom_with_same_structure_different_costs()
    install_generated_bom_lookup(bom)

    validators.validate_sheet_cutting_layout(layout)
```

```python
def test_generated_bom_audit_still_rejects_quantity_drift(self):
    layout = make_layout_with_generated_bom()
    bom = fake_generated_bom(quantity=layout.no_of_strips + 1)
    install_generated_bom_lookup(bom)

    with self.assertRaisesRegex(frappe.ValidationError, "BOM quantity mismatch"):
        validators.validate_sheet_cutting_layout(layout)
```

- [ ] **Step 2: Run the validator module and confirm failure**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
```

Expected: failure if the current audit path still trips on allowed cost-maintenance effects.

- [ ] **Step 3: Tighten the audit to compare only layout-owned structural fields**

In `validators.py`:

1. Keep checks for item, quantity, raw-material rows, scrap rows, and consumption balance.
1. Ignore cost-only differences introduced by `Update Cost`.
1. Keep error messages specific to structural drift.

- [ ] **Step 4: Re-run the validator module and confirm pass**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
```

Expected: cost refresh no longer fails audit; structural drift still does.

- [ ] **Step 5: Commit the audit refinement**

```bash
git add \
  sheet_cutting_layout/services/validators.py \
  sheet_cutting_layout/tests/test_validators.py
git commit -m "fix: allow cost refresh in layout bom audit"
```

## Chunk 5: Supersede All Layout-Linked BOMs and Report Unmatched References

### Task 5: Extend supersede to cover all layout-linked BOMs, replacement updates, and warnings

**Files:**
- Modify: `sheet_cutting_layout/tests/test_release_service.py`
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`
- Modify: `sheet_cutting_layout/services/release_service.py`
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`

- [ ] **Step 1: Add failing supersede tests for replacement updates and warnings**

Add coverage like:

```python
def test_supersede_deactivates_all_boms_linked_to_layout(self):
    old_layout = make_released_layout_with_main_and_end_piece_boms()
    replacement_layout = make_released_replacement_layout()
    install_bom_lookup_and_reference_fakes(old_layout, replacement_layout)

    warning = release_service.deactivate_generated_bom(old_layout, replacement_layout=replacement_layout)

    self.assertEqual(deactivated_bom_names(), {"BOM-MAIN-OLD", "BOM-EP-OLD"})
```

```python
def test_supersede_updates_references_when_replacement_bom_exists(self):
    old_layout = make_released_layout_with_referenced_end_piece_bom()
    replacement_layout = make_released_replacement_layout_with_matching_end_piece_bom()
    install_reference_update_fakes(old_layout, replacement_layout)

    release_service.deactivate_generated_bom(old_layout, replacement_layout=replacement_layout)

    self.assertEqual(updated_references(), [("BOM-EP-OLD", "BOM-EP-NEW")])
```

```python
def test_supersede_warns_when_old_referenced_bom_has_no_replacement(self):
    old_layout = make_released_layout_with_referenced_end_piece_bom()
    replacement_layout = make_released_replacement_layout_with_scrap_end_piece()
    install_reference_update_fakes(old_layout, replacement_layout)

    warning = release_service.deactivate_generated_bom(old_layout, replacement_layout=replacement_layout)

    self.assertIn("BOM-EP-OLD", warning["unmatched_boms"])
    self.assertIn("BOM-PARENT-001", warning["referencing_boms"]["BOM-EP-OLD"])
```

- [ ] **Step 2: Run the release/controller modules and confirm failure**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout
```

Expected: failure because supersede still deactivates only the parent-linked BOM and does not yet collect warnings.

- [ ] **Step 3: Implement supersede-all and warning behavior**

In `release_service.py` and, only if necessary, the controller:

1. Discover all BOMs linked by `sheet_cutting_layout = layout.name`.
1. Require a released replacement layout input for supersede.
1. Map old derived BOMs to replacement derived BOMs.
1. Update references where a valid replacement exists.
1. Deactivate all old linked BOMs.
1. Return structured warning data for unmatched referenced old BOMs.
1. Keep the warning informational, not blocking.

- [ ] **Step 4: Re-run the release/controller modules and confirm pass**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout
```

Expected: supersede now deactivates all layout-linked BOMs and reports unmatched references without blocking completion.

- [ ] **Step 5: Commit the supersede extension**

```bash
git add \
  sheet_cutting_layout/services/release_service.py \
  sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py \
  sheet_cutting_layout/tests/test_release_service.py \
  sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py
git commit -m "feat: extend supersede across layout boms"
```

## Chunk 6: Product Docs and Full Verification

### Task 6: Update docs and run the full app verification set

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update current product docs**

Update `README.md` to reflect:

1. main and end-piece BOMs are submitted immediately
1. `Update Cost` is allowed on layout-derived BOMs
1. `New Version` / `Cancel` / `Amend` are layout-owned restrictions
1. supersede acts on all layout-linked BOMs and can report unmatched-reference warnings

- [ ] **Step 2: Run full bench-native app tests on the primary site**

Run:

```bash
bench --site development.localhost migrate
bench --site development.localhost run-tests --app sheet_cutting_layout
```

Expected: all app tests pass on `development.localhost`.

- [ ] **Step 3: Run full bench-native app tests on the secondary site**

Run:

```bash
bench --site frappe16.localhost migrate
bench --site frappe16.localhost run-tests --app sheet_cutting_layout
```

Expected: all app tests pass on `frappe16.localhost`.

- [ ] **Step 4: Run repository checks**

Run:

```bash
pre-commit run --all-files
```

Expected: all hooks pass.

- [ ] **Step 5: Commit docs/test stabilization**

```bash
git add README.md
git commit -m "docs: describe submitted derived bom lifecycle"
```

## Completion Checklist

- [ ] Main shearing BOMs are inserted and submitted during `MR Release`.
- [ ] Generated end-piece BOMs are inserted and submitted during `Generate End Piece BOMs`.
- [ ] Layout-derived BOMs allow `Update Cost`.
- [ ] Layout-derived BOMs block `New Version`, `Cancel`, and `Amend`.
- [ ] Non-layout BOMs behave as native ERPNext BOMs.
- [ ] Save-time layout audit still catches structural drift and ignores cost-only refresh.
- [ ] Supersede deactivates all BOMs linked to the layout.
- [ ] Supersede updates references where replacement BOMs exist.
- [ ] Supersede warns on referenced old BOMs that have no replacement target.
- [ ] `bench --site development.localhost run-tests --app sheet_cutting_layout` passes.
- [ ] `bench --site frappe16.localhost run-tests --app sheet_cutting_layout` passes.
- [ ] `pre-commit run --all-files` passes.
