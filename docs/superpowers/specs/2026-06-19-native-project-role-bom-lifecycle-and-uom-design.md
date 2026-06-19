# Native Project Role, BOM Lifecycle, and Generated Item UOM Design

## Summary

This design replaces the app-owned Project Manager role usage with ERPNext's native `Projects Manager`
role, removes the custom app-controlled BOM update flag, aligns generated BOM lifecycle with native
Frappe link handling, standardizes alternate UOM rows for every Item created by Sheet Cutting Layout,
and makes strip thickness read-only because it mirrors material thickness.

The goal is to delete app-specific ownership mechanisms where Frappe already gives us enough structure,
while keeping the minimum explicit workflow sequencing needed for cancel/delete to succeed.

## Scope

This design covers:

1. workflow role replacement from the custom Project Manager role to ERPNext native `Projects Manager`
1. generated BOM lifecycle and cancel/delete behavior for Sheet Cutting Layout
1. generated Item alternate UOM creation and repair
1. strip thickness UI behavior

This design does not cover:

1. unrelated workflow expansion
1. broad refactors outside generated BOM and generated Item paths
1. removal of the stored `strip_thickness_mm` field from the schema
1. speculative export redesigns or unrelated BOM-service cleanup

## Current Problems

1. The app still owns workflow role naming instead of reusing ERPNext's native `Projects Manager`
   role.
1. Generated BOM lifecycle relies on `APP_CONTROLLED_BOM_UPDATE_FLAG`, which is an app-specific bypass
   for BOM validation and cancellation behavior.
1. Frappe native links already model parent-child references, but the app currently mixes that with
   custom ownership flags instead of letting links do most of the work.
1. Generated Items do not yet have one explicit rule for alternate UOM rows across all app-created
   Items.
1. `strip_thickness_mm` is user-editable even though it should always match the material thickness.

## Approved Decisions

1. Replace the app-owned Project Manager role everywhere the app owns it with ERPNext native
   `Projects Manager`.
1. Remove `APP_CONTROLLED_BOM_UPDATE_FLAG` and the custom override path that exists only to permit
   app-owned BOM updates.
1. Keep generated BOMs linked back to the layout through `sheet_cutting_layout`.
1. Use native Frappe link behavior for ownership and delete protection instead of a custom ownership
   flag.
1. Keep the minimum app-side sequencing required for layout cancel/delete:
   - cancel generated BOMs first
   - then continue layout cancel/delete flow
1. Every Item created by Sheet Cutting Layout must have an alternate UOM row and conversion factor.
1. RM and scrap Items are unchanged because the app does not create them.
1. `strip_thickness_mm` becomes read-only and mirrors `sheet_thickness_mm`.
1. Alternate UOM conversion factors must follow ERPNext-native conversion semantics, not a custom
   interpretation.

## Workflow Role Design

## Native Role Replacement

1. Replace the custom Project Manager role reference with ERPNext native `Projects Manager` in:
   - workflow configuration
   - fixtures the app owns
   - tests and helpers the app owns
1. Do not keep both role names for compatibility in this change.
1. Any app-owned workflow-access tests should assert against the native role name only.

## Effect on Workflow States

No workflow state names or transitions change in this design.

The current state model remains:

1. `Draft`
1. `Submitted for Check`
1. `PM Approved`
1. `Approved by Purchase`
1. `Released`
1. `Rejected`
1. `Superseded`

Only the role attached to the project-manager approval responsibility changes.

## Generated BOM Lifecycle

## Ownership Model

1. A BOM generated from Sheet Cutting Layout remains identified by `sheet_cutting_layout = <layout>`.
1. Layout fields such as `generated_bom`, `twin_generated_bom`, and row-level
   `generated_end_piece_bom` remain the app's convenience links.
1. Native Frappe link behavior becomes the primary ownership guard.

## Remove Custom BOM-Control Flag

1. Delete `APP_CONTROLLED_BOM_UPDATE_FLAG`.
1. Delete `mark_bom_app_controlled()`.
1. Remove the corresponding bypass branch from BOM override validation.
1. Any remaining BOM restriction logic must be expressible directly from document state, for example:
   - this BOM is linked to a Sheet Cutting Layout
   - this action is not allowed on linked generated BOMs

If a narrow BOM hook is still needed after removing the flag, it should read only native document
fields and action context. It should not create a second ownership channel.

## Cancel Behavior

Frappe links do not natively infer business actions like "cancel children before parent cancel", so
the app still needs explicit sequencing.

Approved behavior:

