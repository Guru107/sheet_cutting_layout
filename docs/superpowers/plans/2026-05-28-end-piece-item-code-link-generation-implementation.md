# End Piece Item Code Link-Only Generation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace editable/precomputed end-piece item code behavior with generation-only link behavior, and enforce deterministic code/rate rules for generated BOM rows.

**Architecture:** Keep a hybrid enforcement strategy: DocType metadata controls visibility/editability, validators enforce deterministic business rules, and generation services own create-or-reuse and pricing fallback logic. Centralize scrap-rate fallback in `services/bom_service.py` and call it from release and end-piece BOM generation paths.

**Tech Stack:** Frappe/ERPNext 15 DocType JSON + Desk Form JS, Python service modules (`validators.py`, `end_piece_bom_service.py`, `bom_service.py`, `release_service.py`), bench-native tests (`bench --site ... run-tests`), pre-commit.

---

## Reference Documents

- Spec: `docs/superpowers/specs/2026-05-28-end-piece-item-code-link-and-generation-design.md`
- Child doctype metadata: `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`
- Parent form script: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`
- Validators: `sheet_cutting_layout/services/validators.py`
- End-piece generation service: `sheet_cutting_layout/services/end_piece_bom_service.py`
- BOM model/rate helper owner: `sheet_cutting_layout/services/bom_service.py`
- Release integration: `sheet_cutting_layout/services/release_service.py`
- Contract/source tests:
  - `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`
  - `sheet_cutting_layout/tests/test_validators.py`
  - `sheet_cutting_layout/tests/test_end_piece_bom_service.py`
  - `sheet_cutting_layout/tests/test_bom_service.py`
  - `sheet_cutting_layout/tests/test_release_service.py`

## File Structure

Modify:

- `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`
  - Convert `end_piece_item_code` to read-only `Link(Item)`.
  - Remove `generated_end_piece_item`.
  - Keep `end_piece_item_code` hidden until generated (`depends_on` on `generated_end_piece_bom`).
- `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`
  - Remove pre-generation item-code suggestion/update logic and preview wiring.
  - Keep disposition cleanup + consumption recalculation only.
- `sheet_cutting_layout/services/validators.py`
  - Add `used_for_finished_part` suffix validation (`SHR|BLK|DR`) for reuse rows.
  - Remove reuse-time requirement for prefilled `end_piece_item_code`.
  - Keep generated code immutable once generated BOM link exists.
- `sheet_cutting_layout/services/end_piece_bom_service.py`
  - Derive deterministic code from `used_for_finished_part` + dimensions.
  - Create/reuse Item with `Nos` stock UOM and `Kg` alternate UOM conversion (`1 / weight_kg`).
  - Persist generated code only in `end_piece_item_code`.
  - Add scrap-rate fallback integration using shared helper.
- `sheet_cutting_layout/services/bom_service.py`
  - Add owned helper `resolve_scrap_item_rate(...)` for valuation-rate fallback.
- `sheet_cutting_layout/services/release_service.py`
  - Use `resolve_scrap_item_rate(...)` when appending BOM scrap rows if `rate` missing.
- Tests listed above to match new contract and remove obsolete preview/generated-item dual-field assumptions.

No migration files are planned (explicitly out of scope for this in-development app).

## Chunk 1: Metadata and UI Contract

### Task 1: Convert `end_piece_item_code` to the only generated link field

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`
- Test: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`

- [ ] **Step 1: Add failing doctype contract assertions**

In `test_sheet_cutting_layout.py`, assert:

```python
assert end_piece_fields["end_piece_item_code"]["fieldtype"] == "Link"
assert end_piece_fields["end_piece_item_code"]["options"] == "Item"
assert end_piece_fields["end_piece_item_code"].get("read_only") == 1
assert end_piece_fields["end_piece_item_code"].get("depends_on") == 'eval:doc.generated_end_piece_bom'
assert end_piece_fields["disposition"]["options"] == "\nReuse\nScrap"
assert "Hold" not in end_piece_fields["disposition"]["options"]
assert "generated_end_piece_item" not in end_piece_fields
```

- [ ] **Step 2: Run doctype contract test and confirm failure**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout
```

