# v1.0.0 Release Design

## Goal

Prepare `sheet_cutting_layout` for a stable `v1.0.0` release with a simple, repeatable, GitHub-only release process.

The release process should:

- keep `develop` as the main integration branch
- introduce a long-lived stable branch for `1.x`
- publish GitHub Releases automatically from version tags
- fail safely when a tag or version is incorrect
- stay small enough for the team to operate without release-engineering overhead

## Scope

This design covers:

- stable branch strategy for `v1.x`
- tag and versioning rules
- GitHub Actions release automation
- changelog and release checklist artifacts
- release validation gates
- hotfix and ongoing `1.x` maintenance flow
- first-release verification and rollback guidance

## Out of Scope

This design does not include:

- PyPI or other package registry publishing
- binary or custom asset packaging
- automatic semantic version bumping
- release-drafter-style long-running automation services
- multi-major support branches beyond `v1`

## Release Model

- `develop` remains the integration branch for ongoing development.
- `release/v1` is the long-lived stable branch for all `1.x` releases.
- Only approved, tested changes move from `develop` to `release/v1`.
- Release tags such as `v1.0.0` and `v1.0.1` are created from `release/v1` only.
- GitHub Releases are published automatically when a `v*` tag is pushed.

### Why This Model

This is the best fit for the repository now because:

- it keeps day-to-day development unchanged
- it gives the release line a stable, reviewable surface
- it avoids the complexity of full release-train tooling
- it makes patch releases straightforward after `v1.0.0`

Alternative fully automatic "merge to stable means release" flows were considered, but they rely too heavily on perfect merge discipline and add unnecessary risk for the first stable release.

## Branch Policy

### `develop`

Purpose:

- receive normal feature and maintenance work
- remain ahead of stable

Rules:

- feature work continues here
- no release tags are created from this branch

### `release/v1`

Purpose:

- hold the production-ready `1.x` line
- receive only promoted changes from `develop`

Rules:

- no direct feature work
- changes arrive by merge or cherry-pick from `develop`
- all release tags must point to commits reachable from this branch
- branch protection should require pull requests and passing checks

## Versioning

Use semantic version tags in the form `vMAJOR.MINOR.PATCH`.

Rules:

- the canonical app version should live in one place
- for this repository, that should be the version field in `pyproject.toml`
- the version in `pyproject.toml` must exactly match the release tag without the `v` prefix
- `CHANGELOG.md` must contain a section for the release version before tagging

Examples:

- tag `v1.0.0` requires version `1.0.0`
- tag `v1.0.1` requires version `1.0.1`

### Why Single-Source Versioning

Keeping one canonical version avoids drift between tags, docs, and automation. It is slightly more manual than auto-bumping, but much easier to audit and recover if a release goes wrong.

## Required Repository Artifacts

### 1. `CHANGELOG.md`

Add a simple changelog using a Keep a Changelog style structure.

Expected shape:

- title and short purpose
- an `Unreleased` section
- versioned sections like `## [1.0.0] - YYYY-MM-DD`

Content should stay human-written and concise. Do not add a complex changelog generator for `v1.0.0`.

### 2. Release Checklist Document

Add a release operations document that covers:

- preparing `release/v1`
- selecting promoted commits
- bumping version and changelog
- running local verification
- creating and pushing the annotated tag
- confirming the GitHub Release
- post-release smoke checks
- rollback steps

This checklist should document human decisions that should not be buried in CI.

### 3. Release Workflow Documentation

Add a short contributor-facing release policy note describing:

- what `release/v1` is for
- where tags must be created
- how hotfixes reach stable

This can live in `README.md`, `AGENTS.md`, or the dedicated release checklist document, but it should exist in at least one obvious place for maintainers.

## GitHub Actions Design

### Tag-Triggered Release Workflow

Create a GitHub Actions workflow that runs on pushed tags matching `v*`.

It should:

1. check out the full git history
2. verify the tag commit is reachable from `origin/release/v1`
3. read the canonical version from `pyproject.toml`
4. fail if the version does not match the tag
5. verify `CHANGELOG.md` contains the target version heading
6. create a GitHub Release for the tag
7. use generated GitHub release notes instead of a custom notes engine

