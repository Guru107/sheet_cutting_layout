# Generated-BOM Visibility Per Part — Design

**Date:** 2026-06-17
**Branch:** `feature/scl-iatf-export-lhrh-recursion`
**Status:** Approved (design)

## 1. Goal

Surface every generated BOM on the Sheet Cutting Layout form as a read-only `Link → BOM`
field that appears **only once the BOM exists**, so a user can open each part's / end piece's
BOM directly from the form:

- **Primary part** → existing parent `generated_bom` (unchanged).
- **Twin part (LH/RH)** → a **new** parent field `twin_generated_bom`, placed directly under
  `generated_bom`, hidden until set.
- **End pieces** → the existing child field `generated_end_piece_bom` on Layout End Piece, made
  to appear only once it is populated.

## 2. Current state (what already exists)

- Parent `Sheet Cutting Layout.generated_bom` — `Link → BOM`, `read_only`, populated on release
  with the **primary** part's BOM (`release_service`). Currently always shown (no `depends_on`).
- `finished_parts` child table (Layout Finished Part) — after release, holds one row per part
  (primary, plus twin when `is_lh_rh`), each with `finished_part_item`, `orientation`, and
  `generated_bom`. The table is gated on `eval:doc.generated_bom`. **Unchanged by this work.**
- `end_pieces` child table (Layout End Piece) — already has `generated_end_piece_bom`
  (`Link → BOM`, `read_only`), **already populated** by `generate_end_piece_boms`
  (`end_piece_bom_service`). It currently has no `depends_on`, so it always shows.

So this is largely a **presentation refinement** plus one new denormalized field and its release-time
population. No change to BOM-generation logic or the `finished_parts` mirror.

## 3. Decisions (from brainstorming)

- **Keep `generated_bom` as-is.** Do not remove, move, or gate the primary field. (Accepted minor
  asymmetry: primary BOM keeps its current position after the weights; the twin BOM is grouped with it.)
- **Twin BOM placement:** the new `twin_generated_bom` goes **immediately after `generated_bom`** in
  `field_order` (not under `twin_finished_part`), grouping the two parent BOM links together.
- **Population approach:** `twin_generated_bom` is a **stored field set during release** (symmetric with
  how `generated_bom` is set), not a virtual/computed field.
- BOM links continue to also live in the child tables (`finished_parts.generated_bom`,
  `end_pieces.generated_end_piece_bom`) — those remain the per-row source; the parent fields are
  convenience pointers.

## 4. Schema changes

### 4.1 Sheet Cutting Layout — new field `twin_generated_bom`
- `fieldtype`: `Link`, `options`: `BOM`
- `read_only`: 1
- `depends_on`: `eval:doc.twin_generated_bom` (visible only once populated)
- `field_order`: inserted immediately **after** `generated_bom` (before `workflow_section`).
- Label: "Twin Part BOM".

### 4.2 Layout End Piece — gate `generated_end_piece_bom`
- Add `depends_on`: `eval:doc.generated_end_piece_bom` (hide in the row detail until populated).
- Ensure `in_list_view`: 1 so it reads as a grid column next to the end piece (blank until generated).
- No fieldtype/population change — it is already `Link → BOM`, `read_only`, and set on generation.

## 5. Population (release)

During release (`release_service`), after the per-part BOMs are generated and the `finished_parts`
mirror is synced:

- The **primary** BOM is already written to `generated_bom` (unchanged).
- When `is_lh_rh`, write the **twin** part's BOM (the RH / twin `finished_parts` row's
  `generated_bom`) into `layout.twin_generated_bom`, using the same supported-field guard the
  primary write uses. When not `is_lh_rh`, `twin_generated_bom` is never set (stays empty → hidden).
- `generated_end_piece_bom` is already written per reuse end piece by `generate_end_piece_boms`
  (unchanged).

On **supersede/new-revision**, `twin_generated_bom` follows the same clearing/copy rules already
applied to `generated_bom` (e.g. cleared on a fresh revision so a new release repopulates it).

## 6. Recursive end-piece behaviour

For a reuse end piece that carries a `child_layout` (the recursive case, spec §9), there is **no**
simple end-piece BOM — the real BOM lives on the child layout and the parent BOM carries the end piece
as a byproduct row. Such rows have no `generated_end_piece_bom`, so the gated field simply stays hidden
for them; they already display `child_layout`. No special handling required.

## 7. IATF export

No change. The export already derives its BOM table from the layout's BOM(s) / `finished_parts`; the new
`twin_generated_bom` is a display-only denormalized pointer and is not read by the exporter.

## 8. Testing (three layers, bench-native)

- **Unit:** releasing an LH/RH layout sets `twin_generated_bom` to the twin row's BOM; a non-LH/RH
  release leaves it empty. `generated_end_piece_bom` population is already covered; add an assertion for
  the `depends_on` gating expressions where unit-testable.
- **Integration (`FrappeTestCase`):** release an LH/RH layout that has a reuse end piece → assert
  `generated_bom`, `twin_generated_bom`, and the end piece's `generated_end_piece_bom` are all
  populated and point at the expected BOMs; a single-part layout leaves `twin_generated_bom` empty.
- **E2E (cypress):** extend `cypress/integration/sheet_cutting_layout_lh_rh.js` to assert the
  `twin_generated_bom` field is present/visible after release; assert the end-piece BOM shows as a
  column once generated. (Release continues to be driven via the workflow API per the existing
  spec's Desk-form note.)

## 9. Out of scope

- Removing, moving, or gating the primary `generated_bom`.
- Changing the `finished_parts` mirror table or BOM-generation logic.
- Any change to end-piece BOM generation, the IATF export, or the recursion model.
