# LH/RH Layouts

## When To Use This Page

Use this page when a layout covers paired left-hand and right-hand parts that belong together. This is most useful for the `Projects User`, `Projects Manager`, `Purchase Manager`, and `MR Coordinator` when they need to move one paired layout through the normal approval and release flow without splitting the work into separate records too early.

## Before You Begin

Before starting, confirm that the layout really represents a left-hand and right-hand pair that should stay together as one controlled layout flow. Users should treat the pair as one layout for drafting, review, approval, and release.

If the layout is still moving through review, expect it to follow the normal workflow:

`Draft` -> `Submitted for Check` -> `PM Approved` -> `Approved by Purchase` -> `Released`

## Steps

1. Build and review the LH/RH pair as one layout.

   Keep both sides together in the same controlled flow so everyone reviews the same version at the same time. This helps the team avoid approving one side while accidentally working from an older or incomplete version of the other side.

2. Move the layout through the standard approval actions.

   The `Projects User` uses `Submit for Check`, the `Projects Manager` uses `Project Manager Approves`, the `Purchase Manager` uses `Purchase Approves`, and the `MR Coordinator` uses `MR Release` when the pair is ready for final release.

3. Confirm that the layout becomes `Released`.

   After `MR Release`, check that the layout status changes to `Released`. This shows the LH/RH pair is now the active approved layout that downstream users should follow.

4. Review the finished-part BOM references after release.

   A released LH/RH layout produces separate finished-part BOM references for the two sides. After release, review the layout carefully and look for the separate BOM references tied to the left-hand and right-hand finished parts. Users should recognize that these are separate references even though the pair was controlled as one layout flow.

5. Make sure downstream users are working from the correct side-specific references.

   When sharing the released result, point users to the correct finished-part BOM reference for each side so purchasing, planning, and related follow-up work stay aligned with the intended LH or RH part.

## What Happens Next

Once the LH/RH layout is `Released`, the pair remains one approved layout record, but users should expect separate finished-part BOM references for the two sides. Those references help users identify the correct released result for each finished part while still preserving the paired layout history in one place.

If a released LH/RH layout needs a change later, do not change it in place. Use `New Version` so the next revision can be reviewed and released in a controlled way.

## Common Mistakes

- Treating LH and RH as two unrelated layout flows when they are meant to stay paired.
- Releasing the layout without checking that it actually became `Released`.
- Looking for only one finished-part BOM reference after release instead of recognizing the separate references for the left-hand and right-hand sides.
- Sharing the wrong side-specific reference with downstream users.
- Editing expectations on a released pair instead of starting a new controlled revision with `New Version`.

## Screenshots

The screenshots on this page should help users recognize a paired LH/RH layout before release and confirm the separate finished-part BOM references after the layout becomes `Released`.

- A paired LH/RH layout in `Draft`
- The workflow actions `Submit for Check`, `Project Manager Approves`, `Purchase Approves`, and `MR Release`
- A paired layout in `Released`
- A released LH/RH layout showing separate finished-part BOM references for both sides
