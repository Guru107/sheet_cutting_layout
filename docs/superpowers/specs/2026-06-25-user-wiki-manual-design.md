# User Wiki Manual Design

## Goal

Create a user-facing GitHub wiki for `sheet_cutting_layout` that explains how end users work with the module in day-to-day operations.

The wiki is for business users only. It must not include code, configuration details, fixtures, technical implementation notes, or developer workflows.

## Audience

This manual is for:

- Projects User
- Projects Manager
- Purchase Manager
- MR Coordinator

It is not for developers, bench administrators, or system implementers.

## Scope

The wiki will cover the full supported user workflow:

- creating a layout
- saving and editing drafts
- submitting for check
- approving layouts
- purchase approval
- releasing layouts
- viewing generated BOM references
- creating a new version
- superseding a released layout
- LH/RH layouts
- end-piece BOM generation
- export and download
- rejection and resubmission
- common user-facing mistakes and recovery steps

## Out of Scope

Do not include:

- code snippets
- commands
- bench setup
- permissions internals
- fixture names
- test details
- migration notes
- patch behavior
- technical architecture
- database or API details

## Recommended Documentation Shape

Use a task-first multi-page wiki.

This is the recommended page set:

1. `Home`
2. `Typical Workflow`
3. `Create a Layout`
4. `Submit and Approve Layouts`
5. `Release and Generated BOMs`
6. `Revisions and Supersede`
7. `LH/RH Layouts`
8. `End-Piece BOM Generation`
9. `Export and Download`
10. `Troubleshooting`

## Why This Shape

This structure is the best fit because:

- users search by task, not by implementation detail
- the module has a clear business workflow with role handoffs
- advanced features can be documented without mixing them into the basic path
- screenshots fit naturally into step-based pages

Alternative role-based pages were considered, but a task-first structure is easier to use when multiple roles interact on the same document over time.

## Page Pattern

Each page should follow the same structure:

1. `When to use this page`
2. `Before you begin`
3. `Steps`
4. `What happens next`
5. `Common mistakes`
6. `Screenshots`

### Writing Style

The manual should:

- use plain business language
- stay close to what the user sees in the UI
- prefer numbered task steps over long prose
- explain outcomes in workflow terms
- avoid technical words unless they are visible product labels

Use the real workflow state names users see:

- `Draft`
- `Submitted for Check`
- `PM Approved`
- `Approved by Purchase`
- `Released`
- `Superseded`

## Page-by-Page Design

### 1. Home

Purpose:

- explain what the module is for
- explain who uses it
- link to each task page

Content:

- short overview of the module
- short role summary
- quick links to the full workflow and common tasks

### 2. Typical Workflow

Purpose:

- show the complete happy path from draft to release

Content:

1. Projects User creates a draft
2. Projects User submits it for check
3. Projects Manager approves it
4. Purchase Manager approves it
5. MR Coordinator releases it
6. User views the released record and generated BOM references

This page should act as the first page a new user reads.

### 3. Create a Layout

Purpose:

- help Projects Users create accurate draft layouts

Content:

- when to create a new layout
- which core business fields matter most
- how to save and return later
- what a valid draft should contain before submission

### 4. Submit and Approve Layouts

Purpose:

- cover submission, review, rejection, and rework

Content:

- Projects User submits a draft
- Projects Manager approves submitted layouts
- Purchase Manager approves PM-approved layouts
- rejection returns the layout to `Draft`
- what users should do after rejection

### 5. Release and Generated BOMs

Purpose:

- show what happens when a layout is released

Content:

- MR Coordinator releases the layout
- release changes status to `Released`
- generated BOM references appear on the layout
- how the user confirms release succeeded

### 6. Revisions and Supersede

Purpose:

- explain how users update or retire released layouts

Content:

- when to use `New Version`
- what is copied into the new draft
- when to use `Supersede`
- what superseding means from a user perspective

### 7. LH/RH Layouts

Purpose:

- explain paired left-hand/right-hand layouts for users who need them

Content:

- when LH/RH should be used
- how to fill the LH/RH-specific fields
- what users should expect after release

This page should be marked as an advanced workflow page.

### 8. End-Piece BOM Generation

Purpose:

- explain how users work with reusable end pieces after release

Content:

- when end-piece BOM generation is needed
- how reusable end pieces should appear before generation
- how users trigger generation
- how users confirm it succeeded

This page should be marked as advanced.

### 9. Export and Download

Purpose:

- show users how to export or download layout output

Content:

- when export is useful
- where to trigger it
- what users should expect after download

### 10. Troubleshooting

Purpose:

- provide user-facing recovery steps without technical internals

Content:

- cannot submit a draft
- layout sent back to `Draft`
- release did not complete
- generated BOM references not visible
- end-piece BOM generation did not complete
- export/download did not behave as expected

Each troubleshooting item should answer:

- what the user is seeing
- the likely user-facing cause
- what to do next
- who to contact or which role should act next, when applicable

## Screenshot Plan

Use real screenshots from the actual app flow.

Recommended capture set:

- draft layout
- submitted layout
- PM approved layout
- approved by purchase layout
- released layout
- new draft form
- completed draft before submit
- release action result with BOM references
- new version result
- superseded layout
- LH/RH fields
- released LH/RH result
- reusable end-piece rows
- generated end-piece BOM result
- export or download action
- representative rejection and recovery views

## Screenshot Rules

- use real application screens, not mockups
- capture clean, readable states
- prefer one screenshot per major step
- show workflow actions where they matter
- avoid admin or developer-only screens
- keep screenshots aligned to the exact steps on the page

## Navigation Guidance

The wiki landing page should make it easy to enter from either of these starting points:

- “I am new and want the full workflow”
- “I need help with one task right now”

That means `Home` should link prominently to:

- `Typical Workflow`
- `Create a Layout`
- `Submit and Approve Layouts`
- `Release and Generated BOMs`
- `Troubleshooting`

## Success Criteria

The manual is successful if:

- a new business user can understand the full workflow without reading code or asking a developer
- each role can find its task page quickly
- advanced tasks are documented without cluttering the basic workflow
- screenshots make the UI steps easier to follow
- troubleshooting explains what to do next in business terms

## Delivery Notes

The final deliverable should be written as wiki-ready Markdown, with one file or draft per wiki page.

The content should be prepared for the GitHub wiki at:

- `https://github.com/Guru107/sheet_cutting_layout/wiki`

The writing should stay user-facing from start to finish.
