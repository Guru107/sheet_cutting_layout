# Sheet Cutting Layout User Manual

Welcome to the user manual for the Sheet Cutting Layout module. This manual is written for ERP users who create, review, approve, release, and maintain sheet cutting layouts as part of everyday work.

## What This Module Is For

The Sheet Cutting Layout module helps your team record how a sheet will be used to produce parts, move that layout through business approval, and release it for downstream use. It gives everyone a shared record of what was prepared, what was approved, and what is currently active.

This manual focuses on the practical tasks users perform in the system, from creating a first draft to retiring an older released layout when a new version is ready.

## Who Uses It

Different users work with the same layout at different points in the process:

- `Projects User` prepares the layout, fills in the required details, and sends it forward for review.
- `Projects Manager` checks the submitted layout and approves it from the project side.
- `Purchase Manager` reviews the approved layout before it moves to release.
- `MR Coordinator` releases approved layouts for use and uses `Supersede` when a released layout must be retired.

## Start Here

If you are new to this module, start with [Typical Workflow](Typical-Workflow.md). It explains the full path a layout usually follows and shows where each role takes over.

After that, move to the page that matches the task you need to complete today:

- Creating a new layout: [Create a Layout](Create-a-Layout.md)
- Sending a layout through approval: [Submit and Approve Layouts](Submit-and-Approve-Layouts.md)
- Releasing a layout and understanding generated BOMs: [Release and Generated BOMs](Release-and-Generated-BOMs.md)
- Replacing an older released layout: [Revisions and Supersede](Revisions-and-Supersede.md)

## Pages In This Manual

- [Typical Workflow](Typical-Workflow.md)
- [Create a Layout](Create-a-Layout.md)
- [Submit and Approve Layouts](Submit-and-Approve-Layouts.md)
- [Release and Generated BOMs](Release-and-Generated-BOMs.md)
- [Revisions and Supersede](Revisions-and-Supersede.md)
- [LH/RH Layouts](LH-RH-Layouts.md)
- [End Piece BOM Generation](End-Piece-BOM-Generation.md)
- [Export and Download](Export-and-Download.md)
- [Troubleshooting](Troubleshooting.md)

## Module Settings

`Sheet Cutting Layout Settings` is a single-record setup used only for the exported Excel header. It lets a `System Manager` maintain the logo, document number, revision number, revision date, and page text that appear when users run `Download Layout (Excel)`.

These settings do not control layout calculations, approval flow, release behavior, BOM generation, or revision logic. For the user-facing export impact, see [Export and Download](Export-and-Download.md).
