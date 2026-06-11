# Sheet Cutting Layout Submitted Derived BOM Lifecycle Design

## Summary

This design refines the June 2 BOM-reference and versioning design by moving every BOM created
from `Sheet Cutting Layout` onto a submitted ERPNext BOM lifecycle. The main shearing BOM created
at `MR Release` and every end-piece BOM created by `Generate End Piece BOMs` will be inserted and
submitted immediately. Layout-owned BOM restrictions will narrow to the real escape hatches that
would bypass layout versioning: `New Version`, `Cancel`, and `Amend`. ERPNext `Update Cost` stays
allowed.

Supersede will operate on all BOMs derived from a layout, not only the parent `generated_bom`.
When a replacement released layout exists, the app will update old BOM references to the new BOMs
where a valid mapping exists. If no replacement BOM exists for a referenced old BOM, supersede
will still proceed and show a structured warning that lists the affected BOMs for manual cleanup.

## Relationship to Prior Design

This spec is a focused follow-on to:

- `docs/superpowers/specs/2026-06-02-sheet-cutting-layout-bom-reference-and-versioning-design.md`

The June 2 design remains the source for:

- parent-driven finished-part inputs
- BOM-backed `finished_parts` reference rows
- save-time BOM drift audit
- layout-driven revisioning

This June 3 spec changes only the derived-BOM lifecycle, layout-derived BOM restrictions, and
supersede/reference-update behavior.

## Goals

1. Make all BOMs created from `Sheet Cutting Layout` follow ERPNext's submitted-BOM lifecycle.
1. Create the main shearing BOM as submitted during `MR Release`.
1. Create end-piece BOMs as submitted during `Generate End Piece BOMs`.
1. Keep `Update Cost` available for layout-derived BOMs.
1. Restrict layout-derived BOM escape hatches that bypass layout-owned versioning:
   - `New Version`
   - `Cancel`
   - `Amend`
1. Keep all BOMs not created from `Sheet Cutting Layout` on native ERPNext behavior with no app
   change.
1. Supersede all BOMs linked to the retired layout, not only the parent `generated_bom`.
1. Attempt BOM reference updates from old derived BOMs to replacement derived BOMs on supersede.
1. Warn, rather than block, when referenced old BOMs have no replacement target.

## Non-Goals

1. No draft lifecycle for layout-derived BOMs after release or BOM generation.
1. No broad override that interferes with ordinary non-layout BOM workflows.
1. No forced supersede blocker when a referenced old BOM has no replacement target.
1. No hidden auto-repair of unmatched BOM references during supersede.
1. No change to the June 2 layout-owned formulas, BOM audit contract, or parent finished-part
   input model.

## Current Problems

1. The main shearing BOM is currently created as a draft BOM and then activated through app logic,
   which fights ERPNext's natural submitted-BOM lifecycle.
1. Layout-derived BOM restrictions are broader than necessary because they compensate for draft BOM
   behavior instead of relying on Frappe's submitted-document rules.
1. End-piece BOMs and the main shearing BOM do not yet share one clear derived-BOM lifecycle
   contract.
1. Supersede currently focuses on the parent-linked BOM and does not fully account for all BOMs
   created from the layout.
1. BOM reference replacement during supersede is not yet explicit when old derived BOMs are still
   referenced upstream.

## Approved Decisions

1. Every BOM created from `Sheet Cutting Layout` will be inserted and submitted immediately.
1. This applies to:
   - the main shearing BOM created during `MR Release`
   - all end-piece BOMs created by `Generate End Piece BOMs`
1. Layout-derived BOMs stay layout-owned; the BOM is not the place where users start a new
   structural version.
1. The app-specific restriction surface narrows to:
   - block `New Version`
   - block `Cancel`
   - block `Amend`
   - allow `Update Cost`
1. Direct edit is not the primary custom restriction because submitted BOMs already inherit Frappe
   native edit limits.
