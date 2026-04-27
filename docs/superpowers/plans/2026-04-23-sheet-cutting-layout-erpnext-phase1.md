# Sheet Cutting Layout ERPNext Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-ready ERPNext module for sheet cutting layouts with approval workflow, dynamic canvas preview, strict validations, revisioning, and automatic BOM generation on MR release.

**Architecture:** Implement as a single custom Frappe app (`sheet_cutting_layout`) with normalized DocTypes, workflow-gated release orchestration, and backend services for validation/BOM/versioning. Use form-driven Canvas 2D rendering for CAD-like live feedback. Keep release actions atomic and auditable, with explicit impact resolution for open manufacturing documents.

**Tech Stack:** Frappe/ERPNext, Python 3, JavaScript (Canvas 2D), pytest, Hypothesis

---

## Scope Check

The approved spec is cohesive for one subsystem (`Sheet Cutting Layout` module) and can be implemented in a single phased plan. No additional decomposition is required before execution.

## File Structure

### App and module files

- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/hooks.py`
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/fixtures/workflow.json`
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/fixtures/custom_field.json`
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/public/js/sheet_layout_canvas.js`

### Parent doctype

- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json`
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`

### Child doctypes

- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/layout_finished_part/layout_finished_part.json`
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/layout_approval_snapshot/layout_approval_snapshot.json`
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/layout_impact_resolution/layout_impact_resolution.json`

### Services

- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/services/validators.py`
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/services/versioning.py`
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/services/bom_service.py`
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/services/release_service.py`

### Tests

- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_validators.py`
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_bom_service.py`
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_release_service.py`
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_property_layout_invariants.py`
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_model_workflow_state_machine.py`

### Docs

- Modify: `apps/sheet_cutting_layout/README.md`

## Task 1: Bootstrap App Skeleton and Fixtures Registration

**Files:**
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/hooks.py`
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/fixtures/workflow.json`
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/fixtures/custom_field.json`
- Test: `apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Write the failing test**

```python
def test_hooks_exposes_required_fixtures():
    from sheet_cutting_layout import hooks
    assert "Workflow" in hooks.fixtures[0]["dt"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/sheet_cutting_layout && pytest sheet_cutting_layout/tests/test_release_service.py::test_hooks_exposes_required_fixtures -v`  
Expected: FAIL with `ImportError` or missing fixture entry.

- [ ] **Step 3: Write minimal implementation**

```python
# hooks.py
fixtures = [
    {"dt": "Workflow", "filters": [["name", "=", "Sheet Cutting Layout Approval Workflow"]]},
    {"dt": "Custom Field", "filters": [["dt", "in", ["BOM", "Work Order", "Production Plan"]]]},
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/sheet_cutting_layout && pytest sheet_cutting_layout/tests/test_release_service.py::test_hooks_exposes_required_fixtures -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/sheet_cutting_layout/sheet_cutting_layout/hooks.py \
        apps/sheet_cutting_layout/sheet_cutting_layout/fixtures/workflow.json \
        apps/sheet_cutting_layout/sheet_cutting_layout/fixtures/custom_field.json \
        apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_release_service.py
git commit -m "chore: register workflow and custom field fixtures"
```

## Task 2: Build Parent and Child DocTypes (Normalized Model)

**Files:**
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json`
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/layout_finished_part/layout_finished_part.json`
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/layout_approval_snapshot/layout_approval_snapshot.json`
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/layout_impact_resolution/layout_impact_resolution.json`
- Test: `apps/sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`

- [ ] **Step 1: Write the failing test**

```python
def test_sheet_cutting_layout_doctype_has_finished_part_and_end_piece_tables():
    meta = frappe.get_meta("Sheet Cutting Layout")
    fields = {d.fieldname for d in meta.fields}
    assert "finished_parts" in fields
    assert "end_pieces" in fields
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/sheet_cutting_layout && pytest sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py::test_sheet_cutting_layout_doctype_has_finished_part_and_end_piece_tables -v`  
Expected: FAIL because DocType does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Define DocType JSONs with required fields from spec:
- Parent tables: `finished_parts`, `end_pieces`, `approval_snapshot`, `impact_resolutions`
- Parent core fields: `layout_code`, `layout_family`, `revision_no`, `raw_material_item`, sheet/strip metrics, status fields
- Finished part child: `finished_part_item`, `parts_per_sheet`, `gross_weight_per_part_kg`, `scrap_weight_per_part_kg`, `generated_bom`
- End piece child (dynamic rows): `end_piece_item`, `weight_kg`, `qty_per_sheet`, `disposition`, `used_for_finished_part`

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/sheet_cutting_layout && bench --site test_site migrate && pytest sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype
git commit -m "feat: add sheet cutting layout doctypes and child tables"
```

## Task 3: Implement Core Validations on Save

**Files:**
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/services/validators.py`
- Modify: `apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`
- Test: `apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_validators.py`

