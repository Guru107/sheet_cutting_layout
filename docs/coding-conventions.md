# Coding Conventions

Follow Frappe/ERPNext conventions unless this repository documents a stricter rule.

## Python & Formatting

- Target Python 3.10+.
- Use Ruff from `pyproject.toml`: 110 character line length, double quotes, tab indentation.
- Keep functions short, explicit, and single-purpose.
- Put the caller above helper functions when a file has multiple related functions.
- Write comments for intent or non-obvious trade-offs, not line-by-line narration.

## Python Practices

- Prefer plain functions and small controller methods before adding classes or service layers.
- Write strict type-safe Python. Add explicit type annotations for public functions, controller
  helpers, service functions, and non-obvious return values; avoid `Any` unless unavoidable.
- Validate inputs early and fail with clear Frappe exceptions such as `frappe.throw`.
- Avoid module-level queries, mutable globals, and work that runs at import time.
- Use `frappe.get_cached_doc` or cached lookups only for stable reference data.
- Keep expensive work out of request hooks; enqueue background jobs when work may block users.

## JavaScript Practices

- Use JavaScript for form interaction, defaults, filters, and progressive UI feedback.
- Keep calculations mirrored on the server when values affect documents, pricing, stock, or reports.
- Prefer `frm` APIs over deprecated globals; avoid new `cur_frm` usage.
- Keep handlers small and move repeated logic into named helper functions.
- Use `frappe.call` for server calls, handle failures, and avoid chatty request loops on field change.

## Frappe Business Logic

- Keep business rules, calculations, validations, and permission-sensitive behavior server-side.
- Use DocType controller hooks such as `validate`, `before_save`, and `on_submit` for document
  lifecycle behavior.
- Mirror behavior in JavaScript only when it improves form usability; never rely on client code as
  the only enforcement path.
- Avoid deprecated globals and APIs such as `cur_frm` in new code.

## Database Access

- Prefer Frappe APIs: `frappe.get_doc`, `frappe.get_all`, `frappe.db.get_value`, and `frappe.qb`.
- Use Query Builder for complex reads that need joins, grouping, or cross-database compatibility.
- Use raw SQL only when the ORM or Query Builder cannot express the query cleanly.
- Always parameterize raw SQL. Do not build SQL with f-strings or `.format()`.
- Add selective filters and consider indexes for frequent reads, while balancing write overhead.

## Naming

- DocTypes: Title Case, singular, US English, no abbreviations.
- Child table DocTypes: parent name plus relation, for example `Sales Order Item`.
- Field names: snake_case slug of the label; table fields should be plural relation names.
- Document variables: slugged DocType name, for example `sales_order`.
- Name variables holding document names with a `_name` suffix.

## User-Facing Text

- Wrap Python user-facing strings with `_()`.
- Wrap JavaScript user-facing strings with `__()`.
- Keep labels and messages clear, sentence case, and free of internal jargon.

## Tests

- Name test files `test_*.py`.
- Prefer Frappe tests that exercise documents, hooks, permissions, calculations, and patches through
  framework APIs.
- Keep test coverage above 96% at all times for project-owned code. Exclude framework, library,
  generated, and vendored code from coverage calculations.
- Run `bench --site <site-name> run-tests --app sheet_cutting_layout` before opening a pull request.
