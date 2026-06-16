# Sheet Cutting Layout — IATF export, LH/RH parts, recursive end pieces, and framework conformance

Date: 2026-06-13
Branch: `feature/scl-iatf-export-lhrh-recursion`
Status: Design — approved in brainstorming, pending written-spec review

## 1. Purpose

The Sheet Cutting Layout app lets press-part planners enter a shearing layout once and have the
system translate it into native ERPNext BOMs, so users never hand-build BOMs. The approved Excel
(`FRM/PRD/15`, "Sheet Cutting Layout") is the IATF-16949 audit artifact.

This effort closes the gaps between the current app and that domain, and pays down accumulated
framework-conformance debt:

- **A1 — Excel/IATF export.** Produce the approved `FRM/PRD/15` workbook from a layout (hard audit
  requirement; currently absent).
- **A2 — LH/RH symmetric parts.** One layout produces identical BOMs for each of its LH/RH item
  codes (the export pairs them as full codes joined with `/`, e.g.
  `0102AAG06400SHR/0102AAG06410SHR` — decision 2026-06-16; see §8.4); currently one layout → one BOM.
- **A3 — Recursive end-piece layouts (hybrid).** A reused end piece may carry its own full cutting
  layout (its own strip + its own end pieces), modeling the Excel's nesting; currently flat,
  single-level reuse only.
- **Phase 0 — Cleanup + framework conformance.** Remove dead code/residue and bring the app back
  onto native Frappe/ERPNext APIs, doc events, and lifecycle.

