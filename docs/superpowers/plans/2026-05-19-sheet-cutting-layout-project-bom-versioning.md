# Sheet Cutting Layout Project BOM Versioning Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Sheet Cutting Layout release create one native ERPNext BOM linked to the layout, version layouts by Project, allow submitted superseding, and handle endpiece scrap disposition correctly.

**Architecture:** Keep the domain rules in `services/validators.py`, BOM construction in `services/bom_service.py`, release persistence in `services/release_service.py`, and revision copying in `services/versioning.py`. Frappe DocType JSON and controller JS only expose the data model and user actions; they should delegate server-side behavior to whitelisted controller methods.

**Tech Stack:** Frappe/ERPNext v15 DocTypes, Workflow, Python services, pytest, Cypress, vanilla Frappe form JS.

---

## File Structure

- Modify `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json`: add `project`, remove `layout_family`, add `based_on_layout` if missing, keep submitted workflow fields updateable.
- Modify `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`: add whitelisted new-version method and keep release workflow side effects.
- Modify `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`: add `New Version` button for Released/Superseded layouts.
- Modify `sheet_cutting_layout/services/validators.py`: enforce exactly one finished part row and preserve complete sheet consumption validation.
- Modify `sheet_cutting_layout/services/bom_service.py`: one BOM per layout; scrap-disposition endpieces are folded into process scrap per part, reusable endpieces remain distinct scrap rows.
- Modify `sheet_cutting_layout/services/release_service.py`: create/persist native ERPNext Shearing BOM, link BOM to finished part child row, use `BOM.sheet_cutting_layout` as the parent-layout link of record, supersede same-project active layout/BOMs, save submitted old layouts safely.
- Add or modify a BOM override module, for example `sheet_cutting_layout/overrides/bom.py`: block manual ERPNext BOM creation/versioning when `custom_operation = "Shearing"` and the BOM is not linked to a Sheet Cutting Layout.
- Modify `sheet_cutting_layout/hooks.py`: register BOM document event validation for the Shearing BOM restriction.
- Modify fixtures/custom fields: ensure BOM has `custom_operation`, and add a read-only `sheet_cutting_layout` Link field on BOM with options `Sheet Cutting Layout` and `no_copy: 1`.
- Modify `sheet_cutting_layout/services/versioning.py`: replace `layout_family` grouping with `project`, copy project into revisions, increment `revision_no`.
- Update tests in `sheet_cutting_layout/tests/test_validators.py`, `test_bom_service.py`, `test_release_service.py`, `test_model_workflow_state_machine.py`, and `sheet_cutting_layout/.../test_sheet_cutting_layout.py`.
- Update Cypress specs under `cypress/integration/` to use `project` instead of `layout_family` and assert new version behavior.

---

## Chunk 1: Project-Based Data Model

### Task 1: Replace Layout Family With Project Field

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json`
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`

- [ ] **Step 1: Write failing DocType test**

Add a test asserting:
```python
def test_sheet_cutting_layout_uses_project_as_version_group() -> None:
    parent = load_doctype("sheet_cutting_layout", "sheet_cutting_layout")
    fields = fields_by_name(parent)

    assert fields["project"]["fieldtype"] == "Link"
    assert fields["project"]["options"] == "Project"
    assert fields["project"]["reqd"] == 1
    assert fields["based_on_layout"]["fieldtype"] == "Link"
    assert fields["based_on_layout"]["options"] == "Sheet Cutting Layout"
    assert fields["based_on_layout"]["read_only"] == 1
    assert "layout_family" not in fields
```

- [ ] **Step 2: Run test to verify RED**

Run:
```bash
pytest -q sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py -k project_as_version_group
```
Expected: FAIL because `project` does not exist.

- [ ] **Step 3: Update DocType JSON**

Add `project` after `layout_code`:
```json
{
  "fieldname": "project",
  "fieldtype": "Link",
  "in_list_view": 1,
  "label": "Project",
  "options": "Project",
  "reqd": 1
}
```

Add `based_on_layout` if missing:
```json
{
  "fieldname": "based_on_layout",
  "fieldtype": "Link",
  "label": "Based On Layout",
  "options": "Sheet Cutting Layout",
  "read_only": 1
}
```

