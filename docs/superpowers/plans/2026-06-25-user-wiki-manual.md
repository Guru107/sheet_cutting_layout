# User Wiki Manual Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a complete user-facing GitHub wiki manual for `sheet_cutting_layout`, written only from an end-user perspective and supported by real screenshots from the live app.

**Architecture:** Draft the wiki as a set of Markdown source files in the repo first, using one page per user task. Capture screenshots from the live bench flow after the page text is outlined, then insert the final image references and publish the pages to the GitHub wiki in a final pass.

**Tech Stack:** GitHub wiki Markdown, local bench UI, existing Frappe app workflow, local screenshot capture tools

---

## File Structure

**Create:**
- `docs/user-manual/wiki/Home.md`
- `docs/user-manual/wiki/Typical-Workflow.md`
- `docs/user-manual/wiki/Create-a-Layout.md`
- `docs/user-manual/wiki/Submit-and-Approve-Layouts.md`
- `docs/user-manual/wiki/Release-and-Generated-BOMs.md`
- `docs/user-manual/wiki/Revisions-and-Supersede.md`
- `docs/user-manual/wiki/LH-RH-Layouts.md`
- `docs/user-manual/wiki/End-Piece-BOM-Generation.md`
- `docs/user-manual/wiki/Export-and-Download.md`
- `docs/user-manual/wiki/Troubleshooting.md`
- `docs/user-manual/wiki/assets/` for screenshot files and a short `README.md` describing asset naming

**Modify:**
- `docs/superpowers/specs/2026-06-25-user-wiki-manual-design.md` only if implementation uncovers a user-facing scope mismatch that must be reflected back into the spec

**Reference while writing:**
- `README.md`
- `sheet_cutting_layout/fixtures/workflow.json`
- live Desk screens on `development.localhost` and/or `frappe16.localhost`

---

### Task 1: Create The Wiki Source Folder And Asset Conventions

**Files:**
- Create: `docs/user-manual/wiki/`
- Create: `docs/user-manual/wiki/assets/README.md`

- [ ] **Step 1: Create the folder structure**

Create:

```text
docs/user-manual/wiki/
docs/user-manual/wiki/assets/
```

- [ ] **Step 2: Add the asset naming guide**

Write `docs/user-manual/wiki/assets/README.md` with:

```md
# Wiki Screenshot Assets

Use real screenshots from the live app only.

Naming pattern:

- `typical-workflow-draft.png`
- `typical-workflow-submitted.png`
- `create-layout-filled-draft.png`
- `release-generated-bom-links.png`

Rules:

- prefer lowercase kebab-case filenames
- one screenshot per major user step
- crop for readability, not decoration
- avoid admin-only or developer-only views
```

- [ ] **Step 3: Verify the folder structure exists**

Run:

```bash
find docs/user-manual/wiki -maxdepth 2 -type d -o -type f | sort
```

Expected: the `wiki/` directory and `assets/README.md` appear.

- [ ] **Step 4: Commit**

```bash
git add docs/user-manual/wiki/assets/README.md
git commit -m "docs: add wiki manual workspace"
```

---

### Task 2: Draft The Landing Page

**Files:**
- Create: `docs/user-manual/wiki/Home.md`

- [ ] **Step 1: Write the landing page**

Write `docs/user-manual/wiki/Home.md` with this structure:

```md
# Sheet Cutting Layout User Manual

## What This Module Is For

Sheet Cutting Layout helps your team create, review, approve, release, and update sheet cutting layouts for press parts.

## Who Uses It

- Projects User
- Projects Manager
- Purchase Manager
- MR Coordinator

## Start Here

- If you are new, read [Typical Workflow](Typical-Workflow.md)
- If you need to create a new record, read [Create a Layout](Create-a-Layout.md)
- If you need to release a layout, read [Release and Generated BOMs](Release-and-Generated-BOMs.md)
- If something is blocked, read [Troubleshooting](Troubleshooting.md)

## Pages In This Manual

- [Typical Workflow](Typical-Workflow.md)
- [Create a Layout](Create-a-Layout.md)
- [Submit and Approve Layouts](Submit-and-Approve-Layouts.md)
- [Release and Generated BOMs](Release-and-Generated-BOMs.md)
- [Revisions and Supersede](Revisions-and-Supersede.md)
- [LH/RH Layouts](LH-RH-Layouts.md)
- [End-Piece BOM Generation](End-Piece-BOM-Generation.md)
- [Export and Download](Export-and-Download.md)
- [Troubleshooting](Troubleshooting.md)
```