1. BOMs not linked to `sheet_cutting_layout` keep native ERPNext behavior unchanged.
1. Supersede applies to every BOM created from the layout, not just the parent `generated_bom`.
1. Supersede should try to update old BOM references to replacement BOMs from a chosen replacement
   released layout.
1. If a referenced old BOM has no replacement BOM, supersede still proceeds and reports a warning
   block for manual follow-up.
1. Example no-replacement case:
   - an old reuse end-piece BOM exists
   - the replacement layout changes that end piece to `Scrap`
   - the old end-piece BOM still has referencing BOMs

## Data and Identity Rules

## Derived BOM Identification

1. A BOM is layout-derived when `sheet_cutting_layout` is populated.
1. The app must continue writing `sheet_cutting_layout = <layout.name>` on:
   - the main shearing BOM
   - each generated end-piece BOM
1. `generated_bom` on the layout remains the parent-level link to the main shearing BOM only.
1. End-piece BOM discovery for supersede and warning logic should be driven from BOM records linked
   by `sheet_cutting_layout`, not from a second parent-level BOM link field.

## Replacement Layout Selection

1. Supersede requires an explicit replacement released layout.
1. The selected replacement layout must already be released before supersede runs.
1. The replacement layout is the source of replacement derived BOMs for reference updates.
1. If no replacement released layout is chosen, supersede does not proceed.

## Submitted BOM Lifecycle

## Main BOM Release Path

1. `MR Release` will generate the main shearing BOM from the layout as defined in the June 2 spec.
1. The app will:
   - insert the BOM
   - submit the BOM in the same release flow
1. The submitted BOM remains the BOM recorded in parent `generated_bom`.
1. After successful submit:
   - `generated_bom` is written back to the layout
   - BOM-backed `finished_parts` rows are synchronized from the submitted BOM

## End-Piece BOM Generation Path

1. `Generate End Piece BOMs` will create each missing end-piece item as today.
1. For each derived end-piece BOM, the app will:
   - insert the BOM
   - submit the BOM in the same generation flow
1. `end_piece_item_code` remains the row-level link to the generated end-piece item.
1. End-piece BOM generation stays available only after the layout is released.

## Error Handling for Submitted BOM Creation

1. If insert fails, the layout action fails and surfaces the insert error.
1. If submit fails, the layout action fails and surfaces the submit error.
1. The app must not silently leave a partially-created draft BOM presented as a successful
   generated result.
1. Any submit-time ERPNext validation requirements for BOMs must be satisfied by the app-generated
   data before claiming release/generation success.

## Restriction Rules for Layout-Derived BOMs

## Allowed Native Behavior

1. `Update Cost` remains allowed for layout-derived BOMs.
1. Save-time layout audit must tolerate cost refresh effects and must not fail solely because cost
   fields changed through `Update Cost`.
1. Non-layout BOMs keep native ERPNext behavior unchanged, including all ordinary draft/submitted
   lifecycle rules.

## Blocked Escape Hatches

1. `New Version` must be blocked for layout-derived BOMs.
1. `Cancel` must be blocked for layout-derived BOMs.
1. `Amend` must be blocked for layout-derived BOMs.
1. User-facing errors must direct the user back to `Sheet Cutting Layout -> New Version` when they
   try to create a new structural BOM version outside the layout flow.

## Scope of Override Logic

1. Override logic must be narrow and conditional on `sheet_cutting_layout`.
1. The app must not broadly change BOM behavior for:
   - non-shearing BOMs
   - ordinary BOMs not created from this app
1. The override should rely on native submitted-document behavior wherever ERPNext already
   provides the needed restriction.

## Save-Time Layout Audit Interaction

1. The June 2 save-time audit remains in force for layout-owned structural fields.
1. The audit must still catch drift in:
   - BOM item
   - BOM quantity
   - raw material rows
   - scrap rows
   - layout-consumption reconciliation
1. The audit must not treat allowed cost-maintenance updates as structural drift.

## Supersede and Reference Update Behavior

