# Sheet Cutting Layout ERPNext Integration Design

Date: 2026-04-23  
Status: Approved for planning  
Scope: Phase 1 (manual-entry, form-driven canvas, approval-driven BOM automation)

## 1. Problem and Goal

Sheet cutting layout directly affects manufacturing BOM accuracy. The system needs a controlled workflow so BOMs are only generated after full approval, while giving engineering users a dynamic visual editor inside ERPNext.

Goals:

1. Create and revise sheet cutting layouts in ERPNext.
2. Enforce multi-step approval workflow:
   - Prepared by `Project User`
   - Checked and verified by `Project Manager` and `Manufacturing Manager` (parallel, both required)
   - Approved by `Purchase Manager`
   - Released by `MR Coordinator`
3. Generate BOMs automatically only at release.
4. Support multiple finished parts per layout (e.g., LH/RH symmetric parts).
5. Create new version on revision and disable/supersede old active version.
6. Provide live, CAD-like visual updates using canvas (pseudo-3D sheet view).

## 2. Phase 1 Scope and Non-Goals

In scope:

1. Manual data entry only.
2. Form-driven parametric canvas preview (no freehand drawing).
3. Approval workflow and server-side release orchestration.
4. Automatic BOM generation (qty always `1`) per finished part.
5. Per-document impact resolution for open manufacturing documents.

Out of scope:

1. Excel import.
2. DXF/SVG true shape nesting.
3. Canvas drag/resize editing.
4. External UI service outside ERPNext.

## 3. Approaches Considered

### Option A: Pure Frappe-native (Selected)

Build fully inside custom ERPNext/Frappe app (DocTypes + Workflow + JS canvas + backend orchestration).

Trade-offs:

1. Pros:
   - Lowest operational complexity.
   - Native permissions, audit logs, workflow.
   - Faster production rollout.
2. Cons:
   - UI flexibility lower than dedicated CAD frontend.

### Option B: External frontend + ERPNext APIs

Trade-offs:

1. Pros:
   - Maximum UI freedom.
2. Cons:
   - More infra/auth complexity.
   - Higher integration risk and longer delivery.

### Option C: Split platform (native now, external later)

Trade-offs:

1. Pros:
   - De-risks initial launch.
2. Cons:
   - Migration overhead later.

Recommendation: Option A for Phase 1.

## 4. Architecture

Single custom app: `sheet_cutting_layout`

Components:

1. DocTypes:
   - `Sheet Cutting Layout` (parent)
   - `Layout Finished Part` (child)
   - `Layout End Piece` (child, dynamic rows)
   - `Layout Approval Snapshot` (child, immutable)
   - `Layout Impact Resolution` (child or standalone doctype)
2. ERPNext Workflow configuration.
3. Form Script + Canvas widget for live visual preview.
4. Server service layer for release validation, BOM generation, supersede flow, and impact handling.
5. Background jobs for release orchestration to avoid long-running request transactions.

## 5. Data Model

The model incorporates repeated template fields observed in `Sheet Cutting Layout-W-502.xlsx` (project, dimensions, strip, part weights, end-piece blocks, revision metadata, approval blocks).

### 5.1 Parent: `Sheet Cutting Layout`

Core identity and revision:

1. `layout_code` (Data, unique business code)
2. `layout_family` (Data/Link for revision chain grouping)
3. `revision_no` (Int, auto-increment within family)
4. `based_on_layout` (Link Sheet Cutting Layout, nullable)
5. `is_active` (Check)
6. `status` (Select; workflow-controlled)

Header and project context:

1. `project` (Link Project)
2. `project_model` (Data, e.g., `NEW THAR`)
3. `part_name` (Data)
4. `doc_no` (Data, template reference)
5. `doc_rev_no` (Data)
6. `doc_rev_date` (Date)
7. `doc_page` (Data)
8. `effective_from` (Date)
9. `release_notes` (Small Text)
10. `note_text` (Small Text)

Material and layout parameters:

1. `raw_material_item` (Link Item, mandatory)
2. `sheet_thickness_mm` (Float, mandatory)
3. `sheet_width_mm` (Float, mandatory)
4. `sheet_length_mm` (Float, mandatory)
5. `weight_per_sheet_kg` (Float, mandatory)
6. `strip_thickness_mm` (Float)
7. `strip_width_mm` (Float)
8. `strip_length_mm` (Float)
9. `weight_of_strip_kg` (Float)
10. `parts_per_strip` (Int)
11. `no_of_strips` (Int)
12. `parts_per_sheet` (Int)

### 5.2 Child: `Layout Finished Part`

One row per finished part item (multiple rows allowed in same layout).

