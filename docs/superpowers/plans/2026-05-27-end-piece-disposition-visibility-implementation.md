# End Piece Disposition Visibility Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure end-piece reuse-only fields are shown only for `Reuse`, removed for `Scrap`, and always cleared/blocked when disposition is not `Reuse`.

**Architecture:** Use a hybrid approach: DocType metadata `depends_on` for UI visibility, client-side row normalization on disposition change for immediate cleanup, and validator guardrails for non-UI save paths. Keep all verification bench-native.

**Tech Stack:** Frappe/ERPNext 15 DocType JSON metadata, Desk Form JS (`frappe.ui.form.on`), Python validators, bench test runner (`bench --site ... run-tests`), pre-commit.

---

## Reference Documents

- Spec: `docs/superpowers/specs/2026-05-27-end-piece-disposition-visibility-design.md`
- Parent form script: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`
- End-piece child DocType JSON: `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`
- Validator service: `sheet_cutting_layout/services/validators.py`
- Source-contract tests: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`
- Validator tests: `sheet_cutting_layout/tests/test_validators.py`

## File Structure

Modify:

- `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`
  - Remove `Hold`.
  - Add/adjust `depends_on` rules for reuse-only/scrap-only fields.
- `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`
  - Add disposition-change normalizer to clear reuse-only fields for non-reuse rows.
- `sheet_cutting_layout/services/validators.py`
  - Add fail-fast checks for reuse-only fields when disposition is not `Reuse`.
- `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`
  - Assert updated options and `depends_on` contract.
  - Assert client script includes clear-on-non-reuse behavior.
- `sheet_cutting_layout/tests/test_validators.py`
  - Add/adjust tests for fail-fast non-reuse guardrails.

No migration files are planned (explicitly out of scope).

## Chunk 1: Metadata and Client Behavior

### Task 1: Update `Layout End Piece` metadata contract

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`
- Test: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`

- [ ] **Step 1: Write/adjust failing metadata contract assertions**

In `test_sheet_cutting_layout.py`, add assertions under existing end-piece field checks:

```python
assert end_piece_fields["disposition"].get("options") == "\nReuse\nScrap"
assert end_piece_fields["used_for_finished_part"].get("depends_on") == 'eval:doc.disposition=="Reuse"'
assert end_piece_fields["bom_quantity"].get("depends_on") == 'eval:doc.disposition=="Reuse"'
assert end_piece_fields["bom_scrap_quantity_kg"].get("depends_on") == 'eval:doc.disposition=="Reuse"'
assert end_piece_fields["scrap_item"].get("depends_on") == 'eval:doc.disposition=="Scrap"'
assert "Hold" not in str(end_piece_fields["disposition"].get("options"))
```

- [ ] **Step 2: Run module test to verify failure**

Run from bench root (example bench15):

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout
```

Expected: fail on new disposition/depends_on assertions.

- [ ] **Step 3: Implement DocType JSON changes**

Edit `layout_end_piece.json`:

1. Change disposition options from:
   - `\nReuse\nScrap\nHold`
   to
   - `\nReuse\nScrap`
2. Add:
   - `depends_on: eval:doc.disposition=="Reuse"` on:
     - `used_for_finished_part`
     - `bom_quantity`
     - `bom_scrap_quantity_kg`
3. Add:
   - `depends_on: eval:doc.disposition=="Scrap"` on:
     - `scrap_item`

- [ ] **Step 4: Re-run module test to verify pass**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout
```

Expected: metadata assertions pass.

- [ ] **Step 5: Commit metadata changes**

```bash
git add sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py
git commit -m "fix: gate end-piece fields by disposition in metadata"
```

### Task 2: Add client-side clear-on-non-reuse behavior

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`
- Test: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`

- [ ] **Step 1: Add failing client source assertion**

Add assertions in `test_client_updates_consumption_tracking_when_user_enters_dimensions_and_net_weight` (or a focused new client-source test):

```python
assert "clearReuseOnlyEndPieceFields" in client_script
assert "used_for_finished_part" in client_script
assert "bom_quantity" in client_script
assert "bom_scrap_quantity_kg" in client_script
assert "disposition: updateEndPieceDispositionAndDerivedFields" in client_script
```

