# Changelog

All notable changes to this project will be documented in this file.

The format follows Keep a Changelog, adapted to stay lightweight for this repo.

## [Unreleased]

## [1.0.0] - 2026-06-27

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