1. `finished_part_item` (Link Item, mandatory)
2. `parts_per_strip` (Int, mandatory)
3. `no_of_strips` (Int, mandatory)
4. `parts_per_sheet` (Int, mandatory)
5. `gross_weight_per_part_kg` (Float, mandatory)
6. `scrap_weight_per_part_kg` (Float, mandatory)
7. `derived_fg_weight_per_part_kg` (Float, read-only computed display, not written to BOM)
8. `total_weight_kg` (Float, optional display)
9. `generated_bom` (Link BOM, read-only)
10. `generated_bom_revision` (Data, read-only)

Note: `side_type` intentionally removed. LH/RH is represented by having two finished-part rows.

### 5.3 Child: `Layout End Piece` (Dynamic)

No fixed `I/II/III` structure. Users can add any number of rows.

1. `end_piece_item` (Link Item, mandatory)
2. `row_label` (Data, optional display label)
3. `thickness_mm` (Float)
4. `width_mm` (Float)
5. `length_mm` (Float)
6. `weight_kg` (Float, mandatory)
7. `qty_per_sheet` (Float, mandatory)
8. `disposition` (Select: `Scrap`, `Reuse`, `By-product Item`)
9. `used_for_finished_part` (Link to child row reference or Item)

Optional split dimensions to support patterns like `1-A/1-B`, `2-A/2-B` from template:

1. `split_a_thickness_mm`, `split_a_width_mm`, `split_a_length_mm`
2. `split_b_thickness_mm`, `split_b_width_mm`, `split_b_length_mm`

### 5.4 Child: `Layout Approval Snapshot`

Immutable audit entries:

1. `step_name`
2. `approver`
3. `decision`
4. `comment`
5. `decision_time`

### 5.5 Child/Doctype: `Layout Impact Resolution`

Tracks open-doc handling when new revision is releasing.

1. `reference_doctype`
2. `reference_docname`
3. `old_bom`
4. `new_bom`
5. `decision` (`Keep Old`, `Switch New`)
6. `decided_by`
7. `decided_on`
8. `status`

## 6. Validation Rules

Enforced server-side (primary), mirrored client-side for immediate UX.

1. At least one `Layout Finished Part` row is mandatory.
2. `finished_part_item` code must:
   - end with `SHR`
   - contain only alphanumeric characters (`^[A-Za-z0-9]+$`)
   - no `-`, `_`, spaces, `/`, or other special chars.
3. `scrap_weight_per_part_kg >= 0` (hard-block; save disallowed).
4. `gross_weight_per_part_kg >= 0`.
5. `parts_per_sheet > 0` where used for distribution formula.
6. `raw_material_item` mandatory.
7. End-piece rows require `end_piece_item`, `weight_kg`, and `qty_per_sheet`.
8. Derived FG must be non-negative for each finished part:
   - `gross_weight_per_part_kg - scrap_weight_per_part_kg - sum(distributed_end_piece_kg) >= 0`
9. Release cannot proceed if any validation fails.

## 7. Approval Workflow

States:

1. `Draft`
2. `Submitted for Check`
3. `Checked` (both checkers approved)
4. `Approved by Purchase`
5. `Release Pending Impact` (if impacted docs exist)
6. `Released`
7. `Rejected`
8. `Superseded`

Transitions:

1. Project User submits `Draft -> Submitted for Check`.
2. Project Manager and Manufacturing Manager approve in parallel.
3. Both approvals required to move to `Checked`.
4. Purchase Manager approves `Checked -> Approved by Purchase`.
5. MR Coordinator triggers release orchestration.
6. If no impacted open docs, release completes to `Released`.
7. If impacted docs exist, move to `Release Pending Impact` until decisions are completed, then finalize release.
8. New released revision automatically supersedes previous released active layout.

## 8. Canvas UX (Phase 1)

Editor mode: form-driven only.

Behavior:

1. Field/table edits trigger debounced recalculation and redraw.
2. Canvas renders:
   - pseudo-3D sheet base (top + shaded side)
   - strip segmentation
   - repeated finished-part blocks
   - dynamic end-piece zones for each row
3. Live metrics:
   - utilization estimate
   - gross/scrap/derived FG summaries
4. Invalid values highlight regions and show inline error cues.

Performance targets:

1. Typical redraw under 100 ms.
2. Debounce 150-250 ms.
3. Cached static layers for smooth updates.

## 9. BOM Generation and Mapping

Trigger: release orchestration (post workflow approvals).

For each finished part row:

1. Create separate BOM (no combined BOM across finished parts).
2. BOM quantity is always `1`.
3. Raw material row:
   - `item_code = raw_material_item`
   - `qty (Kg) = gross_weight_per_part_kg`