1. Released layouts are still cancelled only through the `Supersede` path.
1. During layout cancel:
   - gather all generated BOMs linked to the layout
   - cancel those BOMs first
   - then continue descendant layout and parent layout cancellation
1. This sequencing satisfies native link rules instead of bypassing them.

## Delete Behavior

1. Deletion remains a post-cancel cleanup path, not an active lifecycle transition.
1. During `on_trash`, clear remaining reverse links only where needed to satisfy native delete rules.
1. Do not auto-delete live generated BOMs from a non-cancelled layout.

## Main and End-Piece BOM Creation

This design does not change when BOMs are created:

1. main shearing BOM is created at release
1. end-piece BOMs are created from the existing end-piece generation action

This design only changes how those BOMs are treated after creation:

1. no app-control flag
1. native link ownership
1. explicit cancel sequencing

## Generated Item UOM Design

## Rule

Every Item created by Sheet Cutting Layout must include:

1. its stock UOM
1. one alternate UOM row
1. a conversion factor using ERPNext-native semantics

RM and scrap Items are left unchanged because the app does not create them.

## Item Types

### Finished Items Created by the App

1. stock UOM: `Nos`
1. alternate UOM: `Kg`
1. factor source: finished-item net weight

### End-Piece Items Created by the App

1. stock UOM: `Kg`
1. alternate UOM: `Nos`
1. factor source: end-piece weight

## Conversion Semantics

The app must not guess the direction of `conversion_factor`.

Implementation requirement:

1. verify how ERPNext interprets `conversion_factor` between stock UOM and alternate UOM in this
   codebase
1. set both finished-item and end-piece alternate rows using that exact rule
1. add tests that assert the ERPNext-native direction, not just row presence

If ERPNext expects reciprocal values depending on which UOM is stock, the helper should encode that
once and reuse it.

## Repair Behavior for Existing App-Created Items

1. If the app touches an existing generated Item and the required alternate UOM row is missing, add
   or repair it in place.
1. Do not create duplicate UOM rows.
1. Do not add a migration unless repo evidence shows the missing-UOM issue is already widespread.

This keeps the change incremental and avoids a speculative data patch.

## Implementation Boundary

Use one shared helper for:

1. ensuring the required alternate UOM exists
1. validating the source factor is positive
1. applying ERPNext-native conversion semantics
1. preventing duplicate child rows

Call that helper from each Sheet Cutting Layout item-creation path.

## Strip Thickness Design

1. `strip_thickness_mm` becomes read-only in the doctype UI.
1. Effective thickness should come from `sheet_thickness_mm`.
1. Keep `strip_thickness_mm` stored for compatibility with current formulas, exports, and tests.
1. Validation and formula paths should treat the strip thickness as mirrored from material thickness
   so users cannot drift them apart.

This is intentionally small. It removes user drift without forcing a schema change in the same work.

## Error Handling

1. If generated BOM cancellation fails during layout cancel, stop the layout cancel and surface the
   real BOM cancellation error.
1. If alternate-UOM factor input is zero, negative, or missing, fail Item creation/update with a
   specific message rather than silently creating a partial Item.
1. If the native `Projects Manager` role is missing in a test fixture, fix the fixture; do not
   silently recreate the custom role.

## Testing

Add focused tests only where behavior changes:

1. workflow/fixture coverage uses native `Projects Manager`
1. generated BOM cancel path cancels linked BOMs before the layout cancel completes
1. generated layout delete path succeeds without the app-control flag
1. generated finished Items receive the required alternate UOM row
1. generated end-piece Items receive the required alternate UOM row
1. conversion-factor assertions follow ERPNext-native semantics
1. missing alternate UOM rows on previously-created generated Items are repaired when touched
1. `strip_thickness_mm` is read-only and mirrors material thickness in validation/UI behavior

Avoid adding broad end-to-end coverage unless one of these paths cannot be proven with the existing
bench-native test style.

## Risks and Trade-Offs

1. Removing the app-control flag simplifies the model, but only if cancel sequencing is explicit.
   Native links alone will block invalid parent actions; they will not perform child-state changes for
   us.
1. Replacing the custom role reduces maintenance, but it assumes ERPNext native role naming is the
   stable contract this app should depend on.
1. Keeping `strip_thickness_mm` in the schema is redundant, but it avoids unnecessary churn while we
   tighten the user-facing behavior.
1. Repair-on-touch for generated Item UOM rows is cheaper than a migration, but it will not fix old
   generated Items until the app encounters them again.