Remove `layout_family` from both `field_order` and `fields`. This app is still under development, so no compatibility fallback or backfill is required.

- [ ] **Step 4: Run test to verify GREEN**

Run the same pytest command. Expected: PASS.

---

## Chunk 2: One Finished Part Rule

### Task 2: Enforce Exactly One Finished Part

**Files:**
- Modify: `sheet_cutting_layout/services/validators.py`
- Modify: `sheet_cutting_layout/tests/test_validators.py`

- [ ] **Step 1: Write failing validation tests**

Add tests:
```python
def test_layout_requires_exactly_one_finished_part() -> None:
    with pytest.raises(frappe.ValidationError, match="exactly one finished part"):
        validate_sheet_cutting_layout(Layout(finished_parts=[]))

    with pytest.raises(frappe.ValidationError, match="exactly one finished part"):
        validate_sheet_cutting_layout(Layout(finished_parts=[FinishedPart("A001SHR"), FinishedPart("A002SHR")]))
```

- [ ] **Step 2: Run RED**

Run:
```bash
pytest -q sheet_cutting_layout/tests/test_validators.py -k exactly_one_finished_part
```
Expected: FAIL.

- [ ] **Step 3: Implement validator**

After filtering accounted finished parts:
```python
if len(accounted_finished_parts) != 1:
    frappe.throw("Sheet Cutting Layout requires exactly one finished part")
```

- [ ] **Step 4: Run GREEN**

Run targeted validator tests. Expected: PASS.

- [ ] **Step 5: Update existing tests**

Update any multi-finished-part tests to either expect validation failure or move to unit-only versioning tests that bypass layout validation intentionally.

---

## Chunk 3: BOM Composition And Native ERPNext Persistence

### Frappe Behavior Checklist

- Submitted old Sheet Cutting Layout documents must be superseded with `db_set()` or another Frappe-safe submitted-document update path for fields marked `allow_on_submit`.
- Native ERPNext BOM duplicate, amend, and New Version paths must not create or preserve a Shearing BOM source link outside Sheet Cutting Layout release.
- BOM custom field `sheet_cutting_layout` must be `no_copy: 1` so ERPNext BOM New Version or Duplicate cannot accidentally copy the source link.
- Child rows copied into a new Sheet Cutting Layout revision must get fresh names and parent metadata.
- Workflow `Released` must set `docstatus = 1`; `Superseded` must remain reachable for submitted documents through explicit submitted-document persistence.

### Task 3: Endpiece Scrap Disposition Rule

**Files:**
- Modify: `sheet_cutting_layout/services/bom_service.py`
- Modify: `sheet_cutting_layout/tests/test_bom_service.py`

- [ ] **Step 1: Write failing BOM tests**

Add tests for:
- `disposition="Scrap"` endpiece is not added as an endpiece scrap row.
- Its total weight is added to process scrap total.
- `disposition="Reuse"` endpiece remains a distinct `end_piece_scrap` row.

Example:
```python
def test_scrap_endpiece_weight_is_folded_into_process_scrap_total() -> None:
    layout = Layout(end_pieces=[EndPiece("EP-SCRAP", 8, 1, disposition="Scrap")])
    part = FinishedPart(parts_per_sheet=4, scrap_weight_per_part_kg=1)

    bom = build_bom_from_layout_row(layout, part)

    assert [(r.item_code, r.qty, r.row_type) for r in bom.scrap_items] == [
        ("PROCESS-SCRAP", 12, "process_scrap")
    ]
```

- [ ] **Step 2: Run RED**

Run:
```bash
pytest -q sheet_cutting_layout/tests/test_bom_service.py -k endpiece
```
Expected: FAIL.

- [ ] **Step 3: Implement rule**

In `build_bom_from_layout_row()`:
- Calculate `scrap_endpiece_weight = sum(weight_kg * qty_per_sheet for disposition == "Scrap")`.
- Process scrap total = `part.scrap_weight_per_part_kg * parts_per_sheet + scrap_endpiece_weight`.
- Append process scrap row if total > 0.
- Append separate endpiece rows only for non-scrap dispositions that must be tracked separately, primarily `Reuse`.

- [ ] **Step 4: Run GREEN**

Run targeted BOM tests. Expected: PASS.

