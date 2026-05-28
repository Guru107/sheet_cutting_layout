# End Piece Disposition Visibility Design

Date: 2026-05-27  
Status: Ready for user review  
Scope: Fix end-piece disposition field visibility and stale-value behavior in Sheet Cutting Layout.

## 1. Problem and Goal

Current behavior shows `Used For Finished Part`, `BOM Quantity`, and `BOM Scrap Quantity Kg` even when
`Disposition = Scrap`. This creates invalid UI cues and allows stale reuse-only values to persist.

Goals:

1. Show reuse-only fields only when `Disposition = Reuse`.
2. Show scrap-only field only when `Disposition = Scrap`.
3. Remove `Hold` as a disposition option.
4. Clear reuse-only values immediately when user switches from `Reuse` to `Scrap`.
5. Enforce server-side safety so non-reuse rows cannot save reuse-only values.
6. Keep implementation aligned with Frappe-native patterns and bench-native tests.

Non-goal:

- Data migration/backward compatibility for `Hold` records. This app is under development and migration is not required.

## 2. Options Considered

### Option A: DocType metadata only

Use only `depends_on` and `options` in `layout_end_piece.json`.

Pros:

1. Declarative and framework-native.
2. Minimal code.

Cons:

1. Hidden stale values can remain when disposition changes.
2. No runtime clearing behavior.

### Option B: Client script only

Use only JavaScript show/hide + clear logic.

Pros:

1. Full runtime control.
2. Easy to add clear-on-change logic.

Cons:

1. More custom behavior than needed.
2. Weaker metadata contract.

### Option C: Hybrid (Selected)

Combine metadata visibility + client-side clearing + server-side guardrails.

Pros:

1. Correct UI behavior in grid/form.
2. Prevents stale hidden values at runtime.
3. Safe against non-UI writes/imports/API saves.

Cons:

1. Touches JSON + JS + validators + tests.
2. Slightly larger change surface.

## 3. Design

### 3.1 DocType metadata (`Layout End Piece`)

File: `sheet_cutting_layout/sheet_cutting_layout/doctype/layout_end_piece/layout_end_piece.json`

Changes:

1. `disposition.options` becomes:
   - `Reuse`
   - `Scrap`
2. `used_for_finished_part.depends_on` = `eval:doc.disposition=="Reuse"`
3. `bom_quantity.depends_on` = `eval:doc.disposition=="Reuse"`
4. `bom_scrap_quantity_kg.depends_on` = `eval:doc.disposition=="Reuse"`
5. `scrap_item.depends_on` = `eval:doc.disposition=="Scrap"`

Notes:

- This is the primary UI visibility contract and uses native Frappe metadata behavior.

### 3.2 Client behavior (`sheet_cutting_layout.js`)

File: `sheet_cutting_layout/sheet_cutting_layout/doctype/sheet_cutting_layout/sheet_cutting_layout.js`

On `Layout End Piece.disposition` change:

1. If disposition is not `Reuse`, set:
   - `used_for_finished_part = ""`
   - `bom_quantity = null`
   - `bom_scrap_quantity_kg = null`
2. Keep existing downstream updates:
   - end-piece item code suggestion behavior
   - consumption tracking recalculation

Rationale:

- Users see immediate correction and stale values are removed at edit time.

### 3.3 Server-side validation guardrails

File: `sheet_cutting_layout/services/validators.py` (or existing validator path handling end-piece rules)

Add/update validation:

1. For each end-piece row where disposition is not `Reuse`, enforce:
   - `used_for_finished_part` must be empty
   - `bom_quantity` must be null/empty/zero
   - `bom_scrap_quantity_kg` must be null/empty/zero
2. If not compliant, fail with explicit validation message.

Decision:

- Prefer fail-fast validation to avoid silently mutating payloads in server logic.

## 4. Data Flow

1. User changes disposition in child row.
2. DocType metadata re-evaluates field visibility.
3. Client script clears reuse-only values when disposition is not `Reuse`.
4. Save path runs validators.
5. Validators ensure non-reuse rows contain no reuse-only values.
6. Document persists with consistent state.

## 5. Edge Cases

1. **Reuse -> Scrap toggle with existing values**
   - Values are cleared immediately in client script.
2. **Programmatic/API save bypassing UI**
   - Server validator rejects inconsistent non-reuse rows.
3. **Blank disposition**
   - Reuse-only fields hidden by `depends_on`; validator behavior follows existing required-field policy.
4. **Existing `Hold` values in local data**
   - No migration included. Any manual cleanup is out of scope for this change.

## 6. Testing Strategy (Bench/Frappe Native)

Update bench-native tests only (no pytest runner dependency):

1. Source-contract test for `Layout End Piece` DocType:
   - `disposition.options` excludes `Hold`.
   - `depends_on` exists and matches expected expressions.
2. Client source-contract test:
   - disposition handler includes clear-on-non-reuse behavior.
3. Validator tests:
   - non-reuse rows with non-empty `used_for_finished_part`, non-zero `bom_quantity`, or non-zero `bom_scrap_quantity_kg` fail validation.
4. Full suite verification:
   - `bench --site development.localhost run-tests --app sheet_cutting_layout`

## 7. Acceptance Criteria

1. In the end-piece grid, `Used For Finished Part`, `BOM Quantity`, and `BOM Scrap Quantity Kg` are visible only for `Reuse`.
2. In the end-piece grid, `Scrap Item` is visible only for `Scrap`.
3. `Hold` is removed from `Disposition` options.
4. Changing row disposition to `Scrap` clears reuse-only fields immediately.
5. Server-side validation rejects non-reuse rows that still contain reuse-only values.
6. Bench-native test suite passes after changes.

## 8. Risks and Trade-offs

1. **Validation strictness vs convenience**
   - Fail-fast improves integrity but may require users/scripts to correct payloads.
2. **Mixed null/zero handling**
   - Need consistency with existing conventions to avoid noisy diffs and false validation failures.
3. **UI-only assumptions**
   - Mitigated by server-side guardrails.
