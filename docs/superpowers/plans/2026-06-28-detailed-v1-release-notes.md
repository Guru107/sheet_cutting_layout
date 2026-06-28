# Detailed v1.0.0 Release Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the source-controlled changelog and published `v1.0.0` GitHub Release so they describe the implemented v1 release model, audit cleanup, documentation split, and user-facing application scope.

**Architecture:** Keep `CHANGELOG.md` compact and make the GitHub Release body the fuller reader-facing version. Do not change release tags, branch history, workflow behavior, app code, version metadata, or marketplace README content in this task.

**Tech Stack:** Markdown, GitHub CLI, existing release metadata validator, pre-commit

---

## File Structure

**Modify:**
- `CHANGELOG.md`: source-controlled concise `1.0.0` release summary.

**External release state:**
- GitHub Release `v1.0.0`: published release body updated through `gh release edit`.

**Reference while implementing:**
- `docs/superpowers/specs/2026-06-28-detailed-v1-release-notes-design.md`
- `docs/superpowers/plans/2026-06-26-v1-release.md`
- `docs/superpowers/specs/2026-06-26-v1-release-design.md`
- `docs/release-checklist.md`
- `README.md`

---

### Task 1: Update The Changelog Summary

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Replace the `1.0.0` changelog sections**

Keep the existing title, intro, `Unreleased` heading, release date, and section order. Replace the `### Added` and `### Changed` lists under `## [1.0.0] - 2026-06-27` with:

```md
### Added

- stable `release/v1` branch strategy for `1.x` maintenance, with the release process documented as `develop -> release/v1 -> v*` tags
- release metadata validation for version, changelog, and tag checks before publishing stable releases
- tag-triggered GitHub Release publishing from version tags created on `release/v1`
- maintainer release checklist covering promotion, validation, tag creation, smoke checks, and rollback flow
- Semgrep CI setup using the current Frappe-specific rules from `frappe/semgrep-rules`
- shell-based current coverage gate runner for bench15 and bench16 validation without Python subprocess orchestration
- `docs/development-setup.md` and developer operations docs for local setup and release-maintenance guidance outside the marketplace README

### Changed

- app version promoted from `0.0.1` to `1.0.0`
- CI now validates release metadata on the stable branch
- release metadata now declares the supported Frappe Cloud version range
- marketplace-facing `README.md` now focuses on end-user product behavior and links to dedicated user documentation
- coverage-gate automation now uses direct shell command execution for Frappe marketplace audit compliance
- release documentation now captures the core application scope: controlled Sheet Cutting Layout approvals, BOM generation, revisioning, reusable end-piece handling, and workbook exports
```

- [ ] **Step 2: Verify the changelog text contains no marketplace install patterns**

Run:

```bash
rg -n "bench\\s+get-app|bench\\s+--site\\s+\\S+\\s+install-app|git\\s+clone" CHANGELOG.md
```

Expected: exit code `1` with no matches.

- [ ] **Step 3: Run release metadata validation after the changelog edit**

Run:

```bash
python scripts/check_release_metadata.py
```

Expected: PASS with `Release metadata OK for version 1.0.0`.

---

### Task 2: Draft The Published GitHub Release Body

**Files:**
- External only: `/tmp/v1.0.0-release-notes.md`

- [ ] **Step 1: Write the release body to a temporary file**

Create `/tmp/v1.0.0-release-notes.md` with:

```md
## v1.0.0

`v1.0.0` is the first stable release of Sheet Cutting Layout. It formalizes the `develop -> release/v1 -> v*` release flow, publishes the app from the stable `release/v1` line, and documents the operational checks maintainers should run before future `1.x` releases.

### Application Scope

- controlled Sheet Cutting Layout records for press-part cutting plans
- single-part and LH/RH paired layout support under one approval flow
- checking, PM approval, purchase approval, MR release, reject, supersede, and new-version workflows
- released shearing BOM references generated from approved layouts
- BOM quantity based on `parts_per_sheet`, with raw material quantity tied to full sheet weight
- reusable end-piece capture with separate item and BOM generation after layout release
- `.xlsx` workbook exports for released layouts

### Release Process

- `develop` remains the integration branch for normal feature and maintenance work
- `release/v1` is the stable branch for the `1.x` line
- release tags such as `v1.0.0` are created from `release/v1`
- `CHANGELOG.md` records the versioned release summary and keeps an `Unreleased` section for future work
- `docs/release-checklist.md` documents promotion, local verification, tag creation, GitHub Release confirmation, smoke checks, and rollback flow

### CI And Release Safety

- release metadata validation checks app version, changelog headings, and optional tag/version alignment
- GitHub Actions publish releases from `v*` tags after verifying the tag commit belongs to `release/v1`
- stable-branch CI includes release metadata validation so release prep fails before tag publication
- release metadata declares the supported Frappe dependency range as `>=15.0.0,<17.0.0`

### Audit And Marketplace Readiness

- Semgrep CI uses the current Frappe-specific rule set from `frappe/semgrep-rules`
- coverage-gate orchestration moved from Python subprocess calls to the shell runner at `scripts/run_current_coverage_gates.sh`
- marketplace-facing `README.md` now focuses on end-user capabilities and user documentation
- developer setup and release-maintenance notes live in dedicated docs instead of the long description

### Documentation

- `README.md` describes product scope, roles, workflow, release behavior, revisioning, and recovery
- `docs/development-setup.md` holds developer setup guidance
- `docs/developer-operations.md` holds release-maintenance and automation notes
- `docs/current-app-test-coverage.md` documents the current coverage-gate commands and expectations

### Validation Used For This Release Line

- release metadata validator
- pre-commit workflow checks
- Semgrep with Frappe rules
- bench15 and bench16 current coverage gates through the shell runner
- manual post-release smoke guidance in `docs/release-checklist.md`
```