### Task 4: Restrict Manual Shearing BOM Creation

**Files:**
- Create or modify: `sheet_cutting_layout/overrides/bom.py`
- Modify: `sheet_cutting_layout/hooks.py`
- Modify: `sheet_cutting_layout/fixtures/custom_field.json`
- Modify: `sheet_cutting_layout/tests/test_release_service.py` or create `sheet_cutting_layout/tests/test_bom_overrides.py`

- [ ] **Step 1: Write failing BOM restriction tests**

Add tests for the override function:
```python
def test_manual_shearing_bom_requires_sheet_cutting_layout_link() -> None:
    bom = type("BOM", (), {
        "custom_operation": "Shearing",
        "sheet_cutting_layout": None,
        "flags": type("Flags", (), {})(),
    })()

    with pytest.raises(frappe.ValidationError, match="Create a Sheet Cutting Layout"):
        validate_shearing_bom_source(bom, None)


def test_generated_shearing_bom_with_layout_link_is_allowed() -> None:
    bom = type("BOM", (), {
        "custom_operation": "Shearing",
        "sheet_cutting_layout": "SCL-001",
        "flags": type("Flags", (), {})(),
    })()

    validate_shearing_bom_source(bom, None)


def test_non_shearing_bom_is_unaffected() -> None:
    bom = type("BOM", (), {
        "custom_operation": "Machining",
        "sheet_cutting_layout": None,
        "flags": type("Flags", (), {})(),
    })()

    validate_shearing_bom_source(bom, None)
```

- [ ] **Step 2: Run RED**

Run:
```bash
pytest -q sheet_cutting_layout/tests/test_bom_overrides.py
```
Expected: FAIL because the override module/function does not exist.

- [ ] **Step 3: Add BOM custom field fixtures**

Ensure BOM has:
- `custom_operation`: Data or Select field used by this app to identify `Shearing` BOMs. Add the fixture if the app does not already own it.
- `sheet_cutting_layout`: Link to `Sheet Cutting Layout`, read-only, hidden, and `no_copy: 1`.

Do not rely on a site-only custom field that is absent from fixtures; tests and migrations must install both fields consistently.

- [ ] **Step 4: Implement override function**

Create:
```python
def validate_shearing_bom_source(doc: object, method: str | None = None) -> None:
    if getattr(doc, "custom_operation", None) != "Shearing":
        return
    if getattr(doc, "sheet_cutting_layout", None):
        return
    frappe.throw("Create a Sheet Cutting Layout to generate a Shearing BOM.")
```

Do not add hidden bypass flags unless native ERPNext insert requires a temporary flag before the link field can be set. Prefer setting the link before `insert()`.

Explicitly account for native BOM copy/version paths:
- The `sheet_cutting_layout` custom field must be `no_copy: 1`, so copied/new-version BOMs do not inherit the layout link.
- A manually duplicated or ERPNext New Version Shearing BOM must fail validation unless it was generated through Sheet Cutting Layout release and linked before insert.
- Add tests that duplicate or copy a Shearing BOM with `custom_operation = "Shearing"` and verify validation fails when `sheet_cutting_layout` is blank.

- [ ] **Step 5: Register hook**

In `hooks.py`:
```python
doc_events = {
    "BOM": {
        "validate": "sheet_cutting_layout.overrides.bom.validate_shearing_bom_source",
    }
}
```

If existing `doc_events` exists, merge instead of replacing.

- [ ] **Step 6: Run GREEN**

Run:
```bash
pytest -q sheet_cutting_layout/tests/test_bom_overrides.py
pytest -q sheet_cutting_layout/tests/test_release_service.py -k hooks
```
Expected: PASS.

### Task 5: Persist Native ERPNext Shearing BOM Correctly