### `release/v1` Validation Workflow

Create or extend a workflow for pushes and pull requests targeting `release/v1`.

It should enforce the stricter release gate:

- repository lint and format checks through `pre-commit`
- the existing server test matrix that matters for stable confidence
- release metadata sanity checks

Release metadata sanity checks should be small and explicit:

- version parses as semantic versioning
- changelog has `Unreleased`
- if a version bump is present, a matching changelog heading exists

### Why Generated GitHub Notes

GitHub-generated notes are good enough for `v1.0.0` and keep the workflow small. A custom release notes pipeline would add maintenance cost without clear value yet.

## Release Flow

### First Stable Release: `v1.0.0`

1. create `release/v1` from the chosen `develop` commit
2. protect `release/v1`
3. add the release artifacts and workflows
4. bump version to `1.0.0`
5. add the `1.0.0` changelog entry
6. run local verification
7. merge the release prep into `release/v1`
8. confirm CI passes on `release/v1`
9. create annotated tag `v1.0.0`
10. push the tag
11. confirm the GitHub Release is published
12. run one manual post-release smoke pass

### Ongoing Minor or Patch Releases

1. promote selected tested commits from `develop` into `release/v1`
2. bump version on `release/v1`
3. update changelog
4. confirm `release/v1` checks pass
5. tag and push `v1.x.y`
6. confirm the published GitHub Release

## Hotfix Flow

Hotfixes should still originate from changes validated on `develop`.

Flow:

1. implement and verify the fix on `develop`
2. merge or cherry-pick the approved fix into `release/v1`
3. bump the patch version on `release/v1`
4. update changelog
5. tag the patch release from `release/v1`

This keeps stable promotion explicit and avoids split-brain development between `develop` and `release/v1`.

Trade-off:

- this is slightly slower for urgent fixes than "stable first" hotfixing
- it is safer because `develop` remains the source of truth for code changes

## Safety Rules

The release process must fail early on common operator mistakes.

Required rules:

- `release/v1` is branch-protected
- direct pushes are blocked unless intentionally allowed for admins
- required checks must pass before merge
- release tags are only valid from `release/v1`
- tag/version mismatch fails the workflow
- missing changelog entry fails the workflow

Recommended if supported by repository settings:

- protect `v*` tags from accidental overwrite

## Verification

Reuse the repository's existing validation philosophy rather than inventing a new release test stack.

Required local verification before tagging:

- `pre-commit run --all-files`
- focused app tests appropriate to the promoted changes
- `python scripts/run_current_coverage_gates.py`

Required CI verification on `release/v1`:

- existing essential server/test matrix
- release metadata checks

Required human verification for `v1.0.0`:

- one manual smoke pass after the GitHub Release is published

The manual smoke pass should confirm at least:

- install or update path still works on the target bench setup
- migration completes cleanly
- a core happy-path document flow still works

## Rollback

Rollback should stay operationally simple.

If a release is bad:

1. stop promoting further changes to `release/v1`
2. prepare a fix on `develop`
3. promote the fix to `release/v1`
4. bump patch version
5. issue a corrective patch release

Do not rewrite or delete a published release tag unless there is no alternative and the repository owners explicitly choose that route. A follow-up patch release is the safer default.

## Recommended Deliverables

To implement this design, the repository should end up with:

- long-lived branch `release/v1`
- `CHANGELOG.md`
- release checklist documentation
- tag-triggered GitHub Release workflow
- `release/v1` validation workflow or equivalent extension of current CI
- version and changelog validation scripts or workflow steps kept as small as possible

## Success Criteria

This release prep is complete when:

- `release/v1` exists and is designated as the stable `1.x` line
- maintainers can cut `v1.0.0` from `release/v1` without undocumented manual knowledge
- an incorrect tag branch or version mismatch fails automatically
- GitHub publishes the release from a pushed tag
- the ongoing `1.x` patch flow is documented and operationally clear