- [ ] **Step 2: Verify the links are relative and wiki-friendly**

Run:

```bash
sed -n '1,220p' docs/user-manual/wiki/Home.md
```

Expected: all links point to sibling Markdown files by name.

- [ ] **Step 3: Commit**

```bash
git add docs/user-manual/wiki/Home.md
git commit -m "docs: add wiki home page draft"
```

---

### Task 3: Draft The Typical Workflow Page

**Files:**
- Create: `docs/user-manual/wiki/Typical-Workflow.md`

- [ ] **Step 1: Write the workflow page**

Write `docs/user-manual/wiki/Typical-Workflow.md` with this structure:

```md
# Typical Workflow

## When To Use This Page

Read this page if you want to understand the full layout process from draft to release.

## Before You Begin

- You know which part or layout you need to create
- You know which role should act next after your step

## Steps

1. Projects User creates a new layout and saves it in `Draft`
2. Projects User reviews the draft and uses `Submit for Check`
3. Projects Manager reviews the record and approves it
4. Purchase Manager reviews the approved layout and approves it for purchase
5. MR Coordinator performs the release step
6. The released layout shows the final released state and generated BOM references

## What Happens Next

After release, the layout becomes the active released record for that version. If a change is needed later, create a new version instead of editing the released record directly.

## Common Mistakes

- submitting a draft before the core details are complete
- expecting a released layout to behave like an editable draft
- using supersede when a new version is actually needed

## Screenshots

- Draft layout
- Submitted for Check
- PM Approved
- Approved by Purchase
- Released layout
```

- [ ] **Step 2: Check that the language is user-facing**

Run:

```bash
rg -n "fixture|json|api|patch|doctype|controller|bench" docs/user-manual/wiki/Typical-Workflow.md
```

Expected: no matches.

- [ ] **Step 3: Commit**

```bash
git add docs/user-manual/wiki/Typical-Workflow.md
git commit -m "docs: draft typical workflow wiki page"
```

---

### Task 4: Draft The Core Task Pages

**Files:**
- Create: `docs/user-manual/wiki/Create-a-Layout.md`
- Create: `docs/user-manual/wiki/Submit-and-Approve-Layouts.md`
- Create: `docs/user-manual/wiki/Release-and-Generated-BOMs.md`
- Create: `docs/user-manual/wiki/Revisions-and-Supersede.md`

- [ ] **Step 1: Draft `Create-a-Layout.md`**

Write sections:

- `When To Use This Page`
- `Before You Begin`
- numbered `Steps`
- `What Happens Next`
- `Common Mistakes`
- `Screenshots`

The steps must cover:

1. open a new layout
2. fill core layout details
3. save the draft
4. review before submission

- [ ] **Step 2: Draft `Submit-and-Approve-Layouts.md`**

Cover:

1. Projects User submits for check
2. Projects Manager approves submitted layouts
3. Purchase Manager approves PM-approved layouts
4. rejected layouts return to `Draft`
5. how to continue after rejection

- [ ] **Step 3: Draft `Release-and-Generated-BOMs.md`**

Cover:

1. MR Coordinator releases the layout
2. released status confirmation
3. where users see generated BOM references
4. how to confirm release completed

- [ ] **Step 4: Draft `Revisions-and-Supersede.md`**

Cover:

1. when to use `New Version`
2. what users should expect in the new draft
3. when to use `Supersede`
4. what superseded means in practice

- [ ] **Step 5: Verify all four pages use the same pattern**

Run:

```bash
for f in \
  docs/user-manual/wiki/Create-a-Layout.md \
  docs/user-manual/wiki/Submit-and-Approve-Layouts.md \
  docs/user-manual/wiki/Release-and-Generated-BOMs.md \
  docs/user-manual/wiki/Revisions-and-Supersede.md; do
  echo "== $f ==";
  rg -n "^## (When To Use This Page|Before You Begin|Steps|What Happens Next|Common Mistakes|Screenshots)$" "$f";
done
```