**Files:**
- Modify: `sheet_cutting_layout/services/release_service.py`
- Modify: `sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Write failing native BOM persistence test**

Stub `frappe.new_doc("BOM")` and verify:
- `item` is finished part item.
- `quantity` is parts per sheet.
- `custom_operation` is `Shearing`.
- `sheet_cutting_layout` is the source layout name.
- `items` contains raw material item with qty in kg.
- `scrap_items` contains process scrap and reusable endpieces.
- inserted BOM name is written to `finished_part.generated_bom`.
- No separate parent layout BOM field is required; `BOM.sheet_cutting_layout` is the canonical parent-layout link and `finished_part.generated_bom` is the row-level reverse link.

- [ ] **Step 2: Run RED**

Run:
```bash
pytest -q sheet_cutting_layout/tests/test_release_service.py -k native_bom
```
Expected: FAIL until persistence shape matches.

- [ ] **Step 3: Implement minimal persistence**

Keep `_insert_frappe_bom()` as the only Frappe persistence boundary. Set mandatory ERPNext BOM fields and Shearing ownership before insert:
```python
bom_doc.item = bom.item
bom_doc.company = get_default_company()
bom_doc.quantity = bom.quantity
bom_doc.uom = "Kg"
bom_doc.is_active = 1
bom_doc.is_default = 1
bom_doc.custom_operation = "Shearing"
bom_doc.sheet_cutting_layout = getattr(bom, "sheet_cutting_layout", None) or getattr(bom, "_layout", None).name
```

Ensure BOM rows use ERPNext field names:
```python
bom_doc.append("items", {"item_code": row.item_code, "qty": row.qty, "uom": row.uom})
bom_doc.append("scrap_items", {"item_code": row.item_code, "stock_qty": row.qty, "qty": row.qty, "uom": row.uom})
```

Add an integration test or bench smoke command on both bench15 and bench16 that inserts a real ERPNext BOM through release, not only a stubbed document, so site-specific ERPNext required fields are caught.

- [ ] **Step 4: Run GREEN**

Run targeted release tests. Expected: PASS.

---

## Chunk 4: Project-Based Versioning And Supersede

### Task 6: Versioning Uses Project

**Files:**
- Modify: `sheet_cutting_layout/services/versioning.py`
- Modify: `sheet_cutting_layout/services/release_service.py`
- Modify: `sheet_cutting_layout/tests/test_release_service.py`
- Modify: `sheet_cutting_layout/tests/test_model_workflow_state_machine.py`

- [ ] **Step 1: Write failing tests**

Test:
- `create_revision()` copies `project`.
- `finalize_new_revision_release()` supersedes only previous active released layouts with the same `project`.
- Different project layouts remain active.

- [ ] **Step 2: Run RED**

Run:
```bash
pytest -q sheet_cutting_layout/tests/test_release_service.py -k project
```
Expected: FAIL because logic has not been changed to use `project`.

- [ ] **Step 3: Replace grouping logic**

Use `project` in:
- `versioning.RevisionLayoutDocument`
- `_is_previous_active_released_layout()`
- `release_service._is_previous_layout()`
- `release_service._is_superseded_previous_layout()`
- `release_service._get_same_family_layouts()` renamed to `_get_same_project_layouts()` and changed to query `filters={"project": project}`.

Add a test that stubs `frappe.get_all()` or uses a real test site to prove release-context discovery queries by Project, not only in-memory release behavior.

- [ ] **Step 4: Run GREEN**

Run release/versioning tests. Expected: PASS.

### Task 7: Submitted Supersede Persistence

**Files:**
- Modify: `sheet_cutting_layout/services/release_service.py`
- Modify: `sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Keep existing submitted-layout regression**

Ensure test `test_release_supersedes_submitted_layouts_with_db_set` still passes.

- [ ] **Step 2: Confirm workflow metadata**

Ensure `status` and `is_active` in `sheet_cutting_layout.json` have `allow_on_submit: 1`.

- [ ] **Step 3: Constrain superseded BOM updates**

When a new Project revision is released, disable only generated Shearing BOMs linked to old Sheet Cutting Layouts in the same Project. Do not disable:
- same-item non-Shearing BOMs,
- unrelated Shearing BOMs not linked to the old Sheet Cutting Layout,
- Shearing BOMs linked to a different Project's layout.

Add tests for each unaffected case.

- [ ] **Step 4: Run targeted tests**

Run:
```bash
pytest -q sheet_cutting_layout/tests/test_release_service.py -k supersedes_submitted_layouts_with_db_set
pytest -q sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py -k submitted_workflow_fields
```

---

## Chunk 5: New Version Button And Server Method

