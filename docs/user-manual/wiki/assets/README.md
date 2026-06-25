# Wiki Screenshot Assets

Use real screenshots from the live app only.

Canonical filename template:

`<page-or-flow>__<step>__<state?>__<index?>.png`

Segment meanings:

- `<page-or-flow>`: the user-facing page, form, or workflow name
- `<step>`: the specific user step shown in the screenshot
- `<state?>`: an optional state such as `draft` or `submitted`; include it only when it helps distinguish what the user sees
- `<index?>`: an optional numeric suffix such as `01` or `02` when one step needs multiple screenshots

Rules:

- prefer lowercase kebab-case filenames
- one screenshot per major user step
- add a zero-padded numeric suffix for multiple screenshots from the same step
- crop for readability, not decoration
- avoid admin-only or developer-only views

Examples:

- `typical-workflow__overview__draft.png`
- `typical-workflow__overview__submitted.png`
- `create-layout__filled__draft.png`
- `release__generated-bom-links.png`
- `release__generated-bom-links__01.png`