Expected: each page shows all six section headings.

- [ ] **Step 6: Commit**

```bash
git add \
  docs/user-manual/wiki/Create-a-Layout.md \
  docs/user-manual/wiki/Submit-and-Approve-Layouts.md \
  docs/user-manual/wiki/Release-and-Generated-BOMs.md \
  docs/user-manual/wiki/Revisions-and-Supersede.md
git commit -m "docs: draft core workflow wiki pages"
```

---

### Task 5: Draft The Advanced Task Pages

**Files:**
- Create: `docs/user-manual/wiki/LH-RH-Layouts.md`
- Create: `docs/user-manual/wiki/End-Piece-BOM-Generation.md`
- Create: `docs/user-manual/wiki/Export-and-Download.md`

- [ ] **Step 1: Draft `LH-RH-Layouts.md`**

Mark it clearly as an advanced page and cover:

1. when LH/RH layouts should be used
2. which extra fields the user fills
3. what changes after release

- [ ] **Step 2: Draft `End-Piece-BOM-Generation.md`**

Mark it as advanced and cover:

1. when reusable end pieces matter
2. how the end-piece rows should look before generation
3. how the user triggers generation
4. how the user confirms success

- [ ] **Step 3: Draft `Export-and-Download.md`**

Cover:

1. when export or download is useful
2. where users trigger it
3. what file/result they should expect

- [ ] **Step 4: Verify no technical leakage**

Run:

```bash
rg -n "sql|api|fixture|controller|migration|coverage|bench" docs/user-manual/wiki/LH-RH-Layouts.md docs/user-manual/wiki/End-Piece-BOM-Generation.md docs/user-manual/wiki/Export-and-Download.md
```

Expected: no matches.

- [ ] **Step 5: Commit**

```bash
git add \
  docs/user-manual/wiki/LH-RH-Layouts.md \
  docs/user-manual/wiki/End-Piece-BOM-Generation.md \
  docs/user-manual/wiki/Export-and-Download.md
git commit -m "docs: draft advanced wiki pages"
```

---

### Task 6: Draft The Troubleshooting Page

**Files:**
- Create: `docs/user-manual/wiki/Troubleshooting.md`

- [ ] **Step 1: Write the troubleshooting page**

Write sections for:

- cannot submit a draft
- layout returned to `Draft`
- release did not complete
- generated BOM references are missing
- end-piece BOM generation did not complete
- export/download did not behave as expected

Each item must answer:

1. what the user sees
2. likely business-facing cause
3. what to do next
4. which role acts next, if needed

- [ ] **Step 2: Verify the page never tells the user to inspect code or run commands**

Run:

```bash
rg -n "run |command|terminal|bench|git|code|developer" docs/user-manual/wiki/Troubleshooting.md
```

Expected: no user-facing developer instructions.

- [ ] **Step 3: Commit**

```bash
git add docs/user-manual/wiki/Troubleshooting.md
git commit -m "docs: draft troubleshooting wiki page"
```

---

### Task 7: Capture Real Screenshots

**Files:**
- Create: `docs/user-manual/wiki/assets/*.png`
- Modify: all wiki pages to replace screenshot placeholder lists with actual image embeds

- [ ] **Step 1: Prepare a clean live flow for screenshots**

Use the existing local site and create or locate clean records that show:

- Draft
- Submitted for Check
- PM Approved
- Approved by Purchase
- Released
- Superseded
- LH/RH example
- reusable end-piece example
- generated end-piece BOM result
- export/download action

- [ ] **Step 2: Capture the core workflow screenshots**

Save files such as:

```text
docs/user-manual/wiki/assets/typical-workflow-draft.png
docs/user-manual/wiki/assets/typical-workflow-submitted.png
docs/user-manual/wiki/assets/typical-workflow-pm-approved.png
docs/user-manual/wiki/assets/typical-workflow-approved-by-purchase.png
docs/user-manual/wiki/assets/typical-workflow-released.png
```

- [ ] **Step 3: Capture task-specific screenshots**

Save files such as:

```text
docs/user-manual/wiki/assets/create-layout-filled-draft.png
docs/user-manual/wiki/assets/release-generated-bom-links.png
docs/user-manual/wiki/assets/revisions-new-version-result.png
docs/user-manual/wiki/assets/revisions-superseded-layout.png
docs/user-manual/wiki/assets/lh-rh-fields.png
docs/user-manual/wiki/assets/lh-rh-released-result.png
docs/user-manual/wiki/assets/end-piece-reuse-rows.png
docs/user-manual/wiki/assets/end-piece-generated-result.png
docs/user-manual/wiki/assets/export-download-action.png
```

- [ ] **Step 4: Insert screenshot embeds into the wiki pages**

Use standard Markdown image references, for example:

```md
![Draft layout](assets/typical-workflow-draft.png)
```

- [ ] **Step 5: Verify every page with a screenshot renders readable image links**

Run:

```bash
rg -n "^!\\[" docs/user-manual/wiki/*.md
```

Expected: screenshot embeds are present in the pages that need them.

- [ ] **Step 6: Commit**

```bash
git add docs/user-manual/wiki
git commit -m "docs: add wiki screenshots"
```

---

### Task 8: Review And Polish The Wiki Draft

**Files:**
- Modify: all files under `docs/user-manual/wiki/`

- [ ] **Step 1: Run a terminology consistency check**

Run:

```bash
rg -n "Project User|Project Manager|Purchase Approved|Submitted|Released layout can be edited" docs/user-manual/wiki
```

Expected:

- `Project User` and `Project Manager` should not appear
- no incorrect workflow wording appears

- [ ] **Step 2: Run a technical leakage check**

Run:

```bash
rg -n "doctype|fixture|json|patch|controller|sql|api|migration|coverage|bench" docs/user-manual/wiki
```

Expected: no matches in the final user pages.

- [ ] **Step 3: Check all internal links**

Run:

```bash
rg -n "\\]\\([A-Za-z0-9-]+\\.md\\)" docs/user-manual/wiki
```

Expected: all page links point to existing local Markdown files.

- [ ] **Step 4: Manual read-through**

Read each page and check:

- the tone is user-facing
- steps are short and usable
- advanced pages are clearly marked
- troubleshooting tells the user what to do next

- [ ] **Step 5: Commit**

```bash
git add docs/user-manual/wiki
git commit -m "docs: polish wiki manual draft"
```

---

### Task 9: Publish To The GitHub Wiki

**Files:**
- Source: `docs/user-manual/wiki/*.md`
- Destination: `https://github.com/Guru107/sheet_cutting_layout/wiki`

- [ ] **Step 1: Confirm page names for the GitHub wiki**

Map local files to final wiki page names:

```text
Home.md -> Home
Typical-Workflow.md -> Typical-Workflow
Create-a-Layout.md -> Create-a-Layout
Submit-and-Approve-Layouts.md -> Submit-and-Approve-Layouts
Release-and-Generated-BOMs.md -> Release-and-Generated-BOMs
Revisions-and-Supersede.md -> Revisions-and-Supersede
LH-RH-Layouts.md -> LH-RH-Layouts
End-Piece-BOM-Generation.md -> End-Piece-BOM-Generation
Export-and-Download.md -> Export-and-Download
Troubleshooting.md -> Troubleshooting
```

- [ ] **Step 2: Publish the pages to the wiki**

Use the chosen GitHub wiki workflow to create or update each page from the local Markdown source.

- [ ] **Step 3: Verify the live wiki navigation**

Check that:

- the Home page links work
- screenshots load
- advanced pages are reachable
- no page is missing

- [ ] **Step 4: Commit any final source adjustments**

If the publish pass required wording or link changes in the repo source, commit them:

```bash
git add docs/user-manual/wiki
git commit -m "docs: sync wiki source with published pages"
```

---

## Self-Review

### Spec Coverage

Covered:

- end-user-only audience
- full workflow scope
- hybrid task-oriented structure
- real screenshot capture
- separate advanced pages
- troubleshooting page
- GitHub wiki destination

No spec gaps found.

### Placeholder Scan

No `TODO`, `TBD`, or deferred implementation markers remain in this plan.

### Consistency Check

The plan consistently uses:

- `Projects User`
- `Projects Manager`
- `Purchase Manager`
- `MR Coordinator`
- task-first wiki pages under `docs/user-manual/wiki/`

The flow and page names match the approved design spec.