4. Scrap rows (Kg):
   - process scrap row from `scrap_weight_per_part_kg` (using configured process-scrap item)
   - end-piece scrap rows from distributed per-part weight.

End-piece distribution formula (approved):

`end_piece_distributed_per_part_kg = (end_piece_weight_kg * qty_per_sheet) / parts_per_sheet`

Derived FG (not stored as standard BOM field):

`fg_weight_per_part_kg = gross_weight_per_part_kg - scrap_weight_per_part_kg - sum(end_piece_distributed_per_part_kg)`

All units are Kg (raw and scrap).

## 10. Versioning and Supersede

1. Released layouts are immutable.
2. Revision action clones released layout to new draft with incremented `revision_no`.
3. Finalizing new release:
   - previous active layout -> `Superseded`, `is_active=0`
   - new layout -> `Released`, `is_active=1`
   - previous active BOMs for affected finished parts disabled/superseded
   - new BOMs activated.
4. Guarantee: only one active released layout per family.

## 11. Open Document Impact Handling (Option 3)

Requirement: prompt per affected open document.

Process:

1. Detect open/draft manufacturing documents referencing old BOMs.
2. Create impact entries per document.
3. User/MR Coordinator decides per entry:
   - keep old BOM
   - switch to new BOM
4. Release finalization waits until all impact entries resolved.

Trade-off:

1. Safer than mass auto-update.
2. Slightly slower operational release flow.

## 12. Transaction Safety and Error Handling

1. Release orchestration runs as background job with idempotency key per layout revision.
2. Release finalization is atomic: no partially finalized release.
3. Failures keep layout in pre-release or `Release Pending Impact` with explicit error log.
4. All approval and resolution actions are audit-logged.

## 13. Permission Model

1. `Project User`: create/edit draft, submit.
2. `Development User`: allowed to create/edit/update layout drafts (as requested).
3. `Project Manager`: checker approval.
4. `Manufacturing Manager`: checker approval.
5. `Purchase Manager`: purchase approval.
6. `MR Coordinator`: release + impact resolution closure.
7. Only authorized roles can transition workflow states.

## 14. Scalability and Data Access

Indexes:

1. `Sheet Cutting Layout(layout_family, is_active, status)`
2. `Layout Finished Part(parent, finished_part_item)`
3. `Layout End Piece(parent, used_for_finished_part)`
4. `Layout Impact Resolution(reference_doctype, reference_docname, status)`

Design notes:

1. Keep DB transactions short; use background workers for heavy release flow.
2. Avoid repeated BOM scans by linking generated BOM back to finished-part rows.

## 15. Testing Requirements

Global requirements:

1. Development follows test-driven development only: failing test first, minimal implementation, refactor while green.
2. Project-owned code coverage must stay above 96%.
3. Framework, library, generated, and vendored code are excluded from coverage calculations.
4. Python application code must be strictly type-safe, with explicit annotations for public functions, controller helpers, service functions, and non-obvious return values.

### 15.1 Unit Tests

1. Finished part validator (`SHR` + alphanumeric).
2. Hard block on negative scrap.
3. End-piece distribution formula.
4. Derived FG formula.
5. Revision and active-version invariants.

### 15.2 Property-Based Testing (Mandatory)

Generate randomized valid layouts and assert invariants:

1. BOM quantity always `1`.
2. Raw material qty equals gross per part.
3. Scrap total equals process scrap + distributed end-piece scrap.
4. Derived FG is consistent and non-negative for accepted inputs.
5. Only one active released layout per family after arbitrary revision sequences.

### 15.3 Model-Based Testing (Mandatory)

Model workflow as state machine and generate event sequences:

1. Invalid state transitions are blocked.
2. Parallel checker logic requires both approvals.
3. BOM side effects occur only on release orchestration.
4. Failure paths do not leave partially released state.
5. Supersede logic keeps single active version semantics.

### 15.4 Integration and UI Tests

1. Multi-finished-part release creates separate BOMs correctly.
2. End-piece dynamic rows map correctly to BOM scrap.
3. Impact resolution flow updates/retains documents per decision.
4. Form-to-canvas sync correctness.
5. Canvas redraw performance checks.
6. Cypress end-to-end tests cover critical release workflows through Frappe bench.

## 16. Rollout Plan

1. Build and deploy to staging with feature toggle.
2. Configure workflow/roles/permissions.
3. UAT with representative W-502 layouts.
4. Validate generated BOMs vs manual baseline.
5. Pilot with one project, then scale rollout.

## 17. Known Trade-offs

1. Form-driven canvas is less flexible than direct CAD editing, but much safer for BOM-critical workflows.
2. Strict validation blocks bad data early, but may require additional user corrections.
3. Per-document impact prompting slows releases slightly, but avoids risky blanket BOM replacement.