Expected: fail on `end_piece_item_code` fieldtype/options and removed field assertions.

- [ ] **Step 3: Implement DocType JSON changes**

In `layout_end_piece.json`:

1. Change `end_piece_item_code` from `Data` to `Link` with `options: "Item"` and `read_only: 1`.
1. Add `depends_on: eval:doc.generated_end_piece_bom` to `end_piece_item_code`.
1. Ensure `disposition` options are exactly:
   - `\nReuse\nScrap`
1. Remove `generated_end_piece_item` from `field_order` and `fields`.

- [ ] **Step 4: Re-run doctype contract test and confirm pass**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout
```

Expected: pass with new schema contract.

- [ ] **Step 5: Commit metadata contract change**

```bash
git add sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py
git commit -m "feat: make end piece item code generated link-only field"
```

### Task 2: Remove pre-generation item-code preview/suggestion behavior from client script

**Files:**
- Modify: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`
- Test: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py`

- [ ] **Step 1: Add failing source-contract assertions**

In client source assertions, add:

```python
assert "suggestEndPieceItemCode(" not in client_script
assert "updateEndPieceItemCodes(" not in client_script
assert "updateEndPieceItemCodesFromForm" not in client_script
assert "preview_sheet_cutting_layout_end_piece_boms" not in client_script
assert "Preview End Piece Items" not in client_script
assert 'set_value(row.doctype, row.name, "end_piece_item_code"' not in client_script
```

And keep assertion for disposition cleanup handler:

```python
assert "disposition: updateEndPieceDispositionAndDerivedFields" in client_script
```

- [ ] **Step 2: Run doctype JS source test and confirm failure**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout
```

Expected: fail on removed preview/suggestion behavior assertions.

- [ ] **Step 3: Implement JS cleanup**

In `sheet_cutting_layout.js`:

1. Remove `suggestEndPieceItemCode`, `updateEndPieceItemCodes`, `updateEndPieceItemCodesFromForm`.
1. Remove preview button wiring and preview RPC call usage for end-piece item code.
1. Remove triggers that existed only for preview/suggestion (`raw_material_item`, `disposition` item-code updates).
1. Keep `updateEndPieceDispositionAndDerivedFields` focused on:
   - stale field cleanup
   - consumption tracking

- [ ] **Step 4: Re-run doctype JS source test and confirm pass**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout
```

Expected: pass with no preview/suggestion references.

- [ ] **Step 5: Commit JS behavior contraction**

```bash
git add sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py
git commit -m "refactor: remove end piece code preview and suggestion client flow"
```

## Chunk 2: Deterministic Backend Rules and Generation

### Task 3: Update validators for suffix rule and generated-code lock semantics

**Files:**
- Modify: `sheet_cutting_layout/services/validators.py`
- Test: `sheet_cutting_layout/tests/test_validators.py`

- [ ] **Step 1: Add failing validator tests**

Add/adjust tests:

1. Reuse row accepts `used_for_finished_part` ending with `SHR`, `BLK`, `DR`.
1. Reuse row rejects non-matching suffix:

```python
with pytest.raises(ValidationError, match="must end with SHR, BLK, or DR"):
    validators.validate_sheet_cutting_layout(...)
```

1. Reuse validation no longer requires prefilled `end_piece_item_code` before generation.
1. Before generation contract is explicit:
   - `end_piece_item_code` stays empty until `Generate End Piece BOMs` persists generated value.
1. Lock test uses `generated_end_piece_bom` as immutable gate for `end_piece_item_code`.
1. Legacy invalid disposition path is explicit:
   - `disposition in ("", None, "Hold")` fails with `Disposition must be either Reuse or Scrap`.
1. Deterministic numeric-component validation path is explicit:
   - missing/non-numeric/non-positive thickness, width, or length used for code generation fail with expected message.

- [ ] **Step 2: Run validator module and confirm failure**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
```

Expected: fail on new suffix and pre-generation code assumptions.

- [ ] **Step 3: Implement validator changes**

In `validators.py`:

1. Add helper to validate reuse suffix (normalize via `strip().upper()` for determinism).
1. Keep explicit disposition guard (`Reuse`/`Scrap` only), preserving `Hold` rejection message.
1. Remove reuse-time requirement that `end_piece_item_code` must already be set.
1. Keep/update generated-code lock check:
   - deny `end_piece_item_code` edits when `generated_end_piece_bom` exists.
1. Add/own shared code-format helper in validators (single source of truth for numeric normalization), and use this helper from generation service to avoid derivation drift.

- [ ] **Step 4: Re-run validator module and confirm pass**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
```

Expected: pass with updated business rules.

- [ ] **Step 5: Commit validator updates**

```bash
git add sheet_cutting_layout/services/validators.py sheet_cutting_layout/tests/test_validators.py
git commit -m "feat: validate reuse finished-part suffix and generated code lock rules"
```

### Task 4: Rework end-piece generation service for deterministic code and item creation

**Files:**
- Modify: `sheet_cutting_layout/services/end_piece_bom_service.py`
- Test: `sheet_cutting_layout/tests/test_end_piece_bom_service.py`

- [ ] **Step 1: Add failing service tests**

Add/adjust tests for:

1. Deterministic code format:
   - `<used_for_finished_part>-EP-<thickness>x<width>x<length>`
   - 6-decimal trim normalization.
   - parity test: validator-owned formatter and generation path produce identical normalized code.
1. Item creation metadata:
   - `item_code == item_name`.
   - description contains raw material + dimensions.
   - `item_group` is derived from `raw_material_item` item group.
   - `stock_uom == "Nos"`.
   - UOM row for `"Kg"` has `conversion_factor == 1 / end_piece.weight_kg`.
1. Existing item reuse path does not mutate item.
1. `generated_end_piece_item` is no longer persisted or asserted.
1. Error paths:
   - missing/zero `weight_kg` fails before UOM conversion setup.
   - generated code length overflow fails with explicit error containing `used_for_finished_part` context (no truncation).
   - item-creation failure includes row context in message.

- [ ] **Step 2: Run service module and confirm failure**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
```

Expected: fail on code derivation and item/UOM expectations.

- [ ] **Step 3: Implement end-piece generation changes**

In `end_piece_bom_service.py`:

1. Derive code server-side from `used_for_finished_part` + dimensions.
1. Reuse shared deterministic code-format helper owned by validators (no duplicate formatter logic).
1. Replace previous requirement for user-entered `end_piece_item_code`.
1. Create Item with `Nos` stock UOM and alternate `Kg` UOM conversion.
1. Preserve current `item_group` derivation from `raw_material_item` item group.
1. Persist only:
   - `end_piece_item_code`
   - `generated_end_piece_bom`
1. Remove `generated_end_piece_item` protocol usage and persistence payload fields.
1. Add explicit failures for:
   - missing/zero `weight_kg`
   - derived item code length overflow with `used_for_finished_part` context in message
   - item master creation issues with row index context

- [ ] **Step 4: Re-run service module and confirm pass**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
```

Expected: pass with new deterministic generation behavior.

- [ ] **Step 5: Commit generation service updates**

```bash
git add sheet_cutting_layout/services/end_piece_bom_service.py sheet_cutting_layout/tests/test_end_piece_bom_service.py
git commit -m "feat: generate end piece item code from reuse target and dimensions"
```

### Task 5: Add shared scrap-rate fallback helper and wire both BOM flows

**Files:**
- Modify: `sheet_cutting_layout/services/bom_service.py`
- Modify: `sheet_cutting_layout/services/release_service.py`
- Modify: `sheet_cutting_layout/services/end_piece_bom_service.py`
- Test: `sheet_cutting_layout/tests/test_bom_service.py`
- Test: `sheet_cutting_layout/tests/test_release_service.py`
- Test: `sheet_cutting_layout/tests/test_end_piece_bom_service.py`

- [ ] **Step 1: Add failing tests for rate fallback contract**

Add tests that verify:

1. Existing populated `rate` is preserved.
1. Missing `rate` triggers valuation fallback.
1. Missing/invalid fallback rate raises explicit error including scrap item code and row context.
1. Required scrap item missing raises explicit error when a scrap row must be created.
1. Existing populated `rate` path does not call fallback helper (interaction assertion/mocking).

- [ ] **Step 2: Run focused modules and confirm failure**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
```