- [ ] **Step 2: Verify the draft contains no marketplace install patterns**

Run:

```bash
rg -n "bench\\s+get-app|bench\\s+--site\\s+\\S+\\s+install-app|git\\s+clone" /tmp/v1.0.0-release-notes.md
```

Expected: exit code `1` with no matches.

- [ ] **Step 3: Inspect the drafted body**

Run:

```bash
sed -n '1,220p' /tmp/v1.0.0-release-notes.md
```

Expected: body includes the sections `Application Scope`, `Release Process`, `CI And Release Safety`, `Audit And Marketplace Readiness`, `Documentation`, and `Validation Used For This Release Line`.

---

### Task 3: Validate And Commit The Changelog Change

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Run targeted validation**

Run:

```bash
python scripts/check_release_metadata.py
pre-commit run --files CHANGELOG.md
git diff --check
```

Expected:

```text
Release metadata OK for version 1.0.0
```

Expected: `pre-commit` and `git diff --check` pass.

- [ ] **Step 2: Review the changelog diff**

Run:

```bash
git diff -- CHANGELOG.md
```

Expected: only the `1.0.0` changelog bullet lists changed.

- [ ] **Step 3: Commit the changelog update**

Run:

```bash
git add CHANGELOG.md
git commit -m "docs: expand v1 release changelog"
```

Expected: one commit containing only `CHANGELOG.md`.

---

### Task 4: Update The Published GitHub Release

**Files:**
- External only: GitHub Release `v1.0.0`

- [ ] **Step 1: Confirm the release metadata before editing**

Run:

```bash
gh release view v1.0.0 --json tagName,name,url,isDraft,isPrerelease,publishedAt
```

Expected:

```json
{"isDraft":false,"isPrerelease":false,"name":"v1.0.0","tagName":"v1.0.0"}
```

The JSON output may include additional `publishedAt` and `url` fields.

- [ ] **Step 2: Replace the published release body**

Run:

```bash
gh release edit v1.0.0 --notes-file /tmp/v1.0.0-release-notes.md
```

Expected: command succeeds without changing the tag, release name, draft state, or prerelease state.

- [ ] **Step 3: Verify the published body**

Run:

```bash
gh release view v1.0.0 --json tagName,name,url,isDraft,isPrerelease,publishedAt,body
```

Expected:

```text
"tagName":"v1.0.0"
"name":"v1.0.0"
"isDraft":false
"isPrerelease":false
```

Expected: the `body` contains `Application Scope`, `CI And Release Safety`, and `Audit And Marketplace Readiness`.

---

### Task 5: Final Repository Check

**Files:**
- No additional file changes

- [ ] **Step 1: Confirm no unintended files changed**

Run:

```bash
git status -sb
```

Expected: clean working tree on `codex/detailed-v1-release-notes`.

- [ ] **Step 2: Confirm the latest local commits**

Run:

```bash
git log --oneline -3 --decorate
```

Expected: the latest commits include:

```text
docs: expand v1 release changelog
docs: add detailed release notes design
```

- [ ] **Step 3: Report the GitHub release URL**

Run:

```bash
gh release view v1.0.0 --json url --jq .url
```

Expected: prints the `v1.0.0` release URL.

## Trade-Offs

The published GitHub Release duplicates themes from `CHANGELOG.md`, but it gives marketplace reviewers and maintainers a complete release summary without turning the changelog into a long-form release page. The notes mention the coverage gate runner and Semgrep setup because they were part of the v1 implementation and audit cleanup; they avoid setup commands so the release notes do not reintroduce long-description install-instruction patterns.