### Task 8: Whitelisted New Version Method

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.py`
- Modify: `sheet_cutting_layout/tests/test_release_service.py`

- [ ] **Step 1: Write failing controller test**

Test a function such as:
```python
create_sheet_cutting_layout_revision("SCL-001")
```
It should:
- Load old doc.
- Call `create_revision(old_doc)`.
- Insert new doc.
- Return new doc name.

- [ ] **Step 2: Run RED**

Run:
```bash
pytest -q sheet_cutting_layout/tests/test_release_service.py -k create_sheet_cutting_layout_revision
```
Expected: FAIL because method does not exist.

- [ ] **Step 3: Implement method**

Use `@frappe.whitelist()`. Do not bypass permission except where Frappe’s insert path already checks create permission. Keep behavior explicit:
```python
old_doc = frappe.get_doc("Sheet Cutting Layout", name)
new_doc = create_revision(old_doc)
new_doc.insert()
return new_doc.name
```

`create_revision()` must use `frappe.copy_doc(old_doc)` or explicitly normalize the copied document before insert. It must reset `name`, child row names, child parent metadata, `docstatus`, workflow fields, approval snapshots, generated BOM links, release metadata, and any old generated document references.

- [ ] **Step 4: Run GREEN**

Run targeted test. Expected: PASS.

### Task 9: Client New Version Button

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`

- [ ] **Step 1: Write failing JS structure test**

Assert JS includes:
- `frm.add_custom_button(__("New Version")`
- status guard for `Released` and `Superseded`
- `frappe.call` to the whitelisted revision method
- route to new form.

- [ ] **Step 2: Run RED**

Run:
```bash
pytest -q sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py -k new_version_button
```

- [ ] **Step 3: Implement client button**

In `refresh(frm)`:
```javascript
if (!frm.is_new() && ["Released", "Superseded"].includes(frm.doc.status)) {
  frm.add_custom_button(__("New Version"), () => {
    frappe.call({
      method: "sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.sheet_cutting_layout.create_sheet_cutting_layout_revision",
      args: { name: frm.doc.name },
      callback: (r) => {
        if (r.message) frappe.set_route("Form", "Sheet Cutting Layout", r.message);
      },
    });
  });
}
```

- [ ] **Step 4: Run GREEN**

Run targeted JS structure test. Expected: PASS.

---

## Chunk 6: Browser E2E Coverage

### Task 10: Cypress Project-Based Release Flow

**Files:**
- Modify: `cypress/integration/sheet_cutting_layout_release.js`
- Modify: `cypress/integration/sheet_cutting_layout_consumption.js`

- [ ] **Step 1: Replace `layout_family` setup with Project setup**

Use backend prerequisite API only to create Project and Item records.

- [ ] **Step 2: Add New Version flow**

E2E should:
- Create layout with one finished part.
- Drive workflow to MR Release.
- Assert status `Released`.
- Assert generated BOM link exists.
- Click `New Version`.
- Assert new doc has same project, `revision_no + 1`, status `Draft`, empty generated BOM.

- [ ] **Step 3: Assert Supersede behavior**

Release the new version, then assert old layout is `Superseded` and new layout is `Released`.

- [ ] **Step 4: Assert browser-visible BOM composition**

Open generated BOM and assert:
- BOM item equals finished part item.
- BOM quantity equals parts per sheet.
- `custom_operation` is `Shearing`.
- `sheet_cutting_layout` points to the released Sheet Cutting Layout.
- raw material qty equals sheet weight.
- scrap table includes process scrap total and reusable endpieces.
- scrap-disposition endpieces are included in process scrap total, not as separate endpiece row.

- [ ] **Step 5: Assert manual Shearing BOM is blocked**

Use browser flow or backend API:
- Create/open a new ERPNext BOM manually.
- Set `custom_operation = Shearing`.
- Leave `sheet_cutting_layout` blank.
- Save must fail with `Create a Sheet Cutting Layout to generate a Shearing BOM.`
- Repeat with a non-Shearing operation and verify normal BOM behavior is not blocked.

- [ ] **Step 6: Run bench15 Cypress/UI test**

Run from `/Users/gurudattkulkarni/Workspace/bench15`:
```bash
bench --site development.localhost run-ui-tests sheet_cutting_layout --headless
```
Expected: PASS on bench15.