- [ ] **Step 1: Write the failing test**

```python
def test_finished_part_item_must_end_with_shr_and_be_alnum():
    from sheet_cutting_layout.services.validators import validate_finished_part_code
    with pytest.raises(frappe.ValidationError):
        validate_finished_part_code("AB-12SHR")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/sheet_cutting_layout && pytest sheet_cutting_layout/tests/test_validators.py::test_finished_part_item_must_end_with_shr_and_be_alnum -v`  
Expected: FAIL because validator function is missing.

- [ ] **Step 3: Write minimal implementation**

```python
import re
import frappe

ALNUM_RE = re.compile(r"^[A-Za-z0-9]+$")

def validate_finished_part_code(code: str) -> None:
    if not code.endswith("SHR"):
        frappe.throw("Finished part item code must end with SHR")
    if not ALNUM_RE.fullmatch(code):
        frappe.throw("Finished part item code must be alphanumeric only")
```

Wire save-time checks for:
- at least one finished part row
- `scrap_weight_per_part_kg >= 0`
- derived FG non-negative after distributed end-piece deduction

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/sheet_cutting_layout && pytest sheet_cutting_layout/tests/test_validators.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/sheet_cutting_layout/sheet_cutting_layout/services/validators.py \
        apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py \
        apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_validators.py
git commit -m "feat: enforce finished part and scrap validation rules"
```

## Task 4: Configure Approval Workflow with Parallel Checker Gate

**Files:**
- Modify: `apps/sheet_cutting_layout/sheet_cutting_layout/fixtures/workflow.json`
- Modify: `apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`
- Test: `apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_model_workflow_state_machine.py`

- [ ] **Step 1: Write the failing test**

```python
def test_release_blocked_until_both_parallel_checkers_approve():
    machine = LayoutWorkflowModel()
    machine.project_manager_approves()
    with pytest.raises(AssertionError):
        machine.release()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/sheet_cutting_layout && pytest sheet_cutting_layout/tests/test_model_workflow_state_machine.py::test_release_blocked_until_both_parallel_checkers_approve -v`  
Expected: FAIL since workflow model and transitions are missing.

- [ ] **Step 3: Write minimal implementation**

Implement workflow states and role transitions:
- `Draft -> Submitted for Check`
- parallel flags `project_manager_ok` + `manufacturing_manager_ok`
- only when both true move to `Checked`
- `Checked -> Approved by Purchase -> Release Pending Impact/Released`

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/sheet_cutting_layout && bench --site test_site migrate && pytest sheet_cutting_layout/tests/test_model_workflow_state_machine.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/sheet_cutting_layout/sheet_cutting_layout/fixtures/workflow.json \
        apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py \
        apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_model_workflow_state_machine.py
git commit -m "feat: add approval workflow with parallel checker gate"
```

## Task 5: Implement BOM Mapping Service (Qty=1, Kg-only Logic)

**Files:**
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/services/bom_service.py`
- Test: `apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_bom_service.py`

- [ ] **Step 1: Write the failing test**

```python
def test_generated_bom_uses_quantity_one_and_gross_as_raw_qty():
    bom_doc = build_bom_from_layout_row(layout_doc, row)
    assert bom_doc.quantity == 1
    assert bom_doc.items[0].qty == row.gross_weight_per_part_kg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/sheet_cutting_layout && pytest sheet_cutting_layout/tests/test_bom_service.py::test_generated_bom_uses_quantity_one_and_gross_as_raw_qty -v`  
Expected: FAIL because service is missing.

- [ ] **Step 3: Write minimal implementation**

```python
def end_piece_per_part_kg(ep_weight_kg, qty_per_sheet, parts_per_sheet):
    return (ep_weight_kg * qty_per_sheet) / parts_per_sheet

def build_bom_from_layout_row(layout_doc, finished_part_row):
    bom = frappe.new_doc("BOM")
    bom.item = finished_part_row.finished_part_item
    bom.quantity = 1
    bom.append("items", {
        "item_code": layout_doc.raw_material_item,
        "qty": finished_part_row.gross_weight_per_part_kg,
        "uom": "Kg",
    })
    return bom
