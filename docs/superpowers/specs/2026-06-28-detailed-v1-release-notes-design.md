# Detailed v1.0.0 Release Notes Design

## Goal

Replace the terse `v1.0.0` release notes with notes that reflect the v1 release implementation plan and make the release useful to maintainers, reviewers, and marketplace auditors.

## Scope

Update two release-note surfaces:

- `CHANGELOG.md`: compact source-controlled summary for `1.0.0`.
- GitHub Release `v1.0.0`: fuller reader-facing notes using the same themes.

Do not change code, workflows, version metadata, tags, or release branch history as part of this task.

## Source Material

Use the existing implementation artifacts as the source of truth:

- `docs/superpowers/plans/2026-06-26-v1-release.md`
- `docs/superpowers/specs/2026-06-26-v1-release-design.md`
- `docs/release-checklist.md`
- `CHANGELOG.md`
- current `v1.0.0` release state

## Release Note Structure

Group both notes around the implementation plan themes:

- Stable release model: `develop -> release/v1`, `v*` tags, and GitHub Releases.
- Release safety: metadata validator, changelog/version checks, branch reachability expectations.
- CI and audit readiness: release metadata checks, Semgrep/Frappe audit cleanup, shell coverage gate runner.
- Documentation and operations: release checklist, developer operations docs, README marketplace cleanup.
- User-facing application scope: controlled Sheet Cutting Layout release flow, BOM generation, revisioning, end-piece handling, and workbook export.

## Data Flow

Draft the detailed GitHub Release body first from the implementation plan. Condense the same themes into `CHANGELOG.md` so source control and the published release stay aligned without making the changelog too bulky.

## Error Handling

If GitHub rejects release edits because the release is immutable, keep the Git tag unchanged and report the exact limitation. If changelog validation fails, fix the changelog before editing the GitHub Release.

## Validation

Run the smallest checks that prove the release notes are coherent:

- `python scripts/check_release_metadata.py`
- `pre-commit run --files CHANGELOG.md`
- `gh release view v1.0.0 --json tagName,name,url,isDraft,isPrerelease,publishedAt,body`

## Trade-Offs

The GitHub Release will be more detailed than `CHANGELOG.md`. This duplicates themes but avoids turning the changelog into a marketing page while still giving readers a useful release summary.
