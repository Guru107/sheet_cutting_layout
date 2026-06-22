# Remove Child Layout End-Piece Links Design

## Goal

Remove the `child_layout` cross-layout feature from end-piece rows. A Sheet Cutting Layout will be self-contained: its own `end_pieces` table has the data needed to create the main BOM, generated end-piece Items, and Used-for-Part BOMs.

## Scope

In scope:

- Remove `child_layout` from the `Layout End Piece` DocType.
- Remove child-layout validation, raw-material matching, cycle detection, and descendant traversal.
- Remove recursive release/export behavior that follows `child_layout` links.
- Remove or rewrite tests that exist only for child-layout recursion.
- Keep local end-piece BOM behavior: Reuse/Scrap disposition, strip width/length/weight, generated end-piece item code, Used-for-Part BOM generation, and Excel end-piece block population.

Out of scope:

- No replacement link field.
- No cross-layout BOM tree.
- No runtime compatibility path for old `child_layout` values.
- No data migration unless explicitly requested later.

## Architecture

The layout model becomes local-only:

- `Sheet Cutting Layout` owns raw material, finished part data, strip/sheet dimensions, and its local end pieces.
- `Layout End Piece` describes only a local end piece.
- `release_service` releases the current layout and generates BOM artifacts from the current document only.
- `export_service` exports the selected layout only.
- `validators` validate local calculations and item references only.

Removed responsibilities:

- Child layout raw-material validation.
- Child layout cycle detection.
- Descendant layout collection.
- Descendant cancellation/release ordering.
- Recursive workbook sheet expansion.
- Recursive child-layout permission checks during download.

## Data Flow

Release flow:

1. Validate the current layout.
2. Generate the current layout's main BOM from its sheet/part fields and local end-piece rows.
3. Generate Used-for-Part BOMs for local Reuse end-piece rows.
4. Persist generated BOM links on the current layout and its local rows.

Export flow:

1. Load the selected layout.
2. Build one workbook for that layout.
3. Populate the layout and local end-piece details.
4. Return the workbook.

## Error Handling

The following errors disappear because the feature disappears:

- Child layout raw material mismatch.
- Child layout cycle.
- Child release ordering.
- Missing child layout read permission during recursive export.

Existing validations remain:

- Reuse rows require used-for part, BOM quantity, valid strip dimensions, and valid weight split.
- Scrap rows require a scrap item.
- Generated end-piece item codes remain locked after generation.
- LH/RH reusable end-piece naming keeps using primary+twin part codes.

Old database rows containing `child_layout` are ignored after the field is removed from the DocType. The implementation will not add compatibility branches for stale links.

## Testing

Update coverage to match the new behavior:

- Remove tests dedicated to child-layout links, recursive release, recursive export, child raw-material guards, and child permission checks.
- Add or update schema tests to assert `child_layout` is absent from `Layout End Piece`.
- Keep focused tests for validators, release service, end-piece BOM service, export/download service, and strip-weight behavior.
- Run full app tests with `bench --site development.localhost run-tests --app sheet_cutting_layout`.
- Run `pre-commit run --all-files` or the focused touched-file equivalent during implementation.

## Trade-Offs

This removes an implicit multi-layout workflow and makes each layout easier to reason about. Existing records that depended on `child_layout` will no longer receive recursive export or release behavior. If bulk export or multi-layout BOM workflows are needed later, they will be designed as explicit features instead of hidden behind end-piece rows.