Expected: fail on new rate fallback assertions.

- [ ] **Step 3: Implement shared helper and integration**

In `bom_service.py`:

1. Add `resolve_scrap_item_rate(item_code, company, existing_rate=None)`:
   - return existing rate when already set.
   - otherwise call ERPNext canonical helper:
     `erpnext.manufacturing.doctype.bom.bom.get_valuation_rate`.
   - validate numeric `> 0`, else raise explicit error.

In `release_service.py` and `end_piece_bom_service.py`:

1. Use `resolve_scrap_item_rate(...)` when creating scrap rows without rate.
1. Set `rate` only on missing-rate path.
1. Keep explicit error path for missing scrap item when a scrap row is required.

- [ ] **Step 4: Re-run focused modules and confirm pass**

Run:

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
```

Expected: pass across all fallback paths.

- [ ] **Step 5: Commit fallback helper and integration**

```bash
git add sheet_cutting_layout/services/bom_service.py sheet_cutting_layout/services/release_service.py sheet_cutting_layout/services/end_piece_bom_service.py sheet_cutting_layout/tests/test_bom_service.py sheet_cutting_layout/tests/test_release_service.py sheet_cutting_layout/tests/test_end_piece_bom_service.py
git commit -m "feat: apply valuation-rate fallback for generated scrap rows"
```

## Chunk 3: Full Verification and PR Readiness

### Task 6: Run full verification suite

**Files:**
- Modify only if failures require fixups in changed files.

- [ ] **Step 1: Run doctype/source contract module**

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.sheet_cutting_layout.doctype.sheet_cutting_layout.test_sheet_cutting_layout
```

Expected: pass.

- [ ] **Step 2: Run core changed service/validator modules**

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_validators
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_end_piece_bom_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_bom_service
bench --site development.localhost run-tests --app sheet_cutting_layout --module sheet_cutting_layout.tests.test_release_service
```

Expected: pass.

- [ ] **Step 3: Run full app tests**

```bash
bench --site development.localhost run-tests --app sheet_cutting_layout
```

Expected: pass.

- [ ] **Step 4: Run pre-commit checks**

```bash
pre-commit run --all-files
```

Expected: all hooks pass.
If hooks rewrite files, re-run the same command until it reports clean.

- [ ] **Step 5: Verify diff scope**

```bash
git fetch origin
git status --short
git diff --name-only origin/develop...HEAD
```

Expected: only implementation-scope files from Tasks 1-5 (metadata, services, doctype JS, and listed tests) are changed.

- [ ] **Step 6: Final commit for any verification-driven adjustments**

```bash
git status --short
git add \
  sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json \
  sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js \
  sheet_cutting_layout/services/validators.py \
  sheet_cutting_layout/services/end_piece_bom_service.py \
  sheet_cutting_layout/services/bom_service.py \
  sheet_cutting_layout/services/release_service.py \
  sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/test_sheet_cutting_layout.py \
  sheet_cutting_layout/tests/test_validators.py \
  sheet_cutting_layout/tests/test_end_piece_bom_service.py \
  sheet_cutting_layout/tests/test_bom_service.py \
  sheet_cutting_layout/tests/test_release_service.py
git commit -m "test: finalize end-piece link-only generation verification"
git status --short
```

Expected: commit succeeds and `git status --short` is clean.

### Task 7: Prepare for execution handoff

**Files:**
- None (handoff state only).

- [ ] **Step 1: Summarize what was implemented vs spec**

Include:
1. Single-field link contract.
1. Deterministic code derivation.
1. Reuse suffix validation.
1. Scrap-rate fallback coverage.

- [ ] **Step 2: Confirm clean working tree**

```bash
git status --short
```

Expected: clean.

- [ ] **Step 3: Push branch**

```bash
git push -u origin $(git branch --show-current)
```

Expected: remote branch updated for PR.