## Supersede Scope

1. Supersede will gather all BOMs linked by `sheet_cutting_layout = <layout.name>`.
1. That set includes:
   - the main shearing BOM
   - any derived end-piece BOMs
1. Supersede deactivates all BOMs in that set.

## Replacement Mapping

1. When a replacement released layout is chosen, supersede will attempt to map old derived BOMs to
   replacement derived BOMs.
1. Main shearing BOM mapping is by the parent finished part.
1. End-piece BOM mapping is by the reuse end-piece identity represented by the old and new layouts.
1. Only valid, unambiguous mappings should be used for BOM reference updates.

## Reference Update Behavior

1. For every old derived BOM that has a valid replacement BOM, supersede should run ERPNext-style
   BOM reference updates from old BOM to new BOM.
1. Reference updates must happen before old BOM deactivation.
1. If an old derived BOM has no replacement target, supersede does not block on that condition.

## Warning Block Behavior

1. When an old derived BOM still has referencing BOMs and no replacement BOM exists, supersede
   must produce a structured warning block.
1. The warning block must list:
   - the old derived BOM
   - the referencing BOMs
   - the reason no replacement exists, for example reuse-to-scrap
1. The warning is informational. Supersede still completes and deactivates the old BOMs.
1. This warning is the user's prompt to manually repair upstream BOM references after supersede.

## Edge Case: Reuse to Scrap

1. If an old end-piece BOM came from a reuse end piece and the replacement layout changes that end
   piece to `Scrap`, the new layout has no replacement end-piece BOM.
1. In that case:
   - no automatic reference target exists
   - the old BOM is still deactivated on supersede
   - the user receives the warning block if upstream BOMs still reference it

## Implementation Boundaries

1. `release_service.py` owns:
   - insert-and-submit flow for the main shearing BOM
   - layout-level supersede of all BOMs tied to `sheet_cutting_layout`
   - reference update orchestration and warning collection
1. `end_piece_bom_service.py` owns:
   - insert-and-submit flow for derived end-piece BOMs
1. `overrides/bom.py` owns:
   - narrow restrictions for layout-derived BOM `New Version`
   - narrow restrictions for layout-derived BOM `Cancel`
   - narrow restrictions for layout-derived BOM `Amend`
   - allowance for `Update Cost`
1. `validators.py` keeps:
   - layout-owned structural audit
   - tolerance for allowed cost-refresh changes
1. The current June 2 parent-field and BOM-reference-table design stays intact outside these
   lifecycle changes.

## Testing Strategy

1. Release test coverage:
   - main BOM is inserted and submitted during `MR Release`
   - `generated_bom` points to the submitted BOM
1. End-piece BOM generation coverage:
   - generated end-piece BOMs are inserted and submitted
1. Restriction coverage:
   - layout-derived BOM `Update Cost` is allowed
   - layout-derived BOM `New Version` is blocked
   - layout-derived BOM `Cancel` is blocked
   - layout-derived BOM `Amend` is blocked
   - non-layout BOM behavior is unchanged
1. Supersede coverage:
   - all BOMs linked to the layout are deactivated
   - mapped old BOM references are updated to replacement BOMs
   - unmatched referenced BOMs produce warning details without blocking supersede
   - reuse-to-scrap edge case produces a warning for unmatched incoming references
1. Audit coverage:
   - structural drift still fails save
   - allowed cost-refresh behavior does not fail the save-time audit

## Trade-Offs

1. Submitted derived BOMs are closer to ERPNext native behavior and reduce custom draft-BOM
   handling, but they force full BOM validity earlier in the release/generation path.
1. Narrow override rules are safer than a blanket BOM lock, but they require accurately targeting
   `New Version`, `Cancel`, and `Amend` without interfering with allowed operations.
1. Warning-only supersede behavior stays close to ERPNext's permissive BOM retirement behavior,
   but it leaves manual upstream cleanup in the user's hands when no replacement BOM exists.