```

Add scrap rows:
- process scrap from `scrap_weight_per_part_kg`
- end-piece distributed Kg rows

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/sheet_cutting_layout && pytest sheet_cutting_layout/tests/test_bom_service.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/sheet_cutting_layout/sheet_cutting_layout/services/bom_service.py \
        apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_bom_service.py
git commit -m "feat: implement qty-1 bom mapping with distributed scrap"
```

## Task 6: Implement Release Orchestration and Impact Resolution

**Files:**
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/services/release_service.py`
- Modify: `apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`
- Test: `apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Write the failing test**

```python
def test_release_creates_impact_rows_when_open_docs_exist():
    result = release_layout(layout_name)
    assert result.status == "Release Pending Impact"
    assert len(result.impact_rows) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/sheet_cutting_layout && pytest sheet_cutting_layout/tests/test_release_service.py::test_release_creates_impact_rows_when_open_docs_exist -v`  
Expected: FAIL because release service is missing.

- [ ] **Step 3: Write minimal implementation**

Implement:
- find impacted open docs (`Work Order`, `Production Plan`)
- create `Layout Impact Resolution` rows
- if unresolved rows exist, set status `Release Pending Impact`
- only finalize release when all decisions present

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/sheet_cutting_layout && pytest sheet_cutting_layout/tests/test_release_service.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/sheet_cutting_layout/sheet_cutting_layout/services/release_service.py \
        apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py \
        apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_release_service.py
git commit -m "feat: add release orchestration with per-document impact handling"
```

## Task 7: Implement Revision and Supersede Service

**Files:**
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/services/versioning.py`
- Modify: `apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`
- Test: `apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Write the failing test**

```python
def test_revising_released_layout_clones_and_increments_revision():
    new_doc = create_revision(old_doc.name)
    assert new_doc.revision_no == old_doc.revision_no + 1
    assert new_doc.status == "Draft"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/sheet_cutting_layout && pytest sheet_cutting_layout/tests/test_release_service.py::test_revising_released_layout_clones_and_increments_revision -v`  
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Implement:
- clone released record to new draft
- reset approval snapshot rows
- keep only one active layout in family on successful release
- disable superseded BOMs linked to same family finished-part items

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/sheet_cutting_layout && pytest sheet_cutting_layout/tests/test_release_service.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/sheet_cutting_layout/sheet_cutting_layout/services/versioning.py \
        apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py \
        apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_release_service.py
git commit -m "feat: add layout revision and supersede lifecycle"
```

## Task 8: Build Form Script and Canvas 2D Preview

**Files:**
- Create: `apps/sheet_cutting_layout/sheet_cutting_layout/public/js/sheet_layout_canvas.js`
- Modify: `apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`
- Test: `apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_property_layout_invariants.py`

- [ ] **Step 1: Write the failing test**

```python
def test_canvas_payload_builder_returns_end_piece_zones_for_all_rows():
    payload = build_canvas_payload(layout_doc)
    assert len(payload["end_piece_zones"]) == len(layout_doc.end_pieces)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/sheet_cutting_layout && pytest sheet_cutting_layout/tests/test_property_layout_invariants.py::test_canvas_payload_builder_returns_end_piece_zones_for_all_rows -v`  
Expected: FAIL because payload builder is missing.

- [ ] **Step 3: Write minimal implementation**

Implement:
- `build_canvas_payload` server/helper
- JS renderer with debounced redraw (`200ms`)
- pseudo-3D base sheet (top plane + right side shade)
- strip/part/end-piece overlays from payload
- inline invalid marker render for failed fields

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/sheet_cutting_layout && pytest sheet_cutting_layout/tests/test_property_layout_invariants.py::test_canvas_payload_builder_returns_end_piece_zones_for_all_rows -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/sheet_cutting_layout/sheet_cutting_layout/public/js/sheet_layout_canvas.js \
        apps/sheet_cutting_layout/sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js \
        apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_property_layout_invariants.py
git commit -m "feat: add form-driven pseudo-3d canvas preview"
```

## Task 9: Add Property-Based Tests for Invariants

**Files:**
- Modify: `apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_property_layout_invariants.py`

- [ ] **Step 1: Write the failing test**

```python
@given(layout_case_strategy())
def test_bom_invariants_hold_for_random_valid_layouts(layout_case):
    result = simulate_bom(layout_case)
    assert result["bom_qty"] == 1
    assert result["raw_qty"] == layout_case.gross_weight_per_part_kg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/sheet_cutting_layout && pytest sheet_cutting_layout/tests/test_property_layout_invariants.py::test_bom_invariants_hold_for_random_valid_layouts -v`  
Expected: FAIL until strategy/simulator are complete.

- [ ] **Step 3: Write minimal implementation**

Implement Hypothesis strategies for:
- valid finished part codes (`[A-Za-z0-9]+SHR`)
- non-negative weights
- positive `parts_per_sheet`
- dynamic end-piece row counts

Assertions:
- qty always `1`
- raw qty == gross
- scrap total == process + distributed end-piece
- derived FG non-negative for accepted inputs

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/sheet_cutting_layout && pytest sheet_cutting_layout/tests/test_property_layout_invariants.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_property_layout_invariants.py
git commit -m "test: add property-based invariant coverage for bom mapping"
```

