# Changelog

All notable changes to this project will be documented in this file.

The format follows Keep a Changelog, adapted to stay lightweight for this repo.

## [Unreleased]

## [1.0.0] - 2026-06-27

### Added

- stable `release/v1` branch strategy for `1.x` maintenance
- release metadata validation for version and changelog checks
- tag-triggered GitHub Release publishing
- maintainer release checklist for branch, tag, and smoke-test operations
- `docs/development-setup.md` for developer bench and local tooling setup

### Changed

- app version promoted from `0.0.1` to `1.0.0`
- CI now validates release metadata on the stable branch
- release metadata now declares the supported Frappe Cloud version range
- coverage gate subprocess calls are inlined for Semgrep audit compliance
- marketplace-facing `README.md` now links to dedicated setup docs instead of embedding install commands
