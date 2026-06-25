# Submit and Approve Layouts

## When To Use This Page

Use this page when a layout is ready to move from drafting into formal review and approval. This page is useful for the `Projects User`, `Projects Manager`, and `Purchase Manager` because each role takes a different action in the approval path.

## Before You Begin

Before starting, make sure the layout has already been prepared and saved in `Draft`. The people involved in approval should understand that each step uses a specific workflow action and that the layout moves forward only when the current stage is complete.

The approval path is:

`Draft` -> `Submitted for Check` -> `PM Approved` -> `Approved by Purchase`

## Steps

1. The `Projects User` uses `Submit for Check`.

   This is the first approval handoff. When the `Projects User` is satisfied that the draft is complete, using `Submit for Check` moves the layout from `Draft` to `Submitted for Check`.

2. The `Projects Manager` reviews the layout and uses `Project Manager Approves`.

   At this stage, the `Projects Manager` checks that the layout is acceptable from the project side. When the review is complete, using `Project Manager Approves` changes the status from `Submitted for Check` to `PM Approved`.

3. The `Purchase Manager` reviews the layout and uses `Purchase Approves`.

   After project approval, the layout moves to purchase-side review. When the `Purchase Manager` is satisfied, using `Purchase Approves` changes the status from `PM Approved` to `Approved by Purchase`.

4. If a layout is rejected, it returns to `Draft`.

   A rejection does not end the process. It sends the layout back to `Draft` so the needed corrections can be made clearly before it is submitted again.

5. Continue the work after a rejection.

   When a layout returns to `Draft`, the `Projects User` should update the layout based on the review feedback, save the corrected draft, and send it through the same approval path again using `Submit for Check`.

## What Happens Next

After the layout reaches `Approved by Purchase`, it is ready for release by the `MR Coordinator`. The approval stages are complete, but the layout is not yet the active approved version until `MR Release` is performed.

## Common Mistakes

- Using `Submit for Check` before the draft has been reviewed properly by the `Projects User`.
- Treating `PM Approved` as the final step. The `Purchase Manager` must still use `Purchase Approves`.
- Forgetting that rejected layouts return to `Draft`, not to an approval stage.
- Resubmitting a rejected layout without first correcting the issues that caused the rejection.

## Screenshots

This page should show each approval checkpoint so users can confirm where the layout is in the flow:

- A layout in `Draft` before `Submit for Check`
- A layout in `Submitted for Check`
- A layout in `PM Approved`
- A layout in `Approved by Purchase`
- A rejected layout returned to `Draft`