- [ ] **Step 2: Run module test to verify failure**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout
```

Expected: fail on new client-source assertions.

- [ ] **Step 3: Implement disposition normalizer in JS**

In `sheet_cutting_layout.js`:

1. Add helper:

```javascript
function clearReuseOnlyEndPieceFields(row) {
	const updates = [];
	if (row.disposition === "Reuse") {
		return Promise.resolve([]);
	}
	if (row.used_for_finished_part) {
		updates.push(frappe.model.set_value(row.doctype, row.name, "used_for_finished_part", ""));
	}
	if (row.bom_quantity) {
		updates.push(frappe.model.set_value(row.doctype, row.name, "bom_quantity", null));
	}
	if (row.bom_scrap_quantity_kg) {
		updates.push(
			frappe.model.set_value(row.doctype, row.name, "bom_scrap_quantity_kg", null)
		);
	}
	return Promise.all(updates);
}
```

1. Add new disposition handler:

```javascript
function updateEndPieceDispositionAndDerivedFields(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	return clearReuseOnlyEndPieceFields(row)
		.then(() => updateEndPieceItemCodesFromForm(frm))
		.then(() => updateConsumptionTracking(frm));
}
```

1. Wire handler:

```javascript
disposition: updateEndPieceDispositionAndDerivedFields,
```

and keep existing behavior for item code + consumption recalculation.

- [ ] **Step 4: Re-run module test**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout
```

Expected: pass, including new client assertions.

- [ ] **Step 5: Commit JS changes**

```bash
git add sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py
git commit -m "fix: clear reuse-only end-piece fields on scrap disposition"
```

## Chunk 2: Validator Guardrails and Full Verification

### Task 3: Enforce non-reuse field integrity in validators

**Files:**
- Modify: `sheet_cutting_layout/services/validators.py`
- Test: `sheet_cutting_layout/tests/test_validators.py`

- [ ] **Step 1: Add failing validator tests**

In `test_validators.py`, add a focused test ensuring non-reuse rows reject reuse-only values:

```python
def test_non_reuse_end_piece_rows_reject_reuse_only_fields(validators):
	cases = [
		(EndPiece(disposition="Scrap", used_for_finished_part="FG01SHR"), "Used for finished part"),
		(EndPiece(disposition="Scrap", bom_quantity=1), "BOM quantity"),
		(EndPiece(disposition="Scrap", bom_scrap_quantity_kg=0.1), "BOM scrap quantity"),
	]
	for end_piece, message in cases:
		with pytest.raises(ValidationError, match=message):
			validators.validate_sheet_cutting_layout(
				Layout(finished_parts=[FinishedPart("AB12SHR", 2, 11, 1)], end_pieces=[end_piece])
			)
```

Also keep existing `scrap_item` requirement test intact.

- [ ] **Step 2: Run validators module to verify failure**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
```

Expected: fail on new guardrail test.

- [ ] **Step 3: Implement minimal validator guardrail**

In `validators.py`, inside end-piece validation path (adjacent to `_validate_end_piece_required_fields`), add explicit checks for rows where disposition is not `Reuse`:

```python
def _validate_non_reuse_rows_do_not_keep_reuse_fields(end_piece: EndPieceRow) -> None:
	if _is_reuse_end_piece(end_piece):
		return
	if not _is_missing(getattr(end_piece, "used_for_finished_part", None)):
		frappe.throw(_("Used for finished part is allowed only for reuse end pieces"))
	if _is_positive(getattr(end_piece, "bom_quantity", None)):
		frappe.throw(_("BOM quantity is allowed only for reuse end pieces"))
	if _is_positive(getattr(end_piece, "bom_scrap_quantity_kg", None)):
		frappe.throw(_("BOM scrap quantity is allowed only for reuse end pieces"))
```

Call it from `validate_sheet_cutting_layout` before/alongside other end-piece row checks.

Use helper:

```python
def _is_positive(value: float | None) -> bool:
	return value is not None and value > 0
```

Keep behavior fail-fast; do not auto-mutate server payload.

- [ ] **Step 4: Re-run validators module**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
```

Expected: validators module passes, including new non-reuse guardrails.

- [ ] **Step 5: Commit validator changes**

```bash
git add sheet_cutting_layout/services/validators.py sheet_cutting_layout/tests/test_validators.py
git commit -m "fix: enforce reuse-only end-piece fields in validator"
```

### Task 4: Integrated verification and PR hygiene

**Files:**
- Modify if needed: any files from Tasks 1-3

- [ ] **Step 1: Run focused test modules**

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
```

Expected: both modules pass.

- [ ] **Step 2: Run full app tests**

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout
```

Expected: all app tests pass.

- [ ] **Step 3: Run formatting/lint hooks**

```bash
pre-commit run --all-files
```

Expected: all hooks pass.

- [ ] **Step 4: Review final diff for scope**

```bash
git fetch origin
git status --short
git diff --name-only origin/develop...HEAD
```

Expected: only planned files changed.

- [ ] **Step 5: Push and update PR**

```bash
git push -u origin $(git branch --show-current)
```

Expected: branch updated on remote PR.