- [ ] **Step 7: Run bench16 Cypress/UI test**

Run from `/Users/gurudattkulkarni/Workspace/bench16` against site `frappe16.localhost`:
```bash
bench --site frappe16.localhost run-ui-tests sheet_cutting_layout --headless
```
Expected: PASS on bench16.

---

## Chunk 7: Bench Migration And Final Verification

### Task 11: Migrate Local Benches

**Files:** no code files; runtime verification.

- [ ] **Step 1: Migrate bench15**

Run:
```bash
cd /Users/gurudattkulkarni/Workspace/bench15
bench --site development.localhost migrate
bench --site development.localhost clear-cache
```

- [ ] **Step 2: Migrate bench16**

Run from `/Users/gurudattkulkarni/Workspace/bench16`:
```bash
bench --site frappe16.localhost migrate
bench --site frappe16.localhost clear-cache
```

- [ ] **Step 3: Smoke check metadata**

Use bench execute or UI to confirm:
- `project` field exists and is required.
- `layout_family` no longer exists on the DocType.
- `status` and `is_active` allow submit updates.
- BOM has `sheet_cutting_layout` custom field.
- Manual BOM with `custom_operation = Shearing` and no source layout is blocked.

### Task 12: Full Verification

- [ ] **Step 1: Run Python tests**

```bash
pytest -q sheet_cutting_layout/tests sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py
```
Expected: all pass.

- [ ] **Step 2: Run syntax checks**

```bash
python -m py_compile sheet_cutting_layout/services/bom_service.py sheet_cutting_layout/services/release_service.py sheet_cutting_layout/services/versioning.py sheet_cutting_layout/services/validators.py
python -m py_compile sheet_cutting_layout/overrides/bom.py
node --check sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js
python -m json.tool sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.json >/tmp/scl_doctype.json.check
```

- [ ] **Step 3: Run bench UI tests**

From bench15:
```bash
bench --site development.localhost run-ui-tests sheet_cutting_layout --headless
```
From bench16:
```bash
bench --site frappe16.localhost run-ui-tests sheet_cutting_layout --headless
```
Expected: UI tests pass on both benches.

- [ ] **Step 4: Real BOM insert smoke on both benches**

Run a bench execute or targeted workflow smoke on bench15 and bench16 that releases a Sheet Cutting Layout and confirms a native ERPNext BOM is inserted with required site fields populated. Expected output:
- Released layout name.
- Generated BOM name.
- BOM `item`, `quantity`, `custom_operation`, and `sheet_cutting_layout`.
- Raw material row qty in kg equals sheet weight.
- Scrap rows equal process scrap plus reusable endpieces.

- [ ] **Step 5: Manual bench15 spot check**

In `http://localhost:8002`:
- Open a released layout.
- Confirm `New Version` button appears.
- Create new version.
- Release it.
- Confirm old layout becomes `Superseded`.
- Confirm native BOM exists and is linked.

---

## Commit Plan

- [ ] Commit 1: `feat: add project-based sheet layout grouping`
- [ ] Commit 2: `feat: enforce single finished part layouts`
- [ ] Commit 3: `feat: create native bom from sheet release`
- [ ] Commit 4: `feat: restrict manual shearing bom creation`
- [ ] Commit 5: `feat: add sheet layout new version flow`
- [ ] Commit 6: `test: cover project release and versioning flows`

## Risks And Trade-Offs

- Requiring exactly one finished part simplifies BOM correctness but forces LH/RH or multi-output layouts into separate layout documents.
- Removing `layout_family` outright is acceptable because this app is still under development. The trade-off is any local draft data using `layout_family` must be recreated or manually corrected.
- Native ERPNext BOM validation may require additional mandatory ERPNext fields depending on site configuration; keep `_insert_frappe_bom()` as the single place to adapt those fields.
- Blocking manual `custom_operation = "Shearing"` BOMs preserves Sheet Cutting Layout as the single source of truth. The trade-off is users cannot use ERPNext BOM New Version for Shearing BOMs; they must create a new Sheet Cutting Layout version.
- Non-Shearing BOMs must remain untouched by the override. Keep the validation condition narrow and test it explicitly.
