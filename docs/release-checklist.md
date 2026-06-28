# Release Checklist

## Stable Branch Model

- `develop` is the integration branch
- `release/v1` is the stable `1.x` branch
- release tags must be created from `release/v1`

## Prepare A Release

1. Promote the approved commit set from `develop` into `release/v1`
2. Confirm `sheet_cutting_layout/__init__.py` has the target version
3. Confirm `CHANGELOG.md` has `Unreleased` and the target version heading
4. Run `pre-commit run --all-files`
5. Run `python -m unittest scripts.tests.test_check_release_metadata -v`
6. Run `python scripts/check_release_metadata.py`
7. Run `scripts/run_current_coverage_gates.sh`
8. Confirm GitHub Actions passed on `release/v1`

## Cut The Tag

```bash
git checkout release/v1
git pull --ff-only origin release/v1
git tag -a v1.x.y -m "v1.x.y"  # replace with the actual release tag
git push origin v1.x.y
```

## Verify The Published Release

```bash
gh release view v1.x.y  # replace with the actual release tag
```

Confirm:

- the release exists
- generated notes are present
- the tag points to the expected `release/v1` commit

## Manual Smoke Pass

- run migrate on the target bench
- verify one happy-path layout can still move through approval and release
- verify generated BOM references still appear on the released layout

## Rollback Default

Do not rewrite a published tag by default.

Instead:

1. fix the issue on `develop`
2. promote the fix into `release/v1`
3. bump patch version
4. cut a corrective patch release