## Task 10: Add Model-Based Workflow State Machine Tests

**Files:**
- Modify: `apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_model_workflow_state_machine.py`

- [ ] **Step 1: Write the failing test**

```python
def test_state_machine_never_reaches_released_without_purchase_and_mr():
    machine = WorkflowStateMachine.TestCase()
    machine.runTest()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/sheet_cutting_layout && pytest sheet_cutting_layout/tests/test_model_workflow_state_machine.py::test_state_machine_never_reaches_released_without_purchase_and_mr -v`  
Expected: FAIL until state model is complete.

- [ ] **Step 3: Write minimal implementation**

Implement Hypothesis stateful model with transitions:
- submit
- checker approvals (parallel)
- purchase approval
- MR release
- reject
- revise

Invariants:
- invalid transitions rejected
- release side effects only after valid path
- single active version guarantee

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/sheet_cutting_layout && pytest sheet_cutting_layout/tests/test_model_workflow_state_machine.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_model_workflow_state_machine.py
git commit -m "test: add model-based workflow state machine tests"
```

## Task 11: End-to-End Release Flow Integration Tests

**Files:**
- Modify: `apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Write the failing test**

```python
def test_release_generates_two_boms_for_lh_rh_and_supersedes_old():
    result = release_layout(layout_name)
    assert len(result.generated_boms) == 2
    assert result.superseded_layout is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/sheet_cutting_layout && pytest sheet_cutting_layout/tests/test_release_service.py::test_release_generates_two_boms_for_lh_rh_and_supersedes_old -v`  
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Complete wiring:
- orchestrator calls validators -> BOM service -> versioning -> impact checks
- status transitions: `Approved by Purchase -> Release Pending Impact/Released`
- link generated BOMs back to finished-part rows

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/sheet_cutting_layout && pytest sheet_cutting_layout/tests/test_release_service.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_release_service.py \
        apps/sheet_cutting_layout/sheet_cutting_layout/services/release_service.py \
        apps/sheet_cutting_layout/sheet_cutting_layout/services/bom_service.py \
        apps/sheet_cutting_layout/sheet_cutting_layout/services/versioning.py
git commit -m "feat: complete release orchestration and integration coverage"
```

## Task 12: Documentation and Operational Runbook

**Files:**
- Modify: `apps/sheet_cutting_layout/README.md`

- [ ] **Step 1: Write the failing test**

```python
def test_readme_mentions_release_gate_and_bom_qty_one():
    content = Path("apps/sheet_cutting_layout/README.md").read_text()
    assert "BOM quantity is always 1" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/sheet_cutting_layout && pytest sheet_cutting_layout/tests/test_release_service.py::test_readme_mentions_release_gate_and_bom_qty_one -v`  
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Document:
- role matrix
- workflow transitions
- validation rules
- BOM mapping formulas
- impact resolution procedure
- rollback/recovery guidance

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/sheet_cutting_layout && pytest sheet_cutting_layout/tests/test_release_service.py::test_readme_mentions_release_gate_and_bom_qty_one -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/sheet_cutting_layout/README.md \
        apps/sheet_cutting_layout/sheet_cutting_layout/tests/test_release_service.py
git commit -m "docs: add sheet cutting layout operational runbook"
```

## Final Verification Checklist

- [ ] Run all tests:

```bash
cd apps/sheet_cutting_layout
pytest sheet_cutting_layout/tests -v
```

- [ ] Run targeted performance sanity:

```bash
pytest sheet_cutting_layout/tests/test_property_layout_invariants.py -k "canvas or redraw" -v
```

- [ ] Export fixtures after workflow/custom field changes:

```bash
bench --site <site> export-fixtures
```

- [ ] Smoke test in UI:
1. Create draft layout with 2 finished parts and 3 end-piece rows.
2. Verify live canvas updates.
3. Complete approvals.
4. Resolve impact prompts.
5. Release and verify BOMs (`qty=1`) + old revision superseded.