Out of scope this round: the visual cutting diagram (Excel's graphical strip drawing). Deferred.

## 2. Domain model (from the approved Excel)

A single-page-per-part layout:

- **Header:** company, doc no (`FRM/PRD/15`), part name, part number(s), project (code + name).
- **Main strip:** raw-material grade, sheet thickness, sheet W×L, weight of strip
  (`thickness × width × length × 0.786 / 100000`, the steel density factor), strip W×L, parts/strip,
  no. of strips, parts/sheet (= strips × parts/strip), gross/net/scrap weight per part
  (net measured practically, scrap = gross − net).
- **End pieces (I, II, III…):** each has a size; a *reused* end piece is itself treated like a sheet —
  it has a "used for part number", its own strip, parts/strip, gross/net/scrap, and *its own*
  sub-end-pieces (the Excel's `End Piece 2 → 2-A, 2-B`). This is the recursive structure.
- **LH/RH twins:** symmetric parts share an identical layout; the page names both part numbers
  ("Part Name: Brkt bumper top LH & RH", "Part Number: 0102AAG06400SHR/0102AAG06410SHR" — full codes, `/`-joined; see §8.4).
- **BOM table (right side):** main part row + end-piece rows (gross / f.g. / scrap / nos / total wt).
- **Signatures:** Prepared By (Engg/Prod), Checked by Production Manager, BOM Updated by Purchase,
  Released by Management Rep.

## 3. Current state (baseline)

The happy path is mature: a `Sheet Cutting Layout` doctype (single `finished_part_code`), a 5-state
approval workflow (Draft → Submitted for Check → PM Approved → Approved by Purchase → Released),
automatic main-BOM + end-piece-BOM generation on MR release, BOM versioning / supersede,
valuation/UOM handling, and a large test suite (~15 incremental specs shipped).

Key facts the design builds on:

- `services/release_service.py::_generate_boms` already **loops over finished parts**
  (`_parent_finished_part_rows`), today returning a single row from `finished_part_code`. LH/RH is a
  natural extension of this loop.
- `end_pieces` is a flat child table (`Layout End Piece`); reuse produces an item + a *simple* BOM via
  `end_piece_bom_service`.
- No LH/RH support, no export, no recursion, no visual diagram (a `canvas_payload` module was removed).

## 4. Cross-cutting principles

These govern **every** phase.

### 4.1 Framework-native first
Use Frappe/ERPNext APIs, doc events, validation, and lifecycle. Do not reimplement or bypass framework
behaviour. Anywhere we would need to step outside the framework, it is flagged for explicit approval
**with the native alternative spelled out**. The Phase 0 conformance work (§7) is the first application
of this rule; it is a standing rule thereafter.

### 4.2 Native lifecycle: Supersede ≡ Cancel
"Supersede" and "Cancel" are the same operation — the layout is no longer used, so the layout document
is **cancelled** (`doc.cancel()`). There is no separate "deactivate-only" supersede path.

Release and retirement are driven by **native doc events**, not by `validate()` or a custom
`apply_workflow` override (see §7, theme 2):

- **Release** is triggered from `on_submit` (the `Released` workflow state has `doc_status = 1`, so the
  native `apply_workflow` calls `doc.submit()`).
- **Retirement** is triggered from `on_cancel`; **deletion** from `on_trash`.

This requires a **workflow fixture change** (Phase 0): today `fixtures/workflow.json` makes `Superseded`
a `doc_status: 1` state reached by a 1→1 `Released --Supersede--> Superseded` transition that fires *no*
doc event, and the `doc_status: 2` `Cancel` state is unreachable. We set **`Superseded` to
`doc_status: 2`** so `apply_workflow` executes the Supersede transition (submitted → docstatus 2) as
`doc.cancel()` → `on_cancel`, and **remove the redundant unreachable `Cancel` state** (and its entries
in the `status` Select options + the `hooks.py` Workflow State fixture filter). `Superseded` becomes the
single docstatus-2 retirement state.

### 4.3 Cascade + BOM retirement (verified against installed source)
Verified in ERPNext v15.101 / Frappe v15:

- `BOM.on_cancel` natively sets `is_active=0`, `is_default=0`, runs `validate_bom_links`
  (blocks only if the BOM is a component of another *active* BOM), and `manage_default_bom`
  (re-points `Item.default_bom` to a remaining active BOM).
  Ref: `erpnext/manufacturing/doctype/bom/bom.py:310-317, 554-576, 979-990`.
- Frappe's generic `check_if_doc_is_linked(method="Cancel")` **blocks** cancelling a BOM that a
  *submitted* Work Order / Manufacture Stock Entry links to (BOM does not exempt them).
  Ref: `frappe/model/delete_doc.py:264-388`.
- **Deactivating** a submitted BOM (`is_active=0` via `on_update_after_submit`) is always allowed.

Resulting lifecycle, all native:

- **Supersede/Cancel a layout → `layout.cancel()`.** `on_cancel`:
  1. **Cascades** down each end-piece `child_layout`, cancelling the child (which recurses through
     *its own* `on_cancel`). A parent already at `docstatus=2` no longer blocks the child's cancel,
     so depth-first ordering falls out of the native flow.
  2. **Retires each BOM it created:** attempt native `bom.cancel()` (succeeds when unused →
     `is_active=0`, `docstatus=2`); if Frappe blocks it as used-in-manufacturing, fall back to native
     **deactivate** (`is_active=0` via the submitted-BOM update path, stays `docstatus=1`). Either way
     the BOM ends **deactivated**.
  3. The layout cancels cleanly via native **`ignore_linked_doctypes = ["BOM"]`** on the doctype — no
     manual `db_set` / backlink-unlink / savepoint juggling.
- **Delete** is purely framework-gated: attempt `doc.delete()`; Frappe blocks via `on_trash` link
  checks if anything still links (submitted BOM, Work Order, Stock Entry). Success ⇒ genuinely unused.
  No custom "is it used?" query.

The no-cycle guard on `child_layout` (§9.3) guarantees the cascade terminates.

### 4.4 Three-layer bench-native tests, gating every feature
The app runs **full bench-native** tests — frappe-less test mode and the in-app pytest emulation are
removed (§7, theme 8; the test-mode/adapter removal and the bench-native `tests/base.py` v15/v16 probe
**landed via develop merge 2026-06-13**). Every feature ships, and does not merge without, all three
layers green:

- **Unit** — pure-domain logic in frappe-free modules (geometry, export cell-mapping, cascade-graph
  traversal, twin expansion, cycle detection), exercised under `FrappeTestCase` via the bench runner.
- **Integration** — `bench --site <site> run-tests --app sheet_cutting_layout` against a real DB.
- **E2E** — Cypress via `bench --site <site> run-ui-tests sheet_cutting_layout --headless`.

## 5. Phasing & dependencies

```
Phase 0 ─▶ Phase 1 ─▶ ┌─ Phase 2 (export) ─┐─▶ Integrate
 cleanup    LH/RH      └─ Phase 3 (recursion)┘   (export covers recursion)
 + native              (parallel tracks)
 lifecycle
```

- **0 → 1 sequential.** LH/RH builds on the Phase-0 multi-BOM fix and the native release/cancel spine.
- **2 ∥ 3.** Export and recursion branch off post-Phase-1 and merge independently; a final integration
  PR teaches the exporter to render the recursive child tree.
- The native lifecycle thread (§4.2–4.3) spans Phase 0 (the `on_submit`/`on_cancel` spine) → Phase 3
  (the cross-layout cascade). It is one thread, sequenced through the phases.

## 6. Phase 0a — Dead-code & residue cleanup

No behaviour change; characterization tests pin current release/BOM output first.

- Remove dead `qty_per_sheet` (field on `Layout End Piece` + the attr on the three `EndPieceRow`
  Protocols in `bom_service`, `release_service`, `validators` — `end_piece_bom_service` does not
  declare it).
- Delete `layout_impact_resolution` residue (stale `.pyc` / empty dir; zero active refs).
- Drop the 5 migration patches (`patches.txt` + modules) per the dev-only hard-reset policy. This also
  resolves conformance findings 19–22 for free.
- Fix the multi-BOM latent bug: `_generate_boms` overwrites `layout.generated_bom` every iteration —
  make it the **primary** part's BOM and rely on the `finished_parts` reference rows for the rest
  (groundwork for LH/RH). Also add the `generated_bom` (Link → BOM) column to `Layout Finished Part`
  that `_layout_bom_names` already reads but the doctype is missing.
- Extract the steel-weight geometry (`× 0.786 / 100000`, strip/sheet/part weights, `parts_per_sheet`)
  into one frappe-free `services/geometry.py` shared by the controller, validators, and exporter.

## 7. Phase 0b — Framework conformance remediation

Source-validated audit of the codebase against installed Frappe v15 / ERPNext v15.101 produced **36
confirmed deviations (3 high / 13 medium / 20 low)**; full appendix in §12. Grouped into themes with
the native direction:

1. **BOM-lifecycle bypass (high).** `release_service` retires BOMs by raw `db_set` of
   `is_active/disabled/is_default/status` (writes a `status="Superseded"` field that does **not exist**
   on BOM), skipping `validate_bom_links` + `manage_default_bom`; `_clear_item_default_bom_reference`
   reimplements `manage_default_bom` but never promotes a replacement → dangling `Item.default_bom`.
   → Retire via `doc.cancel()` / `is_active` toggle through `on_update_after_submit`; delete the mirror
   helper and the non-schema field writes. *Folds into §4.3.* (Findings 1, 2, 13, 14, 32.)
2. **Release driven from `validate()` (high).** BOMs are inserted/submitted as a side effect of
   `validate()`, reached via `before_workflow_action` reading `frappe.flags.selected_workflow_action`,
   which only exists because the app overrides `frappe.model.workflow.apply_workflow`.
   → **Adopt native `on_submit`/`on_cancel`** (decision approved): drop the override + flags +
   `before_workflow_action`; trigger release from `on_submit`, retirement from `on_cancel`. This is the
   spine of §4.2–4.3. (Findings 3, 10.)
3. **Hand-rolled cancel cascade / savepoint juggling (med).** `cancel_generated_bom` clears backlinks +
   a manual savepoint to dodge link validation. → `on_cancel` + `ignore_linked_doctypes=["BOM"]` +
   `frappe.database.savepoint`. *Folds into §4.3.* (Finding 9.)
4. **Construction sets controller-computed fields (low cluster).** Pre-resolved scrap `rate`; BOM Item
   `stock_qty/stock_uom/conversion_factor`; `bom.uom="Kg"` (overwritten by `validate_main_item`);
   manual stock-UOM row; `is_active/disabled/status` on insert; `_company_for_layout` reimplements
   `erpnext.get_default_company`; `frappe.db.get_value` → `get_cached_value` for stable Item config
   (+ guard `None` names). → Set only input fields; let the BOM/Item controllers compute.
   (Findings 6, 7, 23, 24, 26, 27, 28, 29, 32.)
5. **Manual DB writes bypassing lifecycle (med/low).** Item `valuation_rate` backfill and end-piece
   link writes via `set_value`/`db_set` ladders. → `doc.save()` / direct `doc.db_set`.
   (Findings 8, 25.)
6. **Permissions (med — practically high).** The doctype grants only System Manager, so PM / Purchase /
   MR roles cannot read/write the doc the workflow moves them through; `Item.insert(ignore_permissions=
   True)` is unjustified. → Add role perm blocks (read/write, submit/cancel where doc_status changes);
   justify or drop the elevation. (Findings 12, 30.)
7. **Workflow/audit overlap (low).** The `Cancel` workflow state is unreachable and `Superseded` is a
   docstatus-1 dead-end (see §4.2); `approval_snapshot` partially duplicates native workflow audit.
   → Make `Superseded` `doc_status: 2` so Supersede drives `doc.cancel()`, remove the unreachable
   `Cancel` state, and **keep `approval_snapshot`** for the IATF signature trail (justified), noting the
   overlap. (Findings 17, 35.)
8. **frappe-less test mode + pytest emulation (low, pervasive).** `try: import frappe` shims in
   production services/controllers; `unittest_adapter.py` reimplements pytest
   (`approx/raises/parametrize/fixtures`); `factories.py` hand-rolls cleanup vs `FrappeTestCase`
   rollback. → **Full bench-native** (decision approved): remove all shims and the emulation layer;
   pure-domain logic lives in frappe-free modules but is run under `FrappeTestCase` + the bench runner.
   The **test-infra half landed via develop merge 2026-06-13** — `unittest_adapter.py` deleted,
   `tests/base.py` now a 26-line bench-native v16-first/v15-fallback `FrappeTestCase` probe, and the
   frappe-less TEST mode + `@skipUnless` guards removed (Findings 16, 36 done; factories cleanup
   reworked, Finding 15). The **production `_FrappeCompat`/`try: import frappe` shims STILL remain in
   scope** (Findings 11, 18, 31, 34). (Findings 11, 15, 16, 18, 31, 34, 36.)
9. **Patch conventions (low) — mostly moot.** Import guards, missing `reload_doc`, hand-rolled
   `has_column`. Resolved by dropping the patches in §6. (Findings 19, 20, 21, 22.)
10. **Fixtures / versioning (low).** Custom Field fixture filter exports Work Order / Production Plan
    that have no fields → scope to BOM; `create_revision` nulls child linkage `copy_doc` already
    handles → let `copy_doc` localize, clear only app fields. (Findings 4, 33.)

Themes 1–3 are the same machinery the native lifecycle replaces, so they are implemented **with** the
release/cancel redesign, not as separate upfront edits. Themes 4–10 are independent Phase 0b edits,
each behind a characterization or new test.

## 8. Phase 1 — LH/RH symmetric parts (A2)

### 8.1 Data model
Keep `finished_part_code` as the primary finished part (drives strip calc + net weight). Add three
**parent fields** — no new child table:

- `is_lh_rh` (Check) — "Symmetric LH/RH part?".
- `orientation` (Select: `LH` / `RH`; `depends_on: is_lh_rh`; mandatory when checked) — the orientation
  of the **primary** `finished_part_code`. The twin is the opposite orientation (derived).
- `twin_finished_part` (Link → Item; `depends_on: is_lh_rh`; mandatory when checked) — the symmetric
  twin item code.

The twin is structurally identical to the primary — same weights, parts/sheet, and end pieces —
differing only in item code and orientation. The pair is exactly two items.

The existing read-only mirror `finished_parts` (doctype `Layout Finished Part`) is **reused** to display
both produced items and their BOMs after release. Add a `generated_bom` (Link → BOM) column to that
child doctype — `release_service::_layout_bom_names` already reads `row.generated_bom`, but the doctype
has no such field, a latent mismatch this closes — plus an `orientation` column for clarity.

### 8.2 Release
`_parent_finished_part_rows` returns `[primary]`, or `[primary, twin]` when `is_lh_rh` → the existing
`_generate_boms` loop emits one structurally-identical Shearing BOM per item code. **Both BOMs set
`sheet_cutting_layout = this layout`** (already done in `_insert_frappe_bom`), so both reference the same
Sheet Cutting Layout. `_sync_finished_part_reference_rows` fills the `finished_parts` mirror with both
rows (item, orientation, generated BOM, quantities). With the Phase-0 fix, the parent `generated_bom`
holds the primary's BOM; the mirror holds both.

### 8.3 Validation
When `is_lh_rh`: `orientation` and `twin_finished_part` are required; the twin code is alphanumeric +
ends `SHR`, distinct from the primary and from the raw material. Net/gross/scrap are shared across the
pair.

### 8.4 Export interaction
The part-number cell joins the pair as **full item codes, `/`-joined** (e.g.
`0102AAG06400SHR/0102AAG06410SHR`); the part-name/label uses the orientations (e.g. "… LH & RH").
The generated BOM keeps the **primary** item code only.

> **Decision 2026-06-16:** the part-number cell uses the full item codes joined with `/`, NOT a
> common-prefix short form (`0102AAG06400_6410N`). The short-form `joined_part_number_label`
> /`_common_prefix_length` helpers proposed in the Phase 1 plan are superseded and were not built.

### 8.5 Tests
- Unit: pair expansion (`is_lh_rh` → `[primary, twin]`; unchecked → `[primary]`); orientation/twin
  validation; joined part-number + LH/RH labeling.
- Integration: an LH/RH layout → two identical BOMs **both linked to the same layout**; the
  `finished_parts` mirror shows both with orientation + BOM; supersede/cancel retire **both** BOMs
  (`_layout_bom_names` gathers them — assert it).
- E2E: check "LH/RH", pick twin + orientation, release → both items/BOMs shown in the mirror, both
  referencing the layout.

## 9. Phase 3 — Hybrid recursive end-piece layouts (A3)

(Phase 2 follows in §10; recursion is described first because the lifecycle thread lands here.)

### 9.1 Data model
Add optional **`child_layout`** (Link → Sheet Cutting Layout) to `Layout End Piece`, shown when
`disposition = Reuse`.

### 9.2 Semantics (hybrid)
- `child_layout` **unset** → today's behaviour (simple end-piece item + simple BOM).
- `child_layout` **set** → the end piece's generated item becomes the child layout's
  `raw_material_item`; the child is a full Sheet Cutting Layout with its own approval/release that owns
  the real BOM. The parent BOM still carries the end piece as a byproduct row (consumed by the child as
  raw material — no double counting; the existing weight-balance validator already accounts for
  byproducts).

### 9.3 Guards (native validation)
- Child `raw_material_item` must equal the parent end-piece item.
- Cycle / self-reference prevention (a layout cannot be its own ancestor) — guarantees the §4.3 cascade
  terminates.
- A child cannot be released before the parent's end-piece item exists.

### 9.4 Lifecycle cascade
Implemented by the native `on_cancel`/`on_trash` cascade of §4.3 (cancel children depth-first, retire
BOMs, `ignore_linked_doctypes=["BOM"]`, framework-gated delete).

### 9.5 Simplification to evaluate during build
Once recursion exists, assess whether `end_piece_bom_service` for *complex* reuse is superseded by child
layouts (keep the simple path; deprecate only the overlap). Decide in the implementation plan.

### 9.6 Tests
- Unit: cascade-graph traversal order; cycle detection; child raw-material equality.
- Integration: end piece → child layout → its own end piece (2 levels); release builds all BOMs;
  cancel/supersede parent cascades — every descendant layout cancelled, every BOM deactivated;
  cancel blocked natively when a descendant BOM is consumed by a Manufacture Stock Entry; delete gated.
- E2E: link a child layout → release → supersede parent → child + all BOMs show retired.

## 10. Phase 2 — Excel / IATF export (A1)

### 10.1 Approach
New frappe-free `services/export_service.py` + a thin Frappe entry point. It opens the curated
`FRM/PRD/15` template shipped at `sheet_cutting_layout/templates/iatf/sheet_cutting_layout.xlsx`,
populates cells via `openpyxl` (bundled with Frappe), and streams `.xlsx` back through the native
file-download response. `.xlsx` only (no PDF this round).

### 10.2 Template
One canonical **blank** `FRM/PRD/15` page curated from the 38-sheet sample workbook. **Open input:**
the curated template must be confirmed as the audit-approved one before Phase 2 closes.

### 10.3 Cell map (codified, from the approved sheet)
Representative (finalized in the implementation plan against the curated template):

- `B1` company · `G5` part name · `N5` joined part numbers (LH_RH) · `B6` project name (merged `B6:F6`; name only — decision 2026-06-16, no project code)
- `K8` thickness · `K9/L9/M9` sheet T/W/L · `K10` strip weight · `K11/L11/M11` strip T/W/L ·
  `K12` parts/strip · `K13` no. strips · `K14` parts/sheet · `K15/K16/K17` gross/net/scrap per part
- Right-side BOM table `O7:U11` and the end-piece detail blocks from `end_pieces`
- Signature blocks (row 38) left **blank** (decision: physical signatures)

### 10.4 Entry point
Whitelisted `download_sheet_cutting_layout(name)` (permission-checked, read) + a "Download Layout
(Excel)" form button.

### 10.5 Recursion interaction (integration step)
Multi-sheet workbook: parent page + one page per linked `child_layout` (mirrors the sample's
multi-sheet structure). Built in the final integration PR once Phase 3 lands.

### 10.6 Tests
- Unit: cell-mapping (layout → cell values), joined part-number rendering, missing-data guards.
- Integration: export a persisted layout → valid workbook with expected cell values; multi-twin join.
- E2E: form button downloads a non-empty `.xlsx`.

## 11. Branch & PR strategy

- This spec + the per-phase implementation plans live on `feature/scl-iatf-export-lhrh-recursion`.
- Phase 0 and Phase 1 land sequentially via PRs to `develop`; Phases 2 and 3 branch off post-Phase-1
  and merge independently; a final integration PR wires export ↔ recursion.
- TDD throughout per `AGENTS.md` / `docs/development-philosophy.md`; every feature gates on the three
  test layers (§4.4).

## 12. Appendix — confirmed framework-conformance findings

36 confirmed (3 high / 13 medium / 20 low); 6 false positives pruned by the adversarial pass. Each was
cross-checked against the installed Frappe v15 / ERPNext v15.101 source. Findings 16 and 36 (test-infra)
**landed via the develop merge 2026-06-13** and are struck through below; all production-side findings
(including the `_FrappeCompat` shims 11/18/31/34 and the native-lifecycle cluster) remain open.

| # | Sev | File:lines (symbol) | Native fix |
|---|-----|---------------------|-----------|
| 1 | high | release_service.py:225-239 (`_clear_item_default_bom_reference`) | Let `BOM.on_cancel`/`manage_default_bom` manage `Item.default_bom`; delete helper |
| 2 | high | release_service.py:147-176 (`deactivate_generated_bom`; raw `db_set` status="Superseded" at 159/168) | Retire via `doc.cancel()` / `is_active` through `on_update_after_submit`; stop raw `db_set` of is_active/status |
| 3 | high | sheet_cutting_layout.py:50-101,198-222 (`before_workflow_action`/`_apply_workflow_action_effects`/`apply_*`) | Drop `apply_workflow` override + flags; release from `on_submit`, retire from `on_cancel` |
| 4 | med | hooks.py:33 (Custom Field fixture) | Scope fixture filter to BOM (WO/Production Plan have no fields) |
| 5 | med | patches/v1_0_submit_released_layouts.py:13-19 | Use `doc.submit()` not raw `set_value` of docstatus (moot — patch dropped) |
| 6 | med | bom_service.py:91-121,294-299 (scrap rate) | Append scrap rows without `rate`; let BOM compute via `get_rm_rate` |
| 7 | med | bom_service.py:58-69 (`BomDocument` status/disabled) | Use only `is_active`/`is_default` + submit/cancel; drop non-schema fields |
| 8 | med | end_piece_item_service.py:177-192 (valuation backfill) | `doc.save()` so Item hooks run |
| 9 | med | release_service.py:179-222 (`cancel_generated_bom`) | `on_cancel` + `ignore_linked_doctypes` + `frappe.database.savepoint` |
| 10 | med | release_service.py:104-144 + controller:50-101 (`release_layout` from validate) | Drive release from `on_submit`, not `validate()` |
| 11 | med | validators.py:16-30 (`_FrappeCompat` shim) | Remove shim; unconditional `import frappe`; pure logic in frappe-free modules |
| 12 | med | sheet_cutting_layout.json:327-340 (permissions) | Add PM/Purchase/MR perm blocks (read/write, submit/cancel) |
| 13 | med | release_service.py:147-239 (BOM retire/default) | Native cancel/save lifecycle for retirement + default mgmt |
| 14 | med | release_service.py:160-171,546-558 (submitted `db_set`) | `allow_on_submit`/`on_update_after_submit` + `doc.save()`; native BOM cancel/save |
| 15 | med | tests/factories.py:98 (`cleanup_test_records` sweep) | `FrappeTestCase` rollback (`addClassCleanup`/`_rollback_db`) |
| 16 | med | ~~tests/unittest_adapter.py (pytest emulation)~~ — **DONE (develop merge 2026-06-13)**: adapter file deleted; suites use `unittest`/`FrappeTestCase` primitives | — |
| 17 | low | fixtures/workflow.json (Superseded docstatus-1 dead-end; `Cancel` unreachable) | Set `Superseded` doc_status 2 (Supersede → `doc.cancel()`); remove `Cancel` state + its status-option/fixture entries |
| 18 | low | overrides/bom.py:3-19 (import guard) | Remove shim; bench-native tests |
| 19 | low | patches/v1_0_backfill_mr_approval_snapshots.py:6-16 | Unconditional `import frappe` (moot — patch dropped) |
| 20 | low | patches/v1_0_mark_cancelled_layouts_and_unlink_boms.py:3-11 | Unconditional `import frappe` (moot — patch dropped) |
| 21 | low | patches/v1_0_migrate_checked_workflow_state_to_pm_approved.py:3-16 | Unconditional `import frappe` (moot — patch dropped) |
| 22 | low | (same patch):18-52 (`_has_column`) | `frappe.reload_doc` + `frappe.db.has_column` (moot — patch dropped) |
| 23 | low | end_piece_bom_service.py:105-116 (BOM Item) | Append only item_code/qty/uom; let `update_stock_qty` compute |
| 24 | low | end_piece_bom_service.py:92,95 (`bom.uom`) | Omit; `validate_main_item` sets it from FG Item |
| 25 | low | end_piece_bom_service.py:170-219 (`_persist_generated_links`) | `doc.db_set` directly; drop fallback ladder |
| 26 | low | end_piece_bom_service.py:230-251 (`_company_for_layout`) | `erpnext.get_default_company()` |
| 27 | low | end_piece_item_service.py:124-229 (`_get_value`) | `frappe.get_cached_value` for stable Item config |
| 28 | low | end_piece_item_service.py:124-229 (None name) | Guard `None` name before `get_value` |
| 29 | low | end_piece_item_service.py:132,165-174 (UOM rows) | Append only non-stock UOM; controller adds stock UOM |
| 30 | low | end_piece_item_service.py:134 (`ignore_permissions`) | Drop elevation or justify with explicit perm check |
| 31 | low | end_piece_item_service.py:5-31 (`_FrappeCompat`) | Remove shim; bench-native tests |
| 32 | low | release_service.py:378-439 (`_insert_frappe_bom`) | Set only input fields; let `validate()` compute rate/status |
| 33 | low | versioning.py:73-89 (`_reset_child_row`) | Let `copy_doc` localize children; clear only app fields |
| 34 | low | controllers (`try: import frappe` + stub Document) | Bench-native tests; remove stub Document/whitelist |
| 35 | low | workflow.py:33-64 (`record_approval_snapshot`) | Keep for IATF trail; note overlap with native workflow audit |
| 36 | low | ~~tests/base.py (FrappeTestCase fallback)~~ — **DONE (develop merge 2026-06-13)**: `base.py` now a 26-line bench-native v16-first/v15-fallback `FrappeTestCase` probe (`SheetCuttingLayoutTestCase`) | — |

## 13. Open items

- Curated `FRM/PRD/15` blank template confirmed as the audit-approved page (Phase 2 gate).
- ~~During Phase 3: whether `end_piece_bom_service` complex-reuse path is superseded by child
  layouts.~~ **Resolved (Phase 3):** keep both. End-piece rows without `child_layout` use the simple
  `end_piece_bom_service` item+BOM path unchanged; rows with `child_layout` route the real BOM to the
  child layout and are excluded from `_reuse_end_pieces`. The two paths are mutually exclusive per row,
  so neither is deprecated.
